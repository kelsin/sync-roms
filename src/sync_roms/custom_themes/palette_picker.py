"""The palette picker for `themes build`/`publish`: every palette with a bar of its six colors (and, where the terminal
draws images, a preview panel), starting from the saved selection, the setting `custom_theme_palettes`.

A swatch is two blanks styled `"<hex> on <hex>"`, not just `"on <hex>"`: the list draws its highlighted row reversed,
which shows a part's foreground as its background, so a background-only swatch turns the default color there (and a
`██` block in `<hex>` would show the default background). With both colors the same, it looks alike either way.
"""
import os

from .. import picker, store, usersettings
from . import palette_sheet, palettes

SETTING = "custom_theme_palettes"


def swatches(palette):
    """The palette's six colors as list parts (one column each): text, list, selected, accent, dim, bar."""
    return [("  ", f"{c} on {c}") for c in (palette.text, palette.list, palette.selected, palette.accent, palette.dim,
                                              palette.bar)]


def _preview(palette):
    """Path of the palette's preview panel, drawn into the cache."""
    path = os.path.join(store.cache_dir(), "themes", "palette-previews", f"{palette.name}.png")
    palette_sheet.save_image(palette_sheet.render_panel(palette, palette_sheet.font_path()), path)
    return path


def pick(title, chosen):
    """Multi pick of the palettes, chosen ones on. Returns the names on in palette order, or None on Esc."""
    names = palettes.names()
    drawn = {}

    def preview(i):
        if names[i] not in drawn:  # drawn once per pick, so a changed palette never shows a stale panel
            drawn[names[i]] = _preview(palettes.get(names[i]))
        return drawn[names[i]]
    states = picker.filter_list(title, names, multi=True, initial=[n in chosen for n in names],
                                extras=[swatches(palettes.get(n)) for n in names], preview=preview, esc_asks=False,
                                hint="Space toggle · Enter done · / filter · a all · Esc cancel")
    if states is None:
        return None
    return [n for n, on in zip(names, states) if on]


def pick_one(title, names, palettes_by_name, current):
    """Single pick of one of names ({name: Palette} in palettes_by_name), the highlight starting on current. Returns
    the name, None when there are no names, False on Esc."""
    if not names:
        return None
    drawn = {}

    def preview(i):
        if names[i] not in drawn:
            drawn[names[i]] = _preview(palettes_by_name[names[i]])
        return drawn[names[i]]
    i = picker.filter_list(title, names, cursor=names.index(current) if current in names else 0,
                           extras=[swatches(palettes_by_name[n]) for n in names], preview=preview,
                           hint="Enter pick · / filter · Esc cancel")
    return False if i is None else names[i]


def saved():
    """The saved palette names that still exist, in palette order ([] when unset)."""
    names = usersettings.load_settings().get(SETTING)
    names = set(n for n in names if isinstance(n, str)) if isinstance(names, list) else set()
    return [n for n in palettes.names() if n in names]


def save(names):
    settings = usersettings.load_settings()
    settings[SETTING] = [n for n in palettes.names() if n in set(names)]
    usersettings.save_settings(settings)
