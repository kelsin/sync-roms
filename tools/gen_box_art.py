"""Draw the retro game box pictures Spruce shows for collections.

Each art id gets a box: its title in a pixel font, its sprite (sprites/<id>.txt) on a sunburst in the id's band colour,
and a badge picked by a stable hash of the id. Boxes are drawn at 84x120 base pixels and written to
art-box/Imgs|Imgs_med|Imgs_small/<id>.png.

uv run python tools/gen_box_art.py [id ...] [--sheet PATH]
"""

import argparse
import hashlib
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from gen_theme_art import ART

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "themes",
                    "art-book-next")
OUT = os.path.join(DATA, "art-box")

W, H = 84, 120
SIZES = {"Imgs": (336, 480), "Imgs_med": (210, 300), "Imgs_small": (140, 200)}
BADGES = ["16-BIT", "16 MEG", "1-2 PLAYERS", "1-4 PLAYERS", "BATTERY BACKUP", "STEREO SOUND", "HI-SCORE", "TURBO",
          "NEW!", "ARCADE HIT", "PASSWORD SAVE", "COLLECTOR'S"]

DARK = (0x14, 0x12, 0x1C)        # title band and footer
OUTLINE = (0x0C, 0x0A, 0x10)     # box outline
SHADOW = (0x18, 0x10, 0x20)      # text drop shadow
WHITE, GOLD = (0xFF, 0xFF, 0xFF), (0xFA, 0xD0, 0x48)
BADGE_WHITE = (0xEC, 0xF0, 0xF8)
TEXT_X, TEXT_Y, LINE = 9, 4, 8
FOOTER = 108
BADGE_Y = 111
SPRITE = 64                      # the 32x32 sprite at 2x


def _load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


TITLES = _load("art.json")
FONT = _load("box-font.json")
PALETTE = {k: _rgb(v) for k, v in _load("box-palette.json").items()}


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def ids():
    return sorted({"surprise", *TITLES})


def colour(art_id):
    return ART[art_id][1]


def title(art_id):
    return ("Surprise" if art_id == "surprise" else TITLES[art_id]).upper()


def badge(art_id):
    digest = hashlib.sha256(art_id.encode()).digest()
    c = colour(art_id)
    colours = [BADGE_WHITE, GOLD, tuple((v + 255) // 2 for v in c)]
    return BADGES[digest[0] % len(BADGES)], colours[digest[1] % len(colours)]


def text_width(text):
    return sum(len(FONT[ch][0]) + 1 for ch in text) - 1


def wrap(text, width=72):
    lines = []
    for word in text.split(" "):
        if lines and text_width(lines[-1] + " " + word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    if any(text_width(line) > width for line in lines) or len(lines) > 3:
        raise ValueError(f"{text!r} doesn't fit {width} px in 3 lines")
    return lines


def load_sprite(art_id):
    with open(os.path.join(DATA, "sprites", f"{art_id}.txt")) as f:
        rows = f.read().splitlines()
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                im.putpixel((x, y), PALETTE[ch] + (255,))
    return im


def layout(art_id):
    band = TEXT_Y + LINE * len(wrap(title(art_id))) + 2
    x0, y0, x1, y1 = 7, band + 7, 81, 106
    return {
        "title_band": (0, 0, W - 1, band),
        "picture": (x0, y0, x1, y1),
        "sprite": (x0 + (x1 - x0 + 1 - SPRITE) // 2, y0 + (y1 - y0 + 1 - SPRITE) // 2),
    }


def _text(im, x, y, text, fill):
    for colour_, dx in ((SHADOW, 1), (fill, 0)):
        cx = x
        for ch in text:
            for gy, row in enumerate(FONT[ch]):
                for gx, bit in enumerate(row):
                    if bit == "#":
                        im.putpixel((cx + gx + dx, y + gy + dx), colour_)
            cx += len(FONT[ch][0]) + 1


def _sunburst(c, centre, rays=16):
    im = Image.new("RGB", (W, H), c)
    d = ImageDraw.Draw(im)
    cx, cy = centre
    r = 200
    def point(turn):  # whole pixels, so the platform's trig rounding can't move a ray's edge
        a = 2 * math.pi * turn / rays
        return round(cx + r * math.cos(a)), round(cy + r * math.sin(a))

    cx, cy = round(cx), round(cy)
    for i in range(rays):
        d.polygon([(cx, cy), point(i), point(i + 0.5)], fill=shade(c, 1.18))
    return im


def render(art_id):
    c = colour(art_id)
    lay = layout(art_id)
    band = lay["title_band"][3]
    x0, y0, x1, y1 = lay["picture"]
    sx, sy = lay["sprite"]
    im = Image.new("RGB", (W, H), c)
    im.paste(_sunburst(c, (sx + SPRITE / 2, sy + SPRITE / 2)).crop((x0, y0, x1 + 1, y1 + 1)), (x0, y0))
    d = ImageDraw.Draw(im)
    d.rectangle(lay["title_band"], fill=DARK)
    for i, f in enumerate((0.70, 0.85, 1.00)):
        d.line([(0, band + 1 + 2 * i), (W - 1, band + 1 + 2 * i)], fill=shade(c, f))
    sprite = load_sprite(art_id).resize((SPRITE, SPRITE), Image.NEAREST)
    im.paste(sprite, (sx, sy), sprite)
    d.rectangle([0, FOOTER, W - 1, H - 1], fill=DARK)
    for i, line in enumerate(wrap(title(art_id))):
        _text(im, TEXT_X, TEXT_Y + LINE * i, line, (WHITE, GOLD)[i % 2])
    text, fill = badge(art_id)
    _text(im, W - 4 - text_width(text), BADGE_Y, text, fill)
    d.rectangle([0, 0, 4, H - 1], fill=shade(c, 0.55))
    d.line([(5, 0), (5, H - 1)], fill=shade(c, 1.35))
    d.rectangle([0, 0, W - 1, H - 1], outline=OUTLINE)
    return im


def sizes(art_id):
    full = render(art_id).resize(SIZES["Imgs"], Image.NEAREST)
    return {name: full if name == "Imgs" else full.resize(size, Image.LANCZOS) for name, size in SIZES.items()}


def sheet(art_ids, path, per_row=6):
    cw, ch = SIZES["Imgs"]
    gap, label = 24, 32
    rows = (len(art_ids) + per_row - 1) // per_row
    cols = min(per_row, len(art_ids))
    out = Image.new("RGB", (gap + cols * (cw + gap), gap + rows * (ch + label + gap)), (0x24, 0x26, 0x3A))
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=20)
    for i, art_id in enumerate(art_ids):
        x = gap + (i % per_row) * (cw + gap)
        y = gap + (i // per_row) * (ch + label + gap)
        d.text((x, y), art_id, font=font, fill=(230, 230, 240))
        out.paste(sizes(art_id)["Imgs"], (x, y + label))
    out.save(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw the retro box art for Spruce collections.")
    parser.add_argument("ids", nargs="*", help="art ids (default: all)")
    parser.add_argument("--sheet", help="also write a contact sheet of these boxes here")
    args = parser.parse_args(argv)
    art_ids = args.ids or ids()
    unknown = sorted(set(art_ids) - set(ids()))
    if unknown:
        parser.error(f"unknown art ids: {', '.join(unknown)}")
    for art_id in art_ids:
        for name, im in sizes(art_id).items():
            os.makedirs(os.path.join(OUT, name), exist_ok=True)
            im.save(os.path.join(OUT, name, f"{art_id}.png"))
    if args.sheet:
        sheet(art_ids, args.sheet)


if __name__ == "__main__":
    sys.exit(main())
