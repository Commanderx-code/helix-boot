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
import hashlib  # noqa: F401
import html  # noqa: F401
import re  # noqa: F401
import struct  # noqa: F401
import tarfile  # noqa: F401
import tomllib  # noqa: F401
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
import xml.etree.ElementTree  # noqa: F401
import zipfile  # noqa: F401
import zlib  # noqa: F401

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
    Size    = [int64]$_.Size
    Bus     = "$($_.BusType)"
    System  = [bool]($_.IsSystem -or $_.IsBoot)
    Labels  = @($v | ForEach-Object { "$($_.FileSystemLabel)" })
    Letters = @($v | Where-Object DriveLetter | ForEach-Object { "$($_.DriveLetter)" })
    Ventoy  = "$(($data | Select-Object -First 1).DriveLetter)"
  }
} | ConvertTo-Json -Compress -Depth 3
"""


def powershell(script: str) -> str:
    # stdin=DEVNULL: PowerShell started from a windowless app otherwise waits on input forever
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
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


def wait_for_ventoy_letter(disk_no: int, run=powershell, timeout: float = 90) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        d = next((d for d in all_disks(run) if d["Number"] == disk_no), None)
        if d and d.get("Ventoy"):
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


def install(disk_no: int, gpt=True, secure_boot=True, progress=lambda pct: None, run=powershell,
            ventoy=run_ventoy, keep_going=lambda: True, pack=None) -> str:
    """Erase disk N, put Ventoy on it, fill it (from the internet, or from a pack).
    Returns the stick's drive letter."""
    cfg = config()
    d = pick(disk_no, run)
    if pack:   # everything comes out of the pack: check it has Ventoy for Windows before erasing
        vdir = pack_ventoy_dir(cfg, pack)
    else:
        if not fetch(cfg) and not keep_going():
            raise RescueError("stopped — nothing was written to any disk")
        vdir = ventoy_dir(cfg)
    print(f"\nInstalling Ventoy on disk {disk_no} ({d['Name']}, {human(d['Size'])}) …")
    ventoy(ventoy_command(vdir, "/I", disk_no, gpt, secure_boot), vdir, progress)
    letter = wait_for_ventoy_letter(disk_no, run)
    print(f"✓ Ventoy installed, stick is {letter}")
    if pack:
        unpack(cfg, letter, pack, init=True)
    else:
        sync(cfg, letter, init=True)
    return letter


