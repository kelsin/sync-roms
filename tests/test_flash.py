import contextlib
import gzip
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from test_scripting import Isolated  # noqa: E402
from sync_roms import flash, inventory, picker, store, ui, usersettings  # noqa: E402

KEYS = ["os/knulli/knulli-h700-rg35xx-h-scarab-20260511.img.gz", "os/knulli/knulli-h700-rg34xx-sp-scarab-20260511.img.gz",
        "os/knulli/knulli-h700-rg35xx-h-gladiator-20250101.img.gz", "os/knulli/knulli-rk3568-miyoo-flip-scarab-20260510.img.gz"]


class Flash(unittest.TestCase):
    def test_images_keeps_only_knulli_gz_and_baseos_zip(self):
        listing = {k: 1 for k in KEYS} | {"os/Onion-v4.3.1-1.zip": 1, "os/esde/knulli-x-y-z-20260101.img.gz": 1,
                                          "os/knulli-h700-old-scarab-20260101.img.gz": 1,
                                          "os/baseos/baseos-rg28xx-1.4.0.bosupd": 1,
                                          "os/baseos/baseos-rg28xx-1.4.0.img.zip": 1, "os/Zero40_32G.img.xz": 1}
        self.assertEqual(sorted(flash.images(listing)), sorted(KEYS + ["os/baseos/baseos-rg28xx-1.4.0.img.zip"]))

    def test_baseos_matches_and_sorts_newest_version_first(self):
        keys = ["os/baseos/baseos-rg35xxsp-1.4.0.img.zip", "os/baseos/baseos-rg35xxsp-1.10.0.img.zip",
                "os/baseos/baseos-rgsp-1.4.0.img.zip", KEYS[0]]
        got = flash.sort_images(keys, "anbernic-rg35xx-sp")
        self.assertEqual(got[:2], [(keys[1], True), (keys[0], True)])
        self.assertEqual(flash.sort_images(keys, "anbernic-rg-sp")[0], (keys[2], True))

    def test_flashable_devices_adds_baseos_matches(self):
        devs = [{"id": "anbernic-rg-sp", "firmwares": ["nextui"]}, {"id": "b", "firmwares": ["knulli"]},
                {"id": "anbernic-rg28xx", "firmwares": ["esde"]}]
        self.assertEqual([d["id"] for d in flash.flashable_devices(devs, ["os/baseos/baseos-rgsp-1.4.0.img.zip"])],
                         ["anbernic-rg-sp", "b"])

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

    def test_parse_disks_skips_excluded_and_reads_info(self):
        infos = {"disk4": {"TotalSize": 64_000_000_000, "MediaName": "SD Card Reader"},
                 "disk5": {"Size": 32_000_000_000, "IORegistryEntryName": "Generic"}, "disk6": {}}
        got = flash.parse_disks({"WholeDisks": ["disk4", "disk5", "disk6"]}, infos.__getitem__, {"disk6"})
        self.assertEqual(got, [flash.Disk("disk4", 64_000_000_000, "SD Card Reader"),
                               flash.Disk("disk5", 32_000_000_000, "Generic")])

    def test_parse_disks_reads_volume_names(self):
        listing = {"WholeDisks": ["disk4", "disk6"], "AllDisksAndPartitions": [
            {"DeviceIdentifier": "disk4", "Partitions": [{"VolumeName": "KNULLI"}, {}, {"VolumeName": "SHARE"}]},
            {"DeviceIdentifier": "disk6", "Partitions": [{"APFSVolumes": [{"VolumeName": "Backup"}]}]}]}
        got = flash.parse_disks(listing, lambda d: {"Size": 1, "MediaName": "SD Card Reader"}, set())
        self.assertEqual(got, [flash.Disk("disk4", 1, "SD Card Reader", ("KNULLI", "SHARE")),
                               flash.Disk("disk6", 1, "SD Card Reader", ("Backup",))])

    def test_parse_disks_empty(self):
        self.assertEqual(flash.parse_disks({}, lambda d: {}, set()), [])

    def test_whole_disks_plain(self):
        self.assertEqual(flash.whole_disks({"ParentWholeDisk": "disk2"}), {"disk2"})

    def test_whole_disks_apfs_includes_physical_disk(self):
        info = {"ParentWholeDisk": "disk5", "APFSPhysicalStores": [{"APFSPhysicalStore": "disk4s2"}]}
        self.assertEqual(flash.whole_disks(info), {"disk5", "disk4"})

    def test_whole_disks_empty(self):
        self.assertEqual(flash.whole_disks({}), set())


