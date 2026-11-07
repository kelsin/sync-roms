"""Personal scrape state under the user data folder: hash cache, manual matches, unknown ledger."""
import json
import os
import threading

from . import scrape_plan, store

_lock = threading.RLock()  # scrape runs match ROMs on several threads; each save is a read-modify-write


def _path(name):
    return os.path.join(store.data_dir(), name)


def _load(name):
    try:
        with open(_path(name)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(name, data):
    os.makedirs(store.data_dir(), exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w") as f:
        f.write(scrape_plan.dump_json(data))
    os.replace(tmp, _path(name))


def _key(system, rom):
    return system + "/" + rom


def cached_hashes(system, rom, size, mtime):
    """{"md5","sha1","crc"} saved for this ROM, or None when absent or its size/mtime changed."""
    entry = _load("scrape-hashes.json").get(_key(system, rom))
    if not isinstance(entry, dict) or entry.get("size") != size or entry.get("mtime") != mtime:
        return None
    hashes = entry.get("hashes")
    return hashes if isinstance(hashes, dict) else None


def save_hashes(system, rom, size, mtime, hashes):
    with _lock:
        data = _load("scrape-hashes.json")
        data[_key(system, rom)] = {"size": size, "mtime": mtime, "hashes": hashes}
        _save("scrape-hashes.json", data)


def manual_match(system, rom):
    game_id = _load("scrape-matches.json").get(_key(system, rom))
    return game_id if isinstance(game_id, int) else None


def save_match(system, rom, game_id):
    with _lock:
        data = _load("scrape-matches.json")
        data[_key(system, rom)] = game_id
        _save("scrape-matches.json", data)


def is_unknown(system, rom):
    return _key(system, rom) in _load("scrape-unknown.json")


def mark_unknown(system, rom):
    with _lock:
        data = _load("scrape-unknown.json")
        data[_key(system, rom)] = True
        _save("scrape-unknown.json", data)


def clear_unknown(system=None):
    """Forget the unknown ROMs of one system, or of every system."""
    with _lock:
        data = _load("scrape-unknown.json")
        if system is not None:
            data = {k: v for k, v in data.items() if not k.startswith(system + "/")}
        else:
            data = {}
        _save("scrape-unknown.json", data)
