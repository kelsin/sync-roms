#!/usr/bin/env python3
"""Make the SpruceOS collection art, src/sync_roms/data/themes/art-book-next/art-spruce/<id>.png (needs Pillow).

PyUI shows a collection's picture in a square-ish box, so each 300x300 image is a fixed square cut from the part of the
theme's slanted band (art/<id>.png) that holds the drawing (every drawing sits in y 635..996, x 38..384), scaled
0.78 without distortion. Outside the band it stays transparent; the band's right edge cuts the drawing as before.

    uv run python tools/gen_spruce_art.py [id ...]     # all of them, or just the ids given
"""
import json
import os
import sys

from PIL import Image

THEME = os.path.join(os.path.dirname(__file__), "..", "src", "sync_roms", "data", "themes", "art-book-next")
CROP = (6, 624, 390, 1008)  # the 384px square of the band around the drawings
SIZE = 300


def ids():
    with open(os.path.join(THEME, "art.json"), encoding="utf-8") as f:
        return sorted({"surprise", *json.load(f)})


def convert(art_id):
    with Image.open(os.path.join(THEME, "art", f"{art_id}.png")) as band:
        return band.convert("RGBA").crop(CROP).resize((SIZE, SIZE), Image.LANCZOS)


def main(wanted):
    out = os.path.join(THEME, "art-spruce")
    os.makedirs(out, exist_ok=True)
    for art_id in wanted or ids():
        convert(art_id).save(os.path.join(out, f"{art_id}.png"), optimize=True)
        print(art_id)


if __name__ == "__main__":
    main(sys.argv[1:])
