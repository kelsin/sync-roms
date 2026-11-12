"""ROMs sync-roms never shows, syncs or scrapes: ignored.json at the root of storage, {system folder: [ROM paths]}.

The list is shared (it lives in storage, not in the data folder). A copy is kept in the data folder with the storage
file's tag, and is downloaded again once per run when that tag changes. ROM files are never deleted."""
import json
import os
import threading

from . import inventory, runtime, s3, store, ui

KEY = "ignored.json"
_lock = threading.RLock()
_keys = None  # frozenset of "system/rom" keys, None until loaded this run


def _local_path():
    return os.path.join(store.data_dir(), KEY)


def _read():
    """The storage file's text, from storage itself (never the local mirror, which holds only what syncs need)."""
    if runtime.ROOT:
        with open(s3.safe_join(runtime.ROOT, KEY), encoding="utf-8") as f:
            return f.read()
    return s3.s3_client().get_object(Bucket=runtime.BUCKET, Key=KEY)["Body"].read().decode("utf-8")


def _clean(data):
    """{system: [paths]} with anything malformed left out."""
    if not isinstance(data, dict):
        return {}
    return {system: [p for p in paths if isinstance(p, str)]
            for system, paths in data.items() if isinstance(system, str) and isinstance(paths, list)}


def _flat(data):
    return frozenset(f"{system}/{p}" for system, paths in data.items() for p in paths)


def _load_local():
    try:
        with open(_local_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tag"), _clean(data.get("ignored"))
    except (OSError, ValueError, AttributeError):
        return None, {}


def _save_local(tag, data):
    store.write_json(_local_path(), {"tag": tag, "ignored": data}, indent=2)


def _load():
    local_tag, local = _load_local()
    try:
        tag = inventory.tag(KEY)
        if tag is None:
            if os.path.exists(_local_path()):
                os.remove(_local_path())
            return {}
        if tag == local_tag:
            return local
        data = _clean(json.loads(_read()))
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't check {KEY} in storage ({e}); using the local copy")
        return local
    try:
        _save_local(tag, data)
    except OSError as e:
        ui.warn(f"Couldn't save the local copy of {KEY} ({e})")
    return data


def keys():
    """The ignored ROMs' storage keys ("system/rom"), read once per run."""
    global _keys
    with _lock:
        if _keys is None:
            _keys = _flat(_load())
        return _keys


def is_ignored(key):
    return key in keys()


def add(entries):
    """Merge {system: [ROM paths]} into the storage file (read fresh) and the local copy. Returns how many were new."""
    global _keys
    with _lock:
        try:
            data = _clean(json.loads(_read()))
        except s3.ERRORS as e:
            if not s3.missing(e):
                raise
            data = {}
        before = _flat(data)
        for system, paths in entries.items():
            data[system] = sorted(set(data.get(system, [])) | set(paths))
        data = {system: data[system] for system in sorted(data)}
        s3.put_text(KEY, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        _save_local(inventory.tag(KEY), data)
        _keys = _flat(data)
        return len(_keys - before)


def reset():
    """Forget the loaded list, so the next keys() checks storage again."""
    global _keys
    with _lock:
        _keys = None
