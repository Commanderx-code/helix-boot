<div align="center">

<img src="docs/artwork/helix-logo.png" alt="Helix Boot" width="150">

# Helix Boot

**A multiboot rescue USB that builds itself from upstream sources.**<br>
Current tools, verified downloads, a MediCat-style boot menu, and room for your own licensed software.

[![CI](https://github.com/Commanderx-code/helix-boot/actions/workflows/ci.yml/badge.svg)](https://github.com/Commanderx-code/helix-boot/actions/workflows/ci.yml)
[![Windows build](https://github.com/Commanderx-code/helix-boot/actions/workflows/windows.yml/badge.svg)](https://github.com/Commanderx-code/helix-boot/actions/workflows/windows.yml)
[![Release](https://img.shields.io/github/v/release/Commanderx-code/helix-boot?sort=semver)](https://github.com/Commanderx-code/helix-boot/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey)

[Quick start](#quick-start) ·
[Installing](docs/install.md) ·
[What's on the stick](docs/tools.md) ·
[Packs](docs/packs.md) ·
[Lazarus PE](docs/lazarus-pe.md) ·
[Themes](docs/look.md) ·
[Changelog](CHANGELOG.md)

<img src="docs/boot-menu.jpg" alt="The Helix Boot menu (Helix Neon theme) in Ventoy" width="820">

</div>

## Why

MediCat was the stick everyone carried, but its last full build dates from
December 2021: frozen versions, overlapping tools and plenty of trialware.
Helix Boot keeps the idea (one stick, a categorised menu, a Windows PE
desktop) and fixes the rest:

| | |
|---|---|
| **Always current** | Every tool resolves to its latest upstream release on each refresh. |
| **Verified** | Downloads are checked against the publisher's own checksums before they reach the stick. Anything without one is flagged, never trusted silently. |
| **Free by default** | The shipped tool list is free software and freeware. Paid tools get [bring-your-own](docs/tools.md#bring-your-own-tools) slots for your licensed copies. |
| **Refreshable in place** | `./refresh.sh` swaps in new versions and leaves alone the files you added yourself, and the tools another PC put there. |
| **Yours to restyle** | Seven boot-menu [themes](docs/look.md), icon styles, your own background and splash: switched on a finished stick from Linux or the Windows app, with a preview first. |
| **Offline-ready** | [Packs](docs/packs.md) put the whole stick, your own tools included, into one zip that builds a stick with no internet, from Linux or Windows. |
| **A real recovery desktop** | [Lazarus PE](docs/lazarus-pe.md), your own Windows 11 PE, opens on a full-screen launcher with every tool on the stick sorted into categories. |
| **Nothing redistributed** | The repo holds a manifest and scripts, not binaries. The Windows PE is built from *your* Windows ISO. |

## Quick start

Download one file from [Releases](https://github.com/Commanderx-code/helix-boot/releases),
put it in a folder of its own, and run it. It asks before it erases anything.

| On | Download | Then |
|---|---|---|
| Windows | `HelixBoot.exe` | Run it, pick the stick, **Install Helix Boot** |
| Linux, in a window | `HelixBoot-linux-x86_64` | `chmod +x` it and run it |
| Linux, in a terminal | `HelixBoot.sh` | `chmod +x HelixBoot.sh && ./HelixBoot.sh` |
| Mac (updates a stick) | `HelixBoot-mac-arm64` or `-x86_64` | See [the Mac steps](docs/install.md) |

Or from a clone, on Linux (Python 3.11.4 or newer and `sudo`; nothing to `pip install`):

```fish
git clone https://github.com/Commanderx-code/helix-boot
cd helix-boot
./install.sh      # download and verify, pick a stick, type its name to confirm
./refresh.sh      # later: update the stick in place
./check.sh        # read the stick back: any damaged files?
```

<img src="docs/windows-app.png" alt="The Helix Boot app" width="480">

[Installing and updating](docs/install.md) has every way in, the app's buttons
one by one, and how to check a download.

## What's on the stick

Nine categories of boot images, portable apps for any Windows PE, and tools for
a Mac that still runs. The shipped list is free software and freeware; paid
tools get slots you fill with your own copy.

<img src="docs/boot-menu-folder.jpg" alt="Inside a boot-menu category, with tool icons" width="820">

[What's on the stick](docs/tools.md) lists every tool, where it comes from and
how it is verified, and how to add or leave out your own.

## More

All of it is in [`docs/`](docs/README.md):

| | |
|---|---|
| [Installing and updating](docs/install.md) | Linux, Windows and Mac; the app's window; checking a download |
| [What's on the stick](docs/tools.md) | Every tool, PortableApps.com, bringing your own, `local.toml` |
| [Packs](docs/packs.md) | The whole stick in one offline zip; packs made to be shared |
| [Lazarus PE](docs/lazarus-pe.md) | Your own Windows 11 PE and its launcher ([building it](pe/README.md)) |
| [The boot menu's look](docs/look.md) | Themes, icons, your own background and splash |
| [The engine](docs/engine.md) | Every command, verification, checking a stick, the safety rules |
| [Roadmap](docs/roadmap.md) | What is planned and what has shipped |
| [Testing on real hardware](docs/testing.md) | What has been tried on a real stick, Windows and Mac |
| [Code signing and privacy](docs/code-signing.md) | How releases are made; what the app contacts |

## How it works

`install.sh`, `refresh.sh` and the Windows app are thin wrappers around `helix`,
a single standard-library Python script: `helix fetch` downloads and verifies,
`helix sync` fills a stick, `helix pack` makes an offline pack, `helix verify`
reads a stick back to find damage.

- **Verified downloads.** Each tool is checked against its publisher's own
  checksum, or GitHub's recorded digest. One with neither is refused unless
  the tool list says, in so many words, to trust it on first use.
- **Nothing touches a disk until everything is downloaded and checked.**
- **Only USB disks are offered**, never the one your system runs from, and the
  disk you confirm is checked to be the same device before each write.
- **An update keeps what it didn't bring.** Tools another PC put on the stick
  stay, with their menu entries.
- **A crafted pack or a tampered stick can't write outside the stick.**

[The engine in full](docs/engine.md): every command, how verification works,
checking a stick for damage, the safety rules, and updating from more than one PC.

## Contributing

Bug reports, tool suggestions and pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md), and please report security issues
privately as described in [SECURITY.md](SECURITY.md).

## Credits and license

Built on [Ventoy](https://www.ventoy.net),
[PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) and the
[PortableApps.com Platform](https://portableapps.com), with thanks to every tool
author listed in [`tools.toml`](tools.toml). The plain fallback category
icons are from [Material Design Icons](https://pictogrammers.com/library/mdi/).
Inspired by MediCat USB.

This repo's scripts are [MIT](LICENSE) licensed. Each tool keeps its own
license, and nothing here grants rights to software you bring yourself. Product
names, logos and icons belong to their owners and only identify the software
([icon notes](docs/tool-icons.md)). Two of
the boot-menu themes are other people's work under their own licences, credited
in their folders: [Standby](theme/presets/standby/NOTICE.md) (GPL) and
[Poly dark](theme/presets/poly-dark/NOTICE.md) (MIT).
