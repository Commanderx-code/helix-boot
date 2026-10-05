#!/usr/bin/env python3
"""Helix Boot for Windows: build or refresh the rescue stick from a window.

The same engine as the Linux scripts (helix: tools.toml, verified downloads,
local.toml, byo/, theme) behind a small tkinter GUI. Ventoy is installed with
its own command-line mode (Ventoy2Disk.exe VTOYCLI …).

    HelixBoot.exe                   the window
    HelixBoot.exe --list [--all]    USB disks as JSON
    HelixBoot.exe --fetch [tool…]   download + verify into the cache
    HelixBoot.exe --install N --yes erase disk N, install Ventoy, fill it
    HelixBoot.exe --update N        refresh a stick in place
    HelixBoot.exe --sync-to DIR     fill a folder (testing)
    … --pack PACK.zip               with --install / --update: everything from a pack,
                                    offline (--unpack-to DIR fills a folder from one)

A pack beside the app (or beside the installer folder it was unzipped to) is
picked up by the window on its own.

The .exe has no console, so command-line output also goes to helix-boot.log
next to it (or wherever --log points).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# helix is loaded from a data file, so PyInstaller can't see what it imports; name it here.
# (tests/test_windows_app.py checks this list against helix.)
import ctypes  # noqa: F401
import email.utils  # noqa: F401
import fnmatch  # noqa: F401
import hashlib  # noqa: F401
import html  # noqa: F401
import http.client  # noqa: F401
import lzma  # noqa: F401
import mmap  # noqa: F401
import re  # noqa: F401
import struct  # noqa: F401
import tarfile  # noqa: F401
import tempfile  # noqa: F401
import tomllib  # noqa: F401
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
import xml.etree.ElementTree  # noqa: F401
import zipfile  # noqa: F401
import zlib  # noqa: F401

try:  # Windows only fetches a root certificate the first time something asks its own way, and
    # Python doesn't: a site whose root this PC hasn't met fails with CERTIFICATE_VERIFY_FAILED.
    import ssl
    import certifi
    _https = ssl.create_default_context()
    _https.load_verify_locations(certifi.where())       # Mozilla's roots, on top of the system's
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=_https)))
except ImportError:
    pass

try:  # optional there: previews, resizing your pictures, the splash's loading bar
    import PIL.Image  # noqa: F401
    import PIL.ImageDraw  # noqa: F401
    import PIL.ImageFilter  # noqa: F401
    import PIL.ImageFont  # noqa: F401
    import PIL.ImageOps  # noqa: F401
except ImportError:
    pass

class _NoConsole(io.TextIOBase):
    """Where output goes before the window takes over, when there's no console. (Not
    os.devnull: on Windows NUL counts as a terminal, which would turn helix's colours on.)"""

    def write(self, text):
        return len(text)

    def isatty(self):
        return False


# Started from Explorer, a windowed program has no console: sys.stdout and sys.stderr are
# None, and anything that prints (or asks isatty) before the window takes over would crash.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, _NoConsole())

APP = "Helix Boot"
FROZEN = getattr(sys, "frozen", False)
USB_BUSES = {"USB", "SD", "MMC"}
BIG_DISK = 300 * 1000**3
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashing up for PowerShell


def bundle_dir() -> Path:
    """Shipped files: helix, tools.toml, theme/, pe/launcher/."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def user_dir() -> Path:
    """Your files: local.toml and byo/, next to the .exe (or the repo when run from source)."""
    return Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent


def load_helix():
    path = bundle_dir() / "helix"
    loader = importlib.machinery.SourceFileLoader("helix", str(path))
    spec = importlib.util.spec_from_loader("helix", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


if os.name == "nt":
    import msvcrt  # noqa: F401  (helix reads a stick back unbuffered with it)
    import winreg  # noqa: F401  (… and finds 7-Zip where its installer says it is)

cr = load_helix()


class RescueError(cr.RescueError):
    pass


def config():
    if "HELIX_CACHE" not in os.environ and "CRESCUE_CACHE" not in os.environ and os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
        if not (base / "HelixBoot").exists() and (base / "CommanderRescue").is_dir():
            os.rename(base / "CommanderRescue", base / "HelixBoot")   # its name before the rename
        os.environ["HELIX_CACHE"] = str(base / "HelixBoot" / "cache")
    mine = user_dir()
    (mine / "byo").mkdir(exist_ok=True)
    readme = bundle_dir() / "byo" / "README.md"
    if readme.exists() and not (mine / "byo" / "README.md").exists():
        shutil.copy2(readme, mine / "byo" / "README.md")
    return cr.Config(repo=mine, assets=bundle_dir())


def ns(**kw):
    return argparse.Namespace(**kw)


# ── Disks (PowerShell storage cmdlets) ─────────────────────────────────────
# A Ventoy stick is known by Ventoy's own small partition, always labelled VTOYEFI. The data
# partition is the one labelled Ventoy or, since people rename it, the biggest other one.
DISKS_PS = r"""
Get-Disk | ForEach-Object {
  $v = @(Get-Partition -DiskNumber $_.Number -ErrorAction SilentlyContinue |
         Get-Volume -ErrorAction SilentlyContinue)
  $data = @($v | Where-Object { $_.DriveLetter -and $_.FileSystemLabel -eq 'Ventoy' })
  if (-not $data -and ($v | Where-Object FileSystemLabel -eq 'VTOYEFI')) {
    $data = @($v | Where-Object { $_.DriveLetter -and $_.FileSystemLabel -ne 'VTOYEFI' } | Sort-Object Size -Descending)
  }
  [pscustomobject]@{
    Number  = [int]$_.Number
    Name    = "$($_.FriendlyName)"
    Serial  = "$($_.SerialNumber)"
    Id      = "$($_.UniqueId)"
    Path    = "$($_.Path)"
    Size    = [int64]$_.Size
    Bus     = "$($_.BusType)"
    System  = [bool]($_.IsSystem -or $_.IsBoot)
    Labels  = @($v | ForEach-Object { "$($_.FileSystemLabel)" })
    Letters = @($v | Where-Object DriveLetter | ForEach-Object { "$($_.DriveLetter)" })
    Ventoy  = "$(($data | Select-Object -First 1).DriveLetter)"
  }
} | ConvertTo-Json -Compress -Depth 3
"""


def system_tool(*parts: str, folder: str | None = None) -> str:
    """The full path of one of Windows' own programs, in its system folder. The app runs with
    admin rights, so a program is never looked up by name: a file of that name in the folder
    the app was started from, or on the PATH, would be run instead."""
    if folder is None:
        if os.name != "nt":
            return parts[-1]
        buf = ctypes.create_unicode_buffer(260)
        n = ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260)
        if not 0 < n < 260:
            raise RescueError("Windows didn't say where its system folder is")
        folder = buf.value
    path = Path(folder).joinpath(*parts)
    if not path.is_file():
        raise RescueError(f"{path} is missing from Windows")
    return str(path)


def powershell(script: str) -> str:
    # stdin=DEVNULL: PowerShell started from a windowless app otherwise waits on input forever
    try:
        exe = system_tool("WindowsPowerShell", "v1.0", "powershell.exe")
        # (started in the system folder too: nothing it looks up is found in the app's own folder)
        r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                           cwd=os.path.dirname(exe) or None, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
                           creationflags=NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        raise RescueError("PowerShell didn't answer within 2 minutes") from None
    if r.returncode:
        raise RescueError(f"PowerShell failed: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout


def all_disks(run=powershell) -> list[dict]:
    out = run(DISKS_PS).strip()
    data = json.loads(out) if out else []
    disks = data if isinstance(data, list) else [data]
    for d in disks:
        d["Labels"] = [x for x in (d.get("Labels") or []) if x]
        d["IsVentoy"] = "VTOYEFI" in d["Labels"]        # whatever the data partition has been renamed to
    return sorted(disks, key=lambda d: d["Number"])


def usb_disks(run=powershell) -> list[dict]:
    """Disks it's safe to offer: USB/SD, never one holding the running system."""
    return [d for d in all_disks(run) if d.get("Bus") in USB_BUSES and not d.get("System")]


