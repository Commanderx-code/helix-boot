#!/usr/bin/env python3
"""Helix Boot for Linux, in a window: build or refresh the rescue stick without a terminal.

The same window as the Windows app (windows/helix_boot.py) and the same engine (helix), with
the parts that are Windows' own replaced here: disks come from lsblk, a stick is a mount point
and not a drive letter, and Ventoy is installed by its own Linux script.

    linux/helix_gui.py              the window
    linux/helix_gui.py --list       USB sticks as JSON (--all: every disk, marked)
    linux/helix_gui.py --self-update   get the latest release of this program, verified

Nothing here runs as root but two things, each behind the desktop's own password dialog
(pkexec): Ventoy's installer, which writes the disk, and fsck for Repair stick. Run it as
your normal user. Your local.toml and byo/ folder are the ones beside the `helix` script,
or beside the one-file program (HelixBoot-linux-x86_64).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("NO_COLOR", "1")          # what the engine prints goes to a window and a log, not a terminal
if not getattr(sys, "frozen", False):           # (the one-file build has it inside)
    sys.path.insert(0, str(HERE.parent / "windows"))

import helix_boot as app  # noqa: E402

cr = app.cr
RescueError = app.RescueError
DISK_NAME = re.compile(r"(sd[a-z]+|mmcblk\d+|nvme\d+n\d+|vd[a-z]+)")   # a whole disk's kernel name
ROOT_TIMEOUT = 1200


def run(cmd: list[str], timeout: float = 60, **kw) -> str:
    """Run a command and return what it printed; RescueError with what it said if it failed."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, **kw)
    except FileNotFoundError:
        raise RescueError(f"'{cmd[0]}' isn't installed, and this needs it") from None
    except subprocess.TimeoutExpired:
        raise RescueError(f"{cmd[0]} didn't answer within {int(timeout)} seconds") from None
    if r.returncode:
        raise RescueError(f"{' '.join(cmd[:3])} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


# ── Disks (lsblk) ──────────────────────────────────────────────────────────
def system_disks() -> set[str]:
    """Whole disks holding the running system, through LUKS, LVM and btrfs: scripts/common.sh
    works that out for install.sh, and the same code answers here. No answer, no list."""
    script = app.bundle_dir() / "scripts" / "common.sh"
    try:
        r = subprocess.run(["bash", "-c", 'source "$1" && system_disks', "helix-boot", str(script)],
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        r = None
    if r is None or r.returncode:
        raise RescueError("can't tell which disks hold the running system, so no disk is offered")
    return set(r.stdout.split())


def _diskseq(name: str) -> str:
    """The number the kernel gives a disk each time one appears: a stick unplugged and another
    plugged in is /dev/sdb again, with another number."""
    try:
        seq = Path(f"/sys/class/block/{name}/diskseq").read_text().strip()
    except OSError:
        return ""
    return seq if seq.isdigit() else ""


def all_disks(run_=None, lsblk=None, protected=None) -> list[dict]:
    """Every disk, in the shape the window knows from Windows: Number is the kernel's name for
    it (sdb), Ventoy the data partition of a Ventoy stick, Letters where its partitions are mounted."""
    out = lsblk if lsblk is not None else json.loads(run(
        ["lsblk", "-J", "-b", "-p", "-o", "NAME,PATH,SIZE,TYPE,TRAN,RM,MODEL,VENDOR,SERIAL,LABEL,MOUNTPOINTS"]))
    protected = system_disks() if protected is None else protected
    disks = []
    for d in out.get("blockdevices", []):
        if d.get("type") != "disk":
            continue
        path, name = d["path"], d["path"].rsplit("/", 1)[-1]
        parts = [p for p in d.get("children") or [] if p.get("type") == "part"]
        labels = [p["label"] for p in parts if p.get("label")]
        efi = next((p["path"] for p in parts if p.get("label") == "VTOYEFI"), None)
        data = max((p for p in parts if p.get("label") != "VTOYEFI"), key=lambda p: int(p.get("size") or 0),
                   default=None)
        bus = "USB" if d.get("tran") == "usb" else "SD" if d.get("rm") in (True, "1", 1) else str(d.get("tran") or "").upper()
        disks.append({
            "Number": name, "Path": path, "Size": int(d.get("size") or 0), "Bus": bus,
            "Name": " ".join(x for x in (str(d.get("vendor") or "").strip(), str(d.get("model") or "").strip()) if x) or "unknown",
            "System": path in protected, "Labels": labels, "IsVentoy": efi is not None,
            "Ventoy": data["path"] if efi and data else None, "Efi": efi,
            "Letters": [m for p in parts for m in (p.get("mountpoints") or []) if m],
            "Serial": str(d.get("serial") or "").strip(), "Id": _diskseq(name),
        })
    return sorted(disks, key=lambda d: d["Number"])


def disk_identity(d: dict) -> tuple:
    """What tells this disk from another that takes its place under the same name: the number the
    kernel gave it when it appeared. Without it nothing is written."""
    if not d.get("Id"):
        raise RescueError(f"the kernel gives no sequence number for {d.get('Path')}; refusing to write")
    return d["Path"], d["Id"], d["Size"], d["Bus"]


def mounted_at(part: str) -> str:
    try:
        return run(["findmnt", "-no", "TARGET", part]).splitlines()[0].strip()
    except (RescueError, IndexError):
        return ""


def mount(part: str) -> str:
    """Mount a partition as you (udisks, as the file manager does) and return where."""
    at = mounted_at(part)
    if not at:
        run(["udisksctl", "mount", "-b", part], timeout=120)
        at = mounted_at(part)
    if not at:
        raise RescueError(f"couldn't mount {part}")
    return at


def unmount(part: str) -> None:
    if mounted_at(part):
        run(["udisksctl", "unmount", "-b", part], timeout=120)


def partitions(dev: str) -> list[str]:
    return [line.split()[0] for line in run(["lsblk", "-lnpo", "NAME,TYPE", dev]).splitlines()
            if line.split()[1:] == ["part"]]


def stick_path(d: dict) -> str:
    """Where the stick's files are: its data partition's mount point (mounted if it isn't)."""
    return mount(d["Ventoy"])


def where_text(d: dict) -> str:
    """Where a disk is mounted, by the folder's name: the whole path is too long for the list."""
    return ", ".join(Path(m).name or m for m in d["Letters"]) if d["Letters"] else ("not mounted" if d.get("Ventoy") else "")


def wait_for_stick(disk_no, run_=None, timeout: float = 60, expected: dict | None = None) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        d = next((d for d in app.all_disks() if d["Number"] == disk_no), None)
        if d and expected is not None:
            d = app.recheck_disk(expected)
        if d and d.get("Ventoy") and d.get("IsVentoy"):
            return stick_path(d)
        time.sleep(2)
    raise RescueError(f"/dev/{disk_no} shows no Ventoy stick. Unplug it, plug it in again and use Update.")


# ── Ventoy (its own script, as root) ───────────────────────────────────────
# What runs as root is decided here, not by what happens to be on disk when the password is
# typed. Your cache is yours to write, so root never runs anything out of it: it is handed
# Ventoy's archive and the checksum that archive was verified against, makes its own copy where
# only root can write, checks that copy, unpacks it there and runs Ventoy's script from there.
ROOT_TOOLS = ("/usr/bin", "/usr/sbin", "/bin", "/sbin")     # root's programs are found here, never on your PATH
VERIFIED: dict[str, str] = {}                               # Ventoy archive -> the sha256 it was verified to have
# What Ventoy's archive must be. Not what the cache or a pack says it is, since whoever could
# change the archive there could change that as well: the checksums Ventoy publishes, as this
# program was built knowing them, and for a Ventoy newer than those, asked of its release now.
# (scripts/release.sh won't cut a release whose Ventoy isn't listed here.)
VENTOY_SHA256 = {
    "ventoy-1.1.17-linux.tar.gz": "7fb4ed08cef6a6b4d39dd19260d8c80291a78dfdf9af7d461571e23cbbc43805",
}
VENTOY_SUMS = "https://github.com/ventoy/Ventoy/releases/download/v{version}/sha256.txt"
RUN_VENTOY = r'''
set -eu
archive=$1; want=$2; shift 2
work=$(mktemp -d /run/helix-boot.XXXXXX)
trap 'rm -rf "$work"' EXIT INT TERM
cp -- "$archive" "$work/ventoy.tar.gz"
if ! echo "$want  $work/ventoy.tar.gz" | sha256sum -c --status -; then
  echo "Ventoy's archive is not the one that was verified; nothing was written" >&2
  exit 97
fi
mkdir "$work/x"
tar -xzf "$work/ventoy.tar.gz" -C "$work/x" --no-same-owner
cd "$work"/x/ventoy-*/
./Ventoy2Disk.sh "$@"
'''


def root_tool(name: str) -> str:
    for folder in ROOT_TOOLS:
        if os.access(f"{folder}/{name}", os.X_OK):
            return f"{folder}/{name}"
    raise RescueError(f"'{name}' isn't installed, and this step needs it")


def as_root(cmd: list[str], feed: str = "", timeout: float = ROOT_TIMEOUT) -> tuple[int, str]:
    """Run one command as root, behind the desktop's password dialog. (code, what it printed)."""
    try:
        pkexec = root_tool("pkexec")
    except RescueError:
        raise RescueError("this step needs your password, and there is no pkexec (polkit) to ask for it. "
                          "Use ./install.sh or ./refresh.sh in a terminal instead.") from None
    try:
        r = subprocess.run([pkexec, *cmd], input=feed, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RescueError(f"{Path(cmd[0]).name} didn't finish within {int(timeout / 60)} minutes") from None
    if r.returncode in (126, 127):          # pkexec: not authorised, or the dialog was dismissed
        raise RescueError("the password wasn't given, so nothing was written")
    return r.returncode, r.stdout + r.stderr


def ventoy_sha256(name: str) -> str:
    """The checksum Ventoy publishes for one of its Linux archives, by the archive's name."""
    if name in VENTOY_SHA256:
        return VENTOY_SHA256[name]
    m = re.fullmatch(r"ventoy-(\d+(?:\.\d+){1,3})-linux\.tar\.gz", name)
    if not m:
        raise RescueError(f"{name} isn't named as Ventoy's Linux archives are; refusing to run it as root")
    try:        # (https to github.com only: the engine never follows a download down to http)
        found = cr.parse_checksum_text(cr.http_get(VENTOY_SUMS.format(version=m[1])).decode("utf-8", "replace"), name)
    except (cr.RescueError, OSError) as e:
        found, why = None, str(e)
    else:
        why = "its release lists no checksum for that file"
    if not found or found[0] != "sha256" or not re.fullmatch(r"[0-9a-f]{64}", found[1]):
        raise RescueError(f"Ventoy {m[1]} is newer than this program knows, and its checksum couldn't be had from "
                          f"Ventoy's release page ({why}). Go online and try again, or use ./install.sh in a terminal.")
    return found[1]


def verified(archive: Path) -> Path:
    """An archive root may run: it has the checksum Ventoy publishes for a file of that name."""
    want = ventoy_sha256(archive.name)
    if cr.file_hash(archive) != want:
        raise RescueError(f"{archive} is not the file Ventoy published under that name (its checksum differs). "
                          "It won't be run as root. Delete it and try again.")
    VERIFIED[str(archive)] = want
    return archive


def ventoy_dir(cfg) -> Path:
    """Ventoy's archive as downloaded, if it is still the file Ventoy publishes."""
    entry = cr.load_lock(cfg).get("ventoy") or {}
    archive = cfg.cache / "ventoy" / Path(str(entry.get("source_file") or "-")).name
    if not archive.is_file():
        raise RescueError("Ventoy isn't downloaded: check your connection and try again")
    return verified(archive)


def pack_ventoy_dir(cfg, pack) -> Path:
    """Ventoy's archive out of a pack, in the cache, if it is the file Ventoy publishes."""
    with cr._open_pack(str(pack)) as zf:
        v = cr._read_pack(zf).get("ventoy")
        if not v or not str(v.get("file", "")).endswith(".tar.gz"):
            raise RescueError("this pack has no Ventoy installer for Linux. Make it again after `helix fetch ventoy`.")
        dest = cr._inside(cfg.cache.resolve(), f"ventoy-from-pack/{Path(v['file']).name}", "Ventoy archive")
        dest.parent.mkdir(parents=True, exist_ok=True)
        cr._unzip_to(zf, v["file"], dest)
    return verified(dest)


def ventoy_command(vdir: Path, mode: str, disk_no, gpt: bool = True, secure_boot: bool = True) -> list[str]:
    """Ventoy2Disk.sh's arguments: install (/I, as the window calls it) or upgrade in place (/U)."""
    if not DISK_NAME.fullmatch(str(disk_no)):
        raise RescueError(f"{disk_no!r} isn't a disk's name")
    args = ["-I"] if mode == "/I" else ["-u"]
    if mode == "/I":
        label = str(getattr(app.config(), "stick_label", "") or "")
        if label != "Ventoy" and re.fullmatch(r"[A-Za-z0-9_-]{1,11}", label):
            args += ["-L", label]
        if gpt:
            args.append("-g")
    args.append("-s" if secure_boot else "-S")
    return [*args, f"/dev/{disk_no}"]


def run_ventoy(args: list[str], vdir: Path, progress=lambda pct: None, timeout: float = ROOT_TIMEOUT) -> None:
    """Unmount the disk and have root run Ventoy2Disk.sh on it, from its own checked copy of the
    archive `vdir`. Ventoy asks "Continue?" twice, which was answered in the window; it exits 0
    even when it gives up, so its own words decide."""
    dev, want = args[-1], VERIFIED.get(str(vdir))
    if not want or not re.fullmatch(r"[0-9a-f]{64}", want):
        raise RescueError(f"{vdir} isn't a Ventoy archive this run verified; refusing to run it as root")
    for part in partitions(dev):
        unmount(part)
    code, said = as_root(["/bin/sh", "-c", RUN_VENTOY, "helix-boot", str(vdir), want, *args],
                         feed="y\ny\n", timeout=timeout)
    lines = [line.rstrip() for line in said.splitlines() if line.strip()]
    print("\n".join(lines[-12:]))
    try:
        subprocess.run(["udevadm", "settle", "--timeout=30"], capture_output=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        time.sleep(3)
    if code or "successfully finished" not in said:
        raise RescueError(f"Ventoy's installer didn't finish on {dev}:\n" + "\n".join(lines[-4:]))
    progress(100)


def name_stick(letter: str, label: str, run_=None) -> None:
    """(Ventoy's Linux installer names the stick itself: -L in ventoy_command.)"""


def boot_script(target: str, efi: str | None = None, disk_no=None, run=None) -> bool:   # noqa: ARG001
    """The splash before the menu and what the L and F1 keys do, in Ventoy's boot script on its own
    partition. Never fatal: without it the stick starts as Ventoy does. False then."""
    cfg = app.config()
    part = None
    try:
        d = next((d for d in app.all_disks() if d["Number"] == disk_no), None)
        part = efi or (d or {}).get("Efi")
        if not part:
            raise RescueError("Ventoy's own partition isn't on this disk")
        if cr.cmd_splash(cfg, app.ns(efi=mount(part), remove=False, dry_run=False, stick=target)):
            raise RescueError("Ventoy's boot script couldn't be changed")
        return True
    except (cr.RescueError, OSError, ValueError) as e:
        print(f"! no splash, and L and F1 stay Ventoy's Language and Help: {e}")
        try:
            cr.forget_keys_hook(cfg, Path(target))
        except (cr.RescueError, OSError):
            pass
        return False
    finally:
        if part:
            try:
                unmount(part)
            except RescueError:
                pass


# ── Repair, and the words that differ ──────────────────────────────────────
def repair_question(d: dict) -> str:
    return (f"Repair the filesystem on {d['Ventoy']}?\n\n"
            f"This unmounts the stick and runs fsck on it, which asks for your password. It is for a "
            "stick that an update or a check says is damaged; it erases nothing, though a file that "
            "was damaged may be lost. Close anything that has the stick open first.")


def repair(target: str, run_=None) -> str:
    """Unmount the stick, have fsck repair it as root, and mount it again."""
    part = run(["findmnt", "-no", "SOURCE", "--target", str(target)]).strip().split("[")[0]
    if not re.fullmatch(r"/dev/[A-Za-z0-9]+", part) or not mounted_at(part):
        raise RescueError(f"{target} isn't a mounted stick")
    fsck = root_tool("fsck")
    print(f"\nRepairing the filesystem on {part} (fsck -y) …")
    unmount(part)
    try:
        code, said = as_root([fsck, "-y", part], timeout=3600)
    finally:
        try:
            mount(part)
        except RescueError as e:
            print(f"! {e}: unplug the stick and plug it in again")
    said = "\n".join(line.rstrip() for line in said.splitlines() if line.strip())
    print(said)
    # fsck: 0 nothing wrong, 1 errors corrected, 2 corrected (reboot wanted); 4 and up, not repaired
    if code >= 4:
        raise RescueError(f"fsck couldn't repair {part}. If it keeps failing, the stick is worn out: "
                          f"make a new one.\n\n{said[-600:]}")
    return (f"✓ {part} had errors and they were repaired. Update the stick, then Check stick."
            if code else f"✓ fsck found nothing wrong with the filesystem on {part}.")


def open_path(path: Path) -> bool:
    opener = shutil.which("xdg-open")
    if not opener:
        return False
    subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def on_linux() -> None:
    """Put this system's parts where the window and its install and update steps look for them."""
    for name, mine in dict(
        all_disks=all_disks, disk_identity=disk_identity, stick_path=stick_path, where_text=where_text,
        wait_for_ventoy_letter=wait_for_stick, ventoy_dir=ventoy_dir, pack_ventoy_dir=pack_ventoy_dir,
        ventoy_command=ventoy_command, run_ventoy=run_ventoy, name_stick=name_stick, boot_script=boot_script,
        repair=repair, repair_question=repair_question, open_path=open_path,
    ).items():
        setattr(app, name, mine)
    app.SYSTEM = "system"
    app.APP_ASSET = f"HelixBoot-linux-{platform.machine()}"     # this program's file in a release
    app.WINDOW = (680, 600)             # (the fonts here are wider than Windows' own)
    app.SAFE_TO_REMOVE = "eject it in your file manager before unplugging it"
    app.NO_LETTER = "or its partition can't be found"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if os.name == "nt":
        print("This is the Linux window; on Windows use HelixBoot.exe.", file=sys.stderr)
        return 1
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Run this as your normal user: it asks for your password only for the steps that need it.",
              file=sys.stderr)
        return 1
    on_linux()
    app.tidy_old_program()
    try:
        if "--self-update" in argv:
            print(app.self_update())
            return 0
        if "--version" in argv:
            print(f"helix {cr.__version__}")
            return 0
        if "--list" in argv:
            print(json.dumps(app.all_disks() if "--all" in argv else app.usb_disks(), indent=2))
            return 0
        if argv and argv != ["--selftest-gui"]:
            print(__doc__.strip())
            return 0 if argv[0] in ("-h", "--help") else 2
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("The window needs Tk, which this Python doesn't have. Install it (Arch: sudo pacman -S tk; "
                  "Debian/Ubuntu: sudo apt install python3-tk; Fedora: sudo dnf install python3-tkinter),\n"
                  "or download the one-file program from the releases page, which has it inside.", file=sys.stderr)
            return 1
        return app.gui(selftest=argv == ["--selftest-gui"])
    except cr.RescueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
