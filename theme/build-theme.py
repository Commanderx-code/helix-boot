#!/usr/bin/env python3
"""Regenerate the Helix Boot Ventoy theme's images and fonts.

The generated files are committed, so you only need this to change the look.
Needs Pillow, grub-mkfont (grub package) and the DejaVu fonts:

    sudo pacman -S --needed python-pillow grub ttf-dejavu
    theme/build-theme.py

Tools you add in local.toml get their letter badges (into byo/icons/) with:

    theme/build-theme.py --local
"""
import argparse
import math
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080

# Helix Steel: the default theme (keep theme.txt and helix's menu_tip colour in step).
ARTS = HERE.parent / "docs/artwork/themes"                      # the backgrounds, wordmark and footer included
ARTWORK = ARTS / "steel.png"
SPLASH_ART = HERE.parent / "docs/artwork/helix-splash.png"     # the default theme's splash, as it is
ICON_DIR = HERE.parent / "docs/artwork/helix-icons"            # the default set: <menu class>.png masters
PANEL = (9, 5, 20, 228)
BORDER = (152, 76, 230, 255)
ACCENT = (181, 94, 255)
CYAN = (0, 220, 235)
TEXT = (244, 240, 255)
MUTED = (186, 171, 211)
SELECT = (71, 22, 119, 220)   # the selected row
SCROLL = (35, 18, 55, 255)
DIM = (6, 3, 14)              # what the splash dims the artwork towards
TITLE = "Helix Steel"
DESCRIPTION = "Brushed metal and a framed wireframe helix."
HOTKEYS = "87%"               # the hotkey row's top in theme.txt: above the artwork's footer rule
VERSION = ("78%", "91%")      # Ventoy's version text: [left, top], in the metal strip under the raised rule

# Presets: the same theme over other artwork from ARTS (theme/presets/<id>/). Each picture has
# its own footer rule, so the hotkey row and Ventoy's version text move to sit above it.
# `helix theme` switches a stick between them.
PRESETS = {
    "moon": dict(title="Helix Moon", description="Bright helix and a moon over dark hills.",
                 hotkeys="91%", version=None),
    "horizon": dict(title="Helix Horizon", description="A planet's glowing rim behind the helix.",
                    hotkeys="91%", version=None),
    "nebula": dict(title="Helix Nebula", description="A thin helix in a purple nebula.",
                   hotkeys="89%", version=("78%", "91%")),
    "circuit": dict(title="Helix Circuit", description="Circuit traces around a wireframe helix.",
                    hotkeys="89%", version=("78%", "91%")),
    "scope": dict(title="Helix Scope", description="A large helix inside crosshair rings.",
                  hotkeys="89%", version=("78%", "91%")),
}
# Other people's GRUB themes, kept as presets with their own layout, boxes and fonts (see each
# folder's NOTICE.md). Their files are committed as adapted; only the splash, in these colours
# over the theme's own background, and preset.toml are made here.
IMPORTED = {
    "standby": dict(
        title="Standby", description="The plain one: black cubes, a power symbol, grey icons. By Llewelyn Trahaearn (GPL).",
        text=(214, 214, 214), highlight=(255, 255, 255), accent=(136, 136, 136), muted=(187, 187, 187),
        tip=("33%", "77%"), version=("84%", "96%"), plain=True),
    "poly-dark": dict(
        title="Poly dark", description="Dark polygons and a plain list, in greys. By Andrei Shevchuk (MIT).",
        text=(190, 190, 190), highlight=(235, 235, 235), accent=(119, 119, 119), muted=(119, 119, 119),
        tip=("15%", "81%"), version=("72%", "96%")),
}
OUT = None                    # where an imported preset's splash is written; None: the theme folder

ICON = 40                     # keep in step with icon_width/icon_height in theme.txt
SS = 8                        # draw icons this many times larger, then scale down (anti-aliasing)

