import contextlib
import io
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import argparse  # noqa: E402
from test_inventory import StorageFolder  # noqa: E402
from sync_roms import downloads, ignore, inventory, runtime, s3, scrape_plan, store, ui, upload, usersettings  # noqa: E402

SYSTEMS = [
    {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba", "onion": "GBA"}},
    {"name": "Mega Drive", "bucket": "genesis", "folders": {"esde": "megadrive", "knulli": "megadrive"}},
    {"name": "WonderSwan", "bucket": "wonderswan", "folders": {"esde": "wonderswan", "onion": "WS"}},
    {"name": "Neo Geo Pocket", "bucket": "ngp", "folders": {"esde": "ngp", "onion": "WS", "knulli": None}},
]


def touch(root, rel, size=1):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)


class GuessSystemTest(unittest.TestCase):
    def guess(self, folder):
        i = store.guess_system(SYSTEMS, folder)
        return None if i is None else SYSTEMS[i]["bucket"]

    def test_bucket_id(self):
        self.assertEqual(self.guess("/cards/sd/genesis"), "genesis")

    def test_frontend_folder_any_layout_and_case(self):
        self.assertEqual(self.guess("/cards/sd/megadrive"), "genesis")
        self.assertEqual(self.guess("/cards/sd/Roms/GBA/"), "gba")

    def test_shared_folder_takes_first_system(self):
        self.assertEqual(self.guess("/cards/sd/WS"), "wonderswan")

    def test_unknown_folder(self):
        self.assertIsNone(self.guess("/cards/sd/misc"))


class PlanRomUploadTest(unittest.TestCase):
    def test_new_changed_same_and_ignored_files(self):
        with tempfile.TemporaryDirectory() as root:
            touch(root, "a.gba", 10)
            touch(root, "b.gba", 20)
            touch(root, "c.gba", 30)
            touch(root, "Disc/d.chd", 40)
            touch(root, "gamelist.xml")
            touch(root, "images/a.png")
            touch(root, ".DS_Store")
            touch(root, "._a.gba")
            touch(root, ".Trashes/x.gba")
            touch(root, ".hack.gba", 50)
            existing = {"gba/b.gba": 20, "gba/c.gba": 99, "gba/other.gba": 5}
            new, changed, same = upload.plan_rom_upload(root, "gba", existing)
        self.assertEqual(sorted((k, s) for k, _, s in new), [("gba/.hack.gba", 50), ("gba/Disc/d.chd", 40), ("gba/a.gba", 10)])
        self.assertEqual([(k, s) for k, _, s in changed], [("gba/c.gba", 30)])
        self.assertEqual([(k, s) for k, _, s in same], [("gba/b.gba", 20)])


class IgnoredUploadTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(ignore, "_keys", frozenset({"gba/b.gba"}))
        p.start()
        self.addCleanup(p.stop)

    def test_plan_rom_upload_skips_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            touch(root, "a.gba", 10)
            touch(root, "b.gba", 20)
            new, changed, same = upload.plan_rom_upload(root, "gba", {})
        self.assertEqual([k for k, _, _ in new + changed + same], ["gba/a.gba"])

    def test_replace_never_uploads_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            touch(root, "a.gba", 10)
            touch(root, "b.gba", 20)
            out = io.StringIO()
            with mock.patch.object(inventory, "etags", lambda prefix: {}), contextlib.redirect_stdout(out):
                upload.replace_command(argparse.Namespace(dry_run=True), root, SYSTEMS[0])
        self.assertIn("gba/a.gba", out.getvalue())
        self.assertNotIn("b.gba", out.getvalue())

    def test_replace_never_deletes_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            touch(root, "a.gba", 10)
            out = io.StringIO()
            listing = {"a.gba": (10, "-"), "b.gba": (20, "-")}
            with mock.patch.object(inventory, "etags", lambda prefix: inventory._unignored(listing, prefix)), \
                    contextlib.redirect_stdout(out):
                upload.replace_command(argparse.Namespace(dry_run=True), root, SYSTEMS[0])
        self.assertNotIn("would ask about deleting", out.getvalue())


