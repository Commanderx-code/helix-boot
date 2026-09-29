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
DISKS_PS = r"""
Get-Disk | ForEach-Object {
  $v = @(Get-Partition -DiskNumber $_.Number -ErrorAction SilentlyContinue |
         Get-Volume -ErrorAction SilentlyContinue)
  [pscustomobject]@{
    Number  = [int]$_.Number
    Name    = "$($_.FriendlyName)"
    Size    = [int64]$_.Size
    Bus     = "$($_.BusType)"
    System  = [bool]($_.IsSystem -or $_.IsBoot)
    Labels  = @($v | ForEach-Object { "$($_.FileSystemLabel)" })
    Letters = @($v | Where-Object DriveLetter | ForEach-Object { "$($_.DriveLetter)" })
    Ventoy  = "$(($v | Where-Object FileSystemLabel -eq 'Ventoy' | Select-Object -First 1).DriveLetter)"
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
        d["IsVentoy"] = "Ventoy" in d["Labels"] and "VTOYEFI" in d["Labels"]
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
    """The newest pack beside the app, or beside the installer\ folder it was unzipped into."""
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
    b_install = ttk.Button(btns, text="Install  (erases the stick)", style="Accent.TButton")
    b_update = ttk.Button(btns, text="Update stick")
    for b in (b_refresh, b_folder):
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
        for b in (b_refresh, b_install, b_update, b_pack):
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
