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
