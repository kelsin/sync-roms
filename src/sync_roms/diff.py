"""Comparing and replacing local files against storage."""
import hashlib
import io
import os
import sys
import threading
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import downloads, ignore, inventory, picker, runtime, s3, store, ui


class RangeReader(io.RawIOBase):
    """Read-only file over a bucket object, fetching byte ranges; the tail is cached since a zip's index is there."""
    TAIL = 65536

    def __init__(self, key, size):
        self.key, self.size, self.pos = key, size, 0
        self.tail_at = max(0, size - self.TAIL)
        self.tail = self.fetch(self.tail_at, size) if size else b""

    def fetch(self, start, end):
        if end <= start:
            return b""
        return s3.read_range(self.key, start, end)

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=os.SEEK_SET):
        self.pos = offset if whence == os.SEEK_SET else self.pos + offset if whence == os.SEEK_CUR else self.size + offset
        return self.pos

    def read(self, n=-1):
        end = self.size if n is None or n < 0 else min(self.size, self.pos + n)
        if self.pos >= self.tail_at:
            data = self.tail[self.pos - self.tail_at:end - self.tail_at]
        else:
            data = self.fetch(self.pos, end)
        self.pos += len(data)
        return data


def zip_fingerprint(fileobj):
    """The (size, crc32) of every file inside a zip, from its index alone, so the name and compression don't matter."""
    with zipfile.ZipFile(fileobj) as z:
        return ("zip", tuple(sorted((i.file_size, i.CRC) for i in z.infolist() if not i.is_dir())))


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_fingerprint(path):
    """A local zip's fingerprint, else ("raw", size, None): match_content hashes a raw file only when a storage file could match it."""
    try:
        return zip_fingerprint(path)
    except zipfile.BadZipFile:
        return ("raw", os.path.getsize(path), None)


def bucket_fingerprint(key, size, etag):
    try:
        return zip_fingerprint(RangeReader(key, size))
    except (zipfile.BadZipFile, *s3.ERRORS):
        etag = etag.strip('"')
        return ("raw", size, None if "-" in etag else etag)  # a multipart upload's ETag isn't an md5


SAMPLE_CHUNK = 1 << 20  # same_bytes reads chunks this big
SAMPLES = 8  # and this many of them: the first, the last and evenly spaced ones between; a smaller file is read whole


