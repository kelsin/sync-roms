"""Storage plumbing: the S3 bucket, or a folder (e.g. a network share) in its place."""
import contextlib
import os
import shutil
import stat
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound

from . import runtime, ui


def safe_join(base, rel):
    """base/rel, or ValueError if rel (a bucket key or part of one) is empty, absolute or climbs out of base."""
    parts = rel.replace("\\", "/").split("/")
    if not rel or rel.startswith("/") or ".." in parts:
        raise ValueError(f"unsafe path: {rel!r}")
    path = os.path.join(base, rel)
    if os.path.commonpath([os.path.abspath(base), os.path.abspath(path)]) != os.path.abspath(base):
        raise ValueError(f"unsafe path: {rel!r}")
    return _on_disk(base, rel)


def _on_disk(base, rel):
    """base/rel spelled the way the disk has it. Some network shares store accented names decomposed (NFD) and find a
    file only by that exact spelling, so a composed key misses it. A name that isn't there keeps rel's spelling, under
    its parent's on-disk spelling."""
    path = os.path.join(base, rel)
    if rel.isascii() or os.path.lexists(path):
        return path
    for form in ("NFD", "NFC"):
        other = os.path.join(base, unicodedata.normalize(form, rel))
        if other != path and os.path.lexists(other):
            return other
    head, tail = os.path.split(rel)
    return os.path.join(_on_disk(base, head), tail) if head else path


JUNK_NAMES = {".DS_Store"}  # macOS Finder litter: never listed, cached, synced or scraped


def junk(key):
    """Whether a storage key or local path names OS litter, or one of sync-roms's own .part files, that sync-roms never
    treats as a file."""
    name = key.replace("\\", "/").rsplit("/", 1)[-1]
    return name in JUNK_NAMES or name.endswith(".part")


def mirror_sizes(root, prefix="", sizes=True):
    """{key: size} of the files under root whose key starts with prefix (a folder, ending in /).
    Without sizes the values are None: a network share answers a name listing fast but each size is a round trip."""
    paths = [os.path.join(folder, name) for folder, _, files in os.walk(os.path.join(root, prefix)) for name in files
             if not junk(name)]
    keys = [os.path.relpath(path, root).replace(os.sep, "/") for path in paths]
    if not sizes:
        return dict.fromkeys(keys)
    with ThreadPoolExecutor(STAT_WORKERS) as ex:  # the stats wait on the network, so many at once
        return dict(zip(keys, ex.map(os.path.getsize, paths)))


STAT_WORKERS = 32  # parallel stats on a folder: each is a round trip on a network share

ERRORS = (ClientError, BotoCoreError, OSError)  # what a bucket or a folder can raise


def missing(e):
    """Whether a storage error means the file isn't there."""
    return isinstance(e, FileNotFoundError) or (
        isinstance(e, ClientError) and e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"))


def read_root():
    """The folder reads come from (the local mirror, else the storage folder), or None when they come from storage."""
    return runtime._mirror_root or runtime.ROOT


def location():
    return runtime.ROOT or f"s3://{runtime.BUCKET}"


def access(write=False):
    """A short description of where files are stored and, for a bucket, which profiles are used."""
    if runtime.ROOT:
        return runtime.ROOT
    return f"read={runtime.PROFILE}  write={runtime.WRITE_PROFILE}" if write else f"{location()}  profile={runtime.PROFILE}"


_writing = set()  # keys write_file is writing, so an abort can remove their .part files


def remove_parts():
    """Remove the .part files of the writes in flight: a hard exit skips write_file's own cleanup."""
    for key in list(_writing):
        with contextlib.suppress(OSError):
            os.remove(safe_join(runtime.ROOT, key + ".part"))


def write_file(key, write):
    """Create the file for a key under the storage folder; write(tmp_path) fills a temporary file that then replaces it."""
    path = safe_join(runtime.ROOT, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _writing.add(key)
    try:
        write(path + ".part")
        tmp = safe_join(runtime.ROOT, key + ".part")  # a share may have stored the new name in another spelling
        os.replace(tmp, tmp[:-len(".part")])
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(safe_join(runtime.ROOT, key + ".part"))
        raise
    finally:
        _writing.discard(key)
    path = safe_join(runtime.ROOT, key)
    from . import inventory  # imported here: inventory reads storage through this module
    inventory.wrote(key, os.path.getsize(path))


def read_range(key, start, end):
    """Bytes start..end-1 of an object."""
    if read_root():
        with open(safe_join(read_root(), key), "rb") as f:
            f.seek(start)
            return f.read(end - start)
    return s3_client().get_object(Bucket=runtime.BUCKET, Key=key, Range=f"bytes={start}-{end - 1}")["Body"].read()


def list_sizes(prefix, sizes=True):
    if read_root():
        return mirror_sizes(read_root(), prefix, sizes)
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET, Prefix=prefix)
    return {o["Key"]: o["Size"] for page in pages for o in page.get("Contents", [])}


def list_folders():
    """Names of the top-level folders in storage (one listing, however many files they hold)."""
    if runtime.ROOT:
        with os.scandir(runtime.ROOT) as entries:
            return {e.name for e in entries if e.is_dir()}
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET, Delimiter="/")
    return {p["Prefix"].rstrip("/") for page in pages for p in page.get("CommonPrefixes", [])}


