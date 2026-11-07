"""Personal scrape state under the user data folder: hash cache, manual matches, unknown ledger."""
import json
import os
import tempfile
import threading

from . import scrape_plan, store, ui

_lock = threading.RLock()  # scrape runs match ROMs on several threads; each save is a read-modify-write
_warned = set()  # paths of corrupt files already warned about
MATCHES = "scrape-matches.json"  # the only one holding what the user typed, so the only one worth a warning


def _path(name):
    return os.path.join(store.data_dir(), name)


def _load(name):
    try:
        with open(_path(name)) as f:
            data = json.load(f)
    except OSError:
        return {}
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if name == MATCHES and _path(name) not in _warned:
            _warned.add(_path(name))
            ui.warn(f"{_path(name)} isn't a valid JSON object; its manual matches are ignored, "
                    "and the next `scrape match` replaces it")
        return {}
    return data


def _save(name, data):
    os.makedirs(store.data_dir(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=store.data_dir(), prefix=f".{name}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(scrape_plan.dump_json(data))
        os.replace(tmp, _path(name))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


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


def _game_id(v):
    return type(v) is int and v > 0


def manual_match(system, rom):
    game_id = _load(MATCHES).get(_key(system, rom))
    return game_id if _game_id(game_id) else None


def save_match(system, rom, game_id):
    if not _game_id(game_id):
        raise ValueError(f"not a ScreenScraper game id: {game_id!r}")
    with _lock:
        data = _load(MATCHES)
        data[_key(system, rom)] = game_id
        _save(MATCHES, data)


def is_unknown(system, rom):
    return _key(system, rom) in _load("scrape-unknown.json")


def mark_unknown(system, rom):
    with _lock:
        data = _load("scrape-unknown.json")
        data[_key(system, rom)] = True
        _save("scrape-unknown.json", data)


def clear_unknown(system=None, rom=None):
    """Forget one unknown ROM, the unknown ROMs of one system, or those of every system."""
    with _lock:
        data = _load("scrape-unknown.json")
        if rom is not None:
            data.pop(_key(system, rom), None)
        elif system is not None:
            data = {k: v for k, v in data.items() if not k.startswith(system + "/")}
        else:
            data = {}
        _save("scrape-unknown.json", data)
