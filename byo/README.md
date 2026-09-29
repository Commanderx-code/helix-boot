# Bring your own

Tools the project can't download or share: paid software, Microsoft images
you download yourself, and free tools whose sites block or time out on
automated downloads (PassMark MemTest86, HDAT2). Put your copy here under the
name below and it gets its own entry in the boot menu:

```fish
cp ~/Downloads/SpinRite.iso byo/spinrite.iso
./refresh.sh
```

| File | Menu entry |
|---|---|
| `macrium-reflect.iso` | Macrium Reflect Rescue |
| `aomei-backupper.iso` | AOMEI Backupper |
| `easeus-todo-backup.iso` | EaseUS Todo Backup |
| `easeus-data-recovery.iso` | EaseUS Data Recovery Wizard |
| `active-data-studio.iso` | Active@ Data Studio |
| `aomei-pa.iso` | AOMEI Partition Assistant |
| `paragon-hdm.iso` | Paragon Hard Disk Manager |
| `parted-magic.iso` | Parted Magic |
| `bootit-bm.iso` | BootIt Bare Metal |
| `hdat2.iso` | HDAT2 |
| `memtest86.img` | PassMark MemTest86 Free |
| `spinrite.iso` | SpinRite |
| `windows11.iso` | Windows 11 Setup |
| `windows10.iso` | Windows 10 Setup |
| `ms-dart.iso` | Microsoft DaRT |
| `lockpick.iso` | Jayro's Lockpick |

Everything in this folder except this README is git-ignored. To keep an ISO
somewhere else, point the slot at it in `local.toml`:

```toml
[overrides.macrium-reflect]
path = "~/isos/Macrium_Rescue.iso"
```

Free ones: HDAT2 is `hdat2cd_<version>.iso` from
[hdat2.com/download.html](https://www.hdat2.com/download.html) (not the
`lite` one); MemTest86 is the `.img` inside `memtest86-usb.zip` from
[memtest86.com](https://www.memtest86.com/download.htm).

Remove the file and the next `./refresh.sh` takes it off the stick. Most
vendors build their rescue ISO from the installed program (look for "Create
bootable media" or "Rescue media"). Pick the WinPE/UEFI option where offered.

## Your own tools

Anything not in the list gets a slot of its own in `local.toml`. A bootable
ISO:

```toml
[[tool]]
name = "acronis"                 # any short id
title = "Acronis True Image"     # menu text
kind = "iso"
category = "imaging"             # antivirus, imaging, boot-repair, diagnostics, wipe,
source = "local"                 #   live, partitioning, password, windows, images
byo = true
path = "byo/acronis.iso"
description = "Shown under the menu when it's highlighted."
```

A portable Windows program, listed by the Lazarus launcher and the **Helix Apps** menu. The
path can be a single `.exe` or a `.zip` (it's unpacked into `USB:\Apps\<name>\`),
and `entry` is the program to launch, relative to that folder:

```toml
[[tool]]
name = "mytool"
title = "My Tool"
kind = "app"
source = "local"
byo = true
path = "byo/MyTool_portable.zip"
entry = "MyTool/MyTool.exe"
```

Then `./refresh.sh`. Trial versions work the same way. Note that many of them
expect activation or an internet connection, which can fail inside WinPE.
Portable versions are the ones to look for.


## Menu icons

Every tool in `tools.toml` has a letter badge in the boot menu. Tools you add
in `local.toml` get theirs with one command (it needs Pillow, and never
overwrites an icon already in `byo/icons/`):

```fish
theme/build-theme.py --local
```

Add `badge = "XX"` to a tool's entry to choose its letters. To show a tool's
real logo instead, save it as `byo/icons/<name>.png`, using the tool's `name` from
`tools.toml` or your `local.toml` (e.g. `byo/icons/macrium-reflect.png`,
`byo/icons/acronis.png`), and refresh. A category's icon is
`byo/icons/cat-<id>.png` (e.g. `cat-antivirus.png`).

Use a square, non-interlaced PNG, ideally 40×40 pixels (larger ones are
scaled down). A tool with no icon at all gets a plain disc. Like everything
else in `byo/`, your icons stay out of git.
