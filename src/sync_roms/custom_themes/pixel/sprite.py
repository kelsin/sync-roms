"""Tiny pixel-sprite toolkit: draw on a grid with named colors, then render with an outline and bevel shading.

Rules that keep lines clean: draw one half and `mirror()` it, use `rrect`/`ellipse`/`line` (regular steps),
never hand-place single odd pixels on an outline. `render` adds the 1px outline and the light/dark edges.
"""
from PIL import Image

INK = "#1b1530"  # outline

COLORS = {
    "white": "#f6f3ff", "cream": "#f1e4c3", "gray": "#a9abc4", "dgray": "#62647f", "dark": "#2b2742",
    "red": "#ee4b3f", "orange": "#f7992a", "yellow": "#ffd43f", "green": "#4fc65d", "lime": "#a8e04a",
    "teal": "#2fc5b6", "cyan": "#43c8f0", "blue": "#3d83e8", "indigo": "#5b50d8", "purple": "#a66be2",
    "pink": "#ff7fb8", "brown": "#8c5b3c", "tan": "#d9b080", "screen": "#bfe9a6", "sky": "#8fd4ff",
    "black": "#17141f", "maroon": "#a3303f", "magenta": "#c2308f", "periwinkle": "#8b9bd6",
    "navy": "#2d3a6b", "forest": "#2f6b34",
}
# colors drawn flat (no bevel): small details
FLAT = {"white", "dark", "black", "screen", "sky", "cream"}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def light(c):
    return _mix(c, (255, 255, 255), 0.38)


def dark(c):
    return _mix(c, (0, 0, 0), 0.34)


class Sprite:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.g = [[None] * w for _ in range(h)]

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c)

    def rrect(self, x, y, w, h, c, r=1):
        """Rectangle with corners cut diagonally r pixels (a 1:1 step, so lines stay regular)."""
        for yy in range(h):
            for xx in range(w):
                dx = min(xx, w - 1 - xx)
                dy = min(yy, h - 1 - yy)
                if dx + dy < r:
                    continue
                self.px(x + xx, y + yy, c)

    def ellipse(self, cx, cy, rx, ry, c):
        """Filled ellipse centered at (cx, cy) in pixel-center coordinates (use .5 for even sizes)."""
        for y in range(self.h):
            for x in range(self.w):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    self.px(x, y, c)

    def line(self, x0, y0, x1, y1, c):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.px(x0, y0, c)
            if (x0, y0) == (x1, y1):
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def art(self, x, y, rows, legend):
        """Stamp ASCII rows: legend maps a character to a color name; '.' and ' ' are skipped."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch in ". ":
                    continue
                self.px(x + i, y + j, legend[ch])

    def mirror(self):
        """Copy the left half onto the right half (width must be even)."""
        for y in range(self.h):
            for x in range(self.w // 2):
                if self.g[y][x] is not None:
                    self.g[y][self.w - 1 - x] = self.g[y][x]

    def bounds(self):
        xs = [x for y in range(self.h) for x in range(self.w) if self.g[y][x]]
        ys = [y for y in range(self.h) for x in range(self.w) if self.g[y][x]]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _color(name, palette):
    return _rgb(palette.get(name) or COLORS[name])


def render(sprite, scale=4, state="sel", palette=None):
    """RGBA image: the sprite with a 1px outline and bevel (light top edge, dark bottom edge), scaled up.
    state 'n' (unselected) dims and desaturates every color."""
    palette = palette or {}
    w, h = sprite.w, sprite.h
    pad = 1
    out = [[None] * (w + 2 * pad) for _ in range(h + 2 * pad)]

    def at(x, y):
        return sprite.g[y][x] if 0 <= x < w and 0 <= y < h else None

    for y in range(-pad, h + pad):
        for x in range(-pad, w + pad):
            c = at(x, y)
            if c is None:
                if any(at(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    out[y + pad][x + pad] = _rgb(INK)
                continue
            rgb = _color(c, palette)
            if c not in FLAT:
                if at(x, y - 1) is None:
                    rgb = light(rgb)
                elif at(x, y + 1) is None:
                    rgb = dark(rgb)
            out[y + pad][x + pad] = rgb
    img = Image.new("RGBA", (len(out[0]), len(out)), (0, 0, 0, 0))
    for y, row in enumerate(out):
        for x, rgb in enumerate(row):
            if rgb:
                if state == "n":
                    gray = round(sum(rgb) / 3)
                    rgb = tuple(round((v * 0.5 + gray * 0.5) * 0.62) for v in rgb)
                img.putpixel((x, y), rgb + (255,))
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def place(img, size, center):
    """Paste img onto a transparent canvas of `size` with its middle at `center`."""
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(img, (round(center[0] - img.width / 2), round(center[1] - img.height / 2)), img)
    return canvas
