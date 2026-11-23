"""The spruce settings saved in settings.json (the spruce_ra_* RetroAchievements ones and the allowlisted spruce_settings), written into a spruce card's Saves/spruce/spruce-config.json, and the import of the latter from a card."""
import json
import os
import re

from . import applied, cardfs, store, ui, usersettings

FILE = os.path.join("Saves", "spruce", "spruce-config.json")
BLOCK = "RetroAchievements Settings"
MODES = ("Manual", "Disabled", "Casual", "Softcore", "Hardcore")
# settings.json key -> (key in the block, bool setting)
KEYS = {"spruce_ra_mode": ("modeToggle", False), "spruce_ra_username": ("username", False),
        "spruce_ra_password": ("password", False), "spruce_ra_api_key": ("webApiKey", False),
        "spruce_ra_offline_proxy": ("enableOfflineProxy", True), "spruce_ra_proxy_stats": ("raproxyUsageStats", True)}


def wanted():
    """{key in the block: string} of the settings that are set."""
    settings = usersettings.load_settings()
    result = {}
    for name, (key, is_bool) in KEYS.items():
        value = settings.get(name)
        if is_bool and isinstance(value, bool):
            result[key] = "True" if value else "False"
        elif not is_bool and isinstance(value, str) and value:
            result[key] = value
    return result


HIDDEN = ("password", "webApiKey")  # block keys whose values are never shown


def _lines(values):
    return [f"   {key} = {'(hidden)' if key in HIDDEN else value}" for key, value in values.items()]


def _indent(text):
    found = re.search(r"\n([ \t]+)\S", text)
    return found.group(1) if found else 4


MISSING = object()


def allowed():
    """{section: [keys]} that spruce_settings may hold (data/spruce-settings.json)."""
    from . import spruce_syncthing
    sections = store.repo_json("spruce-settings")["sections"]
    if not spruce_syncthing.enabled():
        return sections
    forced = spruce_syncthing.forced_keys()
    return {section: [k for k in keys if (section, k) not in forced] for section, keys in sections.items()}


def wanted_settings():
    """[(section, key, value)] of the allowlisted spruce_settings entries; others, and a malformed value, are warned about once.
    While Syncthing is on, the keys it forces are dropped without a warning."""
    from . import spruce_syncthing
    saved = usersettings.load_settings().get("spruce_settings")
    if saved is None:
        return []
    if not isinstance(saved, dict) or not all(isinstance(v, dict) for v in saved.values()):
        ui.warn("spruce_settings in settings.json must be {section: {key: value}}; ignored")
        return []
    allow = allowed()
    forced = spruce_syncthing.forced_keys() if spruce_syncthing.enabled() else set()
    result, unknown = [], []
    for section, keys in saved.items():
        for key, value in keys.items():
            if (section, key) in forced:
                continue
            if key in allow.get(section, ()):
                result.append((section, key, value))
            else:
                unknown.append(f"{section} / {key}")
    if unknown:
        ui.warn(f"spruce_settings in settings.json has settings that aren't shared, ignored: {', '.join(unknown)}")
    return result


def _options(base, shown):
    """(file text, parsed data, its menuOptions dict) of the card's spruce-config.json, or None with a warning when it's missing or can't be read."""
    path = os.path.join(base, FILE)
    path = os.path.join(base, FILE)
    if not os.path.isfile(path):
        ui.warn(f"{shown} is missing; spruce settings skipped (start the card in the device once first)")
        return None
    old = cardfs.text(path)
    try:
        data = json.loads(old)
    except ValueError:
        data = None
    options = data.get("menuOptions") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        ui.warn(f"{shown} can't be read as Spruce settings; spruce settings skipped")
        return None
    return old, data, options


def _selected(options, section, key):
    """The entry dict of section / key, or None."""
    found = options.get(section)
    entry = found.get(key) if isinstance(found, dict) else None
    return entry if isinstance(entry, dict) else None


def entries(card, base):
    """[Entry] for every saved spruce setting that applies to the card's spruce-config.json, changed or not; [] when it can't be used."""
    from . import spruce_syncthing
    values = wanted()
    extra = wanted_settings()
    forced = spruce_syncthing.forced_settings(card)
    if not values and not extra and not forced:
        return []
    shown = FILE.replace(os.sep, "/")
    found = _options(base, shown)
    if not found:
        return []
    options = found[2]
    result = []
    for key, value in values.items():
        entry = _selected(options, BLOCK, key)
        result.append(applied.Entry(shown, f"{BLOCK} / {key}", entry.get("selected") if entry else None, value, key in HIDDEN))
    for section, key, value in extra:
        entry = _selected(options, section, key)
        if entry:
            result.append(applied.Entry(shown, f"{section} / {key}", entry.get("selected"), value, False))
    for section, key, value in forced:
        entry = _selected(options, section, key)
        if entry:
            result.append(applied.Entry(shown, f"{section} / {key} (Syncthing)", entry.get("selected"), value, False))
        else:
            ui.warn(f"{shown} has no {section} / {key}; update spruceOS for Syncthing saves to work")
    return result


