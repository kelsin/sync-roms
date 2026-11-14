import contextlib
import io
import os
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from unittest import mock

import boto3
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError
from botocore.stub import Stubber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import inventory, runtime, s3, scrape_files, store  # noqa: E402

BUCKET = "test-bucket"


def fake_client():
    """An S3 client with dummy credentials; every call goes through a Stubber, never the network."""
    return boto3.Session(aws_access_key_id="x", aws_secret_access_key="x",
                         region_name="us-east-1").client("s3")


class S3Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.read, cls.write = fake_client(), fake_client()  # building a client is slow, so once; each test gets fresh Stubbers

    def setUp(self):
        self.rs, self.ws = Stubber(self.read), Stubber(self.write)
        self.rs.activate()
        self.ws.activate()
        patches = [mock.patch.object(runtime, "BUCKET", BUCKET), mock.patch.object(runtime, "_mirror_root", None),
                   mock.patch.dict(s3._s3, {runtime.PROFILE: self.read, runtime.WRITE_PROFILE: self.write}, clear=True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.rs.deactivate()
        self.ws.deactivate()
        self.rs.assert_no_pending_responses()
        self.ws.assert_no_pending_responses()

    def test_list_sizes_paginates(self):
        self.rs.add_response("list_objects_v2",
                             {"Contents": [{"Key": "gba/a.zip", "Size": 1}, {"Key": "gba/", "Size": 0}],
                              "IsTruncated": True, "NextContinuationToken": "t"},
                             {"Bucket": BUCKET, "Prefix": "gba/"})
        self.rs.add_response("list_objects_v2", {"Contents": [{"Key": "gba/b.zip", "Size": 2}], "IsTruncated": False},
                             {"Bucket": BUCKET, "Prefix": "gba/", "ContinuationToken": "t"})
        self.assertEqual(s3.list_sizes("gba/"), {"gba/a.zip": 1, "gba/": 0, "gba/b.zip": 2})

    def test_list_sizes_empty(self):
        self.rs.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": BUCKET, "Prefix": "none/"})
        self.assertEqual(s3.list_sizes("none/"), {})

    def test_list_folders(self):
        self.rs.add_response("list_objects_v2", {"CommonPrefixes": [{"Prefix": "BIOS/"}, {"Prefix": "gba/"}],
                                                 "Contents": [{"Key": "readme.txt", "Size": 1}], "IsTruncated": False},
                             {"Bucket": BUCKET, "Delimiter": "/"})
        self.assertEqual(s3.list_folders(), {"BIOS", "gba"})

    def test_get_text(self):
        self.rs.add_response("get_object", {"Body": io.BytesIO("héllo".encode("utf-8"))},
                             {"Bucket": BUCKET, "Key": "scrapes/x/metadata.json"})
        self.assertEqual(s3.get_text("scrapes/x/metadata.json"), "héllo")

    def test_get_text_missing_key_raises_client_error(self):
        self.rs.add_client_error("get_object", "NoSuchKey", http_status_code=404)
        with self.assertRaises(ClientError):
            s3.get_text("nope")

    def test_put_text_uses_write_profile(self):
        self.ws.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "k", "Body": "é".encode("utf-8")})
        s3.put_text("k", "é")

    def test_download(self):
        client = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(s3._s3, {runtime.PROFILE: client}):
            path = os.path.join(tmp, "sub", "a.zip")
            s3.download(("gba/a.zip", path, 1))
            self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertEqual(client.download_fileobj.call_args.args[:2], (BUCKET, "gba/a.zip"))
        kwargs = client.download_fileobj.call_args.kwargs
        self.assertIsNone(kwargs["Callback"])
        self.assertEqual(kwargs["Config"].max_concurrency, s3.DOWNLOAD_PARTS)

    def test_delete_keys_batches_and_returns_errors(self):
        keys = [f"k{i}" for i in range(1001)]
        err = {"Key": "k1000", "Code": "AccessDenied", "Message": "no"}
        self.ws.add_response("delete_objects", {},
                             {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": k} for k in keys[:1000]], "Quiet": True}})
        self.ws.add_response("delete_objects", {"Errors": [err]},
                             {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": "k1000"}], "Quiet": True}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(s3.delete_keys(keys), [err])
        self.assertIn("deleted 1000/1001", out.getvalue())
        self.assertIn("deleted 1001/1001", out.getvalue())

    def test_clean_scrapes_client_error_exits(self):
        self.rs.add_client_error("list_objects_v2", "AccessDenied", "Access Denied")
        with mock.patch.object(store, "load_manifest", return_value={"systems": []}), \
                mock.patch.object(scrape_files, "bucket_roms", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                scrape_files.clean_scrapes(mock.Mock(dry_run=True))
        self.assertEqual(cm.exception.code, 3)


class ProfileTest(unittest.TestCase):
    def test_missing_profile_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            open(empty, "w").close()
            env = {"HOME": tmp, "AWS_CONFIG_FILE": empty, "AWS_SHARED_CREDENTIALS_FILE": empty}
            with mock.patch.dict(os.environ, env), mock.patch.dict(s3._s3, {}, clear=True):
                with self.assertRaises(SystemExit) as cm:
                    s3.s3_client("no-such-profile")
        self.assertEqual(cm.exception.code, 3)


class MirrorListTest(unittest.TestCase):
    def test_list_sizes_reads_the_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "gba"))
            with open(os.path.join(tmp, "gba", "a.zip"), "w") as f:
                f.write("xyz")
            with mock.patch.object(runtime, "_mirror_root", tmp):
                self.assertEqual(s3.list_sizes("gba/"), {"gba/a.zip": 3})


class FolderListTest(unittest.TestCase):
    def test_list_folders_reads_the_storage_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "gba"))
            open(os.path.join(tmp, "notes.txt"), "w").close()
            with mock.patch.object(runtime, "ROOT", tmp):
                self.assertEqual(s3.list_folders(), {"gba"})


class CopyFileTest(unittest.TestCase):
    def test_copies_and_reports_every_byte(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst, seen = os.path.join(d, "a"), os.path.join(d, "b"), []
            with open(src, "wb") as f:
                f.write(b"x" * (2 * 1024 * 1024 + 5))
            s3.copy_file(src, dst, seen.append)
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), b"x" * (2 * 1024 * 1024 + 5))
            self.assertEqual(sum(seen), 2 * 1024 * 1024 + 5)
            self.assertEqual(len(seen), 3)