def human(size: int) -> str:
    return f"{size / 1000**3:.0f} GB" if size >= 10 * 1000**3 else f"{size / 1000**3:.1f} GB"


def pick(disk_no: int, run=powershell) -> dict:
    for d in all_disks(run):
        if d["Number"] == disk_no:
            if d.get("System"):
                raise RescueError(f"Disk {disk_no} holds the running Windows. Refusing.")
            if d.get("Bus") not in USB_BUSES:
                raise RescueError(f"Disk {disk_no} ({d['Name']}) isn't a USB/SD disk. Refusing.")
            return d
    raise RescueError(f"there's no disk {disk_no}")


def disk_identity(d: dict) -> tuple:
    """What tells this disk from another that takes its place under the same number: its hardware
    serial, or for the many sticks that report none, the id Windows gave this one when it was
    plugged in. Without either there is nothing to hold a confirmation to, so nothing is written."""
    for key in ("Serial", "Id", "Path"):
        value = str(d.get(key) or "").strip()
        if value:
            return key, value, d["Size"], d["Bus"]
    raise RescueError("Windows reports nothing that identifies this disk (no serial, no device id); "
                      "refusing to write")


def recheck_disk(expected: dict, run=powershell, *, same_volume: bool = False) -> dict:
    current = pick(expected["Number"], run)
    if disk_identity(current) != disk_identity(expected):
        raise RescueError("The selected disk was replaced. Select and confirm it again.")
    if same_volume and (current.get("Ventoy") != expected.get("Ventoy") or not current.get("IsVentoy")):
        raise RescueError("The stick's drive letter changed. Preview and confirm the update again.")
    return current


def wait_for_ventoy_letter(disk_no: int, run=powershell, timeout: float = 90, expected: dict | None = None) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        d = next((d for d in all_disks(run) if d["Number"] == disk_no), None)
        if d and expected is not None:
            d = recheck_disk(expected, run)
        if d and d.get("Ventoy") and d.get("IsVentoy"):
            return f"{d['Ventoy']}:\\"
        time.sleep(2)
    raise RescueError(f"the Ventoy partition on disk {disk_no} didn't get a drive letter. "
                      "Open Disk Management, give it one, then use Update.")


# ── Ventoy (its own CLI mode) ──────────────────────────────────────────────
def ventoy_command(vdir: Path, mode: str, disk_no: int, gpt: bool = True, secure_boot: bool = True) -> list[str]:
    exe = vdir / "Ventoy2Disk.exe"
    x64 = vdir / "altexe" / "Ventoy2Disk_X64.exe"
    if os.environ.get("PROCESSOR_ARCHITECTURE", "").upper() == "AMD64" and x64.exists():
        # Ventoy's docs: the x64 build is run from the top folder, next to ventoy/ and boot/
        exe = vdir / "Ventoy2Disk_X64.exe"
        if not exe.exists():
            shutil.copy2(x64, exe)
    args = [str(exe), "VTOYCLI", mode, f"/PhyDrive:{disk_no}"]
    if mode == "/I" and gpt:
        args.append("/GPT")
    if not secure_boot:
        args.append("/NoSB")
    return args


def run_ventoy(args: list[str], vdir: Path, progress=lambda pct: None, timeout: float = 1200) -> None:
    """Run Ventoy2Disk in CLI mode; it reports through cli_percent.txt / cli_done.txt."""
    done, pct_file, log = vdir / "cli_done.txt", vdir / "cli_percent.txt", vdir / "cli_log.txt"
    for f in (done, pct_file):
        f.unlink(missing_ok=True)
    proc = subprocess.Popen(args, cwd=vdir, stdin=subprocess.DEVNULL,
                            creationflags=NO_WINDOW if os.name == "nt" else 0)
    end = time.monotonic() + timeout
    while not done.exists():
        if time.monotonic() > end:
            proc.kill()
            raise RescueError("Ventoy didn't finish within 20 minutes")
        if proc.poll() is not None and not done.exists():
            time.sleep(1)  # a relaunched process may still be writing
            if not done.exists() and proc.returncode:
                break
        try:
            progress(int(pct_file.read_text().strip() or 0))
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    try:
        proc.wait(timeout=60)  # let Ventoy finish flushing before anyone touches the disk
    except subprocess.TimeoutExpired:
        pass
    result = done.read_text().strip() if done.exists() else "missing"
    if result != "0":
        tail = log.read_text(errors="replace").splitlines()[-15:] if log.exists() else []
        raise RescueError("Ventoy reported a failure (cli_done.txt: %s)%s" %
                          (result, "\n  " + "\n  ".join(tail) if tail else ""))
    progress(100)


# ── The two jobs ───────────────────────────────────────────────────────────
def fetch(cfg, tools=()) -> bool:
    print(f"Downloading and verifying into {cfg.cache} …")
    return cr.cmd_fetch(cfg, ns(tools=list(tools), force=False)) == 0


def ventoy_dir(cfg) -> Path:
    lock = cr.load_lock(cfg)
    entry = lock.get("ventoy")
    path = cfg.cache / "ventoy" / entry["final"] if entry else None
    if not path or not (path / "Ventoy2Disk.exe").exists():
        raise RescueError("the Windows Ventoy package isn't downloaded — check your connection and try again")
    return path


