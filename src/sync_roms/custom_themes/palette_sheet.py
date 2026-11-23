"""The palette overview image: one small pixel-theme main screen per palette, drawn from the palette data."""
import contextlib
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .. import store

PANEL = (320, 240)
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


def render_panel(palette, font_path=None, caption=None):
    from .pixel import preview
    img = preview.preview_image("CONSOLES", palette, font_path)
    img = img.resize(PANEL, Image.NEAREST)
    d = ImageDraw.Draw(img)
    font, text = _font(font_path, 15), caption or palette.name
    d.rectangle((0, 0, 8 + d.textlength(text, font=font), 24), fill=(0, 0, 0))
    d.text((6, 4), text, font=font, fill=CAPTION)
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
