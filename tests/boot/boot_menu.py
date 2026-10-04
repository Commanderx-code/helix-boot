#!/usr/bin/env python3
"""Boot the Ventoy menu in a virtual machine, once per theme, and check that it came up.

Builds a throwaway Ventoy disk image (no root needed), lays the stick's menu and theme on it
exactly as `helix sync` would, with a small stand-in for each boot image, then starts it in
QEMU and takes real screenshots: the main menu and the inside of a category. A theme passes
when the screen shows that theme's own background behind a menu that was actually drawn, so a
theme Ventoy refuses to load, or a menu that never appears, fails here and not on a real stick.

    tests/boot/boot_menu.py                      # every theme, UEFI
    tests/boot/boot_menu.py --themes default,standby --firmware both --out /tmp/shots

Needs qemu-system-x86_64, OVMF, mtools, dosfstools, xz and Pillow, and Ventoy in the
cache (`./helix fetch ventoy`). Screenshots and a contact sheet land in --out.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
OVMF = [  # (code, vars) by distribution
    ("/usr/share/edk2/x64/OVMF_CODE.4m.fd", "/usr/share/edk2/x64/OVMF_VARS.4m.fd"),       # Arch
    ("/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_VARS_4M.fd"),                # Debian, Ubuntu
    ("/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_VARS.fd"),
    ("/usr/share/edk2/ovmf/OVMF_CODE.fd", "/usr/share/edk2/ovmf/OVMF_VARS.fd"),            # Fedora
]
SECTOR, DISK_SECTORS, EFI_SECTORS = 512, 2 * 1024 * 1024, 65536      # a 1 GiB disk; Ventoy's 32 MiB VTOYEFI
KVM = os.access("/dev/kvm", os.W_OK)
SLOW = 1 if KVM else 8                                               # without KVM everything takes longer


def load_helix():
    loader = importlib.machinery.SourceFileLoader("helix", str(ROOT / "helix"))
    spec = importlib.util.spec_from_loader("helix", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw)


def mtools(image: Path, *cmd, offset: bool = True):
    """An mtools command on the image's data partition (at 1 MiB) or on a partition image."""
    return run(cmd[0], "-i", f"{image}@@1M" if offset else image, *cmd[1:], env={**os.environ, "MTOOLS_SKIP_CHECK": "1"})


def build_disk(cr, cfg, work: Path) -> Path:
    """A Ventoy disk laid out by the engine (ventoy_layout, as a Mac install writes it), with a
    FAT32 data partition, and the splash added to Ventoy's boot script as install.sh adds it."""
    ventoy = Path(run(ROOT / "helix", "ventoy-path").stdout.strip())
    layout = cr.ventoy_layout(ventoy, DISK_SECTORS, data_type=0x0C)
    efi = work / "vtoyefi.img"
    efi.write_bytes(layout["efi"])
    (work / "efi/grub").mkdir(parents=True)
    mtools(efi, "mcopy", "-o", "::/grub/grub.cfg", work / "efi/grub/grub.cfg", offset=False)
    cr.cmd_splash(cfg, argparse.Namespace(efi=str(work / "efi"), remove=False, dry_run=False))
    mtools(efi, "mcopy", "-o", work / "efi/grub/grub.cfg", "::/grub/grub.cfg", offset=False)

    disk = work / "stick.img"
    with open(disk, "wb") as f:
        f.truncate(DISK_SECTORS * SECTOR)
        f.write(layout["head"])
        f.seek(layout["efi_start"] * SECTOR)
        f.write(efi.read_bytes())
    run("mkfs.vfat", "-F", "32", "-n", cfg.stick_label[:11], "--offset", str(layout["data_start"]), disk,
        layout["data_sectors"] // 2)
    return disk


def fake_stick(cr, cfg, stick: Path) -> None:
    """The menu and theme as sync writes them, and a 64 KiB stand-in for every boot image."""
    placed = [{"name": t["name"], "title": t["title"], "category": t["category"], "file": f"{t['name']}.iso",
               "description": t.get("description", "")} for t in cfg.enabled(kinds={"iso"})]
    (stick / cr.STATE_DIR).mkdir(parents=True)
    extras = [(rel, data) for rel, data in cr._stick_extras(cfg, placed, [])
              if rel.startswith((f"{cr.STATE_DIR}/", "ventoy/"))]
    menu = cr._write_extras(cfg, stick, {}, extras, True)
    (stick / cr.STATE_DIR / "state.json").write_text(                 # so changing the look isn't taken for
        json.dumps({"files": [], "apps": {}, "ventoy_json_sha": cr.file_hash(menu)}), encoding="utf-8")   # a hand edit
    for p in placed:
        image = stick / cfg.iso_root / cfg.categories[p["category"]]["dir"] / p["file"]
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"\0" * 65536)


