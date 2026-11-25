"""The saved settings written into a Knulli card's system/knulli.conf (key=value lines), merged in place: only the wanted
keys' lines change, everything else (other keys, comments, order) stays. The file is never created; Knulli makes it on first boot."""
import os
import re

from . import applied, cardfs, spruce_wifi, ui, usersettings
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


def wanted(current):
    """{key: value} of every setting to write, given the file's current values."""
    return {**ra_values(), **wifi_values(current)}


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
