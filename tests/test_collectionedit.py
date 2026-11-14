import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import cli, collectionedit, commands, collections, edit, inventory, listedit, picker, setedit, store, themeart, ui  # noqa: E402

SYSTEMS = [{"name": "Game Boy Advance", "bucket": "gba"}, {"name": "PlayStation", "bucket": "psx"}]
DISCS = {"psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd", "psx/Crash.chd"}
RUBY = {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}


class Shared(unittest.TestCase):
    def test_set_editor_uses_the_shared_helpers(self):
        for name in ("view", "stocked", "insert_game", "reconcile", "recategorize", "ask_category", "game_label", "add_from_set"):
            self.assertIs(getattr(setedit, name), getattr(listedit, name))


class Stocked(unittest.TestCase):
    SYSTEMS = SYSTEMS + [{"name": "Game Boy", "bucket": "gb"}, {"name": "Saturn", "bucket": "saturn"}]

    def offered(self, module, folders, cache, extras=None):
        seen = []

        def fake(title, labels, **k):
            if title.startswith("✏️  Add games"):
                seen.extend(labels)
                if extras is not None:
                    extras.extend(k.get("extras") or [[]] * len(labels))
                return None
            return 1 if not seen else None  # add from a system, then back

        with mock.patch.object(inventory, "folders", side_effect=folders), \
                mock.patch.object(inventory, "cached", lambda p: cache.get(p)), \
                mock.patch.object(picker, "filter_list", fake):
            module.edit_one({"name": "Favs", "games": []}, self.SYSTEMS, lambda bucket: set())
        return seen

    def test_add_games_hides_systems_with_a_missing_or_empty_folder(self):
        cache = {"gba/": {"Ruby.zip": 1}, "psx/": {}, "gb/": {"Tetris.zip": 1}}
        for module in (collectionedit, setedit):
            # psx is cached as empty, saturn has no folder; gb has a folder and games
            self.assertEqual(self.offered(module, lambda: {"gba", "psx", "gb"}, cache), ["Game Boy", "Game Boy Advance"])

    def test_add_games_shows_each_systems_file_count_from_the_cache(self):
        cache = {"gba/": {"gba/Ruby.zip": 1, "gba/Emerald.zip": 2, "gba/hacks/": 0}, "gb/": {"gb/Tetris.zip": 1}}
        for module in (collectionedit, setedit):
            extras = []
            self.assertEqual(self.offered(module, lambda: {"gba", "gb"}, cache, extras), ["Game Boy", "Game Boy Advance"])
            self.assertEqual(extras, [[("  1 file", "dim")], [("  2 files", "dim")]], module.__name__)

    def test_renaming_a_set_changes_the_next_menu_title(self):
        titles, picks = [], iter([4, None])  # Rename, then back
        game_set = {"id": "x", "name": "Old", "games": []}

        def fake(title, labels, **k):
            titles.append(title)
            return next(picks)

        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(setedit.ui, "ask", side_effect=["New", ""]):
            setedit.edit_one(game_set, self.SYSTEMS, lambda bucket: set())
        self.assertEqual(titles, ["✏️  📦 Old (Esc = back)", "✏️  📦 New (Esc = back)"])

    def test_add_games_counts_nothing_without_a_cache(self):
        extras = []
        with mock.patch.object(inventory, "files", side_effect=AssertionError("listed a folder")):
            self.offered(setedit, lambda: {"gba", "psx", "gb", "saturn"}, {}, extras)
        self.assertEqual(extras, [[], [], [], []])  # every system listed (no cache to tell), none counted

    def test_add_games_lists_systems_by_company_then_name_like_the_card_editor(self):
        systems = [{"name": "Game Boy Advance", "bucket": "gba", "company": "Nintendo"},
                   {"name": "PlayStation", "bucket": "psx", "company": "Sony"},
                   {"name": "Mega Drive", "bucket": "md", "company": "Sega"},
                   {"name": "Game Boy", "bucket": "gb", "company": "Nintendo"}]
        for module in (collectionedit, setedit):
            with mock.patch.object(self, "SYSTEMS", systems):
                self.assertEqual(self.offered(module, lambda: {"gba", "psx", "md", "gb"}, {}),
                                 ["Game Boy", "Game Boy Advance", "Mega Drive", "PlayStation"], module.__name__)

    def test_add_games_goes_by_the_cache_when_storage_cannot_be_reached(self):
        def down():
            raise OSError("down")
        self.assertEqual(self.offered(collectionedit, down, {"psx/": {}}), ["Game Boy", "Game Boy Advance", "Saturn"])