# The categories with an icon of their own, by [[category]] id in tools.toml
CATEGORIES = ("antivirus", "imaging", "boot-repair", "diagnostics", "wipe", "live",
              "partitioning", "password", "windows", "images")

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


def out_dir() -> Path:
    return OUT or HERE


def hexc(color) -> str:
    return "#%02x%02x%02x" % tuple(color[:3])


def ttf(name: str) -> Path:
    for d in FONT_DIRS:
        if (d / name).exists():
            return d / name
    sys.exit(f"can't find {name} — install the DejaVu fonts")


def artwork() -> Image.Image:
    """The picture behind everything: the artwork file, fitted to the screen. Nothing here is UI."""
    with Image.open(ARTWORK) as art:
        return ImageOps.fit(art.convert("RGB"), (W, H), method=Image.LANCZOS)


def background() -> None:
    # The artwork already carries the HELIXBOOT wordmark and the footer; the menu rows,
    # selection, timers and status are live GRUB components.
    artwork().save(out_dir() / "background.png", optimize=True)


def splash() -> None:
    """The picture Ventoy shows for a moment before its menu (splash.png): the same artwork,
    dimmed, with the DNA mark, wordmark and tagline centred. The default theme's is a finished
    picture instead (SPLASH_ART); the imported presets' are drawn, in their colours; the artwork presets use the
    theme's. byo/splash.png
    replaces either."""
    if OUT is None and SPLASH_ART.is_file():
        with Image.open(SPLASH_ART) as art:
            ImageOps.fit(art.convert("RGB"), (W, H), method=Image.LANCZOS).save(out_dir() / "splash.png", optimize=True)
        return
    img = Image.blend(artwork(), Image.new("RGB", (W, H), DIM), 0.45).convert("RGBA")
    cx, top = W // 2, 300
    mark = Image.new("RGBA", (W, H))
    md = ImageDraw.Draw(mark)
    span, amp = 230, 70                     # the theme's DNA mark, about twice the size
    for y in range(0, span + 1, 22):
        offset = amp * math.cos(y / span * math.tau)
        md.line((cx - offset, top + y, cx + offset, top + y), fill=(*MUTED, 255), width=5)
    for sign, color in ((1, CYAN), (-1, ACCENT)):
        points = [(cx + sign * amp * math.cos(t / span * math.tau), top + t) for t in range(span + 1)]
        md.line(points, fill=(*color, 255), width=15, joint="curve")
    img = Image.alpha_composite(img, mark.filter(ImageFilter.GaussianBlur(16)))
    img = Image.alpha_composite(img, mark).convert("RGB")
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(str(ttf("DejaVuSans-Bold.ttf")), 132)
    small = ImageFont.truetype(str(ttf("DejaVuSans.ttf")), 34)
    tiny = ImageFont.truetype(str(ttf("DejaVuSans.ttf")), 21)
    width = d.textlength("HELIX", font=big) + d.textlength("BOOT", font=big)
    x, y = cx - width / 2, top + span + 60
    d.text((x, y), "HELIX", font=big, fill=TEXT)
    d.text((x + d.textlength("HELIX", font=big), y), "BOOT", font=big, fill=CYAN)
    d.text((cx, y + 180), "RECOVERY  •  DIAGNOSTICS  •  REPAIR", font=small, fill=MUTED, anchor="ma")
    d.text((cx, H - 120), "L O A D I N G", font=tiny, fill=(*MUTED,), anchor="ma")
    img.save(out_dir() / "splash.png", optimize=True)


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
            if "n" in part:
                d.line((0, 0, w, 0), fill=border)
            if "s" in part:
                d.line((0, h - 1, w, h - 1), fill=border)
            if "w" in part:
                d.line((0, 0, 0, h), fill=border)
            if "e" in part:
                d.line((w - 1, 0, w - 1, h), fill=border)
        if left_bar and part in ("nw", "w", "sw"):
            ImageDraw.Draw(im).rectangle((0, 0, 3, h), fill=left_bar)
        im.save(out_dir() / f"{prefix}_{part}.png", optimize=True)


