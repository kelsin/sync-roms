"""Writes the ES-DE "Pixel" theme: capabilities, colour schemes (one per palette), variants and the system sprites."""
import os
import re
import shutil
from collections import namedtuple
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

from .. import palettes
from ..pixel import build as pixel_build
from ..pixel.sprite import place, render
from . import systems

THEME = "pixel-sync-roms"
RATIOS = ("16:9", "16:10", "4:3", "3:2", "1:1", "8:7", "5:3_vertical")
VARIANTS = {"consoles": ("Consoles", "CONSOLES"), "controllers": ("Controllers", "CONTROLLERS")}
COLORS = ("text", "list", "selected", "accent", "dim", "bar")
TILE_SIZE, TILE_RADIUS = (136, 136), 12
FONT_PATH = "./font/" + pixel_build.FONT

# The system view per aspect ratio: the screen size in pixels the layout is drawn for, the selected
# item's scale over the sprite PNG (so a sprite pixel is a whole number of screen pixels, the unfocused
# items at half that) and the font sizes in pixels (multiples of 12, where Fusion Pixel is crisp).
SystemLayout = namedtuple("SystemLayout", "screen scale name count help")
SYSTEM_LAYOUTS = {
    "16:9": SystemLayout((1920, 1080), 3, 48, 36, 36),
    "16:10": SystemLayout((1280, 800), 2, 36, 24, 24),
    # Scale 2 and multiples of 24 px: whole sprite pixels and crisp text at 640x480 and 1280x960 too.
    "4:3": SystemLayout((1280, 960), 2, 48, 24, 24),
    "3:2": SystemLayout((960, 640), 2, 36, 24, 24),
    "1:1": SystemLayout((720, 720), 2, 36, 24, 24),
    "8:7": SystemLayout((1234, 1080), 3, 48, 36, 36),
    "5:3_vertical": SystemLayout((480, 800), 2, 36, 24, 12),
}
VERTICAL = {"5:3_vertical"}

# The game list per aspect ratio (same screens as SYSTEM_LAYOUTS): font sizes in pixels of the list,
# the metadata labels and values, and the description (multiples of 12).
GamelistLayout = namedtuple("GamelistLayout", "list meta desc")
GAMELIST_LAYOUTS = {
    "16:9": GamelistLayout(36, 24, 24),
    "16:10": GamelistLayout(24, 24, 24),
    "4:3": GamelistLayout(24, 24, 24),
    "3:2": GamelistLayout(24, 24, 12),
    "1:1": GamelistLayout(24, 24, 12),
    "8:7": GamelistLayout(36, 24, 24),
    "5:3_vertical": GamelistLayout(24, 24, 12),
}
LIST_WIDTH = 0.46  # of the screen width, on the wide ratios
LABEL_EMS = 5  # the label column, in font sizes ("Released" is 4 wide in Fusion Pixel)
# The metadata rows: (label, value element type, ES-DE metadata name). Elements are `pixel<label>Label`
# and `pixel<label>`; rating is ES-DE's number (`4.5`), so it needs no star images.
METADATA = (("Genre", "text", "genre"), ("Players", "text", "players"),
            ("Released", "datetime", "releasedate"), ("Rating", "text", "rating"))
# In sprite PNG pixels (pixel_build.ICON_SIZE): the middle of every sprite's drawing (ICON_CENTER) sits
# this far above the PNG's middle, so the tile behind the selected item is raised by as much.
ART_RAISE = pixel_build.ICON_SIZE[1] / 2 - pixel_build.ICON_CENTER[1]
ITEM_SPACING = {"horizontal": 128, "vertical": 112}  # between item middles, in PNG pixels at the selected scale