class OwnTempTest(unittest.TestCase):
    def test_own_temp_folders_are_never_uploaded(self):
        from sync_roms import diff
        with tempfile.TemporaryDirectory() as root:
            touch(root, "a.gba")
            touch(root, ".hack.gba")
            for rel in (".chd-1/a.bin", ".xiso-2/b.iso", ".unzip-3/c.gba", "Disc/.unzip-4/d.gba"):
                touch(root, rel)
            new, _, _ = upload.plan_rom_upload(root, "gba", {})
            self.assertEqual(sorted(k for k, _, _ in new), ["gba/.hack.gba", "gba/a.gba"])
            self.assertEqual(sorted(diff.local_sizes(root)), [".hack.gba", "a.gba"])


class ReplaceContentTest(unittest.TestCase):
    """upload --replace on a storage folder: raw files that only share a size are not a rename."""

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        for p in (mock.patch.object(runtime, "ROOT", self.storage.name), mock.patch.object(runtime, "_mirror_root", None)):
            p.start()
            self.addCleanup(p.stop)

    def replace(self, local, remote):
        with tempfile.TemporaryDirectory() as root:
            for rel, data in local.items():
                with open(os.path.join(root, rel), "wb") as f:
                    f.write(data)
            for rel, data in remote.items():
                os.makedirs(os.path.join(self.storage.name, "gba"), exist_ok=True)
                with open(os.path.join(self.storage.name, "gba", rel), "wb") as f:
                    f.write(data)
            listing = {rel: (len(data), "-") for rel, data in remote.items()}
            out = io.StringIO()
            with mock.patch.object(inventory, "etags", lambda prefix: listing), contextlib.redirect_stdout(out):
                upload.replace_command(argparse.Namespace(dry_run=True), root, SYSTEMS[0])
        return out.getvalue()

    def test_big_files_differing_between_the_samples_are_not_a_rename(self):
        size = 9 << 20
        a = bytearray(b"A" * size)
        a[(1 << 20) + 100] = ord("B")  # past the first 1 MiB sample, before the second
        out = self.replace({"new.iso": b"A" * size}, {"old.iso": bytes(a)})
        self.assertNotIn("→", out)
        self.assertIn("would ask about deleting gba/old.iso", out)

    def test_big_file_under_a_new_name_is_a_rename_not_marked_sampled(self):
        out = self.replace({"new.iso": b"A" * (9 << 20)}, {"old.iso": b"A" * (9 << 20)})
        self.assertIn("old.iso → new.iso", out)
        self.assertNotIn("samples", out)

    def test_same_size_different_content_is_new_not_a_rename(self):
        out = self.replace({"Game B (USA).gba": b"B" * 4096}, {"Game A (Europe).gba": b"A" * 4096})
        self.assertNotIn("→", out)
        self.assertIn("  gba/Game B (USA).gba", out)
        self.assertIn("would ask about deleting gba/Game A (Europe).gba", out)

    def test_same_content_under_a_new_name_is_a_rename(self):
        out = self.replace({"Game B (USA).gba": b"A" * 4096}, {"Game A (Europe).gba": b"A" * 4096})
        self.assertIn("Game A (Europe).gba → Game B (USA).gba", out)
        self.assertNotIn("would ask about deleting", out)

    def test_dry_run_prints_every_rename(self):
        n = 12
        out = self.replace({f"new{i:02}.gba": bytes([i]) * 10 for i in range(n)}, {f"old{i:02}.gba": bytes([i]) * 10 for i in range(n)})
        for i in range(n):
            self.assertIn(f"old{i:02}.gba → new{i:02}.gba", out)
        self.assertNotIn("more", out)


class BucketReplaceSamplesTest(unittest.TestCase):
    """upload --replace on a bucket: a big object with no MD5 is compared on samples, and the rename says so."""

    def test_big_multipart_object_is_sampled_and_marked(self):
        size = 9 << 20
        stored = bytearray(b"A" * size)
        stored[(1 << 20) + 100] = ord("B")  # between the samples: not seen
        reads = []

        def read_range(key, start, end):
            reads.append(end - start)
            return bytes(stored[start:end])

        with tempfile.TemporaryDirectory() as root, contextlib.ExitStack() as st:
            with open(os.path.join(root, "new.iso"), "wb") as f:
                f.write(b"A" * size)
            for name in ("ROOT", "_mirror_root"):
                st.enter_context(mock.patch.object(runtime, name, None))
            st.enter_context(mock.patch.object(s3, "read_range", read_range))
            st.enter_context(mock.patch.object(inventory, "etags", lambda prefix: {"old.iso": (size, '"abc-2"')}))
            out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            upload.replace_command(argparse.Namespace(dry_run=True), root, SYSTEMS[0])
        self.assertIn("old.iso → new.iso", out.getvalue())
        self.assertIn("matched on samples", out.getvalue())
        self.assertLess(sum(reads), size)


