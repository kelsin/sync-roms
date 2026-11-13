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

    def offered(self, module, folders, cache):
        seen = []

        def fake(title, labels, **k):
            if title.startswith("✏️  Add games"):
                seen.extend(labels)
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
            self.assertEqual(self.offered(module, lambda: {"gba", "psx", "gb"}, cache), ["Game Boy Advance", "Game Boy"])

    def test_add_games_goes_by_the_cache_when_storage_cannot_be_reached(self):
        def down():
            raise OSError("down")
        self.assertEqual(self.offered(collectionedit, down, {"psx/": {}}), ["Game Boy Advance", "Game Boy", "Saturn"])


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

    def test_p_narrows_the_add_games_list_to_past_surprises(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 0, None])  # add from a system, Game Boy Advance, back
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels)))
                steps = [("p", 0), ("c", 0), kw["initial"]]
                return steps[len(lists) - 1]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
            collectionedit.edit_one(collection, SYSTEMS, lambda bucket: keys if bucket == "gba" else set())
        self.assertEqual(lists[1][1], ["Ruby.zip"])
        self.assertIn("🎁 past surprises only (c shows all)", lists[1][0])
        self.assertEqual(len(lists[2][1]), 2)

    def test_s_and_m_narrow_the_add_games_list_to_a_set_and_to_metadata(self):
        from sync_roms import cardedit
        collection = {"name": "Favs", "games": []}
        picks = iter([1, 0, None])
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels)))
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
        self.assertIn("📦 Zeldas only", lists[1][0])
        self.assertEqual(lists[2][1], ["Zelda.zip"])
        self.assertEqual(len(lists[3][1]), 3)


class Editor(DataDir):
    def run_editor(self, picks, asks=(), confirm=True, edit_one=None):
        picks, confirms = iter(picks), []
        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=list(asks)), \
                mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text) or confirm), \
                mock.patch.object(edit, "note") as note, \
                mock.patch.object(collectionedit, "edit_one", edit_one or (lambda c, systems, keys_of: c["games"].append(dict(RUBY)))), \
                mock.patch("subprocess.run") as run:
            code = collectionedit.edit_collections()
        run.assert_not_called()  # no git, no gh
        return code, confirms, note

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

    def test_an_empty_collection_is_refused_on_done(self):
        _, _, note = self.run_editor([0, 2, 3], asks=["Empty", ""], edit_one=lambda c, s, k: None, confirm=True)
        self.assertIn("Empty has no games", note.call_args_list[0][0][0])
        self.assertFalse(os.path.exists(self.path("collections")))


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
