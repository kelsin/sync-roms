import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli  # noqa: E402

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
        i = cli.guess_system(SYSTEMS, folder)
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
            new, changed, same = cli.plan_rom_upload(root, "gba", existing)
        self.assertEqual(sorted((k, s) for k, _, s in new), [("gba/.hack.gba", 50), ("gba/Disc/d.chd", 40), ("gba/a.gba", 10)])
        self.assertEqual([(k, s) for k, _, s in changed], [("gba/c.gba", 30)])
        self.assertEqual([(k, s) for k, _, s in same], [("gba/b.gba", 20)])


class UploadWorkersTest(unittest.TestCase):
    def test_scales_with_cores_and_is_capped(self):
        for cores, expected in ((2, 8), (10, 40), (64, 64), (None, 16)):
            with mock.patch.object(cli.os, "cpu_count", return_value=cores):
                self.assertEqual(cli.upload_workers(), expected)


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
        with mock.patch.object(cli, "BUCKET", "test-bucket"), \
                mock.patch.object(cli, "create_transfer_manager", return_value=manager) as create, \
                mock.patch.object(cli, "s3_client") as client, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            failed = cli.run_uploads(todo)
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
        client.assert_called_once_with(cli.WRITE_PROFILE, connections=cli.upload_workers())
        config = create.call_args[0][1]
        self.assertEqual(config.max_request_concurrency, cli.upload_workers())
        self.assertEqual(config.multipart_threshold, cli.UPLOAD_MULTIPART_AT)
        self.assertEqual(config.multipart_chunksize, cli.UPLOAD_PART)
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
        with mock.patch.object(cli, "shrink_png", side_effect=shrink) as shrunk:
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
        with mock.patch.object(cli, "shrink_png", side_effect=RuntimeError("bad png")):
            failed, out, _, _ = self.run_uploads([("scrapes/onion/a.png", "/x/a.png", 5, (250, 360))], manager)
        self.assertEqual(failed, 1)
        self.assertIn("bad png", out)
        self.assertEqual(manager.uploads, [])


class S3ClientPoolTest(unittest.TestCase):
    def test_pool_size_gets_its_own_client(self):
        with mock.patch.dict(cli._s3, {}, clear=True), mock.patch.object(cli.boto3, "Session") as session:
            session.return_value.client.side_effect = lambda *a, **k: mock.Mock(pool=k["config"].max_pool_connections)
            small, big = cli.s3_client("p"), cli.s3_client("p", connections=40)
            self.assertIs(small, cli.s3_client("p"))
            self.assertIs(big, cli.s3_client("p", connections=40))
        self.assertEqual((small.pool, big.pool), (cli.WORKERS, 40))

    def test_custom_endpoint_uses_path_style(self):
        with mock.patch.dict(cli._s3, {}, clear=True), mock.patch.object(cli.boto3, "Session") as session, \
                mock.patch.object(cli, "ENDPOINT", "http://minio:9000"):
            cli.s3_client("p")
        kwargs = session.return_value.client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], "http://minio:9000")
        self.assertEqual(kwargs["config"].s3, {"addressing_style": "path"})

    def test_bucket_and_endpoint_env_override_settings(self):
        settings = {"bucket": "b", "endpoint": "http://saved"}
        env = {"ROMS_BUCKET": "eb", "ROMS_ENDPOINT": "http://env"}
        with mock.patch.object(cli, "load_settings", return_value=settings), \
                mock.patch.dict(cli.os.environ, env), \
                mock.patch.object(cli, "BUCKET"), mock.patch.object(cli, "ENDPOINT"):
            cli.ensure_bucket()
            self.assertEqual((cli.BUCKET, cli.ENDPOINT), ("eb", "http://env"))

    def test_profiles_from_settings_with_env_override(self):
        settings = {"bucket": "b", "profile": "r", "write_profile": "w"}
        with mock.patch.object(cli, "load_settings", return_value=settings), \
                mock.patch.dict(cli.os.environ, {"ROMS_PROFILE": "env"}), \
                mock.patch.object(cli, "PROFILE"), mock.patch.object(cli, "WRITE_PROFILE"):
            cli.ensure_bucket()
            self.assertEqual((cli.PROFILE, cli.WRITE_PROFILE), ("env", "w"))


if __name__ == "__main__":
    unittest.main()
