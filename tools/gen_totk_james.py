"""Make the art of the "ToTK - James" spruce theme from the ToTK base theme and Zelda Wiki's character renders.

Reads the base theme (never writes to it), downloads the four renders into a cache, and writes
src/sync_roms/data/themes/totk-james/: cards/<id>-f.png and -n.png (156x328) and bg-title.png (196x51).
Also writes a review sheet to the cache (never the repo) and prints its path.

uv run python tools/gen_totk_james.py [--base DIR] [--cache DIR]
"""

import argparse
import itertools
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from sync_roms import store  # noqa: E402

BASE = "/Volumes/roms/os/spruceos/themes/ToTK"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "themes", "totk-james")
WIKI = "https://cdn.wikimg.net/en/zeldawiki/images/"
# id: (url, top, height fraction, centre x fraction) of the crop, as fractions of the render's visible bounds
CHARS = {
    "sidon": (WIKI + "5/54/TotK_Sidon_Artwork_2.png", 0.02, 0.50, 0.60),
    "riju": (WIKI + "1/14/TotK_Riju_Artwork_2.png", 0.06, 0.45, 0.50),
    "mineru": (WIKI + "1/10/TotK_Mineru_Artwork.png", 0.02, 0.42, 0.47),
    "rauru": (WIKI + "a/a4/TotK_Rauru_Artwork_2.png", 0.0, 0.80, 0.40),
}
FOCUSED = ("game", "favorite", "recent", "app", "retroarch", "setting")
W, H = 156, 328
WIN_X, WIN_Y, WIN_W, WIN_H = 7, 24, 142, 252
CREAM = (250, 247, 221)
TEXT_COLOR = (255, 229, 153)


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def stitch_background(cards):
    """The swirl every focused card shares: per pixel the first pair of cards that agree, holes filled by mirrors."""
    px = [c.convert("RGB").load() for c in cards]
    bg = [[None] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            for i, j in itertools.combinations(range(len(px)), 2):
                a, b = px[i][x, y], px[j][x, y]
                if max(abs(a[k] - b[k]) for k in range(3)) <= 4:
                    bg[y][x] = a
                    break
    for y in range(H):
        for x in range(W):
            c = bg[y][x]
            if c is not None and (max(c) - min(c) > 25 or max(c) > 120):
                bg[y][x] = None
    shifts = [lambda x, y: (W - 1 - x, y), lambda x, y: (x, H - 1 - y), lambda x, y: (W - 1 - x, H - 1 - y)]
    for dx in (40, -40, 80, -80, 60, -60, 100, -100):
        for dy in (0, 60, -60, 120, -120):
            shifts.append(lambda x, y, dx=dx, dy=dy: ((x - dx) % W, (y - dy) % H))
    for shift in shifts:
        fills = {}
        for y in range(H):
            for x in range(W):
                if bg[y][x] is None:
                    sx, sy = shift(x, y)
                    if bg[sy][sx] is not None:
                        fills[x, y] = bg[sy][sx]
        for (x, y), c in fills.items():
            bg[y][x] = c
    return [[c if c is not None else (14, 14, 14) for c in row] for row in bg]


def frame_mask(cards):
    """Pixels copied from the base card: its transparent corners, and what all focused cards share outside the art."""
    px = [c.convert("RGBA").load() for c in cards]
    mask = set()
    for y in range(H):
        for x in range(W):
            first = px[0][x, y]
            if first[3] < 255:
                mask.add((x, y))
                continue
            if any(p[x, y] != first for p in px[1:]):
                continue
            cream = max(abs(first[k] - CREAM[k]) for k in range(3)) <= 30
            edge = x <= 11 or x >= 144 or y <= 28 or y >= 271
            if cream or edge:
                mask.add((x, y))
    return mask


def fetch(cid, url, cache):
    path = os.path.join(cache, os.path.basename(url))
    if not os.path.isfile(path):
        os.makedirs(cache, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "sync-roms-tools"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def crop_art(path, top, hf, cx):
    with Image.open(path) as im:
        src = im.convert("RGBA")
    src = src.crop(src.getbbox())
    sw, sh = src.size
    ch = hf * sh
    cw = ch * WIN_W / WIN_H
    box = (cx * sw - cw / 2, top * sh, cx * sw + cw / 2, top * sh + ch)
    return src.resize((WIN_W, WIN_H), Image.LANCZOS, box=box)


def make_cards(base, bg, mask, art_path, params):
    focused0 = Image.open(os.path.join(base, "skin", "ic-game-f.png")).convert("RGBA")
    normal0 = Image.open(os.path.join(base, "skin", "ic-game-n.png")).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(crop_art(art_path, *params), (WIN_X, WIN_Y))
    canvas = Image.new("RGBA", (W, H))
    canvas.putdata([bg[y][x] + (255,) for y in range(H) for x in range(W)])
    canvas.alpha_composite(layer)
    cp, fp, np_, lp = canvas.load(), focused0.load(), normal0.load(), layer.load()
    focused = Image.new("RGBA", (W, H))
    normal = Image.new("RGBA", (W, H))
    fo, no = focused.load(), normal.load()
    for y in range(H):
        for x in range(W):
            fo[x, y] = fp[x, y] if (x, y) in mask else cp[x, y]
            alpha = np_[x, y][3]
            if alpha == 0:
                no[x, y] = (255, 255, 255, 0)
                continue
            a = lp[x, y][3] / 255
            g = round(lum(cp[x, y]) * 0.25 * a + min(lum(bg[y][x]) * 1.1, 64) * (1 - a))
            g = max(0, min(255, g))
            no[x, y] = (g, g, g, alpha)
    return focused, normal


def make_title(base):
    orig = Image.open(os.path.join(base, "skin", "bg-title.png")).convert("RGBA")
    title = Image.new("RGBA", orig.size, (0, 0, 0, 255))
    title.paste(orig.crop((7, 0, 33, orig.height)), (7, 0))  # the Triforce, as is
    font_path = os.path.join(base, "HYLIA.TTF")
    chosen = None
    for size in range(10, 60):
        font = ImageFont.truetype(font_path, size)
        mask = Image.new("L", (200, 100), 0)
        ImageDraw.Draw(mask).text((0, 0), "James", font=font, fill=255)
        box = mask.getbbox()
        if box[3] - box[1] >= 24:
            chosen = (font, mask, box)
            break
    font, mask, box = chosen
    # glyph box top-left lands at x 35, y 27 (bottom at 50)
    glyphs = mask.crop(box)
    title.paste(Image.new("RGBA", glyphs.size, TEXT_COLOR + (255,)), (35, 27), glyphs)
    return title


def review_sheet(base, out, path):
    cards = []
    for name in ("game", "favorite", "recent", "app", "retroarch", "setting"):
        cards.append((os.path.join(base, "skin", f"ic-{name}-n.png"), os.path.join(base, "skin", f"ic-{name}-f.png")))
    for cid in CHARS:
        cards.append((os.path.join(out, "cards", f"{cid}-n.png"), os.path.join(out, "cards", f"{cid}-f.png")))
    sheet = Image.new("RGBA", (len(cards) * 2 * W, H + 60), (0, 0, 0, 255))
    for k, (n, f) in enumerate(cards):
        sheet.alpha_composite(Image.open(n).convert("RGBA"), (2 * k * W, 0))
        sheet.alpha_composite(Image.open(f).convert("RGBA"), ((2 * k + 1) * W, 0))
    sheet.alpha_composite(Image.open(os.path.join(out, "bg-title.png")).convert("RGBA"), (0, H + 5))
    sheet.alpha_composite(Image.open(os.path.join(base, "skin", "bg-title.png")).convert("RGBA"), (200, H + 5))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.LANCZOS).save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=BASE, help="the ToTK base theme folder (read only)")
    ap.add_argument("--cache", default=os.path.join(store.cache_dir(), "theme-art", "totk-james"))
    args = ap.parse_args()
    out = os.path.normpath(OUT)
    focused = [Image.open(os.path.join(args.base, "skin", f"ic-{n}-f.png")).convert("RGBA") for n in FOCUSED]
    bg = stitch_background(focused)
    mask = frame_mask(focused)
    os.makedirs(os.path.join(out, "cards"), exist_ok=True)
    for cid, (url, *params) in CHARS.items():
        f, n = make_cards(args.base, bg, mask, fetch(cid, url, args.cache), params)
        f.save(os.path.join(out, "cards", f"{cid}-f.png"))
        n.save(os.path.join(out, "cards", f"{cid}-n.png"))
    make_title(args.base).convert("RGB").save(os.path.join(out, "bg-title.png"))
    sheet = os.path.join(args.cache, "review.png")
    review_sheet(args.base, out, sheet)
    print(sheet)


if __name__ == "__main__":
    main()