def slider() -> None:
    for part, h in (("n", 4), ("c", 1), ("s", 4)):
        im = Image.new("RGBA", (6, h), (*CYAN, 230))
        im.save(out_dir() / f"slider_{part}.png", optimize=True)


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
        # Poly dark's own 16 px Unifont is too small to read at 1080p: its list in a larger mono font
        ("DejaVuSansMono.ttf", 20, "../presets/poly-dark/dejavu-mono-20.pf2"),
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
        out = out or out_dir() / "icons"
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
    elif cid == "images":       # disc with a download arrow
        d.ellipse(xy(.14, .14, .76, .76), outline=fg, width=w(.07))
        d.ellipse(xy(.37, .37, .53, .53), fill=fg)
        d.ellipse(xy(.56, .56, .9, .9), fill=bg)
        d.line(xy(.73, .6, .73, .8), fill=fg, width=w(.07))
        d.polygon(xy(.63, .74, .83, .74, .73, .87), fill=fg)
    elif cid == "windows":      # window with a restore arrow
        d.rounded_rectangle(xy(.16, .2, .84, .8), radius=w(.05), outline=fg, width=w(.06))
        d.rectangle(xy(.16, .2, .84, .33), fill=fg)
        pen.arrow_arc((.34, .42, .66, .74), 150, 420, .055, fg)


