"""Shared scrape state in storage: hash cache, manual matches, unknown and not-offered media ledgers, non-games.

Per system: scrapes/<system>/{matches,unknown,nomedia,hashes}.json, keyed by ROM path; scrapes/notgames.json is keyed
by "system/rom". Each file is read once per run (through its local mirror, see shared.py) and this module's own changes
are applied to that copy, so the run always sees them. Every write reads the storage file fresh and applies only this
run's changes (shared.update), so two machines merge. Matches and non-games are written at once; unknown, not-offered
and hash marks wait in memory for flush_unknown/flush_nomedia/flush_hashes."""
import json
import os
import threading

from . import inventory, s3, scrape_plan, shared, store, ui

_lock = threading.RLock()  # scrape runs match ROMs on several threads
_GONE = object()  # a pending change that removes the ROM's entry
MATCHES = "matches.json"  # the only one holding what the user typed, so the only one worth a warning
UNKNOWN = "unknown.json"
NOMEDIA = "nomedia.json"  # media types ScreenScraper didn't offer for a ROM: {rom: [types]}
HASHES = "hashes.json"  # {rom: {"size", "mtime", "hashes"}}
NOTGAMES = f"{scrape_plan.SCRAPES}/notgames.json"  # ROMs ScreenScraper calls non-games, waiting for `scrape review`: {"system/rom": what it said}
KEPT = "kept"  # in NOTGAMES (never a "system/rom" key): ["system/rom"] of the ROMs `scrape review` was told to keep for later
HASH_FLUSH = 1000  # hashes saved in memory before the hash files are written
_where = None  # the data folder everything below was loaded for (a new one in each test)
_systems = None  # {file name: systems having it in storage}, from one listing of scrapes/
_state = {}  # file name -> {system: {rom: value}}, and NOTGAMES -> its data: as loaded, with this run's changes
_pending = {}  # file name -> {system: {rom: value or _GONE}} not yet written (unknown, nomedia, hashes)
_warned = set()  # keys of corrupt files already warned about


def reset():
    """Forget everything loaded and pending (tests)."""
    global _where, _systems
    with _lock:
        _where, _systems = None, None
        _state.clear()
        _pending.clear()
        _warned.clear()


def _check_where():
    global _where
    if store.data_dir() != _where:
        reset()
        _where = store.data_dir()


def _key(system, name):
    return f"{scrape_plan.SCRAPES}/{system}/{name}"