class DownloadTest(unittest.TestCase):
    def test_reports_written_bytes_and_replaces_part_file(self):
        with tempfile.TemporaryDirectory() as d:
            path, wrote = os.path.join(d, "g.zip"), []

            def fake_download(bucket, key, fileobj, Callback=None, Config=None):
                fileobj.seek(0)
                fileobj.write(b"abc")
                Callback(3)

            client = mock.Mock(download_fileobj=fake_download)
            with mock.patch.object(s3, "s3_client", return_value=client), mock.patch.object(s3, "read_root", return_value=None):
                s3.download(("gba/g.zip", path, 3), lambda n: None, wrote.append)
            self.assertEqual(wrote, [3])
            self.assertEqual(open(path, "rb").read(), b"abc")
            self.assertFalse(os.path.exists(path + ".part"))

    def test_failed_download_leaves_no_part_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.zip")

            def fail(bucket, key, fileobj, Callback=None, Config=None):
                fileobj.write(b"ab")
                raise OSError("boom")

            with mock.patch.object(s3, "s3_client", return_value=mock.Mock(download_fileobj=fail)), \
                    mock.patch.object(s3, "read_root", return_value=None), self.assertRaises(OSError):
                s3.download(("gba/g.zip", path, 3))
            self.assertEqual(os.listdir(d), [])


class FakeObject:
    """One bucket object served through a client's events, answering each request by what it asks (so ranged GETs may
    come in any order): HEAD, GET with Range and If-Match (412 when the ETag isn't the object's), 404 when body is None.
    calls records (operation, If-Match, Range). After changes GETs, the object becomes after (body, ETag); a 412 is held
    for wait seconds, so the GETs in flight finish first."""
    def __init__(self, client, body, etag, changes=None, after=None, wait=0):
        self.body, self.etag, self.changes, self.after, self.wait, self.calls = body, etag, changes, after, wait, []
        self.lock = threading.Lock()
        client.meta.events.register_first("before-call.s3", self.serve, unique_id="fake-object")

    def serve(self, model, params, **kwargs):
        headers, meta = params["headers"], {"HTTPStatusCode": 200, "HTTPHeaders": {}}
        with self.lock:
            self.calls.append((model.name, headers.get("If-Match"), headers.get("Range")))
            body, etag = self.body, self.etag
            if model.name == "GetObject" and self.changes is not None:
                self.changes -= 1
                if self.changes == 0:
                    self.body, self.etag = self.after
        if body is None:
            return AWSResponse(None, 404, {}, None), {"Error": {"Code": "NoSuchKey", "Message": "gone"}, "ResponseMetadata": meta}
        if headers.get("If-Match") not in (None, etag):
            time.sleep(self.wait)
            return AWSResponse(None, 412, {}, None), {"Error": {"Code": "PreconditionFailed", "Message": "no"}, "ResponseMetadata": meta}
        if model.name == "HeadObject":
            return AWSResponse(None, 200, {}, None), {"ContentLength": len(body), "ETag": etag, "ResponseMetadata": meta}
        start, end = 0, len(body) - 1
        if headers.get("Range"):
            a, b = headers["Range"][len("bytes="):].split("-")
            start, end = int(a), min(int(b) if b else end, end)
        out = {"Body": io.BytesIO(body[start:end + 1]), "ContentLength": end + 1 - start, "ETag": etag, "ResponseMetadata": meta}
        if headers.get("Range"):
            out["ContentRange"] = f"bytes {start}-{end}/{len(body)}"
        return AWSResponse(None, 200, {}, None), out