def initials(title: str) -> str:
    words = [w for w in title.replace("-", " ").split() if w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def badge(t: dict, out=None, col=None) -> None:
    """A tool's letter badge, tinted by its category. `badge = "XX"` in the manifest wins."""
    col = col or (CYAN if t.get("category") in CATEGORIES else MUTED)
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
    """theme/icons/: the default set, from the masters in docs/artwork/helix-icons/ (one per
    menu class: a tool's name, cat-<category id>, Ventoy's own). Anything without a master
    there gets a plain fallback: a letter badge, or a flat icon drawn here."""
    out = out_dir() / "icons"
    shutil.rmtree(out, ignore_errors=True)
    fallback_icons(out)
    for src in sorted(ICON_DIR.glob("*.png")):
        with Image.open(src) as master:
            icon = master.convert("RGBA")
        icon = ImageOps.contain(icon.crop(icon.getchannel("A").getbbox()), (ICON - 2, ICON - 2), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (ICON, ICON))
        canvas.alpha_composite(icon, ((ICON - icon.width) // 2, (ICON - icon.height) // 2))
        canvas.save(out / src.name, optimize=True)


KEYS = [  # the hotkey bar at the bottom of the menu: (file, key, what it does, master in helix-icons/ or None to draw it)
    ("lang", "L", "Language", None),
    ("help", "F1", "Help", None),
    ("browse", "F2", "Browse", "vtoydir.png"),
    ("tree", "F3", "Tree view", None),
    ("local", "F4", "Local boot", "more/hdd.png"),
    ("tools", "F5", "Tools", "more/ventoy.png"),
    ("menu", "F6", "Menu", "more/boot.png"),
    # On a stick whose Ventoy has the keys' hook (`helix splash --stick`), L and F1 do these instead
    ("power", "L", "Power menu", "power-halt.png"),
    ("mem", "F1", "Memtest86+", "more/mem.png"),
]
KEY_ICON = 32


def key_icons() -> None:
    """theme/key_<name>.png: the icons of the hotkey bar. Those the collection has are fitted from
    their masters; Language, Help and Tree view are drawn here to sit with them: a white sign on a
    glossy blue disc in a steel ring."""
    n = 256

    def disc() -> Image.Image:
        img = Image.new("RGBA", (n, n))
        d = ImageDraw.Draw(img)
        for i in range(n // 2):                                  # the ring: steel, lit from above
            t = i / (n / 2)
            d.ellipse((i * .08, i * .08, n - 1 - i * .08, n - 1 - i * .08),
                      fill=tuple(round(a + (b - a) * t) for a, b in zip((120, 130, 146), (236, 240, 247))) + (255,))
        blue = Image.new("RGBA", (n, n))
        bd = ImageDraw.Draw(blue)
        for i in range(60):                                      # the disc: deep blue, lighter towards the top
            t = i / 59
            col = tuple(round(a + (b - a) * t) for a, b in zip((8, 52, 150), (40, 150, 245)))
            bd.ellipse((24 + i * .6, 24 + i * 1.5 - 30 * t, n - 25 - i * .6, n - 25 - i * .4), fill=col + (255,))
        mask = Image.new("L", (n, n), 0)
        ImageDraw.Draw(mask).ellipse((24, 24, n - 25, n - 25), fill=255)
        img.paste(blue, (0, 0), mask)
        return img

    def gloss(img: Image.Image) -> Image.Image:
        shine = Image.new("RGBA", (n, n))
        ImageDraw.Draw(shine).ellipse((48, 30, n - 49, 132), fill=(255, 255, 255, 54))
        mask = Image.new("L", (n, n), 0)
        ImageDraw.Draw(mask).ellipse((24, 24, n - 25, n - 25), fill=255)
        img.paste(Image.alpha_composite(img, shine), (0, 0), mask)
        return img

    white = (255, 255, 255, 255)
    for name, _, _, master in KEYS:
        if master:
            with Image.open(ICON_DIR / master) as m:
                img = m.convert("RGBA")
            img = img.crop(img.getchannel("A").getbbox())
        else:
            img = disc()
            d = ImageDraw.Draw(img)
            if name == "lang":                                   # a globe
                d.ellipse((62, 62, 193, 193), outline=white, width=11)
                d.ellipse((98, 62, 157, 193), outline=white, width=9)
                d.line((66, 128, 190, 128), fill=white, width=9)
                d.arc((70, 28, 185, 110), 25, 155, fill=white, width=8)
                d.arc((70, 146, 185, 228), 205, 335, fill=white, width=8)
            elif name == "help":
                font = ImageFont.truetype(str(ttf("DejaVuSans-Bold.ttf")), 150)
                d.text((n / 2, n / 2 + 4), "?", font=font, fill=white, anchor="mm")
            else:                                                # tree view: a folder's lines, the lower ones indented
                for k, (x, w) in enumerate(((66, 124), (96, 94), (96, 94))):
                    y = 82 + k * 44
                    d.rounded_rectangle((x, y, x + w, y + 20), radius=8, fill=white)
                d.line((76, 102, 76, 180), fill=white, width=9)
                d.line((76, 136, 96, 136), fill=white, width=9)
                d.line((76, 180, 96, 180), fill=white, width=9)
            img = gloss(img)
        img = ImageOps.contain(img, (KEY_ICON, KEY_ICON), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (KEY_ICON, KEY_ICON))
        canvas.alpha_composite(img, ((KEY_ICON - img.width) // 2, (KEY_ICON - img.height) // 2))
        canvas.save(HERE / f"key_{name}.png", optimize=True)


def fallback_icons(out: Path) -> None:
    """Plain icons for whatever has no master, in `out`: a flat icon per category, a letter badge
    per boot tool, and Ventoy's own classes."""
    manifest = tomllib.loads((HERE.parent / "tools.toml").read_text(encoding="utf-8"))
    white = (255, 255, 255, 255)
    for cid in CATEGORIES:
        pen = Pen()
        glyph(cid, pen, (*CYAN, 255), PANEL)
        pen.save(f"cat-{cid}", out)

    for t in manifest.get("tool", []):
        if t.get("kind") == "iso":
            badge(t, out)

    # Ventoy's own classes: folders, the "go back" entry and files without an icon of their own
    pen = Pen()
    accent = (*CYAN, 255)
    pen.d.polygon(pen.xy(.12, .24, .4, .24, .46, .32, .88, .32, .88, .4, .12, .4), fill=accent)
    pen.d.rounded_rectangle(pen.xy(.12, .34, .88, .78), radius=pen.w(.05), fill=accent)
    pen.save("vtoydir", out)
    pen = Pen(bg=(*BORDER[:3], 255))
    pen.d.line(pen.xy(.72, .5, .32, .5), fill=white, width=pen.w(.08))
    pen.d.polygon(pen.xy(.22, .5, .44, .3, .44, .7), fill=white)
    pen.save("vtoyret", out)
    pen = Pen()
    pen.d.ellipse(pen.xy(.12, .12, .88, .88), fill=(*TEXT, 255))
    pen.d.ellipse(pen.xy(.24, .24, .76, .76), outline=(*MUTED, 255), width=pen.w(.03))
    pen.d.ellipse(pen.xy(.4, .4, .6, .6), fill=(*BORDER[:3], 255))
    pen.d.ellipse(pen.xy(.46, .46, .54, .54), fill=(0, 0, 0, 0))
    for cls in ("vtoyiso", "vtoyimg", "vtoywim", "vtoyefi", "vtoyvhd", "vtoyvtoy"):
        pen.save(cls, out)


def preset_toml(title: str, description: str, version: tuple[str, str] | None) -> str:
    """preset.toml for the theme or one of its presets, all in the theme's palette."""
    return (f'title = "{title}"\ndescription = "{description}"\n'
            f'muted = "{hexc(MUTED)}"                 # ventoy.json: the tip line and Ventoy\'s version text\n'
            f'bar = ["{hexc(CYAN)}", "{hexc(ACCENT)}"]     # the splash\'s loading bar, left to right\n'
            + (f'version = ["{version[0]}", "{version[1]}"]     # Ventoy\'s version text, above the footer rule\n'
               if version else ""))


def themed() -> None:
    """Everything that follows the palette, written to the theme folder."""
    background()
    splash()
    nine_slice("menu", PANEL, border=BORDER)
    nine_slice("select", SELECT, border=(*ACCENT, 255), left_bar=(*CYAN, 255), size=4)
    nine_slice("terminal_box", (*PANEL[:3], 245), border=BORDER)
    nine_slice("scrollbar", SCROLL, size=2)
    slider()
    icons()
    key_icons()
    (out_dir() / "preset.toml").write_text(preset_toml(TITLE, DESCRIPTION, VERSION), encoding="utf-8")


def presets() -> None:
    """theme/presets/<id>/: what differs from the theme itself, which is its background,
    theme.txt and preset.toml. `helix theme` lays one over the theme."""
    theme_txt = (HERE / "theme.txt").read_text(encoding="utf-8")
    for pid, p in PRESETS.items():
        out = HERE / "presets" / pid
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        with Image.open(ARTS / f"{pid}.png") as art:
            ImageOps.fit(art.convert("RGB"), (W, H), method=Image.LANCZOS).save(out / "background.png", optimize=True)
        text = re.sub(rf"top = {HOTKEYS}(?=[-+])", f"top = {p['hotkeys']}", theme_txt.replace(TITLE, p["title"]))
        (out / "theme.txt").write_text(text, encoding="utf-8")
        (out / "preset.toml").write_text(preset_toml(p["title"], p["description"], p["version"]), encoding="utf-8")


def imported() -> None:
    """The splash and preset.toml of each imported theme (IMPORTED), in its own colours."""
    g = globals()
    names = ("OUT", "ARTWORK", "ACCENT", "CYAN", "TEXT", "MUTED", "DIM")
    default = {k: g[k] for k in names}
    try:
        for pid, p in IMPORTED.items():
            out = HERE / "presets" / pid
            g.update(OUT=out, ARTWORK=out / "background.png", ACCENT=p["accent"], CYAN=p["highlight"],
                     TEXT=p["text"], MUTED=p["muted"], DIM=(0, 0, 0))
            splash()
            (out / "preset.toml").write_text(
                f'title = "{p["title"]}"\ndescription = "{p["description"]}"\n'
                'standalone = true                 # its own layout, boxes and fonts: the theme\'s aren\'t laid under it\n'
                + ('plain = true                      # the plain choice: `--theme off` gives this, not Ventoy\'s own look\n'
                   if p.get("plain") else "") +
                'icons = "grey"                    # the tool icons in greyscale, unless you pick a pack\n'
                f'muted = "{hexc(MUTED)}"                 # ventoy.json: the tip line and Ventoy\'s version text\n'
                f'tip = ["{p["tip"][0]}", "{p["tip"][1]}"]             # … and where they go in this layout\n'
                f'version = ["{p["version"][0]}", "{p["version"][1]}"]\n'
                f'bar = ["{hexc(CYAN)}", "{hexc(ACCENT)}"]     # the splash\'s loading bar, left to right\n',
                encoding="utf-8")
    finally:
        g.update(default)


def icon_packs() -> None:
    """theme/icon-packs/<id>/: other icons for the tools, laid over the theme's by `helix theme`."""
    out = HERE / "icon-packs" / "badges"
    shutil.rmtree(out, ignore_errors=True)
    manifest = tomllib.loads((HERE.parent / "tools.toml").read_text(encoding="utf-8"))
    for t in manifest.get("tool", []):
        if t.get("kind") == "iso":
            badge(t, out, col=(186, 171, 211))       # neutral, so it suits every preset
    (out / "pack.toml").write_text('title = "Letter badges"\n'
                                   'description = "Two-letter badges in place of the tools\' logos."\n',
                                   encoding="utf-8")


def fit_icons() -> None:
    """Shrink your own icons in byo/icons/ to ICON x ICON, the size Ventoy shows them. Large
    ones also use up the boot loader's memory at boot, so the icons after them don't appear.
    Each original is kept, once, in byo/icons/originals/ (which refresh doesn't copy)."""
    mine = HERE.parent / "byo" / "icons"
    keep = mine / "originals"
    for f in sorted(mine.glob("*.png")):
        with Image.open(f) as im:
            if im.size == (ICON, ICON):
                continue
            size, im = im.size, im.convert("RGBA")
        keep.mkdir(exist_ok=True)
        if not (keep / f.name).exists():
            shutil.copy2(f, keep / f.name)
        im = ImageOps.contain(im, (ICON, ICON), Image.Resampling.LANCZOS)   # whole picture, centred
        out = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
        out.alpha_composite(im, ((ICON - im.width) // 2, (ICON - im.height) // 2))
        out.save(f, optimize=True)
        print(f"byo/icons/{f.name}: {size[0]}x{size[1]} -> {ICON}x{ICON} (original in byo/icons/originals/)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local", action="store_true", help="only generate missing local-tool badges")
    ap.add_argument("--fit-icons", action="store_true",
                    help=f"shrink your icons in byo/icons/ to {ICON}x{ICON}, keeping the originals")
    ap.add_argument("--skip-fonts", action="store_true", help="reuse the committed, unchanged GRUB fonts")
    args = ap.parse_args()
    if args.local:  # only your local.toml tools; the theme itself is untouched
        local_badges()
        sys.exit(0)
    if args.fit_icons:  # only byo/icons/; the theme itself is untouched
        fit_icons()
        sys.exit(0)
    if not args.skip_fonts and not shutil.which("grub-mkfont"):
        sys.exit("grub-mkfont not found — install grub or use --skip-fonts to reuse committed fonts")
    if args.skip_fonts and not all((HERE / "fonts" / name).is_file() for name in
                                  ("dejavu-16.pf2", "dejavu-22.pf2", "dejavu-bold-22.pf2")):
        sys.exit("committed fonts are missing — run without --skip-fonts after installing grub")
    themed()
    presets()
    imported()
    icon_packs()
    if not args.skip_fonts:
        fonts()
    print(f"theme written to {HERE}")
