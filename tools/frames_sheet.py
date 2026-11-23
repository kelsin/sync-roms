#!/usr/bin/env python3
"""Contact sheet of the pixel-art frames, for review (a developer tool; nothing here ships).

Builds a theme from the base with the real build_theme in a throwaway folder, once per palette, and tiles every
registered frame found in the chosen skin folder with its name over black: files over WIDE px wide or tall at 1x
(the full-screen backgrounds, bars and animation strips), the rest enlarged by --scale. --only limits the sheet to
one group of frames, by the module that draws them (select: frames_select, panels: frames_panels, keys: frames_keys).

    uv run python tools/frames_sheet.py --base DIR --palette Gruvbox --palette Mint --out sheet.png
        [--folder skin_1280x720] [--scale 2] [--only select|panels|keys]
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

GAP, LABEL, WIDTH, WIDE = 16, 14, 1400, 300
GROUPS = ("select", "panels", "keys")


def section(theme, folder, title, scale, only=None):
    """One palette's frames, shelf-packed under a title."""
    tiles = []
    for name in sorted(frame_files(only)):
        path = os.path.join(theme, folder, name)
        if os.path.exists(path):
            with Image.open(path) as im:
                img = im.convert("RGBA")
            factor = 1 if max(img.size) > WIDE else scale
            tiles.append((name, img.resize((img.width * factor, img.height * factor), Image.NEAREST)))
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


def frame_files(only=None):
    """The registered frames' file names, those of one group (`frames_<only>` draws them) with `only`."""
    return {key.split("/", 1)[1] for key, spec in frames.FRAMES.items()
            if only is None or spec.draw.__module__.rsplit(".", 1)[-1] == f"frames_{only}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the base theme folder (read only)")
    parser.add_argument("--palette", action="append", required=True, choices=palettes.names())
    parser.add_argument("--out", required=True)
    parser.add_argument("--folder", default="skin", help="the skin folder to show (default skin)")
    parser.add_argument("--scale", type=int, default=2, help=f"enlargement of files up to {WIDE} px wide and tall (default 2)")
    parser.add_argument("--only", choices=GROUPS, help="only this group of frames")
    args = parser.parse_args(argv)
    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in args.palette:
            theme = build_theme(args.base, tmp, name, "CONSOLES", palettes.get(name))
            parts.append(section(theme, args.folder, f"{name}  ({args.folder})", args.scale, args.only))
    sheet = Image.new("RGBA", (max(p.width for p in parts), sum(p.height for p in parts)), (0, 0, 0, 255))
    y = 0
    for part in parts:
        sheet.paste(part, (0, y))
        y += part.height
    sheet.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
