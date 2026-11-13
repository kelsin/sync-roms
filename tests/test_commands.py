import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cli, commands, downloads, mirroring, runtime, store, ui  # noqa: E402
from helpers import Cmd, DataDir  # noqa: E402,F401



class CardCmd(Cmd):
    """Cmd with a card SD saved, so `games` commands can name it."""

    def setUp(self):
        super().setUp()
        with open(self.path("cards.json"), "w") as f:
            json.dump({"SD": {"device": "full", "layout": "esde"}}, f)

    def run_cmd(self, *argv):
        return super().run_cmd(*argv, *(["--card", "SD"] if argv[0] == "games" else []))

    def games(self):
        return self.read("cards.json")["SD"].get("games", {})


class GamesTest(CardCmd):
    def test_add_remove_and_dry_run(self):
        self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip", "gba/B.zip")[0], 0)
        self.assertEqual([g["bucket"] for g in self.games()["gba"]], ["gba/A.zip", "gba/B.zip"])
        self.run_cmd("games", "add", "gba", "C.zip", "-n")
        self.assertEqual(len(self.games()["gba"]), 2)
        self.run_cmd("games", "remove", "gba", "A.zip")
        self.assertEqual([g["bucket"] for g in self.games()["gba"]], ["gba/B.zip"])
        self.run_cmd("games", "remove", "gba", "B.zip")
        self.assertNotIn("gba", self.games())

    def test_add_saves_proper_arcade_name(self):
        raw = {}
        commands.add_games(raw, "fbneo", ["fbneo/1941j.zip"])
        self.assertEqual(raw["fbneo"], [{"title": "1941: Counter Attack (Japan)", "bucket": "fbneo/1941j.zip"}])

    def test_add_warns_about_a_name_the_cache_lacks(self):
        tree = commands.inventory.Tree("s", 0, {"gba/A.zip": 1, "snes/X.zip": 1}, {})
        with mock.patch.object(commands.inventory, "current", return_value=tree):
            code, out, err = self.run_cmd("games", "add", "gba", "A.zip", "Typo.zip")
            self.assertEqual(code, 0)
            self.assertIn("gba/Typo.zip isn't in the storage cache", err)
            self.assertNotIn("gba/A.zip", err)
            self.assertEqual([g["bucket"] for g in self.games()["gba"]], ["gba/A.zip", "gba/Typo.zip"])
            self.assertEqual(self.run_cmd("games", "add", "nes", "New.zip")[2], "")  # the cache has no nes/ folder
        self.assertEqual(self.run_cmd("games", "add", "gba", "Other.zip")[2], "")  # no cache

    def test_games_commands_require_a_card(self):
        code, _, err = Cmd.run_cmd(self, "games", "add", "gba", "A.zip")
        self.assertEqual(code, 2)
        self.assertIn("--card", err)
        self.assertFalse(os.path.exists(self.path("games.json")))

    def test_unknown_system_exits_2(self):
        self.assertEqual(self.run_cmd("games", "add", "nope", "A.zip")[0], 2)

    def test_full_system_and_export_import(self):
        self.run_cmd("games", "full", "gba", "on")
        self.assertEqual(self.games()["gba"], {"full_system": True})
        self.assertEqual(self.run_cmd("games", "export")[1].split(), ["gba/*"])
        self.run_cmd("games", "full", "gba", "off")
        self.assertNotIn("gba", self.games())
        listing = os.path.join(self.tmp.name, "list.txt")
        with open(listing, "w") as f:
            f.write("# comment\ngba/A.zip\nnes/*\nbogus line\n")
        code, _, err = self.run_cmd("games", "import", listing)
        self.assertEqual(code, 0)
        self.assertIn("bogus line", err)
        saved = self.games()
        self.assertEqual(saved["nes"], {"full_system": True})
        self.assertEqual(saved["gba"][0]["bucket"], "gba/A.zip")

    def test_export_and_import_carry_collections_and_frontend_names(self):
        from sync_roms import collections
        collections.save_collection({"id": "favs", "name": "Favs", "games": []})
        cards = self.read("cards.json")
        cards["SD"].update(collections=["favs"], frontend_collections=["Favs"], drivers=["a-v1.zip"])
        self.write_json("cards.json", cards)
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(),
                         ["@collections favs", "@frontend_collections Favs", "@drivers a-v1.zip"])
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        listing = os.path.join(self.tmp.name, "list.txt")
        with open(listing, "w") as f:
            f.write("@collections favs\n@collections ghost\n@frontend_collections Favs\n@drivers a-v1.zip\n@bogus x\n")
        code, _, err = self.run_cmd("games", "import", listing, "-n")
        self.assertEqual((code, self.read("cards.json")["SD"].get("collections")), (0, None))
        code, _, err = self.run_cmd("games", "import", listing)
        self.assertEqual(code, 0)
        self.assertIn("ghost", err)
        self.assertIn("@bogus", err)
        entry = self.read("cards.json")["SD"]
        self.assertEqual((entry["collections"], entry["frontend_collections"], entry["drivers"]), (["favs"], ["Favs"], ["a-v1.zip"]))

    def test_import_skips_an_empty_frontend_collection_name(self):
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("@frontend_collections\n@frontend_collections   \n@frontend_collections Favs\n")
        self.assertEqual(self.run_cmd("games", "import", path)[0], 0)
        self.assertEqual(self.read("cards.json")["SD"]["frontend_collections"], ["Favs"])

    def test_export_carries_surprise_state(self):
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprise": False, "surprises": [
            {"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}], "games": {"gba": [{"bucket": "gba/B.zip"}]}}})
        code, out, _ = self.run_cmd("games", "export")
        self.assertEqual(out.splitlines(), ["gba/B.zip", "@surprise false", "@surprises gba/A (USA).zip"])

    def test_import_reads_surprise_lines(self):
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("gba/B.zip\n@surprise false\n@surprises gba/A (USA).zip\n@surprises nope/X.zip\n@surprise maybe\n")
        with mock.patch.object(commands.s3, "list_sizes", lambda prefix, sizes=True: {}):
            code, _, err = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("nope/X.zip", err)
        self.assertIn("@surprise maybe", err)
        entry = self.read("cards.json")["SD"]
        self.assertIs(entry["surprise"], False)
        self.assertEqual(entry["surprises"], [{"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}])
        self.assertEqual(entry["games"]["gba"][0]["bucket"], "gba/B.zip")

    def test_import_keeps_at_most_ten_surprises(self):
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("".join(f"@surprises gba/G{i} (USA).zip\n" for i in range(12)))
        with mock.patch.object(commands.s3, "list_sizes", lambda prefix, sizes=True: {}):
            code, _, err = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("gba/G10 (USA).zip", err)
        self.assertIn("gba/G11 (USA).zip", err)
        self.assertEqual([x["bucket"] for x in self.read("cards.json")["SD"]["surprises"]],
                         [f"gba/G{i} (USA).zip" for i in range(10)])

    def test_import_surprise_true_drops_the_off_flag(self):
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprise": False}})
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("@surprise true\n")
        self.assertEqual(self.run_cmd("games", "import", path)[0], 0)
        self.assertNotIn("surprise", self.read("cards.json")["SD"])

    def test_multi_disc_surprise_round_trips(self):
        ff7 = {"system": "psx", "bucket": "psx/FF7 (USA).m3u", "title": "FF7 (USA)",
               "files": ["psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd"]}
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprises": [ff7]}})
        out = self.run_cmd("games", "export")[1]
        self.assertEqual(out.splitlines(), ["@surprises psx/FF7 (USA).m3u"])
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write(out)
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        listing = dict.fromkeys([ff7["bucket"], *ff7["files"], "psx/Spyro (USA).chd"], 1)
        with mock.patch.object(commands.s3, "list_sizes", lambda prefix, sizes=True: listing if prefix == "psx/" else {}):
            self.assertEqual(self.run_cmd("games", "import", path)[0], 0)
        self.assertEqual(self.read("cards.json")["SD"]["surprises"], [ff7])

    def test_card_target_requires_an_existing_card(self):
        self.assertEqual(Cmd.run_cmd(self, "games", "add", "gba", "A.zip", "--card", "NOPE")[0], 2)
        self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip")[0], 0)
        self.assertEqual(self.read("cards.json")["SD"]["games"]["gba"][0]["bucket"], "gba/A.zip")
        self.assertEqual(self.read("cards.json")["SD"]["layout"], "esde")

    def test_sets_add_remove(self):
        set_id = store.load_sets()[0]["id"]
        self.run_cmd("games", "sets", "add", set_id)
        self.assertEqual(self.games()["sets"], [set_id])
        self.run_cmd("games", "sets", "remove", set_id)
        self.assertNotIn("sets", self.games())
        self.assertEqual(self.run_cmd("games", "sets", "add", "nope")[0], 2)

    def write_cards(self, cards):
        with open(self.path("cards.json"), "w") as f:
            json.dump(cards, f)


class BracketKeysTest(CardCmd):
    NAME = "[BIOS] Nintendo Game Boy Boot ROM (World).zip"

    def test_bracketed_names_are_literal(self):
        self.assertEqual(self.run_cmd("games", "add", "gba", self.NAME)[0], 0)
        self.assertEqual([g["bucket"] for g in self.games()["gba"]], [f"gba/{self.NAME}"])
        self.assertEqual(self.run_cmd("games", "remove", "gba", self.NAME)[0], 0)
        self.assertNotIn("gba", self.games())

    def test_remove_globs_against_the_list_without_s3(self):
        self.run_cmd("games", "add", "gba", "A1.zip", "A2.zip", "B.zip")
        with mock.patch.object(commands.s3, "list_sizes", side_effect=AssertionError("no S3 for remove")):
            self.assertEqual(self.run_cmd("games", "remove", "gba", "A*.zip")[0], 0)
        self.assertEqual([g["bucket"] for g in self.games()["gba"]], ["gba/B.zip"])


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
            self.assertFalse(store.save_lists({"SD": {}}))
        code, _, _ = self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")
        self.assertNotEqual(code, 0)

    def test_check_finds_problems(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"device": "full", "layout": "esde",
                             "games": {"nope": [], "gba": [{"title": "x", "bucket": "nes/x.zip"}], "sets": ["ghost"]}}}, f)
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
        for name, data in (("cards.json", []), ("device-systems.json", [])):
            with self.subTest(name=name):
                self.write(name, data)
                self.assertTrue(commands.check_data())
                os.remove(self.path(name))
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "games": []},
                                  "d": {"device": "full", "layout": "esde", "games": {"gba": [{"bucket": 5}]}}})
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
        self.assertEqual(t(["cards", "edit"]), ["--edit"])
        self.assertEqual(t(["edit"]), ["--edit"])
        self.assertEqual(t(["devices", "steam-deck", "--json"]), ["--devices", "--device-id", "steam-deck", "--json"])
        self.assertEqual(t(["/Volumes/SD", "-n"]), ["/Volumes/SD", "-n"])
        self.assertEqual(t(["sync", "/x"]), ["/x"])

    def test_flag_between_a_mode_and_its_directory(self):
        t = cli.translate
        self.assertEqual(t(["diff", "-n", "/x"]), ["--diff", "/x", "-n"])
        self.assertEqual(t(["playlist", "-y", "/Volumes/SD"]), ["--m3u", "/Volumes/SD", "-y"])
        self.assertEqual(t(["mirror", "-y", "/new"]), ["--mirror", "/new", "-y"])
        self.assertEqual(t(["devices", "-y", "rg35xx"]), ["--devices", "--device-id", "rg35xx", "-y"])

    def test_value_flags_between_a_mode_and_its_directory(self):
        t = cli.translate
        self.assertEqual(t(["diff", "--system", "gba", "/tmp"]), ["--diff", "/tmp", "--system", "gba"])
        self.assertEqual(t(["-n", "diff", "--json", "--system", "gba", "/tmp"]), ["-n", "--diff", "/tmp", "--json", "--system", "gba"])
        self.assertEqual(t(["--json", "devices"]), ["--json", "--devices"])

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

    def test_require_terminal_looks_through_quiet_to_the_real_stdout(self):
        tty = mock.Mock()
        tty.isatty.return_value = True
        with mock.patch.object(sys, "stdout", tty), mock.patch.object(sys.stdin, "isatty", lambda: True):
            ui.set_output(True, False)
            try:
                ui.require_terminal("pick", "--x")
            finally:
                ui.reset()


