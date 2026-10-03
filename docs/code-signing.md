# Code signing policy

**Status: releases are not code-signed yet.** This page describes how signed
releases of `HelixBoot.exe` are to be made, and what the program does on your
PC and on the network. Until a release is signed, check a download with its
`SHA256SUMS` file and build attestation ([how](../README.md#quick-start)).

## Signing

Free code signing provided by [SignPath.io](https://about.signpath.io),
certificate by [SignPath Foundation](https://signpath.org).

- Only `HelixBoot.exe` is signed, and only as built by this repository's own
  GitHub Actions workflow ([`windows.yml`](../.github/workflows/windows.yml))
  from a tagged commit on `main`. Nothing built on anyone's own PC is signed.
- The build is tested before it is signed: the workflow runs the real `.exe`
  through an install, an update, a stick check and the Look window.
- Every release is approved by hand before it is signed.
- The `.exe` carries its product name and version (Properties > Details); the
  version matches `helix --version` and the release's tag.

## Team roles

| Role | Who |
|---|---|
| Committers and reviewers | [Commanderx-code](https://github.com/Commanderx-code) |
| Approvers | [Commanderx-code](https://github.com/Commanderx-code) |

Changes from anyone else come in as pull requests and are reviewed before they
are merged. Accounts with access to the repository or to signing use
multi-factor authentication.

## Privacy policy

Helix Boot has no accounts, no telemetry and no analytics. It sends nothing to
this project or to its maintainer, and it collects no information about you or
your PC.

It does make ordinary web requests to the publishers of the tools it puts on a
stick, and to nobody else:

- **When the app starts**, it asks GitHub, SourceForge and the tools' own
  download sites for the latest version number of each tool, to tell you which
  have newer versions. It does this at most once every 6 hours. To turn it off,
  put `check_for_updates = false` under `[settings]` in `local.toml`, next to
  the `.exe`.
- **When you press Install or Update** with *the internet* chosen, it downloads
  the tools and their checksums from those same sites. With *a pack* chosen it
  downloads nothing.

Like any download, those requests show the site your IP address. They carry no
identifier of yours. If you set a `GITHUB_TOKEN` yourself, it is sent to
`api.github.com` only.

## What it changes on your PC

- **Install** erases the USB stick you pick, after you type its disk number to
  confirm. Only USB and SD disks are offered, never the disk Windows runs from.
- **Update**, **Look…** and **Check stick** write only to the stick you pick.
  Update first shows what it will copy, remove and keep, and asks.
- Downloads are kept in `%LOCALAPPDATA%\HelixBoot`. A log, your `local.toml`
  and your `byo` folder sit next to the `.exe`.
- It installs nothing into Windows and changes no Windows settings.

## Removing it

Delete `HelixBoot.exe` and the files next to it, and the folder
`%LOCALAPPDATA%\HelixBoot`. Nothing else is left behind.
