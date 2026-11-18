"""ROMs sync-roms never shows, syncs or scrapes: ignored.json at the root of storage, {system folder: [ROM paths]}.

The list is shared (it lives in storage, not in the data folder). A copy is kept in the data folder (see shared.py)
and is downloaded again once per run when the storage file's tag changes. ROM files are never deleted."""
import json
import threading

from . import s3, shared

KEY = "ignored.json"
_lock = threading.RLock()
_keys = None  # frozenset of "system/rom" keys, None until loaded this run


def _clean(data):
    """{system: [paths]} with anything malformed left out."""
    if not isinstance(data, dict):
        return {}
    return {system: [p for p in paths if isinstance(p, str)]
            for system, paths in data.items() if isinstance(system, str) and isinstance(paths, list)}


def _flat(data):
    return frozenset(f"{system}/{p}" for system, paths in data.items() for p in paths)


def _parse(text):
    return _clean(json.loads(text))


def _fresh():
    """The storage file's contents, read now ({} when it isn't there)."""
    try:
        return _parse(shared.read(KEY))
    except s3.ERRORS as e:
        if not s3.missing(e):
            raise
        return {}


def _write(data):
    shared.write(KEY, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def keys():
    """The ignored ROMs' storage keys ("system/rom"), read once per run."""
    global _keys
    with _lock:
        if _keys is None:
            _keys = _flat(shared.load(KEY, _parse, {}))
        return _keys


def is_ignored(key):
    return key in keys()


def add(entries):
    """Merge {system: [ROM paths]} into the storage file (read fresh) and the local copy. Returns how many were new."""
    global _keys
    with _lock:
        data = _fresh()
        before = _flat(data)
        for system, paths in entries.items():
            data[system] = sorted(set(data.get(system, [])) | set(paths))
        data = {system: data[system] for system in sorted(data)}
        _write(data)
        _keys = _flat(data)
        return len(_keys - before)


def remove(entries):
    """Drop {system: [ROM paths]} from the storage file (read fresh) and the local copy; a system left empty goes too.
    Returns how many were removed."""
    global _keys
    with _lock:
        data = _fresh()
        before = _flat(data)
        for system, paths in entries.items():
            if system in data:
                data[system] = [p for p in data[system] if p not in set(paths)]
        data = {system: data[system] for system in sorted(data) if data[system]}
        removed = len(before - _flat(data))
        if removed:
            _write(data)
        _keys = _flat(data)
        return removed


def reset():
    """Forget the loaded list, so the next keys() checks storage again."""
    global _keys
    with _lock:
        _keys = None
