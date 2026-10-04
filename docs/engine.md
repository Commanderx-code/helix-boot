# The engine, and how it keeps a stick safe

`install.sh` and `refresh.sh` are thin wrappers around `helix`, a single
standard-library Python script:

| Command | Does |
|---|---|
| `helix list` | every tool, its source, and whether it's enabled |
| `helix check [--json]` | compares your cache against upstream, no downloads |
| `helix fetch [tool…] [--force]` | downloads, verifies and caches (`~/.cache/helix-boot`); resumes interrupted downloads |
| `helix sync <mount> [--dry-run] [--verify] [--prune-unknown]` | copies the cache to a Ventoy stick, replaces old versions, writes the menu; `--dry-run` ends with what it would copy, remove and keep |
| `helix pack [file.zip]` | the whole stick, your own tools and Ventoy in one zip |
| `helix unpack <pack.zip> <mount> [--dry-run] [--verify] [--prune-unknown]` | fills a Ventoy stick from a pack, no downloads |
| `helix theme <mount> [--theme ID] [--icons ID] [--background PIC] [--splash PIC] [--menu] [--preview FILE]` | shows or changes a stick's look ([themes](look.md#the-boot-menus-look)); `--export ZIP` / `--import ZIP` save and load it |
| `helix verify <mount> [--json]` | reads the stick back and finds damaged or missing files, no downloads ([checking a stick](#checking-a-stick)) |
| `helix splash <VTOYEFI mount>` | adds the splash to Ventoy's boot script (`install.sh` and `refresh.sh` run it) |

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
since a changed program file looks the same. If a fresh copy goes bad again,
replace the stick.

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
