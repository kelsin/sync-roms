"""Storage plumbing: the S3 bucket, or a folder (e.g. a network share) in its place."""
import contextlib
import os
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor

import boto3
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
    return path


def mirror_sizes(root, prefix="", sizes=True):
    """{key: size} of the files under root whose key starts with prefix (a folder, ending in /).
    Without sizes the values are None: a network share answers a name listing fast but each size is a round trip."""
    paths = [os.path.join(folder, name) for folder, _, files in os.walk(os.path.join(root, prefix)) for name in files]
    keys = [os.path.relpath(path, root).replace(os.sep, "/") for path in paths]
    if not sizes:
        return dict.fromkeys(keys)
    with ThreadPoolExecutor(STAT_WORKERS) as ex:  # the stats wait on the network, so many at once
        return dict(zip(keys, ex.map(os.path.getsize, paths)))


STAT_WORKERS = 32  # parallel stats on a folder: each is a round trip on a network share

ERRORS = (ClientError, BotoCoreError, OSError)  # what a bucket or a folder can raise


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


def write_file(key, write):
    """Create the file for a key under the storage folder; write(tmp_path) fills a temporary file that then replaces it."""
    path = safe_join(runtime.ROOT, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write(path + ".part")
    os.replace(path + ".part", path)


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


def download(job, callback=None, wrote=None):
    """callback(bytes) is called as data arrives, wrote(bytes) as it is written to disk."""
    key, path, _ = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if read_root():
        copy_file(safe_join(read_root(), key), path + ".part", callback, wrote)
        os.replace(path + ".part", path)
        return
    try:
        with open(path + ".part", "wb") as f:
            s3_client().download_fileobj(runtime.BUCKET, key, CountingWriter(f, wrote) if wrote else f, Callback=callback)
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
    s3_client(runtime.WRITE_PROFILE).put_object(Bucket=runtime.BUCKET, Key=key, Body=text.encode("utf-8"))


def list_with_etags(prefix):
    """{path under prefix: (size, etag)}. A folder has no ETags: its tag has a "-" (like a multipart upload's), so the
    same path and size count as the same file and the rest is matched by content."""
    if runtime.ROOT:
        return {k[len(prefix):]: (size, f"{int(os.path.getmtime(safe_join(runtime.ROOT, k)))}-{size}")
                for k, size in mirror_sizes(runtime.ROOT, prefix).items() if not k.endswith("/")}
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET, Prefix=prefix)
    return {o["Key"][len(prefix):]: (o["Size"], o["ETag"]) for page in pages for o in page.get("Contents", [])
            if not o["Key"].endswith("/")}


def move_keys(moves):
    """Move storage objects server-side: copy each (old key, new key), then delete the old one. Returns the failure count."""
    client = None if runtime.ROOT else s3_client(runtime.WRITE_PROFILE)

    def move(job):
        old, new = job
        try:
            if runtime.ROOT:
                dest = safe_join(runtime.ROOT, new)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                os.replace(safe_join(runtime.ROOT, old), dest)
                return job, None
            client.copy({"Bucket": runtime.BUCKET, "Key": old}, runtime.BUCKET, new)
            client.delete_object(Bucket=runtime.BUCKET, Key=old)
            return job, None
        except ERRORS as e:
            return job, e

    failed = 0
    print(ui.bold(f"\n🚚 Moving {len(moves)} renamed file(s)"))
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        for i, (job, error) in enumerate(ex.map(move, moves), 1):
            prog = ui.dim(f"[{i}/{len(moves)}]")
            if error is None:
                print(f"  {prog} ✅ {job[0]} → {job[1]}")
            else:
                failed += 1
                print(f"  {prog} ❌ {ui.red(job[0])}: {str(error).strip()}")
    return failed


def delete_keys(keys):
    """Delete storage objects (or storage folder files) in batches of 1000. Returns the errors reported."""
    errors = []
    for i in range(0, len(keys), 1000):
        batch = keys[i:i + 1000]
        if runtime.ROOT:
            for k in batch:
                try:
                    os.remove(safe_join(runtime.ROOT, k))
                except OSError as e:
                    errors.append({"Key": k, "Message": str(e)})
            print(ui.dim(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}"))
            continue
        out = s3_client(runtime.WRITE_PROFILE).delete_objects(
            Bucket=runtime.BUCKET, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
        errors += out.get("Errors", [])
        print(ui.dim(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}"))
    return errors