class CachedDownloadTest(unittest.TestCase):
    """A bucket download given the object's size and ETag from the cache skips the HEAD request."""
    BIG = 9 * 1024 * 1024  # over s3transfer's multipart threshold, so the GETs are ranged and carry If-Match

    @classmethod
    def setUpClass(cls):
        cls.client = fake_client()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(self.client.meta.events.unregister, "before-call.s3", unique_id="fake-object")
        patches = [mock.patch.object(runtime, "BUCKET", BUCKET), mock.patch.object(runtime, "ROOT", None),
                   mock.patch.object(runtime, "_mirror_root", None),
                   mock.patch.dict(s3._s3, {runtime.PROFILE: self.client}, clear=True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def download(self, files, etags):
        """Download gba/a.zip with this cache; returns (file contents, bytes received, bytes written)."""
        path, got, wrote = os.path.join(self.tmp, "a.zip"), [], []
        tree = inventory.Tree(f"s3://{BUCKET}", 0, files, etags)
        with mock.patch.object(inventory, "current", return_value=tree):
            s3.download(("gba/a.zip", path, None), got.append, wrote.append)
        with open(path, "rb") as f:
            data = f.read()
        self.assertEqual(os.listdir(self.tmp), ["a.zip"])
        return data, sum(got), sum(wrote)

    def test_cached_size_and_etag_skip_the_head(self):
        fake = FakeObject(self.client, b"abc", '"e1"')
        self.assertEqual(self.download({"gba/a.zip": 3}, {"gba/a.zip": '"e1"'}), (b"abc", 3, 3))
        self.assertEqual(fake.calls, [("GetObject", None, None)])

    def test_multipart_object_gets_ranges_with_if_match_and_no_head(self):
        body = os.urandom(self.BIG)
        fake = FakeObject(self.client, body, '"e1-2"')
        self.assertEqual(self.download({"gba/a.zip": self.BIG}, {"gba/a.zip": '"e1-2"'}), (body, self.BIG, self.BIG))
        self.assertEqual(sorted(fake.calls), [("GetObject", '"e1-2"', "bytes=0-8388607"),
                                              ("GetObject", '"e1-2"', "bytes=8388608-")])

    def test_stale_etag_falls_back_to_a_head_once(self):
        fake = FakeObject(self.client, b"new", '"e2"')
        self.assertEqual(self.download({"gba/a.zip": self.BIG}, {"gba/a.zip": '"e1"'}), (b"new", 3, 3))
        self.assertEqual(fake.calls[0][:2], ("GetObject", '"e1"'))
        self.assertEqual(fake.calls[-2:], [("HeadObject", None, None), ("GetObject", None, None)])
        self.assertEqual([c for c in fake.calls[:-2] if c != ("GetObject", '"e1"', "bytes=0-8388607")
                          and c != ("GetObject", '"e1"', "bytes=8388608-")], [])

    def test_change_during_download_restarts_the_file_and_its_progress(self):
        old, new = os.urandom(self.BIG), b"short"
        fake = FakeObject(self.client, old, '"e1"', changes=1, after=(new, '"e2"'), wait=0.3)
        self.assertEqual(self.download({"gba/a.zip": self.BIG}, {"gba/a.zip": '"e1"'}), (new, len(new), len(new)))
        self.assertEqual([c[0] for c in fake.calls].count("HeadObject"), 1)

    def test_other_errors_do_not_fall_back(self):
        fake = FakeObject(self.client, None, '"e1"')
        with self.assertRaises(ClientError) as cm:
            self.download({"gba/a.zip": 3}, {"gba/a.zip": '"e1"'})
        self.assertIn("NoSuchKey", str(cm.exception))
        self.assertEqual(fake.calls, [("GetObject", None, None)])
        self.assertEqual(os.listdir(self.tmp), [])

    def test_no_cached_etag_downloads_as_before(self):
        fake = FakeObject(self.client, b"abc", '"e1"')
        self.assertEqual(self.download({"gba/a.zip": 3}, {}), (b"abc", 3, 3))
        self.assertEqual(fake.calls, [("HeadObject", None, None), ("GetObject", None, None)])

    def test_no_cache_downloads_as_before(self):
        fake = FakeObject(self.client, b"abc", '"e1"')
        path = os.path.join(self.tmp, "a.zip")
        with mock.patch.object(inventory, "current", return_value=None):
            s3.download(("gba/a.zip", path, None))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"abc")
        self.assertEqual(fake.calls, [("HeadObject", None, None), ("GetObject", None, None)])

    def test_storage_folder_download_never_uses_the_client(self):
        root = os.path.join(self.tmp, "roms")
        os.makedirs(os.path.join(root, "gba"))
        with open(os.path.join(root, "gba", "a.zip"), "wb") as f:
            f.write(b"abc")
        tree = inventory.Tree(root, 0, {"gba/a.zip": 3}, {"gba/a.zip": '"e1"'})
        path = os.path.join(self.tmp, "out", "a.zip")
        with mock.patch.object(runtime, "ROOT", root), mock.patch.object(inventory, "current", return_value=tree), \
                mock.patch.object(s3, "s3_client") as client:
            s3.download(("gba/a.zip", path, None))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"abc")
        client.assert_not_called()


