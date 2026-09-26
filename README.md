<div align="center">

# Commander Rescue

**A lean, always-current multiboot rescue USB, in the spirit of MediCat.**

One stick with a Windows 11 PE desktop and the best free Linux rescue tools,
rebuilt from upstream sources and verified before it touches your drive.

</div>

---

MediCat was the stick everyone carried, but its last full build is from
December 2021. It has 15 overlapping tools, most of them commercial trialware,
all frozen at 2021 versions. Commander Rescue keeps the idea and drops the rest:

- **One tool per job.** Only free tools, with no trial nags.
- **Always current.** Every tool resolves to its latest upstream release.
- **Verified.** Downloads are checked against the publisher's own checksums.
  Anything without one is flagged loudly instead of trusted silently.
- **Refreshable in place.** `./refresh.sh` swaps new versions onto the stick
  and leaves the ISOs you added yourself alone.
- **No redistribution headaches.** The repo holds a manifest and scripts, not
  binaries. The Windows PE is built from *your* Windows ISO.

## What's on the stick

| Menu | Tool | Source |
|---|---|---|
| Windows PE | **Commander PE**, your own [PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) Win11 build | built locally ([guide](pe/README.md)) |
| | Hiren's BootCD PE *(off by default, stopgap)* | hirensbootcd.org |
| Linux Rescue | SystemRescue | SourceForge, sha512 |
| Backup & Imaging | Rescuezilla, Clonezilla | GitHub / SourceForge |
| Partitioning | GParted Live | SourceForge, CHECKSUMS.TXT |
| Hardware Diagnostics | Memtest86+ | GitHub |
| Secure Wipe | ShredOS (nwipe) | GitHub |
| **PE apps** (`USB:\Apps`) | Sysinternals, Explorer++, Notepad++, CrystalDiskInfo, CrystalDiskMark, HWiNFO, TestDisk/PhotoRec, ProduKey | various |

Everything lives in [`tools.toml`](tools.toml). Adding a tool is a few lines.

## Quick start

Requirements: Linux, Python 3.11+, `sudo`, and `udisksctl` (optional). There's
nothing to `pip install`.

```fish
git clone https://github.com/Commanderx-code/commander-rescue
cd commander-rescue

./crescue check        # what's the latest of everything? (no downloads)
./install.sh           # download + verify, pick a stick, type its name, done
```

Later:

```fish
./refresh.sh                    # update the stick in place
./refresh.sh --upgrade-ventoy   # …and the Ventoy boot loader too
```

## `crescue`, the engine

`install.sh` and `refresh.sh` are thin wrappers. The work happens in `crescue`,
a single standard-library Python script:

| Command | Does |
|---|---|
| `crescue list` | every tool, its source, and whether it's enabled |
| `crescue check [--json]` | compares your cache against upstream, no downloads |
| `crescue fetch [tool…] [--force]` | downloads, verifies, caches (`~/.cache/commander-rescue`), resumes interrupted downloads |
| `crescue sync <mount> [--dry-run] [--verify]` | copies the cache to a Ventoy stick, prunes old versions, writes `ventoy.json` |

### How verification works

Each tool lists checksum strategies in order of preference. The first one
that yields a hash is used, and a mismatch deletes the file and stops:

1. the publisher's checksum file (`sha256.txt`, `CHECKSUMS.TXT`, `*.sha512`)
2. GitHub's recorded sha256 digest for the release asset
3. SourceForge's md5 (integrity only)
4. `tofu`: trust-on-first-use, **only if the manifest explicitly says so**.
   The hash is recorded, and a re-download of the same version with a
   different hash is refused as possible tampering.

If no strategy works, the tool is refused rather than silently used.

## Customising

Personal changes go in `local.toml` (git-ignored). It overlays `tools.toml`:

```toml
[overrides.hirens]
enabled = true              # turn on the stopgap PE

[overrides.shredos]
enabled = false             # don't want a wipe tool on this stick

[[tool]]                    # add your own
name = "kali"
title = "Kali Linux"
kind = "iso"
category = "rescue"
source = "url"
url = "https://cdimage.kali.org/current/kali-linux-2026.3-live-amd64.iso"
version_pin = "2026.3"
checksum = [{ url = "https://cdimage.kali.org/current/SHA256SUMS" }]
```

ISOs you drop onto the stick by hand (e.g. in `ISO/Custom/`) are never touched.

## Layout on the stick

```
ISO/1-Windows-PE/   ISO/2-Rescue/   ISO/3-Imaging/   ISO/4-Partitioning/
ISO/5-Diagnostics/  ISO/6-Data-Wipe/
Apps/               portable apps + CommanderApps.cmd launcher
ventoy/ventoy.json  generated menu: tree view, friendly names, tips
.commander-rescue/  sync state (which files this project manages)
```

## Safety

- `install.sh` downloads and verifies **before** touching any disk.
- It lists only USB/removable disks and refuses any disk holding your running
  system (it follows LUKS, LVM and btrfs subvolumes back to the physical disk).
- You must type the device name to confirm, and it warns if the "stick" is
  suspiciously large.
- `refresh.sh` never erases anything except old versions of files it put there.

## Status

- [x] Manifest, fetch/verify engine, installer, refresher, Ventoy menu
- [x] PE app launcher (works in any WinPE)
- [ ] First Commander PE build + recommended PhoenixPE preset
- [ ] Ventoy theme
- [ ] Commander Toolbox entry

## Credits

[Ventoy](https://www.ventoy.net) · [PhoenixPE](https://github.com/PhoenixPE/PhoenixPE) ·
every tool author listed in `tools.toml` · inspired by MediCat USB.
Each tool keeps its own license; this repo's scripts are MIT.
