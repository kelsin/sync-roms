"""Proper game names for MAME and FBNeo sets, whose file names are short codes ("1941j.zip"), and for PICO-8 carts.

A set's name comes from the system's scraped metadata.json in storage, else the file name. A copy of each metadata file's names is kept in the data folder with the storage file's tag, and the file is
downloaded again once per run when that tag changes."""
import json
import os
import threading

from . import inventory, s3, scrape_plan, shared, store, ui

KEY = "names.json"
SYSTEMS = ("mame", "fbneo", "pico8", "ports")
_lock = threading.RLock()
_scraped = None  # {system: {ROM path: name}}, filled per system on first use this run


def _local_path():
    return os.path.join(store.cache_dir(), KEY)


def _load_local():
    try:
        with open(_local_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_local(data):
    try:
        os.makedirs(store.cache_dir(), exist_ok=True)
        store.write_json(_local_path(), data, indent=2)
    except OSError as e:
        ui.warn(f"Couldn't save the local copy of {KEY} ({e})")


def _entry_names(entry):
    names = entry.get("names") if isinstance(entry, dict) else None
    if not isinstance(names, dict):
        return {}
    return {rom: name for rom, name in names.items() if isinstance(name, str)}


def _load(system):
    local = _load_local()
    entry = local.get(system)
    try:
        key = scrape_plan.metadata_key(system)
        tag = inventory.tag(key)
        if tag is not None and not (isinstance(entry, dict) and entry.get("tag") == tag):
            try:
                text = shared.read(key)
            except s3.ERRORS as e:
                if not s3.missing(e):
                    raise
                tag = None
            else:
                data = scrape_plan.parse_metadata(text, key)
                found = {rom: v["name"] for rom, v in data.items()
                         if isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"]}
                local[system] = {"tag": tag, "names": found}
                _save_local(local)
                return found
        if tag is None:
            if system in local:
                del local[system]
                _save_local(local)
            return {}
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't check scraped names for {system} ({e}); using the local copy")
    return _entry_names(entry)


def title(key):
    """A storage key's display name: the proper name for a MAME or FBNeo set or a PICO-8 cart,
    else the file name without extension."""
    global _scraped
    system, _, rest = key.partition("/")
    if system not in SYSTEMS:
        return store.key_title(key)
    stem = os.path.splitext(os.path.basename(rest))[0]
    with _lock:
        if _scraped is None:
            _scraped = {}
        if system not in _scraped:
            _scraped[system] = _load(system)
        fallback = store.key_title(key)
        if system == "pico8":
            fallback = fallback.removesuffix(".p8")
        return _scraped[system].get(rest) or fallback


def reset():
    """Forget what was loaded, so the next lookup checks storage again."""
    global _scraped
    with _lock:
        _scraped = None
