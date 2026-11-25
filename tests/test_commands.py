import contextlib
import hashlib
import io
import json
import os
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import clean, cli, commands, downloads, inventory, mirroring, names, runtime, s3, store, themeart, ui, usersettings  # noqa: E402
from helpers import Cmd, DataDir, storage_sets  # noqa: E402,F401



class ConfigSetTest(Cmd):
    def settings(self):
        return self.read("settings.json") if os.path.exists(self.path("settings.json")) else {}

    def test_sets_each_kind_of_setting(self):
        for argv, saved in ((["bucket", "b"], {"bucket": "b"}), (["eject", "false"], {"eject": False}),
                            (["storage_cache_declined", "true"], {"storage_cache_declined": True}),
                            (["surprise_ttl_days", "30"], {"surprise_ttl_days": 30}),
                            (["surprise_excluded_systems", "gba, snes"], {"surprise_excluded_systems": ["gba", "snes"]})):
            with self.subTest(argv=argv):
                code, out, err = self.run_cmd("config", "set", *argv)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual({k: self.settings()[k] for k in saved}, saved)
                self.assertIn(argv[0], out)

    def test_unset_removes_the_setting(self):
        self.write_json("settings.json", {"bucket": "b", "eject": False})
        code, _, err = self.run_cmd("config", "unset", "eject")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.settings(), {"bucket": "b"})

    def test_bad_values_are_refused(self):
        for argv, message in ((["eject", "no"], "true or false"), (["surprise_ttl_days", "0"], "positive"),
                              (["surprise_ttl_days", "x"], "positive"), (["surprise_excluded_systems", "gba,nope"], "nope"),
                              (["bucket", ""], "bucket"), (["eject"], "needs a value")):
            with self.subTest(argv=argv):
                code, _, err = self.run_cmd("config", "set", *argv)
                self.assertEqual(code, 2)
                self.assertIn(message, err)
        self.assertEqual(self.settings(), {})

    def test_unknown_names_list_the_known_ones(self):
        for action in ("set", "unset"):
            with self.subTest(action=action):
                code, _, err = self.run_cmd("config", action, "nope", *(["x"] if action == "set" else []))
                self.assertEqual(code, 2)
                self.assertIn("'nope'", err)
                self.assertIn("surprise_ttl_days", err)
        code, _, err = self.run_cmd("config", "set")
        self.assertEqual(code, 2)
        self.assertIn("`config set` needs a setting's name. Known: bucket", err)

    def test_extra_arguments_are_refused(self):
        for argv in (["show", "bucket"], ["path", "x"], ["unset", "eject", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cmd("config", *argv)[0], 2)

    def test_paths_are_expanded_and_must_be_absolute(self):
        for name in ("root", "mirror"):
            with self.subTest(name=name):
                code, _, err = self.run_cmd("config", "set", name, "~/roms")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(self.settings()[name], os.path.expanduser("~/roms"))
                code, _, err = self.run_cmd("config", "set", name, "roms")
                self.assertEqual(code, 2)
                self.assertIn("roms is not an absolute path: give the whole folder path, e.g. /Volumes/roms", err)
                self.assertEqual(self.settings()[name], os.path.expanduser("~/roms"))

    def test_unset_of_a_missing_setting_says_so(self):
        code, out, _ = self.run_cmd("config", "unset", "eject")
        self.assertEqual(code, 0)
        self.assertIn("eject wasn't set", out)
        self.assertNotIn("Removed", out)

    def test_unset_with_a_value_never_echoes_it(self):
        code, out, err = self.run_cmd("config", "unset", "screenscraper_password", "secret4")
        self.assertEqual(code, 2)
        self.assertNotIn("secret4", out + err)

    def test_dry_run_says_it_cant_preview_the_change(self):
        for action in (["set", "eject", "false"], ["unset", "eject"]):
            with self.subTest(action=action):
                code, _, err = self.run_cmd("config", *action, "-n")
                self.assertEqual(code, 2)
                self.assertIn(f"--dry-run can't preview `config {action[0]}`", err)
                self.assertNotIn("has no effect", err)
        self.assertEqual(self.settings(), {})

    def test_password_is_saved_but_never_shown(self):
        code, out, err = self.run_cmd("config", "set", "screenscraper_password", "p-secret")
        self.assertEqual(code, 0)
        self.assertEqual(self.settings(), {"screenscraper_password": "p-secret"})
        self.assertIn("screenscraper_password", out)
        self.assertNotIn("p-secret", out + err)

    def test_broken_settings_file_is_not_overwritten(self):
        with open(self.path("settings.json"), "w") as f:
            f.write("{not json")
        code, _, err = self.run_cmd("config", "set", "bucket", "b")
        self.assertEqual(code, 3)
        with open(self.path("settings.json")) as f:
            self.assertEqual(f.read(), "{not json")


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
        with mock.patch.object(names, "_scraped", {"fbneo": {"1941j.zip": "1941: Counter Attack (Japan)"}}):
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

    def test_full_keeps_the_game_list_and_off_brings_it_back(self):
        self.run_cmd("games", "add", "gba", "B.zip", "A.zip")
        listed = self.games()["gba"]
        code, out, _ = self.run_cmd("games", "full", "gba", "on")
        self.assertEqual(code, 0)
        self.assertIn("+ gba (full system)", out)
        self.assertEqual(self.games()["gba"], {"full_system": True, "games": listed})  # as cardedit.toggle_full saves it
        self.assertEqual(self.run_cmd("games", "full", "gba", "on")[1].strip(), "Nothing to change.")
        self.assertEqual(self.games()["gba"], {"full_system": True, "games": listed})
        self.assertEqual(json.loads(self.run_cmd("games", "list", "--json")[1]),
                         {"full_systems": ["gba"], "sets": [], "games": []})
        self.run_cmd("games", "full", "gba", "off", "--dry-run")
        self.assertEqual(self.games()["gba"], {"full_system": True, "games": listed})
        code, out, _ = self.run_cmd("games", "full", "gba", "off")
        self.assertEqual(code, 0)
        self.assertIn("- gba (full system)", out)
        self.assertEqual(self.games()["gba"], listed)
        self.assertEqual(self.run_cmd("games", "full", "gba", "off")[1].strip(), "Nothing to change.")
        self.assertEqual(self.games()["gba"], listed)

    def test_import_of_a_full_system_keeps_the_game_list_for_full_off(self):
        self.run_cmd("games", "add", "gba", "A.zip")
        listed = self.games()["gba"]
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("gba/*\n")
        code, out, _ = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("+ gba (full system)", out)
        self.assertEqual(self.games()["gba"], {"full_system": True, "games": listed})
        self.run_cmd("games", "full", "gba", "off")
        self.assertEqual(self.games()["gba"], listed)

    def test_import_adds_a_game_listed_twice_once(self):
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("gba/Foo.zip\ngba/Foo.zip\n")
        code, out, _ = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertEqual([g["bucket"] for g in self.games()["gba"]], ["gba/Foo.zip"])
        self.assertEqual(out.count("+ gba/Foo.zip"), 1)

    def test_export_and_import_carry_collections_and_frontend_names(self):
        from sync_roms import collections
        collections.save_collection({"id": "favs", "name": "Favs", "games": []})
        cards = self.read("cards.json")
        cards["SD"].update(collections=["favs"], frontend_collections=["Favs"], drivers=["a-v1.zip"], boot_logos=["K.png"])
        self.write_json("cards.json", cards)
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(),
                         ["@collections favs", "@frontend_collections Favs", "@drivers a-v1.zip", "@boot_logos K.png"])
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        listing = os.path.join(self.tmp.name, "list.txt")
        with open(listing, "w") as f:
            f.write("@collections favs\n@collections ghost\n@frontend_collections Favs\n@drivers a-v1.zip\n@boot_logos K.png\n@bogus x\n")
        code, _, err = self.run_cmd("games", "import", listing, "-n")
        self.assertEqual((code, self.read("cards.json")["SD"].get("collections")), (0, None))
        code, _, err = self.run_cmd("games", "import", listing)
        self.assertEqual(code, 0)
        self.assertIn("ghost", err)
        self.assertIn("@bogus", err)
        entry = self.read("cards.json")["SD"]
        self.assertEqual((entry["collections"], entry["frontend_collections"], entry["drivers"], entry["boot_logos"]),
                         (["favs"], ["Favs"], ["a-v1.zip"], ["K.png"]))

    def test_export_and_import_carry_the_pico8_zip(self):
        cards = self.read("cards.json")
        cards["SD"]["pico8"] = "pico-8_0.2.7_raspi.zip"
        self.write_json("cards.json", cards)
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(), ["@pico8 pico-8_0.2.7_raspi.zip"])
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("@pico8 pico-8_0.2.6_raspi.zip\n@pico8 pico-8_0.2.7_raspi.zip\n@pico8\n")
        code, _, err = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("@pico8", err)
        self.assertEqual(self.read("cards.json")["SD"]["pico8"], "pico-8_0.2.7_raspi.zip")

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

    def test_allium_surprise_state_round_trips(self):
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "allium", "surprise": True}})
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(), ["@surprise true"])
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "allium"}})
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(), [])
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("@surprise true\n")
        self.assertEqual(self.run_cmd("games", "import", path)[0], 0)
        self.assertIs(self.read("cards.json")["SD"]["surprise"], True)
        with open(path, "w") as f:
            f.write("@surprise false\n")
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
        storage_sets(self, {"mix": {"name": "Mix", "games": [{"title": "A", "system": "gba", "bucket": "gba/A.zip"}]}})
        set_id = "mix"
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

    def _two_cards(self):
        for name in ("A", "B"):
            self.run_cmd("cards", "new", name, "--device", "full", "--layout", "esde")
        cards = self.read("cards.json")
        cards["A"]["games"] = {"gba": [{"title": "X", "bucket": "gba/X.zip"}], "sets": []}
        cards["A"]["collections"] = ["c"]
        with open(self.path("cards.json"), "w") as f:
            json.dump(cards, f)
        return cards

    def test_copy_merges_into_target(self):
        self._two_cards()
        self.assertEqual(self.run_cmd("cards", "copy", "A", "B")[0], 0)
        b = self.read("cards.json")["B"]
        self.assertEqual(b["games"]["gba"], [{"title": "X", "bucket": "gba/X.zip"}])
        self.assertEqual(b["collections"], ["c"])
        self.assertEqual((b["device"], b["layout"]), ("full", "esde"))

    def test_copy_counts_what_dst_syncs_in_a_system_it_turned_off(self):
        cards = self._two_cards()
        cards["A"]["excluded"] = {"gba": ["gba/Y.zip"]}
        storage_sets(self, {"mix": {"name": "Mix", "games": [{"title": "Y", "system": "gba", "bucket": "gba/Y.zip"}]}})
        cards["B"]["games"] = {"sets": ["mix"]}
        cards["B"]["systems_off"] = ["gba"]
        with open(self.path("cards.json"), "w") as f:
            json.dump(cards, f)
        self.assertEqual(self.run_cmd("cards", "copy", "A", "B")[0], 0)
        self.assertNotIn("excluded", self.read("cards.json")["B"])

    def test_copy_dry_run_writes_nothing(self):
        before = self._two_cards()
        self.assertEqual(self.run_cmd("cards", "copy", "A", "B", "--dry-run")[0], 0)
        self.assertEqual(self.read("cards.json"), before)

    def test_copy_errors(self):
        self._two_cards()
        self.assertEqual(self.run_cmd("cards", "copy", "Z", "B")[0], 2)
        self.assertEqual(self.run_cmd("cards", "copy", "A", "Z")[0], 2)
        self.assertEqual(self.run_cmd("cards", "copy", "A", "A")[0], 2)

    def test_set_layout_drops_the_pico8_record(self):
        device = next(d for d in store.repo_json("devices") if "esde" in d["firmwares"])
        zip_name = "pico-8_0.2.7_raspi.zip"
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "pico8": zip_name}})
        self.assertEqual(self.run_cmd("cards", "set", "SD", "--layout", "knulli", "--dry-run")[0], 0)
        self.assertEqual(self.run_cmd("cards", "set", "SD", "--layout", "esde")[0], 0)
        self.assertEqual(self.run_cmd("cards", "set", "SD", "--device", device["id"])[0], 0)
        self.assertEqual(self.read("cards.json")["SD"], {"device": device["id"], "layout": "esde", "pico8": zip_name})
        self.assertEqual(self.run_cmd("cards", "set", "SD", "--device", "full", "--layout", "knulli")[0], 0)
        self.assertEqual(self.read("cards.json")["SD"], {"device": "full", "layout": "knulli"})

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

    def test_check_flags_a_bad_pico8_or_spruce_os_name(self):
        for field in ("pico8", "spruce_os"):
            for bad in (3, ""):
                with self.subTest(field=field, bad=bad):
                    with open(self.path("cards.json"), "w") as f:
                        json.dump({"c": {"device": "full", "layout": "esde", field: bad}}, f)
                    self.assertIn(f"cards.json: c: '{field}' must be a file name", commands.check_data())

    def test_check_flags_a_bad_muos_storage(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"device": "full", "layout": "muos", "muos_storage": "usb"}}, f)
        self.assertIn("cards.json: c: 'muos_storage' must be sd1 or sd2", commands.check_data())

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

    def test_the_keys_of_a_cards_surprises_are_checked(self):
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "surprises": [
            {"system": "gba", "bucket": "gba/A.zip", "title": "A", "files": ["gba/A2.zip", "nes/B.zip"]},
            {"system": "gba", "bucket": "nes/C.zip", "title": "C", "files": "gba/D.zip"}]}})
        self.assertEqual(commands.check_data(lambda system: {"gba/A.zip"}),
                         ["cards.json: c: surprises: 'nes/B.zip' isn't under gba/",
                          "cards.json: c: surprises: nes/C.zip: 'files' must be a list of bucket keys",
                          "cards.json: c: surprises: 'nes/C.zip' isn't under gba/",
                          "cards.json: c: surprises: 'gba/A2.zip' isn't in storage"])


