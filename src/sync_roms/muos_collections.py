"""muOS collections: where each storage choice is mounted on the device, and the collection entries on the card."""
import contextlib
import os
import posixpath

from . import frontend, ui

MOUNTS = {"sd1": "/mnt/mmc", "sd2": "/mnt/sdcard"}
COLLECTION_DIR = os.path.join("MUOS", "info", "collection")


def mount(entry):
    """The mount of a card's muOS storage (default sd1), or None when the value is unknown."""
    storage = entry.get("muos_storage", "sd1")
    return MOUNTS.get(storage) if isinstance(storage, str) else None


def fnv1a32(data):
    """The 32-bit FNV-1a hash of data (bytes)."""
    h = 2166136261
    for byte in data:
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


def entry_lines(mount, folder, rel):
    """The three lines of a collection entry: the ROM's path on the device, its folder under ROMS/, its name."""
    subdir = posixpath.dirname(rel)
    stem = posixpath.splitext(posixpath.basename(rel))[0]
    return [f"{mount}/ROMS/{folder}/{rel}", f"{folder}/{subdir}" if subdir else folder, stem]


def entry_path(base, collection, folder, rel, mount):
    """The collection entry's .cfg file on the card."""
    lines = entry_lines(mount, folder, rel)
    name = f"{lines[2]}-{fnv1a32(lines[0].encode('utf-8')):08X}.cfg"
    return os.path.join(base, COLLECTION_DIR, collection, name)


def wanted(collections, systems, on_card, mount):
    """{safe name: {path under the card: text}} of the collections' games that are on the card, on the systems it syncs."""
    result = {}
    for name, folder, rel in frontend.collection_roms("muos", collections, systems, on_card):
        result.setdefault(name, {})[entry_path("", name, folder, rel, mount)] = "\n".join(entry_lines(mount, folder, rel))
    return result


def _cfgs(base, name):
    """The .cfg files in a collection's folder, as paths under base."""
    folder = os.path.join(base, COLLECTION_DIR, name)
    try:
        return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".cfg")]
    except OSError:
        return []


def plan(base, wanted, owned):
    """What to write and delete on the card for the wanted {name: {path: text}}, given the names sync-roms owns."""
    result = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": []}
    for name in sorted(wanted):
        folder = os.path.join(base, COLLECTION_DIR, name)
        if name not in owned and _cfgs(base, name):
            result["warnings"].append(f"muOS already has a collection folder {name} that sync-roms didn't write; skipped")
            continue
        files = {os.path.join(base, rel): text for rel, text in wanted[name].items()}
        result["writes"] += [(p, t) for p, t in sorted(files.items()) if not frontend.same(p, t)]
        result["deletes"] += [p for p in _cfgs(base, name) if p not in files]
        result["enable"].add(name)
    result["owned"] = sorted(result["enable"])
    for name in frontend.retired(result, owned):
        result["deletes"] += _cfgs(base, name)
    return result


def apply(plan):
    """Write and delete plan's collection entries."""
    frontend.write_files(plan)
    for path in plan["deletes"]:
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)
        try:
            os.rmdir(os.path.dirname(path))  # only when the drop emptied it
        except OSError:
            pass


def describe(plan):
    """Print what apply(plan) would do."""
    for path, _ in plan["writes"]:
        print(ui.dim(f"💖 would write {os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}"))
    for path in plan["deletes"]:
        print(ui.dim(f"💖 would delete {os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}"))
    for warning in plan["warnings"]:
        ui.warn(warning)
