import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli  # noqa: E402

BUCKET = "test-bucket"


def fake_client():
    """An S3 client with dummy credentials; every call goes through a Stubber, never the network."""
    return boto3.Session(aws_access_key_id="x", aws_secret_access_key="x",
                         region_name="us-east-1").client("s3")


class S3Test(unittest.TestCase):
    def setUp(self):
        self.read, self.write = fake_client(), fake_client()
        self.rs, self.ws = Stubber(self.read), Stubber(self.write)
        self.rs.activate()
        self.ws.activate()
        patches = [mock.patch.object(cli, "BUCKET", BUCKET), mock.patch.object(cli, "_mirror_root", None),
                   mock.patch.dict(cli._s3, {cli.PROFILE: self.read, cli.WRITE_PROFILE: self.write}, clear=True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.rs.assert_no_pending_responses()
        self.ws.assert_no_pending_responses()

    def test_list_sizes_paginates(self):
        self.rs.add_response("list_objects_v2",
                             {"Contents": [{"Key": "gba/a.zip", "Size": 1}, {"Key": "gba/", "Size": 0}],
                              "IsTruncated": True, "NextContinuationToken": "t"},
                             {"Bucket": BUCKET, "Prefix": "gba/"})
        self.rs.add_response("list_objects_v2", {"Contents": [{"Key": "gba/b.zip", "Size": 2}], "IsTruncated": False},
                             {"Bucket": BUCKET, "Prefix": "gba/", "ContinuationToken": "t"})
        self.assertEqual(cli.list_sizes("gba/"), {"gba/a.zip": 1, "gba/": 0, "gba/b.zip": 2})

    def test_list_sizes_empty(self):
        self.rs.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": BUCKET, "Prefix": "none/"})
        self.assertEqual(cli.list_sizes("none/"), {})

    def test_get_text(self):
        self.rs.add_response("get_object", {"Body": io.BytesIO("héllo".encode("utf-8"))},
                             {"Bucket": BUCKET, "Key": "scrapes/x/metadata.json"})
        self.assertEqual(cli.get_text("scrapes/x/metadata.json"), "héllo")

    def test_get_text_missing_key_raises_client_error(self):
        self.rs.add_client_error("get_object", "NoSuchKey", http_status_code=404)
        with self.assertRaises(ClientError):
            cli.get_text("nope")

    def test_put_text_uses_write_profile(self):
        self.ws.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "k", "Body": "é".encode("utf-8")})
        cli.put_text("k", "é")

    def test_download(self):
        client = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(cli._s3, {cli.PROFILE: client}):
            path = os.path.join(tmp, "sub", "a.zip")
            cli.download(("gba/a.zip", path, 1))
            self.assertTrue(os.path.isdir(os.path.dirname(path)))
        client.download_file.assert_called_once_with(BUCKET, "gba/a.zip", path)

    def test_delete_keys_batches_and_returns_errors(self):
        keys = [f"k{i}" for i in range(1001)]
        err = {"Key": "k1000", "Code": "AccessDenied", "Message": "no"}
        self.ws.add_response("delete_objects", {},
                             {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": k} for k in keys[:1000]], "Quiet": True}})
        self.ws.add_response("delete_objects", {"Errors": [err]},
                             {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": "k1000"}], "Quiet": True}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.delete_keys(keys), [err])
        self.assertIn("deleted 1000/1001", out.getvalue())
        self.assertIn("deleted 1001/1001", out.getvalue())

    def test_clean_scrapes_client_error_exits(self):
        self.rs.add_client_error("list_objects_v2", "AccessDenied", "Access Denied")
        with mock.patch.object(cli, "load_manifest", return_value={"systems": []}), \
                mock.patch.object(cli, "bucket_roms", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.clean_scrapes(mock.Mock(dry_run=True))
        self.assertIn("AccessDenied", str(cm.exception.code))


class ProfileTest(unittest.TestCase):
    def test_missing_profile_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            open(empty, "w").close()
            env = {"HOME": tmp, "AWS_CONFIG_FILE": empty, "AWS_SHARED_CREDENTIALS_FILE": empty}
            with mock.patch.dict(os.environ, env), mock.patch.dict(cli._s3, {}, clear=True):
                with self.assertRaises(SystemExit) as cm:
                    cli.s3_client("no-such-profile")
        self.assertIn("no-such-profile", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