class Machine:
    """QEMU started on the disk, driven over QMP: keys in, screenshots out."""

    def __init__(self, disk: Path, firmware: str, work: Path):
        self.sock = work / "qmp.sock"
        self.sock.unlink(missing_ok=True)
        cmd = ["qemu-system-x86_64", "-m", "2048", "-machine", "q35", "-display", "none", "-vga", "std",
               "-drive", f"file={disk},format=raw,if=virtio", "-qmp", f"unix:{self.sock},server,nowait"]
        cmd += ["-enable-kvm", "-cpu", "host"] if KVM else ["-cpu", "max"]
        if firmware == "uefi":
            code, nvram = next(((c, v) for c, v in OVMF if Path(c).is_file() and Path(v).is_file()), (None, None))
            if not code:
                sys.exit("no OVMF firmware found: install ovmf (edk2-ovmf)")
            shutil.copy(nvram, work / "vars.fd")
            cmd += ["-drive", f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive", f"if=pflash,format=raw,file={work / 'vars.fd'}"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            if self.sock.exists():
                break
            if self.proc.poll() is not None:
                sys.exit(f"QEMU didn't start: {self.proc.stderr.read().decode()[-400:]}")
            time.sleep(0.1)
        self.conn = socket.socket(socket.AF_UNIX)
        self.conn.connect(str(self.sock))
        self.io = self.conn.makefile("rw")
        self.io.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, name: str, **arguments):
        self.io.write(json.dumps({"execute": name, **({"arguments": arguments} if arguments else {})}) + "\n")
        self.io.flush()
        while True:
            reply = json.loads(self.io.readline())
            if "return" in reply or "error" in reply:
                return reply

    def key(self, name: str) -> None:
        self.cmd("send-key", keys=[{"type": "qcode", "data": name}])
        time.sleep(0.4 * SLOW)

    def shot(self, path: Path) -> Image.Image:
        raw = path.with_suffix(".ppm")
        self.cmd("screendump", filename=str(raw))
        for _ in range(50):                                           # QEMU writes it a moment later
            try:
                with Image.open(raw) as im:
                    image = im.convert("RGB")
                break
            except (OSError, SyntaxError):
                time.sleep(0.1)
        else:
            sys.exit("QEMU didn't write a screenshot")
        raw.unlink()
        image.save(path)
        return image

    def close(self) -> None:
        self.proc.kill()
        self.proc.wait()


def difference(shot: Image.Image, wanted: Image.Image, box: tuple[float, float, float, float]) -> float:
    """How far a part of the screenshot is from the same part of a picture: 0 identical, 255 opposite."""
    w, h = shot.size
    area = (round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))
    return sum(ImageStat.Stat(ImageChops.difference(shot.crop(area), wanted.resize(shot.size).crop(area))).mean) / 3


def regions(theme_txt: str) -> tuple[tuple, tuple]:
    """From a theme's layout: a stretch of plain background beside the menu, and the part of the
    menu where its rows are. Both as (left, top, right, bottom) fractions of the screen."""
    block = re.search(r"\+ boot_menu \{(.*?)\}", theme_txt, re.S).group(1)
    left, top, width, height = (float(re.search(rf"^\s*{key}\s*=\s*(\d+)%", block, re.M).group(1)) / 100
                                for key in ("left", "top", "width", "height"))
    right = left + width
    beside = (0.02, top, left - 0.03, top + height) if left > 1 - right else (right + 0.03, top, 0.98, top + height)
    return beside, (left + 0.01, top + 0.01, left + min(width, 0.45) - 0.01, top + height * 0.6)


def check_theme(cr, cfg, stick: Path, disk: Path, theme: str, firmware: str, out: Path, work: Path) -> list[str]:
    look, pictures = cr.look_changes(stick, theme=theme, splash="theme")
    cr.set_look(cfg, stick, look, pictures)
    for folder in ("ventoy", cfg.iso_root):
        subprocess.run(["mdeltree", "-i", f"{disk}@@1M", f"::/{folder}"], capture_output=True,
                       env={**os.environ, "MTOOLS_SKIP_CHECK": "1"})
    mtools(disk, "mcopy", "-s", stick / "ventoy", stick / cfg.iso_root, "::/")

    built = stick / "ventoy/theme"
    with Image.open(built / cr._desktop_image(built)) as im:
        background = im.convert("RGB")
    name = f"{theme}-{firmware}"
    clear, menu = regions((built / "theme.txt").read_text(encoding="utf-8"))
    problems, vm = [], Machine(disk, firmware, work)
    try:
        deadline, main = time.monotonic() + 45 * SLOW, None
        while time.monotonic() < deadline:                            # past the firmware and the splash
            time.sleep(1.5)
            main = vm.shot(out / f"{name}-main.png")
            if main.size == (1920, 1080) and difference(main, background, clear) < 12 \
                    and difference(main, background, menu) > 1.5:
                break
        else:
            return [f"{name}: the menu didn't come up with this theme's background (see {name}-main.png)"]
        time.sleep(1 * SLOW)                                          # let the last row finish drawing
        main = vm.shot(out / f"{name}-main.png")
        vm.key("down")
        vm.key("ret")
        time.sleep(1.5 * SLOW)
        folder = vm.shot(out / f"{name}-folder.png")
        if difference(folder, background, clear) >= 12:
            problems.append(f"{name}: opening a category lost the theme (see {name}-folder.png)")
        if difference(folder, main, menu) < 0.5:
            problems.append(f"{name}: Enter on a category didn't open it (see {name}-folder.png)")
        if "key_power.png" in (built / "theme.txt").read_text(encoding="utf-8"):   # the row says L is the power menu
            vm.key("esc")
            time.sleep(1.5 * SLOW)
            back = vm.shot(out / f"{name}-power.png")
            vm.key("l")
            time.sleep(2 * SLOW)
            power = vm.shot(out / f"{name}-power.png")
            if difference(power, background, clear) >= 12 or difference(power, back, menu) < 0.5:
                problems.append(f"{name}: L didn't open the power menu (see {name}-power.png)")
    finally:
        vm.close()
    return problems