def stat_sizes(keys):
    """{key: size} of the keys that exist as files in the read folder, checked in parallel (one stat each, no folder walk)."""
    def size(key):
        try:
            st = os.stat(safe_join(read_root(), key))
        except (OSError, ValueError):
            return None
        return st.st_size if stat.S_ISREG(st.st_mode) else None
    keys = list(keys)
    with ThreadPoolExecutor(STAT_WORKERS) as ex:
        return {k: n for k, n in zip(keys, ex.map(size, keys)) if n is not None}


_s3 = {}


def s3_client(profile=None, connections=runtime.WORKERS):
    """Shared boto3 S3 client for a profile (one per connection pool size). Exits if the profile isn't configured."""
    profile = profile or runtime.PROFILE
    key = profile if connections == runtime.WORKERS else (profile, connections)
    if key not in _s3:
        import boto3  # slow to import, and a folder or a mirror never needs it
        try:
            session = boto3.Session(profile_name=profile)
        except ProfileNotFound:
            ui.fail(f"AWS profile '{profile}' not found; define it in ~/.aws/config and ~/.aws/credentials", 3)
        config = Config(max_pool_connections=connections, **({"s3": {"addressing_style": "path"}} if runtime.ENDPOINT else {}))
        _s3[key] = session.client("s3", endpoint_url=runtime.ENDPOINT, config=config)
    return _s3[key]