class Write(unittest.TestCase):
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

    def test_write_copies_image(self):
        size = flash.write_image(self.gz, "disk9")
        self.assertEqual(size, len(self.data))
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_write_copies_zipped_image(self):
        path = os.path.join(self.tmp.name, "img.img.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("baseos-x.img", self.data)
        seen = []
        self.assertEqual(flash.write_image(path, "disk9", seen.append), len(self.data))
        self.assertAlmostEqual(seen[-1], 1.0)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_zip_without_one_img_raises(self):
        path = os.path.join(self.tmp.name, "bad.img.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("readme.txt", "x")
        with self.assertRaises(flash.FlashError):
            flash.write_image(path, "disk9")

    def test_dd_failure_raises(self):
        with mock.patch.object(flash, "raw", lambda d: "/nonexistent-dir/x"):
            with self.assertRaises(flash.FlashError):
                flash.write_image(self.gz, "disk9")

    def test_dd_dying_mid_write_raises(self):
        with mock.patch.object(flash, "DD", ["sh", "-c", "head -c 1000 >/dev/null; exit 1", "dd"]):
            with self.assertRaises(flash.FlashError):
                flash.write_image(self.gz, "disk9")

    def test_bad_gzip_raises(self):
        with open(self.gz, "rb") as f:
            raw_bytes = f.read()
        with open(self.gz, "wb") as f:
            f.write(raw_bytes[:-8] + b"\xff" * 8)
        with self.assertRaises(flash.FlashError):
            flash.write_image(self.gz, "disk9")

    def test_progress_reaches_one(self):
        seen = []
        flash.write_image(self.gz, "disk9", seen.append)
        self.assertAlmostEqual(seen[-1], 1.0)


IMAGE = "os/knulli/knulli-h700-rg35xx-h-scarab-20260511.img.gz"
CARD = flash.Disk("disk4", 64_000_000_000, "SD")
SUDO = ["sudo", "-v"]


class Args:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run


class Run(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.put(IMAGE, gzip.compress(b"img"))
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.calls = []
        self.answer = "disk4"
        self.tmps = []
        real_mkdtemp = tempfile.mkdtemp

        def mkdtemp(**kw):
            path = real_mkdtemp(dir=self.tmp.name, **kw)
            self.tmps.append(path)
            return path

        def run(cmd, **kw):
            self.calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        def write(gz, disk, progress=None):
            self.calls.append("<write>")
            return 3

        self.filter_list = mock.Mock(return_value=0)
        self.write_image = mock.Mock(side_effect=write)
        self.external_disks = mock.Mock(return_value=[CARD])
        for p in (mock.patch.object(flash, "_run", side_effect=run),
                  mock.patch.object(picker, "filter_list", self.filter_list),
                  mock.patch.object(ui, "ask", lambda prompt: self.answer),
                  mock.patch.object(flash, "external_disks", self.external_disks),
                  mock.patch.object(flash, "disks_of", return_value={"disk0"}),
                  mock.patch.object(flash.sys, "platform", "darwin"),
                  mock.patch.object(usersettings, "ensure_bucket"),
                  mock.patch.object(flash, "write_image", self.write_image),
                  mock.patch.object(flash.tempfile, "mkdtemp", mkdtemp),
                  mock.patch.object(store, "repo_json", return_value=[
                      {"id": "anbernic-rg35xxh", "name": "Anbernic RG35XX H", "firmwares": ["knulli"]}])):
            p.start()
            self.addCleanup(p.stop)

    def flash(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = flash.run(Args(dry_run))
        self.out = out.getvalue()
        return code

    def steps(self):
        return [c for c in self.calls if isinstance(c, str) or c[0] in ("sudo", "diskutil", "sync")]

    def assert_temp_removed(self):
        self.assertEqual(len(self.tmps), 1)
        self.assertFalse(os.path.exists(self.tmps[0]))

    def test_wrong_confirmation_writes_nothing(self):
        for answer in ("Disk4", "y", ""):
            self.calls.clear()
            self.answer = answer
            self.assertEqual(self.flash(), 1)
            self.write_image.assert_not_called()
            self.assertNotIn(SUDO, self.calls)
            self.assertIn("Not flashed", self.out)

    def test_confirmation_strips_whitespace(self):
        self.answer = " disk4 \n"
        self.assertEqual(self.flash(), 0)
        self.write_image.assert_called_once()

    def test_dry_run_downloads_and_writes_nothing(self):
        with mock.patch.object(flash.s3, "download") as download:
            self.assertEqual(self.flash(dry_run=True), 0)
        download.assert_not_called()
        self.write_image.assert_not_called()
        self.assertNotIn(SUDO, self.calls)
        self.assert_temp_removed()

    def test_success_order(self):
        self.assertEqual(self.flash(), 0)
        self.assertEqual(self.steps(), [SUDO, SUDO, ["diskutil", "unmountDisk", "disk4"], "<write>", ["sync"],
                                        ["diskutil", "eject", "disk4"]])
        self.assert_temp_removed()
        self.assertIn("Flashed", self.out)
        self.assertTrue(self.write_image.call_args.args[0].endswith(os.path.basename(IMAGE)))

    def test_image_labels_mark_match(self):
        self.flash()
        title, labels = self.filter_list.call_args_list[1].args[:2]
        self.assertEqual(labels, [IMAGE[len("os/"):]])
        self.assertIn("✓", str(self.filter_list.call_args_list[1].kwargs["extras"]))
        self.assertEqual(self.filter_list.call_args_list[2].args[1], [f"disk4  {ui.human_size(64_000_000_000)}  SD"])

    def test_unknown_size_label(self):
        self.external_disks.return_value = [flash.Disk("disk4", None, "SD")]
        self.flash()
        self.assertEqual(self.filter_list.call_args_list[2].args[1], ["disk4  ?  SD"])

    def test_esc_on_device_returns_zero(self):
        self.filter_list.return_value = None
        self.assertEqual(self.flash(), 0)
        self.assertEqual(self.calls, [])

    def test_esc_on_card_removes_temp(self):
        self.filter_list.side_effect = [0, 0, None]
        self.assertEqual(self.flash(), 0)
        self.assert_temp_removed()
        self.assertEqual(self.steps(), [])

    def test_write_error_cleans_up(self):
        self.write_image.side_effect = flash.FlashError("dd: boom")
        self.assertEqual(self.flash(), 1)
        self.assert_temp_removed()
        self.assertEqual(self.steps()[-1], ["diskutil", "unmountDisk", "disk4"])
        self.assertNotIn(["diskutil", "eject", "disk4"], self.calls)
        self.assertIn("dd: boom", self.out)

    def test_ctrl_c_cleans_up(self):
        self.write_image.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.flash()
        self.assert_temp_removed()
        self.assertEqual(self.steps()[-1], ["diskutil", "unmountDisk", "disk4"])

    def test_low_space_stops_before_download(self):
        with mock.patch.object(flash.shutil, "disk_usage", return_value=mock.Mock(free=0)), \
                mock.patch.object(flash.s3, "download") as download:
            self.assertEqual(self.flash(), 1)
        download.assert_not_called()
        self.assertNotIn(SUDO, self.calls)
        self.assert_temp_removed()

    def test_sudo_failure_stops_before_write(self):
        def run(cmd, **kw):
            self.calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1 if cmd == SUDO else 0, "", "")
        flash._run.side_effect = run
        self.assertEqual(self.flash(), 1)
        self.write_image.assert_not_called()
        self.assert_temp_removed()

    def test_unmount_failure_stops_before_write(self):
        def run(cmd, **kw):
            self.calls.append(cmd)
            busy = cmd[:2] == ["diskutil", "unmountDisk"]
            return subprocess.CompletedProcess(cmd, 1 if busy else 0, "", "disk busy" if busy else "")
        flash._run.side_effect = run
        self.assertEqual(self.flash(), 1)
        self.write_image.assert_not_called()
        self.assertIn("disk busy", self.out)

    def test_sudo_uses_terminal(self):
        self.flash()
        for call in flash._run.call_args_list:
            self.assertEqual(call.kwargs.get("capture", True), call.args[0] != SUDO)

    def test_eject_failure_warns(self):
        def run(cmd, **kw):
            self.calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1 if cmd[:2] == ["diskutil", "eject"] else 0, "", "")
        flash._run.side_effect = run
        self.assertEqual(self.flash(), 0)
        self.assertNotIn("safe to remove", self.out)

    def test_disk_changed_before_write_aborts(self):
        self.external_disks.side_effect = [[CARD], [flash.Disk("disk4", 128_000_000_000, "SD")]]
        self.assertEqual(self.flash(), 1)
        self.write_image.assert_not_called()
        self.assertFalse([c for c in self.calls if isinstance(c, list) and c[0] == "diskutil" and "disk4" in c])
        self.assertIn("changed since you picked it", self.out)

    def test_download_storage_error_fails(self):
        from botocore.exceptions import ClientError
        error = ClientError({"Error": {"Code": "NoSuchKey", "Message": "gone"}}, "GetObject")
        with mock.patch.object(flash.s3, "download", side_effect=error):
            self.assertEqual(self.flash(), 1)
        self.write_image.assert_not_called()
        self.assert_temp_removed()

    def test_excludes_temp_and_storage_disks(self):
        with mock.patch.object(flash, "disks_of", return_value={"disk7"}):
            self.flash()
        self.assertIn("disk7", self.external_disks.call_args_list[0].args[0])

    def test_disk_lookup_failure_aborts(self):
        with mock.patch.object(flash, "disks_of", side_effect=lambda p: set() if p == "/" else {"disk0"}), \
                mock.patch.object(ui, "ask") as ask:
            self.assertEqual(self.flash(), 1)
        self.external_disks.assert_not_called()
        ask.assert_not_called()
        self.assertEqual(self.filter_list.call_count, 2)
        self.write_image.assert_not_called()
        self.assertEqual(self.steps(), [])
        self.assertIn("couldn't tell which disk holds /", self.out)
        self.assert_temp_removed()

    def test_temp_disk_lookup_failure_aborts(self):
        with mock.patch.object(flash, "disks_of", side_effect=lambda p: set() if p != "/" else {"disk0"}):
            self.assertEqual(self.flash(), 1)
        self.external_disks.assert_not_called()
        self.write_image.assert_not_called()

    def test_excludes_root_disk(self):
        with mock.patch.object(flash, "disks_of", side_effect=lambda p: {"disk1"} if p == "/" else {"disk0"}):
            self.flash()
        self.assertIn("disk1", self.external_disks.call_args_list[0].args[0])

    def test_volume_names_shown(self):
        self.external_disks.return_value = [flash.Disk("disk4", 64_000_000_000, "SD", ("KNULLI", "SHARE"))]
        self.flash()
        self.assertEqual(self.filter_list.call_args_list[2].args[1],
                         [f"disk4  {ui.human_size(64_000_000_000)}  SD  (KNULLI, SHARE)"])
        self.assertIn("SD: KNULLI, SHARE", self.out)
        self.write_image.assert_called_once()

    def test_no_cards(self):
        self.external_disks.return_value = []
        ask = mock.Mock()
        with mock.patch.object(ui, "ask", ask):
            self.assertEqual(self.flash(), 1)
        ask.assert_not_called()
        self.assertIn("no SD card found", self.out)
        self.assert_temp_removed()

    def test_no_images(self):
        os.remove(os.path.join(self.root, IMAGE))
        self.assertEqual(self.flash(), 1)
        self.assertIn("no Knulli or BaseOS images", self.out)

    def test_not_macos(self):
        with mock.patch.object(flash.sys, "platform", "linux"):
            self.assertEqual(self.flash(), 1)
        self.filter_list.assert_not_called()
        self.assertIn("flash needs macOS", self.out)


class Dispatch(Isolated):
    def test_cli_dispatches_flash(self):
        with mock.patch.object(flash, "run", return_value=0) as run:
            code, _, _ = self.sync(["flash", "--dry-run"], {"bucket": "b"})
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertTrue(run.call_args.args[0].dry_run)


if __name__ == "__main__":
    unittest.main()
