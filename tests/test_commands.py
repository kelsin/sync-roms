import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli, commands, downloads, mirroring, store, ui  # noqa: E402
from test_edit import DataDir  # noqa: E402


class Cmd(DataDir):
    def run_cmd(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = commands.run(list(argv))
            except SystemExit as e:
                code = e.code
            finally:
                ui.ASSUME_YES = False
        return code, out.getvalue(), err.getvalue()


class GamesTest(Cmd):
    def test_add_remove_and_dry_run(self):
        self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip", "gba/B.zip")[0], 0)
        self.assertEqual([g["bucket"] for g in self.read("games.json")["gba"]], ["gba/A.zip", "gba/B.zip"])
        self.run_cmd("games", "add", "gba", "C.zip", "-n")
        self.assertEqual(len(self.read("games.json")["gba"]), 2)
        self.run_cmd("games", "remove", "gba", "A.zip")
        self.assertEqual([g["bucket"] for g in self.read("games.json")["gba"]], ["gba/B.zip"])
        self.run_cmd("games", "remove", "gba", "B.zip")
        self.assertNotIn("gba", self.read("games.json"))

    def test_unknown_system_exits_2(self):
        self.assertEqual(self.run_cmd("games", "add", "nope", "A.zip")[0], 2)

    def test_full_system_and_export_import(self):
        self.run_cmd("games", "full", "gba", "on")
        self.assertEqual(self.read("games.json")["gba"], {"full_system": True})
        self.assertEqual(self.run_cmd("games", "export")[1].split(), ["gba/*"])
        self.run_cmd("games", "full", "gba", "off")
        self.assertNotIn("gba", self.read("games.json"))
        listing = os.path.join(self.tmp.name, "list.txt")
        with open(listing, "w") as f:
            f.write("# comment\ngba/A.zip\nnes/*\nbogus line\n")
        code, _, err = self.run_cmd("games", "import", listing)
        self.assertEqual(code, 0)
        self.assertIn("bogus line", err)
        saved = self.read("games.json")
        self.assertEqual(saved["nes"], {"full_system": True})
        self.assertEqual(saved["gba"][0]["bucket"], "gba/A.zip")

    def test_card_target_requires_an_existing_card(self):
        self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip", "--card", "SD")[0], 2)
        self.write_cards({"SD": {"device": "full", "layout": "esde"}})
        self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip", "--card", "SD")[0], 0)
        self.assertEqual(self.read("cards.json")["SD"]["games"]["gba"][0]["bucket"], "gba/A.zip")
        self.assertEqual(self.read("cards.json")["SD"]["layout"], "esde")

    def test_sets_add_remove(self):
        set_id = store.load_sets()[0]["id"]
        self.run_cmd("games", "sets", "add", set_id)
        self.assertEqual(self.read("games.json")["sets"], [set_id])
        self.run_cmd("games", "sets", "remove", set_id)
        self.assertNotIn("sets", self.read("games.json"))
        self.assertEqual(self.run_cmd("games", "sets", "add", "nope")[0], 2)

    def write_cards(self, cards):
        with open(self.path("cards.json"), "w") as f:
            json.dump(cards, f)


class BracketKeysTest(Cmd):
    NAME = "[BIOS] Nintendo Game Boy Boot ROM (World).zip"

    def test_bracketed_names_are_literal(self):
        self.assertEqual(self.run_cmd("games", "add", "gba", self.NAME)[0], 0)
        self.assertEqual([g["bucket"] for g in self.read("games.json")["gba"]], [f"gba/{self.NAME}"])
        self.assertEqual(self.run_cmd("games", "remove", "gba", self.NAME)[0], 0)
        self.assertNotIn("gba", self.read("games.json"))

    def test_remove_globs_against_the_list_without_s3(self):
        self.run_cmd("games", "add", "gba", "A1.zip", "A2.zip", "B.zip")
        with mock.patch.object(commands.s3, "list_sizes", side_effect=AssertionError("no S3 for remove")):
            self.assertEqual(self.run_cmd("games", "remove", "gba", "A*.zip")[0], 0)
        self.assertEqual([g["bucket"] for g in self.read("games.json")["gba"]], ["gba/B.zip"])


class CardsTest(Cmd):
    def test_new_set_rename_delete(self):
        self.assertEqual(self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")[0], 0)
        self.assertEqual(self.read("cards.json")["SD"], {"device": "full", "layout": "esde"})
        self.assertEqual(self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")[0], 2)
        self.run_cmd("cards", "rename", "SD", "SD2")
        self.assertEqual(list(self.read("cards.json")), ["SD2"])
        self.assertEqual(self.run_cmd("cards", "delete", "SD2", "--yes")[0], 0)
        self.assertEqual(self.read("cards.json"), {})
        self.assertTrue(os.path.exists(self.path("cards.json.bak")))

    def test_bad_layout_for_device_is_refused(self):
        device = store.repo_json("devices")[0]
        other = next(n for n in store.repo_json("layouts") if n not in device["firmwares"])
        self.assertEqual(self.run_cmd("cards", "new", "SD", "--device", device["id"], "--layout", other)[0], 2)


class DataSafetyTest(Cmd):
    def test_corrupt_cards_json_is_never_overwritten(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{oops")
        with contextlib.redirect_stderr(io.StringIO()):
            store.update_card("SD", device="full", layout="esde")
        with open(self.path("cards.json")) as f:
            self.assertEqual(f.read(), "{oops")

    def test_save_reports_failure_and_commands_refuse(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{oops")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(store.update_card("SD", device="full", layout="esde"))
            self.assertFalse(store.save_lists(None, {"SD": {}}))
        code, _, _ = self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")
        self.assertNotEqual(code, 0)

    def test_saves_keep_a_backup(self):
        store.save_lists({"gba": []}, {})
        store.save_lists({"nes": []}, {})
        with open(self.path("games.json.bak")) as f:
            self.assertEqual(json.load(f), {"gba": []})

    def test_check_finds_problems(self):
        with open(self.path("games.json"), "w") as f:
            json.dump({"nope": [], "gba": [{"title": "x", "bucket": "nes/x.zip"}], "sets": ["ghost"]}, f)
        problems = commands.check_data()
        self.assertEqual(len(problems), 3)

    def test_overlay_save_replaces_and_drops_entries(self):
        dev = store.repo_json("devices")[0]["id"]
        store.save_overlay({dev: (["gba"], ["nes"])})
        self.assertEqual(self.read("device-systems.json"), {dev: {"add": ["gba"], "remove": ["nes"]}})
        store.save_overlay({dev: ([], [])})
        self.assertEqual(self.read("device-systems.json"), {})


class CheckShapesTest(Cmd):
    def write(self, name, data):
        with open(self.path(name), "w") as f:
            json.dump(data, f)

    def test_wrong_shapes_are_reported_not_raised(self):
        dev = store.repo_json("devices")[0]["id"]
        for name, data in (("cards.json", []), ("device-systems.json", []), ("games.json", [])):
            with self.subTest(name=name):
                self.write(name, data)
                self.assertTrue(commands.check_data())
                os.remove(self.path(name))
        self.write("games.json", {"gba": [{"bucket": 5}]})
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "games": []}})
        self.write("device-systems.json", {dev: {"add": "gba", "remove": 3}, "x": []})
        self.assertGreaterEqual(len(commands.check_data()), 4)


class CliTest(unittest.TestCase):
    def test_translate_maps_subcommands_to_flags(self):
        t = cli.translate
        self.assertEqual(t(["upload", "roms", "x", "--replace"]), ["--upload", "x", "--replace"])
        self.assertEqual(t(["-n", "mirror", "use", "d"]), ["-n", "--use-mirror", "d"])
        self.assertEqual(t(["mirror", "d"]), ["--mirror", "d"])
        self.assertEqual(t(["convert"]), ["--cd"])
        self.assertEqual(t(["games", "edit"]), ["--edit"])
        self.assertEqual(t(["devices", "steam-deck", "--json"]), ["--devices", "--device-id", "steam-deck", "--json"])
        self.assertEqual(t(["/Volumes/SD", "-n"]), ["/Volumes/SD", "-n"])
        self.assertEqual(t(["sync", "/x"]), ["/x"])

    def test_flag_between_a_mode_and_its_directory(self):
        t = cli.translate
        self.assertEqual(t(["diff", "-n", "/x"]), ["--diff", "/x", "-n"])
        self.assertEqual(t(["playlist", "-y", "/Volumes/SD"]), ["--m3u", "/Volumes/SD", "-y"])
        self.assertEqual(t(["mirror", "-y", "/new"]), ["--mirror", "/new", "-y"])
        self.assertEqual(t(["devices", "-y", "rg35xx"]), ["--devices", "--device-id", "rg35xx", "-y"])

    def test_mode_with_a_stray_directory_exits_2(self):
        args = cli.build_parser().parse_args(["--diff", "-n", "/x"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.check_modes(args)
        self.assertEqual(cm.exception.code, 2)
        cli.check_modes(cli.build_parser().parse_args(["--upload-scrapes", "/card"]))

    def test_commands_after_global_flags_route_to_commands_run(self):
        for argv, expect in ((["-y", "check"], ["check", "-y"]), (["-n", "doctor"], ["doctor", "-n"]),
                             (["-y", "games", "list"], ["games", "list", "-y"])):
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", ["sync-roms"] + argv), \
                    mock.patch.object(commands, "run", return_value=0) as run:
                self.assertEqual(cli.sync(), 0)
            run.assert_called_once_with(expect)

    def test_conflicting_or_ignored_flags_exit_2(self):
        parse = lambda *a: cli.check_modes(cli.build_parser().parse_args(list(a)))  # noqa: E731
        for argv in (["--edit", "--upload"], ["--replace"], ["--edit", "-n"], ["--devices", "-a"], ["--m3u", "--systems", "gba"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                parse(*argv)
            self.assertEqual(cm.exception.code, 2)
        self.assertEqual(parse("--upload", "--replace"), "--upload")

    def test_abbreviations_are_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.build_parser().parse_args(["--up"])
        self.assertEqual(cm.exception.code, 2)


class UiTest(unittest.TestCase):
    def test_confirm_and_choose_take_the_default_on_eof_and_yes(self):
        with mock.patch("builtins.input", side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(ui.confirm("q"))
            self.assertFalse(ui.confirm("q", default=False))
            self.assertEqual(ui.choose("q", "yn", "n"), "n")
        with mock.patch.object(ui, "ASSUME_YES", True), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(ui.confirm("q"))
            self.assertFalse(ui.confirm("q", default=False))

    def test_choose_reads_the_first_letter(self):
        with mock.patch("builtins.input", side_effect=["x", "List"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ui.choose("q", "ynl", "n"), "l")


class DownloadsTest(unittest.TestCase):
    def test_interrupted_download_temp_files_are_not_roms(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for name in ("Game.zip", "Game.zip.1a2b3c4d", "Other.zip.part"):
                open(os.path.join(d, name), "w").close()
            self.assertEqual(downloads.find_extras(d, ["gba/Game.zip"]), [])

    def test_failure_hint(self):
        self.assertIn("access denied", downloads.failure_hint(Exception("403 Forbidden")))
        self.assertEqual(downloads.failure_hint(Exception("odd")), "")

    def test_mirror_keeps_stale_files_when_a_download_failed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, ".sync-roms-mirror"), "w").close()
            stale = os.path.join(root, "gba", "Old.zip")
            os.makedirs(os.path.dirname(stale))
            open(stale, "w").close()
            with mock.patch.object(mirroring.store, "load_manifest", return_value={}), \
                    mock.patch.object(mirroring.store, "all_card_names", return_value=[]), \
                    mock.patch.object(mirroring, "mirror_wanted", return_value={"gba/New.zip": 3}), \
                    mock.patch.object(mirroring.downloads, "run_downloads", return_value=1), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mirroring.refresh_mirror(root), 1)
            self.assertTrue(os.path.exists(stale))


if __name__ == "__main__":
    unittest.main()