def update(disk_no: int, upgrade_ventoy=False, secure_boot=True, progress=lambda pct: None,
           run=powershell, ventoy=run_ventoy, pack=None) -> str:
    """Refresh a Helix Boot / Ventoy stick in place. Never erases."""
    cfg = config()
    d = pick(disk_no, run)
    if not d.get("IsVentoy") or not d.get("Ventoy"):
        raise RescueError(f"disk {disk_no} doesn't have Ventoy on it (or no drive letter) — use Install")
    if not pack:
        fetch(cfg)
    if upgrade_ventoy:
        vdir = pack_ventoy_dir(cfg, pack) if pack else ventoy_dir(cfg)
        print(f"\nUpdating Ventoy on disk {disk_no} (your files are kept) …")
        ventoy(ventoy_command(vdir, "/U", disk_no, secure_boot=secure_boot), vdir, progress)
    letter = wait_for_ventoy_letter(disk_no, run)
    if pack:
        unpack(cfg, letter, pack, init=False)
    else:
        sync(cfg, letter, init=False)
    return letter


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
def gui(selftest: bool = False) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    q: queue.Queue = queue.Queue()
    log = open_log(None)
    sys.stdout = sys.stderr = Tee(q, log)

    root = tk.Tk()
    root.title(APP)
    root.geometry("860x620")
    root.minsize(720, 520)
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
    style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text="Helix Boot", style="Title.TLabel").pack(anchor="w")
    ttk.Label(frm, text="Pick a USB stick, then Install (erases it) or Update (keeps your files).",
              foreground="#555").pack(anchor="w", pady=(0, 10))

    # Where the tools come from: the internet, or a pack (picked up beside the app if there is one)
    src = ttk.Frame(frm)
    src.pack(fill="x", pady=(0, 8))
    found = find_pack()
    pack_path = tk.StringVar(value=str(found or ""))
    use_pack = tk.BooleanVar(value=found is not None)
    ttk.Label(src, text="Tools from:").pack(side="left")
    ttk.Radiobutton(src, text="the internet (latest)", variable=use_pack, value=False).pack(side="left", padx=(8, 0))
    ttk.Radiobutton(src, text="a pack (offline):", variable=use_pack, value=True).pack(side="left", padx=(12, 4))
    pack_label = ttk.Label(src, foreground="#555")
    pack_label.pack(side="left")
    b_pack = ttk.Button(src, text="Choose pack…")
    b_pack.pack(side="left", padx=(8, 0))

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

    cols = ("disk", "name", "size", "ventoy", "letter")
    tree = ttk.Treeview(frm, columns=cols, show="headings", height=5, selectmode="browse")
    for c, text, w in zip(cols, ("Disk", "Name", "Size", "Ventoy", "Drive"), (60, 360, 90, 80, 70)):
        tree.heading(c, text=text)
        tree.column(c, width=w, anchor="w" if c == "name" else "center", stretch=c == "name")
    tree.pack(fill="x")

    opts = ttk.Frame(frm)
    opts.pack(fill="x", pady=8)
    secure = tk.BooleanVar(value=True)
    gpt = tk.BooleanVar(value=True)
    upv = tk.BooleanVar(value=False)
    ttk.Checkbutton(opts, text="Secure Boot support", variable=secure).pack(side="left")
    ttk.Checkbutton(opts, text="GPT (untick for very old BIOS PCs)", variable=gpt).pack(side="left", padx=14)
    ttk.Checkbutton(opts, text="Update also refreshes Ventoy", variable=upv).pack(side="left")

    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    b_refresh = ttk.Button(btns, text="Refresh list")
    b_folder = ttk.Button(btns, text="My tools folder (byo)")
    b_look = ttk.Button(btns, text="Look…")
    b_install = ttk.Button(btns, text="Install  (erases the stick)", style="Accent.TButton")
    b_update = ttk.Button(btns, text="Update stick")
    for b in (b_refresh, b_folder, b_look):
        b.pack(side="left", padx=(0, 6))
    show_pack()
    for b in (b_update, b_install):
        b.pack(side="right", padx=(6, 0))

    bar = ttk.Progressbar(frm, mode="determinate", maximum=100)
    bar.pack(fill="x", pady=(12, 4))
    status = ttk.Label(frm, text="Ready.")
    status.pack(anchor="w")
    out = tk.Text(frm, height=16, wrap="word", font=("Consolas", 9), relief="flat",
                  background="#0f1722", foreground="#d8e1ea", insertbackground="#d8e1ea")
    out.pack(fill="both", expand=True, pady=(6, 0))

    disks: dict[str, dict] = {}
    busy = {"on": False}

    def refresh():
        tree.delete(*tree.get_children())
        disks.clear()
        try:
            found = usb_disks()
        except Exception as e:  # noqa: BLE001 — shown to the user
            status.config(text=f"Couldn't list disks: {e}")
            return
        for d in found:
            iid = tree.insert("", "end", values=(d["Number"], d["Name"], human(d["Size"]),
                                                 "yes" if d["IsVentoy"] else "—",
                                                 f"{d['Ventoy']}:" if d.get("Ventoy") else ", ".join(f"{x}:" for x in d["Letters"])))
            disks[iid] = d
        status.config(text=f"{len(found)} USB disk(s) found." if found else "No USB sticks found. Plug one in and Refresh.")

    def selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo(APP, "Pick a USB stick in the list first.")
            return None
        return disks[sel[0]]

    def set_busy(on):
        busy["on"] = on
        for b in (b_refresh, b_install, b_update, b_pack, b_look):
            b.state(["disabled"] if on else ["!disabled"])

    def work(fn, *a, **kw):
        set_busy(True)
        bar.config(mode="indeterminate")
        bar.start(12)

        def progress(pct):
            q.put(("pct", pct))

        def job():
            try:
                letter = fn(*a, progress=progress, **kw)
                q.put(("done", f"✓ Done. The stick is {letter} — safe to remove once Windows says so."))
            except Exception as e:  # noqa: BLE001
                q.put(("fail", str(e)))

        threading.Thread(target=job, daemon=True).start()

    def keep_going():
        answer = queue.Queue()
        q.put(("ask", answer))
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
        work(install, d["Number"], gpt=gpt.get(), secure_boot=secure.get(), keep_going=keep_going, pack=pack)

    def do_update():
        d = selected()
        pack = chosen_pack() if d else None
        if d and pack is not False:
            work(update, d["Number"], upgrade_ventoy=upv.get(), secure_boot=secure.get(), pack=pack)

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
                elif item[0] == "pct":
                    bar.stop()
                    bar.config(mode="determinate", value=item[1])
                elif item[0] == "ask":
                    item[1].put(messagebox.askyesno(APP, "Some tools failed to download (see the log).\n"
                                                         "Continue with what was fetched?"))
                elif item[0] in ("done", "fail"):
                    bar.stop()
                    bar.config(mode="determinate", value=100 if item[0] == "done" else 0)
                    out.insert("end", ("\n" if item[0] == "done" else "\n✗ ") + item[1] + "\n")
                    out.see("end")
                    status.config(text=item[1].splitlines()[0][:110])
                    set_busy(False)
                    refresh()
                    (messagebox.showinfo if item[0] == "done" else messagebox.showerror)(APP, item[1])
        except queue.Empty:
            pass
        root.after(100, pump)

    b_refresh.config(command=refresh)
    b_folder.config(command=open_folder)
    b_look.config(command=do_look)
    b_install.config(command=do_install)
    b_update.config(command=do_update)
    b_pack.config(command=choose_pack)
    print(f"Your files (local.toml, byo/): {user_dir()}")
    print(f"Pack found beside the app: {found}\n" if found else "")
    root.after(50, refresh)
    root.after(100, pump)
    if selftest:
        root.after(2500, root.destroy)
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
    win.title(f"{APP}: the look of {mnt}")
    # The preview sets the window's height: a smaller one where the screen is short (768 px laptops)
    preview_size = (672, 378) if win.winfo_screenheight() >= 900 else (480, 270)
    win.minsize(preview_size[0] + 40, preview_size[1] + 270)
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
    on_stick = dict(report["custom"])

    preview = ttk.Label(frm, anchor="center", text="Drawing the preview…")
    preview.grid(row=0, column=0, columnspan=4, pady=(0, 12))
    ttk.Label(frm, text="Theme").grid(row=1, column=0, sticky="w", pady=4)
    c_theme = ttk.Combobox(frm, textvariable=theme, values=list(themes), state="readonly", width=26)
    c_theme.grid(row=1, column=1, sticky="w")
    about = ttk.Label(frm, foreground="#555")
    about.grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0))
    ttk.Label(frm, text="Icons").grid(row=2, column=0, sticky="w", pady=4)
    c_icons = ttk.Combobox(frm, textvariable=icons, values=list(packs), state="readonly", width=26)
    c_icons.grid(row=2, column=1, sticky="w")
    about_icons = ttk.Label(frm, foreground="#555")
    about_icons.grid(row=2, column=2, columnspan=2, sticky="w", padx=(10, 0))

    ttk.Label(frm, text="Background").grid(row=3, column=0, sticky="w", pady=4)
    bg = ttk.Frame(frm)
    bg.grid(row=3, column=1, columnspan=3, sticky="w")
    ttk.Radiobutton(bg, text="The theme's", variable=background, value="theme").pack(side="left")
    ttk.Radiobutton(bg, text="My picture", variable=background, value="custom").pack(side="left", padx=(12, 4))
    b_bg = ttk.Button(bg, text="Choose…")
    b_bg.pack(side="left")
    bg_name = ttk.Label(bg, foreground="#555")
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
    sp_name = ttk.Label(sp, foreground="#555")
    sp_name.pack(side="left", padx=(8, 0))

    status = ttk.Label(frm, text="The preview is a sketch from the theme's files; nothing changes until Apply.",
                       foreground="#555")
    status.grid(row=6, column=0, columnspan=4, sticky="w", pady=(12, 6))
    btns = ttk.Frame(frm)
    btns.grid(row=7, column=0, columnspan=4, sticky="ew")
    b_reset = ttk.Button(btns, text="Default look")
    b_reset.pack(side="left")
    b_close = ttk.Button(btns, text="Close", command=win.destroy)
    b_close.pack(side="right")
    b_apply = ttk.Button(btns, text="Apply to the stick")
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
                q.put(("applied", "The stick's look is changed." if changed else "The stick already looks like this."))
            except Exception as e:  # noqa: BLE001
                q.put(("failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def pump():
        try:
            while True:
                kind, text = q.get_nowait()
                if kind == "preview":
                    shown["image"] = tk.PhotoImage(master=win, file=text)   # kept: Tk drops unreferenced images
                    preview.config(image=shown["image"], text="")
                elif kind == "nopreview":
                    preview.config(image="", text=f"No preview: {text}")
                else:
                    if kind == "applied":      # the pictures chosen here are on the stick now
                        for what in chosen:
                            on_stick[what] = True
                        chosen.clear()
                        refresh()
                    status.config(text=text if kind == "applied" else f"✗ {text}")
                    for b in (b_apply, b_reset):
                        b.state(["!disabled"])
        except queue.Empty:
            pass
        win.after(100, pump)

    b_bg.config(command=lambda: choose("background"))
    b_sp.config(command=lambda: choose("splash"))
    b_reset.config(command=reset)
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
    ap.add_argument("--selftest-look", action="store_true", help=argparse.SUPPRESS)
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
            asked = a.theme or a.icons or a.background or a.splash or a.reset_look or a.preview
            if not asked:
                look_window(Path(a.look), selftest=a.selftest_look)
                return 0
            return cr.cmd_theme(config(), ns(stick=a.look, theme=a.theme, icons=a.icons, background=a.background,
                                             dim=a.dim, splash=a.splash, reset=a.reset_look, preview=a.preview,
                                             menu=False, json=False))
        if a.list:
            disks = all_disks() if a.all else usb_disks()
            print(json.dumps(disks, indent=2))
        elif a.fetch is not None:
            return 0 if fetch(config(), a.fetch) else 1
        elif a.sync_to:
            sync(config(), a.sync_to, init=a.init)
        elif a.unpack_to:
            if not a.pack:
                raise RescueError("--unpack-to needs --pack PACK.zip")
            unpack(config(), a.unpack_to, a.pack, init=a.init)
        elif a.install is not None:
            if not a.yes:
                raise RescueError("--install erases the disk; add --yes to confirm")
            install(a.install, gpt=not a.mbr, secure_boot=not a.no_secure_boot, keep_going=lambda: True,
                    pack=a.pack)
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