def slug(name):
    """A palette name as a colour scheme name: lower case, runs of other characters as `-`."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower())


def layout_file(ratio):
    """The layout file of an aspect ratio, relative to the theme folder."""
    return "layouts/" + ratio.replace(":", "-").replace(".", "-") + ".xml"


def _sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = text
    return el


def _write_xml(root, path):
    ET.indent(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(ET.tostring(root, encoding="unicode") + "\n")


def capabilities():
    root = ET.Element("themeCapabilities")
    _sub(root, "themeName", "Pixel")
    for ratio in RATIOS:
        _sub(root, "aspectRatio", ratio)
    for name in palettes.PALETTES:
        _sub(_sub(root, "colorScheme", name=slug(name)), "label", name)
    for name, (label, _kind) in VARIANTS.items():
        variant = _sub(root, "variant", name=name)
        _sub(variant, "label", label)
        _sub(variant, "selectable", "true")
    return root


def theme():
    root = ET.Element("theme")
    variables = _sub(root, "variables")
    _sub(variables, "pixelClear", "00000000")
    for name, palette in palettes.PALETTES.items():
        variables = _sub(_sub(root, "colorScheme", name=slug(name)), "variables")
        for field in COLORS:
            _sub(variables, "pixel" + field.capitalize(), getattr(palette, field).lstrip("#").upper() + "FF")
    root.append(system_config())
    root.append(gamelist_config())
    for name in VARIANTS:
        variant = _sub(root, "variant", name=name)
        _sub(_sub(variant, "variables"), "pixelSystemArt", f"./systems/{name}/${{system.theme}}.png")
        # A variant variable is only defined from the variant step on, so the art is set here.
        carousel = _sub(_sub(variant, "view", name="system"), "carousel", name="systemCarousel")
        _sub(carousel, "staticImage", "${pixelSystemArt}")
    for ratio in RATIOS:
        _sub(_sub(root, "aspectRatio", name=ratio), "include", "./" + layout_file(ratio))
    return root


def _num(value):
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _pair(x, y):
    return f"{_num(x)} {_num(y)}"


def system_config():
    """The system view's ratio-independent part, in theme.xml: colours, fonts and paths
    (`./` paths resolve from the file they are in). Each ratio's layout places the same elements."""
    view = ET.Element("view", name="system")
    tile_el = _sub(view, "image", name="pixelTile")
    _sub(tile_el, "path", "./art/tile.png")
    _sub(tile_el, "color", "${pixelBar}")
    _sub(tile_el, "interpolation", "nearest")
    _sub(tile_el, "stationary", "withinView")
    _sub(tile_el, "zIndex", "30")
    carousel = _sub(view, "carousel", name="systemCarousel")
    _sub(carousel, "imageInterpolation", "nearest")
    _sub(carousel, "imageFit", "contain")
    _sub(carousel, "color", "${pixelClear}")
    _sub(carousel, "unfocusedItemOpacity", "1")
    _sub(carousel, "unfocusedItemSaturation", "0.25")
    _sub(carousel, "unfocusedItemDimming", "0.55")
    _sub(carousel, "textColor", "${pixelText}")
    _sub(carousel, "textSelectedColor", "${pixelText}")
    _sub(carousel, "fontPath", FONT_PATH)
    _sub(carousel, "zIndex", "50")
    for name, color, value in (("pixelSystemName", "${pixelText}", ("text", "${system.fullName}")),
                               ("pixelGameCount", "${pixelAccent}", ("systemdata", "gamecountGames"))):
        text = _sub(view, "text", name=name)
        _sub(text, *value)
        _sub(text, "fontPath", FONT_PATH)
        _sub(text, "color", color)
        _sub(text, "horizontalAlignment", "center")
        _sub(text, "zIndex", "40")
    help_el = _sub(view, "helpsystem", name="help")
    _sub(help_el, "fontPath", FONT_PATH)
    _sub(help_el, "textColor", "${pixelDim}")
    _sub(help_el, "iconColor", "${pixelDim}")
    return view


def system_geometry(ratio):
    """The system view of one ratio in screen pixels: {element: (x, y, w, h)} for the tile, carousel
    and texts (x, y the top left), the carousel's item size and spacing, and the help bar's bottom left."""
    lay = SYSTEM_LAYOUTS[ratio]
    (width, height), scale = lay.screen, lay.scale
    tile_size = TILE_SIZE[0] * scale
    item = (pixel_build.ICON_SIZE[0] * scale / 2, pixel_build.ICON_SIZE[1] * scale / 2)
    margin = lay.help
    help_top = height - margin - lay.help
    gap = lay.count / 2
    if ratio in VERTICAL:
        spacing = ITEM_SPACING["vertical"] * scale
        count_y = help_top - margin - lay.count
        name_y = count_y - gap - lay.name
        carousel = (0, 0, width, name_y - margin)
        tile_cy = carousel[3] / 2 - ART_RAISE * scale
    else:
        spacing = ITEM_SPACING["horizontal"] * scale
        stack = tile_size + margin + lay.name + gap + lay.count
        tile_top = (help_top - stack) / 2
        tile_cy = tile_top + tile_size / 2
        name_y = tile_top + tile_size + margin
        count_y = name_y + lay.name + gap
        art_cy = tile_cy + ART_RAISE * scale
        carousel_h = pixel_build.ICON_SIZE[1] * scale
        carousel = (0, art_cy - carousel_h / 2, width, carousel_h)
    tile_box = (width / 2 - tile_size / 2, tile_cy - tile_size / 2, tile_size, tile_size)
    text_w = width * 0.9
    return {
        "tile": tile_box, "carousel": carousel, "item": item, "spacing": spacing,
        "name": ((width - text_w) / 2, name_y, text_w, lay.name),
        "count": ((width - text_w) / 2, count_y, text_w, lay.count),
        "help": (margin, height - margin),
    }


