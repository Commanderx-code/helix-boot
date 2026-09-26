# Commander PE — building the Windows side

Commander PE is a Windows 11 recovery desktop you build yourself with
[PhoenixPE](https://github.com/PhoenixPE/PhoenixPE). You build it rather than
download it because a WinPE image contains Microsoft files, which can't be
legally redistributed. This repo ships the recipe, and your own Windows ISO
provides the files.

The PE image stays **lean**. It boots to a desktop with drivers, networking, and
Explorer. The portable apps (Sysinternals, HWiNFO, CrystalDiskInfo…) live on the
USB in `Apps/` and are updated by `refresh.sh` **without rebuilding the PE**.

```
USB (Ventoy data partition)
├── ISO/1-Windows-PE/CommanderPE.iso   ← what you build here (rebuild rarely)
├── Apps/                              ← refreshed from Linux, any time
│   ├── CommanderApps.cmd              ← menu launcher
│   ├── apps.txt
│   ├── sysinternals/  hwinfo/  crystaldiskinfo/ …
└── commander-rescue.tag               ← how the launcher finds the stick
```

## What you need

| | |
|---|---|
| Build host | Windows 10/11 **x64**. A VM on your Linux box is fine (virt-manager / QEMU). |
| Source | A Windows 11 ISO. PhoenixPE recommends **Win11 23H2** for the fewest quirks. 24H2 and 25H2 work, but taskbar pins can misbehave. Win10 2004 also works. |
| Disk | ~30 GB free in the build VM |
| PhoenixPE | Latest release from [PhoenixPE releases](https://github.com/PhoenixPE/PhoenixPE/releases). It bundles the PEBakery build engine. |

### VM on Garuda (one-time)

```fish
sudo pacman -S --needed virt-manager qemu-full dnsmasq
sudo systemctl enable --now libvirtd
sudo usermod -aG libvirt $USER   # log out/in
```

Create a Windows 11 VM in virt-manager (4 GB RAM, 60 GB disk). It doesn't need
activating to build PE images. To get the ISO out, add a shared folder
(virtiofs), or just copy it over the network.

## Build steps

1. Unpack the PhoenixPE release inside the VM, e.g. `C:\PhoenixPE`.
2. Copy this repo's `pe\` folder into the VM too (or share it), then apply the
   Commander preset from PowerShell:

   ```powershell
   cd <repo>\pe\phoenixpe
   powershell -ExecutionPolicy Bypass -File .\Apply-CommanderPreset.ps1 C:\PhoenixPE -WhatIf   # preview
   powershell -ExecutionPolicy Bypass -File .\Apply-CommanderPreset.ps1 C:\PhoenixPE
   ```

   This installs the **Commander Rescue** add-on (the app launcher, with
   desktop and Start menu shortcuts) and ticks the options in
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
3. Run `PEBakeryLauncher.exe`. **Source:** mount your Windows ISO, point
   PhoenixPE at it and pick the **Pro** edition index. (Windows S isn't
   supported.)
4. **Extra drivers (optional):** for storage or network hardware not covered
   above, drop the extracted `.inf` driver folders into *Drivers → Driver
   Integration* and tick it.
5. Press **Build**. The first build takes longer because it caches the source.
   Later builds take a few minutes.
6. Test the ISO in the VM (boot it as a CD) before putting it on the stick:
   the desktop should show **Commander Apps**.

## Put it on the stick

Copy the finished ISO into this repo as:

```
pe/out/CommanderPE.iso
```

then, on Linux:

```fish
./crescue fetch commander-pe   # registers the local build (hash + date)
./refresh.sh                   # copies it to ISO/1-Windows-PE/
```

`pe/out/` is git-ignored, so the image never gets committed.

## Until the PE is built

Enable Hiren's BootCD PE as a stopgap. It's a free, ready-made Win11 PE:

```toml
# local.toml
[overrides.hirens]
enabled = true
```

`Apps\CommanderApps.cmd` works from Hiren's too.

## When to rebuild

- A new Windows feature update you want as the base
- New hardware that needs storage or network drivers
- A PhoenixPE release with fixes you care about

App updates **never** need a rebuild. `./refresh.sh` handles those.
