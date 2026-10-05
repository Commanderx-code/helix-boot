# Changelog

Notable changes to Helix Boot (called Commander Rescue before 0.5.0). Versions
follow `helix --version` (`crescue --version` before 0.5.0);
tagged releases also publish the Windows app.

## [Unreleased]

### Security
- The Windows app runs Windows' own programs (PowerShell, and `chkdsk` for
  Repair stick) by their full path in the system folder. It runs with admin
  rights, and a program looked up by name could be a file of that name in the
  folder the app was started from. For the same reason 7-Zip is only taken
  from where its installer puts it on Windows, which also means an installed
  7-Zip is now found there at all.

### Fixed
- `helix-mac --eject` tries again when macOS still holds the stick for a
  moment after writing, and says to eject it in Finder if it stays busy,
  where it stopped with an error after a finished update.

### Added
- **Testing a stick before you rely on it.** `helix test <mount>` writes the
  stick's free space full of data that is different in every megabyte, reads it
  all back and deletes it. A failing stick and a fake one (less room than it
  says) can't pass. `./install.sh --test`, `helix-mac install --test` and
  **Install tests the stick first** in the Windows app run it on the new stick
  before anything is copied on, and stop if it fails.
- **A reminder to check the stick.** The stick records when it was last read
  back in full. An update says so once that is over 30 days ago, since a check
  nobody runs finds nothing.
- **Repair stick** in the Windows app has Windows repair the stick's
  filesystem (`chkdsk /f`), after asking. Also `HelixBoot.exe --repair E:`.
- **A one-file download for Intel Macs:** `HelixBoot-mac-x86_64`, beside the
  Apple Silicon one, built and tried on an Intel Mac in CI.
- The weekly CI run opens an issue when it fails, naming the tools that
  couldn't be resolved, since on a push a site that is down is only a warning.

## [0.7.1] - 2026-10-04

### Added
- **A stick with a damaged filesystem gets a repair command, not a raw error.**
  When the stick answers with a disk error (an "Input/output error"), an
  update or a check stops and says its filesystem is damaged, with the command
  to repair it on that system: `fsck` on Linux, `chkdsk` on Windows, `diskutil
  repairVolume` on a Mac. The Windows app and the Mac tool say the same.
- **The stick remembers damage.** A check that finds files gone bad notes the
  day on the stick, and updates keep that note. If files go bad again after an
  update repaired them, the check says it is the second time and to replace the
  stick.
