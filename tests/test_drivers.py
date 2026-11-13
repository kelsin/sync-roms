import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import drivers  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
