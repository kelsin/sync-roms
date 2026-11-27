"""The pixel art page: every picture sync-roms draws for its spruceOS pixel themes (sprites here)."""
import os
import re

from PIL import Image

from .custom_themes.pixel import app_icons, build, ids, menu, ui_settings, ui_status, variants
from .custom_themes.pixel.sprite import render

PALETTE = "Gruvbox"


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

    def item(self, label, name, draw, files, dim=True, note=None):
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        base, n = stem, 2
        while stem in self.used:
            stem, n = f"{base}_{n}", n + 1
        self.used.add(stem)
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


def _system_files(theme_dir, icon):
    return [{"path": p, "size": _size(theme_dir, p, build.ICON_SIZE)}
            for p in (f"icons/{icon}.png", f"icons/sel/{icon}.png")]


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


def _regions(img_dir, theme_dir):
    w = _Writer(img_dir, "regions")
    items = []
    for icon, regions in variants.VARIANTS.items():
        for region, parts in regions.items():
            for part, draw in parts.items():
                used = region == variants.REGION[icon]
                label = f"{ids.IDS.get(icon, icon)} — {region.upper()} {part}"
                items.append(w.item(label, f"{icon}-{region}-{part}", draw,
                                    _system_files(theme_dir, icon) if used else [],
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
            _ui(img_dir, theme_dir, "apps", "App icons", app_icons, always=True),
            _ui(img_dir, theme_dir, "settings", "Settings icons", ui_settings),
            _ui(img_dir, theme_dir, "status", "Status icons", ui_status)]
