"""What is in storage: every file's key and size (and, for a bucket, its ETag), read from a cache in the data folder.

Every command asks this module what storage holds; only file contents are read from storage itself. `sync-roms cache
update` builds the cache by reading all of storage (a bucket listing, or a walk and a stat of every file in a storage
folder), and sync-roms's own writes to storage patch it as they go (saved by flush()). Nothing refreshes it in the
background and it never expires. A cache built from other storage (another bucket or folder) is not used. Without a
usable cache the reads go to storage, as they always did (from the local mirror, when a sync reads from one)."""
import bisect
import datetime
import json
import os
import stat as statmode
import sys
import threading
import unicodedata
import time
from concurrent.futures import ThreadPoolExecutor

from . import runtime, s3, store, ui, usersettings

DECLINED = "storage_cache_declined"  # settings.json: the user said no to building the cache, so it isn't offered again
UPDATE_HINT = "sync-roms cache update"

_clock = time.time  # replaced by tests
# seconds: a folder mtime this close to now (or later) isn't stored. It is longer than the macOS SMB client serves a
# cached folder listing (up to 60 s, nsmb.conf dir_cache_max) plus slack between the share's clock and this one, so a
# stat can't show a new mtime that a stale listing doesn't reflect.
FRESH = 300
_lock = threading.RLock()
_tree = None  # the loaded cache (a Tree), False when there is none, None until read
_tree_path = None  # the file _tree was read from (the data folder can change, in tests)
_dirty = False  # patched since it was last saved


class Tree:
    """The cache: source (where it was read from), updated (when), files {key: size}, etags {key: ETag} and, for a
    storage folder, dirs {folder: st_mtime_ns, or None when not trusted} of every folder the walk read ("" is the root)."""

    def __init__(self, source, updated, files, etags, dirs=None):
        self.source, self.updated, self.files, self.etags, self.dirs = source, updated, files, etags, dirs or {}
        self._keys = self._folders = None

    def changed(self):
        self._keys = self._folders = None

    def under(self, prefix):
        """{key: size} of the keys starting with prefix, found by bisecting the sorted keys."""
        with _lock:  # a write on another thread may be patching the files
            if self._keys is None:
                self._keys = sorted(self.files)
            keys = self._keys
            lo = bisect.bisect_left(keys, prefix)
            hi = bisect.bisect_left(keys, prefix + "\U0010ffff") if prefix else len(keys)
            return {k: self.files[k] for k in keys[lo:hi]}

    def folders(self):
        if self._folders is None:
            self._folders = {k.split("/", 1)[0] for k in self.files if "/" in k}
        return self._folders


def path():
    return os.path.join(store.data_dir(), "storage-cache.json")


def source():
    """Where reads would come from: the storage folder, or the bucket (with its endpoint, when it isn't AWS)."""
    if runtime.ROOT:
        return runtime.ROOT
    return f"s3://{runtime.BUCKET}" + (f" ({runtime.ENDPOINT})" if runtime.ENDPOINT else "")


def _whole(n):
    return isinstance(n, int) and not isinstance(n, bool)


def _load():
    """The cache on disk, read once per run; None when it is missing or corrupt (a size that isn't a whole number is dropped)."""
    global _tree, _tree_path
    if _tree is None or _tree_path != path():
        _tree_path = path()
        try:
            with open(path()) as f:
                data = json.load(f)
            files = {k: n for k, n in data["files"].items() if _whole(n)}
            etags = {k: e for k, e in (data.get("etags") or {}).items() if isinstance(e, str) and k in files}
            dirs = {k: n if _whole(n) else None for k, n in (data.get("dirs") or {}).items()}
            updated = data.get("updated")
            _tree = Tree(str(data["source"]), updated if _whole(updated) or isinstance(updated, float) else 0, files, etags,
                         dirs)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            _tree = False
    return _tree or None


def reset():
    """Forget the loaded cache, so the next read loads the file again (tests, and after the settings change)."""
    global _tree, _dirty
    with _lock:
        _tree, _dirty = None, False


def current():
    """The cache when it was read from the storage in use, else None."""
    with _lock:
        tree = _load()
        return tree if tree and tree.source == source() else None


