"""Spruce collections: the one Collections/collections.json PyUI reads, which holds every collection."""
import json
import os

from . import frontend, ui

FILE = os.path.join("Collections", "collections.json")
ROMS = "/mnt/SDCARD/Roms"


def wanted(collections, systems, on_card):
    """{safe name: [game entries]} of the collections' games that are on the card, on the systems it syncs."""
    result = {}
    for name, folder, rel in frontend.collection_roms("spruce", collections, systems, on_card):
        result.setdefault(name, []).append({"rom_file_path": f"{ROMS}/{folder}/{rel}", "game_system_name": folder})
    return result


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


def plan(base, wanted, owned, keep=False):
    """What to write on the card for the wanted {name: [entries]}, given the names sync-roms owns. Collections sync-roms
    doesn't own (made on the device) are kept as they are."""
    result = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": [], "unreadable": False}
    current = _read(base)
    if current is None:
        result["unreadable"] = True  # the collections stay on the device, so the art step leaves their pictures alone
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
    frontend.retired(result, owned, keep)
    kept += [c for c in current if c.get("collection_name") in result.get("kept", [])]
    text = json.dumps(kept + added, indent=4) + "\n"
    if (current or added) and json.dumps(current, indent=4) + "\n" != text:
        result["writes"].append((os.path.join(base, FILE), text))
    return result


def apply(plan):
    """Write plan's collections file."""
    frontend.write_files(plan)


def describe(plan):
    """Print what apply(plan) would do."""
    for _ in plan["writes"]:
        print(ui.dim(f"💖 would write {FILE.replace(os.sep, '/')} ({len(plan['enable'])} sync-roms collection(s))"))
    for warning in plan["warnings"]:
        ui.warn(warning)
