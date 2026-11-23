"""The palette overview image: one small mock of a PyUI list screen per palette, drawn from the palette data."""
import contextlib
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .. import store

PANEL = (300, 215)
GAP = 8
BACKGROUND = (28, 28, 28)
CAPTION = (136, 136, 136)


def font_path():
    """The base theme's font when it is in the cache, else None (Pillow's default font)."""
    path = os.path.join(store.cache_dir(), "themes", "base", "SPRUCE", "nunwen.ttf")
    return path if os.path.isfile(path) else None


def _font(path, size):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def render_panel(palette, font_path=None, caption=None):
    img = Image.new("RGB", PANEL, (0, 0, 0))
    d = ImageDraw.Draw(img)
    f15, f18 = _font(font_path, 15), _font(font_path, 18)
    text, listc, selected, accent, dim, bar = (_rgb(c) for c in (
        palette.text, palette.list, palette.selected, palette.accent, palette.dim, palette.bar))
    d.text((8, 4), caption or palette.name, font=f15, fill=CAPTION)
    d.text((8, 24), "Games", font=f18, fill=text)
    d.text((PANEL[0] - 8, 24), "12", font=f18, fill=accent, anchor="ra")
    width = d.textlength("12", font=f18)
    d.text((PANEL[0] - 8 - width, 24), "3/", font=f18, fill=text, anchor="ra")
    for i, name in enumerate(("Super Metroid", "Chrono Trigger", "F-Zero")):
        y = 56 + 30 * i
        if i == 1:
            d.rectangle((0, y, PANEL[0] - 1, y + 27), fill=bar)
        d.text((12, y + 4), name, font=f18, fill=selected if i == 1 else listc)
    for x, label, color in ((12, "GB", text), (70, "SNES", accent), (140, "N64", dim)):
        d.text((x, 150), label, font=f18, fill=color)
    d.text((12, 172), "A  Open   B  Back", font=f15, fill=text)
    for i, color in enumerate((text, listc, selected, accent, dim, bar)):
        x = 8 + 46 * i
        d.rectangle((x, 196, x + 39, 207), fill=color)
    return img


def render_sheet(palettes, font_path=None, columns=5):
    palettes = list(palettes)
    rows = -(-len(palettes) // columns)
    w, h = PANEL
    sheet = Image.new("RGB", (columns * w + (columns + 1) * GAP, rows * h + (rows + 1) * GAP), BACKGROUND)
    for n, palette in enumerate(palettes):
        row, col = divmod(n, columns)
        panel = render_panel(palette, font_path, f"{n + 1}. {palette.name}")
        sheet.paste(panel, (GAP + col * (w + GAP), GAP + row * (h + GAP)))
    return sheet


def save_image(img, path):
    """Save img as a PNG at path (folders made) through a temp file in the same folder, so a failed write leaves the
    old file as it was."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".palettes-", suffix=".png", dir=folder)
    os.close(fd)
    try:
        img.save(tmp, "PNG")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    return path


def write_sheet(path):
    from . import palettes
    return save_image(render_sheet(palettes.PALETTES.values(), font_path()), path)