class Discs(unittest.TestCase):
    def test_a_multi_disc_game_is_one_row_and_keeps_its_discs(self):
        entry = {"bucket": "psx", "name": "PlayStation", "full_system": False, "games": []}
        self.assertEqual([r[1] for r in collectionedit.system_rows(entry, DISCS)], ["psx/Crash.chd", "psx/FF7.m3u"])
        games = [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u"}, {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}]
        collectionedit.fold_discs(games, DISCS)
        self.assertEqual(games[0]["files"], ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"])
        self.assertNotIn("files", games[1])

    def test_adding_a_multi_disc_game_from_a_system_stores_its_discs(self):
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 1, None])  # add from a system, PlayStation, back
        rows = []

        def toggle(title, shown_rows, **k):  # switch on the FF7 row
            rows.extend(r[1] for r in shown_rows)
            s, key, title, _ = shown_rows[1]
            s["games"].append({"bucket": key, "title": title})

        with mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(edit, "toggle_games", toggle), mock.patch.object(ui, "ask", return_value=""):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: DISCS if bucket == "psx" else set())
        self.assertEqual(rows, ["psx/Crash.chd", "psx/FF7.m3u"])
        self.assertEqual(collection["games"], [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
                                                "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}])


    def test_adding_from_a_set_spans_systems_and_keeps_discs(self):
        collection = {"name": "Favs", "games": [dict(RUBY)]}
        game_set = {"name": "Mix", "games": [
            {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]},
            {"title": "Odd", "system": "nes", "bucket": "nes/Odd.zip"}]}
        picks = iter([2, 0, None])  # add from a set, Mix, back
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append(list(labels))
                return [False, True]  # Ruby off, FF7 on
            return next(picks)

        keys = {"gba": {"gba/Ruby.zip"}, "psx": DISCS}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value="RPG"), \
                mock.patch("builtins.print"), mock.patch.object(store, "load_sets", return_value=[game_set]):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: keys.get(bucket, set()))
        self.assertEqual(lists, [["Game Boy Advance — Ruby", "PlayStation — FF7"]])
        self.assertEqual(collection["games"], [{"title": "FF7", "category": "RPG", "system": "psx",
                                                "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}])

    def test_the_add_games_list_keeps_its_place_when_a_key_lists_the_same_games(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 0, None])  # add from a system, Game Boy Advance, back
        place = {"row": 1, "query": "z", "view_mode": 2, "top": 0}
        seen = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                seen.append({k: kw["session"].get(k) for k in place})
                kw["session"].update(place)
                return ("p", 1) if len(seen) == 1 else kw["initial"]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(surprise, "past_keys", return_value=set()), mock.patch.object(edit, "note"):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: keys if bucket == "gba" else set())
        self.assertEqual(seen, [dict.fromkeys(place), place])

    def test_p_narrows_the_add_games_list_to_past_surprises(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 0, None])  # add from a system, Game Boy Advance, back
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels), kw.get("filters", "")))
                steps = [("p", 0), ("c", 0), kw["initial"]]
                return steps[len(lists) - 1]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: keys if bucket == "gba" else set())
        self.assertEqual(lists[1][1], ["Ruby.zip"])
        self.assertEqual("🎁 past surprises only (c shows all)", lists[1][2])
        self.assertNotIn("past surprises", lists[1][0])
        self.assertEqual(len(lists[2][1]), 2)

    def test_s_and_m_narrow_the_add_games_list_to_a_set_and_to_metadata(self):
        from sync_roms import cardedit
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 0, None])
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels), kw.get("filters", "")))
                return [("s", 0), ("m", 0), ("c", 0), kw["initial"]][len(lists) - 1]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip", "gba/Sonic.zip"}
        game_set = {"id": "x", "name": "Zeldas", "games": []}

        def pick_meta(system, meta, filters, keys_for):
            filters["genre"] = "RPG"

        class Meta:
            def __init__(self, bucket):
                pass

            def get(self):
                return {"gba/Zelda.zip": {"genre": "RPG"}}

        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(store, "load_sets", return_value=[game_set]), \
                mock.patch.object(cardedit, "pick_set", return_value=game_set), \
                mock.patch.object(cardedit, "set_filter", return_value={"gba/Zelda.zip", "gba/Ruby.zip"}), \
                mock.patch.object(cardedit, "pick_meta", pick_meta), mock.patch.object(cardedit, "Metadata", Meta), \
                mock.patch.object(cardedit.metafilter, "matches", lambda m, w: m.get("genre") == w["genre"]):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: keys if bucket == "gba" else set())
        self.assertEqual(lists[1][1], ["Ruby.zip", "Zelda.zip"])
        self.assertIn("📦 Zeldas only", lists[1][2])
        self.assertEqual(lists[2][1], ["Zelda.zip"])
        self.assertEqual(len(lists[3][1]), 3)


