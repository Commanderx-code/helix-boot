# Changelog

Notable changes to Commander Rescue. Versions follow `crescue --version`;
tagged releases also publish the Windows app.

## [Unreleased]

### Added
- Chris Titus Tech's WinUtil in the portable apps, verified against GitHub's
  sha256 digest, for tweaking the repaired Windows from the stick.
- The app launcher runs `.ps1` apps with PowerShell instead of opening them in
  Notepad.

### Changed
- The Windows PE is now called **Lazarus PE**: tool id `lazarus-pe`, built as
  `pe/out/LazarusPE.iso`.

## [0.3.0] - 2026-09-27

### Added
- **Packs.** `crescue pack` writes the whole stick (boot images, unpacked apps,
  menu, theme), your bring-your-own tools and the Ventoy installer into one zip,
  recording each image's sha256. `crescue unpack` streams a pack onto a stick
  and verifies every image.
- `install.sh --from` and `refresh.sh --from` build or update a stick from a
  pack with no downloads.
- Packs carry their own installer: unzip `installer/` beside the pack on
  another Linux PC and run `installer/install.sh`, no clone needed.
- DBAN in the Disk Wipe menu, verified against SourceForge's MD5.
- `crescue ventoy-path --from PACK` extracts the pack's Ventoy installer.

### Changed
- Empty bring-your-own ISO slots no longer warn on `sync` and `pack`.
- Build VM: PhoenixPE saved in the VM folder is copied onto the transfer disk,
  so Windows doesn't need to download it.

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
