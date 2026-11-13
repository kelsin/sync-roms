"""Uploading ROMs to storage."""
import functools
import mimetypes
import os
import queue
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError

from . import diff, downloads, ignore, inventory, picker, runtime, s3, scrape_plan, store, ui


UPLOAD_MULTIPART_AT = 64 * 1024 * 1024  # files this big go up as parallel parts
UPLOAD_PART = 32 * 1024 * 1024


def upload_workers():
    """Requests in flight at once. Uploads wait on the network, not the CPU, so run several per core.
    Capped low: dozens of simultaneous fresh TLS handshakes have crashed OpenSSL's certificate check."""
    return min(16, 4 * (os.cpu_count() or 4))


def plan_rom_upload(root, bucket, existing):
    """(new, changed, same) lists of (key, path, size) for the ROM files under root, keyed bucket/relative path.

    existing: {key: size} listing of storage folder; a file whose size matches is the same.
    """
    paths = [os.path.join(dirpath, f) for dirpath, files in downloads.walk_roms(root, keep_dotfiles=True) for f in sorted(files)]
    with ThreadPoolExecutor(s3.STAT_WORKERS) as ex:  # the stats wait on the network when the folder is a share
        sizes = list(ex.map(os.path.getsize, paths))
    new, changed, same = [], [], []
    for path, size in zip(paths, sizes):
        key = f"{bucket}/{os.path.relpath(path, root).replace(os.sep, '/')}"
        if ignore.is_ignored(key):  # never uploaded: storage keeps its own copy, or none
            continue
        if key not in existing:
            new.append((key, path, size))
        elif existing[key] == size:
            same.append((key, path, size))
        else:
            changed.append((key, path, size))
    return new, changed, same


@functools.lru_cache(maxsize=None)
def queue_when_done_class():
    """The s3transfer subscriber that queues (n, job, future) when job n's transfer ends; built on first use since boto3 is slow to import."""
    from s3transfer.subscribers import BaseSubscriber

    class QueueWhenDone(BaseSubscriber):
        def __init__(self, done, n, job, moved=None):
            self.done, self.n, self.job, self.moved = done, n, job, moved  # moved(bytes) is called as parts go up

        def on_progress(self, future, bytes_transferred, **kwargs):
            if self.moved:
                self.moved(bytes_transferred)

        def on_done(self, future, **kwargs):
            self.done.put((self.n, self.job, future))

    return QueueWhenDone


class FailedUpload:
    """Stands in for a finished transfer of a job that failed before it could be queued."""
    def __init__(self, error):
        self.error = error

    def result(self):
        raise self.error


def run_copies(todo):
    """run_uploads for a storage folder: copy (key, path, size[, shrink]) jobs into it. Returns the failure count."""
    print(ui.bold(f"\n📁 Copying {len(todo)} file(s)") + ui.dim(f"  to {runtime.ROOT}"))

    order = sorted(todo, key=lambda j: -j[2])
    moved = ui.ByteProgress([j[2] for j in order])
    bar = ui.ProgressBar(len(todo), moved.fraction, moved.total)

    def copy(n):
        job = order[n]
        try:
            def write(tmp):
                if len(job) > 3:
                    scrape_plan.shrink_png(job[1], tmp, job[3])
                else:
                    s3.copy_file(job[1], tmp, lambda b: moved.add(n, b))
            s3.write_file(job[0], write)
            return job, None
        except Exception as e:
            return job, e

    failed, futs = 0, []
    ex = ThreadPoolExecutor(runtime.WORKERS)
    try:
        futs += [ex.submit(copy, n) for n in range(len(order))]
        for i, f in enumerate(futs, 1):
            job, error = ui.wait_drawing(bar, i - 1, f.result)
            moved.finish(i - 1)
            prog = ui.dim(f"[{i}/{len(todo)}]")
            if error is None:
                bar.say(f"  {prog} ✅ {job[0]}")
            else:
                failed += 1
                bar.say(f"  {prog} ❌ {ui.red(job[0])}: {str(error).strip()}")
            bar.draw(i)
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        running = [f for f in futs if f.running()]
        bar.say(ui.yellow(f"🛑 Interrupted — finishing {len(running)} copy(ies) in flight. ^C again to abort now."))
        try:
            while any(f.running() for f in running):
                bar.draw(sum(f.done() for f in futs))
                time.sleep(ui.POLL)
        except KeyboardInterrupt:
            bar.clear()
            print(ui.red("🛑 Aborted"))
            downloads.hard_exit()
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        bar.clear()
    return failed


