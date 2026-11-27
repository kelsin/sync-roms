#!/usr/bin/env python3
"""Contact sheet of the Pixel sprites of ES-DE systems, for review (a developer tool; nothing here ships).

A row per ES-DE system name: its Consoles and Controllers sprite, each selected then unselected, rendered as the
theme draws them and enlarged 2x, on black. A last row shows eight existing sprites at the same scale to judge
size and style against. Names without a drawing yet are labelled "pending". See docs/pixel-sprites.md.

    uv run python tools/esde_sprite_sheet.py [--out PATH] NAME...
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sync_roms import store  # noqa: E402
from sync_roms.custom_themes.esde import systems  # noqa: E402
from sync_roms.custom_themes.pixel.sprite import render  # noqa: E402

REFERENCE = ["gb", "snes", "genesis", "psx", "n64", "dreamcast", "neogeo", "psp"]  # gb sfc md ps n64 dc neogeo psp
SCALE, ZOOM = 4, 2
CELL = 36 * SCALE * ZOOM  # 30 px sprites plus outline, with room
LABEL = 20
ROW = CELL + LABEL
FONT = os.path.join(os.path.dirname(__file__), "..", "src", "sync_roms", "data", "themes", "fusion-pixel",
                    "fusion-pixel-12px-proportional-ja.ttf")
COLUMNS = [("CONSOLES", "sel"), ("CONSOLES", "n"), ("CONTROLLERS", "sel"), ("CONTROLLERS", "n")]


def tile(draw, state):
    img = render(draw(), SCALE, state)
    return img.resize((img.width * ZOOM, img.height * ZOOM), Image.NEAREST)


def paste(out, img, col, top):
    out.alpha_composite(img, (col * CELL + (CELL - img.width) // 2, top + LABEL + (CELL - img.height) // 2))


def sheet(names):
    """RGBA sheet: a row per name, then the reference row."""
    font = ImageFont.truetype(FONT, 12)
    consoles, controllers = systems.sprites("CONSOLES"), systems.sprites("CONTROLLERS")
    width = max(len(COLUMNS), len(REFERENCE)) * CELL
    out = Image.new("RGBA", (width, (len(names) + 1) * ROW), (0, 0, 0, 255))
    draw = ImageDraw.Draw(out)
    for row, name in enumerate(names):
        top = row * ROW
        if name not in consoles:
            draw.text((4, top + 2), f"{name}: pending (no drawing yet)", fill=(255, 120, 120), font=font)
            continue
        draw.text((4, top + 2), f"{name}   consoles sel, n   controllers sel, n", fill=(255, 255, 255), font=font)
        for col, (kind, state) in enumerate(COLUMNS):
            paste(out, tile((consoles if kind == "CONSOLES" else controllers)[name], state), col, top)
    top = len(names) * ROW
    draw.text((4, top + 2), "reference: " + " ".join(REFERENCE), fill=(160, 160, 160), font=font)
    for col, name in enumerate(REFERENCE):
        paste(out, tile(consoles[name], "sel"), col, top)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="+", metavar="NAME", help="ES-DE system names")
    parser.add_argument("--out", default=os.path.join(store.cache_dir(), "themes", "esde-sprites.png"))
    args = parser.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet(args.names).save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
