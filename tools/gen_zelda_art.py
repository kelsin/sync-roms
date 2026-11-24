"""Make the ToTK-style collection art for spruce cards from the outline drawings of gen_theme_art.py.

Each card is a gold glowing line drawing on a dark Zonai-swirl background with a cream frame,
a divider with a small Triforce and the art's title in the ToTK theme's HYLIA font. Reads the
font from the base theme (never writes to it) and writes
src/sync_roms/data/themes/totk-james/collections/Imgs|Imgs_med|Imgs_small/<id>.png.
With --sheet, also writes a contact sheet to the cache (never the repo) and prints its path.

uv run python tools/gen_zelda_art.py [--base DIR] [--sheet] [id ...]
"""

import argparse
import json
import math
import os
import random
import sys
import zlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(TOOLS, "..", "src"))
sys.path.insert(0, TOOLS)
import gen_theme_art as g  # noqa: E402
from sync_roms import store  # noqa: E402

BASE = "/Volumes/roms/os/spruceos/themes/ToTK"
OUT = os.path.join(store.REPO_DATA, "themes", "totk-james", "collections")
with open(os.path.join(store.REPO_DATA, "themes", "art-book-next", "art.json"), encoding="utf-8") as f:
    NAMES = {**json.load(f), "surprise": "Surprise"}
W, H = 336, 480
SIZES = {"Imgs": (336, 480), "Imgs_med": (210, 300), "Imgs_small": (140, 200)}
CREAM = (250, 247, 221)
GOLD = (255, 229, 153)
MIN_TITLE = 20  # px: a title that would be smaller goes on two lines
TWO_LINE_SIZE = 28


def lines(art_id, cx, cy, unit, stroke):
    """The drawing as an L mask (W x H), centred at cx, cy."""
    draw = g.ART[art_id][0]
    pen = g.Pen()
    draw(pen)
    pts_all = [q for pts, *_ in pen.strokes for q in pts]
    xs, ys = [q[0] for q in pts_all], [q[1] for q in pts_all]
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    u = unit * 95 / max(span, 60)

    def place(pts):
        return [(cx + (x - mx) * u, cy + (y - my) * u) for x, y in pts]

    strokes = [(place(p), c, o, cl and place(cl)) for p, c, o, cl in pen.strokes]
    g.W, g.H, g.STROKE = W, H, stroke
    return g._ink(strokes, random.Random(zlib.crc32(art_id.encode())))


def swirls(seed, bright, dim):
    """Zonai-style clusters of concentric rings, like the theme's background."""
    rng = random.Random(seed)
    img = Image.new("RGB", (W * 2, H * 2), (8, 8, 8))
    d = ImageDraw.Draw(img)
    for _ in range(26):
        x, y, R = rng.uniform(-60, W * 2 + 60), rng.uniform(-60, H * 2 + 60), rng.uniform(50, 150)
        r = R
        while r > 6:
            d.ellipse((x - r, y - r, x + r, y + r), fill=(8, 8, 8), outline=bright if rng.random() < 0.5 else dim, width=4)
            r -= 15
    return img.resize((W, H), Image.LANCZOS)


def glow(mask, colour, radius, strength):
    layer = Image.new("RGB", (W, H), colour)
    blur = mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * strength)))
    return layer, blur


def fit(d, text, font_path, size, smallest=13):
    """The largest font from size down at which text fits between the frame's sides, or None."""
    for s in range(size, smallest - 1, -1):
        font = ImageFont.truetype(font_path, s)
        if d.textlength(text, font=font) <= W - 44:
            return font
    return None


def title(img, text, colour, y, font_path, size=34):
    """One line, shrunk to fit; two lines, split where they are most even, if one would be under MIN_TITLE px."""
    d = ImageDraw.Draw(img)
    font = fit(d, text, font_path, size, MIN_TITLE)
    rows = [text]
    if font is None:
        words = text.split()
        splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
        big = ImageFont.truetype(font_path, TWO_LINE_SIZE)
        rows = list(min(splits, key=lambda r: abs(d.textlength(r[0], font=big) - d.textlength(r[1], font=big))))
        font = min((fit(d, r, font_path, TWO_LINE_SIZE) for r in rows), key=lambda f: f.size)
        y -= font.size // 2
    for i, row in enumerate(rows):
        tw = d.textlength(row, font=font)
        ry = y + i * (font.size + 4)
        d.text(((W - tw) / 2 + 1, ry + 2), row, font=font, fill=(0, 0, 0))
        d.text(((W - tw) / 2, ry), row, font=font, fill=colour)


def triforce(d, cx, cy, s, colour):
    h = s * math.sqrt(3) / 2
    for ox, oy in ((0, -h / 2), (-s / 2, h / 2), (s / 2, h / 2)):
        x, y = cx + ox, cy + oy
        d.polygon([(x, y - h / 2), (x - s / 2, y + h / 2), (x + s / 2, y + h / 2)], fill=colour)


def divider(img, y, colour):
    d = ImageDraw.Draw(img)
    d.line((40, y, W / 2 - 22, y), fill=colour, width=2)
    d.line((W / 2 + 22, y, W - 40, y), fill=colour, width=2)
    triforce(d, W / 2, y, 11, colour)


def frame(img, colour, r=18, inset=8, width=3):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((inset, inset, W - 1 - inset, H - 1 - inset), r, outline=colour, width=width)


def corner_mask(r=22):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, W - 1, H - 1), r, fill=255)
    return m


def render(art_id, font_path):
    """The card of art_id with its title, RGBA W x H."""
    img = swirls(zlib.crc32(art_id.encode()), (44, 44, 40), (28, 28, 26))
    ink = lines(art_id, W / 2, 200, 2.6, 7.0)
    layer, blur = glow(ink, (255, 200, 90), 9, 0.9)
    img.paste(layer, mask=blur)
    img.paste(Image.new("RGB", (W, H), GOLD), mask=ink)
    frame(img, CREAM)
    divider(img, 370, GOLD)
    title(img, NAMES[art_id], CREAM, 392, font_path)
    img.putalpha(corner_mask())
    return img


def sizes(img):
    return {size: img if dims == img.size else img.resize(dims, Image.LANCZOS) for size, dims in SIZES.items()}


def contact_sheet(cards, path, cols=8, pad=12):
    rows = math.ceil(len(cards) / cols)
    sheet = Image.new("RGB", (pad + cols * (W + pad), pad + rows * (H + pad)), (60, 60, 60))
    for i, card in enumerate(cards):
        sheet.paste(card, (pad + i % cols * (W + pad), pad + i // cols * (H + pad)), card)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=BASE, help="the ToTK base theme folder (read only)")
    ap.add_argument("--sheet", action="store_true", help="also write a contact sheet to the cache")
    ap.add_argument("ids", nargs="*", help="art ids (default: every drawing)")
    args = ap.parse_args()
    font_path = os.path.join(args.base, "HYLIA.TTF")
    cards = []
    for art_id in args.ids or list(g.ART):
        card = render(art_id, font_path)
        for size, im in sizes(card).items():
            os.makedirs(os.path.join(OUT, size), exist_ok=True)
            im.save(os.path.join(OUT, size, f"{art_id}.png"), optimize=True)
        cards.append(card)
    if args.sheet:
        path = os.path.join(store.cache_dir(), "theme-art", "zelda", "sheet.png")
        contact_sheet(cards, path)
        print(path)


if __name__ == "__main__":
    main()
