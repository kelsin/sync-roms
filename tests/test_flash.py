import gzip
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import flash  # noqa: E402

KEYS = ["os/knulli-h700-rg35xx-h-scarab-20260511.img.gz", "os/knulli-h700-rg34xx-sp-scarab-20260511.img.gz",
        "os/knulli-h700-rg35xx-h-gladiator-20250101.img.gz", "os/knulli-rk3568-miyoo-flip-scarab-20260510.img.gz"]


class Flash(unittest.TestCase):
    def test_images_keeps_only_knulli_gz(self):
        listing = {k: 1 for k in KEYS} | {"os/Onion-v4.3.1-1.zip": 1, "os/esde/knulli-x-y-z-20260101.img.gz": 1,
                                          "os/Zero40_32G.img.xz": 1}
        self.assertEqual(sorted(flash.images(listing)), sorted(KEYS))

    def test_sort_puts_matches_first_newest_first(self):
        got = flash.sort_images(KEYS, "anbernic-rg35xxh")
        self.assertEqual(got[:2], [(KEYS[0], True), (KEYS[2], True)])
        self.assertTrue(all(not m for _, m in got[2:]))

    def test_sort_matches_miyoo_flip(self):
        self.assertEqual(flash.sort_images(KEYS, "miyoo-flip")[0], (KEYS[3], True))

    def test_sort_matches_sp(self):
        self.assertEqual(flash.sort_images(KEYS, "anbernic-rg34xx-sp")[0], (KEYS[1], True))

    def test_no_match_still_lists_all(self):
        self.assertEqual(len(flash.sort_images(KEYS, "anbernic-rg28xx")), 4)

    def test_knulli_devices(self):
        devs = [{"id": "a", "firmwares": ["esde"]}, {"id": "b", "firmwares": ["knulli"]},
                {"id": "c", "firmwares": ["onion", "knulli"]}]
        self.assertEqual([d["id"] for d in flash.knulli_devices(devs)], ["b", "c"])

    def test_parse_disks_skips_excluded_and_reads_info(self):
        infos = {"disk4": {"TotalSize": 64_000_000_000, "MediaName": "SD Card Reader"},
                 "disk5": {"Size": 32_000_000_000, "IORegistryEntryName": "Generic"}, "disk6": {}}
        got = flash.parse_disks({"WholeDisks": ["disk4", "disk5", "disk6"]}, infos.__getitem__, {"disk6"})
        self.assertEqual(got, [flash.Disk("disk4", 64_000_000_000, "SD Card Reader"),
                               flash.Disk("disk5", 32_000_000_000, "Generic")])

    def test_parse_disks_empty(self):
        self.assertEqual(flash.parse_disks({}, lambda d: {}, set()), [])

    def test_whole_disks_plain(self):
        self.assertEqual(flash.whole_disks({"ParentWholeDisk": "disk2"}), {"disk2"})

    def test_whole_disks_apfs_includes_physical_disk(self):
        info = {"ParentWholeDisk": "disk5", "APFSPhysicalStores": [{"APFSPhysicalStore": "disk4s2"}]}
        self.assertEqual(flash.whole_disks(info), {"disk5", "disk4"})

    def test_whole_disks_empty(self):
        self.assertEqual(flash.whole_disks({}), set())


class WriteVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = os.path.join(self.tmp.name, "target")
        self.data = os.urandom(5 * 1024 * 1024 + 123)
        self.gz = os.path.join(self.tmp.name, "img.gz")
        with gzip.open(self.gz, "wb") as f:
            f.write(self.data)
        for patcher in (mock.patch.object(flash, "DD", ["dd"]), mock.patch.object(flash, "raw", lambda d: self.target)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_write_then_verify_round_trip(self):
        size, digest = flash.write_image(self.gz, "disk9")
        self.assertEqual(size, len(self.data))
        self.assertEqual(digest, hashlib.sha256(self.data).hexdigest())
        self.assertTrue(flash.verify("disk9", size, digest))

    def test_verify_ignores_bytes_past_image(self):
        size, digest = flash.write_image(self.gz, "disk9")
        with open(self.target, "ab") as f:
            f.write(b"x" * 1000)
        self.assertTrue(flash.verify("disk9", size, digest))

    def test_verify_detects_corruption(self):
        size, digest = flash.write_image(self.gz, "disk9")
        pos = 3 * 1024 * 1024
        with open(self.target, "r+b") as f:
            f.seek(pos)
            byte = f.read(1)[0]
            f.seek(pos)
            f.write(bytes([byte ^ 0xFF]))
        self.assertFalse(flash.verify("disk9", size, digest))

    def test_verify_short_read_is_false(self):
        size, digest = flash.write_image(self.gz, "disk9")
        os.truncate(self.target, size - 10)
        self.assertFalse(flash.verify("disk9", size, digest))

    def test_dd_failure_raises(self):
        with mock.patch.object(flash, "raw", lambda d: "/nonexistent-dir/x"):
            with self.assertRaises(flash.FlashError):
                flash.write_image(self.gz, "disk9")

    def test_progress_reaches_one(self):
        seen = []
        flash.write_image(self.gz, "disk9", seen.append)
        self.assertAlmostEqual(seen[-1], 1.0)


if __name__ == "__main__":
    unittest.main()
