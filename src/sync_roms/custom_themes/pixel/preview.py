"""The 640x480 mock of a pixel theme's main screen in a palette: a status bar, the main menu, a game list and system
icons, drawn from the sprite code (no built theme needed). Text is drawn without anti-aliasing so the palette's exact
colors appear."""
from PIL import Image, ImageDraw

from . import menu, ui_status
from .sprite import render

SIZE = (640, 480)
MENU_Y = (66, 236)  # the selected item's bar box
ROW_X, ROW_Y, ROW_H = (20, 380), 278, 40
SWATCH_Y, SWATCH_W = (446, 466), 94
SWATCH_STEP = 102
LAYOUT = {
    "menu_bar": (80, MENU_Y[0] + 6),
    "row_bar": (ROW_X[1] - 10, ROW_Y + ROW_H + 12),
    "swatches": [(20 + i * SWATCH_STEP + SWATCH_W // 2, (SWATCH_Y[0] + SWATCH_Y[1]) // 2) for i in range(6)],
}
GAMES = ("Super Metroid", "Chrono Trigger", "F-Zero")
SYSTEMS = ("gb", "sfc", "n64")


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _paste(img, sprite, scale, state, cx, cy):
    im = render(sprite, scale, state)
    img.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def preview_image(kind, palette, font_path=None):
    """The main screen of the `kind` (CONSOLES or CONTROLLERS) theme in `palette`, as an RGB image of `SIZE`."""
    from . import build  # build imports this module
    from ..palette_sheet import _font
    img = Image.new("RGB", SIZE, (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    small, big = _font(font_path, 20), _font(font_path, 22)
    d.text((20, 14), "12:34", font=small, fill=_rgb(palette.text))
    _paste(img, ui_status.ICONS["skin/icon-wifi-signal-04.png"](), 2, "sel", 560, 26)
    _paste(img, ui_status.ICONS["skin/power-80%-icon.png"](), 2, "sel", 605, 26)
    items = (("Favorites", menu.SPRITES["favorite"]), ("Games", build.SPECS[kind]["game"]),
             ("Apps", menu.SPRITES["app"]), ("Settings", menu.SPRITES["setting"]))
    for i, (label, draw) in enumerate(items):
        cx = 80 + i * 160
        if i == 0:
            d.rounded_rectangle((cx - 72, MENU_Y[0], cx + 72, MENU_Y[1]), 10, fill=_rgb(palette.bar))
        _paste(img, draw(), 4, "sel" if i == 0 else "n", cx, 140)
        d.text((cx, 214), label, font=big, fill=_rgb(palette.selected if i == 0 else palette.dim), anchor="mm")
    d.line((20, 258, 620, 258), fill=_rgb(palette.dim), width=2)
    for i, name in enumerate(GAMES):
        y = ROW_Y + i * ROW_H
        if i == 1:
            d.rectangle((ROW_X[0], y - 4, ROW_X[1], y + 32), fill=_rgb(palette.bar))
        d.text((34, y), name, font=big, fill=_rgb(palette.selected if i == 1 else palette.list))
    systems = build.systems(kind)
    ids = [s for s in SYSTEMS if s in systems] or list(systems)[:3]
    for i, sid in enumerate(ids):
        _paste(img, systems[sid](), 2, "sel" if i == 0 else "n", 440 + i * 62, 330)
    d.text((502, 380), "Game Boy", font=small, fill=_rgb(palette.accent), anchor="mm")
    for i, c in enumerate((palette.text, palette.list, palette.selected, palette.accent, palette.dim, palette.bar)):
        x = 20 + i * SWATCH_STEP
        d.rectangle((x, SWATCH_Y[0], x + SWATCH_W, SWATCH_Y[1]), fill=_rgb(c))
    return img
