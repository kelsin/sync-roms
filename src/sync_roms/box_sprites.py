"""The box-art sprites, `data/themes/art-book-next/sprites/<id>.txt`: 32 rows of 32 characters, `.` clear and every other
character a colour of `box-palette.json` (`K` is the outline, drawn in the sprite itself)."""
import functools
import json
import os

from PIL import Image

from . import store

DATA = os.path.join(store.REPO_DATA, "themes", "art-book-next")
SIZE = 32


@functools.cache
def palette():
    with open(os.path.join(DATA, "box-palette.json")) as f:
        return {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in json.load(f).items()}


def load(art_id):
    """The sprite as a 32x32 RGBA image."""
    with open(os.path.join(DATA, "sprites", f"{art_id}.txt")) as f:
        rows = f.read().splitlines()
    colours = palette()
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                im.putpixel((x, y), colours[ch] + (255,))
    return im
