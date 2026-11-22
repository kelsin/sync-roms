import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from xml.dom import minidom

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardfs, downloads, frontend, store, themeart  # noqa: E402

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

    def test_a_setting_name_is_xml_escaped(self):
        name = 'subset.A & <B> "C".system-view-artwork'
        text = frontend.set_string("", "knulli", name, "custom")
        entry, = minidom.parseString(text).getElementsByTagName("string")
        self.assertEqual((entry.getAttribute("name"), entry.getAttribute("value")), (name, "custom"))
        self.assertEqual(frontend.get_string(text, name), "custom")

    def test_setting_an_escaped_name_again_replaces_its_entry(self):
        name = 'subset.A & <B> "C".system-view-artwork'
        text = frontend.set_string(frontend.set_string("", "knulli", name, "custom"), "knulli", name, "theme")
        self.assertEqual(len(minidom.parseString(text).getElementsByTagName("string")), 1)
        self.assertEqual(frontend.get_string(text, name), "theme")

    def test_an_unescaped_name_from_an_older_sync_is_replaced(self):
        name = "subset.Mario & Sonic.system-view-artwork"
        old = f'<config>\n\t<string name="{name}" value="custom" />\n</config>\n'
        self.assertEqual(frontend.get_string(old, name), "custom")
        self.assertEqual(frontend.set_string(old, "knulli", name, "custom"), old.replace("&", "&amp;"))

    def test_removing_a_setting_finds_its_name_escaped_or_not(self):
        name = "subset.Mario & Sonic.system-view-artwork"
        kept = '\t<string name="subset.Mario.system-view-artwork" value="custom" />\n'
        for written in (name.replace("&", "&amp;"), name):  # as sync-roms writes it now, and as it did before
            text = f'<config>\n{kept}\t<string name="{written}" value="custom" />\n</config>\n'
            self.assertEqual(frontend.remove_string(text, name), f'<config>\n{kept}</config>\n', written)
        self.assertEqual(frontend.remove_string(f'<config>\n{kept}</config>\n', name), f'<config>\n{kept}</config>\n')

    def test_a_name_escaped_the_way_emulationstation_writes_it_is_replaced(self):
        name = "subset.Kel's R&B.system-logos"  # ES escapes the & and leaves the apostrophe
        text = '<config>\n\t<string name="subset.Kel\'s R&amp;B.system-logos" value="custom" />\n</config>\n'
        self.assertEqual(frontend.get_string(text, name), "custom")
        self.assertEqual(frontend.set_string(text, "knulli", name, "theme"),
                         text.replace("'", "&apos;").replace('"custom"', '"theme"'))


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