# --- Reads --------------------------------------------------------------------------------------------------------

def _unignored(listing, prefix=""):
    """listing without the ignored ROMs and OS litter like .DS_Store (its keys are prefix + key)."""
    from . import ignore  # imported here: ignore checks its own file through this module
    hidden = ignore.keys()
    return {k: v for k, v in listing.items() if prefix + k not in hidden and not s3.junk(k)}


def files(prefix, sizes=True):
    """{key: size} of the files whose key starts with prefix (a folder, ending in /). Without a cache it lists storage,
    and with sizes=False a storage folder's values are None (names list fast on a network share; each size is a stat).
    Ignored ROMs are left out here and in every read below."""
    tree = current()
    return _unignored(s3.list_sizes(prefix, sizes) if tree is None else tree.under(prefix))


def cached(prefix):
    """files(prefix) from the cache only, or None when there is no cache (never reads storage)."""
    tree = current()
    return None if tree is None else _unignored(tree.under(prefix))


def stat(keys):
    """{key: size} of the keys that are files in storage."""
    tree = current()
    if tree is None:
        return _unignored(s3.stat_sizes(keys))
    return _unignored({k: tree.files[k] for k in keys if k in tree.files and not k.endswith("/")})


def etags(prefix):
    """{path under prefix: (size, ETag)}, as s3.list_with_etags. A file whose ETag isn't known has "-", like a folder's."""
    tree = current()
    if tree is None:
        return _unignored(s3.list_with_etags(prefix), prefix)
    return _unignored({k[len(prefix):]: (n, tree.etags.get(k, "-")) for k, n in tree.under(prefix).items()
                       if not k.endswith("/")}, prefix)


def tag(key):
    """A tag that changes whenever one storage file's contents do, read live (never from the cache or the mirror): its
    ETag in a bucket, "<mtime_ns>-<size>" in a storage folder. None when the file doesn't exist."""
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not a missing file
        raise FileNotFoundError(f"{runtime.ROOT} is missing")
    try:
        if runtime.ROOT:
            st = os.stat(s3.safe_join(runtime.ROOT, key))
            return f"{st.st_mtime_ns}-{st.st_size}"
        return s3.s3_client().head_object(Bucket=runtime.BUCKET, Key=key)["ETag"]
    except s3.ERRORS as e:
        if s3.missing(e):
            return None
        raise


def folders():
    """Names of the top-level folders in storage."""
    tree = current()
    return s3.list_folders() if tree is None else set(tree.folders())


# --- Patches from sync-roms's own writes ----------------------------------------------------------------------------

def _patch(change, keys):
    """Apply change to the cache, and stop trusting the mtimes of the keys' folders (spelled as given, NFC or NFD: a share
    may store a name decomposed): the next update lists them."""
    global _dirty
    with _lock:
        tree = current()
        if tree is not None:
            change(tree)
            for k in keys:
                folder = k.rpartition("/")[0]
                for name in {folder, unicodedata.normalize("NFC", folder), unicodedata.normalize("NFD", folder)}:
                    if name in tree.dirs:
                        tree.dirs[name] = None
            tree.changed()
            _dirty = True


def wrote(key, size, etag=None):
    """A file was written to storage (its ETag, when known)."""
    def change(tree):
        tree.files[key] = size
        if etag:
            tree.etags[key] = etag
        else:
            tree.etags.pop(key, None)
    _patch(change, [key])


def removed(keys):
    """Files were deleted from storage."""
    keys = list(keys)

    def change(tree):
        for k in keys:
            tree.files.pop(k, None)
            tree.etags.pop(k, None)
    _patch(change, keys)


def moved(old, new):
    """A file was moved in storage (its ETag is dropped: a copy can change it)."""
    def change(tree):
        if old in tree.files:
            tree.files[new] = tree.files.pop(old)
            tree.etags.pop(old, None)
            tree.etags.pop(new, None)
    _patch(change, [old, new])


