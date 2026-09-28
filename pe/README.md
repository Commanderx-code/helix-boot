# Lazarus PE — building the Windows side

Lazarus PE is a Windows 11 recovery desktop you build yourself with
[PhoenixPE](https://github.com/PhoenixPE/PhoenixPE). You build it rather than
download it because a WinPE image contains Microsoft files, which can't be
legally redistributed. This repo ships the recipe, and your own Windows ISO
provides the files.

The PE image stays **lean**. It boots to a desktop with drivers, networking, and
Explorer. The portable apps (Sysinternals, HWiNFO, CrystalDiskInfo…) live on the
USB in `Apps/` and are updated by `refresh.sh` **without rebuilding the PE**.

```
USB (Ventoy data partition)
├── ISO/6-Live-Operating-Systems/LazarusPE.iso   ← what you build here (rebuild rarely)
├── Apps/                              ← refreshed from Linux, any time
│   ├── CommanderApps.cmd              ← menu launcher
│   ├── apps.txt
│   ├── sysinternals/  hwinfo/  crystaldiskinfo/ …
└── commander-rescue.tag               ← how the launcher finds the stick
```

## What you need

| | |
|---|---|
| Build host | Windows 10/11 **x64**. On Linux, `pe/vm/build-vm.sh` makes a VM for you (below). |
| Source | A Windows 11 ISO. PhoenixPE recommends **Win11 23H2** for the fewest quirks. 24H2 and 25H2 work, but taskbar pins can misbehave. Win10 2004 also works. |
| Disk | ~40 GB free on Linux for the VM (its disk grows as it fills, up to 64 GB) |
| PhoenixPE | Latest release from [PhoenixPE releases](https://github.com/PhoenixPE/PhoenixPE/releases). It bundles the PEBakery build engine. With the build VM, save the `PhoenixPE-*.7z` in `~/.local/share/commander-rescue/vm/` and it goes onto the transfer disk for you. |

### VM on Garuda (one-time)

`pe/vm/build-vm.sh` sets up the build VM for you. It runs in your own user's
libvirt session, so it needs no root and no libvirt group. It makes Windows 11
(UEFI + TPM, 6 GB RAM, 64 GB disk) plus a small **transfer disk** that carries
this repo's `pe/` tooling into Windows and the finished ISO back out.

```fish
sudo pacman -S --needed qemu-desktop libvirt virt-install virt-viewer edk2-ovmf swtpm dosfstools mtools
```

1. Download the Windows 11 ISO from
   [microsoft.com/software-download/windows11](https://www.microsoft.com/software-download/windows11)
   (*Download Windows 11 Disk Image (ISO) for x64 devices*).
2. Create the VM and start Windows setup:

   ```fish
   pe/vm/build-vm.sh create ~/Downloads/Win11_25H2_English_x64.iso
   ```

   Click into the window and press a key if it says *Press any key to boot
   from CD*. Choose *I don't have a product key* and **Windows 11 Pro**. You
   don't need to activate Windows to build PE images.
3. Later: `pe/vm/build-vm.sh start` boots it again and `status` shows where
   things stand. `destroy` deletes it all.

If your user's core-dump limit is 0 (Garuda's default), `create` adds
`max_core = 0` to `~/.config/libvirt/qemu.conf`; without it QEMU won't start.

The Windows ISO stays in the VM's DVD drive, which is also PhoenixPE's source.
The transfer disk shows up in Explorer as **CRTRANSFER**, with a README.txt of
these steps. Files move only while the VM is **shut down**: `push` refreshes the
tooling and `pull` fetches the ISO.

## Build steps

1. Unpack the PhoenixPE release inside the VM to `C:\PhoenixPE` (the `.7z` has no
   top folder, so extract into that folder). With the build VM it's on the
   transfer disk: right-click it, *Extract All*.
2. Apply the Commander preset from PowerShell, using the copy of `pe\` on the
   transfer disk (`CRTRANSFER\commander`), or this repo if you build elsewhere:

   ```powershell
   cd E:\commander\phoenixpe        # the CRTRANSFER drive letter may differ
   powershell -ExecutionPolicy Bypass -File .\Apply-CommanderPreset.ps1 C:\PhoenixPE -WhatIf   # preview
   powershell -ExecutionPolicy Bypass -File .\Apply-CommanderPreset.ps1 C:\PhoenixPE
   ```

   This installs the **Commander Rescue** add-on (the app launcher, with
   desktop and Start menu shortcuts, and the PortableApps.com Platform opening
   from the USB when the desktop loads) and ticks the options in
   [`phoenixpe/preset.txt`](phoenixpe/preset.txt):

   | | |
   |---|---|
   | **Intel RST driver** | NVMe drives behind Intel VMD/RST (most 11th-gen+ Intel laptops) are invisible to WinPE without it |
   | **Network drivers** | Windows' own extra Wi-Fi and Ethernet drivers |
   | **PowerShell, Task Manager** | the full versions, not WinPE's cut-down ones |
   | **VC++ 2015–2026 runtime** | so the portable apps on the USB start |
   | Notepad++ **off** | it comes from `USB:\Apps` instead, always current |

   Everything else stays at PhoenixPE's defaults: Explorer with StartAllBack,
   networking, audio, ramdisk, 7-Zip, Firefox. Edit `preset.txt` to taste; a
   script PhoenixPE has renamed is reported, not guessed at.
3. **Exclude the build from Defender first.** Some of PhoenixPE's tools are
   flagged as hack tools or PUAs, and quarantined files break the build. Turn
   *Tamper Protection* off in Windows Security, then in an admin terminal:

   ```powershell
   Add-MpPreference -ExclusionPath 'C:\PhoenixPE','D:\'   # D: = CRTRANSFER
   (Get-MpPreference).ExclusionPath                        # both should be listed
   ```

   Exclusions stay put even when Defender switches its protection back on. If
   Defender already quarantined anything, extract PhoenixPE afresh and rerun
   the preset.
4. Run `PEBakeryLauncher.exe` as administrator. In **Source Config**, set the
   source to the Windows DVD drive root (e.g. `E:\`), keep the base image at
   **2 (Windows Setup)**, pick the **Pro** edition for `install.wim` (Windows S
   isn't supported), and leave **Run all programs from RAM** unticked. Apps
   then load from the stick when opened, so the boot image stays small: it
   boots faster, needs less RAM, and works in legacy BIOS mode, where an image
   over about 1.5 GB fails with *not enough memory to create a ramdisk device*.
   A fresh PhoenixPE folder forgets these settings.
5. **Extra drivers:** Windows PE has no Wi-Fi drivers for most laptop cards.
   Tick *Drivers → Driver Integration* and point **x64 Drivers** at unpacked
   `.inf` driver folders. With the build VM, put them in
   `~/.local/share/commander-rescue/vm/drivers/x64/` and `pe/vm/build-vm.sh
   push`: they appear as `D:\drivers\x64`. For Intel Wi-Fi (AC 9260/9560 and
   AX201/203/210/211 and newer), unzip Intel's
   [IT-admin driver package](https://www.intel.com/content/www/us/en/download/18231/intel-proset-wireless-software-and-wi-fi-drivers-for-it-administrators.html)
   there; the AX200 and older AC cards need Intel's separate legacy packages.
6. Press **Build**. The first build takes longer because it caches the source.
   Later builds take a few minutes.
7. Test the ISO in the VM (boot it as a CD) before putting it on the stick:
   the desktop should show **Commander Apps**.

## Which Windows to build from

Build from **Windows 11 22H2 or 23H2** (build 22621/22631), as PhoenixPE
recommends: on 24H2 and later the PE's Start menu doesn't open. Microsoft only
offers the newest release, so make the older ISO with
[UUP dump](https://uupdump.net), which assembles it on Linux from Microsoft's
own update files (search `22631 amd64`, pick *Windows 11, version 23H2*,
English, Pro, and run its Linux script; it needs `aria2 cabextract wimlib
chntpw cdrtools`). The Linux converter can't add updates, so the result is the
original 22H2 build, which is fine for a PE.

Those older discs have a 2022 UEFI boot manager that hangs on newer UEFI
firmware. After each build, give the PE the boot manager from a current
Windows 11 ISO (the one on Microsoft's download page):

```fish
pe/vm/build-vm.sh pull
pe/fix-bootmgr.sh ~/Downloads/Win11_25H2_English_x64.iso
./crescue fetch lazarus-pe
```

## Put it on the stick

With the build VM: copy the ISO into `CRTRANSFER\out`, shut Windows down, then
run `pe/vm/build-vm.sh pull`. Otherwise, copy it into this repo yourself as:

```
pe/out/LazarusPE.iso
```

Then, on Linux:

```fish
./crescue fetch lazarus-pe   # registers the local build (hash + date)
./refresh.sh                   # copies it to ISO/6-Live-Operating-Systems/
```

`pe/out/` is git-ignored, so the image never gets committed.

## Until the PE is built

Hiren's BootCD PE is on the stick too: a free, ready-made Win11 PE. It covers
for Lazarus PE until yours is built, and `Apps\CommanderApps.cmd` works from
it as well. To leave it off, set `enabled = false` under `[overrides.hirens]`
in `local.toml`.

## When to rebuild

- A new Windows feature update you want as the base
- New hardware that needs storage or network drivers
- A PhoenixPE release with fixes you care about

App updates **never** need a rebuild. `./refresh.sh` handles those.