def same_bytes(path, key, size):
    """True when local path and storage key (both size bytes) hold the same bytes: the whole file when it is small,
    else SAMPLES chunks of it, so a big storage file is never read whole. Stops at the first chunk that differs."""
    if size <= SAMPLES * SAMPLE_CHUNK:
        spans = [(start, min(SAMPLE_CHUNK, size - start)) for start in range(0, size, SAMPLE_CHUNK)]
    else:
        spans = [(k * (size - SAMPLE_CHUNK) // (SAMPLES - 1), SAMPLE_CHUNK) for k in range(SAMPLES)]
    with open(path, "rb") as f:
        for start, n in spans:
            f.seek(start)
            if f.read(n) != s3.read_range(key, start, start + n):
                return False
    return True


def same_content(a, b):
    if a[0] != b[0]:
        return False
    return a == b if a[0] == "zip" else a[1] == b[1] and (a[2] is None or b[2] is None or a[2] == b[2])


def counted(fn, label, total):
    """fn wrapped to show a "label done/total" counter on a terminal as it is called from the worker threads."""
    if not total or not sys.stdout.isatty():
        return fn
    lock, done = threading.Lock(), [0]

    def run(*a):
        result = fn(*a)
        with lock:
            done[0] += 1
            sys.stdout.write(f"\r\033[K  {ui.dim(f'{label} {done[0]}/{total}')}" + ("\r\033[K" if done[0] == total else ""))
            sys.stdout.flush()
        return result
    return run


def match_content(local, remote, local_print, remote_print, differs=None, md5=None, same_bytes=None):
    """([(local path, bucket path)] with the same content, only local, only storage) lists, ignoring names.

    local: {path: size}; remote: {path: (size, etag)}. A file with the same path and size on both sides is the same
    without reading it; the rest are matched by content, a file with the same path first. local_print(path) /
    remote_print(path, size, etag) return a fingerprint, and are only called for the files left over.
    differs(path, etag), if given, is asked about same-path same-size files and returns True when their bytes are
    known to differ; those are then matched by content too.
    md5(path), if given, hashes a local file whose print is ("raw", size, None), and is only called when a storage
    file of that size has an md5 to compare it with.
    same_bytes(local path, bucket path), if given, compares the bytes of two raw files of the same size when one of
    them has no md5; they are matched only when it returns True.
    """
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        same = [p for p, size in local.items() if p in remote and remote[p][0] == size]
        suspect = {p for p, d in zip(same, ex.map(counted(lambda p: differs(p, remote[p][1]), "Checking same-size files", len(same)), same)) if d} if differs else set()
        left_local = sorted(p for p, size in local.items() if p not in remote or remote[p][0] != size or p in suspect)
        left_remote = sorted(p for p, (size, _) in remote.items() if p not in local or local[p] != size or p in suspect)
        remote_prints = list(ex.map(counted(lambda p: remote_print(p, *remote[p]), "Reading storage files", len(left_remote)),
                                    left_remote))
        local_prints = list(ex.map(counted(local_print, "Reading local files", len(left_local)), left_local))
        if md5:
            sizes = {fp[1] for fp in remote_prints if fp[0] == "raw" and fp[2] is not None}
            hashed = [i for i, fp in enumerate(local_prints) if fp[0] == "raw" and fp[2] is None and fp[1] in sizes]
            for i, digest in zip(hashed, ex.map(counted(md5, "Hashing local files", len(hashed)), [left_local[i] for i in hashed])):
                local_prints[i] = (*local_prints[i][:2], digest)
    # unmatched storage files by path, and by what they can match: a zip's whole print, or a raw file's size
    unmatched = dict(zip(left_remote, remote_prints))
    by_zip, by_size = defaultdict(dict), defaultdict(dict)
    for path, fp in unmatched.items():
        if fp[0] == "raw":
            by_size[fp[1]][path] = fp[2]
        else:
            by_zip[fp][path] = None

    def alike(path, fp, p, other):
        if not same_content(fp, other):
            return False
        return fp[0] != "raw" or same_bytes is None or (fp[2] is not None and other[2] is not None) or same_bytes(path, p)

    def find(path, fp):
        if path in unmatched and alike(path, fp, path, unmatched[path]):
            return path
        if fp[0] != "raw":
            return next(iter(by_zip.get(fp, ())), None)
        return next((p for p in by_size.get(fp[1], {}) if alike(path, fp, p, unmatched[p])), None)

    matched, only_local = [], []
    for path, fp in zip(left_local, local_prints):
        found = find(path, fp)
        if found is None:
            only_local.append(path)
            continue
        old = unmatched.pop(found)
        del (by_size[old[1]] if old[0] == "raw" else by_zip[old])[found]
        matched.append((path, found))
    return matched, only_local, list(unmatched)


def plan_diff(local, remote, local_print, remote_print, md5=None):
    """(only local, only storage) lists of relative paths, ignoring renames. Arguments as in match_content."""
    _, only_local, only_bucket = match_content(local, remote, local_print, remote_print, md5=md5)
    return only_local, only_bucket


def plan_replace(local, remote, local_print, remote_print, differs=None, md5=None, same_bytes=None):
    """(renames, new, changed, only storage) for making the storage folder match the local one.

    renames: [(bucket path, local path)] with the same content under another name. changed: paths on both sides
    with different content. Arguments as in match_content.
    """
    matched, only_local, only_bucket = match_content(local, remote, local_print, remote_print, differs, md5, same_bytes)
    renames = [(r, l) for l, r in matched if l != r]
    targets = {l for _, l in renames}
    changed = [p for p in only_local if p in remote]
    new = [p for p in only_local if p not in remote]
    # an unmatched bucket file under a rename's new name or a changed file's name is overwritten, not left behind
    only_bucket = [p for p in only_bucket if p not in targets and p not in local]
    return renames, new, changed, only_bucket


def local_sizes(folder):
    """{relative path: size} of the ROM files under folder."""
    paths = [os.path.join(dirpath, f) for dirpath, files in downloads.walk_roms(folder, keep_dotfiles=True) for f in files]
    with ThreadPoolExecutor(s3.STAT_WORKERS) as ex:  # the stats wait on the network when the folder is a share
        return {os.path.relpath(p, folder).replace(os.sep, "/"): n for p, n in zip(paths, ex.map(os.path.getsize, paths))}


def diff_command(args):
    """Show the ROMs that are in only one of a local folder (default: the current directory) and a storage folder."""
    folder = os.path.abspath(os.path.expanduser(args.diff or os.getcwd()))
    if not os.path.isdir(folder):
        ui.fail(f"{folder} is not a folder", 2)
    systems = sorted(store.load_manifest()["systems"], key=lambda s: s["name"].lower())
    guess = store.guess_system(systems, folder)
    if args.system or args.json:  # no picker: scripts name the system (or it's guessed from the folder name)
        names = [s["bucket"] for s in systems]
        if args.system and args.system not in names:
            ui.fail(f"Unknown system {args.system!r}. Known: {', '.join(names[:8])}, … (see systems.json)", 2)
        if not args.system and guess is None:
            ui.fail("Can't tell which system this folder is: pass --system ID", 2)
        i = names.index(args.system) if args.system else guess
    else:
        i = picker.filter_list("🔍 Which system is this folder compared with?", [f"{s['name']}  ({s['bucket']}/)" for s in systems],
                        cursor=guess or 0, hint="/ filter · j/k move · Enter continue · Esc cancel")
    if i is None:
        print(ui.yellow("👋 Cancelled."))
        return 0
    bucket = systems[i]["bucket"]
    print(ui.bold(f"🔍 Compare {systems[i]['name']}") + ui.dim(f"  {folder} ↔ {s3.location()}/{bucket}/"))
    local = {p: n for p, n in local_sizes(folder).items() if not ignore.is_ignored(f"{bucket}/{p}")}
    try:
        remote = inventory.etags(bucket + "/")
        only_local, only_bucket = plan_diff(
            local, remote, lambda p: local_fingerprint(os.path.join(folder, *p.split("/"))),
            lambda p, size, etag: bucket_fingerprint(f"{bucket}/{p}", size, etag),
            md5=lambda p: file_md5(os.path.join(folder, *p.split("/"))))
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    if args.json:
        ui.emit_json({"system": bucket,
                      "only_local": [{"path": p, "size": local[p]} for p in only_local],
                      "only_bucket": [{"path": p, "size": remote[p][0]} for p in only_bucket]})
        return 0
    for title, paths, sizes, paint in (("Only in the folder", only_local, {p: local[p] for p in only_local}, ui.green),
                                       ("Only in storage", only_bucket, {p: remote[p][0] for p in only_bucket}, ui.yellow)):
        print(f"\n{ui.bold(title)}: {len(paths)} ({ui.human_size(sum(sizes.values()))})")
        for p in paths:
            print(paint(f"  {p} ") + ui.dim(ui.human_size(sizes[p])))
    if not only_local and not only_bucket:
        print(ui.green("\nSame games on both sides ✨"))
    return 0
