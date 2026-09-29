#!/usr/bin/env python3
"""Render an offline layout preview from the actual theme assets (not a GRUB screenshot)."""
import argparse
import importlib.util
import re
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("theme_build", HERE / "build-theme.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def box(image, prefix, x, y, width, height):
    """Assemble the same nine slices that GRUB stretches around a box."""
    parts = {p: Image.open(HERE / f"{prefix}_{p}.png").convert("RGBA")
             for p in ("nw", "n", "ne", "w", "c", "e", "sw", "s", "se")}
    left, top = parts["nw"].size
    right, bottom = parts["se"].size
    xs, ys = (x, x + left, x + width - right), (y, y + top, y + height - bottom)
    widths, heights = (left, width - left - right, right), (top, height - top - bottom, bottom)
    for row, names in enumerate((("nw", "n", "ne"), ("w", "c", "e"), ("sw", "s", "se"))):
        for col, part in enumerate(names):
            image.alpha_composite(parts[part].resize((widths[col], heights[row])), (xs[col], ys[row]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", default="1920x1080", help="e.g. 1280x720 or 1024x768")
    ap.add_argument("--out", type=Path, default=HERE.parent / "docs/artwork/helix-neon-preview.jpg")
    args = ap.parse_args()
    width, height = (int(v) for v in args.size.split("x"))
    theme = (HERE / "theme.txt").read_text()
    menu = re.search(r"\+ boot_menu \{(.*?)\}", theme, re.S).group(1)
    props = dict(re.findall(r"^\s*(\w+)\s*=\s*([^#\n]+)", menu, re.M))

    def px(key, full):
        v = props[key].strip()
        return round(float(v[:-1]) * full / 100) if v.endswith("%") else int(v)

    x, y, w, h = px("left", width), px("top", height), px("width", width), px("height", height)
    image = Image.open(HERE / "background.png").convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
    box(image, "menu", x, y, w, h)
    regular = ImageFont.truetype(str(build.ttf("DejaVuSans.ttf")), 22)
    bold = ImageFont.truetype(str(build.ttf("DejaVuSans-Bold.ttf")), 22)
    small = ImageFont.truetype(str(build.ttf("DejaVuSans.ttf")), 16)
    manifest = tomllib.loads((HERE.parent / "tools.toml").read_text())
    rows = manifest["category"]
    # Conservative fit: reserve item padding and selection-box edges as well as item height.
    pad = px("item_padding", width)
    row_height = px("item_height", height) + 2 * pad
    step = row_height + px("item_spacing", height)
    visible = min(len(rows), (h - 16) // step)
    for i, row in enumerate(rows[:visible]):
        ry = y + 8 + i * step
        if i == 2:
            box(image, "select", x + 8, ry, w - 24, row_height)
        icon = Image.open(HERE / f"icons/cat-{row['id']}.png").convert("RGBA")
        image.alpha_composite(icon, (x + 22, ry + (row_height - 40) // 2))
        d = ImageDraw.Draw(image)
        title = row["title"]
        font = bold if i == 2 else regular
        available = w - 112
        while d.textlength(title, font=font) > available:
            title = title[:-2].rstrip("…") + "…"
        d.text((x + 78, ry + row_height // 2), title, font=font, fill=build.TEXT, anchor="lm")
    if visible < len(rows):
        d = ImageDraw.Draw(image)
        d.rounded_rectangle((x + w - 12, y + 16, x + w - 7, y + h // 2), 2, fill=build.CYAN)
    d = ImageDraw.Draw(image)
    d.text((width * .05, height * .82), rows[2]["description"], font=small, fill=build.MUTED)
    d.text((width * .05, height * .91), "F1 Help     F2 Browse     F3 Tree View    [sample hotkeys]", font=small, fill=build.MUTED)
    d.text((width * .05, height * .94), "Enter  open      Esc  back", font=small, fill=build.MUTED)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(args.out, optimize=True)
    print(f"{args.out}: {visible}/{len(rows)} category rows visible; offline simulation, not a boot capture")


if __name__ == "__main__":
    main()
