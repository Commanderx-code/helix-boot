# Changelog

Notable changes to Helix Boot (called Commander Rescue before 0.5.0). Versions
follow `helix --version` (`crescue --version` before 0.5.0);
tagged releases also publish the Windows app.

## [Unreleased]

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

[Unreleased]: https://github.com/Commanderx-code/helix-boot/compare/v0.6.3...HEAD
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
