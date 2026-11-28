"""PUT2 theme templates: an image whose pixels are palette recipes, so one file serves every palette (format:
docs/theme-options-format.md). `render` is stdlib only: it is the reference the device's code mirrors."""
import struct
import zlib

MAGIC = b"PUT2"
ROLE_IDS = ("text", "list", "selected", "accent", "dim", "bar")  # manifest.colors.roles order (recipe.ROLES)
HEADER, ENTRY = struct.Struct("<4H"), struct.Struct("<BBHBHBBB")  # entry: alpha, kind, src, target, t, r, g, b
TARGET_NONE, TARGET_WHITE, TARGET_BLACK, TARGET_FIXED = range(4)
WHITE, BLACK = (255, 255, 255), (0, 0, 0)


def _target(target):
    if target is None:
        return TARGET_NONE, (0, 0, 0)
    target = tuple(target)
    return {WHITE: TARGET_WHITE, BLACK: TARGET_BLACK}.get(target, TARGET_FIXED), target


class _Table:
    def __init__(self):
        self.entries, self.index = [], {}

    def add(self, entry):
        if entry not in self.index:
            self.index[entry] = len(self.entries)
            self.entries.append(entry)
        return self.index[entry]

    def recipe(self, r, alpha):
        """Index of the entry for recipe `r` at `alpha`; its nested sources are added first."""
        from .pixel import recipe
        t = round(r.t * 1000)
        if abs(r.t * 1000 - t) > 1e-9 or not 0 <= t <= 65535:
            raise ValueError(f"mix amount {r.t} isn't a whole number of thousandths in 0..65.535")
        if isinstance(r.src, recipe.Recipe):
            src = self.recipe(r.src, 255)
            code, rgb = _target(r.target)
            return self.add((alpha, 2, src, code, t, *rgb))
        if isinstance(r.src, str):
            code, rgb = _target(r.target)
            return self.add((alpha, 1, recipe.ROLES.index(r.src), code, t, *rgb))
        if r.target is None:
            return self.add((alpha, 0, 0, 0, 0, *r.src))
        src = self.add((255, 0, 0, 0, 0, *r.src))
        code, rgb = _target(r.target)
        return self.add((alpha, 2, src, code, t, *rgb))


def encode(width, height, pixels):
    """A template of `width` x `height` from row-major `pixels`: an RGBA tuple, or (Recipe, alpha)."""
    from .pixel.recipe import Recipe
    table, idx = _Table(), []
    for px in pixels:
        if len(px) == 2 and isinstance(px[0], Recipe):
            idx.append(table.recipe(*px))
        else:
            r, g, b, a = px
            idx.append(table.add((a, 0, 0, 0, 0, r, g, b)))
    wide = len(table.entries) > 256
    head = MAGIC + HEADER.pack(width, height, len(table.entries), 1 if wide else 0)
    body = struct.pack(f"<{len(idx)}{'H' if wide else 'B'}", *idx)
    return head + b"".join(ENTRY.pack(*e) for e in table.entries) + zlib.compress(body, 9)


def decode(data):
    """(width, height, entries, indexes): entries are tuples of the ENTRY fields, indexes one per pixel.
    ValueError when the data isn't a PUT2 template or is truncated or corrupt."""
    if data[:4] != MAGIC:
        raise ValueError("not a PUT2 template")
    try:
        width, height, count, flags = HEADER.unpack_from(data, 4)
        pos = 4 + HEADER.size
        entries = [ENTRY.unpack_from(data, pos + i * ENTRY.size) for i in range(count)]
        raw = zlib.decompress(data[pos + count * ENTRY.size:])
        wide = flags & 1
        n = width * height
        return width, height, entries, struct.unpack(f"<{n}{'H' if wide else 'B'}", raw[:n * (2 if wide else 1)])
    except (struct.error, zlib.error) as e:
        raise ValueError(f"truncated or corrupt PUT2 template: {e}") from e


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render(data, colors):
    """(width, height, RGBA bytes) of the template with `colors` ({role id: "#RRGGBB"})."""
    width, height, entries, indexes = decode(data)
    rgb = []
    for alpha, kind, src, target, t, r, g, b in entries:
        if kind == 0:
            rgb.append((r, g, b))
            continue
        if kind == 1:
            c = colors[ROLE_IDS[src]].lstrip("#")
            base = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        else:
            base = rgb[src]
        goal = {TARGET_WHITE: WHITE, TARGET_BLACK: BLACK, TARGET_FIXED: (r, g, b)}.get(target)
        rgb.append(base if goal is None else _mix(base, goal, t / 1000))
    out = bytearray()
    for i in indexes:
        out += bytes(rgb[i]) + bytes((entries[i][0],))
    return width, height, bytes(out)


def from_canvas(canvas):
    """The template of what `canvas.image()` draws (cells as recipes where they are recipes)."""
    from .pixel.recipe import Recipe
    w, h = canvas.size

    def px(color):
        return (color, 255) if isinstance(color, Recipe) else (*color, 255)

    grid = [(0, 0, 0, 0)] * (w * h)
    if canvas.background is not None:
        x0, y0, x1, y1 = canvas.box
        for y in range(y0, y1):
            for x in range(x0, x1):
                grid[y * w + x] = px(canvas.background)
    c = canvas.cell
    for (cx, cy), color in sorted(canvas.cells.items()):
        for y in range(canvas.oy + cy * c, canvas.oy + cy * c + c):
            for x in range(canvas.ox + cx * c, canvas.ox + cx * c + c):
                grid[y * w + x] = px(color)
    return encode(w, h, grid)


def from_bar_image(path):
    """The template of the PNG at `path` with its bar-gray pixels as the bar role, None when it has none."""
    from PIL import Image
    from .pixel.recipe import Recipe
    from .pixel.recolor import BAR_GRAY
    with Image.open(path) as im:
        img = im.convert("RGBA")
    raw = img.tobytes()
    pixels, found = [], False
    for r, g, b, a in zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4]):
        if (r, g, b) == BAR_GRAY:
            found = True
            pixels.append((Recipe("bar"), a))
        else:
            pixels.append((r, g, b, a))
    return encode(*img.size, pixels) if found else None
