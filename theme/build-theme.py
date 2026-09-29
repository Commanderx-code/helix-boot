#!/usr/bin/env python3
"""Regenerate the Commander Rescue Ventoy theme's images and fonts.

The generated files are committed, so you only need this to change the look.
Needs Pillow, grub-mkfont (grub package) and the DejaVu fonts:

    sudo pacman -S --needed python-pillow grub ttf-dejavu
    theme/build-theme.py

Tools you add in local.toml get their letter badges (into byo/icons/) with:

    theme/build-theme.py --local
"""
import math
import shutil
import subprocess
import sys
import tomllib
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

ICON = 40                     # keep in step with icon_width/icon_height in theme.txt
SS = 8                        # draw icons this many times larger, then scale down (anti-aliasing)

# Category tile colours, by [[category]] id in tools.toml
CATEGORY_COLOURS = {
    "antivirus": (46, 160, 67),
    "imaging": (31, 155, 181),
    "boot-repair": (110, 127, 150),
    "diagnostics": (229, 83, 75),
    "wipe": (232, 116, 59),
    "live": (59, 130, 246),
    "partitioning": (137, 87, 229),
    "password": (245, 165, 36),
    "windows": (14, 165, 233),
}

# Badge text for tools whose initials don't read well; the rest use their title's initials.
# Drop a real logo in byo/icons/<name>.png to replace any of these on your stick.
BADGES = {
    "lazarus-pe": "LZ", "hirens": "HB", "rescuezilla": "RZ", "clonezilla": "CZ",
    "gparted": "GP", "memtest86plus": "M+", "shredos": "SH", "dban": "DB", "supergrub2": "SG", "boot-repair-disk": "BR",
    "kaspersky-rd": "K", "drweb-livedisk": "DW", "macrium-reflect": "MR", "aomei-backupper": "AB",
    "easeus-todo-backup": "ET", "easeus-data-recovery": "ED", "active-data-studio": "A@", "aomei-pa": "AP",
    "paragon-hdm": "PH", "parted-magic": "PM", "bootit-bm": "BI", "hdat2": "H2", "memtest86": "MT",
    "spinrite": "SP", "windows11": "11", "windows10": "10", "ms-dart": "DR", "lockpick": "LP",
}

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


# ── Icons (theme/icons/<class>.png; Ventoy's menu_class picks the class) ────

class Pen:
    """Draw in 0..1 coordinates on a supersampled canvas."""

    def __init__(self, bg=None):
        self.n = ICON * SS
        self.im = Image.new("RGBA", (self.n, self.n), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        if bg:
            self.d.rounded_rectangle((0, 0, self.n - 1, self.n - 1), radius=self.n * 0.22, fill=bg)

    def xy(self, *pts):
        return [v * self.n for v in pts]

    def w(self, v):
        return max(1, round(v * self.n))

    def arrow_arc(self, box, start, end, width, fill):
        self.d.arc(self.xy(*box), start, end, fill=fill, width=self.w(width))
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        r = (box[2] - box[0]) / 2 - width / 2
        a = math.radians(end)
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)          # direction of travel (clockwise)
        nx, ny = math.cos(a), math.sin(a)
        h = width * 1.9
        self.d.polygon(self.xy(px + tx * h, py + ty * h, px + nx * h, py + ny * h, px - nx * h, py - ny * h),
                       fill=fill)

    def save(self, name, out=None):
        out = out or HERE / "icons"
        out.mkdir(parents=True, exist_ok=True)
        self.im.resize((ICON, ICON), Image.LANCZOS).save(out / f"{name}.png", optimize=True)


def glyph(cid: str, pen: Pen, fg, bg) -> None:
    d, xy, w = pen.d, pen.xy, pen.w
    if cid == "antivirus":      # shield with a tick
        d.polygon(xy(.5, .15, .75, .25, .73, .52, .5, .85, .27, .52, .25, .25), fill=fg)
        d.line(xy(.37, .5, .47, .61, .64, .39), fill=bg, width=w(.08), joint="curve")
    elif cid == "imaging":      # clock with a circular arrow
        pen.arrow_arc((.2, .2, .8, .8), 120, 400, .07, fg)
        d.line(xy(.5, .5, .5, .34), fill=fg, width=w(.06))
        d.line(xy(.5, .5, .62, .58), fill=fg, width=w(.06))
    elif cid == "boot-repair":  # sticking plaster
        layer = Pen()
        layer.d.rounded_rectangle(layer.xy(.14, .36, .86, .64), radius=layer.n * .13, fill=fg)
        layer.d.rectangle(layer.xy(.38, .36, .62, .64), fill=bg)
        for x in (.44, .56):
            for y in (.44, .56):
                layer.d.ellipse(layer.xy(x - .025, y - .025, x + .025, y + .025), fill=fg)
        pen.im.alpha_composite(layer.im.rotate(45, resample=Image.BICUBIC))
    elif cid == "diagnostics":  # heart with a pulse
        d.ellipse(xy(.2, .24, .52, .56), fill=fg)
        d.ellipse(xy(.48, .24, .8, .56), fill=fg)
        d.polygon(xy(.22, .46, .78, .46, .5, .8), fill=fg)
        d.line(xy(.16, .52, .36, .52, .44, .36, .54, .66, .61, .52, .84, .52), fill=bg, width=w(.05),
               joint="curve")
    elif cid == "wipe":         # shredder
        d.rounded_rectangle(xy(.2, .2, .8, .46), radius=w(.06), fill=fg)
        d.rectangle(xy(.2, .5, .8, .54), fill=fg)
        for i in range(5):
            x = .26 + i * .115
            d.rectangle(xy(x, .58, x + .06, .8 - (i % 2) * .06), fill=fg)
    elif cid == "live":         # monitor with a prompt
        d.rounded_rectangle(xy(.16, .2, .84, .64), radius=w(.05), outline=fg, width=w(.06))
        d.line(xy(.29, .33, .38, .42, .29, .51), fill=fg, width=w(.05), joint="curve")
        d.line(xy(.43, .51, .58, .51), fill=fg, width=w(.05))
        d.rectangle(xy(.45, .64, .55, .74), fill=fg)
        d.rounded_rectangle(xy(.32, .74, .68, .8), radius=w(.02), fill=fg)
    elif cid == "partitioning":  # pie chart with a slice pulled out
        d.pieslice(xy(.2, .22, .78, .8), -90, 200, fill=fg)
        d.pieslice(xy(.16, .18, .74, .76), 200, 270, fill=fg)
    elif cid == "password":     # key
        d.ellipse(xy(.14, .3, .46, .62), outline=fg, width=w(.08))
        d.rectangle(xy(.44, .43, .86, .5), fill=fg)
        d.rectangle(xy(.7, .5, .76, .62), fill=fg)
        d.rectangle(xy(.8, .5, .86, .58), fill=fg)
    elif cid == "windows":      # window with a restore arrow
        d.rounded_rectangle(xy(.16, .2, .84, .8), radius=w(.05), outline=fg, width=w(.06))
        d.rectangle(xy(.16, .2, .84, .33), fill=fg)
        pen.arrow_arc((.34, .42, .66, .74), 150, 420, .055, fg)


