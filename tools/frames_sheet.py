#!/usr/bin/env python3
"""Contact sheet of the pixel-art frames, for review (a developer tool; nothing here ships).

Builds a theme from the base with the real build_theme in a throwaway folder, once per palette, and tiles every
registered frame found in the chosen skin folder with its name, enlarged, over black.

    uv run python tools/frames_sheet.py --base DIR --palette Gruvbox --palette Mint --out sheet.png
        [--folder skin_1280x720] [--scale 2]
"""
import argparse
import os
import sys
import tempfile

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import frames  # noqa: E402
from sync_roms.custom_themes.pixel.build import build_theme  # noqa: E402

GAP, LABEL, WIDTH = 16, 14, 1400


def section(theme, folder, title, scale):
    """One palette's frames, shelf-packed under a title."""
    tiles = []
    for name in sorted(frame_files()):
        path = os.path.join(theme, folder, name)
        if os.path.exists(path):
            with Image.open(path) as im:
                img = im.convert("RGBA")
            tiles.append((name, img.resize((img.width * scale, img.height * scale), Image.NEAREST)))
    width = max([WIDTH] + [t.width + 2 * GAP for _, t in tiles])
    places, x, y, shelf = [], GAP, GAP + LABEL + GAP, 0
    for name, tile in tiles:
        if x + tile.width + GAP > width:
            x, y, shelf = GAP, y + shelf + GAP, 0
        places.append((name, tile, x, y))
        x += tile.width + GAP
        shelf = max(shelf, tile.height + LABEL)
    out = Image.new("RGBA", (width, y + shelf + GAP), (0, 0, 0, 255))
    draw = ImageDraw.Draw(out)
    draw.text((GAP, GAP), title, fill=(255, 255, 255))
    for name, tile, x, y in places:
        draw.text((x, y), name, fill=(160, 160, 160))
        out.alpha_composite(tile, (x, y + LABEL))
    return out


def frame_files():
    return {key.split("/", 1)[1] for key in frames.FRAMES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the base theme folder (read only)")
    parser.add_argument("--palette", action="append", required=True, choices=palettes.names())
    parser.add_argument("--out", required=True)
    parser.add_argument("--folder", default="skin", help="the skin folder to show (default skin)")
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args(argv)
    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in args.palette:
            theme = build_theme(args.base, tmp, name, "CONSOLES", palettes.get(name))
            parts.append(section(theme, args.folder, f"{name}  ({args.folder})", args.scale))
    sheet = Image.new("RGBA", (max(p.width for p in parts), sum(p.height for p in parts)), (0, 0, 0, 255))
    y = 0
    for part in parts:
        sheet.paste(part, (0, y))
        y += part.height
    sheet.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
