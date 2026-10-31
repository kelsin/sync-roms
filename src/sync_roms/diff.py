"""Comparing and replacing local files against the bucket."""
import hashlib
import io
import os
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError

from . import downloads, picker, runtime, s3, store, ui


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
        r = s3.s3_client().get_object(Bucket=runtime.BUCKET, Key=self.key, Range=f"bytes={start}-{end - 1}")
        return r["Body"].read()

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
    try:
        return zip_fingerprint(path)
    except zipfile.BadZipFile:
        return ("raw", os.path.getsize(path), file_md5(path))


def bucket_fingerprint(key, size, etag):
    try:
        return zip_fingerprint(RangeReader(key, size))
    except (zipfile.BadZipFile, ClientError, BotoCoreError):
        etag = etag.strip('"')
        return ("raw", size, None if "-" in etag else etag)  # a multipart upload's ETag isn't an md5


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


def match_content(local, remote, local_print, remote_print, differs=None):
    """([(local path, bucket path)] with the same content, only local, only bucket) lists, ignoring names.

    local: {path: size}; remote: {path: (size, etag)}. A file with the same path and size on both sides is the same
    without reading it; the rest are matched by content, a file with the same path first. local_print(path) /
    remote_print(path, size, etag) return a fingerprint, and are only called for the files left over.
    differs(path, etag), if given, is asked about same-path same-size files and returns True when their bytes are
    known to differ; those are then matched by content too.
    """
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        same = [p for p, size in local.items() if p in remote and remote[p][0] == size]
        suspect = {p for p, d in zip(same, ex.map(counted(lambda p: differs(p, remote[p][1]), "Checking same-size files", len(same)), same)) if d} if differs else set()
        left_local = sorted(p for p, size in local.items() if p not in remote or remote[p][0] != size or p in suspect)
        left_remote = sorted(p for p, (size, _) in remote.items() if p not in local or local[p] != size or p in suspect)
        local_prints = list(ex.map(counted(local_print, "Reading local files", len(left_local)), left_local))
        remote_prints = list(ex.map(counted(lambda p: remote_print(p, *remote[p]), "Reading bucket files", len(left_remote)),
                                    left_remote))
    unmatched = list(zip(left_remote, remote_prints))
    matched, only_local = [], []
    for path, fp in zip(left_local, local_prints):
        candidates = sorted(range(len(unmatched)), key=lambda i: unmatched[i][0] != path)
        for i in candidates:
            if same_content(fp, unmatched[i][1]):
                matched.append((path, unmatched.pop(i)[0]))
                break
        else:
            only_local.append(path)
    return matched, only_local, [p for p, _ in unmatched]


def plan_diff(local, remote, local_print, remote_print):
    """(only local, only bucket) lists of relative paths, ignoring renames. Arguments as in match_content."""
    _, only_local, only_bucket = match_content(local, remote, local_print, remote_print)
    return only_local, only_bucket


def plan_replace(local, remote, local_print, remote_print, differs=None):
    """(renames, new, changed, only bucket) for making the bucket folder match the local one.

    renames: [(bucket path, local path)] with the same content under another name. changed: paths on both sides
    with different content. Arguments as in match_content.
    """
    matched, only_local, only_bucket = match_content(local, remote, local_print, remote_print, differs)
    renames = [(r, l) for l, r in matched if l != r]
    targets = {l for _, l in renames}
    changed = [p for p in only_local if p in remote]
    new = [p for p in only_local if p not in remote]
    # an unmatched bucket file under a rename's new name or a changed file's name is overwritten, not left behind
    only_bucket = [p for p in only_bucket if p not in targets and p not in local]
    return renames, new, changed, only_bucket


def local_sizes(folder):
    """{relative path: size} of the ROM files under folder."""
    sizes = {}
    for dirpath, files in downloads.walk_roms(folder, keep_dotfiles=True):
        for f in files:
            path = os.path.join(dirpath, f)
            sizes[os.path.relpath(path, folder).replace(os.sep, "/")] = os.path.getsize(path)
    return sizes


def diff_command(args):
    """Show the ROMs that are in only one of a local folder (default: the current directory) and a bucket folder."""
    folder = os.path.abspath(os.path.expanduser(args.diff or os.getcwd()))
    if not os.path.isdir(folder):
        raise SystemExit(ui.red(f"❌ {folder} is not a folder"))
    systems = sorted(store.load_manifest()["systems"], key=lambda s: s["name"].lower())
    guess = store.guess_system(systems, folder)
    i = picker.filter_list("🔍 Which system is this folder compared with?", [f"{s['name']}  ({s['bucket']}/)" for s in systems],
                    cursor=guess or 0, hint="type to filter · ↑/↓ move · Enter continue · Esc cancel")
    if i is None:
        print(ui.yellow("👋 Cancelled."))
        return 0
    bucket = systems[i]["bucket"]
    print(ui.bold(f"🔍 Compare {systems[i]['name']}") + ui.dim(f"  {folder} ↔ s3://{runtime.BUCKET}/{bucket}/"))
    local = local_sizes(folder)
    try:
        remote = s3.list_with_etags(bucket + "/")
        only_local, only_bucket = plan_diff(
            local, remote, lambda p: local_fingerprint(os.path.join(folder, *p.split("/"))),
            lambda p, size, etag: bucket_fingerprint(f"{bucket}/{p}", size, etag))
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(ui.red(f"❌ {e}"))
    for title, paths, sizes, paint in (("Only in the folder", only_local, {p: local[p] for p in only_local}, ui.green),
                                       ("Only in the bucket", only_bucket, {p: remote[p][0] for p in only_bucket}, ui.yellow)):
        print(f"\n{ui.bold(title)}: {len(paths)} ({ui.human_size(sum(sizes.values()))})")
        for p in paths:
            print(paint(f"  {p} ") + ui.dim(ui.human_size(sizes[p])))
    if not only_local and not only_bucket:
        print(ui.green("\nSame games on both sides ✨"))
    return 0
