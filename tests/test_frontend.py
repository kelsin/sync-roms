import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardfs, frontend, store, themeart  # noqa: E402

ESDE_SETTINGS = ('<?xml version="1.0"?>\n<bool name="ScrapeRatings" value="true" />\n'
                 '<string name="CollectionSystemsCustom" value="Mine,Old" />\n<string name="Theme" value="x" />\n')
LINE = '<string name="CollectionSystemsCustom" value="Favs" />'


class Names(unittest.TestCase):
    def test_safe_name_drops_what_es_de_rejects(self):
        self.assertEqual(frontend.safe_name(' A*"b,c.d/e:f;g<h>i\\j|k\nl\tm\rn '), "Abcdefghijklmn")

    def test_paths_and_lines(self):
        j = os.path.join
        self.assertEqual(frontend.collection_path("esde", "/c", "Favs"), j("/c", "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertEqual(frontend.collection_path("knulli", "/c", "Favs"),
                         j("/c", "system", "configs", "emulationstation", "collections", "custom-Favs.cfg"))
        self.assertEqual(frontend.settings_path("esde", "/c"), j("/c", "ES-DE", "settings", "es_settings.xml"))
        self.assertEqual(frontend.settings_path("knulli", "/c"), j("/c", "system", "configs", "emulationstation", "es_settings.cfg"))
        self.assertEqual(frontend.collection_line("esde", "gba", "Sub/A.zip"), "%ROMPATH%/gba/Sub/A.zip")
        self.assertEqual(frontend.collection_line("knulli", "gba", "Sub/A.zip"), "./roms/gba/Sub/A.zip")

    def test_emudeck_uses_es_de_on_this_computer(self):
        j = os.path.join
        with tempfile.TemporaryDirectory() as appdata, mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": appdata}):
            self.assertEqual(frontend.esde_dir("emudeck", "/c"), appdata)
            self.assertEqual(frontend.collection_path("emudeck", "/c", "Favs"), j(appdata, "collections", "custom-Favs.cfg"))
            self.assertEqual(frontend.settings_path("emudeck", "/c"), j(appdata, "settings", "es_settings.xml"))
        self.assertEqual(frontend.collection_line("emudeck", "wiiu/roms", "A.wua"), "%ROMPATH%/wiiu/roms/A.wua")
        with mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": ""}):
            self.assertEqual(frontend.esde_dir("emudeck", "/c"), os.path.expanduser("~/ES-DE"))
        self.assertEqual(frontend.esde_dir("esde", "/c"), j("/c", "ES-DE"))
        self.assertEqual(frontend.set_string("", "emudeck", "Theme", "x"), frontend.set_string("", "esde", "Theme", "x"))

    def test_emudeck_problem_says_why_this_computer_s_es_de_does_not_serve_the_card(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as card:
            appdata, roms = os.path.join(tmp, "ES-DE"), os.path.join(card, "Emulation", "roms")
            with mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": appdata}):
                self.assertEqual(frontend.emudeck_problem(card, roms), f"ES-DE isn't set up on this computer (no {appdata})")
                other = (f"ES-DE on this computer ({appdata}) doesn't use this card's ROMs "
                         f"(its ROMDirectory isn't {roms})")
                os.makedirs(os.path.join(appdata, "settings"))
                self.assertEqual(frontend.emudeck_problem(card, roms), other)  # no settings file
                path = frontend.settings_path("emudeck", card)
                for used, problem in (("", other), ("/elsewhere/roms", other), (roms + "/", None), (roms, None)):
                    with open(path, "w") as f:
                        f.write(frontend.set_string("", "emudeck", "ROMDirectory", used) if used else '<?xml version="1.0"?>\n')
                    self.assertEqual(frontend.emudeck_problem(card, roms), problem, used)


class FewerCardIO(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_collection_file_of_another_size_is_not_read(self):
        path = os.path.join(self.dir, "custom-x.cfg")
        with open(path, "w") as f:
            f.write("old\n")
        with mock.patch.object(frontend, "_read", side_effect=AssertionError("read")):
            self.assertFalse(frontend._same(path, "new line\n"))
            self.assertFalse(frontend._same(path + "x", "a"))  # missing
        self.assertTrue(frontend._same(path, "old\n"))
        self.assertFalse(frontend._same(path, "olx\n"))  # same size, other text

    def test_art_file_of_another_size_is_not_read(self):
        path = os.path.join(self.dir, "a.png")
        themeart._put(path, b"12345")
        with mock.patch("builtins.open", side_effect=AssertionError("read")):
            with mock.patch.object(themeart.store, "replace_file") as replace:
                self.assertTrue(themeart._put(path, b"123456"))
        replace.assert_called_once()
        with mock.patch.object(themeart.store, "replace_file") as replace:
            self.assertFalse(themeart._put(path, b"12345"))
        replace.assert_not_called()

    def test_settings_are_read_once_and_written_once_with_both_edits(self):
        path = frontend.settings_path("esde", self.dir)
        plan = frontend.plan_collections("esde", self.dir, {"Fav": ["a"]}, [])
        reads, writes = [], []
        real_replace = store.replace_file
        with mock.patch.object(store, "replace_file", side_effect=lambda p, *a, **k: (writes.append(p), real_replace(p, *a, **k))), \
                mock.patch("builtins.open", side_effect=lambda p, *a, **k: (reads.append(p), open_real(p, *a, **k))[1]):
            with cardfs.caching():
                frontend.apply_collections(plan, "esde", self.dir)
                cardfs.clear()
                themeart._write_settings(path, "esde", {"Theme": themeart.ESDE_COPY})
                themeart.esde_wanted("esde", self.dir)
        self.assertEqual(reads.count(path), 1)
        self.assertEqual(writes.count(path), 1)
        with open_real(path) as f:
            text = f.read()
        self.assertIn("Fav", text)
        self.assertIn(themeart.ESDE_COPY, text)

    def test_unchanged_settings_are_not_written(self):
        path = os.path.join(self.dir, "es_settings.xml")
        with cardfs.caching():
            self.assertTrue(cardfs.write_text(path, "<x/>\n"))
            self.assertFalse(cardfs.write_text(path, "<x/>\n"))
            self.assertFalse(os.path.exists(path))  # written when the sync ends
        self.assertTrue(os.path.exists(path))
        self.assertFalse(cardfs.write_text(path, "<x/>\n"))


open_real = open


class Enabled(unittest.TestCase):
    def test_set_enabled_keeps_other_names_and_the_rest_of_the_file(self):
        self.assertEqual(frontend.set_enabled(ESDE_SETTINGS, "esde", {"Favs"}, {"Old"}),
                         ESDE_SETTINGS.replace('value="Mine,Old"', 'value="Mine,Favs"'))

    def test_a_missing_line_is_added(self):
        text = '<?xml version="1.0"?>\n<string name="Theme" value="x" />\n'
        self.assertEqual(frontend.set_enabled(text, "esde", {"Favs"}, set()), text + LINE + "\n")
        cfg = '<?xml version="1.0"?>\n<config>\n\t<string name="A" value="b" />\n</config>\n'
        self.assertEqual(frontend.set_enabled(cfg, "knulli", {"Favs"}, set()), cfg.replace("</config>", f"\t{LINE}\n</config>"))

    def test_an_empty_file_gets_a_minimal_one(self):
        self.assertEqual(frontend.set_enabled("", "esde", {"Favs"}, set()), f'<?xml version="1.0"?>\n{LINE}\n')
        self.assertEqual(frontend.set_enabled("", "knulli", {"Favs"}, set()), f'<?xml version="1.0"?>\n<config>\n\t{LINE}\n</config>\n')

    def test_names_are_xml_escaped(self):
        text = '<string name="CollectionSystemsCustom" value="A&amp;B" />\n'
        self.assertEqual(frontend.set_enabled(text, "esde", {"R&B"}, set()),
                         '<string name="CollectionSystemsCustom" value="A&amp;B,R&amp;B" />\n')

    def test_apostrophes_and_quotes_in_other_names_survive_untouched(self):
        text = '<string name="CollectionSystemsCustom" value="Kel&apos;s,Say &quot;hi&quot;,A&amp;B" />\n'
        self.assertEqual(frontend.set_enabled(text, "esde", {"Favs"}, set()),
                         text.replace('B"', 'B,Favs"'))


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def test_new_collection_is_written_enabled_and_owned(self):
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, [])
        path = frontend.collection_path("esde", self.base, "Favs")
        self.assertEqual(plan, {"writes": [(path, "%ROMPATH%/gba/A.zip\n")], "deletes": [], "enable": {"Favs"},
                                "disable": set(), "owned": ["Favs"], "warnings": []})
        frontend.apply_collections(plan, "esde", self.base)
        self.assertEqual(self.read(path), "%ROMPATH%/gba/A.zip\n")
        self.assertIn('value="Favs"', self.read(frontend.settings_path("esde", self.base)))

    def test_a_name_clash_with_a_user_made_file_is_skipped_with_a_warning(self):
        path = frontend.collection_path("esde", self.base, "Favs")
        self.put(path, "mine\n")
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, [])
        self.assertEqual((plan["writes"], plan["owned"], plan["enable"]), ([], [], set()))
        self.assertEqual(plan["warnings"], ["ES-DE already has a custom collection Favs that sync-roms didn't write; skipped"])
        frontend.apply_collections(plan, "esde", self.base)
        self.assertEqual(self.read(path), "mine\n")

    def test_an_owned_file_is_rewritten(self):
        path = frontend.collection_path("knulli", self.base, "Favs")
        self.put(path, "edited in the frontend\n")
        plan = frontend.plan_collections("knulli", self.base, {"Favs": ["./roms/gba/A.zip"]}, ["Favs"])
        self.assertEqual(plan["writes"], [(path, "./roms/gba/A.zip\n")])

    def test_an_owned_file_with_the_same_text_is_not_rewritten_but_stays_enabled_and_owned(self):
        path = frontend.collection_path("esde", self.base, "Favs")
        self.put(path, "%ROMPATH%/gba/A.zip\n")
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, ["Favs"])
        self.assertEqual((plan["writes"], plan["enable"], plan["owned"]), ([], {"Favs"}, ["Favs"]))

    def test_an_owned_file_deleted_by_hand_is_written_again(self):
        path = frontend.collection_path("esde", self.base, "Favs")
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, ["Favs"])
        self.assertEqual(plan["writes"], [(path, "%ROMPATH%/gba/A.zip\n")])

    def test_apply_says_whether_it_changed_the_settings_file(self):
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, [])
        self.assertTrue(frontend.apply_collections(plan, "esde", self.base))
        self.assertFalse(frontend.apply_collections(plan, "esde", self.base))

    def test_a_renamed_or_removed_collection_deletes_the_old_file_and_unlists_it(self):
        old = frontend.collection_path("esde", self.base, "Old")
        self.put(old, "x\n")
        self.put(frontend.settings_path("esde", self.base), ESDE_SETTINGS)
        plan = frontend.plan_collections("esde", self.base, {"New": ["%ROMPATH%/gba/A.zip"]}, ["Old"])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([old], {"Old"}, ["New"]))
        frontend.apply_collections(plan, "esde", self.base)
        self.assertFalse(os.path.exists(old))
        self.assertIn('value="Mine,New"', self.read(frontend.settings_path("esde", self.base)))

    def test_an_owned_name_that_is_not_a_safe_name_is_ignored_with_one_warning(self):
        outside = os.path.join(self.base, "x.cfg")
        self.put(outside, "keep\n")
        plan = frontend.plan_collections("esde", self.base, {}, ["../../x", "../../x"])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([], set(), []))
        self.assertEqual(len(plan["warnings"]), 1)
        self.assertTrue(os.path.exists(outside))

    def test_an_empty_owned_name_deletes_nothing(self):
        blank = frontend.collection_path("esde", self.base, "")
        self.put(blank, "keep\n")
        plan = frontend.plan_collections("esde", self.base, {}, [""])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([], set(), []))
        frontend.apply_collections(plan, "esde", self.base)
        self.assertTrue(os.path.exists(blank))

    def test_a_delete_that_already_vanished_is_fine(self):
        gone = frontend.collection_path("esde", self.base, "Old")
        plan = {"writes": [], "deletes": [gone], "enable": set(), "disable": {"Old"}, "owned": [], "warnings": []}
        frontend.apply_collections(plan, "esde", self.base)

    def test_nothing_wanted_or_owned_touches_nothing(self):
        frontend.apply_collections(frontend.plan_collections("esde", self.base, {}, []), "esde", self.base)
        self.assertEqual(os.listdir(self.base), [])


