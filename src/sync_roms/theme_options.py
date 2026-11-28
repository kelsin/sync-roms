"""A spruce card's choice of variant and palette for a PyUI theme with options/ (docs/theme-options-format.md): the
card setting theme_options, which sync writes as Themes/<name>/options/selected.json. The device can change that file
itself, so sync writes it only when the setting differs from what it wrote last (theme_options_written), or when the
file is gone."""
import json
import os

from . import mirroring, runtime, s3, store, ui

SELECTED = ("options", "selected.json")


def manifest(name):
    """Storage's os/spruceos/themes/<name>/options/manifest.json, or None without one (or when it can't be read,
    warned about). Read from storage itself, past a sync's mirror."""
    key = f"{runtime.SPRUCE_THEMES_PREFIX}{name}/options/manifest.json"
    with mirroring.storage_reads():
        try:
            s3.check_root()  # an unmounted share, not a missing file
        except OSError as e:
            ui.warn(f"Couldn't read {key}: {e}")
            return None
        try:
            data = json.loads(s3.get_bytes(key))
        except ValueError as e:
            ui.warn(f"{key} can't be read: {e}")
            return None
        except s3.ERRORS as e:
            if not s3.missing(e):
                ui.warn(f"Couldn't read {key}: {e}")
            return None
    return data if isinstance(data, dict) else None


def variants(manifest):
    """[(id, name)] of the manifest's variants."""
    section = manifest.get("variants")
    items = section.get("list") if isinstance(section, dict) else None
    return [(v["id"], v.get("name") or v["id"]) for v in items or [] if isinstance(v, dict) and isinstance(v.get("id"), str)]


def palettes(manifest):
    """{name: {role: hex}} of the manifest's palettes, in its order."""
    section = manifest.get("colors")
    items = section.get("palettes") if isinstance(section, dict) else None
    return {p["name"]: p.get("colors") or {} for p in items or [] if isinstance(p, dict) and isinstance(p.get("name"), str)}


def roles(manifest):
    section = manifest.get("colors")
    items = section.get("roles") if isinstance(section, dict) else None
    return [r["id"] for r in items or [] if isinstance(r, dict) and isinstance(r.get("id"), str)]


def defaults(manifest):
    """(default variant, default palette) of the manifest (None for a section it lacks)."""
    v, c = manifest.get("variants"), manifest.get("colors")
    return (v.get("default") if isinstance(v, dict) else None, c.get("defaultPalette") if isinstance(c, dict) else None)


def choice(manifest, setting):
    """(variant, palette) a card setting picks: its own values, else the manifest's defaults."""
    setting = setting if isinstance(setting, dict) else {}
    default_variant, default_palette = defaults(manifest)
    return setting.get("variant") or default_variant, setting.get("palette") or default_palette


def selected(manifest, variant, palette):
    """The selected.json for variant and palette: {"variant", "palette", "colors"} with every role's value. None
    picks the manifest's default. Raises ValueError for a variant or palette the manifest doesn't have."""
    variant, palette = choice(manifest, {"variant": variant, "palette": palette})
    ids = [v for v, _ in variants(manifest)]
    if not ids:
        variant = None
    elif variant not in ids:
        raise ValueError(f"the theme has no variant {variant}")
    if not isinstance(manifest.get("colors"), dict):
        return {"variant": variant, "palette": None, "colors": {}}
    colors = palettes(manifest).get(palette)
    if colors is None:
        raise ValueError(f"the theme has no palette {palette}")
    missing = [r for r in roles(manifest) if r not in colors]
    if missing:
        raise ValueError(f"the palette {palette} lacks {', '.join(missing)}")
    return {"variant": variant, "palette": palette, "colors": {r: colors[r] for r in roles(manifest)}}


def _wanted(setting):
    """The part of a card setting sync records: its string variant and palette."""
    return {k: setting[k] for k in ("variant", "palette") if isinstance(setting.get(k), str)}


def label(data):
    return " · ".join(str(data.get(k) or "default") for k in ("variant", "palette"))


def write(card, base, names, dry_run):
    """Write Themes/<name>/options/selected.json for each synced theme (names) with a card setting in theme_options
    that differs from theme_options_written (or whose file is gone) and a manifest in storage, then record it in
    theme_options_written (a dry run prints what it would write and records nothing). A variant or palette the
    manifest lacks is warned about and skipped. Returns whether it wrote (in a dry run, would write)."""
    saved = store.saved_card(card)
    settings = saved.get("theme_options")
    settings = settings if isinstance(settings, dict) else {}
    written = saved.get("theme_options_written")
    written = dict(written) if isinstance(written, dict) else {}
    before = dict(written)
    wrote = False
    for name in names:
        setting = settings.get(name)
        if not isinstance(setting, dict):
            continue
        want = _wanted(setting)
        path = os.path.join(base, "Themes", name, *SELECTED)
        if written.get(name) == want and os.path.exists(path):
            continue
        found = manifest(name)
        if found is None:
            print(ui.dim(f"   ⏭️  Theme options for {name}: storage's theme has no options; skipped"))
            continue
        try:
            data = selected(found, want.get("variant"), want.get("palette"))
        except ValueError as e:
            ui.warn(f"Theme options for {name}: {e}; skipped (pick again in the card editor's S menu)")
            continue
        if dry_run:
            print(ui.dim(f"🧪 Dry run: would set the {name} theme options to {label(data)}"))
            wrote = True
            continue
        if not os.path.isdir(os.path.dirname(path)):
            print(ui.dim(f"   ⏭️  Theme options for {name}: Themes/{name}/options/ isn't on the card; skipped"))
            continue
        try:
            store.replace_file(path, json.dumps(data, indent=2) + "\n")
        except OSError as e:
            ui.warn(f"Couldn't write {os.path.relpath(path, base)}: {e}")
            continue
        print(f"🎨 Theme options: {name} → {label(data)}")
        written[name] = want
        wrote = True
    if not dry_run:
        written = {k: v for k, v in written.items() if k in settings}  # a cleared setting leaves no record
        if written != before:
            cards = store.load_cards()
            if isinstance(cards.get(card), dict):
                if written:
                    cards[card]["theme_options_written"] = written
                else:
                    cards[card].pop("theme_options_written", None)
                store.write_cards(cards)
    return wrote
