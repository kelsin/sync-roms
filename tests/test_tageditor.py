import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import cli, commands, edit, listedit, picker, store, tageditor, tags, tagui, ui  # noqa: E402

A, B = "nes/A (USA).zip", "nes/B (USA).zip"
SYSTEMS = [{"name": "Nintendo NES", "bucket": "nes"}]


class Editor(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        self.root = helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
            "games": {A: {"tags": ["cave", "shmups"]}, B: {"tags": ["shmups"]}}, "declined": {}})
        self.notes = []
        self.enterContext(mock.patch.object(edit, "note", self.notes.append))
        self.enterContext(mock.patch.object(store, "repo_json", lambda name: SYSTEMS if name == "systems" else []))
        self.shown = []  # (title, labels) of every list shown

    def disk(self):
        with open(os.path.join(self.root, tags.KEY), encoding="utf-8") as f:
            return f.read()

    def run_editor(self, script, asks=(), confirms=()):
        """edit_tags() with filter_list answering script in turn: a string picks the first row containing it, a tuple
        or None is returned as it is. Then the editor leaves with Esc."""
        script = iter([*script, None, None, None])

        def fake(title, labels, **kw):
            self.shown.append((title, labels))
            step = next(script)
            if isinstance(step, str):
                return next(i for i, label in enumerate(labels) if step in label)
            return step
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", side_effect=list(asks)), \
                mock.patch.object(ui, "confirm", side_effect=list(confirms)) as confirm:
            self.assertEqual(tageditor.edit_tags(), 0)
        return confirm

    def test_list_shows_emoji_name_and_count(self):
        self.run_editor([None])
        title, labels = self.shown[0]
        self.assertEqual(labels[:2], ["🐝 Cave  (1 games)", "🚀 Shmups  (2 games)"])
        self.assertIn("New tag", labels[2])

    def test_c_on_the_tag_list_clears_the_sticky_filter_and_the_banner_shows_while_it_is_on(self):
        tagui.FILTER.required = {"shmups"}
        self.addCleanup(tagui.FILTER.clear)
        banners = []
        script = iter([(tagui.CLEAR_KEY, 0), None])

        def fake(title, labels, **kw):
            banners.append((kw["filters"], kw["hint"]))
            return next(script)
        with mock.patch.object(picker, "filter_list", fake):
            self.assertEqual(tageditor.edit_tags(), 0)
        self.assertEqual(banners[0][0], "✅ 🚀 Shmups (c clear filters)")
        self.assertIn("c clear filters", banners[0][1])
        self.assertEqual(banners[1], ("", "/ filter · Enter open · n new tag · o sort · Esc back"))
        self.assertEqual(tagui.FILTER.describe(), "")

    def test_rename_changes_the_name_not_the_id(self):
        self.run_editor(["Shmups", "Rename", None, None], asks=["Shoot-em-ups"])
        self.assertEqual(tags.all_tags()["shmups"]["name"], "Shoot-em-ups")
        self.assertEqual(tags.tags_of(B), ["shmups"])
        self.assertNotIn("shoot-em-ups", tags.all_tags())

    def test_empty_name_is_refused(self):
        before = self.disk()
        self.run_editor(["Shmups", "Rename", None, None], asks=[""])
        self.assertEqual(self.disk(), before)
        self.assertTrue(self.notes)

    def test_emoji_changes(self):
        self.run_editor(["Shmups", "Emoji", None, None], asks=["🛸"])
        self.assertEqual(tags.all_tags()["shmups"]["emoji"], "🛸")

    def test_emoji_another_tag_uses_is_refused(self):
        before = self.disk()
        self.run_editor(["Shmups", "Emoji", None, None], asks=["🐝"])
        self.assertEqual(self.disk(), before)
        self.assertIn("🐝", self.notes[-1])

    def test_empty_emoji_is_refused(self):
        before = self.disk()
        self.run_editor(["Shmups", "Emoji", None, None], asks=[""])
        self.assertEqual(self.disk(), before)
        self.assertTrue(self.notes)

    def test_description(self):
        self.run_editor(["Shmups", "Description", None, None], asks=["Shoot them up"])
        self.assertEqual(tags.all_tags()["shmups"]["description"], "Shoot them up")

    def test_merge_into_another_tag(self):
        self.run_editor(["Shmups", "Merge", "Cave"], confirms=[True])
        self.assertNotIn("shmups", tags.all_tags())
        self.assertEqual(tags.tags_of(B), ["cave"])
        self.assertEqual(tags.tags_of(A), ["cave"])

    def test_merge_and_delete_say_what_happened(self):
        self.run_editor(["Shmups", "Merge", "Cave"], confirms=[True])
        self.assertEqual(self.notes[-1], "🔀 Merged 2 games into 🐝 Cave")
        self.run_editor(["Cave", "Delete"], confirms=[True])
        self.assertEqual(self.notes[-1], "🗑️  Deleted 🐝 Cave")

    def test_rename_refuses_a_name_another_tag_has(self):
        before = self.disk()
        self.run_editor(["Shmups", "Rename", None, None], asks=["cave"])
        self.assertEqual(self.disk(), before)
        self.assertIn("already a tag named cave", self.notes[-1])

    def test_o_toggles_the_sort_to_game_count_and_dims_empty_tags(self):
        tags.define_tag("empty", {"name": "Aaa", "emoji": "⭕"})
        seen = []
        script = iter([("o", 0), None])

        def fake(title, labels, **kw):
            seen.append((labels, kw))
            return next(script)
        with mock.patch.object(picker, "filter_list", fake):
            self.assertEqual(tageditor.edit_tags(), 0)
        self.assertEqual(seen[0][0][0][:5], "⭕ Aaa")  # by name first
        self.assertEqual(seen[1][0][0][:8], "🚀 Shmups")  # then most games first
        self.assertIn(("no games", "dim"), seen[0][1]["extras"][0])
        self.assertIn("o sort", seen[0][1]["hint"])

    def test_merge_declined_writes_nothing(self):
        before = self.disk()
        self.run_editor(["Shmups", "Merge", "Cave", None, None], confirms=[False])
        self.assertEqual(self.disk(), before)

    def test_delete_confirmed_removes_it_from_every_game(self):
        confirm = self.run_editor(["Shmups", "Delete"], confirms=[True])
        self.assertIn("2 game", confirm.call_args[0][0])
        self.assertEqual(list(tags.all_tags()), ["cave"])
        self.assertEqual(tags.tags_of(A), ["cave"])
        self.assertEqual(tags.tags_of(B), [])

    def test_delete_declined_writes_nothing(self):
        before = self.disk()
        self.run_editor(["Shmups", "Delete", None, None], confirms=[False])
        self.assertEqual(self.disk(), before)

    def test_its_games_lists_titles_with_systems_and_unchecked_ones_lose_the_tag(self):
        seen = []

        def toggle(title, rows, **kw):
            seen.append([(r[1], r[2], r[3]) for r in rows])
            entry = rows[0][0]
            entry["games"] = [g for g in entry["games"] if g["bucket"] != B]
            return None
        with mock.patch.object(edit, "toggle_games", toggle):
            self.run_editor(["Shmups", "Games with this tag", None, None])
        self.assertEqual(seen, [[(A, "A (USA)", "Nintendo NES — A (USA)"), (B, "B (USA)", "Nintendo NES — B (USA)")]])
        self.assertEqual(tags.tags_of(A), ["cave", "shmups"])
        self.assertEqual(tags.tags_of(B), [])

    def test_its_games_unchanged_writes_nothing(self):
        before = self.disk()
        with mock.patch.object(edit, "toggle_games", lambda *a, **k: None):
            self.run_editor(["Shmups", "Games with this tag", None, None])
        self.assertEqual(self.disk(), before)

    def test_add_from_a_system_tags_the_added_games(self):
        def add(listing, systems, shown, keys_of, label, **kw):
            self.assertEqual(label, "🐝 Cave")
            listing["games"].append({"system": "nes", "bucket": "nes/New.zip", "title": "New"})
            listing["games"] = [g for g in listing["games"] if g["bucket"] != A]
        with mock.patch.object(tageditor, "add_from_system", add):
            self.run_editor(["Cave", "from a system", None, None])
        self.assertEqual(tags.tags_of("nes/New.zip"), ["cave"])
        self.assertEqual(tags.tags_of(A), ["shmups"])

    def test_add_from_a_tag_tags_the_added_games(self):
        def add(listing, shown, keys_of, label, **kw):
            listing["games"].append({"system": "nes", "bucket": B, "files": ["nes/B (Disc 2).zip"]})
        with mock.patch.object(tageditor, "add_from_tag", add):
            self.run_editor(["Cave", "with another tag", None, None])
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])
        self.assertEqual(tags.record(B)["files"], ["nes/B (Disc 2).zip"])

    def test_with_another_tag_presets_the_filter_and_restores_yours(self):
        tagui.FILTER.required, tagui.FILTER.excluded = {"shmups"}, {"cave"}
        seen = []
        with mock.patch.object(edit, "toggle_games", lambda *a, **k: seen.append(
                (set(tagui.FILTER.required), set(tagui.FILTER.excluded)))):
            self.run_editor(["Cave", "with another tag", "Shmups", None, None])
        self.assertEqual(seen, [({"shmups"}, set())])
        self.assertEqual((tagui.FILTER.required, tagui.FILTER.excluded), ({"shmups"}, {"cave"}))

    def test_n_creates_a_tag_and_opens_it(self):
        self.run_editor([("n", 0), None, None], asks=["Pixel Art", "🎨"])
        self.assertEqual(tags.all_tags()["pixel-art"], {"name": "Pixel Art", "emoji": "🎨"})
        self.assertIn("Pixel Art", self.shown[1][0])

    def test_a_refused_new_tag_adds_nothing(self):
        before = self.disk()
        self.run_editor([("n", 0), None], asks=["Pixel Art", "🐝"])
        self.assertEqual(self.disk(), before)
        self.assertTrue(self.notes)

    def test_a_storage_error_is_a_note(self):
        with mock.patch.object(tags, "define_tag", side_effect=OSError("unmounted")):
            self.run_editor(["Shmups", "Emoji", None, None], asks=["🛸"])
        self.assertIn("unmounted", self.notes[-1])
        self.assertEqual(tags.all_tags()["shmups"]["emoji"], "🚀")

    def test_switching_games_off_offers_no_notes(self):
        with mock.patch.object(edit, "toggle_games") as toggle:
            tageditor.switch_games_off("shmups", "🚀 Shmups", {})
        self.assertIs(toggle.call_args.kwargs["notes"], False)

    def test_malformed_tags_json_in_storage_is_noted(self):
        with open(os.path.join(self.root, tags.KEY), "w", encoding="utf-8") as f:  # broken after this run read it
            f.write("{nope")
        self.assertFalse(tageditor._save(tags.define_tag, "shmups", {"emoji": "🛸"}))
        self.assertEqual(len(self.notes), 1)

    def test_merging_into_a_tag_deleted_elsewhere_is_noted(self):
        with open(os.path.join(self.root, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump({"tags": {"cave": {"name": "Cave", "emoji": "🐝"}}, "games": {}, "declined": {}}))
        self.assertFalse(tageditor._save(tags.merge_tag, "cave", "shmups"))
        self.assertIn("shmups", self.notes[-1])
        self.assertIn("cave", tags.all_tags())


C = "nes/C (USA).zip"  # in storage, with no tags


class Walkthrough(unittest.TestCase):
    """The everyday flows, screen by screen: each step answers one filter_list call as a key sequence would."""
    setUp = Editor.setUp

    def walk(self, steps):
        """edit_tags() with each filter_list call answered by the next step(labels, kw) in turn; returns the titles."""
        steps = iter(steps)
        titles = []

        def fake(title, labels, **kw):
            titles.append(title)
            return next(steps)(labels, kw)
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(listedit, "stocked", lambda s: s), \
                mock.patch.object(listedit, "file_counts", lambda s: [[] for _ in s]), \
                mock.patch.object(tageditor, "folder_lister", lambda: lambda bucket: {A, B, C}), \
                mock.patch("builtins.print"):
            self.assertEqual(tageditor.edit_tags(), 0)
        return titles

    @staticmethod
    def pick(text):
        """Enter on the row containing text (after / and the text, or j/k)."""
        return lambda labels, kw: next(i for i, label in enumerate(labels) if text in label)

    @staticmethod
    def search_then(key, query):
        """/ query Enter, then key (a hotkey) in a multi list: what the picker leaves in its session."""
        def step(labels, kw):
            kw["session"]["query"] = query
            return key, None
        return step

    @staticmethod
    def toggle(text):
        """Space on the row containing text, then Enter."""
        def step(labels, kw):
            return [on != (text in label) for on, label in zip(kw["initial"], labels)]
        return step

    esc = staticmethod(lambda labels, kw: None)

    quit = staticmethod(lambda labels, kw: (tageditor.QUIT_KEY, None))

    def add_missing(self, system_row=None, then_quit_in_the_add_list=False):
        """Flow A: Shmups, its games, / C finds nothing and + goes to all systems with the search (system_row: no
        search, + picks that system), Space on C, then Enter and Q in the tag's games, or Q in the add list."""
        tagui.FILTER.required = {"cave"}  # a sticky filter that would hide C
        seen = {}

        def add_list(labels, kw):
            seen["add"] = (list(labels), kw["session"].get("query"), kw["filters"])
            on = self.toggle("C (USA)")(labels, kw)
            if then_quit_in_the_add_list:
                kw["session"]["sel"] = on
                return tageditor.QUIT_KEY, None
            return on

        def back_in_its_games(labels, kw):
            seen["back"] = (list(labels), kw["session"].get("row"))
            return tageditor.QUIT_KEY, None
        steps = [self.pick("Shmups"), self.pick("Games with this tag")]
        steps += [self.search_then("+", "C (USA)")] if system_row is None else [self.search_then("+", ""), self.pick(system_row)]
        steps += [add_list] + ([] if then_quit_in_the_add_list else [back_in_its_games])
        titles = self.walk(steps)
        self.assertEqual(tags.tags_of(C), ["shmups"])
        self.assertEqual(tags.tags_of(A), ["cave", "shmups"])
        labels, query, filters = seen["add"]
        self.assertTrue(any("C (USA)" in label for label in labels))  # the sticky filter doesn't hide it here
        self.assertEqual(query or "", "" if system_row else "C (USA)")  # the search typed in the tag's games is applied
        self.assertIn("paused", filters)
        if not then_quit_in_the_add_list:
            labels, row = seen["back"]
            self.assertIn("C (USA)", labels[row])  # back in the tag's games, on the game just added
        self.assertEqual({"cave"}, tagui.FILTER.required)  # the user's filter is untouched
        return titles

    def test_a_plus_after_a_search_goes_straight_to_all_systems_with_it(self):
        titles = self.add_missing()
        self.assertEqual(len(titles), 5)  # the tags, Shmups, its games, all systems, its games again (Q)
        self.assertIn("All systems", titles[3])

    def test_a_plus_with_no_search_picks_a_system(self):
        titles = self.add_missing("Nintendo NES")
        self.assertEqual(len(titles), 6)
        self.assertIn("which system", titles[3])
        self.assertIn("Nintendo NES", titles[4])

    def test_a_q_in_the_all_systems_list_saves_the_game_and_leaves(self):
        self.assertEqual(len(self.add_missing(then_quit_in_the_add_list=True)), 4)

    def test_a_q_in_a_systems_list_saves_the_game_and_leaves(self):
        self.assertEqual(len(self.add_missing("Nintendo NES", then_quit_in_the_add_list=True)), 5)

    def test_b_remove_a_game_and_q_leaves_with_it_saved(self):
        def off_then_q(labels, kw):
            kw["session"]["sel"] = self.toggle("B (USA)")(labels, kw)
            return tageditor.QUIT_KEY, None
        titles = self.walk([self.pick("Shmups"), self.pick("Games with this tag"), off_then_q])
        self.assertEqual(len(titles), 3)
        self.assertEqual(tags.tags_of(B), [])
        self.assertEqual(tags.tags_of(A), ["cave", "shmups"])

    def test_b_remove_a_game_with_enter_and_esc(self):
        titles = self.walk([self.pick("Shmups"), self.pick("Games with this tag"), self.toggle("B (USA)"),
                            self.esc, self.esc])
        self.assertEqual(len(titles), 5)
        self.assertEqual(tags.tags_of(B), [])

    def test_q_in_the_tag_menu_leaves_the_tag_editor(self):
        hints = []

        def menu(labels, kw):
            hints.append((kw["hint"], kw["hotkeys"]))
            return tageditor.QUIT_KEY, 0
        self.assertEqual(len(self.walk([self.pick("Shmups"), menu])), 2)
        self.assertIn("Q quit the editor", hints[0][0])
        self.assertIn(tageditor.QUIT_KEY, hints[0][1])

    def test_q_raises_for_the_top_editor_when_asked(self):
        with mock.patch.object(picker, "filter_list", side_effect=[0, (tageditor.QUIT_KEY, 0)]):
            with self.assertRaises(tageditor.Quit):
                tageditor.edit_tags(quit_raises=True)

    def test_plus_on_a_tag_with_no_games_adds_its_first(self):
        tags.define_tag("new", {"name": "New", "emoji": "🆕"})
        seen = []

        def empty(labels, kw):
            seen.append(list(labels))
            return "+", None
        self.walk([self.pick("New"), self.pick("Games with this tag"), empty, self.pick("All systems"),
                   self.toggle("C (USA)"), self.quit])
        self.assertEqual(seen, [[]])
        self.assertEqual(tags.tags_of(C), ["new"])

    def test_the_tags_games_list_names_plus(self):
        hints = []

        def games(labels, kw):
            hints.append(kw["hint"])
            return list(kw["initial"])
        self.walk([self.pick("Shmups"), self.pick("Games with this tag"), games, self.esc, self.esc])
        for part in ("+ add games", "Q quit the editor", "o view"):
            self.assertIn(part, hints[0])

    def test_the_menus_add_from_a_system_ignores_the_sticky_filter(self):
        tagui.FILTER.required = {"cave"}
        seen = []

        def add_list(labels, kw):
            seen.extend(labels)
            return list(kw["initial"])
        self.walk([self.pick("Shmups"), self.pick("from a system"), self.pick("All systems"), add_list,
                   self.esc, self.esc])
        self.assertTrue(any("C (USA)" in label for label in seen))


    def test_q_in_the_menus_add_lists_saves_and_leaves(self):
        def on_then_q(labels, kw):
            kw["session"]["sel"] = self.toggle("C (USA)")(labels, kw)
            return tageditor.QUIT_KEY, None
        self.assertEqual(len(self.walk([self.pick("Shmups"), self.pick("from a system"), self.pick("All systems"),
                                        on_then_q])), 4)
        self.assertEqual(tags.tags_of(C), ["shmups"])

        def b_on_then_q(labels, kw):
            kw["session"]["sel"] = self.toggle("B (USA)")(labels, kw)
            return tageditor.QUIT_KEY, None
        self.assertEqual(len(self.walk([self.pick("Cave"), self.pick("with another tag"), self.pick("Shmups"),
                                        b_on_then_q])), 4)
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])