class Wanted(unittest.TestCase):
    def test_names_that_sanitise_alike_share_one_file_and_an_empty_one_is_dropped(self):
        gba = {"bucket": "gba", "folders": {"esde": "gba"}}
        a = {"name": "A.B", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"}]}
        b = {"name": "AB", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"},
                                     {"title": "Y", "system": "gba", "bucket": "gba/Y.zip"}]}
        dots = {"name": "...", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"}]}
        got = frontend.wanted_collections("esde", [a, b, dots], [gba], lambda s, rel: True)
        self.assertEqual(got, {"AB": ["%ROMPATH%/gba/X.zip", "%ROMPATH%/gba/Y.zip"]})

    def test_lines_are_the_synced_games_on_systems_the_card_syncs(self):
        favs = {"name": "Fa.vs", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/Sub/A.zip"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]},
            {"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"}]}
        empty = {"name": "Empty", "games": [{"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"}]}
        gba, psx = {"bucket": "gba", "folders": {"esde": "gba"}}, {"bucket": "psx", "folders": {"esde": "psx"}}
        on_card = lambda s, rel: rel != "Gone.zip"  # noqa: E731
        self.assertEqual(frontend.wanted_collections("esde", [favs, empty], [gba], on_card), {"Favs": ["%ROMPATH%/gba/Sub/A.zip"]})
        self.assertEqual(frontend.wanted_collections("esde", [favs], [gba, psx], on_card),
                         {"Favs": ["%ROMPATH%/gba/Sub/A.zip", "%ROMPATH%/psx/FF7.m3u"]})


class NextUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def test_path_and_line(self):
        self.assertEqual(frontend.collection_path("nextui", self.base, "Favs"),
                         os.path.join(self.base, "Collections", "Favs.txt"))
        self.assertEqual(frontend.collection_line("nextui", "Game Boy Advance (GBA)", "Sub/A.zip"),
                         "/Roms/Game Boy Advance (GBA)/Sub/A.zip")
        self.assertIn("nextui", frontend.FRONTEND_LAYOUTS)

    def test_wanted_drops_games_without_a_folder_or_card_copy_and_empty_collections(self):
        gba = {"bucket": "gba", "folders": {"nextui": "Game Boy Advance (GBA)"}}
        none = {"bucket": "ngp", "folders": {"nextui": None}}
        favs = {"name": "Favs", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
            {"title": "G", "system": "gba", "bucket": "gba/Gone.zip"},
            {"title": "N", "system": "ngp", "bucket": "ngp/N.zip"}]}
        only_none = {"name": "None", "games": [{"title": "N", "system": "ngp", "bucket": "ngp/N.zip"}]}
        got = frontend.wanted_collections("nextui", [favs, only_none], [gba, none], lambda s, rel: rel != "Gone.zip")
        self.assertEqual(got, {"Favs": ["/Roms/Game Boy Advance (GBA)/A.zip"]})

    def test_wanted_lists_a_folder_game_by_its_path_in_the_folder(self):
        psx = {"bucket": "psx", "folders": {"nextui": "PlayStation (PS)", "esde": "psx"}}
        favs = {"name": "Favs", "games": [{"title": "FF7", "system": "psx", "bucket": "psx/FF7 (USA).m3u"}]}
        folders = {"psx/FF7 (USA).m3u": "FF7 (USA)"}
        seen = []
        got = frontend.wanted_collections("nextui", [favs], [psx], lambda s, rel: seen.append(rel) or True, folders)
        self.assertEqual(got, {"Favs": ["/Roms/PlayStation (PS)/FF7 (USA)/FF7 (USA).m3u"]})
        self.assertEqual(seen, ["FF7 (USA)/FF7 (USA).m3u"])
        self.assertEqual(frontend.wanted_collections("esde", [favs], [psx], lambda s, rel: True),
                         {"Favs": ["%ROMPATH%/psx/FF7 (USA).m3u"]})

    def test_plan_deletes_only_owned_and_apply_touches_no_settings(self):
        mine = frontend.collection_path("nextui", self.base, "Old")
        theirs = frontend.collection_path("nextui", self.base, "Theirs")
        os.makedirs(os.path.dirname(mine))
        for path in (mine, theirs):
            with open(path, "w") as f:
                f.write("/Roms/x/y.zip\n")
        plan = frontend.plan_collections("nextui", self.base, {"New": ["/Roms/g/a.zip"]}, ["Old"])
        self.assertEqual(plan["deletes"], [mine])
        self.assertFalse(frontend.apply_collections(plan, "nextui", self.base))
        self.assertFalse(os.path.exists(mine))
        self.assertTrue(os.path.exists(theirs))
        with open(frontend.collection_path("nextui", self.base, "New")) as f:
            self.assertEqual(f.read(), "/Roms/g/a.zip\n")
        self.assertEqual(sorted(os.listdir(self.base)), ["Collections"])

    def test_describe_prints_no_settings_lines(self):
        plan = frontend.plan_collections("nextui", self.base, {"New": ["/Roms/g/a.zip"]}, [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            frontend.describe_collections(plan, "nextui")
        self.assertIn("would write New.txt", out.getvalue())
        self.assertNotIn("enable", out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.base, "Collections")))


if __name__ == "__main__":
    unittest.main()
