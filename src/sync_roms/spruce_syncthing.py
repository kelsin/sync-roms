"""The Syncthing settings sync puts on spruce cards (data/syncthing.json), switched off by `syncthing: false`."""
import glob
import json
import os
import re

from . import applied, cardfs, spruce_emu, store, ui, usersettings

NO_WIFI_SKIPS = ("Network Settings", "enableSyncthing")


def data():
    return store.repo_json("syncthing")


def enabled():
    return usersettings.load_settings().get("syncthing") is not False


def forced_keys():
    """Every (section, key) the Syncthing data sets on a spruce card."""
    return {(section, key) for section, keys in data()["spruce"]["settings"].items() for key in keys}


def forced_settings(card):
    """[(section, key, value)] sync sets on the card's spruce-config.json: [] when off, and without enableSyncthing on a device with no WiFi."""
    if not enabled():
        return []
    device = store.saved_card(card).get("device")
    no_wifi = any(d.get("id") == device and d.get("network") is False for d in store.repo_json("devices"))
    return [(section, key, value) for section, keys in data()["spruce"]["settings"].items()
            for key, value in keys.items() if not (no_wifi and (section, key) == NO_WIFI_SKIPS)]


def _cores(base, warnings):
    """Yield (folder, core, path, old text, config) for each Emu/<FOLDER>/config.json that exists and can be read."""
    seen = set()
    systems = {s["bucket"]: s for s in store.repo_json("systems")}
    for system, core in data()["cores"].items():
        folder = systems.get(system, {}).get("folders", {}).get("spruce")
        if not folder or folder in seen:
            continue
        seen.add(folder)
        path = os.path.join(base, "Emu", folder, "config.json")
        try:
            old = cardfs.text(path)
            if not old:
                continue
            config = json.loads(old)
            if not isinstance(config, dict):
                raise ValueError
        except (OSError, ValueError):
            warnings.append(f"Emu/{folder}/config.json can't be read; its core left as it is")
            continue
        yield folder, core, path, old, config


def _offering(config, core):
    """[entry dict] of the config's Emulator* entries that offer the core."""
    options = config.get("menuOptions")
    return [entry for key, entry in (options.items() if isinstance(options, dict) else [])
            if key.startswith("Emulator") and isinstance(entry, dict) and isinstance(entry.get("options"), list)
            and core in entry["options"]]


def core_writes(base):
    """(writes [(path, text)], lines, warnings): each Emu/<FOLDER>/config.json that exists, with the Syncthing core selected in every Emulator* entry that offers it."""
    writes, lines, warnings = [], [], []
    for folder, core, path, old, config in _cores(base, warnings):
        changed = False
        for entry in _offering(config, core):
            if entry.get("selected") != core:
                entry["selected"] = core
                changed = True
        if changed:
            writes.append((path, spruce_emu._dump(config, old)))
            lines.append(f"   Emu/{folder}: {core}")
    return writes, lines, warnings


def _pattern(key):
    return re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=.*?(?=\r?$)", re.M)


def retroarch_writes(base):
    """(writes, lines, warnings): each Saves/ra-configs/retroarch-*.cfg with the Syncthing save settings set, other lines kept."""
    paths = sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "ra-configs", "retroarch-*.cfg")))
    if not paths:
        return [], [], ["Saves/ra-configs has no retroarch-*.cfg yet; launch a game once on the device, then sync again for RetroArch's save settings"]
    writes, lines, warnings = [], [], []
    for path in paths:
        try:
            old = cardfs.read(path).decode("utf-8")  # raw: cardfs.text would turn CRLF into LF
        except (OSError, ValueError):
            warnings.append(f"Saves/ra-configs/{os.path.basename(path)} can't be read; its save settings left as they are")
            continue
        eol = "\r\n" if "\r\n" in old else "\n"
        new = old
        for key, value in data()["retroarch"].items():
            line = f'{key} = "{value}"'
            pattern = _pattern(key)
            if pattern.search(new):
                updated = pattern.sub(lambda m: m.group(0) if m.group(0) == line or _same(m.group(0), value) else line, new)
            else:
                updated = new + ("" if not new or new.endswith("\n") else eol) + line + eol
            if updated != new:
                new = updated
                lines.append(f"   {os.path.basename(path)}: {key} = {value}")
        if new != old:
            writes.append((path, new))
    return writes, lines, warnings


def _same(line, value):
    """True when a cfg line already holds value (quoted or not)."""
    return line.split("=", 1)[1].strip().strip('"') == value


def entries(card, base):
    """[Entry] for every Syncthing core and RetroArch save setting, changed or not; [] when Syncthing is off."""
    if not enabled():
        return []
    warnings = []
    result = []
    for folder, core, _, _, config in _cores(base, warnings):
        offering = _offering(config, core)
        if offering:
            old = next((e.get("selected") for e in offering if e.get("selected") != core), core)
            result.append(applied.Entry(f"Emu/{folder}/config.json", "core", old, core, False))
    for path in sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "ra-configs", "retroarch-*.cfg"))):
        try:
            text = cardfs.read(path).decode("utf-8")
        except (OSError, ValueError):
            continue  # retroarch_writes warns about it below
        for key, value in data()["retroarch"].items():
            found = _pattern(key).search(text)
            old = found.group(0).split("=", 1)[1].strip().strip('"') if found else None
            result.append(applied.Entry(f"Saves/ra-configs/{os.path.basename(path)}", key, old, value, False))
    for warning in warnings + retroarch_writes(base)[2]:
        ui.warn(warning)
    return result


def run(card, layout_name, base, dry_run):
    """Set the Syncthing cores and RetroArch save settings on a spruce card. 0: a problem is a warning."""
    if layout_name != "spruce" or not enabled():
        return 0
    writes, lines, warnings = [], [], []
    for part in (core_writes(base), retroarch_writes(base)):
        writes += part[0]
        lines += part[1]
        warnings += part[2]
    for warning in warnings:
        ui.warn(warning)
    if not writes:
        return 0
    if dry_run:
        print(ui.dim("🧪 Dry run: would set for Syncthing:"))
        for line in lines:
            print(ui.dim(line))
        return 0
    for path, text in writes:
        cardfs.write_text(path, text)
    print(ui.green(f"🔄 Syncthing: set {len(lines)} setting(s) so saves and states sync"))
    for line in lines:
        print(line)
    return 0