class Rocknix(unittest.TestCase):
    """ROCKNIX's EmulationStation reads custom collections from internal storage only: sync stages them in the card's
    ROM folder, and an install script in Ports copies them there."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "card")
        self.es = os.path.join(self.tmp.name, "storage", ".config", "emulationstation")
        self.script = os.path.join(self.base, "roms", "ports", "Install Collections.sh")

    def stage(self, wanted, owned=()):
        plan = frontend.plan_collections("rocknix", self.base, wanted, list(owned))
        return plan, frontend.apply_collections(plan, "rocknix", self.base)

    def run_script(self):
        """Run the card's install script as ROCKNIX would (bash, from Ports), with ES's folder at self.es."""
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        if not os.path.exists(os.path.join(bin_dir, "python3")):
            os.symlink(sys.executable, os.path.join(bin_dir, "python3"))
        env = {"PATH": bin_dir, "SYNC_ROMS_ES_DIR": self.es, "HOME": self.tmp.name}
        return subprocess.run([shutil.which("bash"), self.script], env=env, capture_output=True, text=True,
                              check=True).stdout

    def es_file(self, *rel):
        with open(os.path.join(self.es, *rel), encoding="utf-8") as f:
            return f.read()

    def write_settings(self, body):
        os.makedirs(self.es, exist_ok=True)
        with open(os.path.join(self.es, "es_settings.cfg"), "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0"?>\n<config>\n{body}</config>\n')

    def test_path_and_line(self):
        self.assertIn("rocknix", frontend.FRONTEND_LAYOUTS)
        self.assertEqual(frontend.collection_path("rocknix", self.base, "Favs"),
                         os.path.join(self.base, "roms", ".sync-roms-collections", "custom-Favs.cfg"))
        self.assertEqual(frontend.collection_line("rocknix", "snes", "Sub/A.sfc"), "/storage/roms/snes/Sub/A.sfc")

    def test_wanted_lines_use_the_roms_mount(self):
        snes = {"bucket": "snes", "folders": {"rocknix": "snes"}}
        favs = {"name": "Favs", "games": [{"title": "A", "system": "snes", "bucket": "snes/A.sfc"}]}
        self.assertEqual(frontend.wanted_collections("rocknix", [favs], [snes], lambda s, rel: True),
                         {"Favs": ["/storage/roms/snes/A.sfc"]})

    def test_apply_stages_the_files_and_writes_the_install_script_once(self):
        plan, changed = self.stage({"Favs": ["/storage/roms/snes/A.sfc"]})
        self.assertTrue(changed)
        self.assertEqual(plan["owned"], ["Favs"])
        with open(frontend.collection_path("rocknix", self.base, "Favs")) as f:
            self.assertEqual(f.read(), "/storage/roms/snes/A.sfc\n")
        self.assertTrue(os.access(self.script, os.X_OK))
        with open(self.script) as f:
            text = f.read()
        self.assertTrue(text.startswith("#!/bin/bash\n"))
        self.assertNotIn(self.base, text)
        self.assertNotIn("games-external", text)
        self.assertEqual(os.listdir(self.base), ["roms"])  # no ES settings on the card
        self.assertFalse(self.stage({"Favs": ["/storage/roms/snes/A.sfc"]}, ["Favs"])[1])  # nothing new the second time
        ports = os.path.dirname(self.script)  # the Ports system's ROM folder: the script is never a ROM to delete
        keep = downloads.layout_files("rocknix", {"bucket": "ports"})
        self.assertEqual(downloads.find_extras(ports, [], keep=keep), [])
        self.assertFalse(downloads.has_local_files(ports, ignore=keep))
        self.assertEqual(downloads.layout_files("knulli", {"bucket": "ports"}), ())
        self.assertEqual(downloads.layout_files("rocknix", {"bucket": "snes"}), ())
        self.assertEqual(downloads.find_extras(ports, []), [self.script])  # any other folder offers it for deletion

    def test_the_script_is_removed_when_the_card_has_no_collections(self):
        self.stage({"Favs": ["/storage/roms/snes/A.sfc"]})
        os.remove(frontend.collection_path("rocknix", self.base, "Favs"))
        self.assertTrue(self.stage({})[1])
        self.assertFalse(os.path.exists(self.script))

    def test_the_script_stays_while_removed_collections_wait_to_be_uninstalled(self):
        self.stage({"Old": ["/storage/roms/snes/A.sfc"]})
        plan, _ = self.stage({}, ["Old"])
        self.assertEqual(plan["deletes"], [frontend.collection_path("rocknix", self.base, "Old")])
        self.assertTrue(os.path.exists(self.script))

    def test_describe_says_to_run_the_script(self):
        plan = frontend.plan_collections("rocknix", self.base, {"Favs": ["/storage/roms/snes/A.sfc"]}, [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            frontend.describe_collections(plan, "rocknix")
        self.assertIn("would write custom-Favs.cfg", out.getvalue())
        self.assertIn("Install Collections", out.getvalue())
        self.assertNotIn("es_settings", out.getvalue())
        self.assertFalse(os.path.exists(self.base))

    def test_the_script_installs_and_enables_the_collections(self):
        odd = "Rock 'n' Roll & Co"
        self.stage({"Favs": ["/storage/roms/snes/A.sfc"], odd: ["/storage/roms/gba/B (USA).gba"]})
        out = self.run_script()
        self.assertEqual(self.es_file("collections", "custom-Favs.cfg"), "/storage/roms/snes/A.sfc\n")
        self.assertEqual(self.es_file("collections", f"custom-{odd}.cfg"), "/storage/roms/gba/B (USA).gba\n")
        settings = self.es_file("es_settings.cfg")
        self.assertIn('<string name="CollectionSystemsCustom" value="Favs,Rock \'n\' Roll &amp; Co" />', settings)
        self.assertNotIn("subset.", settings)  # no art on the card
        self.assertIn("Restart EmulationStation", out)  # no systemd here to restart it
        self.assertTrue(os.path.exists(self.script))

    def test_the_script_keeps_what_it_did_not_install_and_removes_what_it_did(self):
        self.stage({"Old": ["/storage/roms/snes/A.sfc"], "Mine": ["/storage/roms/snes/A.sfc"]})
        os.makedirs(os.path.join(self.es, "collections"))
        with open(os.path.join(self.es, "collections", "custom-Mine.cfg"), "w") as f:
            f.write("./roms/nes/x.nes\n")
        self.write_settings('\t<bool name="X" value="true" />\n\t<string name="CollectionSystemsCustom" value="Mine" />\n')
        self.assertIn("Mine", self.run_script())  # skipped: EmulationStation's own collection of that name
        self.assertEqual(self.es_file("collections", "custom-Mine.cfg"), "./roms/nes/x.nes\n")
        self.assertEqual(frontend.get_string(self.es_file("es_settings.cfg"), "CollectionSystemsCustom"), "Mine,Old")
        self.stage({}, ["Old", "Mine"])
        self.run_script()
        self.assertFalse(os.path.exists(os.path.join(self.es, "collections", "custom-Old.cfg")))
        self.assertEqual(self.es_file("collections", "custom-Mine.cfg"), "./roms/nes/x.nes\n")
        settings = self.es_file("es_settings.cfg")
        self.assertEqual(frontend.get_string(settings, "CollectionSystemsCustom"), "Mine")
        self.assertIn('<bool name="X" value="true" />', settings)
        self.assertFalse(os.path.exists(self.script))  # nothing left to install: it removes itself

    def test_the_script_turns_on_the_art_on_the_card_for_art_book_next(self):
        self.stage({"Favs": ["/storage/roms/snes/A.sfc"], "東方": ["/storage/roms/snes/A.sfc"]})
        with mock.patch("sync_roms.ui.warn"):
            self.assertTrue(themeart.install("rocknix", self.base, {"Favs": "surprise", "東方": "shmups"}))
        self.run_script()
        settings = self.es_file("es_settings.cfg")
        for name, value in (("subset.Favs.system-view-artwork", "custom"), ("subset.Favs.system-logos", "custom"),
                            ("subset.東方.system-view-artwork", "custom"), ("subset.distribution", "rocknix"),
                            ("UseCustomCollectionsSystemEx", "false")):
            self.assertEqual(frontend.get_string(settings, name), value, name)
        self.assertIsNone(frontend.get_string(settings, "subset.東方.system-logos"))  # no logo: the theme shows the name

    def test_the_script_turns_off_the_art_sync_took_off_the_card(self):
        games = ["/storage/roms/snes/A.sfc"]
        self.stage({"Favs": games, "Old": games, "Plain": games})
        themeart.install("rocknix", self.base, {"Favs": "surprise", "Old": "rpg", "Plain": "horror"})
        self.run_script()
        self.write_settings(self.es_file("es_settings.cfg").split("<config>\n")[1].split("</config>")[0]
                            + '\t<string name="subset.Mine.system-view-artwork" value="custom" />\n')
        self.stage({"Favs": games, "Plain": games}, ["Favs", "Old", "Plain"])  # Old is gone, Plain lost its art
        themeart.install("rocknix", self.base, {"Favs": "surprise"})
        self.run_script()
        settings = self.es_file("es_settings.cfg")
        for name in ("subset.Old.system-view-artwork", "subset.Old.system-logos", "subset.Plain.system-view-artwork",
                     "subset.Plain.system-logos"):
            self.assertIsNone(frontend.get_string(settings, name), name)
        for name in ("subset.Favs.system-view-artwork", "subset.Favs.system-logos", "subset.Mine.system-view-artwork"):
            self.assertEqual(frontend.get_string(settings, name), "custom", name)
        self.assertEqual(frontend.get_string(settings, "CollectionSystemsCustom"), "Favs,Plain")
        self.assertTrue(settings.endswith("</config>\n"))

    def test_the_script_leaves_another_theme_and_choices_already_made_alone(self):
        self.stage({"Favs": ["/storage/roms/snes/A.sfc"]})
        themeart.install("rocknix", self.base, {"Favs": "surprise"})
        self.write_settings('\t<string name="ThemeSet" value="es-theme-carbon" />\n')
        self.run_script()
        self.assertNotIn("subset.", self.es_file("es_settings.cfg"))
        self.write_settings('\t<string name="UseCustomCollectionsSystemEx" value="true" />\n'
                            '\t<string name="subset.distribution" value="batocera" />\n')
        self.run_script()
        settings = self.es_file("es_settings.cfg")
        self.assertEqual(frontend.get_string(settings, "UseCustomCollectionsSystemEx"), "true")
        self.assertEqual(frontend.get_string(settings, "subset.distribution"), "batocera")
        self.assertEqual(frontend.get_string(settings, "subset.Favs.system-view-artwork"), "custom")


if __name__ == "__main__":
    unittest.main()
