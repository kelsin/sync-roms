import contextlib
import io
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import drivers, github, runtime, s3, ui  # noqa: E402


def release(tag, *assets, **flags):
    return {"tag_name": tag, "assets": [{"name": a, "browser_download_url": f"https://x/{a}", "size": 1} for a in assets], **flags}


class PickRelease(unittest.TestCase):
    def test_pinned_picks_its_tag(self):
        driver = {"repo": "o/r", "asset": r"\.zip$", "tag": "v1"}
        tag, asset = drivers.pick_release(driver, [release("v2", "a.zip"), release("v1", "b.zip")])
        self.assertEqual((tag, asset["name"]), ("v1", "b.zip"))

    def test_latest_skips_releases_without_a_matching_asset(self):
        driver = {"repo": "o/r", "asset": r"^Turnip_v.*\.zip$"}
        tag, asset = drivers.pick_release(driver, [release("v840", "Qualcomm_840.zip"), release("v26", "Turnip_v26.zip")])
        self.assertEqual((tag, asset["name"]), ("v26", "Turnip_v26.zip"))

    def test_drafts_skipped_prereleases_used_only_when_all_are(self):
        driver = {"repo": "o/r", "asset": r"\.zip$"}
        mixed = [release("v3", "a.zip", draft=True), release("v2", "a.zip", prerelease=True), release("v1", "a.zip")]
        self.assertEqual(drivers.pick_release(driver, mixed)[0], "v1")
        pre = [release("v2", "a.zip", prerelease=True), release("v1", "a.zip", prerelease=True)]
        self.assertEqual(drivers.pick_release(driver, pre)[0], "v2")

    def test_two_matching_assets_raise(self):
        driver = {"repo": "o/r", "asset": "A8xx"}
        with self.assertRaisesRegex(drivers.NoAsset, "2 assets of o/r v1 match A8xx: T-A8xx.zip, T-A8xx-Linux.zip"):
            drivers.pick_release(driver, [release("v1", "T-A8xx.zip", "T-A8xx-Linux.zip")])

    def test_no_match_raises(self):
        with self.assertRaisesRegex(drivers.NoAsset, r"no release of o/r has an asset matching \^x\$"):
            drivers.pick_release({"repo": "o/r", "asset": "^x$"}, [release("v1", "a.zip")])


class Names(unittest.TestCase):
    def test_card_name(self):
        self.assertEqual(drivers.card_name("mrpurple", "vturnip_mrpurple_T30-toasted.adpkg"), "mrpurple-vturnip_mrpurple_T30-toasted.adpkg.zip")
        self.assertEqual(drivers.card_name("x", "v1/2 b"), "x-v1_2_b.zip")


class ForDevice(unittest.TestCase):
    def test_for_device(self):
        data = drivers.load()
        expected = [d for i in data["gpus"]["adreno-650"]["drivers"] for d in data["drivers"] if d["id"] == i]
        device = {"gpu": "adreno-650"}
        got = drivers.for_device(device, "esde")
        self.assertEqual(len(got), 4)
        self.assertEqual(got, expected)
        self.assertEqual(drivers.for_device(device, "knulli"), [])
        self.assertEqual(drivers.for_device({}, "esde"), [])
        self.assertEqual(drivers.for_device(None, "esde"), [])


def entry(i, **extra):
    return {"id": i, "name": f"Driver {i}", "repo": f"o/{i}", "asset": r"\.zip$", **extra}