class RealKeys(unittest.TestCase):
    """The flows with real keys fed to the picker's list model (picker._run), not answers made up per screen."""
    setUp = Editor.setUp

    def press(self, screens):
        """edit_tags() with each list answered by the next key sequence; returns the titles."""
        screens = iter(screens)
        titles = []

        def run(model):
            titles.append(model.title)
            for k in next(screens):
                got = model.key(k)
                if got is not picker.KEEP:
                    return got
            self.fail(f"{model.title} was still open")
        with mock.patch.object(picker, "_run", run), mock.patch.object(picker, "_draws_images", return_value=False), \
                mock.patch.object(listedit, "stocked", lambda s: s), \
                mock.patch.object(listedit, "file_counts", lambda s: [[] for _ in s]), \
                mock.patch.object(tageditor, "folder_lister", lambda: lambda bucket: {A, B, C}), \
                mock.patch("builtins.print"):
            self.assertEqual(tageditor.edit_tags(), 0)
        return titles

    def test_a_search_with_no_match_then_plus_space_q(self):
        tagui.FILTER.required = {"cave"}
        titles = self.press([["/", *"shmups", "enter", "enter"], ["enter"], ["/", *"c (usa)", "enter", "+"],
                             ["space", tageditor.QUIT_KEY]])
        self.assertEqual(len(titles), 4)
        self.assertIn("All systems", titles[3])
        self.assertEqual(tags.tags_of(C), ["shmups"])

    def test_b_search_space_q(self):
        titles = self.press([["/", *"shmups", "enter", "enter"], ["enter"], ["/", *"b (usa)", "enter", "space",
                                                                             tageditor.QUIT_KEY]])
        self.assertEqual(len(titles), 3)
        self.assertEqual(tags.tags_of(B), [])

    def test_plus_and_q_while_typing_are_text(self):
        titles = self.press([["/", *"shmups", "enter", "enter"], ["enter"], ["/", "+", "Q", "escape", "escape"],
                             ["escape"], ["escape"]])
        self.assertEqual(len(titles), 5)  # back out through the menu and the tag list: nothing was added or quit


