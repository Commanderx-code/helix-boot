# Changelog

Notable changes to Helix Boot (called Commander Rescue before 0.5.0). Versions
follow `helix --version` (`crescue --version` before 0.5.0);
tagged releases also publish the Windows app.

## [Unreleased]

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

### Added
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
  Ventoy mode every time (it's written into the file name on the stick). Dr.Web
  LiveDisk now always boots in WIMBOOT mode, the one that works for it.
- Lazarus PE's startup helper hands over to `Apps\LazarusStartup.cmd` on the
  stick (from the next PE build), so what happens at startup changes with a
  refresh instead of a PE rebuild.
- `build-vm.sh push` carries `vm/extra/` (e.g. a wallpaper image) to the
  transfer disk.

### Removed
- SystemRescue: redundant next to Lazarus PE and Hiren's BootCD PE.

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

[Unreleased]: https://github.com/Commanderx-code/helix-boot/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Commanderx-code/commander-rescue/releases/tag/v0.1.0
