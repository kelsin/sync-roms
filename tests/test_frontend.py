import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import frontend  # noqa: E402

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

    def test_a_renamed_or_removed_collection_deletes_the_old_file_and_unlists_it(self):
        old = frontend.collection_path("esde", self.base, "Old")
        self.put(old, "x\n")
        self.put(frontend.settings_path("esde", self.base), ESDE_SETTINGS)
        plan = frontend.plan_collections("esde", self.base, {"New": ["%ROMPATH%/gba/A.zip"]}, ["Old"])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([old], {"Old"}, ["New"]))
        frontend.apply_collections(plan, "esde", self.base)
        self.assertFalse(os.path.exists(old))
        self.assertIn('value="Mine,New"', self.read(frontend.settings_path("esde", self.base)))

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


if __name__ == "__main__":
    unittest.main()
