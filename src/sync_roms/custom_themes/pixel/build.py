"""Builds a pixel-art spruceOS (PyUI) theme from the default SPRUCE theme: black backgrounds, pixel-art menu and
system icons (icons/<id>.png and icons/sel/<id>.png), app and UI icons, and the pre-scaled copies."""
import json
import os
import posixpath
import shutil

from PIL import Image, ImageChops

from ... import store
from . import (app_icons, arcade, extras, frames, handhelds, menu, nintendo_sega, others, recolor, ui_settings, ui_status,
               variants)
from .preview import preview_image
from .sprite import place, render

BATCHES = (handhelds, nintendo_sega, others, arcade, extras)
ICON_MODULES = (app_icons, ui_settings, ui_status)  # {path in the theme: draw fn}, sized to the base theme's file


def systems(kind):
    """{icon id: draw function} for the theme: sprites drawn the same in both themes plus the theme's own."""
    out = {}
    for batch in BATCHES:
        out.update(batch.SHARED)
        out.update(getattr(batch, kind))
    part = "console" if kind == "CONSOLES" else "pad"
    for icon, regions in variants.VARIANTS.items():
        out[icon] = regions[variants.REGION.get(icon, variants.DEFAULT[icon])][part]
    return out


ICON_SIZE, ICON_CENTER = (120, 130), (60, 50)
MENU_SIZE, MENU_CENTER = (100, 140), (50, 50)
BLACK = (0, 0, 0, 255)
# the default theme's #282828 full-screen backgrounds and bars, turned black (other pixels are kept)
BLACKED = {
    "skin": ["app_loading_bg.png", "bg-gamelist.png", "bg-title.png", "tips-bar-bg.png", "menu-5line-bg.png", "menu-6line-bg.png"],
    "skin_640_480": ["menu-5line-bg.png", "menu-6line-bg.png"],
}


FONT_DIR = os.path.join(store.REPO_DATA, "themes", "fusion-pixel")
FONT, FONT_LICENSE = "fusion-pixel-12px-proportional-ja.ttf", "FONT-LICENSE.txt"
# {config section: [size keys]}: each rounded down to a multiple of 12, where the pixel font is crisp
FONT_SIZES = {"batteryPercentage": ["size"], "title": ["size"], "hint": ["size"], "currentpage": ["size"], "total": ["size"],
              "list": ["size"], "grid": ["grid1x4", "grid3x4"]}


