"""muOS collections: where each storage choice is mounted on the device, and the collection entries on the card."""
import os
import posixpath

from . import downloads, frontend, store, ui

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
    by_bucket = {s["bucket"]: s for s in systems}
    result = {}
    for collection in collections:
        name = frontend.safe_name(collection["name"])
        for game in collection["games"]:
            system = by_bucket.get(game["system"])
            folder = system and system["folders"].get("muos")
            if not folder:
                continue
            rel = downloads.rom_rel(game["bucket"])
            if on_card(system, rel):
                text = "\n".join(entry_lines(mount, folder, rel))
                result.setdefault(name, {})[entry_path("", name, folder, rel, mount)] = text
    return {name: files for name, files in result.items() if name and files}


def _cfgs(base, name):
    """The .cfg files in a collection's folder, as paths under base."""
    folder = os.path.join(base, COLLECTION_DIR, name)
    try:
        return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".cfg")]
    except OSError:
        return []


def _same(path, text):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read() == text
    except (OSError, UnicodeDecodeError):
        return False


def plan(base, wanted, owned):
    """What to write and delete on the card for the wanted {name: {path: text}}, given the names sync-roms owns."""
    result = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": []}
    for name in sorted(wanted):
        folder = os.path.join(base, COLLECTION_DIR, name)
        if name not in owned and _cfgs(base, name):
            result["warnings"].append(f"muOS already has a collection folder {name} that sync-roms didn't write; skipped")
            continue
        files = {os.path.join(base, rel): text for rel, text in wanted[name].items()}
        result["writes"] += [(p, t) for p, t in sorted(files.items()) if not _same(p, t)]
        result["deletes"] += [p for p in _cfgs(base, name) if p not in files]
        result["enable"].add(name)
    result["owned"] = sorted(result["enable"])
    for name in dict.fromkeys(owned):
        if not name or frontend.safe_name(name) != name:
            result["warnings"].append(f"ignoring the recorded collection name {name!r}; it isn't a valid name")
            continue
        if name not in result["enable"]:
            result["disable"].add(name)
            result["deletes"] += _cfgs(base, name)
    return result


def apply(plan):
    """Write and delete plan's collection entries."""
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.replace_file(path, text, newline="\n")
    for path in plan["deletes"]:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
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


ART_DIR = os.path.join("MUOS", "info", "catalogue", "Collection")
ART_OWNED = ".sync-roms-art"  # the collection folder names sync-roms gave art, one per line
ART_KINDS = ("box", "grid")


def _art_owned(base):
    try:
        with open(os.path.join(base, ART_DIR, ART_OWNED), encoding="utf-8") as f:
            return [n for n in f.read().splitlines() if n and frontend.safe_name(n) == n]
    except OSError:
        return []


def install_art(base, arts):
    """Put the collections' art ({name: art png}) in muOS's catalogue as box and grid pictures, and remove what
    sync-roms put there for collections no longer in arts. Returns whether files changed."""
    changed = False
    for name, png in arts.items():
        with open(png, "rb") as f:
            data = f.read()
        for kind in ART_KINDS:
            path = os.path.join(base, ART_DIR, kind, f"{name}.png")
            try:
                with open(path, "rb") as f:
                    if f.read() == data:
                        continue
            except OSError:
                pass
            os.makedirs(os.path.dirname(path), exist_ok=True)
            store.replace_file(path, data)
            changed = True
    owned = _art_owned(base)
    for name in dict.fromkeys(owned):
        if name not in arts:
            for kind in ART_KINDS:
                try:
                    os.remove(os.path.join(base, ART_DIR, kind, f"{name}.png"))
                    changed = True
                except FileNotFoundError:
                    pass
    names = sorted(arts)
    if names != owned:
        if names:
            os.makedirs(os.path.join(base, ART_DIR), exist_ok=True)
            store.replace_file(os.path.join(base, ART_DIR, ART_OWNED), "".join(f"{n}\n" for n in names), newline="\n")
        else:
            try:
                os.remove(os.path.join(base, ART_DIR, ART_OWNED))
            except FileNotFoundError:
                pass
    return changed


def describe_art(base, arts):
    """Print what install_art would do."""
    if arts:
        print(ui.dim(f"🎨 would add art for {', '.join(arts)} to {ART_DIR.replace(os.sep, '/')}/"))