- **`scripts/release.sh`** cuts a release in the one order that works:
  version, changelog, tag, the build on GitHub, and only then the pack. See
  [Releasing](docs/engine.md#releasing).
- CI lints with ruff, which also flags syntax that Python 3.11 doesn't accept.

### Changed
- **A site that is down no longer fails a fetch of a tool you already have.**
  `helix fetch` keeps the copy it fetched and verified before, says so, and
  carries on. `--outage-ok` (on `fetch` and `check`) makes a tool that was
  never fetched a warning too; CI uses it on a push and stays strict in its
  weekly run.
- **Packs are named for their version:** `helix-boot-<version>-<date>.zip`,
  so a pack of a new release doesn't overwrite the one made the same day.
- `helix pack` warns when the `HelixBoot.exe` it carries is older than the
  engine, which is what a pack made before a release is published gets;
  `--need-app` refuses to make such a pack.
- The Pillow the boot tests draw with is pinned and checksummed, like the
  build tools.

## [0.7.0] - 2026-10-04

### Security
- The released programs are built with pinned, checksummed versions of their
  build tools (PyInstaller, Pillow, certifi), where the build took whatever
  was newest that day. Dependabot proposes updates.

### Added
- **A one-file download for Mac:** `HelixBoot-mac-arm64` in each release is
  `helix-mac` with Python and the engine inside, for Apple Silicon. It isn't
  signed by Apple, so macOS needs telling to let it run (the README says
  how). `helix-mac helix …` reaches the engine's own commands.
- **`Tools.txt` at the top of the stick:** every tool on it and its version,
  by where it is in the boot menu, and the tools another PC put there.
- The Windows app's progress bar says how much has been copied and of how
  much ("12.3 GB / 37.0 GB").

### Fixed
- On Windows, reading a file back after copying it, and **Check stick**, could
  be answered from Windows' memory and not from the stick. Files are now read
  back unbuffered there, so the check is of what is really on the stick.

### Changed
- **GitHub's hourly limit is no longer in the way.** A PC that isn't signed in
  gets 60 API requests an hour, and there are over 30 GitHub-hosted tools. The
  engine now asks github.com where a repo's "latest release" leads, which is
  not an API request, and only asks the API when that tag isn't the one it
  saw last. A refresh with nothing new costs no API requests.
- **An update that verifies reads the stick once.** The summary shown first
  read every file, and the update then read them all again. What was read for
  the summary now stands, for half an hour and while a file is unchanged.
- **A tool's own settings aren't taken for damage.** A `.ini`, `.cfg`, `.conf`
  or `.log` file a tool rewrote in its folder (and any file a tool names with
  `settings = [...]`, as Notepad++ does for its `.xml`) no longer makes an
  update copy the tool again, or Check stick report it. A changed program file
  still does both.

## [0.6.14] - 2026-10-04

### Added
- **Updating a stick from a Mac:** `mac/helix-mac` finds the stick, shows what
  an update will copy, remove and keep, asks, updates it (from the internet or
  a pack), and adds the splash and the L / F1 keys, as on Linux. Also
  `helix-mac check`, `look` and `list`. CI runs a whole update on a real Mac,
  against a disk image partitioned like a stick. On most sticks macOS won't
  mount Ventoy's partition by itself, so it is mounted directly, which asks
  for your password.
- **Creating a stick on a Mac (experimental):** `mac/helix-mac install --disk
  disk4`. Ventoy has no installer for macOS, so the engine writes Ventoy's MBR
  layout itself (`ventoy_layout`), as Ventoy's installer does on Linux, with
  Secure Boot support as shipped. Only a USB or SD disk that isn't inside the
  Mac can be erased, after its name is typed. CI makes a stick on a Mac and
  boots that disk in a virtual PC, on UEFI and BIOS. The boot test builds its
  disks with the same code.

### Changed
- Release pages carry that version's section of this changelog, and how to
  check a download (`scripts/release-notes.sh`).
- The README is shorter: the engine's commands, verification, checking a stick
  and the safety rules are in [`docs/engine.md`](docs/engine.md); themes, icons
  and splash in full are in [`docs/look.md`](docs/look.md). Its screenshots
  are retaken, and it shows the Windows app.

## [0.6.13] - 2026-10-04

### Security
A hardening pass over what gets written, and where:
- **The disk you confirm is the disk that is written.** `install.sh`,
  `refresh.sh --upgrade-ventoy` and the Windows app check, between your
  confirmation and each write, that it is still the same device (Linux: the
  kernel's disk sequence number; Windows: the disk's serial, or the device id
  Windows gave it), still USB, and not the system disk.
- **A stick must be a plain file tree.** A symlink, a Windows reparse point or
  a hard link anywhere on the target is refused before anything is changed.
- **No predictable temporary names.** Files are staged under a fresh random
  name before being moved into place (downloads onto the stick, the pack,
  Ventoy's boot script, the lock file).
- **Lazarus PE and Helix Apps run nothing without proof the stick is USB.**
  The fallback that scanned drive letters when PowerShell was missing is gone.
- A pack's Ventoy version and its tree patches are validated before use, and
  the cache folder a pack's Ventoy is unpacked into can't be a link.
- Tar archives are only unpacked with Python's safe extraction (3.11.4+).
- A download that changed upstream without a version bump is no longer
  accepted with `--force`; the message says how to accept a file you checked.

### Changed
- `--verify` on an update checks the apps' files too, and copies an app again
  when any differ; the Windows app's update summary now counts those. This
  puts back settings a tool saved in its own folder.
- `helix verify` and **Check stick** count a changed app file as a finding
  (exit status 1), where it was a note before.
- `refresh.sh --dry-run` can't be combined with `--upgrade-ventoy` or `--eject`.
- A tool of your own that is an app is versioned by its content, so a changed
  file under the same date is noticed.

### Fixed
- The new device check refused every stick that reports no serial number to
  Windows, which many do. Such a stick is now known by the device id Windows
  gives it.
- The new link check stopped on a folder only the system may read
  (`System Volume Information` on an NTFS stick, `lost+found` on ext4). Those
  are left alone; any other unreadable folder gives a plain message.

## [0.6.12] - 2026-10-04

### Security
- The Mac check in CI printed text taken from the downloads (an app's name,
  its version, who signed it) into the log as it was. It is now made safe
  first, so a download can't pass commands to the CI runner that way.

### Added
- The stick's `Mac/README.txt` says which macOS each tool needs ("Needs macOS
  15.6 or newer"), from a new `macos` line per tool in `tools.toml`. The Mac
  job in CI fails, naming the line to change, when an app's own requirement
  no longer matches.

## [0.6.11] - 2026-10-04

### Security
- A tool whose download link is read from a web page (`source = "page"`) took
  any link on that page that matched its pattern, whatever site it pointed to.
  Only links to the page's own site are taken now, or to a site the tool names
  in `hosts`, and never one that drops from https. No shipped tool resolved to
  a wrong link; this closes the gap.

### Added
- Ten more tools for a Mac: DMDE (recovery), Vorta for Apple Silicon and for
  Intel (backup), Maintenance for macOS 26, 15 and 14, Pearcleaner
  (uninstaller), Keka (archives), and Objective-See's Netiquette and
  BlockBlock.
- RustDesk (remote support) and balenaEtcher (writes boot sticks) for a Mac,
  each for Apple Silicon and for Intel.
- CI checks the tools for a Mac on a real Mac: each download is opened as
  macOS would open it, and the app or installer inside must be whole. It
  reports who signed each one and whether Gatekeeper accepts it
  (`tests/mac/check_tools.py`).

## [0.6.10] - 2026-10-04

### Fixed
- An app with no version number of its own (Sysinternals, ProduKey, OnyX, …)
  was copied again whenever the stick was updated from a PC that had fetched
  it on a different day, though the files were the same. They are now compared
  by their checksum.

## [0.6.9] - 2026-10-04

### Changed
- The Windows app has a new look: dark and compact, in the boot menu's colours.
  The stick is picked from a drop-down, Install and Update are the two big
  buttons, the progress bar shows its percentage, and the log is behind
  **Show log**. The Look window matches.
- The project has a logo, the HB mark: in the app's header, as the icon of
  `HelixBoot.exe` and its windows, and at the top of the README.

### Fixed
- The Look window's preview didn't draw the menu's row of hotkey icons.

## [0.6.8] - 2026-10-03

### Added
- The boot menu's hotkeys are a row of icons, each with its key above it
  (a folder for F2 Browse, a hard disk for F4 Local boot, …), in place of
  Ventoy's line of words. On the Helix themes; Standby and Poly dark keep
  Ventoy's line.
- On those themes **L opens a power menu** (reboot, power off, firmware setup)
  and **F1 starts Memtest86+**, in place of Ventoy's Language and Help. This
  needs a hook in Ventoy's boot script, which `install.sh`, `refresh.sh` and
  the Windows app add next to the splash. Where it can't be added, the row
  shows Language and Help, which is what the keys do there.
- **The Windows app adds the splash** (and that hook) to Ventoy's boot script
  on Install and Update, as the Linux scripts do. Until now a stick made on
  Windows had no splash until it was refreshed from Linux.
- `HelixBoot.exe` carries its product name and version (Properties > Details).
- `check_for_updates = false` under `[settings]` in `local.toml` stops the
  Windows app looking for newer versions of the tools when it starts.
- A [code signing policy](docs/code-signing.md), with a privacy policy: what
  the app contacts, what it changes on your PC, and how to remove it.

### Fixed
- A download that stalled part-way (a timeout or a dropped connection while
  reading) stopped the whole fetch with a raw error. It is now resumed from
  where it stopped, a few times, before giving up with a plain message.

## [0.6.7] - 2026-10-03

### Changed
- The HELIXBOOT icon collection is the one icon set. Every master in
  `docs/artwork/helix-icons/` is rebuilt from it, Super GRUB2 Disk has the
  collection's icon, and the rest of the collection (51 icons for tools that
  aren't shipped, and spare variants) is in `docs/artwork/helix-icons/more/`.
- Windows 10 Recovery and Windows 11 Recovery, two tools people add themselves,
  have the collection's recovery icon in the default set.

- The default theme has a new splash: the HB logo and wordmark over a night
  landscape (`docs/artwork/helix-splash.png`). The presets keep theirs.

### Removed
- The `classic` icon pack and its source artwork (`docs/artwork/tool-icons/`).
  A stick whose look asked for it shows the default icons after its next
  refresh. A tool without an icon gets a letter badge.

## [0.6.6] - 2026-10-02

### Added
- **Checking a stick:** `./check.sh`, `helix verify`, and **Check stick** in the
  Windows app (also in `HelixBoot.sh`'s menu). They read every boot image and
  app back off the stick and compare them with the checksums recorded when they
  were copied, to find a stick that's going bad. No downloads are needed. A
  damaged image is copied again by the next update, even a quick one. Apps are
  now recorded in `.helix-boot/hashes.json`, from the download or the pack.
- **Saved looks:** `theme.sh --export` / `--import`, and **Save look…** /
  **Load look…** in the Look window. They save a stick's look, with your own
  pictures and icons, to a small zip and put it back on any stick.
- The Windows app says, under its title, which tools have newer versions than
  this PC has. It looks upstream at most every 6 hours, to stay inside GitHub's
  limit for PCs that aren't signed in. `HelixBoot.exe --updates` prints the same.
- Releases carry a `SHA256SUMS` file and a GitHub build attestation for
  `HelixBoot.exe` and `HelixBoot.sh`
  (`gh attestation verify HelixBoot.exe --repo Commanderx-code/helix-boot`).

### Fixed
- A stick filled from a pack didn't record its boot images' checksums, so a
  later quick update from Linux trusted their size alone.

## [0.6.5] - 2026-10-02

### Fixed
From a review of everything since 0.5.3:
- A stick's own icons and splash could be lost for good if an update from
  another PC failed half-way: they were moved aside first. They now stay in
  place.
- On a stick last written by 0.6.1 or older, a tool could be taken for an old
  version of another whose file name differed only in a number
  (`windows10.iso`, `windows11.iso`) and be removed. Only a download named after
  its version is matched that way now.
- A stick given a name of your own (`stick_label`), or renamed, was refused by
  `refresh.sh` and Update if its first fill had been cut short. It is known by
  Ventoy's own partition beside it.
- In the Windows app, **Apply** in the Look window could run while an update
  was copying. The Look window now holds the app while it is open.
- A dry run, and the app's update summary, listed an image that only moves
  folder as one to be removed.
- A `look.json` on the stick with a value this version doesn't know crashed
  `theme.sh` and left the Look… button doing nothing.
- In the Look window, a picture chosen but not sent was treated as already on
  the stick after Apply.
- A boot menu or theme file that couldn't be written on Windows was reported
  as "in use" and the update still ended as a success; only the running app's
  own file is let through now.
- `refresh.sh <folder>` stopped with an error after a good sync when the folder
  wasn't on a plain partition.

### Changed
- A refresh that changes nothing writes nothing to the stick's theme: the
  theme on the stick is updated in place, and the boot menu is only rebuilt
  when what it is built from changed.

### Added
- Icons in the default set for the two entries that still had their classic
  ones: Lazarus PE (the phoenix on a glossy badge, drawn by
  `docs/artwork/helix-icons/make-lazarus-pe.py`) and Super GRUB2 Disk.

## [0.6.4] - 2026-10-02

### Added
- **Helix Boot on the stick itself**: every stick gets a `HelixBoot` folder with
  the latest released `HelixBoot.exe` and `HelixBoot.sh` and a short README, so
  it can be updated, or its look changed, from any PC without downloading
  anything first.
- **An update says what it will do before it does it.** `HelixBoot.exe` shows
  what **Update stick** will copy, remove and keep, and asks before writing
  when anything is copied or removed. `helix sync --dry-run` and
  `helix unpack --dry-run` end with the same summary.
- **A new stick is named `HelixBoot`** instead of `Ventoy` (`stick_label` under
  `[settings]`; `"Ventoy"` keeps Ventoy's own).
- `tests/boot/boot_menu.py` boots the menu in QEMU with every theme, on UEFI
  and BIOS, and checks each came up; CI runs it on every push and keeps the
  screenshots.

### Fixed
- An update from a PC without your `local.toml` removed a tool that is switched
  off as shipped but that you had switched on (Kaspersky Rescue Disk): it took
  "off here" as a reason to remove it. Only a tool switched off by hand in that
  PC's own `local.toml` counts now.

### Changed
- A file on the stick that hasn't changed isn't written again on every
  refresh, and one that is in use (the app updating the stick from the stick,
  on Windows) no longer stops the run: it is replaced next time.

## [0.6.3] - 2026-10-02

### Changed
- **New default icons**: every tool, category and Ventoy entry now has an icon
  from one glossy set, the HELIXBOOT icon collection, the same on every theme
  (the presets no longer recolour the category icons). The set before it, each
  tool's own logo with flat category icons, is the `classic` icon pack:
  `./theme.sh --icons classic`. Masters are in `docs/artwork/helix-icons/`.
- A stick keeps its own icons and splash (the ones from a `byo/` folder) when it
  is updated from a PC that has none of its own, instead of getting the stock
  ones back. The PC that put them there still replaces or removes them.

## [0.6.2] - 2026-10-02

### Changed
- **An update no longer strips a stick of tools the updating PC doesn't have.**
  Updating from a second PC (the Windows app without your `byo` files, say)
  used to remove every paid or bring-your-own tool, and a tool whose download
  had just failed. Now a managed file is removed only when the same tool was
  brought again (a newer version) or the tool is switched off; the rest stay,
  keep their names, tips and icons in the boot menu, and the run says which
  were kept. `--prune-unknown` (`helix sync`, `helix unpack`, `refresh.sh`)
  removes them as before. The stick records which tool each image belongs to;
  a pack says which tools were switched off where it was made.

### Fixed
- `HelixBoot.exe` failed to download from some sites with
  `CERTIFICATE_VERIFY_FAILED` (Hiren's, OnyX): Windows hadn't fetched their
  root certificate yet. It now also trusts the certifi bundle.
- A stick whose data partition was renamed (to anything but `Ventoy`) wasn't
  recognised: the Windows app showed it as not having Ventoy, so **Look…** and
  **Update** refused it, and `refresh.sh` / `theme.sh` didn't find it. A stick
  is now known by Ventoy's own `VTOYEFI` partition, whatever the other is called.
- The Look window fits a short screen (a 1366×768 laptop, a small VM window): its
  preview is smaller there, so the buttons no longer end up under the taskbar.

## [0.6.1] - 2026-10-02

### Added
- **Tools for a Mac**, in a `Mac` folder on the stick with a `README.txt`: 18
  free utilities to run on a working Mac (EtreCheck, OnyX, Malwarebytes, the
  Objective-See tools, Stats, Macs Fan Control, coconutBattery,
  GrandPerspective, AppCleaner, SuperDuper!, TestDisk & PhotoRec, Mist,
  OpenCore Legacy Patcher, Chris Titus Tech's MacUtil), fetched, verified and
  kept current like everything else. `platform = "mac"` on an app puts it
  there, as downloaded, and packs carry them.
- Two more themes for `theme.sh` and the Look window, both other people's GRUB
  themes with their own layout, adapted for Ventoy: **Standby** (Llewelyn
  Trahaearn, GPL) and **Poly dark** (Andrei Shevchuk, MIT), each with a splash
  in its colours. A preset can now bring its own layout and fonts
  (`standalone = true` in `preset.toml`).
- Greyscale icons: `--icons grey` redraws every icon, yours included, in shades
  of grey. Standby and Poly dark use it by themselves: the icon choice now
  defaults to `auto`, the theme's own style, and `--icons logos` keeps colour.

### Changed
- Standby is the plain choice, in place of Ventoy's own white look: "Off" is no
  longer on the theme list, and `--theme off` (or a stick that had it) gives
  Standby. `theme = ""` in `local.toml` still gives Ventoy's own look.

### Fixed
- The look preview follows each theme's own layout, boxes and font sizes.

## [0.6.0] - 2026-10-01

### Added
- **Change a stick's look**: `./theme.sh` (`helix theme`) switches a finished
  stick between preset themes (Midnight, Ember, Terminal, Slate, beside the
  default Helix Neon), icon packs (the logos, letter badges, your own in
  `byo/icon-packs/`), your own background (`--dim` darkens it) and splash, or
  turns the icons or the whole theme off for Ventoy's own look. The choice is
  kept on the stick, so a refresh doesn't undo it, and packs carry the presets.
  `./theme.sh --menu` (and `HelixBoot.sh`'s menu) asks with numbered lists, the
  Windows app has a **Look…** window with a live preview (`HelixBoot.exe --look`
  from the command line), and `--preview FILE` draws the menu without changing
  the stick. `HelixBoot.exe` now includes Pillow for that.
- **A splash before the Ventoy menu**: the HELIXBOOT logo over the theme's
  artwork for about a second with a loading bar filling up, or your own
  `byo/splash.png`; `splash_seconds` sets how long. The bar's frames are made
  with Pillow at refresh; without it the splash is a still picture. `helix splash` adds it to Ventoy's boot
  script on the VTOYEFI partition; `install.sh` and `refresh.sh` run it, also
  after a Ventoy upgrade, and a Ventoy laid out differently is left alone.
- `theme/build-theme.py --fit-icons` shrinks your icons in `byo/icons/` to the
  40×40 Ventoy shows, keeping the originals; refresh warns about oversized ones,
  which use up the boot loader's memory so later icons don't appear.

### Changed
- The stick keeps the theme as synced in `.helix-boot/theme/` and builds
  `ventoy/theme/` and `ventoy/ventoy.json` from it and the chosen look. The
  default look is byte-for-byte what it was. A stick filled by an older version
  needs one refresh before `theme.sh` works on it.
- The Lazarus launcher opens full screen, over the taskbar, which comes back
  when you switch to another program; `"fullscreen": false` in `launcher.json`
  keeps it above the taskbar instead.

## [0.5.3] - 2026-09-30

### Fixed
- `HelixBoot.exe` crashed on start when double-clicked ("'NoneType' object has no
  attribute 'isatty'"): started from Explorer, a windowed program has no console.
  CI now also starts the `.exe` that way.

## [0.5.2] - 2026-09-29

### Added
- **`HelixBoot.sh`**, a one-file Linux installer attached to each release beside
  `HelixBoot.exe`, like MediCat's `.sh`: download, `chmod +x`, run. A menu for
  Install, Update and Check (or `install`, `refresh` and `helix` commands);
  everything it needs is packed inside and checked against its checksum before
  it unpacks, so it works offline; `local.toml`, `byo/` and a pack live beside it.
  Built reproducibly by `linux/build.sh`; `HELIX_USER_DIR` tells helix where your
  files are.
- A Helix Boot logo banner in `install.sh` and `refresh.sh`.

## [0.5.1] - 2026-09-29

### Added
- **Lazarus launcher**: Lazarus PE's start screen, opened full screen when the
  desktop loads (PortableApps.com is one of its quick actions). Every tool on the
  stick and in the PE in seven categories, with search, quick actions and a
  System Info panel; it scales to any screen. It lives on the stick
  (`Apps\Lazarus`), so a refresh updates it; `launcher.json` holds its
  categories and rules. Windows CI checks how it sorts real tool lists and
  renders screenshots at six screen sizes.
- Descriptions for every app in `tools.toml`, carried in `Apps\apps.txt`.

### Security
Fixes from a security audit of the whole repository (10 findings, each
now covered by a test that failed before the fix):
- **Stick detection** (Lazarus PE's startup and the Helix Apps menu): a tag file
  on any drive was enough to be treated as the stick, so the PC being repaired
  could plant `C:\helix-boot.tag` and a script Lazarus PE would run as SYSTEM.
  The stick is now a USB/SD disk whose tag is a file and that holds no Windows
  (`pe/launcher/FindStick.ps1`); Helix Apps run from the stick uses its own
  drive. The Lazarus PE side takes effect with the next PE build.
- **Packs and stick state**: paths read from a pack (`apps_root`, `iso_root`,
  member names) or from a stick's `.helix-boot/state.json` (app names) could
  point outside the stick, so a crafted pack or a tampered stick could write or
  delete files elsewhere. Every such path is now checked to stay on the stick.
- **GitHub token**: sent only to the GitHub API host itself (it went to any URL
  starting with `https://api.github.com`, e.g. a look-alike host in a scraped
  link), and never carried over a redirect.
- **SourceForge downloads**: the MD5 SourceForge publishes must now agree too,
  since checksum files next to a download come from the same mirrors.
- `Apply-HelixPreset.ps1` is saved with a BOM, which Windows PowerShell 5.1
  needs for its non-ASCII text.

### Changed
- CI hardening: every GitHub Action is pinned to an exact commit (Dependabot
  proposes updates weekly), workflows are read-only by default, checkouts don't
  keep the token, and releases are published by a separate job, the only one
  allowed to write, from the `.exe` the build job tested.
- Documentation brought up to date: real Ventoy screenshots of the Helix Neon
  menu, Lazarus PE's startup and look, the launcher, and packs on Windows.

## [0.5.0] - 2026-09-29

### Changed
- Ventoy now uses **Helix Neon**, the purple/cyan DNA HELIXBOOT theme with
  a left-side live menu, cyan category icons, matching selection, scrollbar,
  terminal and status colours. Lazarus PE's green PortableApps theme stays
  the default in PE. Artwork and an offline layout preview are included;
  `theme/build-theme.py --skip-fonts` rebuilds graphics using committed fonts.
- **Renamed to Helix Boot**, and the engine from `crescue` to `helix`. The
  repository is now `Commanderx-code/helix-boot` (GitHub redirects the old
  address), the Windows app is `HelixBoot.exe`, and the launcher is Helix Apps.
  Nothing made before breaks: sticks get both `helix-boot.tag` and
  `commander-rescue.tag`, a stick's `.commander-rescue` state folder and the
  `~/.cache/commander-rescue` (or `%LOCALAPPDATA%\CommanderRescue`) cache are
  moved over on first use, old packs still unpack, `CRESCUE_*` settings still
  work, Lazarus PE builds with the old launcher open the new one, and an
  existing build VM keeps its name and folder.
- Boot-menu tips: Kaspersky Rescue Disk's points to Limited graphic mode for a
  black screen; Dr.Web LiveDisk's says it may not start on newer PCs (its
  system dates from 2018). Dr.Web no longer carries a WIMBOOT marker, which
  Ventoy only applies to Windows images.

### Added
- **Packs on Windows**: `HelixBoot.exe` builds or updates a stick from a pack,
  fully offline (**Tools from: a pack**, or `--pack` on the command line), and
  picks up a pack sitting beside it. Packs now carry Ventoy for Windows and the
  latest released `HelixBoot.exe` as well, both checked against their published
  checksums; a pack with Linux-only Ventoy says so before any disk is touched.
- **Lazarus PE look**: the preset sets the phoenix wallpaper, dark mode and the
  Seafoam Teal accent in PhoenixPE, and the phoenix as the Start menu profile
  picture. `preset.txt` gained `set` lines that pick any PEBakery option (radio
  buttons, dropdowns, files, text), checked against your PhoenixPE release like
  the rest of the preset. The profile picture goes where StartAllBack reads it:
  Windows' per-user picture list for SYSTEM, found through LogonUI's
  `LoggedOnUserSID`, which a PE never sets.
- **OS Images** (`ISO/OSimages`): your own folder for Windows and Linux
  installers. It has a menu name, tip and disc icon, Helix Boot never changes
  what you put there, and Ventoy only shows it once it holds a bootable image.
  Categories with `user = true` in `tools.toml` behave this way.
- Curated tool icons preserve product colours and proportions across theme
  rebuilds: 17 project/product marks, six publisher marks, two Windows logos
  from Wikimedia Commons and the custom Lazarus phoenix. MemTest86 Free and
  Jayro's Lockpick retain explicit letter-badge fallbacks. Source URLs,
  asset hashes and a labelled preview are included in `docs/tool-icons.md`.
- PortableApps themes carry the folder-button icons (Material Design, CC-BY
  4.0), tinted to each theme's accent, instead of the Platform's beige ones;
  `make-theme.py --search dark` gives a dark search box (Lazarus PE uses it).
- The Platform restyle also recolours its search box icons (`recolor`), which
  are near-black and vanished on dark boxes, to a teal that reads on both.
- **Lazarus PE** PortableApps menu theme (Retro Dark), now the default for new
  sticks; Helix Teal moves to Modern Light, so the six themes sit together.
- The PortableApps.com logo the Platform draws over a theme's bottom-right
  corner is made transparent (`hide_logo`): the one image in its program is
  swapped for a transparent one of the same size, the original kept in `Data`,
  and re-applied after the Platform updates itself.
- `make-theme.py --clear-bottom` for artwork with a drive bar or buttons drawn
  in, which the Platform draws itself.
- `ventoy_mode = "wimboot" | "grub2" | "memdisk"` boots an image in that
  Ventoy mode every time (it's written into the file name on the stick).
- Lazarus PE's startup helper hands over to `Apps\LazarusStartup.cmd` on the
  stick, so what happens at startup changes with a refresh instead of a PE
  rebuild.
- `build-vm.sh push` carries `vm/extra/` (e.g. a wallpaper image) to the
  transfer disk.

### Removed
- SystemRescue: redundant next to Lazarus PE and Hiren's BootCD PE.

### Fixed
- A rebuilt Lazarus PE of exactly the same size as the last one is now copied
  to the stick. Sync records each image's sha256 on the stick instead of
  trusting size alone (ISOs round to whole sectors).
- Two invalid escape sequences that made Python print a warning on every start.

## [0.4.0] - 2026-09-28

### Added
- **PortableApps.com Platform** at the root of the stick (`Start.exe`), like
  MediCat, verified against the SHA-256 on portableapps.com. It goes on once,
  then updates itself and the apps you pick from its App Store; refresh never
  overwrites or prunes it. Lazarus PE opens it when the desktop loads, and the
  Commander Apps menu gains **p) PortableApps.com menu**.
- Five **Helix** PortableApps menu themes (Purple, Electric, Teal, Orange,
  Red), with Helix Teal as a new stick's default. `portableapps/make-theme.py`
  makes more from your own artwork, fitted to the Platform's 406x558 layout.
  They take over built-in theme slots, since the Platform's picker lists only
  its own themes.
- `.wim` boot images (WinRE, Malwarebytes and other WinPE tools) show up in the
  menu: Ventoy's wimboot plugin now comes with the stick (pinned sha256).
- Menu entries marked **[BIOS]** or **[UEFI]** when a tool boots only one way,
  read from each ISO's El Torito catalog and EFI loader.
- An "Enter open · Esc back" hint in the boot menu. Ventoy's left/right arrows
  only scroll a long name sideways, which looked like the menu shifting.
- Boot-menu tips steer SSD and NVMe wiping to Parted Magic's Erase Disk
  (firmware secure erase); DBAN and ShredOS are labelled for hard drives.
- Progress bars while filling a stick: `unpack` shows the whole job (bytes,
  speed, ETA, current file); `sync` shows each file with a counter.
- `theme/build-theme.py --local` makes letter badges for `local.toml` tools,
  with an optional `badge = "XX"`; sync and pack name any tool still without one.
- Lazarus PE build tools: `pe/fix-bootmgr.sh` (a current Windows boot manager
  for PEs built from 22H2/23H2), and `build-vm.sh push` carries drivers such as
  Intel Wi-Fi to the build VM for PhoenixPE's Driver Integration.
- Manifest: `kind = "file"` (a file or folder copied to `dest`), `kind =
  "tree"` (installed once, from a 7-Zip archive or a local folder), checksums
  read from a web page (`{ url, regex }`) and `user_agent = "browser"`.

### Changed
- **Lazarus PE** is built from Windows 11 22H2, where its Start menu works,
  with "Run all programs from RAM" off: it boots faster, needs less memory and
  starts in legacy BIOS mode too. It includes Intel's Wi-Fi drivers (AC 9000
  series, AX201/203/210/211 and newer). The PE guide covers building the 22H2
  ISO with UUP dump, Defender exclusions and the Source Config settings.
- Menu entries show just the tool's name; versions are in `crescue list`.
- The Commander Apps copy built into a PE hands over to the stick's own, so new
  menu entries appear without rebuilding the PE.

### Fixed
- Ventoy's tarball lists its files as `./ventoy-x/…`, which made `fetch`
  delete the extracted Ventoy folder: a fresh `install.sh` or `refresh.sh
  --upgrade-ventoy` then failed with "Ventoy isn't fetched". A cache left that
  way is fetched again.
- `--verify` reads each image back from the stick. It used to hash the copy
  still cached in memory, which couldn't catch a failing stick.

## [0.3.0] - 2026-09-28

### Added
- **Lazarus PE**, the first build of the stick's own Windows 11 PE (formerly
  "Commander PE"): tool id `lazarus-pe`, built as `pe/out/LazarusPE.iso`. It
  boots to a desktop with the Commander Apps launcher and network support.
- **Packs.** `crescue pack` writes the whole stick (boot images, unpacked apps,
  menu, theme), your bring-your-own tools and the Ventoy installer into one zip,
  recording each image's sha256. `crescue unpack` streams a pack onto a stick
  and verifies every image.
- `install.sh --from` and `refresh.sh --from` build or update a stick from a
  pack with no downloads.
- Packs carry their own installer: unzip `installer/` beside the pack on
  another Linux PC and run `installer/install.sh`, no clone needed.
- DBAN in the Disk Wipe menu, verified against SourceForge's MD5.
- Chris Titus Tech's WinUtil in the portable apps, verified against GitHub's
  sha256 digest, for tweaking the repaired Windows from the stick.
- The app launcher runs `.ps1` apps with PowerShell instead of opening them in
  Notepad.
- `crescue ventoy-path --from PACK` extracts the pack's Ventoy installer.
- Changelog, contributing guide, security policy and issue forms.

### Changed
- README reworked around quick start, the tool list and packs.
- Empty bring-your-own ISO slots no longer warn on `sync` and `pack`.
- Build VM: PhoenixPE saved in the VM folder is copied onto the transfer disk,
  so Windows doesn't need to download it. The PE guide covers Defender
  exclusions and the Source Config settings.
- The PhoenixPE preset keeps Microsoft DaRT off; it needs MDOP media and halts
  the build without it.

### Fixed
- Build VM on systems with a zero core-dump limit (Garuda's default): `create`
  sets `max_core = 0` for the session libvirt so QEMU can start.

## [0.2.0] - 2026-09-27

### Added
- MediCat-style boot menu: nine numbered categories, each with an icon, and a
  letter-badge icon for every tool. Your own logos go in `byo/icons/`.

## [0.1.0] - 2026-09-26

First release.

### Added
- `tools.toml` manifest and `crescue`: resolves the newest upstream release of
  every tool, downloads it with resume and retries, and verifies it against
  the publisher's checksum, GitHub's digest, SourceForge's MD5 or an explicit
  trust-on-first-use record.
- `install.sh` (new stick, with disk-safety checks) and `refresh.sh` (update in place).
- Generated Ventoy menu with a Commander Rescue theme.
- Commander PE: PhoenixPE preset, the Commander Apps launcher add-on and a
  one-command Windows build VM (`pe/vm/build-vm.sh`).
- Bring-your-own slots for paid ISOs and portable apps.
- Windows app, `CommanderRescue.exe`, on the same engine.
- CI: unit tests, ShellCheck, a weekly live download-and-verify of every tool,
  and a Windows build that publishes releases.

[Unreleased]: https://github.com/Commanderx-code/helix-boot/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/Commanderx-code/helix-boot/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.14...v0.7.0
[0.6.14]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.13...v0.6.14
[0.6.13]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.12...v0.6.13
[0.6.12]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.11...v0.6.12
[0.6.11]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.10...v0.6.11
[0.6.10]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.9...v0.6.10
[0.6.9]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.8...v0.6.9
[0.6.8]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.7...v0.6.8
[0.6.7]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.6...v0.6.7
[0.6.6]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.5...v0.6.6
[0.6.5]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.4...v0.6.5
[0.6.4]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Commanderx-code/helix-boot/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/Commanderx-code/helix-boot/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/Commanderx-code/helix-boot/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/Commanderx-code/helix-boot/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/Commanderx-code/helix-boot/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Commanderx-code/commander-rescue/releases/tag/v0.1.0
