#!/usr/bin/env python3
r"""Make a PortableApps.com Platform theme from a piece of artwork.

    portableapps/make-theme.py ART.png "Theme Name" --slot Retro --accent 1ec8e6 [--hue -25]

The Platform draws its menu at a fixed 406x558 and lays its controls over the
theme's chrome.png: the app list in the panel at x 10-261, y 51-522, the folder
buttons to its right, the drive-space bar underneath. Artwork drawn with a
matching panel (at any size) is found, scaled and cropped so that panel lands
exactly there, then the panel is darkened a little so white text stays legible.

A theme is just chrome.png, preview.png, a tinted drive-space bar and
PATheme.ini (colours, from the Platform's Default theme in helix's cache);
buttons and icons come from the Platform's shared graphics, as for its own
themes. It's written to portableapps/themes/<slot>/, which tools.toml
copies onto every stick.

The Platform's Options > Themes lists only its built-in themes (a custom theme
in its Data\Theme slot works but makes Options fail with "List index out of
bounds"), so each theme takes over a built-in theme's folder, --slot, e.g.
Retro or SmoothDark, and is picked under that name ("Retro Light"). Needs Pillow.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
W, H = 406, 558                       # the Platform's menu, "modern" layout
PANEL = (10, 51, 261, 522)            # app list: left, top, right, bottom (inclusive)
DRIVE_BAR = (10, 527, 261, 549)       # drive space bar under the list
SLOTS = ["Default", "DefaultDark", "Classic", "ClassicDark", "Flat", "FlatDark", "Glassy", "GlassyDark",
         "Modern", "ModernDark", "Retro", "RetroDark", "Smooth", "SmoothDark"]


def base_theme() -> Path:
    """The Platform's untouched Default theme, from helix's cache."""
    caches = [Path.home() / ".cache/helix-boot", Path.home() / ".cache/commander-rescue"]   # the latter: before the rename
    for d in sorted((d for c in caches for d in (c / "portableapps").glob("tree-*")), reverse=True):
        p = d / "PortableApps/PortableApps.com/App/Graphics/Themes/Default"
        if (p / "PATheme.ini").exists():
            return p
    sys.exit("no PortableApps.com Platform in the cache: run ./helix fetch portableapps first")


def edge(line, lo: float, hi: float) -> int:
    """Strongest brightness step in line[lo*n : hi*n]: one side of the art's panel."""
    n = len(line)
    a, b = int(lo * n), int(hi * n)
    steps = [abs(line[i + 1] - line[i]) for i in range(a, b - 1)]
    return a + max(range(len(steps)), key=steps.__getitem__)


