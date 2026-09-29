# Changelog

Notable changes to Commander Rescue. Versions follow `crescue --version`;
tagged releases also publish the Windows app.

## [Unreleased]

### Added
- **t) PortableApps theme** in Commander Apps: the Platform lists only its
  built-in themes and has one custom slot, so this switches your themes (kept
  in `Data\ThemeLibrary`) into it and restarts the menu.
- A Commander Apps copy built into a PE hands over to the stick's own, so new
  menu entries show up without rebuilding the PE.
- `theme/make-pa-theme.py`: PortableApps.com menu themes from your own
  artwork, fitted to the Platform's 406x558 layout, with an accent colour and
  optional recolouring.
- `kind = "file"` tools can be a local folder, copied under `dest` (used to
  put your PortableApps themes on the stick and in packs).
- `build-vm.sh push` carries unpacked drivers (`vm/drivers/x64`) to the
  transfer disk for PhoenixPE's Driver Integration, e.g. Intel Wi-Fi.
- An "Enter open · Esc back" hint in the boot menu. Ventoy's left/right arrows
  only scroll a long name sideways, which looked like the menu shifting.
- `pe/fix-bootmgr.sh`: puts a current Windows boot manager into a Lazarus PE
  built from 22H2/23H2, whose 2022 UEFI loader hangs on newer firmware. The
  PE guide now recommends building from 22H2/23H2 (via UUP dump), where the
  Start menu works.
- **PortableApps.com Platform** at the root of the stick, verified against the
  SHA-256 on portableapps.com. It goes on once, then updates itself and the
  apps you pick from its App Store; refresh never overwrites or prunes it.
  Lazarus PE opens it when the desktop loads (after the next PE build), and the
  Commander Apps menu gains **p) PortableApps.com menu**.
- `kind = "tree"` tools: an archive unpacked with 7-Zip into `dest`, installed
  only while its `once` file is missing.
- Checksums read from a web page that names the file (`{ url, regex }`), and
  `user_agent = "browser"` for sites that turn other clients away.
- Ventoy's wimboot plugin (`ventoy/ventoy_wimboot.img`, pinned sha256), so
  `.wim` boot images such as WinRE and Malwarebytes appear in the menu. Ventoy
  hides `.wim` files without it.
- `kind = "file"` tools: a file copied to a fixed `dest` on the stick.
- Menu entries marked **[BIOS]** or **[UEFI]** when a tool boots only one way,
  read from each ISO's El Torito catalog and EFI loader.
- `theme/build-theme.py --local` makes letter badges for `local.toml` tools
  (into `byo/icons/`), with an optional `badge = "XX"`; sync and pack name any
  boot tool still without an icon.
- Boot-menu tips steer SSD and NVMe wiping to Parted Magic's Erase Disk
  (firmware secure erase); DBAN and ShredOS are labelled for hard drives.
- Progress while filling a stick: `unpack` shows one bar for the whole job
  (bytes, speed, ETA, current file); `sync` shows each file with a counter.

### Changed
- Menu entries show just the tool's name (and [BIOS]/[UEFI]); versions are
  in `crescue list` and `crescue check`.

### Fixed
- Ventoy's tarball lists its files as `./ventoy-x/…`, which made `fetch`
  delete the extracted Ventoy folder and record it as `.`: a fresh
  `install.sh` or `refresh.sh --upgrade-ventoy` then failed with "Ventoy isn't
  fetched". A cache left that way is now fetched again.
- `--verify` now reads each image back from the stick. It used to hash the
  copy still cached in memory, which couldn't catch a failing stick.

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

[Unreleased]: https://github.com/Commanderx-code/commander-rescue/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Commanderx-code/commander-rescue/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Commanderx-code/commander-rescue/releases/tag/v0.1.0
