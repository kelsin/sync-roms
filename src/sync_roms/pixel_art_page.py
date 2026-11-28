"""The pixel art page: every picture sync-roms draws for its spruceOS pixel themes and the systems only its ES-DE
Pixel theme draws, and its writer."""
import json
import os
import re
import shutil
import tempfile

from PIL import Image

from . import collections_page, custom_themes, store, ui
from .custom_themes import palettes, pixel_consoles, theme_name
from .custom_themes.pixel import app_icons, build, frames, ids, menu, ui_settings, ui_status, variants
from .custom_themes.pixel.sprite import COLORS, INK, render

PALETTE = "Gruvbox"
TEMPLATE_DIR = os.path.join(store.REPO_DATA, "pixel-art-page")


def _size(theme_dir, rel, fixed=None):
    """A file's size in the built theme, else `fixed`, else None."""
    if theme_dir:
        path = os.path.join(theme_dir, *rel.split("/"))
        if os.path.isfile(path):
            with Image.open(path) as im:
                return list(im.size)
    return list(fixed) if fixed else None


class _Writer:
    """Writes one section's PNGs (one pixel per art pixel) and describes each as an item."""

    def __init__(self, img_dir, section):
        self.dir = os.path.join(img_dir, section)
        self.section = section
        self.used = set()
        os.makedirs(self.dir, exist_ok=True)

    def stem(self, name):
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        base, n = stem, 2
        while stem in self.used:
            stem, n = f"{base}_{n}", n + 1
        self.used.add(stem)
        return stem

    def image_item(self, label, name, img, files, note=None, **extra):
        """An item whose picture is a ready PIL image, saved as it is."""
        stem = self.stem(name)
        img.save(os.path.join(self.dir, f"{stem}.png"))
        item = {"label": label, "img": f"img/{self.section}/{stem}.png", "w": img.width, "h": img.height,
                "files": files, **extra}
        if note:
            item["note"] = note
        return item

    def item(self, label, name, draw, files, dim=True, note=None):
        stem = self.stem(name)
        sprite = draw()
        sel = render(sprite, 1, "sel")
        sel.save(os.path.join(self.dir, f"{stem}.png"))
        item = {"label": label, "img": f"img/{self.section}/{stem}.png", "w": sel.width, "h": sel.height, "files": files}
        if dim:
            render(sprite, 1, "n").save(os.path.join(self.dir, f"{stem}-n.png"))
            item["dim"] = f"img/{self.section}/{stem}-n.png"
        if note:
            item["note"] = note
        return item


def _section(sid, title, items):
    return {"id": sid, "title": title, "items": items}


def _file_stem(rel):
    name = rel.rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".png") else name


def _menu(img_dir, theme_dir):
    w = _Writer(img_dir, "menu")
    entries = [(key, key, draw, key.capitalize()) for key, draw in menu.SPRITES.items()]
    entries += [("game-consoles", "game", menu.handheld, "Games (Consoles theme)"),
                ("game-controllers", "game", menu.controller, "Games (Controllers theme)")]
    items = []
    for name, key, draw, label in entries:
        files = [{"path": f"skin/ic-{key}-{s}.png", "size": _size(theme_dir, f"skin/ic-{key}-{s}.png", build.MENU_SIZE)}
                 for s in ("n", "f")]
        items.append(w.item(label, name, draw, files))
    return _section("menu", "Menu icons", items)


THEME_OF_PART = {"console": "Pixel Consoles", "pad": "Pixel Controllers"}


def _system_files(theme_dir, icon, theme=None):
    files = [{"path": p, "size": _size(theme_dir, p, build.ICON_SIZE)}
             for p in (f"icons/{icon}.png", f"icons/sel/{icon}.png")]
    if theme:
        for f in files:
            f["theme"] = theme
    return files


def _systems(img_dir, theme_dir):
    consoles, controllers = build.systems("CONSOLES"), build.systems("CONTROLLERS")
    sections = []
    for sid, title, source, shared_only in (
            ("systems-shared", "System icons (both themes)", consoles, True),
            ("systems-consoles", "System icons (Consoles theme)", consoles, False),
            ("systems-controllers", "System icons (Controllers theme)", controllers, False)):
        w = _Writer(img_dir, sid)
        items = [w.item(ids.IDS.get(icon, icon), icon, draw, _system_files(theme_dir, icon))
                 for icon, draw in source.items() if (consoles[icon] is controllers[icon]) == shared_only]
        sections.append(_section(sid, title, items))
    return sections


def _esde_systems(img_dir):
    """The systems only the ES-DE Pixel theme draws, as in its systems/consoles|controllers/<ES-DE name>.png."""
    from .custom_themes.esde import systems as esde_systems
    with open(os.path.join(store.REPO_DATA, "systems.json"), encoding="utf-8") as f:
        names = {}
        for entry in json.load(f):
            names.setdefault(entry["folders"].get("esde"), entry["name"])
    sections = []
    for sid, title, kind, folders in (
            ("esde-shared", "ES-DE system icons (both variants)", "CONSOLES", ("consoles", "controllers")),
            ("esde-consoles", "ES-DE system icons (Consoles variant)", "CONSOLES", ("consoles",)),
            ("esde-controllers", "ES-DE system icons (Controllers variant)", "CONTROLLERS", ("controllers",))):
        w = _Writer(img_dir, sid)
        items = []
        for name, draws in esde_systems.EXTRA.items():
            if (draws["CONSOLES"] is draws["CONTROLLERS"]) == (sid == "esde-shared"):
                files = [{"path": f"systems/{d}/{name}.png", "size": list(build.ICON_SIZE), "theme": "Pixel ES-DE"}
                         for d in folders]
                items.append(w.item(names.get(name, name), name, draws[kind], files))
        sections.append(_section(sid, title, items))
    return sections


