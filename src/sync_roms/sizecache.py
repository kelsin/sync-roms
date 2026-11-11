"""Persistent per-system file size cache (sizes.json in the data folder), so the editor can show space use at once.

A refresh lists names (fast even on a network share), stats only new files, drops removed ones, spot-checks a few
cached sizes and rebuilds the system when one differs or the entry is old. The cache belongs to one source
(s3.location()); a different source, or a corrupt file, counts as empty."""
import json
import os
import random
import threading
import time

from . import s3, store

MAX_AGE = 30 * 24 * 3600  # seconds before a system is rebuilt from scratch
SPOT_CHECKS = 5

_clock = time.time  # replaced by tests
_sample = random.sample


def _path():
    return os.path.join(store.data_dir(), "sizes.json")


_parsed = {}  # path -> (stat signature, parsed JSON): the editor reads the cache on every redraw, so parse once per change


def _read(path):
    """The parsed sizes.json, parsed again only when the file changed (it is always replaced whole, by a rename)."""
    st = os.stat(path)
    sig = (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    hit = _parsed.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    with open(path) as f:
        data = json.load(f)
    _parsed[path] = (sig, data)
    return data


def _load():
    """{prefix: {"built": time, "files": {key: size}}} for the current source; {} when missing, corrupt or another source.
    A missing or invalid "built" becomes 0, which counts as old."""
    try:
        data = _read(_path())
        if data["source"] != s3.location():
            return {}
        entries = {}
        for p, e in data["prefixes"].items():
            if isinstance(e, dict) and isinstance(e.get("files"), dict):
                built = e.get("built")
                ok = isinstance(built, (int, float)) and not isinstance(built, bool)
                entries[p] = {"built": built if ok else 0, "files": e["files"]}
        return entries
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def cached(prefix):
    """The cached {key: size} for a prefix (a folder, ending in /), or None when there is none."""
    entry = _load().get(prefix)
    return dict(entry["files"]) if entry else None


_lock = threading.Lock()


def _save(prefix, files, built):
    """Store one prefix. Re-reads the file under the lock so a refresh of another prefix that finished meanwhile is kept."""
    with _lock:
        entries = _load()
        entries[prefix] = {"built": built, "files": files}
        store.write_json(_path(), {"source": s3.location(), "prefixes": entries})
    return files


def refresh(prefix):
    """Bring the cache for a prefix up to date (blocking) and return {key: size}. Raises what the listing raises."""
    entry = _load().get(prefix)
    bucket = s3.read_root() is None  # a bucket listing carries the sizes and there is nothing to stat
    names = s3.list_sizes(prefix, sizes=bucket)
    if entry is None or _clock() - entry["built"] > MAX_AGE:
        return _save(prefix, names if bucket else s3.list_sizes(prefix), _clock())
    old = entry["files"]
    kept = [k for k in old if k in names]  # a removed file is dropped below, not a sign the sizes are stale
    check = _sample(kept, min(SPOT_CHECKS, len(kept)))
    sizes_of = (lambda keys: {k: names[k] for k in keys}) if bucket else s3.stat_sizes
    now = sizes_of(check)
    if any(now.get(k) != old[k] for k in check):
        return _save(prefix, names if bucket else s3.list_sizes(prefix), _clock())
    files = {k: old[k] for k in kept}
    files.update(sizes_of([k for k in names if k not in old]))
    return _save(prefix, files, entry["built"])


def refresh_async(prefix, on_done):
    """refresh() on a daemon thread, then on_done(sizes). When the refresh fails (an unreachable share, say), on_done
    gets what was cached before, or {}. Returns the started thread."""
    def run():
        try:
            result = refresh(prefix)
        except Exception:  # the thread must never die loudly: the editor falls back to what it had
            result = cached(prefix) or {}
        on_done(result)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
