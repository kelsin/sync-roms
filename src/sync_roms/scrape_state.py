"""Personal scrape state under the user data folder: hash cache, manual matches, unknown ledger."""
import json
import os
import tempfile
import threading

from . import scrape_plan, store, ui

_lock = threading.RLock()  # scrape runs match ROMs on several threads; each save is a read-modify-write
_cache = {}  # file path -> ((mtime_ns, size), data): a file nobody changed since we last read or wrote it is not parsed again
_unsaved = {}  # hash file path -> hashes saved in memory but not yet written
_unknown_pending = {}  # unknown ledger path -> {key: True (marked) or False (cleared)} not yet written
UNKNOWN = "scrape-unknown.json"
NOTGAMES = "scrape-notgames.json"  # ROMs ScreenScraper calls non-games, waiting for `scrape review`: {key: what it said}
HASH_FLUSH = 200  # hashes saved in memory before the hash file is written
HASHES = "scrape-hashes.json"
_warned = set()  # paths of corrupt files already warned about
MATCHES = "scrape-matches.json"  # the only one holding what the user typed, so the only one worth a warning


def _path(name):
    return os.path.join(store.data_dir(), name)


def _sig(path):
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size


def _load(name):
    """The file's data. The same dict comes back while the file is unchanged, so callers change it only under _lock and
    then _save it."""
    path = _path(name)
    try:
        sig = _sig(path)
    except OSError:
        _cache.pop(path, None)
        return {}
    with _lock:
        hit = _cache.get(path)
        if hit and hit[0] == sig:
            return hit[1]
        data = _read(name)
        if data:
            _cache[path] = (sig, data)
        return data


def _read(name):
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
        _cache[_path(name)] = (_sig(_path(name)), data)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _key(system, rom):
    return system + "/" + rom


def cached_hashes(system, rom, size, mtime):
    """{"md5","sha1","crc"} saved for this ROM, or None when absent or its size/mtime changed."""
    entry = _unsaved.get(_path(HASHES), {}).get(_key(system, rom)) or _load(HASHES).get(_key(system, rom))
    if not isinstance(entry, dict) or entry.get("size") != size or entry.get("mtime") != mtime:
        return None
    hashes = entry.get("hashes")
    return hashes if isinstance(hashes, dict) else None


def save_hashes(system, rom, size, mtime, hashes):
    """Remember a ROM's hashes; the file is written every HASH_FLUSH hashes and by flush_hashes."""
    with _lock:
        pending = _unsaved.setdefault(_path(HASHES), {})
        pending[_key(system, rom)] = {"size": size, "mtime": mtime, "hashes": hashes}
        if len(pending) >= HASH_FLUSH:
            flush_hashes()


def flush_hashes():
    """Write the hashes saved so far."""
    with _lock:
        pending = _unsaved.pop(_path(HASHES), None)
        if pending:
            data = _load(HASHES)
            data.update(pending)
            _save(HASHES, data)


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


def forget_match(system, rom):
    with _lock:
        data = _load(MATCHES)
        if data.pop(_key(system, rom), None) is not None:
            _save(MATCHES, data)


def is_unknown(system, rom):
    with _lock:
        pending = _unknown_pending.get(_path(UNKNOWN), {}).get(_key(system, rom))
        return pending if pending is not None else _key(system, rom) in _load(UNKNOWN)


def mark_unknown(system, rom):
    """Remember a ROM as unknown; the ledger is written by flush_unknown."""
    with _lock:
        _unknown_pending.setdefault(_path(UNKNOWN), {})[_key(system, rom)] = True


def clear_unknown(system=None, rom=None):
    """Forget one unknown ROM (written by flush_unknown), the unknown ROMs of one system, or those of every system."""
    with _lock:
        if rom is not None:
            _unknown_pending.setdefault(_path(UNKNOWN), {})[_key(system, rom)] = False
            return
        flush_unknown()
        data = _load(UNKNOWN)
        if system is not None:
            data = {k: v for k, v in data.items() if not k.startswith(system + "/")}
        else:
            data = {}
        _save(UNKNOWN, data)


def flush_unknown():
    """Write the unknown marks and clears made so far."""
    with _lock:
        pending = _unknown_pending.pop(_path(UNKNOWN), None)
        if not pending:
            return
        data = _load(UNKNOWN)
        changed = False
        for k, marked in pending.items():
            if marked and data.get(k) is not True:
                data[k] = True
                changed = True
            elif not marked and data.pop(k, None) is not None:
                changed = True
        if changed:
            _save(UNKNOWN, data)


def unknown():
    """The "system/rom" keys of the ROMs ScreenScraper didn't know, with the marks not yet written."""
    with _lock:
        keys = set(_load(UNKNOWN))
        for k, marked in _unknown_pending.get(_path(UNKNOWN), {}).items():
            (keys.add if marked else keys.discard)(k)
        return keys


def notgames():
    """{"system/rom": what ScreenScraper said} of the non-game results waiting for review."""
    with _lock:
        return dict(_load(NOTGAMES))


def mark_notgame(system, rom, info):
    with _lock:
        data = dict(_load(NOTGAMES))
        data[_key(system, rom)] = info
        _save(NOTGAMES, data)


def clear_notgame(system, rom):
    with _lock:
        data = dict(_load(NOTGAMES))
        if data.pop(_key(system, rom), None) is not None:
            _save(NOTGAMES, data)


class _Snapshot:
    """manual_match and is_unknown over files read once, for checking many ROMs."""

    def __init__(self):
        with _lock:
            self._matches = _load(MATCHES)
            self._unknown = unknown()
            self._notgames = set(_load(NOTGAMES))

    def manual_match(self, system, rom):
        game_id = self._matches.get(_key(system, rom))
        return game_id if _game_id(game_id) else None

    def is_unknown(self, system, rom):
        return _key(system, rom) in self._unknown

    def is_notgame(self, system, rom):
        return _key(system, rom) in self._notgames


def snapshot():
    return _Snapshot()