class CopyInterruptTest(unittest.TestCase):
    """Ctrl-C during a copy into a storage folder stops the queued copies, as downloads do."""

    def run_interrupted(self, draws_that_interrupt):
        release, started, draws, exits = threading.Event(), [], [], []

        def write_file(key, write):
            started.append(key)
            release.wait(5)

        def draw(self_, done):
            draws.append(done)
            if len(draws) in draws_that_interrupt:
                raise KeyboardInterrupt
            if len(draws) >= 4:
                release.set()

        def hard_exit():
            release.set()
            exits.append(1)
            raise SystemExit(130)

        todo = [(f"gba/{i}.gba", f"/x/{i}.gba", 100 - i) for i in range(20)]
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(s3, "write_file", write_file))
            st.enter_context(mock.patch.object(ui.ProgressBar, "draw", draw))
            st.enter_context(mock.patch.object(downloads, "hard_exit", hard_exit))
            st.enter_context(mock.patch.object(runtime, "ROOT", "/storage"))
            st.enter_context(mock.patch.object(runtime, "WORKERS", 2))
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
            out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaises((KeyboardInterrupt, SystemExit)) as cm:
                upload.run_copies(todo)
        return cm.exception, started, exits, out.getvalue()

    def test_queued_copies_do_not_run(self):
        error, started, exits, out = self.run_interrupted({1})
        self.assertIsInstance(error, KeyboardInterrupt)
        self.assertEqual(sorted(started), ["gba/0.gba", "gba/1.gba"])
        self.assertIn("finishing 2", out)
        self.assertEqual(exits, [])

    def test_second_ctrl_c_aborts_now(self):
        error, _, exits, _ = self.run_interrupted({1, 2})
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(exits, [1])


class MoveInterruptTest(unittest.TestCase):
    """Ctrl-C during s3.move_keys stops the queued moves; the moves that finished are recorded in the cache."""

    def test_queued_moves_do_not_run_and_finished_ones_are_recorded(self):
        release, started, recorded = threading.Event(), [], []

        def replace(src, dst):
            started.append(os.path.basename(src))
            if not src.endswith("/0.gba"):  # only the first move finishes before the interrupt
                release.wait(5)

        printed = []

        def fake_print(*a, **k):
            printed.append(" ".join(map(str, a)))
            if len(printed) == 2:  # the first move's line
                raise KeyboardInterrupt
            if len(printed) == 3:  # the in-flight line
                release.set()

        moves = [(f"gba/{i}.gba", f"gba/n{i}.gba") for i in range(20)]
        with tempfile.TemporaryDirectory() as root, contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(runtime, "ROOT", root))
            st.enter_context(mock.patch.object(runtime, "WORKERS", 2))
            st.enter_context(mock.patch.object(s3.os, "replace", replace))
            st.enter_context(mock.patch.object(s3, "print", fake_print, create=True))
            st.enter_context(mock.patch.object(inventory, "moved", lambda old, new: recorded.append(old)))
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
            with self.assertRaises(KeyboardInterrupt):
                s3.move_keys(moves)
        self.assertLessEqual(len(started), 3)
        self.assertEqual(sorted(recorded), sorted(f"gba/{n}" for n in started))
        self.assertTrue(any("finishing" in p for p in printed))


