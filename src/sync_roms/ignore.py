"""ROMs sync-roms never shows, syncs or scrapes: ignored.json at the root of storage, {system folder: [ROM paths]}.

The list is shared (it lives in storage, not in the data folder). A copy is kept in the data folder (see shared.py)
and is downloaded again once per run when the storage file's tag changes. ROM files are never deleted."""
import json
import threading

from . import shared

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


def _dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


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
    """Merge {system: [ROM paths]} into the storage file (read fresh) and the local copy. Returns how many were new;
    nothing is written when none were."""
    global _keys
    counted = []

    def change(data):
        before = _flat(data)
        merged = dict(data)
        for system, paths in entries.items():
            merged[system] = sorted(set(data.get(system, [])) | set(paths))
        merged = {system: merged[system] for system in sorted(merged)}
        counted.append(len(_flat(merged) - before))
        return merged if counted[0] else None

    with _lock:
        _keys = _flat(shared.update(KEY, _parse, {}, change, _dump))
        return counted[0]


def remove(entries):
    """Drop {system: [ROM paths]} from the storage file (read fresh) and the local copy; a system left empty goes too.
    Returns how many were removed; nothing is written when none were."""
    global _keys
    counted = []

    def change(data):
        before = _flat(data)
        kept = {system: [p for p in data[system] if p not in set(entries.get(system, ()))] for system in sorted(data)}
        kept = {system: paths for system, paths in kept.items() if paths}
        counted.append(len(before - _flat(kept)))
        return kept if counted[0] else None

    with _lock:
        _keys = _flat(shared.update(KEY, _parse, {}, change, _dump))
        return counted[0]


def reset():
    """Forget the loaded list, so the next keys() checks storage again."""
    global _keys
    with _lock:
        _keys = None
