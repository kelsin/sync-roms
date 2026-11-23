"""Builds a pixel-art spruceOS (PyUI) theme from the default SPRUCE theme: black backgrounds, pixel-art menu and
system icons (icons/<id>.png and icons/sel/<id>.png), app and UI icons, and the pre-scaled copies."""
import json
import os
import shutil

from PIL import Image

from . import app_icons, arcade, extras, handhelds, menu, nintendo_sega, others, ui_settings, ui_status, variants
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


def blacken(path):
    img = Image.open(path).convert("RGBA")
    img.putdata([BLACK if px[:3] == (40, 40, 40) and px[3] else px for px in img.getdata()])
    img.save(path)


def resize_variants(dest, drawn):
    """The theme ships pre-scaled copies for other screens (icons_<W>x<H>/, skin_<W>x<H>/) that PyUI never remakes:
    redo the files this script drew at each copy's own size, and black the backgrounds there too."""
    for folder in sorted(os.listdir(dest)):
        base, _, size = folder.partition("_")
        if base not in ("icons", "skin") or not size or folder == "skin_640_480":
            continue
        for dirpath, _, files in os.walk(os.path.join(dest, folder)):
            rel_dir = os.path.relpath(dirpath, os.path.join(dest, folder))
            for file in files:
                rel = os.path.normpath(os.path.join(base, rel_dir, file))
                src = os.path.join(dest, rel)
                target = os.path.join(dirpath, file)
                if file in BLACKED.get("skin", []) and base == "skin":
                    blacken(target)
                elif file == "background.png" and base == "skin":
                    Image.new("RGBA", Image.open(target).size, BLACK).save(target)
                elif rel in drawn:
                    Image.open(src).resize(Image.open(target).size, Image.NEAREST).save(target)


def write_pair(img_for, directory, name_n, name_f, size, center):
    for state, name in (("n", name_n), ("sel", name_f)):
        place(img_for(state), size, center).save(os.path.join(directory, name))


SPECS = {
    "CONSOLES": {"game": menu.handheld, "description": "Cute pixel-art consoles on black."},
    "CONTROLLERS": {"game": menu.controller, "description": "Cute pixel-art controllers on black."},
}


def build_theme(base_dir, out_dir, name, kind):
    """Write <out_dir>/<name>/, a copy of base_dir with the pixel-art overlays (kind: CONSOLES or CONTROLLERS)."""
    spec = dict(SPECS[kind], systems=systems(kind))
    base, out = base_dir, out_dir
    dest = os.path.join(out, name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(base, dest)
    for file in sorted(os.listdir(dest)):
        if not (file.startswith("config") and file.endswith(".json")):
            continue
        config_path = os.path.join(dest, file)
        with open(config_path) as f:
            config = json.load(f)
        config.update({"name": name, "author": "sync-roms", "description": spec["description"]})
        if "screensaver" in config:
            config["screensaver"]["bgColor"] = "#000000"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
            f.write("\n")
    for path in (os.path.join(dest, "skin", "background.png"),):
        Image.new("RGBA", Image.open(path).size, BLACK).save(path)
    for folder, files in BLACKED.items():
        for file in files:
            blacken(os.path.join(dest, folder, file))
    skin = os.path.join(dest, "skin")
    drawn = set()
    sprites = dict(menu.SPRITES, game=spec["game"])
    for key, draw in sprites.items():
        sprite = draw()
        write_pair(lambda st: render(sprite, 4, st), skin, f"ic-{key}-n.png", f"ic-{key}-f.png", MENU_SIZE, MENU_CENTER)
        drawn.update({f"skin/ic-{key}-n.png", f"skin/ic-{key}-f.png"})
    for icon, draw in spec["systems"].items():
        sprite = draw()
        for state, folder in (("n", "icons"), ("sel", os.path.join("icons", "sel"))):
            place(render(sprite, 4, state), ICON_SIZE, ICON_CENTER).save(os.path.join(dest, folder, f"{icon}.png"))
            drawn.add(f"{folder}/{icon}.png")
    for module in ICON_MODULES:
        for rel, draw in module.ICONS.items():
            target = os.path.join(dest, rel)
            if not os.path.exists(target):
                continue
            size = Image.open(target).size
            sprite = draw()
            scale = max(1, min(4, size[0] // (sprite.w + 2), size[1] // (sprite.h + 2)))
            place(render(sprite, scale, "sel"), size, (size[0] / 2, size[1] / 2)).save(target)
            drawn.add(rel)
    resize_variants(dest, drawn)
    preview(dest, spec)
    with open(os.path.join(dest, "CREDITS.txt"), "a") as f:
        f.write(f"\n{name}: the SPRUCE theme with a black background and pixel-art icons drawn for sync-roms.\n")
    return dest


def preview(dest, spec):
    """preview.png (640x480): the main menu row over a grid of system icons, on black."""
    img = Image.new("RGBA", (640, 480), BLACK)
    for n, key in enumerate(list(menu.SPRITES) + ["game"]):
        tile = Image.open(os.path.join(dest, "skin", f"ic-{key}-{'f' if n == 0 else 'n'}.png")).convert("RGBA").resize((70, 98), Image.NEAREST)
        img.paste(tile, (20 + n * 86, 20), tile)
    ids = list(spec["systems"])[:18]
    for n, icon in enumerate(ids):
        tile = Image.open(os.path.join(dest, "icons", "sel" if n == 0 else "", f"{icon}.png")).convert("RGBA").resize((100, 108), Image.NEAREST)
        img.paste(tile, (20 + (n % 6) * 104, 140 + (n // 6) * 110), tile)
    img.save(os.path.join(dest, "preview.png"))