def _regions(img_dir, theme_dir):
    w = _Writer(img_dir, "regions")
    items = []
    for icon, regions in variants.VARIANTS.items():
        for region, parts in regions.items():
            for part, draw in parts.items():
                used = region == variants.REGION.get(icon, variants.DEFAULT[icon])
                label = f"{ids.IDS.get(icon, icon)} — {region.upper()} {part}"
                items.append(w.item(label, f"{icon}-{region}-{part}", draw,
                                    _system_files(theme_dir, icon, THEME_OF_PART[part]) if used else [],
                                    note="used by the themes" if used else "not used by the themes"))
    return _section("regions", "Regional variants", items)


def _ui(img_dir, theme_dir, sid, title, module, always=False):
    """Icons build draws only over a file the base theme has (apps: always, at APP_SIZE), in the selected state."""
    w = _Writer(img_dir, sid)
    items = []
    for rel, draw in module.ICONS.items():
        size = _size(theme_dir, rel, app_icons.APP_SIZE if always else None)
        items.append(w.item(_file_stem(rel), _file_stem(rel), draw, [{"path": rel, "size": size}], dim=False,
                            note="not in the SPRUCE base" if size is None else None))
    return _section(sid, title, items)


def sprite_sections(img_dir, theme_dir=None):
    """Write the sprite PNGs under img_dir (one folder per section) and describe them for the page."""
    return [_menu(img_dir, theme_dir), *_systems(img_dir, theme_dir), _regions(img_dir, theme_dir),
            *_esde_systems(img_dir),
            _ui(img_dir, theme_dir, "apps", "App icons", app_icons, always=True),
            _ui(img_dir, theme_dir, "settings", "Settings icons", ui_settings),
            _ui(img_dir, theme_dir, "status", "Status and buttons", ui_status)]


# The frames that are pictures spruceOS loads on every device: the hint pills PyUI's bottom bars show (it makes only
# A, B and X hints); the bars, panels and boxes, and the frames nothing (or only one device) loads, stay off the page.
ICON_FRAMES = ("context-a", "context-b", "context-x", "icon-A-54", "icon-B-54")


def build_frames_theme(base_dir, out_dir):
    """Build the Consoles theme in the page's palette from base_dir; returns (theme_dir, {"skin/<file>": Canvas})."""
    canvases = {}
    theme = build.build_theme(base_dir, out_dir, theme_name("Pixel Consoles", PALETTE), "CONSOLES",
                              palettes.get(PALETTE), canvases=canvases)
    return theme, {k: v for k, v in canvases.items() if k.startswith("skin/")}


def frame_section(img_dir, canvases):
    """One item per ICON_FRAMES frame the theme drew (its cell grid, one pixel per cell)."""
    w = _Writer(img_dir, "palette-icons")
    for key in sorted(frames.FRAMES):
        if _file_stem(key) in ICON_FRAMES and key not in canvases:
            ui.warn(f"The frame {key} has no canvas in the base theme, so it won't show on the pixel art page")
    items = [w.image_item(_file_stem(key), _file_stem(key), canvas.cell_image(),
                          [{"path": key, "size": list(canvas.size)}], cell=canvas.cell)
             for key, canvas in sorted(canvases.items(), key=lambda kv: kv[0].rsplit("/", 1)[-1])
             if _file_stem(key) in ICON_FRAMES]
    return _section("palette-icons", "Palette icons", items)


def box_section(img_dir):
    """One item per collection box picture, shown at a quarter of its 336x480."""
    folder = os.path.join(store.REPO_DATA, "themes", "art-book-next", "art-box", "Imgs")
    w = _Writer(img_dir, "boxes")
    items = []
    for name in sorted(f[:-4] for f in os.listdir(folder) if f.endswith(".png")):
        file = f"{name}.png"
        with Image.open(os.path.join(folder, file)) as im:
            small = im.convert("RGB").resize((im.width // 4, im.height // 4), Image.NEAREST)
        files = [{"path": f"Collections/{d}/<collection name>.png", "size": s}
                 for d, s in (("Imgs", [336, 480]), ("Imgs_med", [210, 300]), ("Imgs_small", [140, 200]))]
        items.append(w.image_item(name, name, small, files))
    return _section("boxes", "Collection box art", items)


def write(out_dir, base_dir=None):
    """Build the page in out_dir, emptied first: index.html (page.html with its data), page.css, page.js and img/.
    base_dir defaults to the Consoles theme's base from storage (custom_themes.fetch_base raises BaseMissing or
    DownloadFailed)."""
    if base_dir is None:
        base_dir = custom_themes.fetch_base(pixel_consoles.BASE)
    shutil.rmtree(out_dir, ignore_errors=True)
    img_dir = os.path.join(out_dir, "img")
    os.makedirs(img_dir)
    with tempfile.TemporaryDirectory() as tmp:
        theme, canvases = build_frames_theme(base_dir, tmp)
        sections = [*sprite_sections(img_dir, theme), frame_section(img_dir, canvases), box_section(img_dir)]
    files = {}
    for name in ("page.html", "page.css", "page.js"):
        with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
            files[name] = f.read()
    data = {"palette": PALETTE, "home": "/", "sections": sections, "colors": {**COLORS, "ink": INK}}  # colors: the brief's
    store.write_text(os.path.join(out_dir, "index.html"), collections_page.fill(files["page.html"], data))
    for name in ("page.css", "page.js"):
        store.write_text(os.path.join(out_dir, name), files[name])