class AbortKeepsCacheTest(StorageFolder):
    """A second Ctrl-C leaves at once, but the cache file still holds what finished before it."""

    def abort(self, run, release):
        def hard_exit():
            release.set()
            raise SystemExit(130)

        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(downloads, "hard_exit", hard_exit))
            st.enter_context(mock.patch.object(runtime, "WORKERS", 2))
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
            st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaises(SystemExit):
                run()
        inventory.reset()  # forget what is in memory: read the cache file again

    def test_copies_that_finished_are_saved(self):
        self.build()
        real_write, first_done, release, draws = s3.write_file, threading.Event(), threading.Event(), []

        def write_file(key, write):
            if key == "gba/big.gba":
                real_write(key, write)
                first_done.set()
            else:
                release.wait(5)

        def draw(self_, done):
            draws.append(done)
            if len(draws) <= 2:
                first_done.wait(5)
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as local:
            todo = []
            for name, size in (("big.gba", 9), ("b.gba", 2), ("c.gba", 1)):
                touch(local, name, size)
                todo.append((f"gba/{name}", os.path.join(local, name), size))
            with mock.patch.object(s3, "write_file", write_file), mock.patch.object(ui.ProgressBar, "draw", draw):
                self.abort(lambda: upload.run_copies(todo), release)
        self.assertEqual(inventory.files("gba/").get("gba/big.gba"), 9)

    def test_second_ctrl_c_during_moves_aborts_and_saves_finished_moves(self):
        self.build()
        real_replace, release, printed = os.replace, threading.Event(), []

        def replace(src, dst):  # the cache file is saved with os.replace too
            if src.endswith("b.zip"):
                release.wait(5)
            else:
                real_replace(src, dst)

        def fake_print(*a, **k):
            printed.append(" ".join(map(str, a)))
            if len(printed) == 2:  # the first move's line
                raise KeyboardInterrupt

        def sleep(s):
            raise KeyboardInterrupt  # ^C again while waiting for the move in flight

        with mock.patch.object(s3.os, "replace", replace), mock.patch.object(s3, "print", fake_print, create=True), \
                mock.patch.object(s3.time, "sleep", sleep):
            self.abort(lambda: s3.move_keys([("gba/a.zip", "gba/a2.zip"), ("gba/b.zip", "gba/b2.zip")]), release)
        self.assertTrue(any("Aborted" in p for p in printed))
        files = inventory.files("gba/")
        self.assertIn("gba/a2.zip", files)
        self.assertNotIn("gba/a.zip", files)


class UploadWorkersTest(unittest.TestCase):
    def test_scales_with_cores_and_is_capped(self):
        for cores, expected in ((2, 8), (10, 16), (64, 16), (None, 16)):
            with mock.patch.object(os, "cpu_count", return_value=cores):
                self.assertEqual(upload.upload_workers(), expected)


class FakeManager:
    """Stands in for the s3transfer manager: runs each upload at once and reports it through its subscribers."""
    def __init__(self, fail=()):
        self.fail, self.uploads = fail, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def upload(self, path, bucket, key, extra_args, subscribers):
        self.uploads.append((path, bucket, key, extra_args))
        future = mock.Mock()
        future.result.side_effect = RuntimeError("denied") if key in self.fail else None
        for sub in subscribers:
            sub.on_done(future)