def initials(title: str) -> str:
    words = [w for w in title.replace("-", " ").split() if w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def badge(t: dict, out=None) -> None:
    """A tool's letter badge, tinted by its category. `badge = "XX"` in the manifest wins."""
    col = CATEGORY_COLOURS.get(t.get("category"), MUTED)
    tile = tuple(round(c * .28 + b * .72) for c, b in zip(col, (20, 29, 44)))
    pen = Pen(bg=(*tile, 255))
    pen.d.rounded_rectangle((0, 0, pen.n - 1, pen.n - 1), radius=pen.n * .22,
                            outline=(*col, 255), width=pen.w(.05))
    text = t.get("badge") or BADGES.get(t["name"]) or initials(t["title"])
    size = pen.n * (.46 if len(text) < 3 else .36)
    font = ImageFont.truetype(str(ttf("DejaVuSans-Bold.ttf")), round(size))
    pen.d.text((pen.n / 2, pen.n / 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    pen.save(t["name"], out)


def local_badges() -> None:
    """Badges for the boot tools in local.toml, written to byo/icons/ (git-ignored).
    An icon already there, such as a real logo you saved, is left alone."""
    local = HERE.parent / "local.toml"
    if not local.exists():
        print("no local.toml, so no local tools to badge")
        return
    out = HERE.parent / "byo" / "icons"
    made = []
    for t in tomllib.loads(local.read_text(encoding="utf-8")).get("tool", []):
        if t.get("kind") == "iso" and not (out / f"{t['name']}.png").exists():
            badge(t, out)
            made.append(t["name"])
    print(f"badges written to {out}: {', '.join(made)}" if made else "every local tool already has an icon")


def icons() -> None:
    manifest = tomllib.loads((HERE.parent / "tools.toml").read_text(encoding="utf-8"))
    shutil.rmtree(HERE / "icons", ignore_errors=True)
    white = (255, 255, 255, 255)
    for cid, col in CATEGORY_COLOURS.items():
        pen = Pen(bg=(*col, 255))
        glyph(cid, pen, white, (*col, 255))
        pen.save(f"cat-{cid}")

    for t in manifest.get("tool", []):
        if t.get("kind") == "iso":
            badge(t)

    # Ventoy's own classes: folders, the "go back" entry and files without an icon of their own
    pen = Pen()
    amber = (*ACCENT, 255)
    pen.d.polygon(pen.xy(.12, .24, .4, .24, .46, .32, .88, .32, .88, .4, .12, .4), fill=amber)
    pen.d.rounded_rectangle(pen.xy(.12, .34, .88, .78), radius=pen.w(.05), fill=amber)
    pen.save("vtoydir")
    pen = Pen(bg=(*BORDER[:3], 255))
    pen.d.line(pen.xy(.72, .5, .32, .5), fill=white, width=pen.w(.08))
    pen.d.polygon(pen.xy(.22, .5, .44, .3, .44, .7), fill=white)
    pen.save("vtoyret")
    pen = Pen()
    pen.d.ellipse(pen.xy(.12, .12, .88, .88), fill=(*TEXT, 255))
    pen.d.ellipse(pen.xy(.24, .24, .76, .76), outline=(*MUTED, 255), width=pen.w(.03))
    pen.d.ellipse(pen.xy(.4, .4, .6, .6), fill=(*BORDER[:3], 255))
    pen.d.ellipse(pen.xy(.46, .46, .54, .54), fill=(0, 0, 0, 0))
    for cls in ("vtoyiso", "vtoyimg", "vtoywim", "vtoyefi", "vtoyvhd", "vtoyvtoy"):
        pen.save(cls)


if __name__ == "__main__":
    if sys.argv[1:] == ["--local"]:  # only your local.toml tools; the theme itself is untouched
        local_badges()
        sys.exit(0)
    background()
    nine_slice("menu", PANEL, border=BORDER)
    nine_slice("select", (*ACCENT, 40), left_bar=(*ACCENT, 255), size=4)
    nine_slice("terminal_box", (8, 12, 20, 240), border=BORDER)
    slider()
    icons()
    fonts()
    print(f"theme written to {HERE}")