def run_uploads(todo):
    """Upload (key, path, size[, shrink]) jobs through one shared pool of requests, so small files and the parts of
    big ones all keep the connection busy. Biggest files start first so a long one never trails at the end.
    A 4th element (max width, max height) means: upload path shrunk to fit it, shrunk on every core while the others upload."""
    if runtime.ROOT:
        return run_copies(todo)
    workers = upload_workers()
    client = s3.s3_client(runtime.WRITE_PROFILE, connections=workers)
    try:
        client.head_bucket(Bucket=runtime.BUCKET)  # load the CA store and open one connection before the parallel handshakes
    except (ClientError, BotoCoreError):
        pass
    print(ui.bold(f"\n☁️  Uploading {len(todo)} file(s)") + ui.dim(f"  {workers} requests at once"))
    from boto3.s3.transfer import TransferConfig, create_transfer_manager
    config = TransferConfig(max_concurrency=workers, multipart_threshold=UPLOAD_MULTIPART_AT,
                            multipart_chunksize=UPLOAD_PART)
    done, failed = queue.Queue(), 0
    order = sorted(todo, key=lambda j: -j[2])
    moved = ui.ByteProgress([j[2] for j in order])
    bar = ui.ProgressBar(len(todo), moved.fraction, moved.total)
    try:
        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(os.cpu_count() or 4) as shrinkers, \
                create_transfer_manager(client, config) as manager:
            sent = {}  # job n -> bytes sent (a shrunk PNG is smaller than its file)

            def send(job, path, n):
                sent[n] = job[2] if path == job[1] else os.path.getsize(path)
                manager.upload(path, runtime.BUCKET, job[0],
                               {"ContentType": mimetypes.guess_type(path)[0] or "application/octet-stream"},
                               [queue_when_done_class()(done, n, job, lambda b: moved.add(n, b))])

            def shrink_and_send(job, n):
                try:
                    art = os.path.join(tmp, f"{n}.png")
                    scrape_plan.shrink_png(job[1], art, job[3])
                    send(job, art, n)
                except Exception as e:
                    done.put((n, job, FailedUpload(e)))

            try:
                def submit_all():  # queueing blocks once the transfer queue is full, so it can't hold up the output
                    for n, job in enumerate(order):
                        try:
                            if len(job) > 3:
                                shrinkers.submit(shrink_and_send, job, n)
                            else:
                                send(job, job[1], n)
                        except Exception as e:
                            done.put((n, job, FailedUpload(e)))

                threading.Thread(target=submit_all, daemon=True).start()
                for i in range(1, len(todo) + 1):
                    n, job, future = ui.wait_drawing(bar, i - 1, done.get)
                    moved.finish(n)
                    prog = ui.dim(f"[{i}/{len(todo)}]")
                    try:
                        future.result()
                        inventory.wrote(job[0], sent[n])  # its ETag isn't known: a multipart upload's isn't the MD5
                        bar.say(f"  {prog} ✅ {job[0]}")
                    except Exception as e:
                        failed += 1
                        bar.say(f"  {prog} ❌ {ui.red(job[0])}: {str(e).strip()}")
                    bar.draw(i)
            except KeyboardInterrupt:
                shrinkers.shutdown(wait=False, cancel_futures=True)
                raise
    except KeyboardInterrupt:
        bar.say(ui.yellow("🛑 Interrupted — dropping queued uploads, finishing the ones in flight..."))
        raise
    finally:
        bar.clear()
    return failed