class CardsInstallParserTest(unittest.TestCase):
    def test_parses(self):
        args = commands.build_parser().parse_args(["cards", "install", "TF2", "--dry-run", "--yes"])
        self.assertEqual((args.card, args.dry_run, args.yes), ("TF2", True, True))
        self.assertIs(args.fn, commands.cards_install)
        self.assertIn("install", commands.second_words()["cards"])


class CliTest(unittest.TestCase):
    def test_flags_before_a_commands_folder(self):
        parse = lambda *a: commands.build_parser().parse_args(list(a))  # noqa: E731
        self.assertEqual((parse("diff", "-n", "/x").dir, parse("diff", "-n", "/x").dry_run), ("/x", True))
        self.assertEqual(parse("playlist", "-y", "/Volumes/SD").dir, "/Volumes/SD")
        self.assertEqual(parse("devices", "-y", "rg35xx").device_id, "rg35xx")
        args = parse("diff", "--json", "--system", "gba", "/tmp")
        self.assertEqual((args.dir, args.json, args.system), ("/tmp", True, "gba"))

    def test_command_with_a_stray_directory_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            commands.run(["diff", "-n", "/x", "/y"])
        self.assertEqual(cm.exception.code, 2)

    def test_commands_after_global_flags_route_to_commands_run(self):
        for argv, expect in ((["-y", "check"], ["check", "-y"]), (["-n", "doctor"], ["doctor", "-n"]),
                             (["-y", "games", "list"], ["games", "list", "-y"])):
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", ["sync-roms"] + argv), \
                    mock.patch.object(commands, "run", return_value=0) as run:
                self.assertEqual(cli.sync(), 0)
            run.assert_called_once_with(expect)

    def test_conflicting_or_ignored_flags_exit_2(self):
        parse = lambda *a: cli.check_modes(cli.build_parser().parse_args(list(a)))  # noqa: E731
        for argv in (["--scrape", "--clean-scrapes"], ["--replace"], ["--scrape-review", "-n"], ["--scrape", "-a"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                parse(*argv)
            self.assertEqual(cm.exception.code, 2)
        self.assertEqual(parse("--scrape-art", "--replace"), "--scrape-art")
        for argv in (["edit", "-n"], ["devices", "-a"], ["playlist", "--system", "gba"], ["edit", "--replace"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                commands.run(argv)
            self.assertEqual(cm.exception.code, 2)
        self.assertEqual(commands.build_parser().parse_args(["upload", "--replace"]).replace, True)

    def test_abbreviations_are_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.build_parser().parse_args(["--up"])
        self.assertEqual(cm.exception.code, 2)


class PlainCommands(unittest.TestCase):
    """The plain commands (sync, edit, devices, upload, diff, playlist, prepare, install, mirror) as subcommands."""

    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        os.makedirs(os.path.join(self.tmp, "card"))
        os.makedirs(os.path.join(self.tmp, "saves"))
        self.enterContext(contextlib.chdir(self.tmp))  # relative words ("convert", "./saves") resolve here
        self.enterContext(mock.patch.object(commands, "prepare_storage"))
        self.addCleanup(setattr, ui, "ASSUME_YES", False)

    def run_cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.run(list(argv))

    def fails(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            cli.run(list(argv))
        return cm.exception.code, err.getvalue()

    def test_bare_card_is_sync(self):
        card = os.path.join(self.tmp, "card")
        with mock.patch.object(cli, "sync_card", return_value=0) as sync:
            self.assertEqual(self.run_cli("-n", card), 0)
            self.run_cli()
        self.assertEqual((sync.call_args_list[0].args[0].base_dir, sync.call_args_list[0].args[0].dry_run), (card, True))
        self.assertIsNone(sync.call_args_list[1].args[0].base_dir)

    def test_path_named_like_command_is_sync(self):
        with mock.patch.object(cli, "sync_card", return_value=0) as sync:
            self.run_cli("./saves")
        self.assertEqual(sync.call_args.args[0].base_dir, "./saves")

    def test_prepare_and_install(self):
        from sync_roms import chd, external
        with mock.patch.object(chd, "chd_command", return_value=0) as prepare:
            self.run_cli("prepare", "/x")
        self.assertEqual(prepare.call_args.args[0].dir, "/x")
        with mock.patch.object(external, "install_tools_command", return_value=0) as install:
            self.run_cli("install")
        install.assert_called_once_with()

    def test_removed_names_fail(self):
        with mock.patch.object(cli, "sync_card", side_effect=AssertionError("synced")):
            code, err = self.fails("convert", "/x")
            self.assertEqual(code, 2)
            self.assertIn("convert isn't a command or a folder", err)
            for argv in (["tools", "install"], ["games", "edit"], ["cards", "edit"]):
                with self.subTest(argv=argv):
                    self.assertEqual(self.fails(*argv)[0], 2)

    def test_mirror_forms(self):
        for argv, action, folder in ((["mirror"], None, None), (["mirror", "/m"], None, "/m"),
                                     (["mirror", "use", "/m"], "use", "/m"), (["mirror", "clear"], "clear", None)):
            with self.subTest(argv=argv), mock.patch.object(mirroring, "mirror_command", return_value=0) as mirror:
                self.run_cli(*argv)
                self.assertEqual((mirror.call_args.args[0].action, mirror.call_args.args[0].dir), (action, folder))

    def test_doctor_fix_installs_missing_tools(self):
        from sync_roms import external
        for found, calls in ((None, 1), ("/bin/tool", 0)):
            with self.subTest(found=found), mock.patch.object(runtime, "ROOT", self.tmp), \
                    mock.patch.object(commands, "check_data", lambda: []), \
                    mock.patch.object(external, "find_tool", lambda tool, f=found: f), \
                    mock.patch.object(external, "install_tools_command", return_value=0) as install:
                self.run_cli("doctor", "--fix")
            self.assertEqual(install.call_count, calls)

    def test_global_flags_any_position(self):
        from sync_roms import upload
        for argv in (["upload", "/x", "--root", "/r"], ["--root", "/r", "upload", "/x"]):
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", ["sync-roms", *argv]), \
                    mock.patch.object(usersettings, "apply_settings"), \
                    mock.patch.object(upload, "upload_command", return_value=0) as up:
                self.assertEqual(cli.sync(), 0)
                self.assertEqual(runtime.OVERRIDES["root"], "/r")
                self.assertEqual(up.call_args.args[0].dir, "/x")


class UiTest(unittest.TestCase):
    def test_download_pico8_count_must_be_positive(self):
        parse = commands.build_parser().parse_args
        self.assertEqual(parse(["download", "pico8", "--count", "3"]).count, 3)
        for bad in ("0", "-2", "x"):
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
                parse(["download", "pico8", "--count", bad])
            self.assertIn("positive", err.getvalue())

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
        self.assertEqual(self.run_cmd("cards", "--json"), self.run_cmd("cards", "list", "--json"))
        self.run_cmd("cards", "set", "SD", "--size", "256")
        self.assertEqual(self.read("cards.json")["SD"]["size"], "256 GB")

    def test_list_shows_the_space_the_picks_take(self):
        self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde", "--size", "512gb")
        self.run_cmd("cards", "new", "SD2", "--device", "full", "--layout", "esde")
        self.run_cmd("games", "add", "gba", "A.zip", "B.zip", "--card", "SD")
        store.update_card("SD", games={**store.card_games("SD"), "nes": {"full_system": True}})
        cache = {"gba/": {"gba/A.zip": 1_000_000_000, "gba/B.zip": 400_000_000}, "scrapes/gba/": {},
                 "nes/": {"nes/X.zip": 50_000_000, "nes/Y.zip": 50_000_000}, "scrapes/nes/": {}, "BIOS/": {}}
        with mock.patch.object(inventory, "cached", cache.get):
            rows = {r["name"]: (r["used"], r["sized"], r["full_systems"], r["games"])
                    for r in json.loads(self.run_cmd("cards", "list", "--json")[1])}
            text = self.run_cmd("cards", "list")[1]
        self.assertEqual(rows, {"SD": (1_500_000_000, True, 1, 2), "SD2": (0, True, 0, 0)})
        self.assertIn("1.5 GB / 512 GB", text)
        self.assertEqual(text.splitlines(), ["SD   full  esde  1.5 GB / 512 GB  1 full system   2 games  🎁🎨💖🏆",
                                             "SD2  full  esde     0 B /     ❔  0 full systems  0 games  🎁🎨💖🏆"])
        with mock.patch.object(inventory, "cached", lambda p: None):
            lines = self.run_cmd("cards", "list")[1].splitlines()
        self.assertEqual(lines[0], "SD   full  esde    * / 512 GB  1 full system   2 games  🎁🎨💖🏆")
        self.assertEqual(lines[1], "SD2  full  esde  0 B /     ❔  0 full systems  0 games  🎁🎨💖🏆")
        self.assertIn("* Not sized", lines[3])
        self.assertIn("sync-roms cache update", lines[4])

    def test_list_leaves_an_off_full_system_out_of_the_full_count(self):
        self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")
        store.update_card("SD", games={"nes": {"full_system": True}, "gba": {"full_system": True}}, systems_off=["nes"])
        cache = {"nes/": {"nes/X.zip": 5}, "gba/": {"gba/X.zip": 5}, "scrapes/nes/": {}, "scrapes/gba/": {}, "BIOS/": {}}
        with mock.patch.object(inventory, "cached", cache.get):
            row = json.loads(self.run_cmd("cards", "list", "--json")[1])[0]
        self.assertEqual(row["full_systems"], 1)

    def test_list_shows_theme_and_collections_off(self):
        self.run_cmd("cards", "new", "SD", "--device", "full", "--layout", "esde")
        cards = store.load_cards()
        store.set_card_flag(cards["SD"], "theme", False)
        store.set_card_flag(cards["SD"], "custom_collections", False)
        store.set_card_flag(cards["SD"], "raofflineproxy", False)
        store.write_cards(cards)
        row = json.loads(self.run_cmd("cards", "list", "--json")[1])[0]
        self.assertEqual((row["theme"], row["collections"], row["raofflineproxy"]), (False, False, False))
        self.assertTrue(self.run_cmd("cards", "list")[1].rstrip().endswith("🎁"))

    def make_guest_pair(self):
        self.run_cmd("cards", "new", "Mine", "--device", "full", "--layout", "esde")
        self.run_cmd("cards", "new", "Friend", "--device", "full", "--layout", "esde")
        cards = store.load_cards()
        cards["Friend"]["guest"] = True
        store.write_cards(cards)

    def test_cards_list_hides_guest_cards(self):
        self.make_guest_pair()
        text = self.run_cmd("cards", "list")[1]
        self.assertIn("Mine", text)
        self.assertNotIn("Friend", text)
        self.assertIn("1 guest card hidden", text)
        self.assertIn("--all", text)

    def test_cards_list_all_shows_guest_cards_marked(self):
        self.make_guest_pair()
        text = self.run_cmd("cards", "list", "--all")[1]
        self.assertIn("Mine", text)
        friend = [l for l in text.splitlines() if "Friend" in l]
        self.assertEqual(len(friend), 1)
        self.assertTrue(friend[0].endswith("🎁🎨💖🏆👤"))  # in the badge slots on the right, not by the name
        self.assertTrue(friend[0].startswith("Friend "))
        self.assertNotIn("👤", [l for l in text.splitlines() if "Mine" in l][0])
        self.assertNotIn("hidden", text)

    def test_cards_list_json_has_guest_field(self):
        self.make_guest_pair()
        rows = {r["name"]: r["guest"] for r in json.loads(self.run_cmd("cards", "list", "--all", "--json")[1])}
        self.assertEqual(rows, {"Mine": False, "Friend": True})
        self.assertEqual([r["name"] for r in json.loads(self.run_cmd("cards", "list", "--json")[1])], ["Mine"])

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
            with self.subTest(failures=failures), contextlib.redirect_stderr(io.StringIO()) as out:
                cli.report_failures(failures)
            last = out.getvalue().splitlines()[-1]
            self.assertEqual("sync-roms cache update" in last, cache)
            self.assertEqual("run the same command again" in last, retry)

    def test_failure_hint_for_a_folder_the_card_cannot_open_says_the_file_system_is_damaged(self):
        e = OSError(22, "Invalid argument", "/Volumes/SD/BIOS/neocd")
        with mock.patch.object(downloads.os, "stat", side_effect=OSError(22, "Invalid argument")):
            self.assertEqual(downloads.failure_hint(e), downloads.DAMAGED_HINT)
        with mock.patch.object(downloads.os, "stat"):
            self.assertEqual(downloads.failure_hint(e), "")

    def damaged_summary(self, failures, platform="darwin", diskutil="/usr/sbin/diskutil"):
        info = mock.Mock(returncode=0, stdout=plistlib.dumps({"DeviceIdentifier": "disk5s1"}))
        with mock.patch.object(clean.sys, "platform", platform), \
                mock.patch.object(clean.shutil, "which", return_value=diskutil), \
                mock.patch.object(clean.os.path, "ismount", side_effect=lambda p: p == "/Volumes/SD"), \
                mock.patch.object(clean.subprocess, "run", return_value=info) as run, \
                contextlib.redirect_stderr(io.StringIO()) as out:
            cli.report_failures(failures)
        return out.getvalue(), run

    def test_failure_summary_for_a_damaged_card_names_the_repair_instead_of_a_retry(self):
        damaged = ("BIOS/neocd/000-lo.lo", "[Errno 22] Invalid argument: '/Volumes/SD/BIOS/neocd'" + downloads.DAMAGED_HINT)
        out, run = self.damaged_summary([damaged, damaged])
        self.assertIn("diskutil repairVolume disk5s1", out)
        self.assertIn("delete /Volumes/SD/BIOS/neocd", out)
        self.assertNotIn("run the same command again", out)
        run.assert_called_with(["diskutil", "info", "-plist", "/Volumes/SD"], capture_output=True)
        out, _ = self.damaged_summary([damaged, ("psx/B.chd", "[Errno 5] Input/output error")])
        self.assertIn("diskutil repairVolume disk5s1", out)
        self.assertIn("run the same command again", out)

    def test_failure_summary_for_a_damaged_card_without_diskutil_says_to_check_the_file_system(self):
        damaged = ("BIOS/neocd/000-lo.lo", "[Errno 22] Invalid argument: '/Volumes/SD/BIOS/neocd'" + downloads.DAMAGED_HINT)
        for platform, diskutil in (("linux", None), ("darwin", None)):
            with self.subTest(platform=platform):
                out, run = self.damaged_summary([damaged], platform, diskutil)
                self.assertIn("check it (First Aid, chkdsk or fsck), then sync again", out)
                self.assertNotIn("repairVolume", out)
                run.assert_not_called()

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

    def test_mirror_skips_a_key_that_would_leave_it_with_a_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, ".sync-roms-mirror"), "w").close()
            got = []
            with mock.patch.object(mirroring.store, "load_manifest", return_value={}), \
                    mock.patch.object(mirroring.store, "all_card_names", return_value=[]), \
                    mock.patch.object(mirroring, "mirror_wanted", return_value={"../evil.zip": 3, "gba/New.zip": 3}), \
                    mock.patch.object(mirroring.downloads, "run_downloads", side_effect=lambda jobs, *a: got.extend(jobs) or 0), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(mirroring.refresh_mirror(root), 0)
            self.assertEqual(got, [("gba/New.zip", os.path.join(root, "gba/New.zip"), 3)])
        self.assertIn("\n  ⚠️  skipping unsafe path: '../evil.zip'\n", out.getvalue())

    def test_mirror_lists_the_first_ten_files_it_asks_about_deleting(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, ".sync-roms-mirror"), "w").close()
            os.makedirs(os.path.join(root, "gba"))
            for i in range(12):
                open(os.path.join(root, "gba", f"{i:02}.zip"), "w").close()
            with mock.patch.object(mirroring.store, "load_manifest", return_value={}), \
                    mock.patch.object(mirroring.store, "all_card_names", return_value=[]), \
                    mock.patch.object(mirroring, "mirror_wanted", return_value={}), \
                    mock.patch.object(mirroring.downloads, "run_downloads", return_value=0), \
                    mock.patch.object(mirroring.ui, "confirm", return_value=False), \
                    mock.patch.object(ui, "_COLOR", True), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(mirroring.refresh_mirror(root), 0)
            self.assertEqual(len(os.listdir(os.path.join(root, "gba"))), 12)
        self.assertEqual([line for line in out.getvalue().split("\n") if line.startswith("\x1b[2m")],
                         [f"\x1b[2m     gba/{i:02}.zip\x1b[0m" for i in range(10)] + ["\x1b[2m     … and 2 more\x1b[0m"])


def etag(data):
    return f'"{hashlib.md5(data).hexdigest()}"'


class MirrorThemeUpdateTest(DataDir):
    """A bucket whose cache and mirror hold the theme archive and its commit file, before `themes update`."""
    OLD, NEW = b"a" * 40 + b"\n", b"b" * 40 + b"\n"  # a commit file is always 41 bytes

    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        for name, value in (("ROOT", None), ("BUCKET", "roms"), ("ENDPOINT", None), ("_mirror_root", None)):
            self.enterContext(mock.patch.object(runtime, name, value))
        client = mock.Mock()
        client.get_paginator.return_value.paginate.return_value = [{"Contents": [
            {"Key": themeart.ESDE_ARCHIVE, "Size": 3, "ETag": etag(b"old")},
            {"Key": themeart.ESDE_COMMIT, "Size": 41, "ETag": etag(self.OLD)}]}]
        client.put_object.side_effect = lambda **kw: {"ETag": etag(kw["Body"])}
        self.enterContext(mock.patch.object(s3, "s3_client", return_value=client))
        with contextlib.redirect_stdout(io.StringIO()):
            inventory.update()
        self.mirror = os.path.join(self.tmp.name, "mirror")
        for key, data in ((runtime.MIRROR_MARKER, b""), (themeart.ESDE_ARCHIVE, b"old"), (themeart.ESDE_COMMIT, self.OLD)):
            os.makedirs(os.path.dirname(os.path.join(self.mirror, key)), exist_ok=True)
            with open(os.path.join(self.mirror, key), "wb") as f:
                f.write(data)
        self.storage = {themeart.ESDE_ARCHIVE: b"old", themeart.ESDE_COMMIT: self.OLD}  # what the bucket holds

    def themes_update(self, archive=b"newer", commit=NEW):
        """What `themes update` writes to the bucket."""
        path = os.path.join(self.tmp.name, "theme.tar.gz")
        with open(path, "wb") as f:
            f.write(archive)
        s3.put_file(themeart.ESDE_ARCHIVE, path)
        s3.put_text(themeart.ESDE_COMMIT, commit.decode())
        self.storage = {themeart.ESDE_ARCHIVE: archive, themeart.ESDE_COMMIT: commit}

    def fetched(self, fail=()):
        """The keys a mirror refresh downloads, in the order of its download batches; the keys in fail fail."""
        batches = []

        def run_downloads(jobs, label, icon, base, failures=None):
            batches.append(sorted(k for k, _, _ in jobs))
            for key, path, _ in jobs:
                if key in fail:
                    if failures is not None:
                        failures.append((key, "boom"))
                    continue
                with open(path, "wb") as f:
                    f.write(self.storage[key])
            return sum(k in fail for k, _, _ in jobs)
        with mock.patch.object(mirroring.store, "load_manifest", return_value={"systems": []}), \
                mock.patch.object(mirroring.store, "all_card_names", return_value=[]), \
                mock.patch.object(mirroring.downloads, "run_downloads", side_effect=run_downloads), \
                contextlib.redirect_stdout(io.StringIO()):
            mirroring.refresh_mirror(self.mirror)
        return [b for b in batches if b]

    def stored_commit(self):
        """The commit a card sees, read through the mirror."""
        with mock.patch.object(runtime, "_mirror_root", self.mirror):
            return themeart._stored_commit()

    def test_mirror_fetches_the_archive_then_the_commit_after_themes_update(self):
        self.themes_update()
        self.assertEqual(self.fetched(), [[themeart.ESDE_ARCHIVE], [themeart.ESDE_COMMIT]])
        self.assertEqual(self.stored_commit(), self.NEW.decode().strip())

    def test_mirror_fetches_a_same_size_archive_when_the_commit_changed(self):
        self.themes_update(archive=b"new")
        self.assertEqual(self.fetched(), [[themeart.ESDE_ARCHIVE], [themeart.ESDE_COMMIT]])
        with open(os.path.join(self.mirror, themeart.ESDE_ARCHIVE), "rb") as f:
            self.assertEqual(f.read(), b"new")

    def test_mirror_keeps_the_old_commit_when_the_archive_fails(self):
        self.themes_update()
        self.assertEqual(self.fetched(fail={themeart.ESDE_ARCHIVE}), [[themeart.ESDE_ARCHIVE]])
        self.assertEqual(self.stored_commit(), self.OLD.decode().strip())

    def test_mirror_keeps_a_commit_file_storage_still_has(self):
        self.assertEqual(self.fetched(), [])

    def test_an_unreadable_mirror_copy_of_the_commit_file_counts_as_changed(self):
        unreadable = os.path.join(self.mirror, "unreadable")
        os.makedirs(unreadable)  # opening a folder raises an OSError
        self.assertTrue(mirroring.commit_changed(unreadable))

    def test_a_commit_file_with_an_unknown_or_multipart_etag_counts_as_changed_and_is_fetched(self):
        for tag in (None, '"0123abcd-2"'):
            with self.subTest(tag=tag):
                if tag is None:
                    inventory.current().etags.pop(themeart.ESDE_COMMIT)
                else:
                    inventory.current().etags[themeart.ESDE_COMMIT] = tag
                self.assertEqual(self.fetched(), [[themeart.ESDE_ARCHIVE], [themeart.ESDE_COMMIT]])
                self.assertEqual(self.stored_commit(), self.OLD.decode().strip())


if __name__ == "__main__":
    unittest.main()
