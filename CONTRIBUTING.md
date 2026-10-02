# Contributing

Thanks for helping. Bug reports, tool suggestions and pull requests are all welcome.

## Suggesting a tool

Open a [tool request](https://github.com/Commanderx-code/helix-boot/issues/new?template=tool_request.yml).
Tools that ship in `tools.toml` must be:

- **free**: free software or freeware,
  downloaded from the publisher by the user's own machine (paid tools belong in
  a bring-your-own slot instead);
- **fetchable automatically** from a stable location (GitHub releases,
  SourceForge, or a fixed URL);
- **verifiable**, ideally with a checksum the publisher publishes. Tools without
  one need `checksum = ["tofu"]` and a good reason.

## Development

Requirements: Linux, Python 3.11+ (standard library only) and ShellCheck.
Pillow is optional: the theme generator needs it, and the tests that draw
pictures (previews, the loading bar, greyscale icons) are skipped without it.

```fish
python3 -m unittest discover -s tests -v   # the whole suite runs offline
shellcheck -x install.sh refresh.sh theme.sh scripts/common.sh pe/vm/build-vm.sh linux/build.sh linux/HelixBoot.sh.in
./helix check                             # live: does every upstream still resolve?
tests/boot/boot_menu.py --firmware both   # boots the menu in QEMU with every theme, takes screenshots
```

The tests run against a local fake GitHub / SourceForge / web server, so they
need no network; the Windows app's tests fake PowerShell and Ventoy, so they run
here too. `tests/boot/boot_menu.py` builds a throwaway Ventoy disk and boots it
in QEMU once per theme, on UEFI and BIOS, checking that each comes up with its
own background and a drawn menu; it needs QEMU, OVMF, mtools, dosfstools and
Pillow, and it is where the README's screenshots come from. CI runs it on
every push, and also runs a weekly live download-and-verify of every tool, builds
and smoke-tests `HelixBoot.exe` on Windows, and checks the Lazarus launcher
(`pe/lazarus`) on Windows PowerShell 5.1, uploading screenshots of it.

## Pull requests

- Keep `helix` standard-library only, and match the surrounding style. Pillow
  may be imported where it is used, as long as the feature degrades without it.
- PowerShell for Lazarus PE must run on Windows PowerShell 5.1; save `.ps1`
  files with non-ASCII text as UTF-8 **with** a BOM (5.1 reads them as ANSI
  otherwise).
- Add or update tests for behaviour changes, and keep ShellCheck clean.
- After adding a tool or category, run `theme/build-theme.py` so it gets a menu
  icon (a test checks this). The same run regenerates the theme presets and the
  letter-badge icon pack; see [theme notes](docs/theming.md) for adding a preset.
- A tool to run on a working Mac is an app with `platform = "mac"`: it goes in
  the stick's `Mac` folder as downloaded.
- Anything that removes files from a stick must keep to the rule in the README
  ("Updating from more than one PC"): another PC's tools are never removed
  unless asked for with `--prune-unknown`.
- Update `README.md` and `CHANGELOG.md` (under *Unreleased*) when users would
  notice the change.
- Never commit ISOs, packs or anything from `byo/`.