class RunRomUploadsTest(unittest.TestCase):
    def run_uploads(self, todo, manager):
        with mock.patch.object(runtime, "BUCKET", "test-bucket"), \
                mock.patch("boto3.s3.transfer.create_transfer_manager", return_value=manager) as create, \
                mock.patch.object(s3, "s3_client") as client, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            failed = upload.run_uploads(todo)
        return failed, out.getvalue(), create, client

    def test_biggest_first_with_content_type_on_the_write_profile(self):
        manager = FakeManager()
        todo = [("gba/a.zip", "/x/a.zip", 1), ("gba/b.bin", "/x/b.bin", 99)]
        failed, out, create, client = self.run_uploads(todo, manager)
        self.assertEqual(failed, 0)
        self.assertEqual(manager.uploads, [
            ("/x/b.bin", "test-bucket", "gba/b.bin", {"ContentType": "application/octet-stream"}),
            ("/x/a.zip", "test-bucket", "gba/a.zip", {"ContentType": "application/zip"}),
        ])
        client.assert_called_once_with(runtime.WRITE_PROFILE, connections=upload.upload_workers())
        client.return_value.head_bucket.assert_called_once_with(Bucket="test-bucket")
        config = create.call_args[0][1]
        self.assertEqual(config.max_request_concurrency, upload.upload_workers())
        self.assertEqual(config.multipart_threshold, upload.UPLOAD_MULTIPART_AT)
        self.assertEqual(config.multipart_chunksize, upload.UPLOAD_PART)
        self.assertIn("[2/2]", out)

    def test_failures_are_counted_and_shown(self):
        todo = [("gba/a.zip", "/x/a.zip", 1), ("gba/b.zip", "/x/b.zip", 2)]
        failed, out, _, _ = self.run_uploads(todo, FakeManager(fail={"gba/a.zip"}))
        self.assertEqual(failed, 1)
        self.assertIn("denied", out)

    def test_derived_jobs_upload_the_shrunk_copy(self):
        def shrink(src, dst, box):
            with open(dst, "wb") as f:
                f.write(b"small")

        manager = FakeManager()
        todo = [("scrapes/onion/a.png", "/x/a.png", 500, (250, 360)), ("scrapes/b.png", "/x/b.png", 1)]
        with mock.patch.object(scrape_plan, "shrink_png", side_effect=shrink) as shrunk:
            failed, _, _, _ = self.run_uploads(todo, manager)
        self.assertEqual(failed, 0)
        shrunk.assert_called_once()
        self.assertEqual(shrunk.call_args[0][0], "/x/a.png")
        self.assertEqual(shrunk.call_args[0][2], (250, 360))
        self.assertEqual(sorted(u[2] for u in manager.uploads), ["scrapes/b.png", "scrapes/onion/a.png"])
        art = next(u for u in manager.uploads if u[2] == "scrapes/onion/a.png")
        self.assertNotEqual(art[0], "/x/a.png")
        self.assertEqual(art[3], {"ContentType": "image/png"})

    def test_failed_shrink_is_reported_not_uploaded(self):
        manager = FakeManager()
        with mock.patch.object(scrape_plan, "shrink_png", side_effect=RuntimeError("bad png")):
            failed, out, _, _ = self.run_uploads([("scrapes/onion/a.png", "/x/a.png", 5, (250, 360))], manager)
        self.assertEqual(failed, 1)
        self.assertIn("bad png", out)
        self.assertEqual(manager.uploads, [])


class S3ClientPoolTest(unittest.TestCase):
    def test_pool_size_gets_its_own_client(self):
        with mock.patch.dict(s3._s3, {}, clear=True), mock.patch("boto3.Session") as session:
            session.return_value.client.side_effect = lambda *a, **k: mock.Mock(pool=k["config"].max_pool_connections)
            small, big = s3.s3_client("p"), s3.s3_client("p", connections=40)
            self.assertIs(small, s3.s3_client("p"))
            self.assertIs(big, s3.s3_client("p", connections=40))
        self.assertEqual((small.pool, big.pool), (runtime.WORKERS, 40))

    def test_custom_endpoint_uses_path_style(self):
        with mock.patch.dict(s3._s3, {}, clear=True), mock.patch("boto3.Session") as session, \
                mock.patch.object(runtime, "ENDPOINT", "http://minio:9000"):
            s3.s3_client("p")
        kwargs = session.return_value.client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], "http://minio:9000")
        self.assertEqual(kwargs["config"].s3, {"addressing_style": "path"})

    def test_bucket_and_endpoint_env_override_settings(self):
        settings = {"bucket": "b", "endpoint": "http://saved"}
        env = {"ROMS_BUCKET": "eb", "ROMS_ENDPOINT": "http://env"}
        with mock.patch.object(usersettings, "load_settings", return_value=settings), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(runtime, "BUCKET"), mock.patch.object(runtime, "ENDPOINT"):
            usersettings.ensure_bucket()
            self.assertEqual((runtime.BUCKET, runtime.ENDPOINT), ("eb", "http://env"))

    def test_profiles_from_settings_with_env_override(self):
        settings = {"bucket": "b", "profile": "r", "write_profile": "w"}
        with mock.patch.object(usersettings, "load_settings", return_value=settings), \
                mock.patch.dict(os.environ, {"ROMS_PROFILE": "env"}), \
                mock.patch.object(runtime, "PROFILE"), mock.patch.object(runtime, "WRITE_PROFILE"):
            usersettings.ensure_bucket()
            self.assertEqual((runtime.PROFILE, runtime.WRITE_PROFILE), ("env", "w"))


if __name__ == "__main__":
    unittest.main()
