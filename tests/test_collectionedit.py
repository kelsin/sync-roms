import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir, storage_tags  # noqa: E402
from sync_roms import cli, collectionedit, commands, collections, edit, inventory, listedit, picker, store, tags, tagui, themeart, ui  # noqa: E402

SYSTEMS = [{"name": "Game Boy Advance", "bucket": "gba"}, {"name": "PlayStation", "bucket": "psx"}]
DISCS = {"psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd", "psx/Crash.chd"}
ALL = "🌐 All systems"
RUBY = {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}


def tag_games(test, games, defs=None):
    """A Mix tag (🔀, or the tags defs) on games ({bucket key: extra files}), as the run's loaded tags."""
    test.addCleanup(tags._set, tags._empty())
    tags._set(tags.parse(json.dumps({
        "tags": {"mix": {"name": "Mix", "emoji": "🔀"}} if defs is None else defs,
        "games": {k: {"tags": ["mix"], **({"files": files} if files else {})} for k, files in games.items()}})))


def add_from_system(collection, keys_of, toggle=None):
    """The collection editor's add games from a system, without the editor around it."""
    listedit.add_from_system(collection, SYSTEMS, listedit.view(collection, SYSTEMS), keys_of, "💖 Favs", toggle=toggle)


class MenusKeepTheCursor(unittest.TestCase):
    def cursors(self, run, *picks):
        """run() with filter_list answering picks in turn; the cursor each call was opened on."""
        answers, seen = iter(picks), []

        def fake(title, labels, **k):
            seen.append(k.get("cursor"))
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            run()
        return seen

    def test_the_sets_and_collections_menu_reopens_on_the_row_just_used(self):
        working = {x: {"name": x, "games": [RUBY]} for x in "abc"}
        opened = []
        state = {"review": False}
        with mock.patch.object(edit, "note"):
            seen = self.cursors(lambda: listedit.edit_menu("set", working, working, state, lambda g: "", lambda g: None,
                                                           lambda x: "", None, opened.append, None, "?"),
                                2, 1, None)
        self.assertEqual(seen, [0, 2, 1])
        self.assertEqual(len(opened), 2)


class SetsReview(unittest.TestCase):
    def test_esc_at_the_save_review_means_keep_editing(self):
        before = {"a": {"name": "A", "games": [RUBY]}}
        working = {"a": {"name": "A", "games": []}}
        asked = []

        def choose(question, letters, default, legend="", **k):
            asked.append(k)
            return "d"
        with mock.patch.object(picker, "filter_list", side_effect=[None]), mock.patch.object(ui, "choose", side_effect=choose), \
                mock.patch.object(edit, "note"), mock.patch("builtins.print"):
            listedit.edit_menu("set", before, working, {"review": False}, lambda g: "", lambda g: None, lambda x: "", None,
                               lambda item: None, None, "?", empty_ok=True)
        self.assertEqual(asked, [{"esc": "e"}])


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
            return None

        with mock.patch.object(inventory, "folders", side_effect=folders), \
                mock.patch.object(inventory, "cached", lambda p: cache.get(p)), \
                mock.patch.object(picker, "filter_list", fake):
            listedit.add_from_system({"name": "Favs", "games": []}, self.SYSTEMS, listedit.view({"games": []}, self.SYSTEMS),
                                     lambda bucket: set(), "💖 Favs")
        return seen

    def test_add_games_hides_systems_with_a_missing_or_empty_folder(self):
        cache = {"gba/": {"Ruby.zip": 1}, "psx/": {}, "gb/": {"Tetris.zip": 1}}
        for module in (collectionedit,):
            # psx is cached as empty, saturn has no folder; gb has a folder and games
            self.assertEqual(self.offered(module, lambda: {"gba", "psx", "gb"}, cache), [ALL, "Game Boy", "Game Boy Advance"])

    def test_add_games_shows_each_systems_file_count_from_the_cache(self):
        cache = {"gba/": {"gba/Ruby.zip": 1, "gba/Emerald.zip": 2, "gba/hacks/": 0}, "gb/": {"gb/Tetris.zip": 1}}
        for module in (collectionedit,):
            extras = []
            self.assertEqual(self.offered(module, lambda: {"gba", "gb"}, cache, extras), [ALL, "Game Boy", "Game Boy Advance"])
            self.assertEqual(extras, [[], [("  1 file", "dim")], [("  2 files", "dim")]], module.__name__)

    def test_add_games_counts_nothing_without_a_cache(self):
        extras = []
        with mock.patch.object(inventory, "files", side_effect=AssertionError("listed a folder")):
            self.offered(collectionedit, lambda: {"gba", "psx", "gb", "saturn"}, {}, extras)
        self.assertEqual(extras, [[], [], [], [], []])  # every system listed (no cache to tell), none counted

    def test_add_games_lists_systems_by_company_then_name_like_the_card_editor(self):
        systems = [{"name": "Game Boy Advance", "bucket": "gba", "company": "Nintendo"},
                   {"name": "PlayStation", "bucket": "psx", "company": "Sony"},
                   {"name": "Mega Drive", "bucket": "md", "company": "Sega"},
                   {"name": "Game Boy", "bucket": "gb", "company": "Nintendo"}]
        for module in (collectionedit,):
            with mock.patch.object(self, "SYSTEMS", systems):
                self.assertEqual(self.offered(module, lambda: {"gba", "psx", "md", "gb"}, {}),
                                 [ALL, "Game Boy", "Game Boy Advance", "Mega Drive", "PlayStation"], module.__name__)

    def test_add_games_goes_by_the_cache_when_storage_cannot_be_reached(self):
        def down():
            raise OSError("down")
        self.assertEqual(self.offered(collectionedit, down, {"psx/": {}}), [ALL, "Game Boy", "Game Boy Advance", "Saturn"])


