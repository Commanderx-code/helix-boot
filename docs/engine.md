# The engine, and how it keeps a stick safe

`install.sh` and `refresh.sh` are thin wrappers around `helix`, a single
standard-library Python script:

| Command | Does |
|---|---|
| `helix list` | every tool, its source, and whether it's enabled |
| `helix check [--json] [--outage-ok]` | compares your cache against upstream, no downloads |
| `helix fetch [tool…] [--force] [--outage-ok]` | downloads, verifies and caches (`~/.cache/helix-boot`); resumes interrupted downloads; when a tool's site is down, keeps the copy already verified |
| `helix sync <mount> [--dry-run] [--verify] [--prune-unknown]` | copies the cache to a Ventoy stick, replaces old versions, writes the menu; `--dry-run` ends with what it would copy, remove and keep |
| `helix pack [file.zip] [--need-app]` | the whole stick, your own tools and Ventoy in one zip, named `helix-boot-<version>-<date>.zip` |
| `helix unpack <pack.zip> <mount> [--dry-run] [--verify] [--prune-unknown]` | fills a Ventoy stick from a pack, no downloads |
| `helix theme <mount> [--theme ID] [--icons ID] [--background PIC] [--splash PIC] [--menu] [--preview FILE]` | shows or changes a stick's look ([themes](look.md#the-boot-menus-look)); `--export ZIP` / `--import ZIP` save and load it |
| `helix verify <mount> [--json]` | reads the stick back and finds damaged or missing files, no downloads ([checking a stick](#checking-a-stick)) |
| `helix test <mount> [--gb N]` | writes the stick's free space full, reads it back and deletes it: finds a failing or fake stick ([testing a stick](#testing-a-stick)) |
| `helix splash <VTOYEFI mount>` | adds the splash to Ventoy's boot script (`install.sh` and `refresh.sh` run it) |

`linux/helix_gui.py` is the Windows app's window on Linux. It imports
`windows/helix_boot.py` and replaces what is Windows' own: the list of disks
(`lsblk`), where a stick's files are (its mount point, through udisks),
Ventoy's installer (its Linux script, as root through `pkexec`) and Repair
stick (`fsck`). The window, the install and update steps and their safety
checks are the same code on both systems.

Only those two steps run as root. Your cache is yours to write, so root is
never pointed at a script in it: it gets Ventoy's archive and the checksum that
archive was verified against when it was downloaded, copies the archive to a
folder only root can write, checks the copy, unpacks it there and runs
Ventoy's script from there. Root's own programs (`pkexec`, `fsck`) are taken
from the system's folders, never found on your `PATH`.

`theme.sh` and `check.sh` wrap `helix theme` and `helix verify` the same way:
they find and mount the stick first.
Pillow is the one optional extra: with it the engine draws previews, the
splash's loading bar and greyscale icons, and resizes your pictures; without it
those are skipped and everything else works.

## Verification

Each tool lists checksum strategies in order of preference. The first one
that yields a hash is used; a mismatch deletes the file and stops:

1. the publisher's checksum file (`sha256.txt`, `CHECKSUMS.TXT`, `*.sha512`)
2. GitHub's recorded sha256 digest for the release asset
3. SourceForge's md5 (integrity only)
4. `tofu`: trust-on-first-use, **only if the manifest explicitly says so**.
   The hash is recorded, and a re-download of the same version with a
   different hash is refused as possible tampering.

If no strategy works, the tool is refused rather than silently used.

## Checking a stick

Cheap USB sticks can go bad without warning: a file reads back wrong, and a
tool fails to boot just when you need it. `./check.sh` (or **Check stick** in
the app) reads every boot image and app back off the stick. It compares them
with the checksums recorded when they were copied. Those come from the download
or the pack, never from the stick itself. It needs no cache and no internet,
so any PC can check any Helix Boot stick. It takes about as long as copying
the stick.

A damaged image is noted on the stick, and the next update copies it again,
even a quick one. An app file that differs is reported separately, because
some tools save their settings in their own folder; it still counts as a
finding (`helix verify` exits non-zero, and the app shows it as a problem),
since a changed program file looks the same.

The stick remembers the days a check found files gone bad. Once can be a bad
write or a stick pulled out too soon. If it happens again after an update
repaired it, the check says so and says to replace the stick.

A stick whose filesystem is damaged is another matter: files can't be read at
all (an "Input/output error"), and an update can't fix that. The engine, the
Windows app and the Mac tool then stop and give the repair command for the
system they run on (`fsck` on Linux, `chkdsk` on Windows, `diskutil
repairVolume` on a Mac). Repair it, update, and check the stick.

A check is only useful if it happens. The stick records the day it was last
read back in full, and an update says so once that is over 30 days ago.

## Testing a stick

`helix test <mount>` (`./install.sh --test`, `helix-mac install --test`, or
**Install tests the stick first** in the Windows app) is for a stick you are
about to trust. It fills the free space with data that is different in every
megabyte, reads all of it back from the stick itself, and deletes it. A stick
that drops writes fails, and so does a fake that claims more room than it has:
those wrap round and overwrite what they were given, so the first megabytes
read back wrong. Nothing already on the stick is touched. An installer that
runs the test stops before copying anything onto a stick that fails. It writes
and reads the whole stick, so expect it to take as long as two full copies.
`--gb N` tests only the first N GiB, which is quicker but can't find a fake.

## When a tool's site is down

A site that answers with a server error, or not at all, is tried four times. If
it stays down, `helix fetch` keeps the copy of that tool it fetched and verified
before, says so, and carries on; an update of your stick then uses that copy.
Only a tool never fetched on this PC is reported as failed. `--outage-ok` turns
that failure into a warning too, and `helix check --outage-ok` does the same
for a site it can't ask. CI uses both on a push, where an outage elsewhere says
nothing about the commit; its weekly run stays strict, so a site that is gone
for good still shows.

## Releasing

`scripts/release.sh 0.7.1 "what is new"` does a release in the one order that
works. It checks that `main` is clean, pushed and passes the tests, moves
`CHANGELOG.md`'s Unreleased section under the new version, shows the release
notes and asks, then commits, tags and pushes. It waits for the build on GitHub
to publish the release, and only then fetches and makes the pack
(`helix pack --need-app`), so the pack carries that release's `HelixBoot.exe`.
A pack made too early would carry the one before; `helix pack` warns when that
happens. `--no-pack` skips the pack and `scripts/release.sh --pack` makes only
the pack.

An update with `--verify` (`install.sh` always, `refresh.sh --verify`, and
every Update from the Windows app) checks the apps' files as well as the boot
images, and copies an app again when any of its files is missing or differs.
That puts back settings a tool saved in its own folder, so copy those off
first if you want to keep them.

Apps copied by Helix Boot 0.6.5 or older aren't recorded yet. The next update
records them.

## Safety

- `install.sh` downloads and verifies everything **before** touching any disk.
- It lists only USB/removable disks and refuses any disk holding your running
  system, following LUKS, LVM and btrfs back to the physical disk.
- You type the device name to confirm, and it warns if the "stick" is
  suspiciously large. A new stick is named `HelixBoot` (`stick_label` under
  `[settings]`), and is recognised later whatever you rename it to.
- `refresh.sh` removes a tool from the stick only when it brings a newer copy of
  it, the tool is switched off, or this PC put it there and no longer has it.
  The stick records which PC put each tool on it, so updating from a second PC
  leaves the first one's tools alone ([more](#updating-from-more-than-one-pc)).
- Nothing read from a pack or from a stick (paths, app names) can reach outside
  the stick: a crafted pack or a stick tampered with on an infected PC can't
  write or delete anything else.
- Lazarus PE and the Helix Apps menu only accept a USB/SD disk as the stick
  (tag file, no Windows on it), so a tag planted on the PC being repaired can't
  get its script run. They need PowerShell to tell which disks are USB; where
  it's missing they run nothing by themselves, and you open the stick's `Apps`
  folder by hand.
- The disk you confirm is the disk that gets written. Between your confirmation
  and each write, the scripts and the Windows app check it is still the same
  device (Linux: the kernel's disk sequence number; Windows: its serial, or the
  device id Windows gave it), still USB, and not the system disk. A stick
  swapped under the same name stops the run.
- A stick is only written if it is a plain file tree. A symlink, a Windows
  reparse point or a hard link anywhere on it is refused before anything is
  changed, since one could send a write somewhere else. Keep the stick mounted
  by one system only while it's updated.
- Files are written under a fresh, unguessable temporary name and then moved
  into place, so nothing planted under a predictable name gets written through.
- `refresh.sh --dry-run` changes nothing, so it can't be combined with
  `--upgrade-ventoy` or `--eject`.

## Updating from more than one PC

An update removes a tool from the stick only when it brings a newer copy of
that tool, you switched the tool off in `local.toml` (`enabled = false`), or
the PC that put it there no longer has it. Tools from another PC stay where they are, with their
names, tips and icons in the menu: your paid tools when you update from the
Windows app on a second machine, or a tool whose download just failed. The run
lists what it kept; `./refresh.sh --prune-unknown` removes them. The stick's own
icons and splash stay the same way when the updating PC has none of its own.
