# What's on the stick

Nine categories, each with its own icon, and every tool inside with an icon
and a one-line tip. A tenth, **OS Images**, is your own folder for installer
ISOs; it appears as soon as you put one in. Tools that only start on older BIOS PCs (DBAN, HDAT2,
SpinRite) are marked **[BIOS]**, and UEFI-only ones **[UEFI]**, detected from
each ISO's boot records. Windows `.wim` boot images (WinRE, WinPE tools) work
too: Ventoy's wimboot plugin comes with the stick.

<img src="boot-menu-folder.jpg" alt="Inside a boot-menu category, with tool icons" width="820">

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
| Live Operating Systems | **Lazarus PE**, your own [PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) Windows 11 build | built locally · [guide](../pe/README.md) |
| | Hiren's BootCD PE | hirensbootcd.org · unverified |
| Partition Tools | GParted Live | SourceForge · sha512 |
| Password Removal | *bring your own* (e.g. Jayro's Lockpick) | [`byo/`](../byo/README.md) |
| Windows Recovery | *bring your own* (Windows 10/11 setup, DaRT) | [`byo/`](../byo/README.md) |
| OS Images | *yours*: drop Windows or Linux installer ISOs into `ISO/OSimages` on the stick | shown once it holds an image |

Screenshots are real Ventoy renders of a Helix Boot stick. In the menu, use
Up/Down, Enter and Esc: Ventoy's left/right keys only slide the highlighted
name sideways (built into Ventoy, not a setting).

**Portable apps** for any Windows PE, in `USB:\Apps`, listed by the Lazarus
launcher and by the Helix Apps menu (`HelixApps.cmd`, for other PEs such as Hiren's):
Sysinternals, Explorer++, Notepad++, CrystalDiskInfo, CrystalDiskMark, HWiNFO,
TestDisk & PhotoRec, DiskGenius Free, Microsoft Safety Scanner, and two that
are *off by default*: Kaspersky Virus Removal Tool and ProduKey. The launcher also carries
[Chris Titus Tech's WinUtil](https://github.com/ChrisTitusTech/winutil) for
after a repair: run it from the stick in the fixed Windows to debloat, tweak
or reinstall apps.

**Tools for a Mac**, in `USB:/Mac` with a `README.txt`. Nothing on the stick
boots a Mac (Apple silicon can't start a PC stick at all), so these are for a
Mac that still runs, Apple silicon included: copy a tool to the Mac, then open
it. Each stays as downloaded (`.dmg`, `.pkg`, `.zip`), because an unpacked Mac
app doesn't survive the stick's exFAT file system.

| For | Tools |
|---|---|
| Finding the problem | EtreCheck, Stats, Macs Fan Control, coconutBattery, GrandPerspective |
| Malware | Malwarebytes for Mac, and from [Objective-See](https://objective-see.org): KnockKnock, TaskExplorer, LuLu, Netiquette, BlockBlock |
| Cleaning up | OnyX and Maintenance (one each for macOS 26, 15 and 14), AppCleaner, Pearcleaner |
| Data | SuperDuper! and Vorta (backup), TestDisk & PhotoRec and DMDE (recovery) |
| Reinstalling | Mist (macOS installers), OpenCore Legacy Patcher (newer macOS on older Intel Macs) |
| Handy | Keka (archives macOS can't open by itself), RustDesk (remote support), balenaEtcher (writes boot sticks) |
| Tweaks | [Chris Titus Tech's MacUtil](https://github.com/ChrisTitusTech/macutil) *(on hold upstream)* |

CI opens every one of these on a real Mac, and checks that what is inside is
whole, signed by its developer and accepted by Gatekeeper. The `README.txt`
says which macOS each one needs (AppCleaner 15.6, Keka 10.10, …); CI checks
those against the apps too.

<details>
<summary><b>Notes on unverified tools, antivirus and Kaspersky</b></summary>

*Unverified* means the publisher offers no checksum. The file is trusted on
first download and refused if it later changes without a new version (see
[verification](engine.md#verification)). Antivirus tools carry their virus
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

Every tool is described in [`tools.toml`](../tools.toml); adding one is a few lines.

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
[`byo/`](../byo/README.md) under its slot name and `./refresh.sh` puts it in the
right menu. Anything else (another ISO, a `.wim`, a portable app) gets a slot
of its own in `local.toml`. Nothing in `byo/` is ever downloaded, shared or
committed.

## Your own changes

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
