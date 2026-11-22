"""Spruce's Emu/<folder>/config.json: the ignore list that hides BIOS zips from PyUI's game list."""
import copy
import json
import os
import re

from . import cardfs, ui

OLD_FOLDERS = ("FBNEO",)  # folders earlier syncs used for a system that now uses another


def legacy_systems(systems):
    """Stand-in systems for the OLD_FOLDERS no system uses now, so sync clears what an earlier sync left in them."""
    used = {s["folders"].get("spruce") for s in systems}
    return [{"name": f"{folder} (old)", "bucket": f"old-{folder.lower()}", "folders": {"spruce": folder}, "bios": {}}
            for folder in OLD_FOLDERS if folder not in used]


def wanted(systems, has_roms):
    """{folder: [BIOS file names]} that the systems with ROMs to sync put in their ROM folder (bios.rom_files)."""
    result = {}
    for s in systems:
        folder = s["folders"].get("spruce")
        names = [os.path.basename(f) for f in s["bios"].get("rom_files", [])]
        if folder and names and has_roms(s):
            result.setdefault(folder, [])
            result[folder] += [n for n in names if n not in result[folder]]
    return {folder: sorted(names) for folder, names in result.items()}


def _names(value):
    return [n for n in value if isinstance(n, str)] if isinstance(value, list) else []


def _dump(data, text):
    """data as JSON in text's indentation and with its trailing line end."""
    found = re.search(r'\n([ \t]+)\S', text)
    out = json.dumps(data, indent=found.group(1) if found else None, ensure_ascii=False)
    return out + ("\n" if text.endswith("\n") else "")


def plan(base, wanted_by_folder, owned):
    """What to write for each folder's Emu/<folder>/config.json ignoreList: {"writes": [(path, text)], "owned":
    {folder: [names sync-roms added]}, "warnings"}. owned: that record from the last sync. Names it didn't add (the
    ones Spruce ships, the user's) are kept; an added name is removed once it isn't wanted."""
    owned = owned if isinstance(owned, dict) else {}
    result = {"writes": [], "owned": {}, "warnings": []}
    for folder in sorted({*wanted_by_folder, *owned}):
        want, before = wanted_by_folder.get(folder, []), _names(owned.get(folder))
        if not want and not before:
            continue
        path = os.path.join(base, "Emu", folder, "config.json")
        text = cardfs.text(path)
        try:
            data = json.loads(text)
            if not isinstance(data, dict) or not isinstance(data.get("ignoreList", []), list):
                raise ValueError
        except ValueError:
            result["warnings"].append(f"Emu/{folder}/config.json is missing or can't be read; its ignore list skipped")
            result["owned"][folder] = before
            continue
        current = data.get("ignoreList", [])
        mine = [n for n in want if n in before or n not in current]
        new = [n for n in current if n not in set(before) - set(want)]
        new += [n for n in want if n not in new]
        if mine:
            result["owned"][folder] = mine
        if new != current:
            data = copy.deepcopy(data)
            data["ignoreList"] = new
            result["writes"].append((path, _dump(data, text)))
    return result


def apply(plan):
    """Write plan's config files."""
    for path, text in plan["writes"]:
        cardfs.write_text(path, text)


def describe(plan):
    """Print what apply(plan) would do."""
    for path, _ in plan["writes"]:
        print(ui.dim(f"🎮 would update {'/'.join(path.replace(os.sep, '/').split('/')[-3:])} (ignored BIOS zips)"))
    for warning in plan["warnings"]:
        ui.warn(warning)
