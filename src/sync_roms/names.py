"""Proper game names for MAME and FBNeo sets, whose file names are short codes ("1941j.zip").

A set's name comes from clones.json (the DAT name), else from the system's scraped metadata.json in storage, else the
file name. A copy of each metadata file's names is kept in the data folder with the storage file's tag, and the file is
downloaded again once per run when that tag changes."""
import json
import os
import threading

from . import inventory, runtime, s3, scrape_plan, store, ui

KEY = "names.json"
SYSTEMS = ("mame", "fbneo")
_lock = threading.RLock()
_scraped = None  # {system: {ROM path: name}}, filled per system on first use this run
_clones = None


def _local_path():
    return os.path.join(store.data_dir(), KEY)


def _load_local():
    try:
        with open(_local_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_local(data):
    try:
        store.write_json(_local_path(), data, indent=2)
    except OSError as e:
        ui.warn(f"Couldn't save the local copy of {KEY} ({e})")


def _read(key):
    """A storage file's text, from storage itself (never the local mirror, which holds only what syncs need)."""
    if runtime.ROOT:
        with open(s3.safe_join(runtime.ROOT, key), encoding="utf-8") as f:
            return f.read()
    return s3.s3_client().get_object(Bucket=runtime.BUCKET, Key=key)["Body"].read().decode("utf-8")


def _entry_names(entry):
    names = entry.get("names") if isinstance(entry, dict) else None
    if not isinstance(names, dict):
        return {}
    return {rom: name for rom, name in names.items() if isinstance(name, str)}


def _load(system):
    local = _load_local()
    entry = local.get(system)
    try:
        key = f"{scrape_plan.SCRAPES}/{system}/metadata.json"
        tag = inventory.tag(key)
        if tag is not None and not (isinstance(entry, dict) and entry.get("tag") == tag):
            try:
                text = _read(key)
            except s3.ERRORS as e:
                if not s3.missing(e):
                    raise
                tag = None
            else:
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError(f"{key} isn't a JSON object")
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
    """A storage key's display name: the proper name for a MAME or FBNeo set, else the file name without extension."""
    global _scraped, _clones
    system, _, rest = key.partition("/")
    if system not in SYSTEMS:
        return store.key_title(key)
    stem = os.path.splitext(os.path.basename(rest))[0]
    with _lock:
        if _clones is None:
            _clones = store.repo_json("clones")
        family = _clones.get(system, {})
        clone = family.get("clones", {}).get(stem)
        if clone:
            return clone[1]
        if stem in family.get("parents", {}):
            return family["parents"][stem]
        if _scraped is None:
            _scraped = {}
        if system not in _scraped:
            _scraped[system] = _load(system)
        return _scraped[system].get(rest) or store.key_title(key)


def reset():
    """Forget what was loaded, so the next lookup checks storage again."""
    global _scraped, _clones
    with _lock:
        _scraped = None
        _clones = None