class BackupTest(DataDir):
    def test_cards_bak_keeps_the_copy_from_before_this_run(self):
        store._backed_up.clear()
        self.assertTrue(store.write_cards({"a": {}}))
        self.assertTrue(store.write_cards({"a": {}, "b": {}}))
        self.assertTrue(store.write_cards({"c": {}}))
        self.assertEqual(self.read("cards.json.bak"), {"a": {}})


class CardSizeTest(Cmd):
    def test_size_is_saved_normalized_and_listed(self):
        self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde", "--size", "512gb")
        self.run_cmd("cards", "new", "SD2", "--device", "full", "--layout", "esde", "--size", "1 tb")
        rows = {r["name"]: r["size"] for r in json.loads(self.run_cmd("cards", "list", "--json")[1])}
        self.assertEqual(rows, {"SD": "512 GB", "SD2": "1 TB"})
        self.run_cmd("cards", "set", "SD", "--size", "256")
        self.assertEqual(self.read("cards.json")["SD"]["size"], "256 GB")

    def test_bad_size_exits_2(self):
        self.assertEqual(self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde", "--size", "big")[0], 2)


class FailedSaveTest(CardCmd):
    def test_games_save_failure_exits_3(self):
        with mock.patch.object(store, "save_lists", return_value=False):
            self.assertEqual(self.run_cmd("games", "add", "gba", "A.zip")[0], 3)

    def test_card_delete_failure_exits_3(self):
        self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")
        with mock.patch.object(store, "delete_card", return_value=False):
            self.assertEqual(self.run_cmd("cards", "delete", "SD", "--yes")[0], 3)


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

    def test_failure_hint_for_a_file_gone_from_a_storage_folder_points_at_cache_update(self):
        e = FileNotFoundError(2, "No such file or directory", "/Volumes/roms/psx/Big1.chd")
        with mock.patch.object(runtime, "ROOT", "/Volumes/roms"):
            self.assertIn("sync-roms cache update", downloads.failure_hint(e))

    def test_failure_hint_for_a_missing_local_file_says_nothing_about_storage(self):
        e = FileNotFoundError(2, "No such file or directory", "/Volumes/SD/ROMs/psx/Big1.chd.part")
        with mock.patch.object(runtime, "ROOT", "/Volumes/roms"):
            self.assertEqual(downloads.failure_hint(e), "")
        with mock.patch.object(runtime, "ROOT", None):
            self.assertEqual(downloads.failure_hint(e), "")

    def test_failure_summary_points_at_cache_update_only_when_every_failure_is_stale(self):
        stale = ("psx/A.chd", "[Errno 2] No such file or directory" + downloads.STALE_HINT)
        other = ("psx/B.chd", "[Errno 5] Input/output error")
        for failures, cache, retry in (([stale, stale], True, False), ([stale, other], False, True)):
            with self.subTest(failures=failures), contextlib.redirect_stdout(io.StringIO()) as out:
                cli.report_failures(failures)
            last = out.getvalue().splitlines()[-1]
            self.assertEqual("sync-roms cache update" in last, cache)
            self.assertEqual("run the same command again" in last, retry)

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

    def test_mirror_deletes_its_leftover_part_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, ".sync-roms-mirror"), "w").close()
            os.makedirs(os.path.join(root, "gba"))
            for name in ("Keep.zip", "Keep.zip.part"):
                open(os.path.join(root, "gba", name), "w").close()
            with mock.patch.object(mirroring.store, "load_manifest", return_value={}), \
                    mock.patch.object(mirroring.store, "all_card_names", return_value=[]), \
                    mock.patch.object(mirroring, "mirror_wanted", return_value={"gba/Keep.zip": 0}), \
                    mock.patch.object(mirroring.downloads, "run_downloads", return_value=0), \
                    mock.patch.object(mirroring.ui, "confirm", return_value=True), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mirroring.refresh_mirror(root), 0)
            self.assertEqual(os.listdir(os.path.join(root, "gba")), ["Keep.zip"])


if __name__ == "__main__":
    unittest.main()