def set_font(config):
    """Point every "font" in config at FONT and round the FONT_SIZES the config has down to a multiple of 12 (at least
    12), so each screen's config keeps the base's scale; returns the fonts it replaced."""
    replaced = set()

    def walk(node):
        if isinstance(node, dict):
            if "font" in node:
                replaced.add(node["font"])
                node["font"] = FONT
            nodes = node.values()
        else:
            nodes = node if isinstance(node, list) else ()
        for child in nodes:
            walk(child)

    walk(config)
    for section, keys in FONT_SIZES.items():
        for key in keys:
            if key in config.get(section, {}):
                config[section][key] = max(12, config[section][key] // 12 * 12)
    return replaced - {FONT}


def blacken(path):
    if not os.path.exists(path):
        return
    with Image.open(path) as im:
        img = im.convert("RGBA")
    r, g, b, a = img.split()
    is_40 = lambda band: band.point(lambda v: 255 if v == 40 else 0)  # noqa: E731
    solid = a.point(lambda v: 255 if v else 0)
    mask = ImageChops.multiply(ImageChops.multiply(is_40(r), is_40(g)), ImageChops.multiply(is_40(b), solid))
    img.paste(BLACK, mask=mask)
    img.save(path)


def blacken_all(path):
    """A background: every pixel black, at the file's own size. A file the theme doesn't have is skipped."""
    if not os.path.exists(path):
        return
    with Image.open(path) as im:
        size = im.size
    Image.new("RGBA", size, BLACK).save(path)


def resize_variants(dest, drawn, native=()):
    """The theme ships pre-scaled copies for other screens (icons_<W>x<H>/, skin_<W>x<H>/) that PyUI never remakes:
    redo the files this script drew at each copy's own size, and black the backgrounds there too. Files in `native`
    (paths relative to dest, drawn at each copy's own size already) are left alone."""
    for folder in sorted(os.listdir(dest)):
        base, _, size = folder.partition("_")
        if base not in ("icons", "skin") or not size or folder == "skin_640_480":
            continue
        for dirpath, _, files in os.walk(os.path.join(dest, folder)):
            rel_dir = os.path.relpath(dirpath, os.path.join(dest, folder))
            for file in files:
                rel = posixpath.normpath(posixpath.join(base, rel_dir.replace(os.sep, "/"), file))  # drawn's keys use /
                src = os.path.join(dest, *rel.split("/"))
                target = os.path.join(dirpath, file)
                if posixpath.normpath(posixpath.join(folder, rel_dir.replace(os.sep, "/"), file)) in native:
                    continue
                if file in BLACKED.get("skin", []) and base == "skin":
                    blacken(target)
                elif file == "background.png" and base == "skin":
                    blacken_all(target)
                elif rel in drawn:
                    with Image.open(src) as drawn_img, Image.open(target) as old:
                        resized = drawn_img.resize(old.size, Image.NEAREST)
                    resized.save(target)


def write_pair(img_for, directory, name_n, name_f, size, center):
    for state, name in (("n", name_n), ("sel", name_f)):
        place(img_for(state), size, center).save(os.path.join(directory, name))


SPECS = {
    "CONSOLES": {"game": menu.handheld, "description": "Cute pixel-art consoles on black."},
    "CONTROLLERS": {"game": menu.controller, "description": "Cute pixel-art controllers on black."},
}


def build_theme(base_dir, out_dir, name, kind, palette, canvases=None, recipes=None, description=None, drawn=None):
    """Write <out_dir>/<name>/, a copy of base_dir with the pixel-art overlays (kind: CONSOLES or CONTROLLERS) in the
    palette's colors. `canvases` and `recipes` go to frames.apply; `description` replaces the kind's; a set passed as
    `drawn` gets the paths of the files the build drew in icons/ and skin/ (their pre-scaled copies are redone too)."""
    spec = dict(SPECS[kind], systems=systems(kind))
    if description is not None:
        spec["description"] = description
    dest = os.path.join(out_dir, name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(base_dir, dest)
    recolor.recolor_bar(dest, palette)  # the base's own skins and pre-scaled copies, before anything is drawn
    shutil.copyfile(os.path.join(FONT_DIR, FONT), os.path.join(dest, FONT))
    shutil.copyfile(os.path.join(FONT_DIR, "OFL.txt"), os.path.join(dest, FONT_LICENSE))
    with open(os.path.join(dest, "igm.json"), "w") as f:  # RetroArch's in-game menu, spruceOS 4.5.0+
        json.dump(recolor.igm_config(palette, FONT), f, indent=4)
        f.write("\n")
    old_fonts = set()
    for file in sorted(os.listdir(dest)):
        if not (file.startswith("config") and file.endswith(".json")):
            continue
        config_path = os.path.join(dest, file)
        with open(config_path) as f:
            config = json.load(f)
        # collectionsEnabled: PyUI's Show Collections, off when the theme doesn't set it
        config.update({"name": name, "author": "sync-roms", "description": spec["description"], "collectionsEnabled": True})
        if "screensaver" in config:
            config["screensaver"]["bgColor"] = "#000000"
        config.setdefault("hint", {})["contextbuttons"] = True  # PyUI's contextual bottom bar, with the hint pills
        recolor.recolor_config(config, palette)
        old_fonts |= set_font(config)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
            f.write("\n")
    for font in old_fonts:  # no config uses the base's font anymore
        if os.path.isfile(os.path.join(dest, font)):
            os.remove(os.path.join(dest, font))
    blacken_all(os.path.join(dest, "skin", "background.png"))
    for folder, files in BLACKED.items():
        for file in files:
            blacken(os.path.join(dest, folder, file))
    skin = os.path.join(dest, "skin")
    for folder in (skin, os.path.join(dest, "icons", "sel")):
        os.makedirs(folder, exist_ok=True)
    drawn = set() if drawn is None else drawn
    sprites = dict(menu.SPRITES, game=spec["game"])
    for key, draw in sprites.items():
        sprite = draw()
        write_pair(lambda st: render(sprite, 4, st), skin, f"ic-{key}-n.png", f"ic-{key}-f.png", MENU_SIZE, MENU_CENTER)
        drawn.update({f"skin/ic-{key}-n.png", f"skin/ic-{key}-f.png"})
    for icon, draw in spec["systems"].items():
        sprite = draw()
        for state, folder in (("n", "icons"), ("sel", "icons/sel")):
            place(render(sprite, 4, state), ICON_SIZE, ICON_CENTER).save(os.path.join(dest, *folder.split("/"), f"{icon}.png"))
            drawn.add(f"{folder}/{icon}.png")
    for module in ICON_MODULES:
        for rel, draw in module.ICONS.items():
            target = os.path.join(dest, rel)
            if os.path.exists(target):
                with Image.open(target) as im:
                    size = im.size
            elif rel.startswith("icons/app/"):  # an app the base theme has no icon for
                os.makedirs(os.path.dirname(target), exist_ok=True)
                size = app_icons.APP_SIZE
            else:
                continue
            sprite = draw()
            scale = max(1, min(4, size[0] // (sprite.w + 2), size[1] // (sprite.h + 2)))
            place(render(sprite, scale, "sel"), size, (size[0] / 2, size[1] / 2)).save(target)
            drawn.add(rel)
    native = set(frames.apply(dest, palette, canvases, recipes))  # last among the skin steps, after the recolor and blacken
    resize_variants(dest, drawn, native)
    preview(dest, kind, palette)
    with open(os.path.join(dest, "CREDITS.txt"), "a") as f:
        f.write(f"\n{name}: the SPRUCE theme with a black background and pixel-art icons drawn for sync-roms.\n"
                f"Font: Fusion Pixel 12px by TakWolf (https://github.com/TakWolf/fusion-pixel-font), {FONT}, under the SIL "
                f"Open Font License 1.1 ({FONT_LICENSE}).\n"
                "RetroArch's in-game menu (igm.json) is themed in the palette too.\n")
    return dest


def preview(dest, kind, palette):
    """preview.png (640x480): the main screen drawn in the palette (preview.py)."""
    font = os.path.join(dest, "nunwen.ttf")
    preview_image(kind, palette, font if os.path.exists(font) else None).save(os.path.join(dest, "preview.png"))