def _object(text):
    """The text's JSON object, or None when it isn't one."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _parse(text):
    return _object(text) or {}


def _load(key):
    data = shared.load(key, _object, {})
    if data is None:
        if key not in _warned and (key.endswith("/" + MATCHES) or key == NOTGAMES):
            _warned.add(key)
            what = ("its manual matches are ignored, and the next `scrape match` replaces it" if key != NOTGAMES else
                    "its non-games and kept-for-later marks are ignored, and the next change to them replaces it")
            ui.warn(f"{key} isn't a valid JSON object; {what}")
        return {}
    return data


def _listed(name):
    """Systems whose scrapes/<system>/<name> is in storage (or, when storage can't be listed, in the local mirror)."""
    global _systems
    if _systems is None:
        try:
            keys = inventory.files(scrape_plan.SCRAPES + "/", sizes=False)
        except s3.ERRORS as e:
            ui.warn(f"Couldn't list {scrape_plan.SCRAPES}/ in storage ({e}); using the local copies")
            keys = _mirrored()
        _systems = {}
        for k in keys:
            parts = k.split("/")
            if len(parts) == 3 and parts[2] in (MATCHES, UNKNOWN, NOMEDIA, HASHES):
                _systems.setdefault(parts[2], set()).add(parts[1])
    return _systems.get(name, set())


def _mirrored():
    root = shared.local_path(scrape_plan.SCRAPES)
    try:
        systems = os.listdir(root)
    except OSError:
        return []
    return [_key(s, n) for s in systems for n in (MATCHES, UNKNOWN, NOMEDIA, HASHES)
            if os.path.isfile(shared.local_path(_key(s, n)))]


def _ledger(name, system):
    """{rom: value} of one kind for one system, loaded once per run."""
    _check_where()
    loaded = _state.setdefault(name, {})
    if system not in loaded:  # a file the storage cache says isn't there isn't looked for
        absent = inventory.current() is not None and system not in _listed(name)
        loaded[system] = {} if absent else _load(_key(system, name))
    return loaded[system]


def _every(name):
    """{system: {rom: value}} of one kind for every system that has it (or has this run's marks)."""
    _check_where()
    for system in sorted(_listed(name)):
        _ledger(name, system)
    return _state.setdefault(name, {})


def _notgames():
    _check_where()
    if NOTGAMES not in _state:
        _state[NOTGAMES] = _load(NOTGAMES)
    return _state[NOTGAMES]


def _write(key, change, removes_only=False):
    """Apply change to the storage file (read fresh) and write it; a storage error only warns. A change that only
    removes entries is skipped when the file isn't there (it would only create an empty one)."""
    try:
        if removes_only and inventory.tag(key) is None:
            return
        shared.update(key, _parse, {}, change, scrape_plan.dump_json)
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't save {key} ({e}); this run's changes to it may not be in storage")


def _apply(data, changes):
    for rom, value in changes.items():
        if value is _GONE:
            data.pop(rom, None)
        else:
            data[rom] = value


def _mark(name, system, rom, value):
    """Change one ROM's entry in memory; it is written by the kind's flush. Removing an entry that isn't there does
    nothing."""
    if value is _GONE and rom not in _ledger(name, system):
        return
    _apply(_ledger(name, system), {rom: value})
    _pending.setdefault(name, {}).setdefault(system, {})[rom] = value


def _flush(name):
    for system, changes in sorted(_pending.pop(name, {}).items()):
        _write(_key(system, name), lambda data, changes=changes: _apply(data, changes),
               removes_only=all(v is _GONE for v in changes.values()))


def _get(name, system, rom):
    return _ledger(name, system).get(rom)


def cached_hashes(system, rom, size, mtime):
    """{"md5","sha1","crc"} saved for this ROM, or None when absent or its size/mtime changed."""
    with _lock:
        entry = _get(HASHES, system, rom)
    if not isinstance(entry, dict) or entry.get("size") != size or entry.get("mtime") != mtime:
        return None
    hashes = entry.get("hashes")
    return hashes if isinstance(hashes, dict) else None


def save_hashes(system, rom, size, mtime, hashes):
    """Remember a ROM's hashes; the files are written every HASH_FLUSH hashes and by flush_hashes."""
    with _lock:
        _mark(HASHES, system, rom, {"size": size, "mtime": mtime, "hashes": hashes})
        if sum(map(len, _pending[HASHES].values())) >= HASH_FLUSH:
            flush_hashes()


def flush_hashes():
    """Write the hashes saved so far."""
    with _lock:
        _flush(HASHES)


def _game_id(v):
    return type(v) is int and v > 0


def manual_match(system, rom):
    with _lock:
        game_id = _get(MATCHES, system, rom)
    return game_id if _game_id(game_id) else None


def _set_match(system, rom, value):
    with _lock:
        _apply(_ledger(MATCHES, system), {rom: value})
        _write(_key(system, MATCHES), lambda data: _apply(data, {rom: value}))


def save_match(system, rom, game_id):
    if not _game_id(game_id):
        raise ValueError(f"not a ScreenScraper game id: {game_id!r}")
    _set_match(system, rom, game_id)


def forget_match(system, rom):
    with _lock:
        if _get(MATCHES, system, rom) is not None:
            _set_match(system, rom, _GONE)


def is_unknown(system, rom):
    with _lock:
        return _get(UNKNOWN, system, rom) is not None


def mark_unknown(system, rom):
    """Remember a ROM as unknown; the ledger is written by flush_unknown."""
    with _lock:
        _mark(UNKNOWN, system, rom, True)


def clear_unknown(system=None, rom=None):
    """Forget one unknown ROM (written by flush_unknown), the unknown ROMs of one system, or those of every system."""
    with _lock:
        if rom is not None:
            _mark(UNKNOWN, system, rom, _GONE)
            return
        pending = _pending.get(UNKNOWN, {})
        for s in [system] if system is not None else sorted(_every(UNKNOWN)):
            _ledger(UNKNOWN, s).clear()
            pending.pop(s, None)
            _write(_key(s, UNKNOWN), lambda data: data.clear(), removes_only=True)


def flush_unknown():
    """Write the unknown marks and clears made so far."""
    with _lock:
        _flush(UNKNOWN)


def unknown():
    """The "system/rom" keys of the ROMs ScreenScraper didn't know, with the marks not yet written."""
    with _lock:
        return {f"{s}/{rom}" for s, roms in _every(UNKNOWN).items() for rom in roms}


def mark_nomedia(system, rom, types):
    """Remember the media types ScreenScraper's last answer for a ROM didn't offer (none forgets it); the ledger is
    written by flush_nomedia."""
    with _lock:
        _mark(NOMEDIA, system, rom, sorted(types) or _GONE)


def flush_nomedia():
    """Write the not-offered marks made so far."""
    with _lock:
        _flush(NOMEDIA)


def nomedia():
    """{"system/rom": [media types not offered]}, with the marks not yet written."""
    with _lock:
        return {f"{s}/{rom}": types for s, roms in _every(NOMEDIA).items() for rom, types in roms.items()}


def notgames():
    """{"system/rom": what ScreenScraper said} of the non-game results waiting for review."""
    with _lock:
        return {k: v for k, v in _notgames().items() if k != KEPT}


def _kept(data):
    keys = data.get(KEPT)
    return {k for k in keys if isinstance(k, str)} if isinstance(keys, list) else set()


def kept():
    """The "system/rom" keys of the ROMs (non-games and unknown) `scrape review` was told to keep for later."""
    with _lock:
        return _kept(_notgames())


def _change_notgames(change):
    """Apply change to the non-games in memory and in storage (read fresh)."""
    with _lock:
        change(_notgames())
        _write(NOTGAMES, change)


def _without_kept(data, keys):
    have = _kept(data)
    if have & keys:
        data[KEPT] = sorted(have - keys)


def keep(system, rom):
    def change(data):
        have = _kept(data)
        if f"{system}/{rom}" not in have:
            data[KEPT] = sorted(have | {f"{system}/{rom}"})
    with _lock:
        if f"{system}/{rom}" not in kept():
            _change_notgames(change)


def unkeep(keys):
    """Drop the kept-for-later marks of keys ("system/rom"), in one write."""
    keys = set(keys)
    with _lock:
        if kept() & keys:
            _change_notgames(lambda data: _without_kept(data, keys))


def mark_notgame(system, rom, info):
    """Mark a ROM a non-game (a new mark: its kept-for-later mark goes)."""
    def change(data):
        data[f"{system}/{rom}"] = info
        _without_kept(data, {f"{system}/{rom}"})
    _change_notgames(change)


def clear_notgame(system, rom):
    """Take a ROM off the non-games, and its kept-for-later mark with it."""
    def change(data):
        data.pop(f"{system}/{rom}", None)
        _without_kept(data, {f"{system}/{rom}"})
    with _lock:
        if f"{system}/{rom}" in _notgames() or f"{system}/{rom}" in kept():
            _change_notgames(change)


class _Snapshot:
    """manual_match, is_unknown, is_notgame and not_offered for checking many ROMs. Only the non-games are read when it
    is made; each system's matches, unknown and not-offered files are read when first asked about (once per run)."""

    def __init__(self):
        self._notgames = set(notgames())

    def manual_match(self, system, rom):
        return manual_match(system, rom)

    def is_unknown(self, system, rom):
        return is_unknown(system, rom)

    def is_notgame(self, system, rom):
        return f"{system}/{rom}" in self._notgames

    def not_offered(self, system, rom):
        with _lock:
            types = _get(NOMEDIA, system, rom)
        return {t for t in types if isinstance(t, str)} if isinstance(types, list) else set()


def snapshot():
    return _Snapshot()