def find_panel(art: Image.Image) -> tuple[int, int, int, int]:
    g = art.convert("L").filter(ImageFilter.GaussianBlur(1))
    w, h = g.size
    row = [g.getpixel((x, h // 2)) for x in range(w)]
    col = [g.getpixel((int(w * 0.3), y)) for y in range(h)]
    return edge(row, .005, .1), edge(col, .04, .16), edge(row, .5, .75), edge(col, .84, .96)


def shift_hue(img: Image.Image, degrees: float) -> Image.Image:
    h, s, v = img.convert("HSV").split()
    h = h.point(lambda x: int(x + degrees / 360 * 256) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def chrome(art: Image.Image, clear_bottom: bool = False) -> Image.Image:
    x0, y0, x1, y1 = find_panel(art)
    sx = (PANEL[2] - PANEL[0]) / (x1 - x0)
    sy = (PANEL[3] - PANEL[1]) / (y1 - y0)
    if not (.8 < sx / sy < 1.25):
        sys.exit(f"couldn't find a menu-shaped panel in the artwork (found x {x0}-{x1}, y {y0}-{y1})")
    big = art.resize((round(art.width * sx), round(art.height * sy)), Image.LANCZOS)
    ox, oy = round(x0 * sx) - PANEL[0], round(y0 * sy) - PANEL[1]
    out = Image.new("RGB", (W, H))
    out.paste(big, (-ox, -oy))
    if ox < 0 or oy < 0 or big.width - ox < W or big.height - oy < H:  # art doesn't reach an edge: stretch it
        out = big.crop((max(ox, 0), max(oy, 0), min(ox + W, big.width), min(oy + H, big.height))).resize((W, H))
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).rectangle(PANEL, fill=70)          # ~27% darker behind the app list
    out = Image.composite(Image.new("RGB", (W, H)), out, shade)
    if clear_bottom:  # art with a drive bar or buttons drawn in: the Platform draws the real ones here
        strip = out.crop((0, PANEL[3] + 3, W, H))
        pixels = strip.get_flattened_data() if hasattr(strip, "get_flattened_data") else strip.getdata()
        dark = min(pixels, key=sum)                           # the frame's darkest colour
        edge = 3                                              # keep the frame's outline at the sides
        ImageDraw.Draw(out).rectangle((edge, PANEL[3] + 3, W - 1 - edge, H - 1), fill=dark)
    return out


def tint(src: Path, dst: Path, rgb: tuple[int, int, int]) -> None:
    """Recolour a grey UI image (the drive-space bar) to the accent, keeping its shading."""
    im = Image.open(src).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            k = (r + g + b) / 765
            px[x, y] = (*(min(255, int(c * (.35 + .9 * k))) for c in rgb), a)
    im.save(dst)


def recolour(src: Path, dst: Path, rgb: tuple[int, int, int]) -> None:
    """Give a single-colour icon a new colour, keeping its shape (alpha)."""
    im = Image.open(src).convert("RGBA")
    Image.merge("RGBA", (*Image.new("RGB", im.size, rgb).split(), im.getchannel("A"))).save(dst, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("art", type=Path, help="artwork with the menu's panel drawn in (any size)")
    ap.add_argument("name", help='theme name, e.g. "Helix Teal"')
    ap.add_argument("--accent", default="f5a524", help="hex colour for the drive bar and dividers")
    ap.add_argument("--hue", type=float, default=0, help="rotate the artwork's colours by this many degrees")
    ap.add_argument("--search", choices=("light", "dark"), default="light",
                    help="search box: white with dark text, or dark with light text")
    ap.add_argument("--clear-bottom", action="store_true",
                    help="blank the strip under the app list, for art with a drive bar or buttons drawn in")
    ap.add_argument("--slot", required=True, choices=SLOTS,
                    help="built-in theme folder to take over; it's listed under that name in Options > Themes")
    ap.add_argument("--out", type=Path, default=REPO / "portableapps" / "themes")
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{6}", args.accent):
        sys.exit("--accent is a hex colour like 1ec8e6")
    accent = tuple(int(args.accent[i:i + 2], 16) for i in (0, 2, 4))

    base = base_theme()
    dest = args.out / args.slot
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    art = Image.open(args.art).convert("RGB")
    if args.hue:
        art = shift_hue(art, args.hue)
    menu = chrome(art, args.clear_bottom)
    menu.save(dest / "chrome.png", optimize=True)
    # The Options > Themes preview (the Platform's own placeholder is 406x190)
    thumb = menu.resize((round(W * 190 / H), 190), Image.LANCZOS)
    prev = Image.new("RGB", (406, 190), (24, 24, 24))
    prev.paste(thumb, ((406 - thumb.width) // 2, 0))
    prev.save(dest / "preview.png", optimize=True)
    tint(base / "drive_space_slider.png", dest / "drive_space_slider.png", accent)
    # The folder-button icons (Material Design, CC-BY 4.0: licence alongside), lightened toward
    # the accent. Without them the Platform falls back to its beige ones.
    light = tuple(round(c * .45 + 255 * .55) for c in accent)
    (dest / "menu_icons").mkdir()
    for icon in sorted((base / "menu_icons").glob("*.png")):
        if not icon.stem.endswith("_16"):                         # the _16 ones are PortableApps' own
            recolour(icon, dest / "menu_icons" / icon.name, light)
    shutil.copy2(base / "MaterialIconLicense.txt", dest / "MaterialIconLicense.txt")

    # Light text over the dark art; the search box stays white with dark text, as in the mockups
    dim = "".join(f"{int(c * .55):02X}" for c in accent)
    ini = (base / "PATheme.ini").read_text(encoding="utf-8-sig")
    for section, key, value in (("ThemeDetails", "Name", args.name), ("ThemeDetails", "Author", "Helix Boot"),
                                ("ButtonApplications", "FontColor", "FFFFFF"), ("ButtonApplications", "DividerColor", dim),
                                ("ButtonFolders", "FontColor", "FFFFFF"), ("ButtonFolders", "FontColorWhite", "FFFFFF"),
                                ("DriveSpace", "FontColor", "E6EDF3"), ("DriveSpace", "FontShadowColor", "000000"),
                                ("SearchBox", "BorderColor", args.accent.upper())) + (
                               (("SearchBox", "BackgroundColor", "".join(f"{int(c * .12):02X}" for c in accent)),
                                ("SearchBox", "FontColor", "E6F7FA")) if args.search == "dark" else ()):
        block = re.search(rf"^\[{section}\][^\[]*", ini, re.M)
        body = block.group(0)
        new = re.sub(rf"^{key}=[^\r\n]*", f"{key}={value}", body, flags=re.M) if re.search(rf"^{key}=", body, re.M) \
            else body.rstrip("\r\n") + f"\r\n{key}={value}\r\n\r\n"
        ini = ini[:block.start()] + new + ini[block.end():]
    (dest / "PATheme.ini").write_text(ini, encoding="utf-8")
    print(f"{args.name}: {dest}")


if __name__ == "__main__":
    main()
