import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import cli  # noqa: E402
from sync_roms import downloads, picker, store  # noqa: E402


def repo(name):
    return store.repo_json(os.path.splitext(name)[0])


LAYOUTS = {"esde": {"label": "ES-DE"}, "knulli": {"label": "Knulli"}, "onion": {"label": "Onion"}}
DEVICES = [{"id": "a", "firmwares": ["knulli", "onion"]}, {"id": "b", "firmwares": ["esde"]}]


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


class SetupTest(unittest.TestCase):
    def test_device_layouts_keep_the_devices_order(self):
        self.assertEqual(list(picker.device_layouts(DEVICES[0], LAYOUTS)), ["knulli", "onion"])

    def test_saved_setup_resolves_a_current_card(self):
        saved = {"device": "a", "layout": "onion", "android_media": "never"}
        self.assertEqual(picker.saved_setup(saved, DEVICES, LAYOUTS), (DEVICES[0], "onion"))

    def test_saved_setup_from_before_firmwares_still_loads(self):
        self.assertEqual(picker.saved_setup({"device": "b", "layout": "esde"}, DEVICES, LAYOUTS), (DEVICES[1], "esde"))

    def test_saved_setup_full_accepts_any_layout(self):
        self.assertEqual(picker.saved_setup({"device": "full", "layout": "onion"}, DEVICES, LAYOUTS), (None, "onion"))

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
                mock.patch.object(picker, "pick_layout", return_value="onion") as pick:
            self.assertEqual(picker.choose_setup(manifest), (DEVICES[0], "onion"))
        offered, default = pick.call_args[0]
        self.assertEqual(list(offered), ["knulli", "onion"])
        self.assertEqual(default, "knulli")

    def test_choose_setup_full_offers_every_layout(self):
        manifest = {"devices": DEVICES, "layouts": LAYOUTS}
        with mock.patch.object(picker, "pick_device", return_value="full"), \
                mock.patch.object(picker, "pick_layout", return_value="esde") as pick:
            self.assertEqual(picker.choose_setup(manifest), (None, "esde"))
        self.assertEqual(list(pick.call_args[0][0]), list(LAYOUTS))


class PrepareDirsTest(unittest.TestCase):
    def test_creates_the_nested_emudeck_bios_folder(self):
        layout = repo("layouts.json")["emudeck"]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            roms, bios = cli.prepare_dirs(tmp, layout, False, ask=False)
            self.assertTrue(os.path.isdir(os.path.join(tmp, "Emulation", "roms")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "Emulation", "bios")))
            self.assertEqual(bios, os.path.join(tmp, "Emulation", "bios"))
            self.assertFalse(os.path.exists(os.path.join(tmp, "Emulation", "saves")))

    def test_creates_the_esde_retroarch_save_folders(self):
        layout = repo("layouts.json")["esde"]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            os.makedirs(os.path.join(tmp, "RetroArch", "states", "mGBA"))
            cli.prepare_dirs(tmp, layout, False, ask=False)
            self.assertEqual(sorted(os.listdir(os.path.join(tmp, "RetroArch"))), ["saves", "states"])
            self.assertEqual(os.listdir(os.path.join(tmp, "RetroArch", "states")), ["mGBA"])

    def test_dry_run_only_says_it_would_create_the_save_folders(self):
        layout = repo("layouts.json")["esde"]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            cli.prepare_dirs(tmp, layout, True, ask=False)
            self.assertEqual(os.listdir(tmp), [])
        self.assertIn(os.path.join(tmp, "RetroArch", "saves"), out.getvalue())


