"""Applies a palette to a built theme: its config colors and the base theme's selection-bar gray in the skins."""
import os

from PIL import Image, ImageChops

BAR_GRAY = (80, 73, 69)


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def recolor_config(config, palette):
    """Set the palette's colors on the config's text, list, grid and screensaver entries; other keys are kept."""
    def paint(key, **colors):
        section = config.get(key)
        if isinstance(section, dict):
            section.update(colors)
    for key in ("batteryPercentage", "title", "hint", "currentpage"):
        paint(key, color=palette.text)
    paint("total", color=palette.accent)
    paint("grid", color=palette.dim, selectedcolor=palette.accent)
    paint("list", color=palette.list, selectedcolor=palette.selected)
    widgets = {"clock": palette.selected, "date": palette.text, "battery": palette.accent}
    screensaver = config.get("screensaver")
    for widget in screensaver.get("widgets", []) if isinstance(screensaver, dict) else []:
        if isinstance(widget, dict) and widget.get("type") in widgets:
            widget["color"] = widgets[widget["type"]]


def igm_config(palette, font):
    """The in-game menu's igm.json for the palette, read by spruceOS 4.5.0+ from Themes/<theme>/igm.json."""
    return {
        "name": palette.name,
        "colors": {
            "dim_bg": "#000000E6",
            "panel_bg": "#00000000",
            "selection": palette.bar + "FF",
            "accent": palette.accent + "FF",
            "title_line": palette.dim + "FF",
            "text": palette.list + "FF",
            "text_selected": palette.selected + "FF",
            "text_title": palette.text + "FF",
            "text_shadow": "#00000000",
            "battery": palette.text + "FF",
        },
        "layout": {"shadow": False},
        "font": {"path": font, "size_small_pct": 5.0},  # 24px at 480 lines, 36px at 720: where the font is crisp
    }


def recolor_bar(theme_dir, palette):
    """In every .png under the theme's skin*/ folders, turn the exact bar gray into the palette's bar color (alpha
    kept). A file without that gray is left as it is."""
    bar = _rgb(palette.bar)
    for folder in sorted(os.listdir(theme_dir)):
        top = os.path.join(theme_dir, folder)
        if not folder.startswith("skin") or not os.path.isdir(top):
            continue
        for dirpath, _, files in os.walk(top):
            for file in sorted(files):
                if file.lower().endswith(".png"):
                    _recolor_png(os.path.join(dirpath, file), bar)


def _recolor_png(path, bar):
    with Image.open(path) as im:
        img = im.convert("RGBA")
    r, g, b, a = img.split()
    mask = ImageChops.multiply(ImageChops.multiply(_equal(r, BAR_GRAY[0]), _equal(g, BAR_GRAY[1])), _equal(b, BAR_GRAY[2]))
    if mask.getbbox() is None:
        return
    rgb = img.convert("RGB")
    rgb.paste(bar, mask=mask)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    out.save(path)


def _equal(band, value):
    return band.point(lambda v: 255 if v == value else 0)
