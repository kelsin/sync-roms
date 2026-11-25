"""The saved settings written into a Knulli card's system/knulli.conf (key=value lines), merged in place: only the wanted
keys' lines change, everything else (other keys, comments, order) stays. The file is never created; Knulli makes it on first boot."""
import os
import re

from . import applied, cardfs, spruce_wifi, store, ui, usersettings
from .spruce_settings import API_KEY, MODES

FILE = os.path.join("system", "knulli.conf")
SHOWN = "system/knulli.conf"
SECRET = frozenset({"global.retroachievements.password", "global.retroachievements.webapikey",
                    "wifi.key", "wifi2.key", "wifi3.key"})
RA = "global.retroachievements"


def _split(line):
    """(key, value) of an active line, else None."""
    if line.lstrip().startswith("#") or "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key.strip(), value.rstrip("\r").lstrip(" \t")


def parse(text):
    """{key: value} of the active lines; the last one wins."""
    return dict(found for found in map(_split, text.split("\n")) if found)


def merge(text, values):
    """text with every active line of a wanted key set to its value, and the keys with none appended."""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    seen = set()
    for i, line in enumerate(lines):
        found = _split(line)
        if found and found[0] in values:
            lines[i] = f"{found[0]}={values[found[0]]}"
            seen.add(found[0])
    lines += [f"{key}={value}" for key, value in values.items() if key not in seen]
    return "\n".join(lines) + "\n" if lines else ""


def ra_values():
    """{key: value} of the RetroAchievements settings that are set."""
    settings = usersettings.load_settings()
    result = {}
    mode = settings.get("ra_mode")
    if mode == "Disabled":
        result[RA] = "0"
    elif mode in MODES and mode != "Manual":
        result[RA] = "1"
        result[f"{RA}.hardcore"] = "1" if mode == "Hardcore" else "0"
    for name, key in (("ra_username", "username"), ("ra_password", "password")):
        value = settings.get(name)
        if isinstance(value, str) and value:
            result[f"{RA}.{key}"] = value
    key = settings.get("ra_api_key")
    if isinstance(key, str) and key.strip():
        if API_KEY.fullmatch(key.strip()):
            result[f"{RA}.webapikey"] = key.strip()
        else:
            ui.warn(f"ra_api_key isn't a RetroAchievements Web API key (32 letters and digits); not written to {SHOWN}")
    return result


SLOTS = ("wifi", "wifi2", "wifi3")


def wifi_values(current):
    """{key: value} for the wifi slots: the saved networks first, then the ones already in the file, cut to three slots."""
    mine = spruce_wifi.wanted()
    if not mine:
        return {}
    ssids = {ssid for ssid, _ in mine}
    device = [(current[f"{slot}.ssid"], current.get(f"{slot}.key", "")) for slot in SLOTS
              if current.get(f"{slot}.ssid") and current[f"{slot}.ssid"] not in ssids]
    final = mine + device
    kept = final[:len(SLOTS)]
    for label, lost in (("saved", [n for n in mine if n not in kept]), ("device", [n for n in device if n not in kept])):
        if lost:
            ui.warn(f"Only {len(SLOTS)} WiFi networks fit in {SHOWN}; not written ({label}): {', '.join(ssid for ssid, _ in lost)}")
    result = {}
    for slot, (ssid, psk) in zip(SLOTS, final):
        result[f"{slot}.ssid"] = ssid
        result[f"{slot}.key"] = psk
    return result


def hotkey_values():
    """{key: value} of the shared hotkey scheme as Knulli remaps it."""
    return dict(store.repo_json("hotkeys")["knulli"])


def allowed():
    """The keys knulli_settings may hold (data/knulli-settings.json)."""
    return store.repo_json("knulli-settings")["keys"]


def _saved():
    """The saved knulli_settings as {key: value}; {} (with a warning) when malformed."""
    saved = usersettings.load_settings().get("knulli_settings")
    if saved is None:
        return {}
    if not isinstance(saved, dict) or not all(isinstance(v, str) for v in saved.values()):
        ui.warn("knulli_settings in settings.json must be {key: value}; ignored")
        return {}
    return saved


def wanted_settings():
    """{key: value} of the allowlisted knulli_settings entries; the others are warned about once."""
    saved = _saved()
    allow = allowed()
    unknown = [key for key in saved if key not in allow]
    if unknown:
        ui.warn(f"knulli_settings in settings.json has settings that aren't shared, ignored: {', '.join(unknown)}")
    return {key: value for key, value in saved.items() if key in allow}


def wanted(current):
    """{key: value} of every setting to write, given the file's current values."""
    return {**ra_values(), **wifi_values(current), **hotkey_values(), **wanted_settings()}


def entries(base):
    """[Entry] for every wanted key, changed or not; [] (with a warning when the file is missing) when nothing applies."""
    path = os.path.join(base, FILE)
    if not os.path.isfile(path):
        ui.warn(f"{SHOWN} is missing; Knulli settings skipped (boot the card once in Knulli Scarab first)")
        return []
    current = parse(cardfs.text(path))
    return [applied.Entry(SHOWN, key, current.get(key), value, key in SECRET) for key, value in wanted(current).items()]


def install(card, layout_name, base, dry_run):
    """Write the saved settings into a knulli card's system/knulli.conf. The failure count (always 0)."""
    if layout_name != "knulli":
        return 0
    found = entries(base)
    applied.show([e for e in found if applied.changed(e)] if not dry_run else found, dry_run)
    if dry_run or not any(applied.changed(e) for e in found):
        return 0
    path = os.path.join(base, FILE)
    cardfs.write_text(path, merge(cardfs.text(path), {e.key: e.new for e in found}))
    return 0


def import_settings(path):
    """Copy the allowlisted settings' current values from the Knulli card at path into settings.json's knulli_settings."""
    file = os.path.join(path, FILE)
    if not os.path.isfile(file):
        ui.fail(f"{file} is missing; is {path} a Knulli card that has been booted once?", 2)
    current = parse(cardfs.text(file))
    settings = usersettings.load_settings()
    saved = settings.get("knulli_settings")
    saved = dict(saved) if isinstance(saved, dict) and all(isinstance(v, str) for v in saved.values()) else {}
    same, changed = [], []  # (key, card value, saved value or None)
    for key in allowed():
        if key in current:
            have = saved.get(key)
            (same if have == current[key] else changed).append((key, current[key], have))
    if not same and not changed:
        ui.fail(f"{SHOWN} has none of the settings that can be saved", 2)
    if same:
        print(ui.bold(f"Identical ({len(same)}):"))
        print(ui.dim("\n".join(f"   {k} = {v}" for k, v, _ in same)))
    if not changed:
        print(ui.green("Nothing differs from what settings.json has; nothing to import."))
        return 0
    print(ui.bold(f"Different or new ({len(changed)}):"))
    print("\n".join(f"   {k} = {v}" if old is None else f"   {k} = {old} -> {v}" for k, v, old in changed))
    answer = ui.choose_required(f"Import these {len(changed)} setting(s)? Yes, No, or Pick one by one", "ynp")
    if answer == "n":
        print("Nothing imported.")
        return 0
    if answer == "p":
        accepted = [c for c in changed if ui.choose_required(f"   {c[0]} = {c[1]}: import?", "yn") == "y"]
    else:
        accepted = changed
    if not accepted:
        print("Nothing imported.")
        return 0
    for key, value, _ in accepted:
        saved[key] = value
    settings["knulli_settings"] = saved
    usersettings.save_settings(settings)
    print(ui.green(f"💾 Saved {len(accepted)} Knulli setting(s) from {SHOWN} in settings.json"))
    return 0