def upload_command(args):
    """Upload the ROMs in one folder (default: the current directory) to storage folder of a system you pick."""
    folder = os.path.abspath(os.path.expanduser(args.upload or os.getcwd()))
    if not os.path.isdir(folder):
        ui.fail(f"{folder} is not a folder", 2)
    systems = sorted(store.load_manifest()["systems"], key=lambda s: s["name"].lower())
    guess = store.guess_system(systems, folder)
    i = picker.filter_list("☁️  Which system are you uploading?", [f"{s['name']}  ({s['bucket']}/)" for s in systems],
                    cursor=guess or 0, hint="/ filter · j/k move · Enter continue · Esc cancel")
    if i is None:
        print(ui.yellow("👋 Cancelled."))
        return 0
    bucket = systems[i]["bucket"]
    print(ui.bold(f"☁️  {'Replace' if args.replace else 'Upload'} {systems[i]['name']}") + ui.dim(f"  {s3.access(True)}  {folder} → {s3.location()}/{bucket}/"))
    if args.replace:
        return replace_command(args, folder, systems[i])
    try:
        print("☁️  Listing what's already there...")
        existing = inventory.files(bucket + "/")
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    new, changed, same = plan_rom_upload(folder, bucket, existing)
    print(f"\n💿 New: {ui.bold(str(len(new)))} ({ui.human_size(sum(f[2] for f in new))})")
    print(f"♻️  Different size, would overwrite: {ui.bold(str(len(changed)))} ({ui.human_size(sum(f[2] for f in changed))})")
    print(f"⚡ Already there: {len(same)}")
    todo = new + changed
    if not todo:
        print(ui.green("Nothing to upload ✨"))
        return 0
    for key, _, size in changed[:10]:
        print(ui.yellow(f"     overwrite {key} {ui.dim(ui.human_size(size))}"))
    if len(changed) > 10:
        print(ui.yellow(f"     … and {len(changed) - 10} more"))
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing uploaded"))
        for key, _, size in new[:20]:
            print(f"  {key} {ui.dim(ui.human_size(size))}")
        if len(new) > 20:
            print(ui.dim(f"  … and {len(new) - 20} more"))
        return 0
    if not ui.confirm(f"☁️  Upload {len(todo)} file(s) to {s3.location()}/{bucket}/" + (f", overwriting {len(changed)}" if changed else "") + "?", default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    failed = run_uploads(todo)
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def replace_command(args, folder, system):
    """Make a storage folder match a local one: move renamed files, upload new and changed ones, and delete the rest
    that you pick."""
    bucket = system["bucket"]
    local = {p: n for p, n in diff.local_sizes(folder).items() if not ignore.is_ignored(f"{bucket}/{p}")}
    md5 = functools.lru_cache(maxsize=None)(lambda p: diff.file_md5(os.path.join(folder, *p.split("/"))))  # each file hashed once
    try:
        print("☁️  Listing what's already there...")
        remote = inventory.etags(bucket + "/")
        print("🔍 Matching files by content...")
        renames, new, changed, only_bucket = diff.plan_replace(
            local, remote, lambda p: diff.local_fingerprint(os.path.join(folder, *p.split("/"))),
            lambda p, size, etag: diff.bucket_fingerprint(f"{bucket}/{p}", size, etag),
            lambda p, etag: "-" not in etag and md5(p) != etag.strip('"'), md5,
            lambda p, r: diff.same_bytes(os.path.join(folder, *p.split("/")), f"{bucket}/{r}", local[p]))
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    print(f"\n💿 New: {ui.bold(str(len(new)))} ({ui.human_size(sum(local[p] for p in new))})")
    print(f"♻️  Different content, would overwrite: {ui.bold(str(len(changed)))} ({ui.human_size(sum(local[p] for p in changed))})")
    print(f"🚚 Renamed, would move in storage: {ui.bold(str(len(renames)))}")
    print(f"🗑️  Only in storage, not renames: {ui.bold(str(len(only_bucket)))} ({ui.human_size(sum(remote[p][0] for p in only_bucket))})")
    for old, newname in renames if args.dry_run else renames[:10]:
        print(ui.dim(f"     {old} → {newname}"))
    if len(renames) > 10 and not args.dry_run:
        print(ui.dim(f"     … and {len(renames) - 10} more"))
    for p in changed[:10]:
        print(ui.yellow(f"     overwrite {bucket}/{p} {ui.dim(ui.human_size(local[p]))}"))
    if len(changed) > 10:
        print(ui.yellow(f"     … and {len(changed) - 10} more"))
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing changed"))
        for p in new[:20]:
            print(f"  {bucket}/{p} {ui.dim(ui.human_size(local[p]))}")
        if len(new) > 20:
            print(ui.dim(f"  … and {len(new) - 20} more"))
        for p in only_bucket[:20]:
            print(ui.red(f"  would ask about deleting {bucket}/{p} ") + ui.dim(ui.human_size(remote[p][0])))
        if len(only_bucket) > 20:
            print(ui.dim(f"  … and {len(only_bucket) - 20} more"))
        return 0
    delete = []
    if only_bucket:
        picked = picker.filter_list(f"🗑️  Delete from {s3.location()}/{bucket}/ (they match no local file) — untick to keep",
                             only_bucket, multi=True, initial=[True] * len(only_bucket),
                             extras=[[(ui.human_size(remote[p][0]), "dim")] for p in only_bucket],
                             hint="/ filter · j/k move · Space toggle · a toggle all shown · Enter done")
        delete = [f"{bucket}/{p}" for p, on in zip(only_bucket, picked) if on]
    uploads = [(f"{bucket}/{p}", os.path.join(folder, *p.split("/")), local[p]) for p in new + changed]
    if not (renames or uploads or delete):
        print(ui.green("\nNothing to do ✨"))
        return 0
    print(f"\nThis will move {len(renames)}, upload {len(uploads)} ({len(changed)} overwriting), "
          f"delete {len(delete)} and keep {len(only_bucket) - len(delete)} in {s3.location()}/{bucket}/")
    if not ui.confirm("☁️  Go ahead?", default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    failed = s3.move_keys([(f"{bucket}/{old}", f"{bucket}/{n}") for old, n in renames]) if renames else 0
    failed += run_uploads(uploads) if uploads else 0
    if delete and failed:
        print(ui.yellow(f"\n⚠️  {failed} failure(s) above, so nothing was deleted; run it again once they are sorted"))
    elif delete:
        errors = s3.delete_keys(delete)
        failed += len(errors)
        for e in errors:
            print(ui.red(f"  ❌ {e.get('Key')}: {e.get('Message')}"))
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0