class Refresh(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = os.path.join(tmp.name, "storage")
        self.mirror = os.path.join(tmp.name, "mirror")
        self.warned, self.calls, self.downloads, self.order = [], [], [], []
        self.real_put_file, self.real_put_text = s3.put_file, s3.put_text
        self.releases = {}  # repo -> release list or an exception
        for p in (mock.patch.object(runtime, "ROOT", self.storage), mock.patch.object(runtime, "_mirror_root", None),
                  mock.patch.object(ui, "warn", self.warned.append), mock.patch.object(github, "json", self.fake_json),
                  mock.patch.object(github, "get", self.fake_get), mock.patch.object(s3, "put_file", self.put_file),
                  mock.patch.object(s3, "put_text", self.put_text)):
            p.start()
            self.addCleanup(p.stop)
        self.body = b"PK\x05\x06" + b"\0" * 18  # an empty zip

    def fake_json(self, url):
        self.calls.append(url)
        repo = url.split("/repos/")[1].split("/releases")[0]
        got = self.releases[repo]
        if isinstance(got, Exception):
            raise got
        return got

    def fake_get(self, url, accept=None):
        self.downloads.append(url)
        return io.BytesIO(self.body)

    def put_file(self, key, path):
        self.order.append(key)
        return self.real_put_file(key, path)

    def put_text(self, key, text):
        self.order.append(key)
        return self.real_put_text(key, text)

    def store(self, i, tag, body=b"old"):
        os.makedirs(os.path.join(self.storage, "os/drivers"), exist_ok=True)
        with open(os.path.join(self.storage, f"os/drivers/{i}.zip"), "wb") as f:
            f.write(body)
        with open(os.path.join(self.storage, f"os/drivers/{i}.tag"), "w") as f:
            f.write(tag + "\n")

    def read(self, rel, root=None, mode="rb"):
        with open(os.path.join(root or self.storage, rel), mode) as f:
            return f.read()

    def run_refresh(self, entries, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            drivers.refresh(entries, dry_run)

    def test_new_tag_stores_zip_then_tag(self):
        self.store("a", "v1")
        self.releases["o/a"] = [release("v2", "a.zip")]
        self.run_refresh([entry("a")])
        self.assertEqual(self.read("os/drivers/a.zip"), self.body)
        self.assertEqual(self.read("os/drivers/a.tag", mode="r"), "v2\n")
        self.assertEqual(self.order, ["os/drivers/a.zip", "os/drivers/a.tag"])

    def test_same_tag_downloads_nothing(self):
        self.store("a", "v2")
        self.releases["o/a"] = [release("v2", "a.zip")]
        self.run_refresh([entry("a")])
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.read("os/drivers/a.zip"), b"old")

    def test_pinned_in_storage_makes_no_github_call(self):
        self.store("a", "v1")
        self.run_refresh([entry("a", tag="v1")])
        self.assertEqual(self.calls, [])

    def test_pinned_missing_fetches_its_release(self):
        self.releases["o/a"] = release("v1", "a.zip")
        self.run_refresh([entry("a", tag="v1")])
        self.assertTrue(self.calls[0].endswith("/releases/tags/v1"))
        self.assertEqual(self.read("os/drivers/a.tag", mode="r"), "v1\n")

    def test_not_a_zip_keeps_storage(self):
        self.store("a", "v1")
        self.releases["o/a"] = [release("v2", "a.zip")]
        self.body = b"<html>"
        self.run_refresh([entry("a")])
        self.assertEqual(self.read("os/drivers/a.zip"), b"old")
        self.assertEqual(self.read("os/drivers/a.tag", mode="r"), "v1\n")
        self.assertIn("Driver a", self.warned[0])

    def test_rate_limit_midway_keeps_earlier_updates(self):
        for i in "abc":
            self.releases[f"o/{i}"] = [release("v2", "x.zip")]
        self.releases["o/b"] = urllib.error.HTTPError("u", 403, "rate limited", {}, None)
        self.run_refresh([entry(i) for i in "abc"])
        self.assertEqual(self.read("os/drivers/a.tag", mode="r"), "v2\n")
        self.assertEqual(self.read("os/drivers/c.tag", mode="r"), "v2\n")
        self.assertFalse(os.path.exists(os.path.join(self.storage, "os/drivers/b.tag")))
        self.assertEqual(len(self.warned), 1)
        self.assertIn("Driver b", self.warned[0])

    def test_dry_run_writes_nothing(self):
        self.releases["o/a"] = [release("v2", "a.zip")]
        self.run_refresh([entry("a")], dry_run=True)
        self.assertEqual(self.downloads, [])
        self.assertFalse(os.path.exists(os.path.join(self.storage, "os")))

    def test_mirror_gets_the_new_zip(self):
        self.releases["o/a"] = [release("v2", "a.zip")]
        with mock.patch.object(runtime, "_mirror_root", self.mirror):
            self.run_refresh([entry("a")])
        self.assertEqual(self.read("os/drivers/a.zip", self.mirror), self.body)
        self.assertEqual(self.read("os/drivers/a.tag", self.mirror, "r"), "v2\n")

    def test_stored_tag(self):
        self.assertIsNone(drivers.stored_tag("a"))
        self.store("a", "v1")
        self.assertEqual(drivers.stored_tag("a"), "v1")

    def test_can_write(self):
        self.assertTrue(drivers.can_write())
        import botocore.exceptions
        with mock.patch.object(runtime, "ROOT", None), \
                mock.patch("boto3.Session", side_effect=botocore.exceptions.ProfileNotFound(profile="roms")):
            self.assertFalse(drivers.can_write())


if __name__ == "__main__":
    unittest.main()
