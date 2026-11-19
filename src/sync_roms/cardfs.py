"""The card's folder listings, each read once while a sync keeps them (caching()) until clear()."""
import contextlib
import os
import unicodedata

from . import store

_cache = None  # {folder: (entries, folded)} while caching(); None: every lookup lists its folder afresh


@contextlib.contextmanager
def caching():
    """Keep the listings until the end (usable as a decorator); whoever changes the card in between calls clear()."""
    global _cache, _texts, _dirty
    _cache, _texts, _dirty = {}, {}, set()
    try:
        yield
    finally:
        try:
            for path in sorted(_dirty):
                _put(path, _texts[path])
        finally:
            _cache = _texts = _dirty = None


_texts = None  # {path: text} of the settings files while caching(); kept through clear(): it is their latest text
_dirty = None  # the paths in _texts that differ from the card, written once when caching() ends


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


def read(path):
    """path's bytes, read once while caching() keeps them (raises OSError when it can't be read)."""
    key = ("read", os.path.normpath(path))
    if _cache is not None and key in _cache:
        return _cache[key]
    with open(path, "rb") as f:
        data = f.read()
    if _cache is not None:
        _cache[key] = data
    return data


def text(path):
    """path's text ("" when it is missing), read once while caching() keeps it, with write_text's edits."""
    if _texts is not None and path in _texts:
        return _texts[path]
    try:
        with open(path, encoding="utf-8") as f:
            data = f.read()
    except FileNotFoundError:
        data = ""
    if _texts is not None:
        _texts[path] = data
    return data


def _put(path, new):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.replace_file(path, new, newline="\n")


def write_text(path, new):
    """Make path hold new (LF line ends) unless it already does; True when that changes it. While caching() the write
    waits for the end, so edits from several places make one write."""
    if new == text(path):
        return False
    if _texts is None:
        _put(path, new)
    else:
        _texts[path] = new
        _dirty.add(path)
    return True


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