# ── Packs (made on Linux with `helix pack`) ────────────────────────────────
def is_pack(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return cr.PACK_META in names or cr.OLD_PACK_META in names


def find_pack(here: Path | None = None) -> Path | None:
    """The newest pack beside the app, or beside the installer folder it was unzipped into."""
    here = here or user_dir()
    places = [here, here.parent] if here.name.lower() == "installer" else [here]
    packs = [z for d in places for z in sorted(d.glob("*.zip")) if is_pack(z)]
    return max(packs, key=lambda z: z.stat().st_mtime) if packs else None


def pack_ventoy_dir(cfg, pack) -> Path:
    return cr._ventoy_from_pack(cfg, str(pack), windows=True)


def unpack(cfg, target: str, pack, init: bool) -> None:
    print(f"\nCopying from {Path(pack).name} to {target} …")
    if cr.cmd_unpack(cfg, ns(pack=str(pack), target=target, init=init, dry_run=False, verify=True,
                             no_prune=False)):
        raise RescueError("copying from the pack failed (see above)")


def sync(cfg, target: str, init: bool) -> None:
    print(f"\nCopying tools to {target} …")
    if cr.cmd_sync(cfg, ns(target=target, init=init, dry_run=False, verify=True, no_prune=False)):
        raise RescueError("copying to the stick failed (see above)")


def name_stick(letter: str, label: str, run=powershell) -> None:
    """Give a new stick its name (Ventoy for Windows can't; its own is "Ventoy"). Never fatal."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,11}", label or "") or label == "Ventoy":
        return
    try:
        run(f"Set-Volume -DriveLetter {letter[0]} -NewFileSystemLabel '{label}'")
        print(f"✓ Stick named {label}")
    except cr.RescueError as e:
        print(f"! couldn't name the stick {label}: {e}")


def update_summary(cfg, target: str, pack=None, on_plan=lambda nbytes: None) -> str:
    """What an update would copy, remove and keep, in plain words. `on_plan` is told how many
    bytes that is, for the window's progress bar."""
    plan = cr.update_plan(cfg, target, str(pack) if pack else None, init=True, verify=True)
    on_plan(copy_bytes(plan))
    return cr.plan_text(plan)


def copy_bytes(plan: list) -> int:
    """How many bytes an update's plan says it will copy."""
    return sum(size for kind, _, size in plan if kind == "copy" and size > 0)


def install(disk_no: int, gpt=True, secure_boot=True, progress=lambda pct: None, run=powershell,
            ventoy=run_ventoy, keep_going=lambda: True, pack=None, expected=None, on_plan=lambda nbytes: None,
            test=False) -> str:
    """Erase disk N, put Ventoy on it, fill it (from the internet, or from a pack). With `test`,
    the empty stick is written full and read back first, and a stick that fails is left empty.
    Returns the stick's drive letter."""
    cfg = config()
    d = recheck_disk(expected, run) if expected is not None else pick(disk_no, run)
    disk_identity(d)
    if pack:   # everything comes out of the pack: check it has Ventoy for Windows before erasing
        vdir = pack_ventoy_dir(cfg, pack)
    else:
        if not fetch(cfg) and not keep_going():
            raise RescueError("stopped — nothing was written to any disk")
        vdir = ventoy_dir(cfg)
    recheck_disk(d, run)
    print(f"\nInstalling Ventoy on disk {disk_no} ({d['Name']}, {human(d['Size'])}) …")
    ventoy(ventoy_command(vdir, "/I", disk_no, gpt, secure_boot), vdir, progress)
    letter = wait_for_ventoy_letter(disk_no, run, expected=d)
    print(f"✓ Ventoy installed, stick is {letter}")
    name_stick(letter, getattr(cfg, "stick_label", ""), run)
    d = recheck_disk(d, run)
    if f"{d['Ventoy']}:\\" != letter:
        raise RescueError("The stick drive letter changed before copying")
    if test:
        test_stick(letter, progress)
        recheck_disk(d, run)
    try:        # how much there is to copy, for the window's progress bar
        on_plan(copy_bytes(cr.update_plan(cfg, letter, str(pack) if pack else None, init=True)))
    except cr.RescueError:
        pass
    if pack:
        unpack(cfg, letter, pack, init=True)
    else:
        sync(cfg, letter, init=True)
    recheck_disk(d, run)
    if wait_for_ventoy_letter(disk_no, run, expected=d) != letter:
        raise RescueError("The stick drive letter changed; refusing to write its boot script")
    boot_script(letter, disk_no=disk_no, run=run)
    return letter


def update(disk_no: int, upgrade_ventoy=False, secure_boot=True, progress=lambda pct: None,
           run=powershell, ventoy=run_ventoy, pack=None, confirm=lambda summary: True, expected=None,
           on_plan=lambda nbytes: None) -> str:
    """Refresh a Helix Boot / Ventoy stick in place. Never erases. `confirm` is shown what the
    update will copy, remove and keep before anything is written, and can call it off."""
    cfg = config()
    d = recheck_disk(expected, run) if expected is not None else pick(disk_no, run)
    disk_identity(d)
    if not d.get("IsVentoy") or not d.get("Ventoy"):
        raise RescueError(f"disk {disk_no} doesn't have Ventoy on it (or no drive letter) — use Install")
    if not pack:
        fetch(cfg)
    recheck_disk(d, run, same_volume=True)
    # (init=True below: this disk was just checked to be a Ventoy stick, whatever it has been named)
    summary = update_summary(cfg, f"{d['Ventoy']}:\\", pack, on_plan=on_plan)
    print(f"\nThis update will:\n{summary}\n")
    if not confirm(summary):
        raise RescueError("stopped — nothing on the stick was changed")
    recheck_disk(d, run, same_volume=True)
    if upgrade_ventoy:
        vdir = pack_ventoy_dir(cfg, pack) if pack else ventoy_dir(cfg)
        recheck_disk(d, run, same_volume=True)
        print(f"\nUpdating Ventoy on disk {disk_no} (your files are kept) …")
        ventoy(ventoy_command(vdir, "/U", disk_no, secure_boot=secure_boot), vdir, progress)
    letter = wait_for_ventoy_letter(disk_no, run, expected=d)
    recheck_disk(d, run, same_volume=True)
    if pack:
        unpack(cfg, letter, pack, init=True)
    else:
        sync(cfg, letter, init=True)
    recheck_disk(d, run)
    if wait_for_ventoy_letter(disk_no, run, expected=d) != letter:
        raise RescueError("The stick drive letter changed; refusing to write its boot script")
    boot_script(letter, disk_no=disk_no, run=run)      # again after a Ventoy upgrade, which replaces it
    return letter


def updates_notice(cfg, refresh: bool = False) -> str:
    """The line under the app's title: which tools have newer versions than this PC has.
    Looking that up asks GitHub and the tools' own sites for their latest version numbers,
    so `check_for_updates = false` under [settings] in local.toml turns it off."""
    if cfg.settings.get("check_for_updates", True) is False:
        return "Not looking for newer versions of the tools (check_for_updates = false in local.toml)."
    return cr.updates_text(cr.tool_updates(cfg, refresh=refresh))


# Ventoy's own small partition has no drive letter, but Windows knows it as a volume (that is how
# a Ventoy stick is recognised above), and a volume's files can be reached by its id.
EFI_PS = ("(Get-Partition -DiskNumber {n} | Get-Volume | Where-Object FileSystemLabel -eq 'VTOYEFI' | "
          "Select-Object -First 1).Path")


def boot_script(target: str, efi: str | None = None, disk_no: int | None = None, run=powershell) -> bool:
    """The splash before the menu and what the L and F1 keys do: a few lines in Ventoy's own boot
    script, as install.sh and refresh.sh add on Linux. `target` is the stick's drive; `efi` Ventoy's
    partition (found from the disk's number if not given). Never fatal: a stick it can't be done on
    starts as Ventoy does, and its menu shows the keys as Ventoy has them. False then."""
    cfg = config()
    try:
        efi = efi or run(EFI_PS.format(n=int(disk_no))).strip()
        if not efi:
            raise RescueError("Windows doesn't show Ventoy's own partition on this disk")
        if cr.cmd_splash(cfg, ns(efi=efi, remove=False, dry_run=False, stick=target)):
            raise RescueError("Ventoy's boot script couldn't be changed")
        return True
    except (cr.RescueError, OSError, ValueError) as e:
        print(f"! no splash, and L and F1 stay Ventoy's Language and Help: {e}")
        try:
            cr.forget_keys_hook(cfg, Path(target))
        except (cr.RescueError, OSError):
            pass
        return False


def check(target: str, progress=lambda pct: None) -> str:
    """Read a stick back and compare it with what was put on it. Needs no downloads.
    Returns what it found; raises RescueError when something is damaged or missing."""
    print(f"\nChecking {target} (reads the whole stick, so this takes a while) …")
    found = cr.check_stick(Path(target), hook=progress)
    text = cr.check_text(found)
    print(text)
    if found["damaged"] or found["missing"] or found["menu"] or found["changed"]:
        raise RescueError(text)
    return text


def test_stick(target: str, progress=lambda pct: None) -> str:
    """Write a stick's free space full, read it back and delete it. Raises RescueError for a
    stick that loses what is written to it, or has less room than it says."""
    print(f"\nTesting {target}: writes its free space full and reads it back, so this takes a while …")
    watch, cr.Progress.watch = cr.Progress.watch, None      # the bar shows percent here, not bytes copied
    try:
        found = cr.test_stick(Path(target), hook=progress)
    finally:
        cr.Progress.watch = watch
    text = cr.test_text(found)
    print(text)
    if found["bad"] or found["error"] or not found["written"]:
        raise RescueError(text)
    return text


def repair(target: str, run=None) -> str:
    """Have Windows repair the stick's filesystem (chkdsk /f; /x closes whatever has it open).
    Returns what chkdsk said; raises RescueError if it couldn't repair it."""
    drive = Path(target).drive or str(target).rstrip("\\")
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise RescueError(f"{target} isn't a drive letter")
    print(f"\nRepairing the filesystem on {drive} (chkdsk {drive} /f /x) …")
    if run is None:
        def run(cmd):
            r = subprocess.run(cmd, cwd=os.path.dirname(cmd[0]) or None, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="oem",
                               errors="replace", timeout=3600, creationflags=NO_WINDOW if os.name == "nt" else 0)
            return r.returncode, r.stdout + r.stderr
    try:
        code, said = run([system_tool("chkdsk.exe"), drive, "/f", "/x"])
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RescueError(f"chkdsk couldn't be run: {e}") from None
    said = "\n".join(line.rstrip() for line in said.splitlines() if line.strip())
    print(said)
    # 0: nothing wrong. 1: errors found and fixed. 2: tidied up. 3: couldn't check or couldn't fix.
    if code >= 3:
        raise RescueError(f"Windows couldn't repair {drive}. If it keeps failing, the stick is worn out: "
                          f"make a new one.\n\n{said[-600:]}")
    return (f"✓ {drive} had errors and Windows repaired them. Update the stick, then Check stick."
            if code else f"✓ Windows found nothing wrong with the filesystem on {drive}.")


# ── Output plumbing ────────────────────────────────────────────────────────
class Tee:
    """Stand-in for stdout/stderr: to the GUI queue and/or a log file."""

    def __init__(self, *sinks):
        self.sinks = [s for s in sinks if s]

    def write(self, text):
        for s in self.sinks:
            if not hasattr(s, "write"):
                s.put(text)
                continue
            try:
                s.write(text)
            except UnicodeEncodeError:  # a cp1252 Windows console can't show ✓ / ✗
                enc = getattr(s, "encoding", None) or "ascii"
                s.write(text.encode(enc, "replace").decode(enc))
        return len(text)

    def flush(self):
        for s in self.sinks:
            getattr(s, "flush", lambda: None)()

    def isatty(self):
        return False


def open_log(path: Path | None):
    path = path or user_dir() / "helix-boot.log"
    try:
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    f.write(f"\n── {APP} {dt.datetime.now():%Y-%m-%d %H:%M:%S} ──\n")
    return f


# ── GUI ────────────────────────────────────────────────────────────────────
# One dark look for both windows, in the boot menu's colours.
BG, PANEL, FIELD, EDGE = "#14121f", "#1d1a2e", "#262238", "#3a3555"
TEXT, MUTED, ACCENT, ACCENT_HOT, VIOLET = "#ece8f7", "#a79fc0", "#19c3d6", "#3fdcee", "#b55eff"
FONT = "Segoe UI" if os.name == "nt" else "DejaVu Sans"


def apply_theme(root) -> None:
    """Dark, flat widgets: ttk's own "clam" theme recoloured (Windows' native one can't be)."""
    from tkinter import ttk
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=BG)
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=EDGE,
                    lightcolor=EDGE, darkcolor=EDGE, troughcolor=FIELD, focuscolor=ACCENT, font=(FONT, 10))
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("News.TLabel", foreground=ACCENT_HOT, font=(FONT, 9))
    style.configure("Title.TLabel", font=(FONT, 18, "bold"))
    style.configure("TButton", background=PANEL, foreground=TEXT, padding=(12, 7), relief="flat", borderwidth=1)
    style.map("TButton", background=[("disabled", BG), ("pressed", EDGE), ("active", FIELD)],
              foreground=[("disabled", "#6d6787")])
    style.configure("Accent.TButton", background=ACCENT, foreground="#06222a", font=(FONT, 11, "bold"), padding=(12, 11))
    style.map("Accent.TButton", background=[("disabled", "#1f4a52"), ("pressed", "#12a3b3"), ("active", ACCENT_HOT)],
              foreground=[("disabled", "#0c2f36")])
    style.configure("Big.TButton", font=(FONT, 11), padding=(12, 11))
    style.configure("Go.TButton", background=ACCENT, foreground="#06222a", font=(FONT, 10, "bold"))
    style.map("Go.TButton", background=[("disabled", "#1f4a52"), ("pressed", "#12a3b3"), ("active", ACCENT_HOT)],
              foreground=[("disabled", "#0c2f36")])
    for kind in ("TCheckbutton", "TRadiobutton"):
        style.configure(kind, background=BG, foreground=TEXT, indicatorbackground=FIELD, indicatorforeground=TEXT,
                        indicatorcolor=FIELD, padding=(0, 3))
        style.map(kind, background=[("active", BG)], foreground=[("disabled", "#6d6787")],
                  indicatorcolor=[("selected", ACCENT), ("pressed", EDGE)],
                  indicatorbackground=[("selected", ACCENT)])
    style.configure("TCombobox", fieldbackground=FIELD, background=PANEL, foreground=TEXT, arrowcolor=TEXT,
                    selectbackground=FIELD, selectforeground=TEXT, padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD), ("disabled", BG)],
              foreground=[("disabled", "#6d6787")], selectbackground=[("readonly", FIELD)])
    for opt, value in (("background", FIELD), ("foreground", TEXT), ("selectBackground", ACCENT),
                       ("selectForeground", "#06222a")):
        root.option_add(f"*TCombobox*Listbox.{opt}", value)
    style.configure("TSeparator", background=EDGE)
    style.configure("Horizontal.TScale", background=BG, troughcolor=FIELD)
    # a progress bar with its text inside it
    style.layout("Text.Horizontal.TProgressbar", [
        ("Horizontal.Progressbar.trough", {"sticky": "nswe", "children": [
            ("Horizontal.Progressbar.pbar", {"side": "left", "sticky": "ns"})]}),
        ("Horizontal.Progressbar.label", {"sticky": ""})])
    style.configure("Text.Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD, bordercolor=EDGE,
                    lightcolor=ACCENT, darkcolor=ACCENT, foreground=TEXT, thickness=30, text="", anchor="center",
                    font=(FONT, 10))
    if os.name == "nt":             # a dark title bar to go with it (Windows 10 20H1 and later; else ignored)
        try:
            import ctypes
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:  # noqa: BLE001 — only looks
            pass


