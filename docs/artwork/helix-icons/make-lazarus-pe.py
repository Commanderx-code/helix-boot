#!/usr/bin/env python3
"""Draw the Lazarus PE icon of the default set: the project's phoenix on a dark glass globe in a
steel ring, to sit with the rest of the glossy set. Writes lazarus-pe.png (128 px) beside this
file, from the phoenix in src/lazarus-phoenix.png. Needs Pillow.

    docs/artwork/helix-icons/make-lazarus-pe.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps
N = 1024
def radial(inner, outer, centre, radius):
    g = Image.new("L", (256, 256))
    px = g.load()
    for y in range(256):
        for x in range(256):
            px[x, y] = max(0, min(255, round(255 * (1 - math.hypot(x / 255 - centre[0], y / 255 - centre[1]) / radius))))
    g = g.resize((N, N), Image.BICUBIC)
    return Image.composite(Image.new("RGB", (N, N), inner), Image.new("RGB", (N, N), outer), g)
def vertical(top, bottom):
    g = Image.linear_gradient("L").resize((N, N))
    return Image.composite(Image.new("RGB", (N, N), bottom), Image.new("RGB", (N, N), top), g)
def disc(inset):
    m = Image.new("L", (N, N), 0)
    ImageDraw.Draw(m).ellipse((inset, inset, N - inset, N - inset), fill=255)
    return m
def make(src, out):
    img = Image.new("RGBA", (N, N))
    glow = Image.new("RGBA", (N, N))
    ImageDraw.Draw(glow).ellipse((36, 44, N - 36, N - 28), fill=(0, 200, 235, 95))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(22)))
    img.paste(vertical((250, 252, 255), (70, 78, 92)), (0, 0), disc(52))            # steel ring, lit from above
    img.paste(vertical((60, 68, 82), (214, 222, 232)), (0, 0), disc(84))            # its inner bevel, the other way
    img.paste(vertical((18, 24, 34), (8, 12, 20)), (0, 0), disc(110))               # a dark lip
    img.paste(radial((0, 96, 124), (2, 10, 28), (0.5, 0.78), 0.62), (0, 0), disc(122))   # glass: glows from below
    ph = Image.open(src).convert("RGBA")
    ph = ImageOps.contain(ph.crop(ph.getchannel("A").getbbox()), (640, 640), Image.LANCZOS)
    r, g, b, a = ph.split()
    lum = ImageOps.autocontrast(Image.merge("RGB", (r, g, b)).convert("L"), cutoff=2).point(lambda v: min(255, int(v * 1.25) + 30))
    bright = Image.composite(Image.new("RGB", ph.size, (240, 255, 255)), Image.new("RGB", ph.size, (0, 190, 215)), lum)
    layer = Image.new("RGBA", (N, N))
    layer.alpha_composite(Image.merge("RGBA", (*bright.split(), a)), ((N - ph.width) // 2, (N - ph.height) // 2 + 18))
    halo = Image.new("RGBA", (N, N))
    halo.paste((0, 225, 255, 255), (0, 0), layer.getchannel("A"))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(30)))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(8)))
    img = Image.alpha_composite(img, layer)
    gloss = Image.new("L", (N, N), 0)                                                # the reflection across the top
    ImageDraw.Draw(gloss).ellipse((150, 96, N - 150, 470), fill=150)
    fade = Image.linear_gradient("L").resize((N, N)).point(lambda v: max(0, 255 - int(v * 2.6)))
    gloss = ImageChops.multiply(ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(6)), fade), disc(122))
    img = Image.alpha_composite(img, Image.merge("RGBA", (*Image.new("RGB", (N, N), (255, 255, 255)).split(), gloss)))
    img.save(out)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    full = here / "lazarus-pe.full.png"
    make(here / "src/lazarus-phoenix.png", full)
    with Image.open(full) as im:
        im = im.convert("RGBA")
        im = ImageOps.contain(im.crop(im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()), (128, 128), Image.LANCZOS)
    im.save(here / "lazarus-pe.png", optimize=True)
    full.unlink()