def _save(tree):
    files = dict(sorted(tree.files.items()))
    store.write_json(path(), {"source": tree.source, "updated": tree.updated, "files": files,
                              "etags": {k: tree.etags[k] for k in files if k in tree.etags},
                              "dirs": dict(sorted(tree.dirs.items()))}, separators=(",", ":"))


def flush():
    """Save the patches made this run. Called as sync-roms exits."""
    global _dirty
    with _lock:
        if _dirty and _tree and _tree_path == path():
            try:
                _save(_tree)
            except OSError as e:
                ui.warn(f"Couldn't save the storage cache ({e}); run {UPDATE_HINT}")
        _dirty = False


# --- Building it ----------------------------------------------------------------------------------------------------

def _progress(text):
    """Redraw one progress line on a terminal (None clears it); nothing on a pipe."""
    if sys.stdout.isatty():
        sys.stdout.write("\r\033[K" + (text or ""))
        sys.stdout.flush()


def _read_bucket():
    """({key: size}, {key: ETag}) of the whole bucket, in one listing."""
    sizes, tags = {}, {}
    pages = s3.s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET)
    for page in pages:
        for o in page.get("Contents", []):
            if s3.junk(o["Key"]):
                continue
            sizes[o["Key"]], tags[o["Key"]] = o["Size"], o["ETag"]
        _progress(f"  📋 {len(sizes):,} files listed")
    _progress(None)
    return sizes, tags


def _read_folder(root, old=None):
    """({key: size}, dirs) of every file and folder under root (dirs as a Tree's). Every folder is statted, and one whose
    mtime is the one old stored isn't listed: its files and subfolders come from old (a folder's mtime changes when an
    entry is added to, removed from or renamed in it, not when a subfolder changes). The others are listed as os.walk
    would (a symlinked folder isn't followed), and a listing error raises. A file old has keeps its cached size; the rest
    are statted (in parallel: each is a round trip on a network share). A folder's mtime is taken before it is listed,
    and isn't kept when it is within FRESH seconds of now."""
    known, stored, inside = (old.files, old.dirs, {}) if old else ({}, {}, {})
    if stored:  # folder: ([file keys], [subfolders]) in old
        for k in known:
            inside.setdefault(k.rpartition("/")[0], ([], []))[0].append(k)
        for d in stored:
            if d:
                inside.setdefault(d.rpartition("/")[0], ([], []))[1].append(d)
    paths, out, dirs, stack, listed = [], {}, {}, [""], 0
    while stack:
        folder = stack.pop()
        path = os.path.join(root, folder) if folder else root
        now = _clock()
        st = os.stat(path)
        if statmode.S_ISDIR(st.st_mode) and stored.get(folder) == st.st_mtime_ns:
            keys, subfolders = inside.get(folder, ([], []))
            out.update((k, known[k]) for k in keys if not s3.junk(k))
            stack.extend(subfolders)
            dirs[folder] = st.st_mtime_ns
        else:
            listed += 1
            prefix = folder + "/" if folder else ""
            with os.scandir(path) as entries:
                for e in entries:
                    if e.is_dir():  # a symlinked folder is named, as os.walk does, but not read
                        if not e.is_symlink():
                            stack.append(prefix + e.name)
                    elif not s3.junk(e.name):
                        if prefix + e.name in known:
                            out[prefix + e.name] = known[prefix + e.name]
                        else:
                            paths.append(os.path.join(path, e.name))
            dirs[folder] = st.st_mtime_ns if st.st_mtime_ns < (now - FRESH) * 1e9 else None
        _progress(f"  📋 {len(dirs):,} folders checked, {listed:,} listed, {len(paths) + len(out):,} files found")
    _progress(None)

    def size(p):
        try:
            st = os.stat(p)
        except OSError:
            return None
        return st.st_size if statmode.S_ISREG(st.st_mode) else None

    with ThreadPoolExecutor(s3.STAT_WORKERS) as ex:
        for i, (p, n) in enumerate(zip(paths, ex.map(size, paths)), 1):
            if n is not None:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = n
            if i % 500 == 0 or i == len(paths):
                _progress(f"  📏 {i:,}/{len(paths):,} files sized")
    _progress(None)
    return out, dirs