class SafeJoinTest(unittest.TestCase):
    def test_rejects_keys_that_escape_the_base(self):
        for rel in ("../x", "a/../../x", "/etc/passwd", "", "a\\..\\..\\x"):
            with self.assertRaises(ValueError, msg=rel):
                s3.safe_join("/base", rel)

    def test_joins_normal_keys(self):
        self.assertEqual(s3.safe_join("/base", "a/b.zip"), os.path.join("/base", "a/b.zip"))


COMPOSED = unicodedata.normalize("NFC", "psvita/Vacances d'été.zip")
DECOMPOSED = unicodedata.normalize("NFD", COMPOSED)


@contextlib.contextmanager
def decomposing_share():
    """Act like an SMB share that stores accented names decomposed and only finds them by that exact spelling."""
    def exact(p):
        return p == unicodedata.normalize("NFD", p)

    real_lexists, real_replace = os.path.lexists, os.replace

    def lexists(p):
        return exact(p) and real_lexists(p)

    def replace(src, dst):
        if not exact(src):
            raise FileNotFoundError(src)
        real_replace(src, dst)

    with mock.patch.object(s3.os.path, "lexists", lexists), mock.patch.object(s3.os, "replace", replace):
        yield


def share_write(path, data):
    """Write a new file the way that share does: it stores the name decomposed whatever spelling it was given."""
    with open(unicodedata.normalize("NFD", path), "wb") as f:
        f.write(data)


class AccentedNameTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        os.mkdir(os.path.join(self.root, "psvita"))

    def test_safe_join_finds_the_decomposed_name_for_a_composed_key(self):
        open(os.path.join(self.root, DECOMPOSED), "wb").close()
        with decomposing_share():
            self.assertEqual(s3.safe_join(self.root, COMPOSED), os.path.join(self.root, DECOMPOSED))

    def test_write_file_replaces_the_part_file_the_share_renamed(self):
        with mock.patch.object(runtime, "ROOT", self.root), mock.patch("sync_roms.inventory.wrote") as wrote, \
                decomposing_share():
            s3.write_file(COMPOSED, lambda tmp: share_write(tmp, b"abc"))
        names = [unicodedata.normalize("NFC", n) for n in os.listdir(os.path.join(self.root, "psvita"))]
        self.assertEqual(names, [os.path.basename(COMPOSED)])
        wrote.assert_called_once_with(COMPOSED, 3)

    def test_failed_write_leaves_no_part_file(self):
        def fail(tmp):
            share_write(tmp, b"ab")
            raise OSError("boom")

        with mock.patch.object(runtime, "ROOT", self.root), decomposing_share(), self.assertRaises(OSError):
            s3.write_file(COMPOSED, fail)
        self.assertEqual(os.listdir(os.path.join(self.root, "psvita")), [])


if __name__ == "__main__":
    unittest.main()
