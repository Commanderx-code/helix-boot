# Bring your own

Tools the project can't download or share: paid software, and Microsoft
images you download yourself. Put your copy here under the name below and it
gets its own entry in the boot menu:

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

Remove the file and the next `./refresh.sh` takes it off the stick. Most
vendors build their rescue ISO from the installed program (look for "Create
bootable media" or "Rescue media"). Pick the WinPE/UEFI option where offered.
