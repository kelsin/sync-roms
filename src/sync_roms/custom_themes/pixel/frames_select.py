"""The selection frames: list bars, the outlined short-list box and the grid tiles."""
import os
from functools import lru_cache

from PIL import ImageFont

from .frames import register


def bar(canvas, s):
    """A full-width selection bar, inset one cell at the top and bottom: a flat fill in a light rim the same on all four
    sides (a dark outline or bevel vanishes on the black screen, leaving a lone light line along the top)."""
    canvas.panel(0, 1, canvas.cols, canvas.rows - 2, s.bar, s.bar, s.bar, s.hi)


def row_bar(canvas, s):
    """A list row's selection bar, the file exactly one row tall (see row_height): the bar's flat fill and light rim
    over the row's full height, inset one cell from the screen's sides so the side rims don't sit on its edge."""
    canvas.panel(1, 0, canvas.cols - 2, canvas.rows, s.bar, s.bar, s.bar, s.hi)


@lru_cache(maxsize=None)
def _font_height(size):
    from .build import FONT, FONT_DIR  # build imports frames, which imports this module
    ascent, descent = ImageFont.truetype(os.path.join(FONT_DIR, FONT), size).getmetrics()
    return ascent + descent


def row_height(descriptive):
    """height(screen_w, screen_h) of a PyUI list row with the theme's fonts, as views/list_view.py works it out
    (useTextForLineHeight, on by default): the list font's height plus padding, and for a descriptive row (settings: a
    title and a description) the title offset, title and description. PyUI draws the selection bar from its top
    cropped to the row (ZOOM to screen width x row, or crop_h), so a taller file loses its bottom rim."""
    def height(w, h):
        from .build import FONT_SIZES
        padding = int(10 * h / 480)
        title = _font_height(FONT_SIZES["list"]["size"])
        if not descriptive:
            return title + padding
        offset = int(5 * min(w / 640, h / 480))  # descriptiveListTextOffsetY's default
        return offset + title + _font_height(FONT_SIZES["grid"]["grid3x4"]) + padding  # descriptionFontSize's default
    return height


def outlined_box(canvas, s):
    """A dark box with an accent ring inside the ink outline, the bar's footprint."""
    canvas.panel(0, 1, canvas.cols, canvas.rows - 2, s.accent, s.accent, s.accent, s.ink)
    canvas.panel(1, 2, canvas.cols - 2, canvas.rows - 4, s.dark, s.dark, s.dark, s.accent, cut=1)


def tile(canvas, s):
    """A grid tile filling its footprint."""
    canvas.panel(0, 0, canvas.cols, canvas.rows, s.bar, s.hi, s.sh, s.ink)


register("skin/bg-list-l.png", row_bar, symmetric=True, flush=("top", "bottom"), height=row_height(True))
register("skin/bg-list-s.png", row_bar, symmetric=True, flush=("top", "bottom"), height=row_height(False))
for _name in ("bg-list-s2", "menu-sub-title-bg"):
    register(f"skin/{_name}.png", bar, symmetric=True, flush=("left", "right"))
register("skin/list-item-select-bg-short.png", outlined_box, symmetric=True, flush=("left", "right"))
for _name in ("grid-game-selected", "bg-game-item-f", "bg-grid-s"):
    register(f"skin/{_name}.png", tile, symmetric=True, flush=("left", "right", "top", "bottom"))
