"""Spruce collections: the one Collections/collections.json PyUI reads, which holds every collection."""
import json
import os

from . import downloads, frontend, store, ui

FILE = os.path.join("Collections", "collections.json")
ROMS = "/mnt/SDCARD/Roms"


def wanted(collections, systems, on_card):
    """{safe name: [game entries]} of the collections' games that are on the card, on the systems it syncs."""
    by_bucket = {s["bucket"]: s for s in systems}
    result = {}
    for collection in collections:
        name = frontend.safe_name(collection["name"])
        for game in collection["games"]:
            system = by_bucket.get(game["system"])
            folder = system and system["folders"].get("spruce")
            if not folder:
                continue
            rel = downloads.rom_rel(game["bucket"])
            if on_card(system, rel):
                entry = {"rom_file_path": f"{ROMS}/{folder}/{rel}", "game_system_name": folder}
                result.setdefault(name, []).append(entry)
    return {name: games for name, games in result.items() if name and games}


def _read(base):
    """The file's collections ([] when there is none), or None when it can't be read as a list of collections."""
    try:
        with open(os.path.join(base, FILE), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        return None
    ok = isinstance(data, list) and all(isinstance(c, dict) and isinstance(c.get("game_list"), list) for c in data)
    return data if ok else None


def plan(base, wanted, owned):
    """What to write on the card for the wanted {name: [entries]}, given the names sync-roms owns. Collections sync-roms
    doesn't own (made on the device) are kept as they are."""
    result = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": []}
    current = _read(base)
    if current is None:
        if wanted or owned:
            result["warnings"].append(f"{FILE.replace(os.sep, '/')} can't be read; Spruce collections skipped")
        result["owned"] = list(owned)
        return result
    others = {c.get("collection_name") for c in current if c.get("collection_name") not in owned}
    kept = [c for c in current if c.get("collection_name") in others]
    added = []
    for name in sorted(wanted):
        if name in others:
            result["warnings"].append(f"Spruce already has a collection {name} that sync-roms didn't write; skipped")
            continue
        added.append({"collection_name": name, "game_list": wanted[name]})
        result["enable"].add(name)
    result["owned"] = sorted(result["enable"])
    for name in dict.fromkeys(owned):
        if not name or frontend.safe_name(name) != name:
            result["warnings"].append(f"ignoring the recorded collection name {name!r}; it isn't a valid name")
        elif name not in result["enable"]:
            result["disable"].add(name)
    text = json.dumps(kept + added, indent=4) + "\n"
    if (current or added) and json.dumps(current, indent=4) + "\n" != text:
        result["writes"].append((os.path.join(base, FILE), text))
    return result


def apply(plan):
    """Write plan's collections file."""
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.replace_file(path, text, newline="\n")


def describe(plan):
    """Print what apply(plan) would do."""
    for _ in plan["writes"]:
        print(ui.dim(f"💖 would write {FILE.replace(os.sep, '/')} ({len(plan['enable'])} sync-roms collection(s))"))
    for warning in plan["warnings"]:
        ui.warn(warning)