def system_view(ratio):
    """The system view's `<view>` in one ratio's layout file: positions, sizes and font sizes."""
    lay = SYSTEM_LAYOUTS[ratio]
    width, height = lay.screen
    vertical = ratio in VERTICAL
    font_ref = width if vertical else height  # fontSize is a fraction of the width on a vertical screen
    geo = system_geometry(ratio)
    view = ET.Element("view", name="system")

    def place(el, box):
        x, y, w, h = box
        _sub(el, "pos", _pair(x / width, y / height))
        _sub(el, "size", _pair(w / width, h / height))
        _sub(el, "origin", "0 0")

    place(_sub(view, "image", name="pixelTile"), geo["tile"])
    carousel = _sub(view, "carousel", name="systemCarousel")
    place(carousel, geo["carousel"])
    _sub(carousel, "type", "vertical" if vertical else "horizontal")
    item_w, item_h = geo["item"]
    _sub(carousel, "itemSize", _pair(item_w / width, item_h / height))
    _sub(carousel, "itemScale", "2")
    length = geo["carousel"][3] if vertical else geo["carousel"][2]
    _sub(carousel, "maxItemCount", _num(length / geo["spacing"]))
    # A system without art shows its name: the unfocused size, doubled by itemScale on the selected item.
    _sub(carousel, "fontSize", _num(max(12, lay.name // 24 * 12) / font_ref))
    for name, key, px in (("pixelSystemName", "name", lay.name), ("pixelGameCount", "count", lay.count)):
        text = _sub(view, "text", name=name)
        place(text, geo[key])
        _sub(text, "fontSize", _num(px / font_ref))
    help_el = _sub(view, "helpsystem", name="help")
    x, y = geo["help"]
    _sub(help_el, "pos", _pair(x / width, y / height))
    _sub(help_el, "origin", "0 1")
    _sub(help_el, "fontSize", _num(lay.help / font_ref))
    return view


def gamelist_config():
    """The game list's ratio-independent part, in theme.xml: what each element shows, colours, fonts."""
    view = ET.Element("view", name="gamelist")
    textlist = _sub(view, "textlist", name="pixelList")
    _sub(textlist, "selectorColor", "${pixelBar}")
    _sub(textlist, "primaryColor", "${pixelList}")
    _sub(textlist, "selectedColor", "${pixelSelected}")
    _sub(textlist, "secondaryColor", "${pixelAccent}")  # folders
    _sub(textlist, "selectedSecondaryColor", "${pixelSelected}")
    _sub(textlist, "fontPath", FONT_PATH)
    _sub(textlist, "lineSpacing", "1.5")
    _sub(textlist, "indicators", "ascii")  # plain `*`, `#`, `>` in the pixel font
    _sub(textlist, "collectionIndicators", "ascii")
    art = _sub(view, "image", name="pixelArt")
    _sub(art, "imageType", "miximage")
    _sub(art, "interpolation", "linear")  # scraped pictures, shrunk to fit
    for field, kind, metadata in METADATA:
        text = _sub(view, "text", name=f"pixel{field}Label")
        _sub(text, "text", field)
        _sub(text, "metadataElement", "true")
        _sub(text, "fontPath", FONT_PATH)
        _sub(text, "color", "${pixelAccent}")
        value = _sub(view, kind, name=f"pixel{field}")
        _sub(value, "metadata", metadata)
        _sub(value, "fontPath", FONT_PATH)
        _sub(value, "color", "${pixelText}")
    desc = _sub(view, "text", name="pixelDescription")
    _sub(desc, "metadata", "description")
    _sub(desc, "fontPath", FONT_PATH)
    _sub(desc, "color", "${pixelText}")
    help_el = _sub(view, "helpsystem", name="help")
    _sub(help_el, "fontPath", FONT_PATH)
    _sub(help_el, "textColor", "${pixelDim}")
    _sub(help_el, "iconColor", "${pixelDim}")
    return view


def gamelist_geometry(ratio):
    """The game list of one ratio in screen pixels: {element: (x, y, w, h)} (x, y the top left) for
    `list`, `art`, `<field>Label` and `<field>` per metadata row and, except on vertical screens,
    `description`; and the help bar's bottom left as `help`. Wide: list left, details right.
    Vertical: art and metadata on top, list below."""
    width, height = SYSTEM_LAYOUTS[ratio].screen
    lay, help_px = GAMELIST_LAYOUTS[ratio], SYSTEM_LAYOUTS[ratio].help
    margin = max(12, help_px)
    bottom = height - 2 * margin - help_px  # above the help bar
    row, label_w = lay.meta * 1.5, lay.meta * LABEL_EMS
    if ratio in VERTICAL:
        panel_x, panel_w, top = margin, width - 2 * margin, margin
        art_h = round(height * 0.27)
    else:
        panel_x = width * LIST_WIDTH + margin / 2
        panel_w, top = width - margin - panel_x, margin
        art_h = (bottom - margin) / 2
    geo = {"art": (panel_x, top, panel_w, art_h)}
    meta_top = top + art_h + margin
    for i, (field, *_rest) in enumerate(METADATA):
        y = meta_top + i * row
        geo[field + "Label"] = (panel_x, y, label_w, lay.meta)
        geo[field] = (panel_x + label_w, y, panel_w - label_w, lay.meta)
    meta_bottom = meta_top + (len(METADATA) - 1) * row + lay.meta
    if ratio in VERTICAL:
        list_top = meta_bottom + margin
        geo["list"] = (margin, list_top, width - 2 * margin, bottom - list_top)
    else:
        geo["list"] = (margin, margin, width * LIST_WIDTH - margin * 1.5, bottom - margin)
        desc_top = meta_bottom + margin
        geo["description"] = (panel_x, desc_top, panel_w, bottom - desc_top)
    geo["help"] = (margin, height - margin)
    return geo


def gamelist_view(ratio):
    """The game list's `<view>` in one ratio's layout file: positions, sizes and font sizes."""
    width, height = SYSTEM_LAYOUTS[ratio].screen
    lay = GAMELIST_LAYOUTS[ratio]
    vertical = ratio in VERTICAL
    font_ref = width if vertical else height  # fontSize is a fraction of the width on a vertical screen
    geo = gamelist_geometry(ratio)
    view = ET.Element("view", name="gamelist")

    def place(el, box, px=None):
        x, y, w, h = box
        _sub(el, "pos", _pair(x / width, y / height))
        _sub(el, "size", _pair(w / width, h / height))
        _sub(el, "origin", "0 0")
        if px is not None:
            _sub(el, "fontSize", _num(px / font_ref))

    textlist = _sub(view, "textlist", name="pixelList")
    place(textlist, geo["list"], lay.list)
    _sub(textlist, "horizontalMargin", _num(lay.list / 2 / width))
    art = _sub(view, "image", name="pixelArt")
    x, y, w, h = geo["art"]
    _sub(art, "pos", _pair((x + w / 2) / width, (y + h / 2) / height))
    _sub(art, "maxSize", _pair(w / width, h / height))
    _sub(art, "origin", "0.5 0.5")
    for field, kind, _metadata in METADATA:
        place(_sub(view, "text", name=f"pixel{field}Label"), geo[field + "Label"], lay.meta)
        place(_sub(view, kind, name=f"pixel{field}"), geo[field], lay.meta)
    desc = _sub(view, "text", name="pixelDescription")
    if "description" in geo:
        place(desc, geo["description"], lay.desc)
    else:
        _sub(desc, "visible", "false")
    help_el = _sub(view, "helpsystem", name="help")
    x, y = geo["help"]
    _sub(help_el, "pos", _pair(x / width, y / height))
    _sub(help_el, "origin", "0 1")
    _sub(help_el, "fontSize", _num(SYSTEM_LAYOUTS[ratio].help / font_ref))
    return view


def layout(ratio):
    """The `<theme>` of one aspect ratio's layout file."""
    root = ET.Element("theme")
    root.append(system_view(ratio))
    root.append(gamelist_view(ratio))
    return root


def tile():
    """A white rounded tile, tinted by `${pixelBar}` in the theme."""
    img = Image.new("RGBA", TILE_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, TILE_SIZE[0] - 1, TILE_SIZE[1] - 1), TILE_RADIUS, fill=(255, 255, 255, 255))
    return img


def build(out_dir):
    """Write `<out_dir>/pixel-sync-roms/` (replacing it) and return its path."""
    dest = os.path.join(out_dir, THEME)
    shutil.rmtree(dest, ignore_errors=True)
    _write_xml(capabilities(), os.path.join(dest, "capabilities.xml"))
    _write_xml(theme(), os.path.join(dest, "theme.xml"))
    for ratio in RATIOS:
        _write_xml(layout(ratio), os.path.join(dest, *layout_file(ratio).split("/")))
    names = systems.esde_names()
    for folder, (_label, kind) in VARIANTS.items():
        target = os.path.join(dest, "systems", folder)
        os.makedirs(target)
        drawn = systems.sprites(kind)
        for name in names:
            img = place(render(drawn[name](), 4, "sel"), pixel_build.ICON_SIZE, pixel_build.ICON_CENTER)
            img.save(os.path.join(target, f"{name}.png"))
    os.makedirs(os.path.join(dest, "art"))
    tile().save(os.path.join(dest, "art", "tile.png"))
    os.makedirs(os.path.join(dest, "font"))
    for file in (pixel_build.FONT, "OFL.txt"):
        shutil.copyfile(os.path.join(pixel_build.FONT_DIR, file), os.path.join(dest, "font", file))
    with open(os.path.join(dest, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("Generated by sync-roms, from the Pixel themes.\n")
    return dest
