"""Applies a palette to a built theme: its config colors and the base theme's selection-bar gray in the skins."""
import os

from PIL import Image, ImageChops

BAR_GRAY = (80, 73, 69)


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


# config.json keys to palette roles (the theme options format's `configKeys`): dotted keys, and `name[field=value]` for
# every item of a list whose `field` equals `value`
CONFIG_KEYS = {
    "title.color": "text", "hint.color": "text", "batteryPercentage.color": "text",
    "currentpage.color": "text", "total.color": "accent", "grid.color": "dim",
    "grid.selectedcolor": "accent", "list.color": "list", "list.selectedcolor": "selected",
    "screensaver.widgets[type=clock].color": "selected",
    "screensaver.widgets[type=date].color": "text",
    "screensaver.widgets[type=battery].color": "accent",
}
# igm.json colors to palette roles (the format's `igmKeys`); their values are the role's hex plus the suffix
IGM_KEYS = {
    "colors.selection": {"role": "bar", "suffix": "FF"},
    "colors.accent": {"role": "accent", "suffix": "FF"},
    "colors.title_line": {"role": "dim", "suffix": "FF"},
    "colors.text": {"role": "list", "suffix": "FF"},
    "colors.text_selected": {"role": "selected", "suffix": "FF"},
    "colors.text_title": {"role": "text", "suffix": "FF"},
    "colors.battery": {"role": "text", "suffix": "FF"},
}


def set_path(data, path, value):
    """Set `value` at `path` ("a.b", "list[field=value].key") in nested dicts and lists; the last key is set where its
    parent exists. False when a parent isn't there (nothing is created); True once every match is set."""
    head, _, rest = path.partition(".")
    if "[" in head:
        name, selector = head[:-1].split("[", 1)
        field, _, want = selector.partition("=")
        items = data.get(name) if isinstance(data, dict) else None
        if not isinstance(items, list):
            return False
        found = False
        for item in items:
            if isinstance(item, dict) and item.get(field) == want:
                found = (set_path(item, rest, value) if rest else False) or found
        return found
    if not isinstance(data, dict):
        return False
    if not rest:
        data[head] = value
        return True
    return set_path(data[head], rest, value) if head in data else False


def recolor_config(config, palette):
    """Set the palette's colors on the config's text, list, grid and screensaver entries; other keys are kept."""
    for path, role in CONFIG_KEYS.items():
        set_path(config, path, getattr(palette, role))


def igm_config(palette, font):
    """The in-game menu's igm.json for the palette, read by spruceOS 4.5.0+ from Themes/<theme>/igm.json."""
    colors = {  # the palette's keys are filled below, in this order
        "dim_bg": "#000000E6", "panel_bg": "#00000000", "selection": None, "accent": None, "title_line": None,
        "text": None, "text_selected": None, "text_title": None, "text_shadow": "#00000000", "battery": None,
    }
    config = {
        "name": palette.name,
        "colors": colors,
        "layout": {"shadow": False},
        "font": {"path": font, "size_small_pct": 5.0},  # 24px at 480 lines, 36px at 720: where the font is crisp
    }
    for path, spec in IGM_KEYS.items():
        key = path.split(".", 1)[1]
        colors[key] = getattr(palette, spec["role"]) + spec["suffix"]
    return config


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