def copy_file(src, dst, callback=None, wrote=None):
    """Copy src to dst. callback(bytes) is called after each chunk is read, wrote(bytes) after it is written."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while chunk := fin.read(1024 * 1024):
            if callback:
                callback(len(chunk))
            fout.write(chunk)
            if wrote:
                wrote(len(chunk))


class CountingWriter:
    """A seekable file wrapper that reports each write to on_write(bytes), so downloads can still write ranges in parallel."""
    def __init__(self, f, on_write):
        self.f, self.on_write = f, on_write

    def write(self, data):
        n = self.f.write(data)
        self.on_write(len(data))
        return n

    def seek(self, *args):
        return self.f.seek(*args)

    def tell(self):
        return self.f.tell()

    def seekable(self):
        return True


DOWNLOAD_PARTS = 2  # ranges of one file fetched at once: every download has its own pool, and the client's connections are shared


def download(job, callback=None, wrote=None):
    """callback(bytes) is called as data arrives, wrote(bytes) as it is written to disk."""
    key, path, _ = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if read_root():
            copy_file(safe_join(read_root(), key), path + ".part", callback, wrote)
        else:
            from boto3.s3.transfer import TransferConfig
            with open(path + ".part", "wb") as f:
                s3_client().download_fileobj(runtime.BUCKET, key, CountingWriter(f, wrote) if wrote else f,
                                            Callback=callback, Config=TransferConfig(max_concurrency=DOWNLOAD_PARTS))
        os.replace(path + ".part", path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(path + ".part")
        raise


def get_text(key):
    if read_root():
        with open(safe_join(read_root(), key), encoding="utf-8") as f:
            return f.read()
    return s3_client().get_object(Bucket=runtime.BUCKET, Key=key)["Body"].read().decode("utf-8")


def fetch_texts(keys):
    keys = sorted(keys)
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        return dict(zip(keys, ex.map(get_text, keys)))


def put_text(key, text):
    if runtime.ROOT:
        def write(tmp):
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
        return write_file(key, write)
    body = text.encode("utf-8")
    out = s3_client(runtime.WRITE_PROFILE).put_object(Bucket=runtime.BUCKET, Key=key, Body=body)
    from . import inventory
    inventory.wrote(key, len(body), out.get("ETag"))


def put_file(key, path):
    if runtime.ROOT:
        return write_file(key, lambda tmp: shutil.copyfile(path, tmp))
    s3_client(runtime.WRITE_PROFILE).upload_file(path, runtime.BUCKET, key)


def list_with_etags(prefix):
    """{path under prefix: (size, etag)}. A folder has no ETags: its tag is "-" (like a multipart upload's has one), so the
    same path and size count as the same file and the rest is matched by content."""
    if runtime.ROOT:
        return {k[len(prefix):]: (size, "-") for k, size in mirror_sizes(runtime.ROOT, prefix).items()}
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET, Prefix=prefix)
    return {o["Key"][len(prefix):]: (o["Size"], o["ETag"]) for page in pages for o in page.get("Contents", [])
            if not o["Key"].endswith("/")}


def move_groups(moves):
    """(old key, new key) moves in groups that each run in order, so no move overwrites a file another still has to move:
    a chain (a → b, b → c) runs its last move first, and a cycle (a → b, b → a) first moves one file to a .part name
    in its folder. Groups don't touch each other's files."""
    by_old = dict(moves)
    targets = set(by_old.values())
    groups, seen = [], set()
    for start in [old for old, _ in moves if old not in targets] + [old for old, _ in moves]:  # chain starts, then cycles
        if start in seen:
            continue
        walk, key = [], start
        while key in by_old and key not in seen:
            seen.add(key)
            walk.append((key, by_old[key]))
            key = by_old[key]
        if key != start:
            groups.append(walk[::-1])
        else:
            tmp = start + ".part"
            groups.append([(start, tmp), *walk[:0:-1], (tmp, walk[0][1])])
    return groups


def move_keys(moves):
    """Move storage objects server-side: copy each (old key, new key), then delete the old one, in the order
    move_groups gives. Returns the failure count."""
    from . import inventory
    client = None if runtime.ROOT else s3_client(runtime.WRITE_PROFILE)

    def move(job):
        old, new = job
        try:
            if runtime.ROOT:
                dest = safe_join(runtime.ROOT, new)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                os.replace(safe_join(runtime.ROOT, old), dest)
            else:
                client.copy({"Bucket": runtime.BUCKET, "Key": old}, runtime.BUCKET, new)
                client.delete_object(Bucket=runtime.BUCKET, Key=old)
            inventory.moved(old, new)  # here, not in the loop below, so a move that finishes after ^C is recorded too
            return job, None
        except ERRORS as e:
            return job, e

    def run(group):
        """The group's moves in order; after one fails the rest aren't tried, as they would overwrite its file."""
        out = []
        for job in group:
            out.append(move(job) if not out or out[-1][1] is None else (job, OSError(f"skipped: {out[-1][0][0]} wasn't moved")))
        (start, tmp), (_, name) = group[0], group[-1]
        if tmp == group[-1][0] and out[0][1] is None and out[-1][1] is not None:  # a cycle stopped with a file parked
            if out[1][1] is not None and move((tmp, start))[1] is None:  # nothing took its old name yet
                out[-1] = (out[-1][0], OSError(f"skipped: moved back to {start}"))
            else:
                out[-1] = (out[-1][0], OSError(f"left under this name: it should be named {name}"))
        return out

    groups = move_groups(moves)
    total, i = sum(map(len, groups)), 0
    failed, futs = 0, []
    print(ui.bold(f"\n🚚 Moving {len(moves)} renamed file(s)"))
    ex = ThreadPoolExecutor(runtime.WORKERS)
    try:
        futs += [ex.submit(run, group) for group in groups]
        for f in futs:
            for job, error in f.result():
                i += 1
                prog = ui.dim(f"[{i}/{total}]")
                if error is None:
                    print(f"  {prog} ✅ {job[0]} → {job[1]}")
                else:
                    failed += 1
                    print(f"  {prog} ❌ {ui.red(job[0])}: {str(error).strip()}")
    except KeyboardInterrupt:
        from . import downloads  # imported here: downloads reads storage through this module
        ex.shutdown(wait=False, cancel_futures=True)
        running = [f for f in futs if f.running()]
        print(ui.yellow(f"🛑 Interrupted — finishing {len(running)} move(s) in flight. ^C again to abort now."))
        try:
            while any(f.running() for f in running):
                time.sleep(ui.POLL)
        except KeyboardInterrupt:
            print(ui.red("🛑 Aborted"))
            inventory.flush()  # hard_exit skips the flush as sync-roms exits
            downloads.hard_exit()
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return failed


def delete_keys(keys):
    """Delete storage objects (or storage folder files) in batches of 1000. Returns the errors reported."""
    from . import inventory
    errors = []
    for i in range(0, len(keys), 1000):
        batch = keys[i:i + 1000]
        if runtime.ROOT:
            for k in batch:
                try:
                    os.remove(safe_join(runtime.ROOT, k))
                    inventory.removed([k])
                except OSError as e:
                    errors.append({"Key": k, "Message": str(e)})
            print(ui.dim(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}"))
            continue
        out = s3_client(runtime.WRITE_PROFILE).delete_objects(
            Bucket=runtime.BUCKET, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
        failed = out.get("Errors", [])
        errors += failed
        inventory.removed(set(batch) - {e.get("Key") for e in failed})
        print(ui.dim(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}"))
    return errors