class Editor(DataDir):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(edit, "note")  # what the editor says at its end
        self.note = patch.start()
        self.addCleanup(patch.stop)

    def run_editor(self, picks, asks=(), confirm=True, edit_one=None):
        picks, confirms = iter(picks), []

        def answer(value):  # KeyboardInterrupt in picks or as confirm is Ctrl-C there
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value
        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: answer(next(picks))), \
                mock.patch.object(ui, "ask", side_effect=list(asks)), \
                mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text) or answer(confirm)), \
                mock.patch.object(collectionedit, "edit_one", edit_one or (lambda c, systems, keys_of: c["games"].append(dict(RUBY)))), \
                mock.patch("subprocess.run") as run:
            code = collectionedit.edit_collections()
        run.assert_not_called()  # no git, no gh
        return code, confirms, self.note

    def test_new_collection_is_saved_on_done(self):
        code, _, _ = self.run_editor([0, 2], asks=["Favs", "my faves"])  # ➕ New, then (one collection) ✅ Done
        self.assertEqual(code, 0)
        self.assertEqual(self.read("collections/favs.json"), {"name": "Favs", "description": "my faves", "games": [RUBY]})

    def test_quit_discards_everything(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.run_editor([(edit.DELETE_KEY, 0), 2])  # delete, then (no collections left) 🚪 Quit, confirmed
        self.assertTrue(os.path.exists(self.path("collections/favs.json")))

    def test_deleting_a_collection_cards_use_confirms_and_removes_it_from_them(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.write_json("cards.json", {"a": {"collections": ["favs", "x"]}, "b": {"collections": ["favs"]}, "c": {}})
        _, confirms, _ = self.run_editor([(edit.DELETE_KEY, 0), 1])  # delete, then ✅ Done
        self.assertIn("a, b", confirms[0])
        self.assertFalse(os.path.exists(self.path("collections/favs.json")))
        self.assertEqual(self.read("cards.json"), {"a": {"collections": ["x"]}, "b": {"collections": []}, "c": {}})

    def test_declined_delete_keeps_it(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.run_editor([(edit.DELETE_KEY, 0), 2], confirm=False)  # still one collection: index 2 is ✅ Done
        self.assertTrue(os.path.exists(self.path("collections/favs.json")))

    def test_an_empty_collection_is_saved_on_done(self):
        self.run_editor([0, 2], asks=["Empty", ""], edit_one=lambda c, s, k: None)
        self.assertEqual(self.read("collections/empty.json"), {"name": "Empty", "games": []})

    def test_ctrl_c_asks_and_saves_the_changes(self):
        collections.save_collection({"id": "old", "name": "Old", "games": [RUBY]})
        self.write_json("cards.json", {"a": {"collections": ["old"]}})
        with mock.patch("builtins.print"), self.assertRaises(KeyboardInterrupt):
            self.run_editor([(edit.DELETE_KEY, 0), 0, KeyboardInterrupt], asks=["Favs", "my faves"])  # delete Old, ➕ New, Ctrl-C
        self.assertEqual(self.read("collections/favs.json"), {"name": "Favs", "description": "my faves", "games": [RUBY]})
        self.assertFalse(os.path.exists(self.path("collections/old.json")))
        self.assertEqual(self.read("cards.json"), {"a": {"collections": []}})
        self.assertIn("Saved to", str(self.note.call_args_list))

    def test_ctrl_c_saves_an_empty_collection(self):
        with mock.patch("builtins.print"), self.assertRaises(KeyboardInterrupt):
            self.run_editor([0, KeyboardInterrupt], asks=["Empty", ""], edit_one=lambda c, s, k: None)
        self.assertEqual(self.read("collections/empty.json"), {"name": "Empty", "games": []})
        self.assertIn("Saved to", str(self.note.call_args_list))

    def test_a_second_ctrl_c_at_the_question_discards(self):
        with mock.patch("builtins.print") as out, self.assertRaises(KeyboardInterrupt):
            self.run_editor([0, KeyboardInterrupt], asks=["Favs", ""], confirm=KeyboardInterrupt)
        self.assertFalse(os.path.exists(self.path("collections")))
        self.assertIn("Not saved", str(out.call_args_list))

    def interrupted(self, games, picks, lists, sets=(), ask=None):
        """Open collection favs (holding games) in the real collection editor; picks answer the single-choice lists,
        lists holds per toggle list (labels to switch, what it then does: KeyboardInterrupt, a hotkey or None for Enter);
        ask is ui.ask's side_effect. Ctrl-C's save question is answered yes. Returns the confirms asked and the ui.ask mock."""
        collections.save_collection({"id": "favs", "name": "Favs", "games": games})
        picks, lists, confirms = iter(picks), iter(lists), []
        keys = {"gba": {"gba/Ruby.zip", "gba/Zelda.zip"}, "psx": DISCS}

        def fake(title, labels, **kw):
            if not kw.get("multi"):
                return next(picks)
            flip, then = next(lists)
            kw["session"]["sel"] = [on != (label in flip) for label, on in zip(labels, kw["session"]["sel"])]
            if then is KeyboardInterrupt:
                raise KeyboardInterrupt
            return (then, 0) if then else kw["session"]["sel"]

        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(store, "folder_keys", lambda bucket: keys.get(bucket, set())), \
                mock.patch.object(store, "load_sets", return_value=list(sets)), \
                mock.patch.object(inventory, "folders", return_value={"gba", "psx"}), \
                mock.patch.object(inventory, "cached", return_value=None), \
                mock.patch.object(collectionedit.cardedit, "Metadata"), \
                mock.patch.object(ui, "ask", side_effect=ask) as ask, \
                mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text) or True), \
                mock.patch("builtins.print"), self.assertRaises(KeyboardInterrupt):
            collectionedit.edit_collections()
        return confirms, ask

    def test_ctrl_c_keeps_the_open_lists_removals(self):
        zelda = {"title": "Zelda", "system": "gba", "bucket": "gba/Zelda.zip"}
        confirms, _ = self.interrupted([RUBY, zelda], [0, 0], [({"Game Boy Advance — Ruby"}, KeyboardInterrupt)])
        self.assertEqual(len(confirms), 1)
        self.assertEqual(self.read("collections/favs.json")["games"], [zelda])

    def test_ctrl_c_keeps_the_add_games_lists_toggles_with_no_category(self):
        # PlayStation: switch Crash on and press c, then switch FF7 on and Ctrl-C
        confirms, ask = self.interrupted([RUBY], [0, 1, 1], [({"Crash.chd"}, "c"), ({"FF7.m3u"}, KeyboardInterrupt)])
        ask.assert_not_called()  # no category question
        self.assertEqual(len(confirms), 1)
        self.assertEqual(self.read("collections/favs.json")["games"], [
            RUBY, {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}])

    def test_ctrl_c_keeps_the_add_from_a_set_lists_toggles_with_no_category(self):
        game_set = {"id": "mix", "name": "Mix", "games": [
            dict(RUBY), {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}]}
        confirms, ask = self.interrupted([RUBY], [0, 2, 0], [({"Game Boy Advance — Ruby", "PlayStation — FF7"}, KeyboardInterrupt)],
                                         sets=[game_set])
        ask.assert_not_called()
        self.assertEqual(len(confirms), 1)
        self.assertEqual(self.read("collections/favs.json")["games"], [
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}])

    def test_ctrl_c_in_a_list_with_nothing_toggled_asks_nothing(self):
        for picks in ([0, 0], [0, 1, 1], [0, 2, 0]):
            with self.subTest(picks=picks):
                game_set = {"id": "mix", "name": "Mix", "games": [dict(RUBY)]}
                confirms, _ = self.interrupted([RUBY], picks, [(set(), KeyboardInterrupt)], sets=[game_set])
                self.assertEqual(confirms, [])
                self.assertEqual(self.read("collections/favs.json")["games"], [RUBY])

    def test_ctrl_c_in_the_set_or_meta_picker_keeps_the_games_lists_toggles(self):
        ff7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}
        crash = {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}
        for key, picker_name in (("s", "pick_set"), ("m", "pick_meta")):
            with self.subTest(key=key), mock.patch.object(collectionedit.cardedit, picker_name, side_effect=KeyboardInterrupt):
                # PlayStation: Crash on, c; FF7 on, then the key whose picker gets Ctrl-C
                confirms, ask = self.interrupted([RUBY], [0, 1, 1], [({"Crash.chd"}, "c"), ({"FF7.m3u"}, key)])
                ask.assert_not_called()
                self.assertEqual(len(confirms), 1)
                self.assertEqual(self.read("collections/favs.json")["games"], [RUBY, crash, ff7])
            with self.subTest(key=key, toggled=False), \
                    mock.patch.object(collectionedit.cardedit, picker_name, side_effect=KeyboardInterrupt):
                confirms, _ = self.interrupted([RUBY], [0, 1, 1], [(set(), key)])
                self.assertEqual(confirms, [])
                self.assertEqual(self.read("collections/favs.json")["games"], [RUBY])

    def test_ctrl_c_at_the_category_question_keeps_the_games_with_no_category(self):
        game_set = {"id": "mix", "name": "Mix", "games": [
            dict(RUBY), {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}]}
        for picks, flip, ff7 in (([0, 1, 1], {"FF7.m3u"}, ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]),
                                 ([0, 2, 0], {"PlayStation — FF7"}, ["psx/FF7 (Disc 1).chd"])):
            with self.subTest(picks=picks):  # FF7 on, Enter, Ctrl-C at the category question
                confirms, ask = self.interrupted([RUBY], picks, [(flip, None)], sets=[game_set], ask=KeyboardInterrupt)
                ask.assert_called_once()
                self.assertEqual(len(confirms), 1)
                self.assertEqual(self.read("collections/favs.json")["games"],
                                 [RUBY, {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ff7}])

    def test_ctrl_c_without_changes_asks_nothing(self):
        confirms = []
        with mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text)), self.assertRaises(KeyboardInterrupt), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", side_effect=KeyboardInterrupt):
            collectionedit.edit_collections()
        self.assertEqual(confirms, [])


class Wiring(unittest.TestCase):
    def test_command_help_and_completion(self):
        with mock.patch.object(collectionedit, "edit_collections", return_value=0) as run:
            self.assertEqual(commands.run(["collections", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["collections"], ["edit"])
        self.assertEqual(cli.SUBCOMMANDS["collections"][0], "edit")
        self.assertIn("sync-roms collections edit", cli.TOPICS["collections"])


class ArtPicker(unittest.TestCase):
    def pick(self, collection, index):
        with mock.patch.object(picker, "filter_list", lambda *a, **k: index):
            collectionedit.pick_art(collection)
        return collection

    def test_picking_art_sets_it_and_none_clears_it(self):
        first = next(iter(themeart.art_choices()))
        self.assertEqual(self.pick({"name": "Favs"}, 1)["art"], first)
        self.assertNotIn("art", self.pick({"name": "Favs", "art": first}, 0))
        self.assertEqual(self.pick({"name": "Favs", "art": first}, None)["art"], first)  # Esc keeps it
        self.assertEqual(collectionedit.art_label(first), themeart.art_choices()[first])
        self.assertEqual(collectionedit.art_label(None), "none")


if __name__ == "__main__":
    unittest.main()