class Discs(unittest.TestCase):
    def test_a_multi_disc_game_is_one_row_and_keeps_its_discs(self):
        entry = {"bucket": "psx", "name": "PlayStation", "full_system": False, "games": []}
        self.assertEqual([r[1] for r in listedit.system_rows(entry, DISCS)], ["psx/Crash.chd", "psx/FF7.m3u"])
        games = [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u"}, {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}]
        listedit.fold_discs(games, DISCS)
        self.assertEqual(games[0]["files"], ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"])
        self.assertNotIn("files", games[1])

    def test_adding_a_multi_disc_game_from_a_system_stores_its_discs(self):
        collection = {"name": "Favs", "games": []}
        picks = iter([2])  # PlayStation, after All systems
        rows = []

        def toggle(title, shown_rows, **k):  # switch on the FF7 row
            rows.extend(r[1] for r in shown_rows)
            s, key, title, _ = shown_rows[1]
            s["games"].append({"bucket": key, "title": title})

        with mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(edit, "toggle_games", toggle), mock.patch.object(ui, "ask", return_value=""):
            add_from_system(collection, lambda bucket: DISCS if bucket == "psx" else set())
        self.assertEqual(rows, ["psx/Crash.chd", "psx/FF7.m3u"])
        self.assertEqual(collection["games"], [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
                                                "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}])

    def test_adding_from_a_tag_spans_systems_and_keeps_discs(self):
        collection = {"name": "Favs", "games": [dict(RUBY)]}
        tag_games(self, {"gba/Ruby.zip": None, "psx/FF7.m3u": ["psx/FF7 (Disc 1).chd"], "nes/Odd.zip": None})
        picks = iter([0])  # Mix
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append(list(labels))
                return [False, True]  # Ruby off, FF7 on
            return next(picks)

        keys = {"gba": {"gba/Ruby.zip"}, "psx": DISCS}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask") as ask, \
                mock.patch("builtins.print"):
            listedit.add_from_tag(collection, listedit.view(collection, SYSTEMS), lambda bucket: keys.get(bucket, set()), "💖 Favs")
        ask.assert_not_called()  # collections have no categories
        self.assertEqual(lists, [["Game Boy Advance — Ruby", "PlayStation — FF7"]])
        self.assertEqual(collection["games"], [{"title": "FF7", "system": "psx",
                                                "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}])

    def test_the_add_games_list_keeps_its_place_when_a_key_lists_the_same_games(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1])  # Game Boy Advance, after All systems
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
            add_from_system(collection, lambda bucket: keys if bucket == "gba" else set(), toggle=collectionedit.toggle_filtered)
        self.assertEqual(seen, [dict.fromkeys(place), place])

    def test_a_note_typed_on_a_game_just_switched_on_is_saved(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1])  # Game Boy Advance, after All systems
        said = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                if not said:  # Ruby on, then a filter key: the list opens again
                    kw["session"]["sel"] = [True, False]
                    said.append(None)
                    return ("c", 0)
                said.append(kw["on_note"](0, "the good one"))
                return kw["initial"]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(surprise, "past_keys", return_value=set()), mock.patch.object(edit, "note"):
            add_from_system(collection, lambda bucket: keys if bucket == "gba" else set(), toggle=collectionedit.toggle_filtered)
        self.assertEqual(said, [None, "Note saved"])
        self.assertEqual(collection["games"], [{"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip",
                                                "note": "the good one"}])

    def test_p_narrows_the_add_games_list_to_past_surprises(self):
        from sync_roms import surprise
        collection = {"name": "Favs", "games": []}
        picks = iter([1])  # Game Boy Advance, after All systems
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels), kw.get("filters", ""), kw.get("hint"), kw.get("key_help")))
                steps = [("p", 0), ("c", 0), kw["initial"]]
                return steps[len(lists) - 1]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
            add_from_system(collection, lambda bucket: keys if bucket == "gba" else set(), toggle=collectionedit.toggle_filtered)
        self.assertEqual(lists[1][1], ["Ruby.zip"])
        self.assertEqual("🎁 past surprises only · 1 of 2 shown (c clear filters)", lists[1][2])
        self.assertIn("c clear", lists[0][3])
        self.assertEqual([k for k, _ in lists[0][4]], ["s", "m", "p", "t", "T", "c"])  # what ? lists
        self.assertNotIn("past surprises", lists[1][0])
        self.assertEqual(len(lists[2][1]), 2)

    def test_s_and_m_narrow_the_add_games_list_by_tags_and_to_metadata(self):
        from sync_roms import cardedit
        collection = {"name": "Favs", "games": []}
        tag_games(self, {"gba/Zelda.zip": None, "gba/Ruby.zip": None})
        picks = iter([1, 0, None])  # Game Boy Advance, Mix required, tags done
        lists = []

        def fake(title, labels, **kw):
            if kw.get("multi"):
                lists.append((title, list(labels), kw.get("filters", "")))
                return [("s", 0), ("m", 0), ("c", 0), kw["initial"]][len(lists) - 1]
            return next(picks)

        keys = {"gba/Ruby.zip", "gba/Zelda.zip", "gba/Sonic.zip"}

        def pick_meta(system, meta, filters, keys_for):
            filters["genre"] = "RPG"

        class Meta:
            def __init__(self, bucket):
                pass

            def get(self):
                return {"gba/Zelda.zip": {"genre": "RPG"}}

        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", return_value=""), \
                mock.patch.object(cardedit, "pick_meta", pick_meta), mock.patch.object(cardedit, "Metadata", Meta), \
                mock.patch.object(cardedit.metafilter, "matches", lambda m, w: m.get("genre") == w["genre"]):
            add_from_system(collection, lambda bucket: keys if bucket == "gba" else set(), toggle=collectionedit.toggle_filtered)
        self.assertEqual(lists[1][1], ["Ruby.zip", "Zelda.zip"])
        self.assertIn("✅ 🔀 Mix", lists[1][2])
        self.assertEqual(lists[2][1], ["Zelda.zip"])
        self.assertEqual(len(lists[3][1]), 3)


class GamesFirst(unittest.TestCase):
    OLD = {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip", "note": "the good one"}
    FF7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}

    def run_editor(self, collection, script, keys_of=lambda b: {"gba/Ruby.zip", "gba/Zelda.zip", "psx/FF7.m3u"}):
        calls = []

        def toggle(title, rows, **k):
            calls.append({"title": title, "keys": [r[1] for r in rows], "ons": {r[1] for r in rows if r[1] in
                          {g["bucket"] for r in rows for g in r[0]["games"]}}, **k})
            return script[len(calls) - 1](rows)
        with mock.patch.object(edit, "toggle_games", toggle), \
                mock.patch.object(collectionedit, "settings_menu"), \
                mock.patch.object(picker, "filter_list", side_effect=AssertionError("menu")):
            collectionedit.edit_one(collection, SYSTEMS, keys_of)
        return calls

    @staticmethod
    def off(key, then):
        def step(rows):
            for s, k, _, _ in rows:
                if k == key:
                    s["games"] = [g for g in s["games"] if g["bucket"] != k]
            return then
        return step

    @staticmethod
    def on(key, then):
        def step(rows):
            for s, k, title, _ in rows:
                if k == key:
                    s["games"].append({"bucket": k, "title": title})
            return then
        return step

    def test_opening_a_collection_lists_its_games_without_a_menu(self):
        collection = {"name": "Favs", "description": "my best", "games": [dict(self.OLD)]}
        calls = self.run_editor(collection, [lambda rows: None])
        self.assertEqual(calls[0]["keys"], ["gba/Ruby.zip"])
        for part in ("Favs", "my best", "art: none"):
            self.assertIn(part, calls[0]["title"])
        self.assertEqual(calls[0]["hotkeys"], ("A", "+", "S"))  # s and c: the sticky tag filter's own, in edit.toggle_games
        self.assertIs(calls[0]["tag_filter"], True)
        self.assertIn("A add games", calls[0]["hint"])
        self.assertIn(("A / +", "add games"), calls[0]["key_help"])
        self.assertNotIn("+", calls[0]["hint"])

    def test_a_game_switched_off_stays_listed_after_a_hotkey(self):
        collection = {"name": "Favs", "games": [dict(self.OLD), dict(self.FF7)]}
        calls = self.run_editor(collection, [self.off("gba/Ruby.zip", "S"), lambda rows: None])
        self.assertEqual(len(calls), 2)
        self.assertIn("gba/Ruby.zip", calls[1]["keys"])
        self.assertNotIn("gba/Ruby.zip", calls[1]["ons"])
        self.assertEqual(collection["games"], [self.FF7])

    def test_switching_a_removed_game_back_on_restores_its_note_and_discs(self):
        for entry in (self.OLD, self.FF7):
            collection = {"name": "Favs", "games": [dict(entry)]}
            self.run_editor(collection, [self.off(entry["bucket"], "S"), self.on(entry["bucket"], "S"), lambda rows: None])
            self.assertEqual(collection["games"], [entry])

    def run_add(self, collection, key, script, picks, keys_of=lambda b: {"gba/Ruby.zip", "gba/Zelda.zip", "psx/FF7.m3u"}):
        """Open the editor, press key on the games list, answer the system list with picks (None = Esc) and script the toggle
        lists after it; returns the system lists' options and the games lists shown."""
        options, lists, answers = [], [], iter(picks)
        steps = iter(script)

        def toggle(title, rows, **k):
            lists.append([r[1] for r in rows])
            return next(steps)(rows)

        def pick(title, labels, **k):
            options.append(labels)
            return next(answers)
        with mock.patch.object(edit, "toggle_games", toggle), mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(collectionedit.cardedit, "Metadata"), mock.patch.object(inventory, "folders", return_value={"gba", "psx"}), \
                mock.patch.object(inventory, "cached", return_value=None):
            collectionedit.edit_one(collection, SYSTEMS, keys_of)
        return options, lists

    def test_a_opens_the_system_list_with_all_systems_first(self):
        for key in ("A", "+"):
            with self.subTest(key=key):
                options, _ = self.run_add({"name": "Favs", "games": [dict(self.OLD)]}, key,
                                          [lambda rows: key, lambda rows: None], [None])
                self.assertEqual(options[0][0], listedit.ALL_SYSTEMS)

    def test_games_added_with_a_appear_in_the_list_on_return(self):
        for key in ("A", "+"):
            with self.subTest(key=key):
                collection = {"name": "Favs", "games": [dict(self.OLD)]}
                _, lists = self.run_add(collection, key, [lambda rows: key, self.on("gba/Zelda.zip", None), lambda rows: None], [0])
                self.assertIn("gba/Zelda.zip", lists[-1])
                self.assertEqual([g["bucket"] for g in collection["games"]], ["gba/Ruby.zip", "gba/Zelda.zip"])

    def test_re_adding_a_switched_off_game_from_the_a_list_keeps_its_note(self):
        collection = {"name": "Favs", "games": [dict(self.OLD), dict(self.FF7)]}
        self.run_add(collection, "A", [self.off("gba/Ruby.zip", "A"), self.on("gba/Ruby.zip", None), lambda rows: None], [0])
        self.assertEqual(collection["games"], [self.FF7, self.OLD])

    def test_games_are_kept_sorted_by_name_not_by_position(self):
        zelda = {"title": "Zelda", "system": "gba", "bucket": "gba/Zelda.zip"}
        collection = {"name": "Favs", "games": [dict(zelda), dict(self.FF7), dict(self.OLD)]}
        self.run_editor(collection, [self.off("gba/Ruby.zip", "S"), self.on("gba/Ruby.zip", None)])
        self.assertEqual([g["title"] for g in collection["games"]], ["FF7", "Ruby", "Zelda"])

    def test_ordered_sorts_by_title_then_system(self):
        games = [{"title": "The Zed", "system": "psx", "bucket": "psx/z"}, {"title": "Alpha", "system": "psx", "bucket": "psx/a"},
                 {"title": "Alpha", "system": "gba", "bucket": "gba/a"}]
        self.assertEqual([g["bucket"] for g in collectionedit.ordered(games, SYSTEMS)], ["gba/a", "psx/a", "psx/z"])

    def test_a_with_a_tag_filter_set_lists_only_its_games_in_all_systems_with_a_on(self):
        """What "Add games matching the current tag filter" did: A, All systems, `a` adds every game the filter shows."""
        tag_games(self, {"gba/Zelda.zip": None, "psx/FF7.m3u": None})
        tagui.FILTER.required = {"mix"}
        collection = {"name": "Favs", "games": [dict(self.OLD)]}
        seen = []

        def inner(title, rows, hotkeys, hint, place, filters, key_help, select_all, notes):
            seen.append(([r[1] for r in rows], select_all))
            if len(seen) == 1:
                return "A", None
            if len(seen) == 2:  # All systems: every shown game switched on, as `a` does
                for s, k, t, _ in rows:
                    s["games"].append({"bucket": k, "title": t})
            return None, None
        with mock.patch.object(edit, "_toggle_games", inner), mock.patch.object(picker, "filter_list", return_value=0), \
                mock.patch.object(inventory, "folders", return_value={"gba", "psx"}), \
                mock.patch.object(inventory, "cached", return_value=None):
            collectionedit.edit_one(collection, SYSTEMS, lambda b: {k for k in ("gba/Ruby.zip", "gba/Zelda.zip", "psx/FF7.m3u")
                                                                    if k.startswith(f"{b}/")})
        self.assertEqual(seen[0][0], [])  # Ruby isn't tagged: the collection's own list is filtered too
        self.assertEqual(seen[1], (["psx/FF7.m3u", "gba/Zelda.zip"], True))
        self.assertEqual([g["bucket"] for g in collection["games"]], ["psx/FF7.m3u", "gba/Ruby.zip", "gba/Zelda.zip"])

    def test_esc_in_the_system_list_returns_to_the_games_list_unchanged(self):
        collection = {"name": "Favs", "games": [dict(self.OLD)]}
        _, lists = self.run_add(collection, "A", [lambda rows: "A", lambda rows: None], [None])
        self.assertEqual(lists[0], lists[1])
        self.assertEqual(collection["games"], [self.OLD])

    def test_a_from_an_empty_collection_menu_opens_the_system_list(self):
        seen = []

        def pick(title, labels, **k):
            seen.append(labels)
            return 0 if len(seen) == 1 else None
        with mock.patch.object(picker, "filter_list", pick), mock.patch.object(inventory, "folders", return_value={"gba"}), \
                mock.patch.object(inventory, "cached", return_value=None):
            collectionedit.edit_one({"name": "Favs", "games": []}, SYSTEMS, lambda b: set())
        self.assertEqual(seen[1][0], listedit.ALL_SYSTEMS)

    def test_an_empty_collection_offers_add_and_settings(self):
        seen = []
        with mock.patch.object(picker, "filter_list", lambda title, labels, **k: seen.append(labels) or None):
            collectionedit.edit_one({"name": "Favs", "games": []}, SYSTEMS, lambda b: set())
        self.assertEqual(seen, [["Add games", "Settings"]])

    def test_header_omits_an_empty_description(self):
        self.assertEqual(collectionedit.header({"name": "Favs", "description": "", "games": []}).split(" ", 1)[1],
                         "Favs  ·  art: none")


class SettingsMenu(unittest.TestCase):
    def run_menu(self, collection, picks, answers=(), others=()):
        seen = []

        def pick(title, labels, **k):
            seen.append({"title": title, "labels": labels, **k})
            return picks[len(seen) - 1] if len(seen) <= len(picks) else None
        with mock.patch.object(picker, "filter_list", pick), mock.patch.object(ui, "ask", side_effect=list(answers)), \
                mock.patch.object(ui, "yellow", lambda t: t):
            collectionedit.settings_menu(collection, others)
        return seen

    def test_rows_and_art_preview(self):
        c = {"name": "Favs", "description": "", "art": "sonic", "games": []}
        seen = self.run_menu(c, [])
        self.assertEqual(seen[0]["labels"][:2], ["Name: Favs", "Description: none"])
        self.assertIn("Theme art:", seen[0]["labels"][2])
        self.assertEqual(seen[0]["preview"](0), themeart.art_png("sonic"))

    def test_rename_sets_name_and_reopens_on_the_row(self):
        c = {"name": "Favs", "games": []}
        seen = self.run_menu(c, [0], ["Best"])
        self.assertEqual(c["name"], "Best")
        self.assertEqual(seen[1]["cursor"], 0)

    def test_invalid_name_keeps_the_old_one(self):
        c = {"name": "Favs", "games": []}
        with mock.patch.object(collections, "collection_problem", return_value="bad"):
            self.run_menu(c, [0], ["!!!"])
        self.assertEqual(c["name"], "Favs")

    def test_empty_description_keeps_the_old_one(self):
        c = {"name": "Favs", "description": "old", "games": []}
        self.run_menu(c, [1], [""])
        self.assertEqual(c["description"], "old")
        self.run_menu(c, [1], ["new"])
        self.assertEqual(c["description"], "new")

    def test_x_clears_the_description_on_its_row_only(self):
        c = {"name": "Favs", "description": "old", "games": []}
        seen = self.run_menu(c, [("x", 0), ("x", 1)])
        self.assertEqual(c["name"], "Favs")
        self.assertEqual(c["description"], "")
        self.assertEqual(seen[2]["labels"][1], "Description: none")
        self.assertIn("x", seen[0]["hotkeys"])
        self.assertIn("clear", seen[0]["hint"])

    def test_rename_to_another_collections_name_is_refused(self):
        c = {"name": "Favs", "games": []}
        self.run_menu(c, [0], ["Best"], others=("best",))
        self.assertEqual(c["name"], "Favs")

    def test_renaming_to_its_own_name_or_case_is_fine(self):
        c = {"name": "Favs", "games": []}
        self.run_menu(c, [0], ["FAVS"], others=("best",))
        self.assertEqual(c["name"], "FAVS")

    def test_art_row_calls_pick_art(self):
        c = {"name": "Favs", "games": []}
        with mock.patch.object(collectionedit, "pick_art") as pa:
            self.run_menu(c, [2])
        pa.assert_called_once_with(c)

    def test_s_in_edit_one_opens_it_and_refreshes_the_title(self):
        c = {"name": "Favs", "games": [{"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}]}
        titles = []

        def toggle(title, rows, *a, **k):
            titles.append(title)
            return "S" if len(titles) == 1 else None

        def settings(coll, others=()):
            coll["name"] = "Renamed"
        with mock.patch.object(listedit, "toggle_all", toggle), mock.patch.object(collectionedit, "settings_menu", settings):
            collectionedit.edit_one(c, SYSTEMS, lambda b: {"gba/Ruby.zip"})
        self.assertIn("Renamed", titles[1])

    def test_empty_menu_settings_row_opens_it(self):
        with mock.patch.object(picker, "filter_list", side_effect=[1, None]), \
                mock.patch.object(collectionedit, "settings_menu") as sm:
            collectionedit.edit_one({"name": "Favs", "games": []}, SYSTEMS, lambda b: set())
        sm.assert_called_once()


class AddFromSystem(unittest.TestCase):
    """listedit.add_from_system, shared by the set and collection editors."""

    def add(self, listing, toggle_games=None, ask=None, **kw):
        picks = iter([2])  # PlayStation, after All systems
        shown = listedit.view(listing, SYSTEMS)
        with mock.patch.object(listedit, "stocked", lambda systems: systems), \
                mock.patch.object(listedit, "file_counts", lambda systems: [[] for _ in systems]), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(edit, "toggle_games", toggle_games or (lambda *a, **k: None)), \
                mock.patch.object(ui, "ask", side_effect=ask or [""]), mock.patch("builtins.print"):
            listedit.add_from_system(listing, SYSTEMS, shown, lambda bucket: DISCS if bucket == "psx" else set(),
                                     "📦 Favs", **kw)

    @staticmethod
    def switch_on(rows, i):
        s, key, title, _ = rows[i]
        s["games"].append({"bucket": key, "title": title})

    def add_all(self, listing, toggle_games, ask=None, rows_of=None, **kw):
        shown = listedit.view(listing, SYSTEMS)
        labels = []

        def pick(title, options, **k):
            labels.extend(options)
            return 0  # All systems
        keys = {"gba": {"gba/Ruby.zip"}, "psx": DISCS}
        with mock.patch.object(listedit, "stocked", lambda systems: systems), \
                mock.patch.object(listedit, "file_counts", lambda systems: [[] for _ in systems]), \
                mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(edit, "toggle_games", toggle_games), \
                mock.patch.object(ui, "ask", side_effect=ask or [""]) as asked, mock.patch("builtins.print"):
            listedit.add_from_system(listing, SYSTEMS, shown, lambda bucket: keys.get(bucket, set()), "📦 Favs", **kw)
        return labels, asked

    @staticmethod
    def switch_on_ruby_and_ff7(title, rows, **k):
        for r in rows:
            if r[1] in ("gba/Ruby.zip", "psx/FF7.m3u"):
                r[0]["games"].append({"bucket": r[1], "title": r[2]})

    def test_all_systems_is_the_first_option_then_the_stocked_systems(self):
        labels, _ = self.add_all({"name": "Favs", "games": []}, lambda *a, **k: None, ask=AssertionError)
        self.assertEqual(labels, [ALL, "Game Boy Advance", "PlayStation"])

    def test_all_systems_adds_games_of_several_systems_with_discs(self):
        listing = {"name": "Favs", "games": []}
        _, asked = self.add_all(listing, self.switch_on_ruby_and_ff7)
        asked.assert_not_called()
        self.assertEqual(listing["games"], [RUBY, {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
                                                  "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}])

    def test_toggle_shows_the_rows(self):
        listing = {"name": "Favs", "games": []}
        seen = []

        def toggle(s, title, rows):
            seen.append((s["bucket"], [r[1] for r in rows]))
            self.switch_on(rows, 1)
        self.add(listing, mock.Mock(side_effect=AssertionError("plain list")), ask=AssertionError("asked"),
                 toggle=toggle)
        self.assertEqual(seen, [("psx", ["psx/Crash.chd", "psx/FF7.m3u"])])
        self.assertEqual(listing["games"], [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
                                             "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}])

    def test_ctrl_c_keeps_the_toggles_and_is_raised_again(self):
        listing = {"name": "Favs", "games": []}

        def toggle(title, rows, **k):
            self.switch_on(rows, 0)
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.add(listing, toggle, ask=AssertionError("asked"))
        self.assertEqual(listing["games"], [{"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}])

    def test_esc_at_the_system_list_changes_nothing(self):
        listing = {"name": "Favs", "games": []}
        with mock.patch.object(listedit, "stocked", lambda systems: systems), \
                mock.patch.object(listedit, "file_counts", lambda systems: []), \
                mock.patch.object(picker, "filter_list", return_value=None):
            listedit.add_from_system(listing, SYSTEMS, listedit.view(listing, SYSTEMS), AssertionError, "📦 Favs")
        self.assertEqual(listing["games"], [])


class AddFromTag(unittest.TestCase):
    """listedit.add_from_tag: the tag editor's "Add games with another tag"."""

    def test_adds_the_tags_games_on_known_systems_with_their_files(self):
        tag_games(self, {"gba/Ruby.zip": None, "nes/Gone.nes": None, "psx/FF7.m3u": ["psx/FF7 (Disc 1).chd"]},
                  {"mix": {"name": "Mix", "emoji": "🔀"}, "cave": {"name": "Cave", "emoji": "🐝"}})
        listing = {"name": "Favs", "games": []}
        shown = listedit.view(listing, SYSTEMS)
        offered, toggled = [], []

        def pick(title, labels, **kw):
            offered.append(labels)
            return 1

        def toggle(title, rows, **kw):
            toggled.append((title, [r[3] for r in rows]))
            for s, key, name, _ in rows:
                s["games"].append({"title": name, "bucket": key})
        keys = {"gba": {"gba/Ruby.zip"}, "psx": DISCS}
        with mock.patch.object(picker, "filter_list", pick), mock.patch.object(edit, "toggle_games", toggle), \
                mock.patch.object(edit, "note"):
            listedit.add_from_tag(listing, shown, lambda bucket: keys[bucket], "💖 Favs")
        self.assertEqual(offered, [["🐝 Cave  (0 games)", "🔀 Mix  (3 games)"]])
        self.assertEqual(toggled, [("✏️  🔀 Mix — ✅ in 💖 Favs, ⬜ not", ["Game Boy Advance — Ruby", "PlayStation — FF7"])])
        self.assertEqual(listing["games"], [
            {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}])

    def add_with_filter(self, toggle_raises=False):
        tag_games(self, {"gba/Ruby.zip": None})
        tagui.FILTER.required, tagui.FILTER.excluded = {"mix"}, {"other"}
        listing = {"name": "Favs", "games": []}
        seen = []

        def toggle(title, rows, **kw):
            seen.append((set(tagui.FILTER.required), set(tagui.FILTER.excluded)))
            if toggle_raises:
                raise KeyboardInterrupt
        with mock.patch.object(picker, "filter_list", return_value=0), mock.patch.object(edit, "toggle_games", toggle), \
                mock.patch.object(edit, "note"):
            try:
                listedit.add_from_tag(listing, listedit.view(listing, SYSTEMS), lambda b: {"gba/Ruby.zip"}, "💖 Favs")
            except KeyboardInterrupt:
                seen.append("interrupted")
        return seen

    def test_the_tag_filter_is_preset_while_the_list_is_open_and_restored_after(self):
        seen = self.add_with_filter()
        self.assertEqual(seen, [({"mix"}, set())])
        self.assertEqual((tagui.FILTER.required, tagui.FILTER.excluded), ({"mix"}, {"other"}))

    def test_the_filter_is_restored_on_ctrl_c_too(self):
        seen = self.add_with_filter(toggle_raises=True)
        self.assertEqual(seen, [({"mix"}, set()), "interrupted"])
        self.assertEqual((tagui.FILTER.required, tagui.FILTER.excluded), ({"mix"}, {"other"}))

    def test_esc_or_no_tags_adds_nothing(self):
        tag_games(self, {}, defs={})
        listing = {"name": "Favs", "games": []}
        with mock.patch.object(edit, "note") as note, mock.patch.object(picker, "filter_list") as fl:
            listedit.add_from_tag(listing, listedit.view(listing, SYSTEMS), lambda b: set(), "💖 Favs")
        fl.assert_not_called()
        self.assertIn("No tags", note.call_args[0][0])
        tag_games(self, {"gba/Ruby.zip": None})
        with mock.patch.object(picker, "filter_list", return_value=None), \
                mock.patch.object(edit, "toggle_games") as toggle:
            listedit.add_from_tag(listing, listedit.view(listing, SYSTEMS), lambda b: set(), "💖 Favs")
        toggle.assert_not_called()
        self.assertEqual(listing["games"], [])


class FolderLister(unittest.TestCase):
    def test_each_folder_is_listed_once(self):
        asked = []

        def folder_keys(bucket):
            asked.append(bucket)
            return {bucket + "/a.zip"}
        with mock.patch.object(store, "folder_keys", folder_keys):
            keys_of = listedit.folder_lister()
            self.assertEqual(keys_of("gba"), {"gba/a.zip"})
            self.assertEqual(keys_of("gba"), {"gba/a.zip"})
            self.assertEqual(keys_of("psx"), {"psx/a.zip"})
            self.assertEqual(listedit.folder_lister()("gba"), {"gba/a.zip"})  # a new lister lists again
        self.assertEqual(asked, ["gba", "psx", "gba"])


class Editor(DataDir):
    def setUp(self):
        super().setUp()
        self.note = self.enterContext(mock.patch.object(edit, "note"))  # what the editor says at its end
        self.asked, self.reviewed = [], []  # the review's questions, and the changes it showed

    def run_editor(self, picks, asks=(), confirm=True, edit_one=None, choose=()):
        """choose: the review's answers (s save, e keep editing, d discard); save once they run out."""
        picks, confirms, choose = iter(picks), [], iter(choose)

        def answer(value):  # KeyboardInterrupt in picks or as confirm is Ctrl-C there
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value
        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: answer(next(picks))), \
                mock.patch.object(ui, "ask", side_effect=list(asks)), \
                mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text) or answer(confirm)), \
                mock.patch.object(ui, "choose", lambda question, *a, **k: self.asked.append(question) or next(choose, "s")), \
                mock.patch.object(listedit, "print_changes", lambda found: self.reviewed.append(found)), \
                mock.patch.object(collectionedit, "edit_one", edit_one or (lambda c, systems, keys_of, others=(): c["games"].append(dict(RUBY)))), \
                mock.patch("subprocess.run") as run:
            code = collectionedit.edit_collections()
        run.assert_not_called()  # no git, no gh
        return code, confirms, self.note

    def test_new_collection_is_saved_on_done(self):
        code, _, _ = self.run_editor([0, 2], asks=["Favs", "my faves"])  # ➕ New, then (one collection) ✅ Done
        self.assertEqual(code, 0)
        self.assertEqual(self.read("collections/favs.json"), {"name": "Favs", "description": "my faves", "games": [RUBY]})

    def test_esc_reviews_and_saves(self):
        code, _, _ = self.run_editor([0, None], asks=["Favs", ""])  # ➕ New, then Esc
        self.assertEqual(code, 0)
        self.assertEqual(self.asked, ["💾 Save these changes?"])
        self.assertEqual(self.reviewed, [[("new", "favs", ["+ Ruby (gba/Ruby.zip)"])]])
        self.assertEqual(self.read("collections/favs.json"), {"name": "Favs", "games": [RUBY]})

    def test_keep_editing_goes_back_to_the_menu_and_discard_saves_nothing(self):
        code, _, note = self.run_editor([0, None, None], asks=["Favs", ""], choose=["e", "d"])  # ➕ New, Esc, e, Esc, d
        self.assertEqual(code, 0)
        self.assertEqual(self.asked, ["💾 Save these changes?"] * 2)
        self.assertFalse(os.path.exists(self.path("collections")))
        self.assertIn("Not saved", str(note.call_args_list))

    def test_a_file_in_another_order_is_no_change_and_opens_with_the_other_ids(self):
        zed = {"title": "Zed", "system": "gba", "bucket": "gba/Zed.zip"}
        collections.save_collection({"id": "favs", "name": "Favs", "games": [zed, RUBY]})
        collections.save_collection({"id": "best", "name": "Best", "games": []})
        seen = []
        code, _, note = self.run_editor([1, None], edit_one=lambda c, s, k, others=(): seen.append((c["name"], sorted(others))))
        self.assertEqual((code, self.asked), (0, []))
        self.assertEqual(seen, [("Favs", ["best"])])
        self.assertIn("No changes, nothing saved", str(note.call_args_list))

    def test_esc_without_changes_saves_nothing(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        code, _, note = self.run_editor([None])
        self.assertEqual((code, self.asked), (0, []))
        self.assertIn("No changes, nothing saved", str(note.call_args_list))

    def test_the_menu_says_esc_reviews(self):
        seen = []

        def fake(title, labels, **kw):
            seen.append((title, labels, kw.get("hint")))
            return None
        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), mock.patch.object(picker, "filter_list", fake):
            collectionedit.edit_collections()
        title, labels, hint = seen[0]
        self.assertEqual(title, "✏️  Which collection?  (Esc = review & save)")
        self.assertEqual(labels, ["➕ New collection", "✅ Done (review & save)", "🚪 Quit without saving"])
        self.assertIn("Esc review", hint)

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
        self.assertEqual(self.read("collections/favs.json.bak"), {"name": "Favs", "games": [RUBY]})
        self.assertEqual(self.read("cards.json"), {"a": {"collections": ["x"]}, "b": {"collections": []}, "c": {}})

    def test_declined_delete_keeps_it(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.run_editor([(edit.DELETE_KEY, 0), 2], confirm=False)  # still one collection: index 2 is ✅ Done
        self.assertTrue(os.path.exists(self.path("collections/favs.json")))

    def test_an_empty_collection_is_saved_on_done(self):
        self.run_editor([0, 2], asks=["Empty", ""], edit_one=lambda c, s, k, o=(): None)
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
            self.run_editor([0, KeyboardInterrupt], asks=["Empty", ""], edit_one=lambda c, s, k, o=(): None)
        self.assertEqual(self.read("collections/empty.json"), {"name": "Empty", "games": []})
        self.assertIn("Saved to", str(self.note.call_args_list))

    def test_a_second_ctrl_c_at_the_question_discards(self):
        with mock.patch("builtins.print") as out, self.assertRaises(KeyboardInterrupt):
            self.run_editor([0, KeyboardInterrupt], asks=["Favs", ""], confirm=KeyboardInterrupt)
        self.assertFalse(os.path.exists(self.path("collections")))
        self.assertIn("Not saved", str(out.call_args_list))

    def interrupted(self, games, picks, lists, tagged=None, ask=None):
        """Open collection favs (holding games) in the real collection editor; picks answer the single-choice lists,
        KeyboardInterrupt in picks is Ctrl-C there;
        lists holds per toggle list (labels to switch, what it then does: KeyboardInterrupt, a hotkey or None for Enter);
        tagged: the games of the Mix tag ({bucket key: extra files}). ask is ui.ask's side_effect. Ctrl-C's save
        question is answered yes. Returns the confirms asked and the ui.ask mock."""
        if tagged:
            storage_tags(self, {"tags": {"mix": {"name": "Mix", "emoji": "🔀"}}, "declined": {},
                                "games": {k: {"tags": ["mix"], **({"files": f} if f else {})} for k, f in tagged.items()}})
        collections.save_collection({"id": "favs", "name": "Favs", "games": games})
        picks, lists, confirms = iter(picks), iter(lists), []
        keys = {"gba": {"gba/Ruby.zip", "gba/Zelda.zip"}, "psx": DISCS}

        def fake(title, labels, **kw):
            if not kw.get("multi"):
                pick = next(picks)
                if pick is KeyboardInterrupt:
                    raise KeyboardInterrupt
                return pick
            flip, then = next(lists)
            kw["session"]["sel"] = [on != (label in flip) for label, on in zip(labels, kw["session"]["sel"])]
            if then is KeyboardInterrupt:
                raise KeyboardInterrupt
            return (then, 0) if then else kw["session"]["sel"]

        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(store, "folder_keys", lambda bucket: keys.get(bucket, set())), \
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

    MIX = {"gba/Ruby.zip": None, "psx/FF7.m3u": ["psx/FF7 (Disc 1).chd"]}

    def test_ctrl_c_in_a_list_with_nothing_toggled_asks_nothing(self):
        for picks in ([0, 0],):
            with self.subTest(picks=picks):
                confirms, _ = self.interrupted([RUBY], picks, [(set(), KeyboardInterrupt)], tagged={"gba/Ruby.zip": None})
                self.assertEqual(confirms, [])
                self.assertEqual(self.read("collections/favs.json")["games"], [RUBY])

    def test_ctrl_c_keeps_the_add_games_lists_toggles(self):
        # open the collection, A, PlayStation: switch Crash on and press c, then switch FF7 on and Ctrl-C
        for key in ("A", "+"):
            with self.subTest(key=key):
                confirms, ask = self.interrupted([RUBY], [0, 2], [(set(), key), ({"Crash.chd"}, "c"), ({"FF7.m3u"}, KeyboardInterrupt)])
                ask.assert_not_called()
                self.assertEqual(len(confirms), 1)
                self.assertEqual(self.read("collections/favs.json")["games"], [
                    {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"},
                    {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]},
                    RUBY])

    def test_ctrl_c_in_the_all_systems_list_keeps_its_toggles(self):
        confirms, ask = self.interrupted([RUBY], [0, 0], [(set(), "A"), ({"PlayStation — FF7.m3u"}, KeyboardInterrupt)])
        ask.assert_not_called()
        self.assertEqual(len(confirms), 1)
        self.assertEqual(self.read("collections/favs.json")["games"], [
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}, RUBY])

    def test_ctrl_c_in_the_tag_or_meta_picker_keeps_the_games_lists_toggles(self):
        ff7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}
        crash = {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}
        for key, target, picker_name in (("s", tagui.TagFilter, "pick"), ("m", collectionedit.cardedit, "pick_meta")):
            with self.subTest(key=key), mock.patch.object(target, picker_name, side_effect=KeyboardInterrupt):
                # open, A, PlayStation: Crash on, c; FF7 on, then the key whose picker gets Ctrl-C
                confirms, ask = self.interrupted([RUBY], [0, 2], [(set(), "A"), ({"Crash.chd"}, "c"), ({"FF7.m3u"}, key)])
                ask.assert_not_called()
                self.assertEqual(len(confirms), 1)
                self.assertEqual(self.read("collections/favs.json")["games"], [crash, ff7, RUBY])
            with self.subTest(key=key, toggled=False), mock.patch.object(target, picker_name, side_effect=KeyboardInterrupt):
                confirms, _ = self.interrupted([RUBY], [0, 2], [(set(), "A"), (set(), key)])
                self.assertEqual(confirms, [])
                self.assertEqual(self.read("collections/favs.json")["games"], [RUBY])

    def test_adding_games_asks_no_category(self):
        # FF7 on, Enter, then Ctrl-C at the next list of the collection
        confirms, ask = self.interrupted([RUBY], [0, 2], [(set(), "A"), ({"FF7.m3u"}, None), (set(), KeyboardInterrupt)])
        ask.assert_not_called()
        self.assertEqual(len(confirms), 1)
        self.assertEqual(self.read("collections/favs.json")["games"],
                         [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}, RUBY])

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
        self.assertEqual(commands.second_words()["collections"], ["edit", "page", "share", "unshare"])
        self.assertEqual(cli.SUBCOMMANDS["collections"][0], "edit|page|share|unshare")
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


class AllRows(unittest.TestCase):
    def rows(self, gba=frozenset({"gba/Ruby.zip"})):
        shown = listedit.view({"games": []}, SYSTEMS)
        keys = {"gba": set(gba), "psx": DISCS}
        return shown, listedit.all_rows(shown, SYSTEMS, lambda bucket: keys[bucket])

    def test_all_rows_span_systems_with_system_prefixed_labels(self):
        shown, rows = self.rows()
        labels = [r[3] for r in rows]
        self.assertEqual(labels, ["PlayStation — Crash.chd", "PlayStation — FF7.m3u", "Game Boy Advance — Ruby.zip"])
        self.assertFalse(any("FF7 (Disc 1).chd" in label for label in labels))
        self.assertEqual([r[0] for r in rows], [shown["psx"], shown["psx"], shown["gba"]])

    def test_all_rows_skip_a_system_with_no_files(self):
        _, rows = self.rows(gba=frozenset())
        self.assertFalse([r for r in rows if r[1].startswith("gba/")])

    def test_toggle_all_hint_names_s_and_c_once(self):
        seen = []
        with mock.patch.object(picker, "filter_list", lambda t, labels, **k: seen.append(k) or [False]):
            listedit.toggle_all("t", [({**SYSTEMS[0], "games": []}, "gba/Ruby.zip", "Ruby", "Ruby")])
        self.assertEqual(seen[0]["hint"].count("s filter by tag"), 1)
        self.assertEqual(seen[0]["hint"].count("c clear filters"), 1)
        self.assertIn("/ filter", seen[0]["hint"])

    def test_toggle_all_leaves_s_and_c_to_the_sticky_filter(self):
        _, rows = self.rows()
        with mock.patch.object(edit, "toggle_games", return_value=None) as fake:
            listedit.toggle_all("All", rows, place={})
        self.assertEqual(fake.call_args.args[1], rows)
        self.assertEqual(fake.call_args.kwargs["hotkeys"], ())  # s and c are toggle_games's own

    def test_toggle_all_shows_only_what_the_sticky_filter_keeps(self):
        tag_games(self, {"gba/Ruby.zip": None})
        _, rows = self.rows()
        tagui.FILTER.required = {"mix"}
        seen = []

        with mock.patch.object(picker, "filter_list", lambda t, labels, **k: seen.append((labels, k["filters"])) or k["session"]["sel"]):
            listedit.toggle_all("All", rows)
        self.assertEqual(seen, [(["Game Boy Advance — Ruby.zip"], "✅ 🔀 Mix · 1 of 3 shown (c clear filters)")])

    def test_toggle_all_turns_select_all_on_only_while_a_tag_filter_is_set(self):
        _, rows = self.rows()
        with mock.patch.object(edit, "toggle_games", return_value=None) as fake:
            listedit.toggle_all("All", rows)
        self.assertEqual(fake.call_args.kwargs["select_all"], edit.WHEN_FILTERED)
        seen = []
        tag_games(self, {"gba/Ruby.zip": None})
        with mock.patch.object(picker, "filter_list", lambda t, labels, **k: seen.append(k) or k["session"]["sel"]):
            listedit.toggle_all("All", rows)
            tagui.FILTER.required = {"mix"}
            listedit.toggle_all("All", rows)
        self.assertEqual([(k["select_all"], "a all shown" in k["hint"]) for k in seen], [(False, False), (True, True)])


if __name__ == "__main__":
    unittest.main()
