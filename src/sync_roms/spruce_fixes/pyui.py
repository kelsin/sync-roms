"""PyUI's resized copies of a theme: on a screen other than the theme's, PyUI makes `icons_<W>x<H>/` (and reads a
`bg_<W>x<H>/` when there is one) once, then reads only those and never regenerates them, so a fix patches them too."""
import io
import os
import re

from .. import cardfs

VARIANT = re.compile(r"^(bg|icons)_(\d+)x(\d+)$")


def folders(theme, base):
    """theme's `base` folder and its resized copies, as (folder name, (W, H) or None)."""
    found = [(base, None)]
    for name, (is_dir, _) in sorted(cardfs.listing(theme).items()):
        match = VARIANT.match(name)
        if is_dir and match and match[1] == base:
            found.append((name, (int(match[2]), int(match[3]))))
    return found


def scale(theme, size):
    """PyUI's scale for screen size against the theme's skin/background size; 1.0 when that can't be read."""
    from PIL import Image
    for name in ("background.png", "background.qoi"):
        try:
            data = cardfs.read(os.path.join(theme, "skin", name))
        except OSError:
            continue
        try:
            if data[:4] == b"qoif":
                width, height = int.from_bytes(data[4:8], "big"), int.from_bytes(data[8:12], "big")
            else:
                width, height = Image.open(io.BytesIO(data)).size
        except (OSError, ValueError):
            return 1.0
        return min(size[0] / width, size[1] / height) if width and height else 1.0
    return 1.0
