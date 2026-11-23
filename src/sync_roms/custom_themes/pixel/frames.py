"""Pixel-art frames: the base theme's bars, panels and tiles redrawn in a palette's colors on a grid of square cells,
at each skin folder's own file size (drawn natively, never resized).

Margin rules the kit keeps: the artwork stays inside the base image's footprint (its alpha >= 128 box), the leftover
pixels of a footprint that isn't a whole number of cells are split evenly (the extra one right/bottom), and panels have
stepped 1:1 corners identical on all four sides. Drawers work in cells only.
"""
import os
from dataclasses import dataclass, field

from PIL import Image

from .sprite import INK, _rgb


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


@dataclass(frozen=True)
class Shades:
    text: tuple
    list: tuple
    selected: tuple
    accent: tuple
    dim: tuple
    bar: tuple
    hi: tuple
    sh: tuple
    mid: tuple
    dark: tuple
    ink: tuple


def shades(palette):
    """The palette's colors as RGB, with the shades derived from its bar color and the icons' outline ink."""
    bar = _rgb(palette.bar)
    black, white = (0, 0, 0), (255, 255, 255)
    return Shades(text=_rgb(palette.text), list=_rgb(palette.list), selected=_rgb(palette.selected),
                  accent=_rgb(palette.accent), dim=_rgb(palette.dim), bar=bar, hi=_mix(bar, white, .35),
                  sh=_mix(bar, black, .4), mid=_mix(bar, black, .45), dark=_mix(bar, black, .7), ink=_rgb(INK))


SMALL = 64  # base files narrower than this use the small-file cell rule


def cell_for(size, base_size):
    """Cell size in pixels for a file of `size`, from the same file's size in the base skin/ (None: not there)."""
    if base_size is None:
        return 4 if size[0] >= SMALL else 2
    ratio = min(size[0] / base_size[0], size[1] / base_size[1])
    if base_size[0] >= SMALL:
        return max(2, round(4 * ratio))
    return max(1, round(2 * ratio))


def footprint(img):
    """(x0, y0, x1, y1) of the pixels with alpha >= 128; the whole image when it has no alpha; None when all are
    transparent."""
    if img.mode != "RGBA":
        return (0, 0) + img.size
    return img.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()


class Canvas:
    """A grid of square cells laid over the footprint `box` of an image of `size`; leftover pixels split evenly. With a
    `background`, the whole footprint (leftover pixels included) is painted that color under the cells."""

    def __init__(self, size, cell, box, background=None):
        self.size, self.cell, self.box, self.background = size, cell, tuple(box), background
        x0, y0, x1, y1 = box
        self.cols, self.rows = (x1 - x0) // cell, (y1 - y0) // cell
        self.ox = x0 + (x1 - x0 - self.cols * cell) // 2
        self.oy = y0 + (y1 - y0 - self.rows * cell) // 2
        self.cells = {}

    def px(self, cx, cy, rgb):
        if 0 <= cx < self.cols and 0 <= cy < self.rows:
            self.cells[(cx, cy)] = rgb

    def rect(self, cx, cy, cw, ch, rgb):
        for y in range(cy, cy + ch):
            for x in range(cx, cx + cw):
                self.px(x, y, rgb)

    def panel(self, cx, cy, cw, ch, fill, hi, sh, outline, cut=2):
        """A bevelled panel: corners cut `cut` cells in 1:1 steps, a 1-cell `outline`, the light `hi` row under the
        straight top edge, the dark `sh` row over the straight bottom edge, `fill` inside."""
        def inside(x, y):
            if not (0 <= x < cw and 0 <= y < ch):
                return False
            return min(x, cw - 1 - x) + min(y, ch - 1 - y) >= cut

        def edge(x, y):
            return inside(x, y) and not all(inside(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))

        for y in range(ch):
            for x in range(cw):
                if not inside(x, y):
                    continue
                if edge(x, y):
                    color = outline
                elif y == 1:  # straight rows only: the corner steps stay plain fill, no stray bevel cells
                    color = hi
                elif y == ch - 2:
                    color = sh
                else:
                    color = fill
                self.px(cx + x, cy + y, color)

    def hline_dots(self, cx, cy, cw, rgb, on=2, off=1):
        for i in range(cw):
            if i % (on + off) < on:
                self.px(cx + i, cy, rgb)

    def vline_dots(self, cx, cy, ch, rgb, on=2, off=1):
        for i in range(ch):
            if i % (on + off) < on:
                self.px(cx, cy + i, rgb)

    def mirror(self):
        """Copy the left half of the grid onto the right half."""
        for (x, y), rgb in list(self.cells.items()):
            if x < self.cols // 2:
                self.cells[(self.cols - 1 - x, y)] = rgb

    def image(self):
        img = Image.new("RGBA", self.size, (0, 0, 0, 0))
        if self.background is not None:
            img.paste(tuple(self.background) + (255,), self.box)
        c = self.cell
        for (x, y), rgb in sorted(self.cells.items()):
            left, top = self.ox + x * c, self.oy + y * c
            img.paste(tuple(rgb) + (255,), (left, top, left + c, top + c))
        return img


@dataclass
class FrameSpec:
    draw: object  # draw(canvas, shades)
    symmetric: bool = False
    flush: tuple = field(default=())
    background: tuple = None  # painted over the whole footprint first (full-screen backgrounds stay opaque)


FRAMES = {}  # "skin/<file>.png": FrameSpec, drawn in every skin*/ folder that has the file


def register(name, draw, symmetric=False, flush=(), background=None):
    FRAMES[name] = FrameSpec(draw, symmetric, tuple(flush), background)


def apply(theme_dir, palette):
    """Redraw every registered frame present in the theme's skin*/ folders; returns the relative paths written."""
    colors = shades(palette)
    written = []
    for folder in sorted(os.listdir(theme_dir)):
        if not folder.startswith("skin") or not os.path.isdir(os.path.join(theme_dir, folder)):
            continue
        for name, spec in sorted(FRAMES.items()):
            file = name.split("/", 1)[1]
            path = os.path.join(theme_dir, folder, file)
            if not os.path.exists(path):
                continue
            with Image.open(path) as im:
                size, box = im.size, footprint(im.convert("RGBA"))
            if box is None:  # nothing shows in the base: keep it that way
                continue
            canvas = Canvas(size, cell_for(size, _base_size(theme_dir, file)), box, spec.background)
            spec.draw(canvas, colors)
            canvas.image().save(path)
            written.append(f"{folder}/{file}")
    return written


def _base_size(theme_dir, file):
    path = os.path.join(theme_dir, "skin", file)
    if not os.path.exists(path):
        return None
    with Image.open(path) as im:
        return im.size


from . import frames_panels, frames_select  # noqa: E402,F401  (register their frames; they import this module back)
