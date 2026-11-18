"""The card's folder listings, each read once while a sync keeps them (caching()) until clear()."""
import contextlib
import os
import unicodedata

_cache = None  # {folder: (entries, folded)} while caching(); None: every lookup lists its folder afresh


@contextlib.contextmanager
def caching():
    """Keep the listings until the end (usable as a decorator); whoever changes the card in between calls clear()."""
    global _cache
    _cache = {}
    try:
        yield
    finally:
        _cache = None


def clear():
    """Drop every kept listing: the card has changed."""
    if _cache is not None:
        _cache.clear()


def _fold(name):
    return unicodedata.normalize("NFC", name).casefold()


def _scan(folder):
    """({name: DirEntry}, {folded name: [names]}) of folder, empty when it can't be listed."""
    entries = {}
    try:
        with os.scandir(folder) as it:
            entries = {e.name: e for e in it}
    except OSError:
        pass
    folded = {}
    for name in entries:
        folded.setdefault(_fold(name), []).append(name)
    return entries, folded


def _listed(folder):
    folder = os.path.normpath(folder)
    if _cache is None:
        return _scan(folder)
    if folder not in _cache:
        _cache[folder] = _scan(folder)
    return _cache[folder]


def _is_dir(entry):
    try:
        return entry.is_dir()
    except OSError:
        return False


def _size(entry):
    """A file's size (a DirEntry reads it once), None for a folder or a file that can't be read."""
    if _is_dir(entry):
        return None
    try:
        return entry.stat().st_size
    except OSError:
        return None


def listing(folder):
    """{name: (is_dir, size)} of folder (size None for a folder); a missing folder is an empty listing."""
    return {name: (_is_dir(e), _size(e)) for name, e in _listed(folder)[0].items()}


def _entry(path):
    """path's DirEntry in its folder's listing: the exact name, else the one name that differs only in case and
    Unicode form, as a case-insensitive card finds it; None when there is none. A name found only that way is checked
    on the disk, so a case-sensitive one gets the answer os.stat gives."""
    folder, name = os.path.split(os.path.normpath(path))
    entries, folded = _listed(folder)
    if name in entries:
        return entries[name]
    names = folded.get(_fold(name), ())
    return entries[names[0]] if len(names) == 1 and os.path.lexists(path) else None


def exists(path):
    return _entry(path) is not None


def size(path):
    """path's size, or None when it is missing or a folder."""
    entry = _entry(path)
    return None if entry is None else _size(entry)


def is_dir(path):
    entry = _entry(path)
    return entry is not None and _is_dir(entry)


def walk(top):
    """os.walk(top) over the listings: (folder, dirs, files), top down, dirs prunable in place; a symlinked folder is
    listed in dirs but not entered."""
    entries = _listed(top)[0]
    dirs = [name for name, e in entries.items() if _is_dir(e)]
    files = [name for name, e in entries.items() if not _is_dir(e)]
    yield top, dirs, files
    for name in dirs:
        if not entries[name].is_symlink():
            yield from walk(os.path.join(top, name))