def update(full=False):
    """Read all of storage into the cache and save it. Returns (added, removed, changed) file counts against the cache
    it replaces. In a storage folder only folders whose mtime changed are listed and only new files are statted (the rest
    keep their cached files and sizes), unless full (a bucket listing has every size anyway). A storage folder that is
    missing (an unmounted share) or lists empty when the cache has files raises FileNotFoundError and keeps the cache."""
    global _tree, _tree_path, _dirty
    src = source()
    if runtime.ROOT:
        if not os.path.isdir(runtime.ROOT):
            raise FileNotFoundError(f"{runtime.ROOT} is missing")
        (sizes, dirs), tags = _read_folder(runtime.ROOT, None if full else current()), {}
    else:
        (sizes, tags), dirs = _read_bucket(), {}
    with _lock:
        old = current()
        before = old.files if old else {}
        if before and not sizes:
            raise FileNotFoundError(f"{src} listed empty; keeping the cache")
        tree = Tree(src, _clock(), sizes, tags, dirs)
        _save(tree)
        _tree, _dirty = tree, False
        _tree_path = path()
    return (sum(k not in before for k in sizes), sum(k not in sizes for k in before),
            sum(k in before and before[k] != n for k, n in sizes.items()))


def update_command(full=False):
    print(ui.bold("📇 Updating the storage cache") + ui.dim(f"  from {source()}"))
    try:
        added, gone, changed = update(full)
    except s3.ERRORS as e:
        ui.fail(f"Couldn't read storage: {e}", 3)
    tree = current()
    print(ui.green(f"✅ {len(tree.files):,} files, {ui.human_size(sum(tree.files.values()))}")
          + ui.dim(f"  ({added:,} new, {gone:,} gone, {changed:,} changed)"))
    return 0


def prepare():
    """Before a command reads storage: when there is no cache for the storage in use, offer (on a terminal, until the
    user says no once) to build it now."""
    if current() is not None or usersettings.load_settings().get(DECLINED) or not sys.stdin.isatty():
        return
    tree = _load()
    print(ui.yellow(f"📇 The storage cache is for {tree.source}, not {source()}." if tree else
                    "📇 There's no storage cache yet: without it every command lists storage, which is slow."))
    print(ui.dim(f"   Build or refresh it any time with: {UPDATE_HINT}"))
    if ui.confirm("📇 Build it now?", default=True):
        update_command()
        print()
    else:
        usersettings.save_setting(DECLINED, True)
        print(ui.dim(f"   Not asking again. {UPDATE_HINT} builds it."))


def _ago(seconds):
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= n:
            count = int(seconds // n)
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return "just now"


def status_command():
    """Print where the cache was read from, when, and its files and bytes per top-level folder."""
    tree = _load()
    print(ui.bold("📇 Storage cache") + ui.dim(f"  {path()}"))
    if tree is None:
        print(ui.yellow(f"   None yet: every command lists storage. Build it with: {UPDATE_HINT}"))
        return 0
    when = datetime.datetime.fromtimestamp(tree.updated).strftime("%Y-%m-%d %H:%M") if tree.updated else "unknown"
    print(f"   from {tree.source}  ·  updated {when}" + ui.dim(f" ({_ago(max(0, _clock() - tree.updated))})" if tree.updated else ""))
    if tree.source != source():
        print(ui.yellow(f"   ⚠️  Not used: storage is now {source()}. Rebuild it with: {UPDATE_HINT}"))
    totals = {}
    for k, n in tree.files.items():
        top = k.split("/", 1)[0] if "/" in k else ""
        count, size = totals.get(top, (0, 0))
        totals[top] = (count + 1, size + n)
    print(f"   {len(tree.files):,} files · {ui.human_size(sum(tree.files.values()))}\n")
    width = max((len(name) for name in totals), default=0) + 1
    for name, (count, size) in sorted(totals.items()):
        print(f"   {(name + '/') if name else '(top level)':<{width + 1}} {count:>9,} files  {ui.human_size(size):>10}")
    print(ui.dim(f"\n   Refresh it after changing storage outside sync-roms: {UPDATE_HINT}"))
    return 0