class FindExtrasTest(unittest.TestCase):
    def test_psvita_file_goes_with_its_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("A.zip", "A.psvita", "Gone.psvita", "Other.psvita", "Other.zip"):
                touch(os.path.join(tmp, name))
            extras = downloads.find_extras(tmp, ["psvita/A.zip"])
            self.assertEqual(sorted(os.path.basename(p) for p in extras), ["Gone.psvita", "Other.psvita", "Other.zip"])

    def test_extracted_files_are_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "A.gba"))
            self.assertEqual(len(downloads.find_extras(tmp, ["gba/A.zip"])), 1)

    def test_db_caches_are_ignored_only_when_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "cache6.db"))
            self.assertEqual(len(downloads.find_extras(tmp, [])), 1)
            self.assertEqual(downloads.find_extras(tmp, [], skip_db=True), [])
            self.assertTrue(downloads.has_local_files(tmp))
            self.assertFalse(downloads.has_local_files(tmp, skip_db=True))

    def test_a_file_spelled_differently_is_renamed_not_an_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "GAME.zip"))
            renames = []
            self.assertEqual(downloads.find_extras(tmp, ["gba/Game.zip"], renames=renames), [])
            self.assertEqual(renames, [(os.path.join(tmp, "GAME.zip"), os.path.join(tmp, "Game.zip"))])

    def walk(self, *names):
        """find_extras over a card folder /card that lists names (a case-sensitive card), without touching the disk."""
        return mock.patch.object(downloads, "walk_roms", lambda dest, **k: iter([(dest, list(names))]))

    def test_a_unicode_form_difference_is_a_rename(self):
        renames = []
        with self.walk("Pok\u0065\u0301mon.zip"):
            self.assertEqual(downloads.find_extras("/card", ["gb/Pok\u00e9mon.zip"], renames=renames), [])
        self.assertEqual(renames, [("/card/Pok\u0065\u0301mon.zip", "/card/Pok\u00e9mon.zip")])

    def test_a_second_spelling_beside_the_expected_file_is_an_extra(self):
        renames = []
        with self.walk("Game.zip", "GAME.zip"):
            self.assertEqual(downloads.find_extras("/card", ["gba/Game.zip"], renames=renames), ["/card/GAME.zip"])
        self.assertEqual(renames, [])

    def test_a_file_matching_two_spellings_is_kept_and_not_renamed(self):
        renames = []
        with self.walk("GAME.zip"):
            self.assertEqual(downloads.find_extras("/card", ["gba/Game.zip", "gba/game.zip"], renames=renames), [])
        with self.walk("GAME.zip", "game.ZIP"):
            self.assertEqual(downloads.find_extras("/card", ["gba/Game.zip"], renames=renames), [])
        self.assertEqual(renames, [])

    def test_psvita_file_goes_with_its_zip_in_any_case(self):
        with self.walk("a.PSVITA", "A.zip"):
            self.assertEqual(downloads.find_extras("/card", ["psvita/A.zip"]), [])

    def test_a_rename_left_half_done_is_an_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, ".Game.zip.rename"))
            touch(os.path.join(tmp, ".multi-disc", ".A (Disc 1).chd.rename"))
            touch(os.path.join(tmp, ".hidden"))
            self.assertEqual(sorted(downloads.find_extras(tmp, [], disc_dir=".multi-disc")),
                             [os.path.join(tmp, ".Game.zip.rename"), os.path.join(tmp, ".multi-disc", ".A (Disc 1).chd.rename")])
            self.assertFalse(downloads.has_local_files(tmp))

    def test_a_case_only_rename_changes_the_name_on_the_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "GAME.zip"), b"abc")
            downloads.rename_on_card(os.path.join(tmp, "GAME.zip"), os.path.join(tmp, "Game.zip"))
            self.assertEqual(os.listdir(tmp), ["Game.zip"])
            with open(os.path.join(tmp, "Game.zip"), "rb") as f:
                self.assertEqual(f.read(), b"abc")


class AfterRenamesTest(unittest.TestCase):
    def test_a_renamed_file_that_is_current_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "GAME.zip"), b"x" * 5)
            renames = [(os.path.join(tmp, "GAME.zip"), os.path.join(tmp, "Game.zip"))]
            todo = [("gba/Game.zip", os.path.join(tmp, "Game.zip"), 5)]
            self.assertEqual(downloads.after_renames(todo, renames), [])

    def test_a_renamed_file_of_another_size_is_downloaded_to_the_new_spelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "GAME.zip"), b"x" * 3)
            renames = [(os.path.join(tmp, "GAME.zip"), os.path.join(tmp, "Game.zip"))]
            todo = [("gba/Game.zip", os.path.join(tmp, "game.zip"), 5), ("gba/B.zip", os.path.join(tmp, "B.zip"), 1)]
            self.assertEqual(downloads.after_renames(todo, renames),
                             [("gba/Game.zip", os.path.join(tmp, "Game.zip"), 5), ("gba/B.zip", os.path.join(tmp, "B.zip"), 1)])


class PlanMovesTest(unittest.TestCase):
    JOB = ("gba/Game.zip", "/card/ROMs/gba/Game.zip", 5)

    def test_an_extra_with_the_name_and_size_moves(self):
        self.assertEqual(downloads.plan_moves([self.JOB], {"/card/ROMs/old/GAME.ZIP": 5}),
                         [("/card/ROMs/old/GAME.ZIP", self.JOB)])

    def test_another_size_or_name_does_not_move(self):
        self.assertEqual(downloads.plan_moves([self.JOB], {"/card/ROMs/old/Game.zip": 4, "/card/ROMs/old/Other.zip": 5}), [])

    def test_two_extras_or_two_jobs_with_one_name_and_size_move_nothing(self):
        self.assertEqual(downloads.plan_moves([self.JOB], {"/card/a/Game.zip": 5, "/card/b/Game.zip": 5}), [])
        other = ("gb/Game.zip", "/card/ROMs/gb/Game.zip", 5)
        self.assertEqual(downloads.plan_moves([self.JOB, other], {"/card/a/Game.zip": 5}), [])

    def test_a_job_of_unknown_size_does_not_move(self):
        self.assertEqual(downloads.plan_moves([(*self.JOB[:2], None)], {"/card/a/Game.zip": 5}), [])


if __name__ == "__main__":
    unittest.main()