class Retag(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {"tags": {"a": {"name": "A", "emoji": "x"}, "b": {"name": "B", "emoji": "y"}},
                                    "games": {"nes/1.zip": {"tags": ["a"]}, "nes/2.zip": {"tags": ["a", "b"]}},
                                    "declined": {}})

    def test_one_write_adds_and_removes(self):
        tags.retag_games("a", add=["nes/3.zip", "nes/2.zip"], remove=["nes/1.zip"], files={"nes/3.zip": ["nes/3b.zip"]})
        self.assertEqual(tags.tags_of("nes/3.zip"), ["a"])
        self.assertEqual(tags.record("nes/3.zip")["files"], ["nes/3b.zip"])
        self.assertEqual(tags.tags_of("nes/2.zip"), ["a", "b"])
        self.assertEqual(tags.tags_of("nes/1.zip"), [])
        self.assertIsNone(tags.record("nes/1.zip"))


class Wiring(unittest.TestCase):
    def test_tags_edit_runs_the_editor(self):
        with mock.patch.object(tageditor, "edit_tags", return_value=0) as run:
            self.assertEqual(commands.run(["tags", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["tags"], ["edit", "suggest"])
        self.assertEqual(cli.canonical("tag"), "tags")

    def test_sets_edit_is_gone(self):
        self.assertNotIn("sets", commands.COMMANDS)
        self.assertNotIn("sets", cli.SUBCOMMANDS)
        self.assertEqual(cli.canonical("set"), "set")
        with self.assertRaises(SystemExit):
            commands.run(["sets", "edit"])


if __name__ == "__main__":
    unittest.main()
