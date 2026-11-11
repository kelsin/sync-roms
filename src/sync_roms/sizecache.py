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


def _load():
    """{prefix: {"at": time, "files": {key: size}}} for the current source; {} when missing, corrupt or another source."""
    try:
        with open(_path()) as f:
            data = json.load(f)
        if data["source"] != s3.location():
            return {}
        prefixes = data["prefixes"]
        return {p: e for p, e in prefixes.items()
                if isinstance(e, dict) and isinstance(e.get("at"), (int, float)) and isinstance(e.get("files"), dict)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def cached(prefix):
    """The cached {key: size} for a prefix (a folder, ending in /), or None when there is none."""
    entry = _load().get(prefix)
    return dict(entry["files"]) if entry else None


def _save(entries, prefix, files):
    entries[prefix] = {"at": _clock(), "files": files}
    store.write_json(_path(), {"source": s3.location(), "prefixes": entries})
    return files


def refresh(prefix):
    """Bring the cache for a prefix up to date (blocking) and return {key: size}. Raises what the listing raises."""
    entries = _load()
    entry = entries.get(prefix)
    names = s3.list_sizes(prefix, sizes=False)
    if entry is None or _clock() - entry["at"] > MAX_AGE:
        return _save(entries, prefix, s3.list_sizes(prefix))
    old = entry["files"]
    kept = [k for k in old if k in names]  # a removed file is dropped below, not a sign the sizes are stale
    check = _sample(kept, min(SPOT_CHECKS, len(kept)))
    now = s3.stat_sizes(check)
    if any(now.get(k) != old[k] for k in check):
        return _save(entries, prefix, s3.list_sizes(prefix))
    files = {k: old[k] for k in kept}
    new = [k for k in names if k not in old]
    files.update(s3.stat_sizes(new))
    return _save(entries, prefix, files)


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
