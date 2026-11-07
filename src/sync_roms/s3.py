"""Storage plumbing: the S3 bucket, or a folder (e.g. a network share) in its place."""
import os
import shutil
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


def mirror_sizes(root, prefix=""):
    """{key: size} of the files under root whose key starts with prefix (a folder, ending in /)."""
    out = {}
    for folder, _, files in os.walk(os.path.join(root, prefix)):
        for name in files:
            path = os.path.join(folder, name)
            out[os.path.relpath(path, root).replace(os.sep, "/")] = os.path.getsize(path)
    return out


ERRORS = (ClientError, BotoCoreError, OSError)  # what a bucket or a folder can raise


def read_root():
    """The folder reads come from (the local mirror, else the storage folder), or None when they come from the bucket."""
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


def list_sizes(prefix):
    if read_root():
        return mirror_sizes(read_root(), prefix)
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=runtime.BUCKET, Prefix=prefix)
    return {o["Key"]: o["Size"] for page in pages for o in page.get("Contents", [])}


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


def copy_file(src, dst, callback=None):
    """Copy src to dst, calling callback(bytes) after each chunk."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while chunk := fin.read(1024 * 1024):
            fout.write(chunk)
            if callback:
                callback(len(chunk))


def download(job, callback=None):
    """callback(bytes) is called as data arrives."""
    key, path, _ = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if read_root():
        copy_file(safe_join(read_root(), key), path + ".part", callback)
        os.replace(path + ".part", path)
        return
    s3_client().download_file(runtime.BUCKET, key, path, Callback=callback)


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
    """Move bucket objects server-side: copy each (old key, new key), then delete the old one. Returns the failure count."""
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
    """Delete bucket objects (or storage folder files) in batches of 1000. Returns the errors reported."""
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
