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

1. Unpack the PhoenixPE release inside the VM, e.g. `C:\PhoenixPE`, and run
   `PEBakeryLauncher.exe`.
2. **Source:** mount your Windows ISO and point PhoenixPE at it. Pick the
   **Pro** edition index. (Windows S isn't supported.)
3. **Core:** keep the defaults (Explorer shell, networking, Wi-Fi if offered).
4. **Drivers:** add storage and network drivers for the machines you service.
   This matters most on modern Intel laptops: with **Intel VMD/RST** enabled,
   the NVMe drive is invisible to WinPE unless the Intel RST VMD driver is
   injected. Drop the extracted `.inf` driver folders into PhoenixPE's driver
   integration option.
5. **Apps:** enable only what must be *inside* the image, like a browser, 7-Zip
   and the built-in utilities you want on the Start menu. Don't enable the ones
   listed in `tools.toml` under `kind = "app"`, because those come from the USB
   and stay current.
6. **Launcher (optional but nice):** add `pe/launcher/CommanderApps.cmd` as an
   additional file with a desktop shortcut, using PhoenixPE's custom-files /
   shortcut options (names vary by release; see the PhoenixPE wiki). Without
   this step you can still run `Apps\CommanderApps.cmd` straight from the USB.
7. Press **Build**. The first build takes longer because it caches the source.
   Later builds take a few minutes.
8. Test the ISO in the VM (boot it as a CD) before putting it on the stick.

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
