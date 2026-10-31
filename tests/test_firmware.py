import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "src", "sync_roms", "data")
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli  # noqa: E402
from sync_roms import chd, downloads, picker  # noqa: E402


def repo(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


LAYOUTS = {"esde": {"label": "ES-DE"}, "knulli": {"label": "Knulli"}, "muos": {"label": "muOS"}}
DEVICES = [{"id": "a", "firmwares": ["knulli", "muos"]}, {"id": "b", "firmwares": ["esde"]}]


class ShippedDataTest(unittest.TestCase):
    def test_every_device_firmware_is_a_layout(self):
        layouts = repo("layouts.json")
        for d in repo("devices.json"):
            self.assertTrue(d["firmwares"], d["id"])
            self.assertNotIn("layout", d)
            for fw in d["firmwares"]:
                self.assertIn(fw, layouts, d["id"])

    def test_every_system_has_a_folder_entry_for_every_layout(self):
        layouts = repo("layouts.json")
        for s in repo("systems.json"):
            self.assertEqual(set(s["folders"]), set(layouts), s["bucket"])

    def test_slot_only_has_game_boy_systems(self):
        folders = {s["bucket"]: s["folders"]["slot"] for s in repo("systems.json") if s["folders"]["slot"]}
        self.assertEqual(folders, {"gba": "GBA", "gb": "GB", "gbc": "GBC"})

    def test_muos_bios_dir_is_nested(self):
        self.assertEqual(repo("layouts.json")["muos"]["bios_dir"], "MUOS/bios")


class SetupTest(unittest.TestCase):
    def test_device_layouts_keep_the_devices_order(self):
        self.assertEqual(list(picker.device_layouts(DEVICES[0], LAYOUTS)), ["knulli", "muos"])

    def test_saved_setup_resolves_a_current_card(self):
        saved = {"device": "a", "layout": "muos", "android_media": "never"}
        self.assertEqual(picker.saved_setup(saved, DEVICES, LAYOUTS), (DEVICES[0], "muos"))

    def test_saved_setup_from_before_firmwares_still_loads(self):
        self.assertEqual(picker.saved_setup({"device": "b", "layout": "esde"}, DEVICES, LAYOUTS), (DEVICES[1], "esde"))

    def test_saved_setup_full_accepts_any_layout(self):
        self.assertEqual(picker.saved_setup({"device": "full", "layout": "muos"}, DEVICES, LAYOUTS), (None, "muos"))

    def test_saved_setup_rejects_a_firmware_the_device_lacks(self):
        self.assertIsNone(picker.saved_setup({"device": "b", "layout": "knulli"}, DEVICES, LAYOUTS))

    def test_saved_setup_rejects_unknown_device_layout_or_junk(self):
        for saved in ({"device": "zzz", "layout": "esde"}, {"device": "a", "layout": "nope"}, None, "x"):
            self.assertIsNone(picker.saved_setup(saved, DEVICES, LAYOUTS))

    def test_choose_setup_skips_the_prompt_for_a_single_firmware(self):
        manifest = {"devices": DEVICES, "layouts": LAYOUTS}
        with mock.patch.object(picker, "pick_device", return_value=DEVICES[1]), \
                mock.patch.object(picker, "pick_layout") as pick:
            self.assertEqual(picker.choose_setup(manifest), (DEVICES[1], "esde"))
        pick.assert_not_called()

    def test_choose_setup_offers_only_the_devices_firmwares_default_first(self):
        manifest = {"devices": DEVICES, "layouts": LAYOUTS}
        with mock.patch.object(picker, "pick_device", return_value=DEVICES[0]), \
                mock.patch.object(picker, "pick_layout", return_value="muos") as pick:
            self.assertEqual(picker.choose_setup(manifest), (DEVICES[0], "muos"))
        offered, default = pick.call_args[0]
        self.assertEqual(list(offered), ["knulli", "muos"])
        self.assertEqual(default, "knulli")

    def test_choose_setup_full_offers_every_layout(self):
        manifest = {"devices": DEVICES, "layouts": LAYOUTS}
        with mock.patch.object(picker, "pick_device", return_value="full"), \
                mock.patch.object(picker, "pick_layout", return_value="esde") as pick:
            self.assertEqual(picker.choose_setup(manifest), (None, "esde"))
        self.assertEqual(list(pick.call_args[0][0]), list(LAYOUTS))


class PrepareDirsTest(unittest.TestCase):
    def test_creates_the_nested_muos_bios_folder(self):
        layout = repo("layouts.json")["muos"]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            roms, bios = cli.prepare_dirs(tmp, layout, False, ask=False)
            self.assertTrue(os.path.isdir(os.path.join(tmp, "ROMS")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "MUOS", "bios")))
            self.assertEqual(bios, os.path.join(tmp, "MUOS", "bios"))


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class UnzipTest(unittest.TestCase):
    def test_rom_rel_flattens_only_when_unzipping(self):
        self.assertEqual(downloads.rom_rel("gba/Hacks/A.zip", False), "Hacks/A.zip")
        self.assertEqual(downloads.rom_rel("gba/Hacks/A.zip", True), "A.zip")

    def test_extracted_archive_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "A.zip")
            jobs = [("gba/A.zip", zip_path, 10)]
            self.assertEqual(downloads.plan_downloads(jobs, unzip=True), jobs)
            touch(os.path.join(tmp, "A.gba"))
            self.assertEqual(downloads.plan_downloads(jobs, unzip=True), [])
            self.assertEqual(downloads.plan_downloads(jobs), jobs)  # other layouts still want the archive

    def test_extracted_roms_are_not_extras_but_stray_files_are(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("A.gba", "B.gba", "Old.gba"):
                touch(os.path.join(tmp, name))
            extras = downloads.find_extras(tmp, ["gba/A.zip", "gba/sub/B.zip"], unzip=True)
            self.assertEqual([os.path.basename(p) for p in extras], ["Old.gba"])

    def test_without_unzip_extracted_files_are_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "A.gba"))
            self.assertEqual(len(downloads.find_extras(tmp, ["gba/A.zip"])), 1)

    def test_unzip_roms_extracts_flat_and_removes_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "A.zip")
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("inner/A.gba", b"rom")
                z.writestr("inner/", b"")
            self.assertEqual(chd.unzip_roms([path, os.path.join(tmp, "B.gba")]), [])
            self.assertEqual(sorted(os.listdir(tmp)), ["A.gba"])
            with open(os.path.join(tmp, "A.gba"), "rb") as f:
                self.assertEqual(f.read(), b"rom")

    def test_card_archives_finds_leftover_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "A.zip"))
            touch(os.path.join(tmp, "B.gba"))
            touch(os.path.join(tmp, "C.7z"))
            found = chd.card_archives([tmp, os.path.join(tmp, "missing")])
            self.assertEqual(sorted(os.path.basename(p) for p in found), ["A.zip", "C.7z"])

    def test_unzip_roms_keeps_a_bad_archive_and_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "A.zip")
            touch(path, b"not a zip")
            failures = chd.unzip_roms([path])
            self.assertEqual([p for p, _ in failures], [path])
            self.assertTrue(os.path.exists(path))

    def test_unzip_roms_reports_a_7z_without_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "A.7z")
            touch(path)
            with mock.patch.object(chd.shutil, "which", return_value=None):
                failures = chd.unzip_roms([path])
            self.assertEqual([p for p, _ in failures], [path])
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
