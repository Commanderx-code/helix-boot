#!/usr/bin/env python3
"""Regenerate the Commander Rescue Ventoy theme's images and fonts.

The generated files are committed, so you only need this to change the look.
Needs Pillow, grub-mkfont (grub package) and the DejaVu fonts:

    sudo pacman -S --needed python-pillow grub ttf-dejavu
    theme/build-theme.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080

# Palette (keep theme.txt and crescue's menu_tip colour in step with these)
BG_TOP = (11, 16, 26)
BG_BOTTOM = (18, 28, 44)
PANEL = (13, 20, 32, 215)
BORDER = (44, 62, 88, 255)
ACCENT = (245, 165, 36)
TEXT = (230, 237, 243)
MUTED = (139, 152, 169)

FONT_DIRS = [Path("/usr/share/fonts/TTF"), Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu")]


def ttf(name: str) -> Path:
    for d in FONT_DIRS:
        if (d / name).exists():
            return d / name
    sys.exit(f"can't find {name} — install the DejaVu fonts")


def background() -> None:
    sw, sh = W // 10, H // 10          # gradient at 1/10 size, then smoothed up
    img = Image.new("RGB", (sw, sh))
    px = img.load()
    for y in range(sh):
        for x in range(sw):
            t = min(1.0, (y / sh) * 0.8 + (x / sw) * 0.2)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
    img = img.resize((W, H), Image.BICUBIC)
    # soft accent glow, top right
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W - 700, -500, W + 400, 450), fill=38)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(Image.new("RGB", (W, H), ACCENT), img, glow)

    d = ImageDraw.Draw(img)
    bold = ImageFont.truetype(str(ttf("DejaVuSans-Bold.ttf")), 64)
    thin = ImageFont.truetype(str(ttf("DejaVuSans-ExtraLight.ttf")), 64)
    small = ImageFont.truetype(str(ttf("DejaVuSans.ttf")), 24)
    x, y = 192, 118                                     # aligned with the menu's left edge (10%)
    d.rectangle((x, y + 8, x + 8, y + 70), fill=ACCENT)  # accent bar
    x += 32
    d.text((x, y), "COMMANDER", font=bold, fill=TEXT)
    x += d.textlength("COMMANDER ", font=bold)
    d.text((x, y), "RESCUE", font=thin, fill=ACCENT)
    d.text((224, y + 88), "Multiboot rescue USB  ·  verified upstream tools", font=small, fill=MUTED)
    img.save(HERE / "background.png", optimize=True)


def nine_slice(prefix: str, fill, border=None, left_bar=None, size: int = 8) -> None:
    """Write prefix_{nw,n,ne,w,c,e,sw,s,se}.png for GRUB's 9-slice styled boxes."""
    for part, (w, h) in {
        "nw": (size, size), "n": (1, size), "ne": (size, size),
        "w": (size, 1), "c": (1, 1), "e": (size, 1),
        "sw": (size, size), "s": (1, size), "se": (size, size),
    }.items():
        im = Image.new("RGBA", (w, h), fill)
        if border:
            d = ImageDraw.Draw(im)
            if "n" in part: d.line((0, 0, w, 0), fill=border)
            if "s" in part: d.line((0, h - 1, w, h - 1), fill=border)
            if "w" in part: d.line((0, 0, 0, h), fill=border)
            if "e" in part: d.line((w - 1, 0, w - 1, h), fill=border)
        if left_bar and part in ("nw", "w", "sw"):
            ImageDraw.Draw(im).rectangle((0, 0, 3, h), fill=left_bar)
        im.save(HERE / f"{prefix}_{part}.png", optimize=True)


def slider() -> None:
    for part, h in (("n", 4), ("c", 1), ("s", 4)):
        im = Image.new("RGBA", (6, h), (*MUTED, 150))
        im.save(HERE / f"slider_{part}.png", optimize=True)


def fonts() -> None:
    if not shutil.which("grub-mkfont"):
        sys.exit("grub-mkfont not found — install the grub package")
    out = HERE / "fonts"
    out.mkdir(exist_ok=True)
    # Latin, punctuation and arrows keep the files small; Ventoy's own unicode
    # font covers anything else.
    ranges = "0x20-0x7E,0xA0-0x17F,0x2010-0x2027,0x2190-0x2193,0x25B6-0x25B6"
    for src, size, name in (
        ("DejaVuSans.ttf", 16, "dejavu-16.pf2"),
        ("DejaVuSans.ttf", 22, "dejavu-22.pf2"),
        ("DejaVuSans-Bold.ttf", 22, "dejavu-bold-22.pf2"),
    ):
        subprocess.run(["grub-mkfont", "-s", str(size), "-r", ranges, "-o", str(out / name), str(ttf(src))],
                       check=True)


if __name__ == "__main__":
    background()
    nine_slice("menu", PANEL, border=BORDER)
    nine_slice("select", (*ACCENT, 40), left_bar=(*ACCENT, 255), size=4)
    nine_slice("terminal_box", (8, 12, 20, 240), border=BORDER)
    slider()
    fonts()
    print(f"theme written to {HERE}")
