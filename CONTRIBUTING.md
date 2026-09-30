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

```fish
python3 -m unittest discover -s tests -v   # the whole suite runs offline
shellcheck -x install.sh refresh.sh scripts/common.sh pe/vm/build-vm.sh linux/build.sh linux/HelixBoot.sh.in
./helix check                             # live: does every upstream still resolve?
```

The tests run against a local fake GitHub / SourceForge / web server, so they
need no network; the Windows app's tests fake PowerShell and Ventoy, so they run
here too. CI also runs a weekly live download-and-verify of every tool, builds
and smoke-tests `HelixBoot.exe` on Windows, and checks the Lazarus launcher
(`pe/lazarus`) on Windows PowerShell 5.1, uploading screenshots of it.

## Pull requests

- Keep `helix` standard-library only, and match the surrounding style.
- PowerShell for Lazarus PE must run on Windows PowerShell 5.1; save `.ps1`
  files with non-ASCII text as UTF-8 **with** a BOM (5.1 reads them as ANSI
  otherwise).
- Add or update tests for behaviour changes, and keep ShellCheck clean.
- After adding a tool or category, run `theme/build-theme.py` so it gets a menu
  icon (a test checks this).
- Update `README.md` and `CHANGELOG.md` (under *Unreleased*) when users would
  notice the change.
- Never commit ISOs, packs or anything from `byo/`.