def _picture(master, name: str):
    """A bundled picture (beside the app's files, or in windows/ when run from source), or None."""
    import tkinter as tk
    for path in (bundle_dir() / name, bundle_dir() / "windows" / name):
        if path.is_file():
            try:
                return tk.PhotoImage(master=master, file=str(path))
            except tk.TclError:
                return None
    return None


def logo_image(master):
    """The HB mark for a window's header, or None where the picture can't be loaded."""
    return _picture(master, "logo.png")


def set_icon(root) -> None:
    """The app's icon on its windows and taskbar button (new windows of this root take it too)."""
    icon = _picture(root, "icon.png")
    if icon:
        root.iconphoto(True, icon)
        root._helix_icon = icon         # Tk drops an image nothing refers to


def gui(selftest: bool = False) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    q: queue.Queue = queue.Queue()
    log = open_log(None)
    sys.stdout = sys.stderr = Tee(q, log)

    root = tk.Tk()
    root.title(APP)
    root.geometry("600x584")
    root.minsize(560, 564)
    apply_theme(root)
    set_icon(root)
    style = ttk.Style(root)

    frm = ttk.Frame(root, padding=(18, 14, 18, 16))
    frm.pack(fill="both", expand=True)
    head = ttk.Frame(frm)
    head.pack(fill="x")
    logo = logo_image(root)             # (kept in a variable: Tk drops an image nothing refers to)
    if logo:
        ttk.Label(head, image=logo).pack(side="left", padx=(0, 12))
    ttk.Label(head, text="Helix Boot", style="Title.TLabel").pack(side="left")
    ttk.Label(head, text=f"v{cr.__version__}", style="Muted.TLabel").pack(side="right", anchor="n")
    ttk.Separator(frm).pack(fill="x", pady=(12, 10))

    ttk.Label(frm, text="USB stick:").pack(anchor="w")
    pick_row = ttk.Frame(frm)
    pick_row.pack(fill="x", pady=(3, 8))
    b_refresh = ttk.Button(pick_row, text="Refresh", padding=(10, 5))
    b_refresh.pack(side="right", padx=(8, 0))
    drive = ttk.Combobox(pick_row, state="readonly", values=[])
    drive.pack(side="left", fill="x", expand=True)

    secure = tk.BooleanVar(value=True)
    gpt = tk.BooleanVar(value=True)
    upv = tk.BooleanVar(value=False)
    testv = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text="Secure Boot support", variable=secure).pack(anchor="w")
    ttk.Checkbutton(frm, text="GPT partition table (untick for very old BIOS PCs)", variable=gpt).pack(anchor="w")
    ttk.Checkbutton(frm, text="Install tests the stick first (slow: fills it and reads it back)",
                    variable=testv).pack(anchor="w")
    ttk.Checkbutton(frm, text="Update also refreshes Ventoy", variable=upv).pack(anchor="w")

    # Where the tools come from: the internet, or a pack (picked up beside the app if there is one)
    found = find_pack()
    pack_path = tk.StringVar(value=str(found or ""))
    use_pack = tk.BooleanVar(value=found is not None)
    ttk.Radiobutton(frm, text="Tools from the internet (latest)", variable=use_pack, value=False).pack(anchor="w", pady=(8, 0))
    src = ttk.Frame(frm)
    src.pack(fill="x")
    ttk.Radiobutton(src, text="Tools from a pack (offline):", variable=use_pack, value=True).pack(side="left")
    b_pack = ttk.Button(src, text="Choose…", padding=(10, 3))
    b_pack.pack(side="right")
    pack_label = ttk.Label(src, style="Muted.TLabel")
    pack_label.pack(side="left", padx=(6, 0))

    main = ttk.Frame(frm)
    main.pack(fill="x", pady=(14, 10))
    main.columnconfigure((0, 1), weight=1, uniform="main")
    b_install = ttk.Button(main, text="Install Helix Boot", style="Accent.TButton")
    b_install.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    b_update = ttk.Button(main, text="Update stick", style="Big.TButton")
    b_update.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    prog = ttk.Frame(frm)
    prog.pack(fill="x")
    b_log = ttk.Button(prog, text="Show log", padding=(10, 5))
    b_log.pack(side="right", padx=(8, 0))
    bar = ttk.Progressbar(prog, mode="determinate", maximum=100, style="Text.Horizontal.TProgressbar")
    bar.pack(side="left", fill="x", expand=True)
    status = ttk.Label(frm, text="Ready.", style="Muted.TLabel", wraplength=560, justify="left")
    status.pack(anchor="w", pady=(8, 0))
    news = ttk.Label(frm, text="Looking for newer versions of the tools…", style="News.TLabel",
                     wraplength=560, justify="left")
    news.pack(anchor="w", pady=(2, 0))

    foot = ttk.Frame(frm)
    foot.pack(fill="x", side="bottom")
    foot.columnconfigure((0, 1, 2, 3), weight=1, uniform="foot")
    b_look = ttk.Button(foot, text="Look…")
    b_check = ttk.Button(foot, text="Check stick")
    b_repair = ttk.Button(foot, text="Repair stick")
    b_folder = ttk.Button(foot, text="My tools folder")
    for i, b in enumerate((b_look, b_check, b_repair, b_folder)):
        b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 3 else 4))
    # The log: out of the way until asked for
    out = tk.Text(frm, height=10, wrap="word", font=("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 9),
                  relief="flat", background="#0d0b16", foreground="#cfc8e6", insertbackground="#cfc8e6",
                  highlightthickness=1, highlightbackground=EDGE)

    def bar_text(text: str) -> None:
        style.configure("Text.Horizontal.TProgressbar", text=text)

    def toggle_log():
        if out.winfo_ismapped():
            out.pack_forget()
            b_log.config(text="Show log")
            root.geometry(f"{root.winfo_width()}x{max(root.winfo_height() - 190, 564)}")
        else:
            out.pack(fill="both", expand=True, pady=(10, 10))
            b_log.config(text="Hide log")
            root.geometry(f"{root.winfo_width()}x{root.winfo_height() + 190}")

    def show_pack():
        pack_label.config(text=Path(pack_path.get()).name if pack_path.get() else "none chosen")

    def choose_pack():
        f = filedialog.askopenfilename(parent=root, title="Choose a Helix Boot pack",
                                       filetypes=[("Helix Boot pack", "*.zip"), ("All files", "*.*")])
        if not f:
            return
        if not is_pack(Path(f)):
            messagebox.showerror(APP, f"{Path(f).name} isn't a Helix Boot pack.")
            return
        pack_path.set(f)
        use_pack.set(True)
        show_pack()

    def chosen_pack():
        """The pack to use, None for the internet, or False when a pack is wanted but not chosen."""
        if not use_pack.get():
            return None
        if not pack_path.get():
            messagebox.showinfo(APP, "Choose a pack first (or pick “the internet”).")
            return False
        return pack_path.get()

    show_pack()
    disks: list[dict] = []
    busy = {"on": False}

    def refresh():
        chosen = disks[drive.current()]["Number"] if 0 <= drive.current() < len(disks) else None
        try:
            found = usb_disks()
        except Exception as e:  # noqa: BLE001 — shown to the user
            status.config(text=f"Couldn't list disks: {e}")
            return
        disks[:] = found
        names = []
        for d in found:
            where = f"{d['Ventoy']}:" if d.get("Ventoy") else ", ".join(f"{x}:" for x in d["Letters"])
            names.append(f"Disk {d['Number']}:  {d['Name']}  ({human(d['Size'])})"
                         + (f"  {where}" if where else "") + ("  ·  Ventoy stick" if d["IsVentoy"] else ""))
        drive.config(values=names)
        if found:           # keep the stick that was picked, else the one that already has Ventoy, else the first
            numbers = [d["Number"] for d in found]
            drive.current(numbers.index(chosen) if chosen in numbers
                          else next((i for i, d in enumerate(found) if d["IsVentoy"]), 0))
        else:
            drive.set("")
        status.config(text=f"{len(found)} USB disk(s) found." if found else "No USB sticks found. Plug one in and Refresh.")

    def selected():
        if not 0 <= drive.current() < len(disks):
            messagebox.showinfo(APP, "Pick a USB stick in the list first.")
            return None
        return disks[drive.current()]

    def set_busy(on):
        busy["on"] = on
        for b in (b_refresh, b_install, b_update, b_pack, b_look, b_check, b_repair):
            b.state(["disabled"] if on else ["!disabled"])
        drive.state(["disabled"] if on else ["!disabled", "readonly"])

    copying = {"done": 0, "total": 0, "sent": 0.0, "pending": 0}

    def watch(nbytes, label):
        """From the engine, for every chunk copied (not the reading back afterwards): passed on to
        the window a few times a second."""
        if "verifying" in label:
            return
        copying["pending"] += nbytes
        now = time.monotonic()
        if now - copying["sent"] > 0.25:
            q.put(("bytes", copying["pending"]))
            copying.update(pending=0, sent=now)

    def work(fn, *a, done=lambda letter: f"✓ Done. The stick is {letter} — safe to remove once Windows says so.",
             **kw):
        set_busy(True)
        bar.config(mode="indeterminate")
        bar_text("Working…")
        bar.start(12)
        copying.update(done=0, total=0, pending=0)

        def progress(pct):
            q.put(("pct", pct))

        def job():
            cr.Progress.watch = watch
            try:
                q.put(("done", done(fn(*a, progress=progress, **kw))))
            except Exception as e:  # noqa: BLE001
                q.put(("fail", str(e)))
            finally:
                cr.Progress.watch = None

        threading.Thread(target=job, daemon=True).start()

    def keep_going():
        answer = queue.Queue()
        q.put(("ask", answer))
        return answer.get()

    def confirm_update(summary):
        if summary.startswith("Everything on the stick is already up to date"):
            return True                 # nothing to copy or remove: no need to ask
        answer = queue.Queue()
        q.put(("confirm", summary, answer))
        return answer.get()

    def do_install():
        d = selected()
        if not d:
            return
        pack = chosen_pack()
        if pack is False:
            return
        msg = (f"This ERASES everything on disk {d['Number']}:\n\n    {d['Name']}  ({human(d['Size'])})\n\n"
               "Type the disk number to confirm:")
        if d["Size"] >= BIG_DISK:
            msg = "⚠ This disk is bigger than most sticks. Is it an external drive with backups?\n\n" + msg
        typed = simpledialog.askstring(APP, msg, parent=root)
        if typed is None or typed.strip() != str(d["Number"]):
            status.config(text="Cancelled — nothing was changed.")
            return
        work(install, d["Number"], gpt=gpt.get(), secure_boot=secure.get(), keep_going=keep_going, pack=pack, expected=d,
             on_plan=lambda nbytes: q.put(("total", nbytes)), test=testv.get())

    def do_update():
        d = selected()
        pack = chosen_pack() if d else None
        if d and pack is not False:
            work(update, d["Number"], upgrade_ventoy=upv.get(), secure_boot=secure.get(), pack=pack,
                 confirm=confirm_update, expected=d, on_plan=lambda nbytes: q.put(("total", nbytes)))

    def do_look():
        d = selected()
        if not d:
            return
        if not d.get("Ventoy"):
            messagebox.showinfo(APP, "That disk has no Helix Boot stick on it yet, or Windows gave it no drive "
                                     "letter. Install first, then choose its look.")
            return
        try:
            look_window(Path(f"{d['Ventoy']}:\\"), parent=root)
        except cr.RescueError as e:
            messagebox.showerror(APP, str(e))
        except Exception as e:  # noqa: BLE001 — a button that does nothing is worse than a message
            messagebox.showerror(APP, f"Couldn't open the Look window: {e}")

    def look_for_updates(refresh=False):
        """In the background: which tools have newer versions than this PC has (at most one
        look upstream every 6 hours; the rest of the time, from the last look)."""
        def job():
            try:
                q.put(("news", updates_notice(config(), refresh)))
            except Exception as e:  # noqa: BLE001 — offline, or GitHub said no; only a notice
                q.put(("news", f"Couldn't look for newer versions of the tools ({e})."))
        threading.Thread(target=job, daemon=True).start()

    def do_check():
        d = selected()
        if not d:
            return
        if not d.get("Ventoy"):
            messagebox.showinfo(APP, "That disk has no Helix Boot stick on it yet, or Windows gave it no drive "
                                     "letter, so there's nothing to check.")
            return
        work(check, f"{d['Ventoy']}:\\", done=lambda text: text)

    def do_repair():
        d = selected()
        if not d:
            return
        if not d.get("Ventoy"):
            messagebox.showinfo(APP, "That disk has no Helix Boot stick on it yet, or Windows gave it no drive "
                                     "letter, so there's nothing to repair.")
            return
        if messagebox.askokcancel(APP, f"Have Windows repair the filesystem on {d['Ventoy']}:?\n\n"
                                       f"This runs chkdsk {d['Ventoy']}: /f. It is for a stick that an update or a "
                                       "check says is damaged; it erases nothing, though a file that was damaged "
                                       "may be lost. Close anything that has the stick open first."):
            work(lambda target, progress: repair(target), f"{d['Ventoy']}:\\", done=lambda text: text)

    def open_folder():
        path = user_dir() / "byo"
        path.mkdir(exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # noqa: S606
        else:
            messagebox.showinfo(APP, str(path))

    def pump():
        try:
            while True:
                item = q.get_nowait()
                if isinstance(item, str):
                    out.insert("end", item)
                    out.see("end")
                    last = item.strip().splitlines()[-1:] if item.strip() else []
                    if last:
                        status.config(text=last[0][:110])
                elif item[0] == "news":
                    news.config(text=item[1])
                elif item[0] == "total":
                    copying.update(total=item[1], done=0)
                elif item[0] == "bytes":
                    copying["done"] += item[1]
                    if copying["total"]:           # "12.3 GB / 37.0 GB", as much of the bar filled
                        bar.stop()
                        share = min(copying["done"] / copying["total"], 1.0)
                        bar.config(mode="determinate", value=share * 100)
                        bar_text(f"{copying['done'] / 1024**3:.1f} GB / {copying['total'] / 1024**3:.1f} GB")
                    else:
                        bar_text(f"{copying['done'] / 1024**3:.1f} GB copied")
                elif item[0] == "pct":
                    bar.stop()
                    bar.config(mode="determinate", value=item[1])
                    bar_text(f"{item[1]}%")
                elif item[0] == "confirm":
                    bar.stop()
                    item[2].put(messagebox.askokcancel(APP, f"This update will:\n\n{item[1]}\n\nGo ahead?"))
                    bar.config(mode="indeterminate")
                    bar_text("Working…")
                    bar.start(12)
                elif item[0] == "ask":
                    item[1].put(messagebox.askyesno(APP, "Some tools failed to download (see the log).\n"
                                                         "Continue with what was fetched?"))
                elif item[0] in ("done", "fail"):
                    bar.stop()
                    bar.config(mode="determinate", value=100 if item[0] == "done" else 0)
                    bar_text("Done" if item[0] == "done" else "")
                    out.insert("end", ("\n" if item[0] == "done" else "\n✗ ") + item[1] + "\n")
                    out.see("end")
                    status.config(text=item[1].splitlines()[0][:110])
                    set_busy(False)
                    refresh()
                    look_for_updates()      # what was just fetched counts now (no new look upstream)
                    (messagebox.showinfo if item[0] == "done" else messagebox.showerror)(APP, item[1])
        except queue.Empty:
            pass
        root.after(100, pump)

    b_refresh.config(command=refresh)
    b_log.config(command=toggle_log)
    b_folder.config(command=open_folder)
    b_look.config(command=do_look)
    b_check.config(command=do_check)
    b_repair.config(command=do_repair)
    b_install.config(command=do_install)
    b_update.config(command=do_update)
    b_pack.config(command=choose_pack)
    print(f"Your files (local.toml, byo/): {user_dir()}")
    print(f"Pack found beside the app: {found}\n" if found else "")
    root.after(50, refresh)
    root.after(100, pump)
    if selftest:
        root.after(2500, root.destroy)
    else:
        root.after(300, look_for_updates)
    root.mainloop()
    return 0


# ── The Look window ────────────────────────────────────────────────────────
def look_window(mnt: Path, parent=None, selftest: bool = False):
    """A stick's look: its theme, icons, background and splash, with a preview of the boot menu.
    Works on the stick alone, so it needs no downloads. Raises RescueError for a stick that
    an older Helix Boot filled."""
    import tkinter as tk
    from tkinter import filedialog, ttk

    cfg = config()
    report = cr.look_report(mnt)
    cr.look_changes(mnt)                       # an older stick is refused here, before a window opens
    win = tk.Toplevel(parent) if parent else tk.Tk()
    if parent:
        win.configure(background=BG)
    else:
        apply_theme(win)
        set_icon(win)
    win.title(f"{APP}: the look of {mnt}")
    if parent:      # modal: Install and Update can't be started while this can still write to the stick
        win.transient(parent)

        def hold():
            try:
                win.grab_set()
            except tk.TclError:     # not on screen yet
                win.after(50, hold)
        win.after(0, hold)
    # The preview sets the window's height: a smaller one where the screen is short (768 px laptops)
    preview_size = (672, 378) if win.winfo_screenheight() >= 900 else (480, 270)
    win.minsize(preview_size[0] + 40, preview_size[1] + 300)
    frm = ttk.Frame(win, padding=14)
    frm.pack(fill="both", expand=True)
    themes = {t["title"]: t for t in report["themes"]}
    packs = {p["title"]: p for p in report["icon_packs"]}
    splashes = {"Automatic (yours from byo, else the theme's)": "auto", "The theme's": "theme",
                "My picture": "custom", "None": "off"}
    look = report["look"]
    theme = tk.StringVar(value=next((k for k, t in themes.items() if t["id"] == look["theme"]), next(iter(themes))))
    icons = tk.StringVar(value=next((k for k, p in packs.items() if p["id"] == look["icons"]), next(iter(packs))))
    background = tk.StringVar(value=look["background"])
    splash = tk.StringVar(value=next(k for k, v in splashes.items() if v == look["splash"]))
    dim = tk.IntVar(value=40)
    chosen: dict[str, str] = {}                # pictures picked here, not on the stick yet
    sent: set[str] = set()                     # which of them the last Apply put there
    on_stick = dict(report["custom"])

    preview = ttk.Label(frm, anchor="center", text="Drawing the preview…")
    preview.grid(row=0, column=0, columnspan=4, pady=(0, 12))
    ttk.Label(frm, text="Theme").grid(row=1, column=0, sticky="w", pady=4)
    c_theme = ttk.Combobox(frm, textvariable=theme, values=list(themes), state="readonly", width=26)
    c_theme.grid(row=1, column=1, sticky="w")
    about = ttk.Label(frm, style="Muted.TLabel")
    about.grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0))
    ttk.Label(frm, text="Icons").grid(row=2, column=0, sticky="w", pady=4)
    c_icons = ttk.Combobox(frm, textvariable=icons, values=list(packs), state="readonly", width=26)
    c_icons.grid(row=2, column=1, sticky="w")
    about_icons = ttk.Label(frm, style="Muted.TLabel")
    about_icons.grid(row=2, column=2, columnspan=2, sticky="w", padx=(10, 0))

    ttk.Label(frm, text="Background").grid(row=3, column=0, sticky="w", pady=4)
    bg = ttk.Frame(frm)
    bg.grid(row=3, column=1, columnspan=3, sticky="w")
    ttk.Radiobutton(bg, text="The theme's", variable=background, value="theme").pack(side="left")
    ttk.Radiobutton(bg, text="My picture", variable=background, value="custom").pack(side="left", padx=(12, 4))
    b_bg = ttk.Button(bg, text="Choose…")
    b_bg.pack(side="left")
    bg_name = ttk.Label(bg, style="Muted.TLabel")
    bg_name.pack(side="left", padx=(8, 0))
    dimmer = ttk.Frame(frm)
    dimmer.grid(row=4, column=1, columnspan=3, sticky="w")
    ttk.Label(dimmer, text="Darken it").pack(side="left")
    scale = ttk.Scale(dimmer, from_=0, to=90, variable=dim, length=220)
    scale.pack(side="left", padx=8)
    dim_text = ttk.Label(dimmer, width=30)
    dim_text.pack(side="left")

    ttk.Label(frm, text="Splash").grid(row=5, column=0, sticky="w", pady=4)
    sp = ttk.Frame(frm)
    sp.grid(row=5, column=1, columnspan=3, sticky="w")
    c_splash = ttk.Combobox(sp, textvariable=splash, values=list(splashes), state="readonly", width=42)
    c_splash.pack(side="left")
    b_sp = ttk.Button(sp, text="Choose…")
    b_sp.pack(side="left", padx=(8, 0))
    sp_name = ttk.Label(sp, style="Muted.TLabel")
    sp_name.pack(side="left", padx=(8, 0))

    status = ttk.Label(frm, text="The preview is a sketch from the theme's files; nothing changes until Apply.",
                       style="Muted.TLabel")
    status.grid(row=6, column=0, columnspan=4, sticky="w", pady=(12, 6))
    btns = ttk.Frame(frm)
    btns.grid(row=7, column=0, columnspan=4, sticky="ew")
    b_reset = ttk.Button(btns, text="Default look")
    b_reset.pack(side="left")
    b_save = ttk.Button(btns, text="Save look…")
    b_save.pack(side="left", padx=(6, 0))
    b_load = ttk.Button(btns, text="Load look…")
    b_load.pack(side="left", padx=(6, 0))
    b_close = ttk.Button(btns, text="Close", command=win.destroy)
    b_close.pack(side="right")
    b_apply = ttk.Button(btns, text="Apply to the stick", style="Go.TButton")
    b_apply.pack(side="right", padx=(0, 6))
    frm.columnconfigure(0, pad=14)
    frm.columnconfigure(3, weight=1)

    q: queue.Queue = queue.Queue()             # results from the worker threads
    wanted: queue.Queue = queue.Queue()        # previews asked for; only the newest is drawn
    shown = {"image": None, "timer": None}

    def options() -> dict:
        """What the window asks for, as look_changes takes it."""
        want_bg = chosen.get("background") or "custom" if background.get() == "custom" else "theme"
        want_sp = splashes[splash.get()]
        if want_sp == "custom" and chosen.get("splash"):
            want_sp = chosen["splash"]
        return dict(theme=themes[theme.get()]["id"], icons=packs[icons.get()]["id"], background=want_bg,
                    splash=want_sp, dim=round(dim.get()) if chosen.get("background") and want_bg != "theme" else 0)

    def changes():
        opts = options()
        for what in ("background", "splash"):  # "my picture" with none yet: ask for one
            if opts[what] == "custom" and not on_stick[what]:
                return None
        return cr.look_changes(mnt, **opts), opts["dim"]

    def draw_previews():                       # worker: one at a time, skipping to the newest
        while True:
            job = wanted.get()
            while not wanted.empty():
                job = wanted.get()
            if job is None:
                return
            (new_look, pictures), darken = job
            try:
                png = cr.look_preview(cfg, mnt, new_look, cfg.cache / "look-window.png", pictures, darken, preview_size)
                q.put(("preview", str(png)))
            except Exception as e:  # noqa: BLE001 — shown in the window
                q.put(("nopreview", str(e)))

    def refresh(*_):
        stock = themes[theme.get()]["id"] == "off"
        about.config(text=themes[theme.get()]["description"])
        about_icons.config(text="Ventoy's own look has none" if stock else packs[icons.get()]["description"])
        c_icons.state(["disabled"] if stock else ["!disabled"])
        for w in bg.winfo_children():
            w.state(["disabled"] if stock else ["!disabled"])
        bg_name.config(text=Path(chosen["background"]).name if chosen.get("background")
                       else "the one on the stick" if on_stick["background"] else "")
        sp_name.config(text=Path(chosen["splash"]).name if chosen.get("splash")
                       else "the one on the stick" if on_stick["splash"] and splashes[splash.get()] == "custom" else "")
        fresh = bool(chosen.get("background")) and background.get() == "custom" and not stock
        scale.state(["!disabled"] if fresh else ["disabled"])
        dim_text.config(text=f"{round(dim.get())} %" if fresh else "(for a newly chosen picture)")
        if shown["timer"]:
            win.after_cancel(shown["timer"])
        shown["timer"] = win.after(250, ask_preview)

    def ask_preview():
        shown["timer"] = None
        try:
            job = changes()
        except cr.RescueError as e:
            status.config(text=str(e))
            return
        if job:
            wanted.put(job)

    def choose(what: str):
        f = filedialog.askopenfilename(parent=win, title=f"Choose a picture for the {what}",
                                       filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if not f:
            return
        chosen[what] = f
        if what == "background":
            background.set("custom")
        else:
            splash.set("My picture")
        refresh()

    def need_picture(*_):                      # "my picture" picked with none to use: ask for one
        if background.get() == "custom" and not on_stick["background"] and not chosen.get("background"):
            choose("background")
            if not chosen.get("background"):
                background.set("theme")
        if splashes[splash.get()] == "custom" and not on_stick["splash"] and not chosen.get("splash"):
            choose("splash")
            if not chosen.get("splash"):
                splash.set(next(k for k, v in splashes.items() if v == "auto"))
        refresh()

    def reset():
        theme.set(next(k for k, t in themes.items() if t["id"] == "default"))
        icons.set(next(k for k, p in packs.items() if p["id"] == "auto"))
        background.set("theme")
        splash.set(next(k for k, v in splashes.items() if v == "auto"))
        chosen.clear()
        refresh()

    def apply():
        try:
            job = changes()
        except cr.RescueError as e:
            status.config(text=str(e))
            return
        if not job:
            return
        for b in (b_apply, b_reset):
            b.state(["disabled"])
        status.config(text="Changing the stick's look…")

        def work():
            try:
                (new_look, pictures), darken = job
                changed = cr.set_look(cfg, mnt, new_look, pictures, darken)
                sent.update(pictures)
                q.put(("applied", "The stick's look is changed." if changed else "The stick already looks like this."))
            except Exception as e:  # noqa: BLE001
                q.put(("failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def save():
        f = filedialog.asksaveasfilename(parent=win, title="Save this stick's look", initialfile="helix-look.zip",
                                         defaultextension=".zip", filetypes=[("Saved look", "*.zip")])
        if not f:
            return
        try:
            status.config(text=f"Saved to {cr.export_look(mnt, Path(f))}. (What's on the stick, not what's unapplied.)")
        except (cr.RescueError, OSError) as e:
            status.config(text=f"✗ {e}")

    def load():
        f = filedialog.askopenfilename(parent=win, title="Load a saved look onto the stick",
                                       filetypes=[("Saved look", "*.zip"), ("All files", "*.*")])
        if not f:
            return
        for b in (b_apply, b_reset, b_load):
            b.state(["disabled"])
        status.config(text="Loading the look onto the stick…")

        def work():
            try:
                notes = cr.import_look(cfg, mnt, Path(f))
                q.put(("loaded", " ".join(["The saved look is on the stick.", *[n[0].upper() + n[1:] + "." for n in notes]])))
            except Exception as e:  # noqa: BLE001
                q.put(("failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def show_loaded():
        """The controls, set to what's on the stick now."""
        got = cr.look_report(mnt)
        theme.set(next((k for k, t in themes.items() if t["id"] == got["look"]["theme"]), theme.get()))
        icons.set(next((k for k, p in packs.items() if p["id"] == got["look"]["icons"]), icons.get()))
        background.set(got["look"]["background"])
        splash.set(next(k for k, v in splashes.items() if v == got["look"]["splash"]))
        on_stick.update(got["custom"])
        chosen.clear()
        refresh()

    def pump():
        try:
            while True:
                kind, text = q.get_nowait()
                if kind == "loaded":
                    show_loaded()
                if kind == "preview":
                    shown["image"] = tk.PhotoImage(master=win, file=text)   # kept: Tk drops unreferenced images
                    preview.config(image=shown["image"], text="")
                elif kind == "nopreview":
                    preview.config(image="", text=f"No preview: {text}")
                else:
                    if kind == "applied":      # the pictures that were sent are on the stick now
                        for what in list(sent):
                            on_stick[what] = True
                            chosen.pop(what, None)
                        sent.clear()
                        refresh()
                    status.config(text=f"✗ {text}" if kind == "failed" else text)
                    for b in (b_apply, b_reset, b_load):
                        b.state(["!disabled"])
        except queue.Empty:
            pass
        win.after(100, pump)

    b_bg.config(command=lambda: choose("background"))
    b_sp.config(command=lambda: choose("splash"))
    b_reset.config(command=reset)
    b_save.config(command=save)
    b_load.config(command=load)
    b_apply.config(command=apply)
    scale.config(command=refresh)
    c_theme.bind("<<ComboboxSelected>>", refresh)
    c_icons.bind("<<ComboboxSelected>>", refresh)
    c_splash.bind("<<ComboboxSelected>>", need_picture)
    background.trace_add("write", need_picture)
    win.bind("<Destroy>", lambda e: wanted.put(None) if e.widget is win else None)
    threading.Thread(target=draw_previews, daemon=True).start()
    refresh()
    win.after(100, pump)
    if selftest:
        win.after(6000, win.destroy)
    if not parent:
        win.mainloop()
    return win


# ── Command line ───────────────────────────────────────────────────────────
def cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="HelixBoot", description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print USB disks as JSON")
    ap.add_argument("--all", action="store_true", help="with --list: every disk, marked")
    ap.add_argument("--fetch", nargs="*", metavar="TOOL", help="download + verify (all enabled tools if none named)")
    ap.add_argument("--install", type=int, metavar="DISK", help="erase DISK and build the stick (needs --yes)")
    ap.add_argument("--update", type=int, metavar="DISK", help="refresh the stick on DISK in place")
    ap.add_argument("--sync-to", metavar="DIR", help="copy the cached tools into a folder (with --init for a new one)")
    ap.add_argument("--pack", metavar="ZIP", help="with --install / --update / --unpack-to: use this pack, offline")
    ap.add_argument("--unpack-to", metavar="DIR", help="fill a folder from --pack (with --init for a new one)")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--look", metavar="DRIVE", help="open the Look window for a stick (e.g. E:\\); with the "
                                                   "options below, change its look instead")
    ap.add_argument("--theme", metavar="ID", help="with --look: a preset theme, or default (off: the plain one, Standby)")
    ap.add_argument("--icons", metavar="ID", help="with --look: auto, logos, grey, an icon pack, or off")
    ap.add_argument("--background", metavar="PICTURE", help="with --look: your own background, or theme")
    ap.add_argument("--dim", type=int, default=0, metavar="PERCENT", help="with --background: darken it (0-90)")
    ap.add_argument("--splash", metavar="PICTURE", help="with --look: your own splash; theme, auto, or off")
    ap.add_argument("--reset-look", action="store_true", help="with --look: back to the default look")
    ap.add_argument("--preview", metavar="FILE", help="with --look: only write a picture of how it would look")
    ap.add_argument("--export-look", metavar="ZIP", help="with --look: save the stick's look to a zip")
    ap.add_argument("--import-look", metavar="ZIP", help="with --look: put a saved look on the stick")
    ap.add_argument("--selftest-look", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--check", metavar="DRIVE", help="read a stick back and find damaged or missing files")
    ap.add_argument("--test-stick", metavar="DRIVE", help="write a stick's free space full, read it back and "
                                                          "delete it: finds a failing or fake stick")
    ap.add_argument("--test", action="store_true", help="with --install: test the stick first (slow)")
    ap.add_argument("--repair", metavar="DRIVE", help="have Windows repair a stick's filesystem (chkdsk /f)")
    ap.add_argument("--boot-script", metavar="VOLUME", help=argparse.SUPPRESS)   # with --sync-to: Ventoy's partition
    ap.add_argument("--updates", action="store_true", help="say which tools have newer versions than this PC has")
    ap.add_argument("--yes", action="store_true", help="confirm --install")
    ap.add_argument("--mbr", action="store_true", help="MBR instead of GPT")
    ap.add_argument("--no-secure-boot", action="store_true")
    ap.add_argument("--upgrade-ventoy", action="store_true", help="with --update: refresh Ventoy too")
    ap.add_argument("--selftest-gui", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--log", type=Path, help="log file (default: helix-boot.log next to the app)")
    a = ap.parse_args(argv)

    log = open_log(a.log)
    console = sys.__stdout__
    sys.stdout = sys.stderr = Tee(console, log)
    try:
        if a.selftest_gui:
            return gui(selftest=True)
        if a.look:
            asked = a.theme or a.icons or a.background or a.splash or a.reset_look or a.preview \
                or a.export_look or a.import_look
            if not asked:
                look_window(Path(a.look), selftest=a.selftest_look)
                return 0
            return cr.cmd_theme(config(), ns(stick=a.look, theme=a.theme, icons=a.icons, background=a.background,
                                             dim=a.dim, splash=a.splash, reset=a.reset_look, preview=a.preview,
                                             menu=False, json=False, export=a.export_look, import_=a.import_look))
        if a.check:
            check(a.check)
            return 0
        if a.test_stick:
            test_stick(a.test_stick)
            return 0
        if a.repair:
            print(repair(a.repair))
            return 0
        if a.updates:
            print(updates_notice(config(), refresh=True))
            return 0
        if a.list:
            disks = all_disks() if a.all else usb_disks()
            print(json.dumps(disks, indent=2))
        elif a.fetch is not None:
            return 0 if fetch(config(), a.fetch) else 1
        elif a.sync_to:
            sync(config(), a.sync_to, init=a.init)
            if a.boot_script and not boot_script(a.sync_to, efi=a.boot_script):
                return 1
        elif a.unpack_to:
            if not a.pack:
                raise RescueError("--unpack-to needs --pack PACK.zip")
            unpack(config(), a.unpack_to, a.pack, init=a.init)
        elif a.install is not None:
            if not a.yes:
                raise RescueError("--install erases the disk; add --yes to confirm")
            install(a.install, gpt=not a.mbr, secure_boot=not a.no_secure_boot, keep_going=lambda: True,
                    pack=a.pack, test=a.test)
        elif a.update is not None:
            update(a.update, upgrade_ventoy=a.upgrade_ventoy, secure_boot=not a.no_secure_boot, pack=a.pack)
        else:
            ap.print_help()
        return 0
    except cr.RescueError as e:
        print(f"✗ {e}")
        return 1


def main() -> int:
    try:
        if len(sys.argv) > 1:
            return cli(sys.argv[1:])
        return gui()
    except Exception:  # noqa: BLE001
        # The .exe has no console: an uncaught error would pop up PyInstaller's blocking
        # "Unhandled exception" box. Log it and exit instead.
        import traceback
        text = traceback.format_exc()
        log = open_log(None)
        if log:
            log.write(text)
        if sys.__stderr__:
            sys.__stderr__.write(text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
