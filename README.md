<div align="center">

# Helix Boot

**A multiboot rescue USB that builds itself from upstream sources.**<br>
Current tools, verified downloads, a MediCat-style boot menu, and room for your own licensed software.

[![CI](https://github.com/Commanderx-code/helix-boot/actions/workflows/ci.yml/badge.svg)](https://github.com/Commanderx-code/helix-boot/actions/workflows/ci.yml)
[![Windows build](https://github.com/Commanderx-code/helix-boot/actions/workflows/windows.yml/badge.svg)](https://github.com/Commanderx-code/helix-boot/actions/workflows/windows.yml)
[![Release](https://img.shields.io/github/v/release/Commanderx-code/helix-boot?sort=semver)](https://github.com/Commanderx-code/helix-boot/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey)

[Quick start](#quick-start) ·
[What's on the stick](#whats-on-the-stick) ·
[Packs](#packs-the-whole-stick-in-one-file) ·
[Lazarus PE](#lazarus-pe) ·
[Customising](#customising) ·
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
| **Free by default** | The shipped tool list is free software and freeware. Paid tools get [bring-your-own](#bring-your-own-tools) slots for your licensed copies. |
| **Refreshable in place** | `./refresh.sh` swaps in new versions and leaves files you added yourself alone. |
| **Offline-ready** | [Packs](#packs-the-whole-stick-in-one-file) put the whole stick, your own tools included, into one zip that builds a stick with no internet, from Linux or Windows. |
| **A real recovery desktop** | [Lazarus PE](#lazarus-pe), your own Windows 11 PE, opens on a full-screen launcher with every tool on the stick sorted into categories. |
| **Nothing redistributed** | The repo holds a manifest and scripts, not binaries. The Windows PE is built from *your* Windows ISO. |

## Quick start

**Linux.** Needs Python 3.11+ and `sudo`; nothing to `pip install`.

```fish
git clone https://github.com/Commanderx-code/helix-boot
cd helix-boot

./helix check        # latest version of everything (no downloads)
./install.sh           # download + verify, pick a stick, type its name to confirm
```

Keep it current later:

```fish
./refresh.sh                    # update the stick in place
./refresh.sh --upgrade-ventoy   # …and the Ventoy boot loader too
```

**Linux, one file.** Or skip the clone: download **`HelixBoot.sh`** from
[Releases](https://github.com/Commanderx-code/helix-boot/releases), put it in a
folder of its own, then `chmod +x HelixBoot.sh && ./HelixBoot.sh`. A menu offers
Install, Update, Change a stick's look and Check; `./HelixBoot.sh --help` lists the rest. Your
`local.toml` and `byo/` folder live next to it, and a pack beside it is used
with no downloads.

**Windows.** Download **`HelixBoot.exe`** from
[Releases](https://github.com/Commanderx-code/helix-boot/releases), put it
in a folder of its own and run it (see [below](#windows-app)).

**From a pack.** Already have a pack zip? No clone needed:
`unzip pack.zip 'installer/*'`, then `installer/install.sh`, or on Windows run
`installer\HelixBoot.exe` from beside the zip
([details](#packs-the-whole-stick-in-one-file)).

## What's on the stick

Nine categories, each with its own icon, and every tool inside with an icon
and a one-line tip. A tenth, **OS Images**, is your own folder for installer
ISOs; it appears as soon as you put one in. Tools that only start on older BIOS PCs (DBAN, HDAT2,
SpinRite) are marked **[BIOS]**, and UEFI-only ones **[UEFI]**, detected from
each ISO's boot records. Windows `.wim` boot images (WinRE, WinPE tools) work
too: Ventoy's wimboot plugin comes with the stick.

<img src="docs/boot-menu-folder.jpg" alt="Inside a boot-menu category, with tool icons" width="820">

| Menu | Tools | Source · verification |
|---|---|---|
| Antivirus | Dr.Web LiveDisk | vendor site · unverified |
| | Kaspersky Rescue Disk *(off by default, see below)* | vendor site · unverified |
| Backup and Recovery | Rescuezilla | GitHub · sha256 |
| | Clonezilla | SourceForge · sha512 |
| Boot Repair | Super GRUB2 Disk | SourceForge · sha256 |
| | Boot-Repair-Disk | SourceForge · md5 |
| Diagnostic Tools | Memtest86+ | memtest.org · sha512 |
| Disk Wipe | ShredOS (nwipe) | GitHub · sha256 |
| | DBAN (BIOS boot only) | SourceForge · md5 |
| Live Operating Systems | **Lazarus PE**, your own [PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) Windows 11 build | built locally · [guide](pe/README.md) |
| | Hiren's BootCD PE | hirensbootcd.org · unverified |
| Partition Tools | GParted Live | SourceForge · sha512 |
| Password Removal | *bring your own* (e.g. Jayro's Lockpick) | [`byo/`](byo/README.md) |
| Windows Recovery | *bring your own* (Windows 10/11 setup, DaRT) | [`byo/`](byo/README.md) |
| OS Images | *yours*: drop Windows or Linux installer ISOs into `ISO/OSimages` on the stick | shown once it holds an image |

Screenshots are real Ventoy renders of a Helix Boot stick. In the menu, use
Up/Down, Enter and Esc: Ventoy's left/right keys only slide the highlighted
name sideways (built into Ventoy, not a setting).

**Portable apps** for any Windows PE, in `USB:\Apps`, listed by the Lazarus
launcher and by the Helix Apps menu (`HelixApps.cmd`, for other PEs such as Hiren's):
Sysinternals, Explorer++, Notepad++, CrystalDiskInfo, CrystalDiskMark, HWiNFO,
TestDisk & PhotoRec, ProduKey, DiskGenius Free, Microsoft Safety Scanner and
Kaspersky Virus Removal Tool *(off by default)*. The launcher also carries
[Chris Titus Tech's WinUtil](https://github.com/ChrisTitusTech/winutil) for
after a repair: run it from the stick in the fixed Windows to debloat, tweak
or reinstall apps.

<details>
<summary><b>Notes on unverified tools, antivirus and Kaspersky</b></summary>

*Unverified* means the publisher offers no checksum. The file is trusted on
first download and refused if it later changes without a new version (see
[verification](#verification)). Antivirus tools carry their virus
definitions, so `./refresh.sh` before a job keeps them current. Microsoft
Safety Scanner stops working 10 days after download.

On newer PCs, Kaspersky Rescue Disk's *Graphic mode* can end on a black
screen when it doesn't support the graphics card: choose *Limited graphic
mode* in its menu instead (the boot-menu tip says so). Dr.Web LiveDisk runs a
2018 Linux, which may not start at all on newer PCs; Kaspersky, Malwarebytes
and the scanners in Lazarus PE cover those.

Kaspersky refuses downloads from the US, so its two tools are off. Outside the
US, turn them on in `local.toml`:

```toml
[overrides.kaspersky-rd]
enabled = true

[overrides.kvrt]
enabled = true
```

</details>

> [!TIP]
> DBAN and ShredOS overwrite **hard drives**. For SSDs and NVMe drives use
> Parted Magic's *Erase Disk*, which runs the drive's own secure erase or
> sanitize command and reaches the spare flash an overwrite can miss. The
> boot menu says so too.

Every tool is described in [`tools.toml`](tools.toml); adding one is a few lines.

### PortableApps.com

The [PortableApps.com Platform](https://portableapps.com) sits at the root of
the stick (`Start.exe`), like on MediCat: run it on any Windows PC, or from
the **PortableApps** quick action in Lazarus PE, whose launcher also lists
every app you install. Pick apps from its App Store; it keeps them and itself
up to date. Helix Boot puts the Platform
on once and never overwrites or prunes it, so your apps survive every refresh.
The Helix Apps menu also has **p) PortableApps.com menu**.

It comes with six menu themes, **Lazarus PE** (the default on a new stick)
and five **Helix** colours. The Platform's picker lists only its own themes,
so they take over the last six entries in **Options > Themes**: Modern Light
(Helix Teal), Modern Dark (Purple), Retro Light (Electric), Retro Dark (Lazarus
PE), Smooth Light (Orange) and Smooth Dark (Red). The PortableApps.com logo
the Platform would draw over a theme's corner is made transparent. Make your
own from any artwork with the menu's panels drawn in:

```fish
portableapps/make-theme.py ~/art/teal.png "Helix Teal" --slot RetroDark --accent 1ec8e6
```

It finds the panels, fits the art to the Platform's fixed 406x558 menu, and
writes the theme to `portableapps/themes/<slot>/` (`--hue` recolours the art).

### Bring your own tools

Paid and licence-restricted tools get menu slots you fill with your own copy:
Macrium Reflect, AOMEI Backupper and Partition Assistant, EaseUS Todo Backup
and Data Recovery, Paragon Hard Disk Manager, Parted Magic, Active@ Data
Studio, BootIt Bare Metal, SpinRite, PassMark MemTest86, HDAT2, Windows 10/11
Setup, Microsoft DaRT and Jayro's Lockpick. Drop the ISO into
[`byo/`](byo/README.md) under its slot name and `./refresh.sh` puts it in the
right menu. Anything else (another ISO, a `.wim`, a portable app) gets a slot
of its own in `local.toml`. Nothing in `byo/` is ever downloaded, shared or
committed.

## Packs: the whole stick in one file

Like MediCat's download, a pack is one file with every tool in it, ready to
extract onto a stick. It's made from your cache, so it includes your
bring-your-own tools and the Ventoy installer, and a new stick needs no internet:

```fish
./helix fetch                                 # bring everything up to date
./helix pack                                  # → helix-boot-<date>.zip
./install.sh --from helix-boot-<date>.zip # new stick
./refresh.sh --from helix-boot-<date>.zip # update a stick
```

The pack carries its own installer, so on another Linux PC the zip is all you need:

```fish
unzip helix-boot-<date>.zip 'installer/*'   # a few MB
installer/install.sh                               # finds the zip beside it
```

On Windows, take `installer\HelixBoot.exe` out of the zip, keep it next to the
zip and run it: the window picks the pack up on its own (**Tools from: a pack**),
and Install or Update copy everything from it, Ventoy included, with no
downloads. A pack holds both Ventoy packages (Linux and Windows) and the
latest released `HelixBoot.exe`, each checked against its published checksum.

Inside is the stick exactly as `helix sync` lays it out, with boot images
stored uncompressed and each one's sha256 recorded. Extracting streams files
straight onto the stick and checks every image, so a damaged pack is caught,
not booted. A stick filled from a pack refreshes normally afterwards.

> [!IMPORTANT]
> A pack holds your licensed tools, so keep it private: a drive, a NAS or your
> own cloud storage, never a public repo or release. Packs made in this folder
> are git-ignored.

## Windows app

`HelixBoot.exe` asks for admin rights, because installing Ventoy writes
to the disk.

1. Pick the USB stick. Only USB/SD disks are listed, never the one Windows is
   running from.
2. **Install** erases the stick (you type its disk number to confirm), installs
   Ventoy and copies everything on. **Update** refreshes a stick you already
   have and keeps your files.
3. **Look…** changes the selected stick's look: a preset theme or none, the
   icons, your own background (with a slider to darken it) and splash, with a
   preview of the boot menu. Nothing changes until **Apply to the stick**.

It uses the same engine as the Linux scripts: the same tool list, checksums,
theme and menu. Your `local.toml` and `byo/` folder live next to the `.exe`, and
downloads are cached in `%LOCALAPPDATA%\HelixBoot`. The command line
works too: `HelixBoot.exe --help`.

To build a stick offline, pick **Tools from: a pack** and choose a pack zip. A
pack next to the `.exe` is chosen for you. From the command line, add
`--pack helix-boot-<date>.zip` to `--install` or `--update`.

## Lazarus PE

Lazarus PE is the stick's Windows 11 desktop, filling the role of MediCat's
Mini Windows. You build it yourself with PhoenixPE from your own Windows ISO,
because WinPE images contain Microsoft files that can't be redistributed. The
image stays lean: drivers (including Intel Wi-Fi and RST), networking and
Explorer, in its own look: the phoenix wallpaper and profile picture, dark
mode and a teal accent. The launcher, apps and startup live on the stick and
update without a rebuild. On Linux, `pe/vm/build-vm.sh` sets up the build VM
for you. See the [Lazarus PE guide](pe/README.md).

Until yours is built, Hiren's BootCD PE covers for it, and the app launcher
works there too.

### The Lazarus launcher

![The Lazarus launcher](docs/lazarus-launcher.jpg)

When Lazarus PE's desktop loads, the **Lazarus launcher** opens full screen: every
tool on the stick and in the PE, in seven categories (Recovery, Backup, Disk
Tools, Diagnostics, Network, Security, Utilities), with search across all of them
(just start typing), quick actions (Command Prompt, File Explorer, Device
Manager, PortableApps, Reboot, Shutdown) and a System Info panel that also points
out which drives hold a Windows install.

It lists your Helix Apps, every PortableApps.com app (including ones you add
from its App Store) and the PE's own Start menu, the same tool only once. It
lives on the stick in `Apps\Lazarus` (from [`pe/lazarus`](pe/lazarus)), so a
refresh updates it without a PE rebuild. Categories, sorting rules, names and
quick actions are in [`launcher.json`](pe/lazarus/launcher.json). Without it,
Lazarus PE opens the PortableApps.com menu instead.

## `helix`, the engine

`install.sh` and `refresh.sh` are thin wrappers around `helix`, a single
standard-library Python script:

| Command | Does |
|---|---|
| `helix list` | every tool, its source, and whether it's enabled |
| `helix check [--json]` | compares your cache against upstream, no downloads |
| `helix fetch [tool…] [--force]` | downloads, verifies and caches (`~/.cache/helix-boot`); resumes interrupted downloads |
| `helix sync <mount> [--dry-run] [--verify]` | copies the cache to a Ventoy stick, prunes old versions, writes the menu |
| `helix pack [file.zip]` | the whole stick, your own tools and Ventoy in one zip |
| `helix unpack <pack.zip> <mount> [--dry-run] [--verify]` | fills a Ventoy stick from a pack, no downloads |

### Verification

Each tool lists checksum strategies in order of preference. The first one
that yields a hash is used; a mismatch deletes the file and stops:

1. the publisher's checksum file (`sha256.txt`, `CHECKSUMS.TXT`, `*.sha512`)
2. GitHub's recorded sha256 digest for the release asset
3. SourceForge's md5 (integrity only)
4. `tofu`: trust-on-first-use, **only if the manifest explicitly says so**.
   The hash is recorded, and a re-download of the same version with a
   different hash is refused as possible tampering.

If no strategy works, the tool is refused rather than silently used.

### Safety

- `install.sh` downloads and verifies everything **before** touching any disk.
- It lists only USB/removable disks and refuses any disk holding your running
  system, following LUKS, LVM and btrfs back to the physical disk.
- You type the device name to confirm, and it warns if the "stick" is
  suspiciously large.
- `refresh.sh` never erases anything except old versions of files it put there.
- Nothing read from a pack or from a stick (paths, app names) can reach outside
  the stick: a crafted pack or a stick tampered with on an infected PC can't
  write or delete anything else.
- Lazarus PE and the Helix Apps menu only accept a USB/SD disk as the stick
  (tag file, no Windows on it), so a tag planted on the PC being repaired can't
  get its script run.

## Customising

Personal changes go in `local.toml` (git-ignored), which overlays `tools.toml`:

```toml
[overrides.hirens]
enabled = false             # leave Hiren's off this stick

[[tool]]                    # add your own
name = "kali"
title = "Kali Linux"
kind = "iso"
category = "live"
source = "url"
url = "https://cdimage.kali.org/current/kali-linux-2026.3-live-amd64.iso"
version_pin = "2026.3"
checksum = [{ url = "https://cdimage.kali.org/current/SHA256SUMS" }]
```

ISOs you copy onto the stick by hand (e.g. into `ISO/Custom/`) are never touched.

**Theme.** The default Ventoy theme is **Helix Neon**: purple/cyan DNA artwork,
the HELIXBOOT wordmark, cyan category icons and a purple selection with a cyan
edge. The menu, scrolling, timeout, hotkeys and boot-mode indicators are real
Ventoy components; no menu entries are painted into the wallpaper. Lazarus PE
keeps its separate green PortableApps theme.

Tool entries use curated product/project icons in their original colours,
with publisher marks where a product-specific icon was not available.
[Icon preview and sources](docs/tool-icons.md) identify each asset and the
two remaining letter-badge fallbacks. The builder preserves these icons.

![Helix Neon layout preview](docs/artwork/helix-neon-preview.jpg)

The image above is a layout preview; the screenshots at the top are the real
thing. The theme targets 1920×1080; other screen modes use Ventoy's resolution
fallback, and longer menus scroll.

After pulling the changes, `./refresh.sh` installs the new theme on an existing
stick. No PE rebuild is needed. See [theme notes](docs/theming.md) for rebuilding
assets and checking the result on your hardware.

The boot-menu theme lives in [`theme/`](theme/). Edit `theme.txt` for layout,
or the colours and text in `theme/build-theme.py` and re-run it to regenerate
the images, icons and fonts (`--skip-fonts` reuses the committed fonts).
To show a tool's real logo instead of
its letter badge, save a square PNG as `byo/icons/<tool name>.png`;
`byo/icons/cat-<category id>.png` replaces a category icon, and Ventoy's own
(`vtoyiso`, `vtoydir`, `vtoyret` for "back", …) can be replaced the same way.
Ventoy shows icons at 40×40, and big ones use up its memory at boot so later
icons don't appear: `theme/build-theme.py --fit-icons` shrinks yours to
40×40, keeping the originals in `byo/icons/originals/`. Put icons there, not
straight onto the stick: refresh rewrites the stick's theme folder. For Ventoy's stock look, set `theme = ""` under `[settings]`.

**Change the look.** `./theme.sh` changes a finished stick's look without
rebuilding anything, and the choice is kept on the stick, so a refresh doesn't
undo it:

```sh
./theme.sh                                  # how it looks now, and what there is to choose
./theme.sh --theme midnight                 # a preset: midnight, ember, terminal, slate (default: Helix Neon)
./theme.sh --theme standby                  # someone else's theme: standby, poly-dark (icons in grey)
./theme.sh --theme off                      # no theme at all: Ventoy's own look
./theme.sh --icons off                      # no icons, just names (--icons grey, --icons badges)
./theme.sh --background ~/pic.jpg --dim 40  # your own picture behind the menu, darkened 40 %
./theme.sh --splash ~/pic.png               # your own picture before the menu (--splash off: none)
./theme.sh --reset                          # back to the default look
```

![The Midnight, Ember, Terminal and Slate presets](docs/themes.jpg)

`./theme.sh --menu` (also **Change a stick's look** in `HelixBoot.sh`) offers the
same choices as numbered lists; `--preview out.png` draws how the menu would
look without changing the stick. On Windows it is the app's **Look…** button,
or `HelixBoot.exe --look E:\ --theme midnight`.

![The Standby and Poly dark themes](docs/themes-imported.jpg)

Midnight, Ember, Terminal and Slate are the same menu in other colours, over
artwork drawn by `theme/build-theme.py` (so all of it can be shared). **Standby**
(by Llewelyn Trahaearn, GPL) and **Poly dark** (by Andrei Shevchuk, MIT) are
other people's GRUB themes with their own layout, adapted for Ventoy; they show
every tool's icon in shades of grey, which `--icons grey` does on any theme and
`--icons logos` undoes. Your own icons and
`byo/splash.png` still win over a preset's. More icon packs go in
`byo/icon-packs/<name>/` (PNGs named like the ones in `byo/icons/`). Your own
pictures are resized to 1920×1080 with Pillow; without it, a PNG is used as it
is. See [theme notes](docs/theming.md) for how the stick stores all this.

**Splash.** When the stick boots, a splash (the HELIXBOOT logo over the theme's
artwork, `theme/splash.png`) shows for about a second before the Ventoy menu,
with a loading bar filling up along the bottom. Save your own picture as
`byo/splash.png` (1920×1080 works best), set `splash_seconds` under
`[settings]` in `local.toml` (0 turns it off), and refresh. The boot loader
only counts whole seconds, so the bar is a set of frames drawn one after
another: a slower PC takes a little longer. Refresh makes the frames with
Pillow (`python-pillow`); without it the splash is a still picture. Ventoy has no setting for this, so `install.sh` and `refresh.sh` add a
few marked lines to Ventoy's own boot script on the stick's small VTOYEFI
partition, and re-add them after a Ventoy upgrade.

<details>
<summary><b>Layout on the stick</b></summary>

```
ISO/1-Antivirus/  ISO/2-Backup-and-Recovery/  ISO/3-Boot-Repair/
ISO/4-Diagnostic-Tools/  ISO/5-Disk-Wipe/  ISO/6-Live-Operating-Systems/
ISO/7-Partition-Tools/  ISO/8-Password-Removal/  ISO/9-Windows-Recovery/
ISO/OSimages/       your own installer ISOs (never touched; hidden while empty)
Apps/               portable apps, the Helix Apps menu and LazarusStartup.cmd
Apps/Lazarus/       the Lazarus launcher (Lazarus PE's start screen)
PortableApps/       the PortableApps.com Platform's apps (Start.exe at the root)
ventoy/ventoy.json  generated menu: tree view, friendly names, icons, tips
.helix-boot/        sync state (which files this project manages)
```

</details>

## Roadmap

- [x] Manifest, fetch/verify engine, installer, refresher, Ventoy menu and theme
- [x] PE app launcher (works in any WinPE)
- [x] CI: tests, ShellCheck, weekly live resolve + download + verify of every tool
- [x] Windows app (`HelixBoot.exe`)
- [x] Packs: offline, self-installing zip of the whole stick
- [x] PhoenixPE preset, Helix Boot add-on and build VM ([guide](pe/README.md))
- [x] First Lazarus PE build
- [x] PortableApps.com Platform with custom menu themes
- [x] Packs in the Windows app
- [x] Renamed to Helix Boot (0.5.0), Helix Neon boot-menu theme
- [x] Lazarus PE look and the Lazarus launcher
- [x] One-file Linux installer (`HelixBoot.sh`)

## Contributing

Bug reports, tool suggestions and pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md), and please report security issues
privately as described in [SECURITY.md](SECURITY.md).

## Credits and license

Built on [Ventoy](https://www.ventoy.net),
[PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) and the
[PortableApps.com Platform](https://portableapps.com), with thanks to every tool
author listed in [`tools.toml`](tools.toml). Icons from
[Material Design Icons](https://pictogrammers.com/library/mdi/). Inspired by
MediCat USB.

This repo's scripts are [MIT](LICENSE) licensed. Each tool keeps its own
license, and nothing here grants rights to software you bring yourself. Two of
the boot-menu themes are other people's work under their own licences, credited
in their folders: [Standby](theme/presets/standby/NOTICE.md) (GPL) and
[Poly dark](theme/presets/poly-dark/NOTICE.md) (MIT).