def check_image(image: Path, firmware: str, out: Path, work: Path) -> list[str]:
    """Boot a disk made elsewhere (a stick written on a Mac) and check the menu comes up on it, in
    the default theme. The image is copied first: booting writes to a disk."""
    disk = work / f"image-{firmware}.img"
    shutil.copyfile(image, disk)
    theme = ROOT / "theme"
    with Image.open(theme / "background.png") as im:
        background = im.convert("RGB")
    clear, menu = regions((theme / "theme.txt").read_text(encoding="utf-8"))
    name, vm = f"image-{firmware}", Machine(disk, firmware, work)
    try:
        deadline = time.monotonic() + 60 * SLOW
        while time.monotonic() < deadline:
            time.sleep(1.5)
            main = vm.shot(out / f"{name}-main.png")
            if main.size == (1920, 1080) and difference(main, background, clear) < 12 \
                    and difference(main, background, menu) > 1.5:
                return []
        return [f"{name}: the menu didn't come up on this disk (see {name}-main.png)"]
    finally:
        vm.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--themes", help="comma-separated theme ids (default: every one)")
    ap.add_argument("--firmware", choices=["uefi", "bios", "both"], default="uefi")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    ap.add_argument("--image", type=Path, help="boot this disk image, made elsewhere, and check the menu comes up")
    args = ap.parse_args()
    for tool in ("qemu-system-x86_64",) if args.image else ("qemu-system-x86_64", "mkfs.vfat", "mcopy", "mdeltree"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found: this needs QEMU, mtools and dosfstools")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.image:
        problems = []
        with tempfile.TemporaryDirectory(prefix="helix-boot-test-") as tmp:
            for firmware in (["uefi", "bios"] if args.firmware == "both" else [args.firmware]):
                found = check_image(args.image, firmware, args.out, Path(tmp))
                print(f"  {'FAIL' if found else 'ok  '} {args.image.name} ({firmware})")
                problems += found
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        return 1 if problems else 0
    cr = load_helix()
    with tempfile.TemporaryDirectory(prefix="helix-boot-test-") as tmp:
        work = Path(tmp)
        (work / "user").mkdir()                                       # a clean setup: no local.toml, no byo/
        os.environ["HELIX_CACHE"] = os.environ.get("HELIX_CACHE") or str(cr.Config().cache)
        cfg = cr.Config(repo=work / "user", assets=ROOT)
        disk, stick = build_disk(cr, cfg, work), work / "stick"
        fake_stick(cr, cfg, stick)
        cr.set_keys_hook(stick, True)                                 # as `helix splash --stick` does on a real one
        themes = args.themes.split(",") if args.themes else [t["id"] for t in cr.look_report(stick)["themes"]
                                                             if t["id"] != "off"]
        firmwares = ["uefi", "bios"] if args.firmware == "both" else [args.firmware]
        print(f"booting {len(themes)} theme(s) on {' and '.join(firmwares)}, {'with' if KVM else 'WITHOUT'} KVM")
        problems = []
        for firmware in firmwares:
            for theme in themes:
                found = check_theme(cr, cfg, stick, disk, theme, firmware, args.out, work)
                print(f"  {'FAIL' if found else 'ok  '} {theme} ({firmware})")
                problems += found
    shots = sorted(args.out.glob("*-main.png")) + sorted(args.out.glob("*-folder.png")) \
        + sorted(args.out.glob("*-power.png"))
    if shots:                                                         # one picture of them all
        cols = 4
        sheet = Image.new("RGB", (cols * 480, -(-len(shots) // cols) * 270))
        for i, f in enumerate(shots):
            with Image.open(f) as im:
                sheet.paste(im.convert("RGB").resize((480, 270)), ((i % cols) * 480, (i // cols) * 270))
        sheet.save(args.out / "sheet.jpg", quality=85)
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    print(f"{'FAILED' if problems else 'all themes boot'}; screenshots in {args.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