def install(card, layout_name, base, dry_run):
    """Set the saved spruce settings in a spruce card's spruce-config.json, keeping everything else in it: the RetroAchievements
    ones, and the allowlisted spruce_settings whose section and key the file already has.
    The failure count (always 0: a file that can't be used is warned about and skipped)."""
    if layout_name != "spruce":
        return 0
    from . import spruce_syncthing
    values = wanted()
    extra = wanted_settings()
    forced = spruce_syncthing.forced_settings(card)
    if not values and not extra and not forced:
        return 0
    shown = FILE.replace(os.sep, "/")
    found = _options(base, shown)
    if not found:
        return 0
    old, data, options = found
    lines = []
    if values:
        block = options.get(BLOCK)
        if not isinstance(block, dict):
            block = options[BLOCK] = {}
        for key, value in values.items():
            entry = block.get(key)
            if isinstance(entry, dict):
                entry["selected"] = value
            else:
                block[key] = {"selected": value}
        lines += _lines(values)
    for section, key, value in extra:
        entry = _selected(options, section, key)
        if isinstance(entry, dict) and entry.get("selected") != value:
            entry["selected"] = value
            lines.append(f"   {section} / {key} = {value}")
    for section, key, value in forced:
        entry = _selected(options, section, key)
        if not isinstance(entry, dict):
            ui.warn(f"{shown} has no {section} / {key}; update spruceOS for Syncthing saves to work")
        elif entry.get("selected") != value:
            entry["selected"] = value
            lines.append(f"   {section} / {key} = {value} (Syncthing)")
    if json.loads(old) == data:
        return 0
    new = json.dumps(data, indent=_indent(old), ensure_ascii=False) + ("\n" if old.endswith("\n") else "")
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would set {len(lines)} spruce setting(s) in {shown}"))
        print(ui.dim("\n".join(lines)))
        return 0
    cardfs.write_text(os.path.join(base, FILE), new)
    print(f"🏆 Spruce settings → {shown} ({len(lines)} set)")
    print("\n".join(lines))
    return 0


def import_settings(path):
    """Copy the allowlisted settings' current values from the spruce card at path into settings.json's spruce_settings."""
    file = os.path.join(path, FILE)
    shown = FILE.replace(os.sep, "/")
    try:
        data = json.loads(cardfs.text(file))
    except (OSError, ValueError):
        data = None
    options = data.get("menuOptions") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        ui.fail(f"{file} isn't a readable Spruce settings file; is {path} a spruce card that has been started once?", 2)
    settings = usersettings.load_settings()
    saved = settings.get("spruce_settings")
    saved = {s: dict(k) for s, k in saved.items()} if isinstance(saved, dict) and all(isinstance(k, dict) for k in saved.values()) else {}
    same, changed = [], []  # (section, key, card value, saved value or MISSING)
    for section, keys in allowed().items():
        found = options.get(section)
        for key in keys:
            entry = found.get(key) if isinstance(found, dict) else None
            if isinstance(entry, dict) and "selected" in entry:
                have = saved.get(section, {}).get(key, MISSING)
                (same if have == entry["selected"] and type(have) is type(entry["selected"]) else changed).append((section, key, entry["selected"], have))
    if not same and not changed:
        ui.fail(f"{shown} has none of the settings that can be saved", 2)
    if same:
        print(ui.bold(f"Identical ({len(same)}):"))
        print(ui.dim("\n".join(f"   {s} / {k} = {v}" for s, k, v, _ in same)))
    if not changed:
        print(ui.green("Nothing differs from what settings.json has; nothing to import."))
        return 0
    print(ui.bold(f"Different or new ({len(changed)}):"))
    print("\n".join(f"   {s} / {k} = {v}" if old is MISSING else f"   {s} / {k} = {old} -> {v}" for s, k, v, old in changed))
    answer = ui.choose_required(f"Import these {len(changed)} setting(s)? Yes, No, or Pick one by one", "ynp")
    if answer == "n":
        print("Nothing imported.")
        return 0
    if answer == "p":
        accepted = [c for c in changed
                    if ui.choose_required(f"   {c[0]} / {c[1]} = {c[2]}: import?", "yn") == "y"]
    else:
        accepted = changed
    if not accepted:
        print("Nothing imported.")
        return 0
    for section, key, value, _ in accepted:
        saved.setdefault(section, {})[key] = value
    settings["spruce_settings"] = saved
    usersettings.save_settings(settings)
    print(ui.green(f"💾 Saved {len(accepted)} spruce setting(s) from {shown} in settings.json"))
    return 0
