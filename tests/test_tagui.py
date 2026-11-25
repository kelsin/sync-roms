import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import edit, picker, store, tags, tagui, ui  # noqa: E402

A, B = "nes/A (USA).zip", "nes/B (USA).zip"


class TagUi(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
            "games": {B: {"tags": ["shmups"]}}, "declined": {}})
        self.notes = []
        self.enterContext(mock.patch.object(edit, "note", self.notes.append))

    def test_column_rows(self):
        self.assertEqual(tagui.column([A, B]), [("", ""), ("🚀", "")])
        tags.change_game_tags(A, add=["cave", "shmups"])
        self.assertEqual(tagui.column([A, B]), [("🐝🚀", ""), ("🚀", "")])
        with mock.patch.object(tags, "emoji_of", return_value="12345678"):
            self.assertEqual(tagui.column([A]), [("12345678", "")])

    def test_summary_rows(self):
        tags.define_tag("cave", {"name": "Cave", "emoji": "🐝", "description": "Cave shooters"})
        tags.change_game_tags(A, add=["cave", "shmups"])
        summary = tagui.summary([A, B, "nes/None.zip"])
        self.assertEqual(summary(0), [("🐝", "Cave", "Cave shooters"), ("🚀", "Shmups", "")])
        self.assertEqual(summary(1), [("🚀", "Shmups", "")])
        self.assertEqual(summary(2), [])

    def test_unknown_key_row(self):
        tags.change_game_tags("nes/Gone.zip", add=["cave"])
        self.assertEqual(tagui.column(["nes/Gone.zip"]), [("🐝", "")])

    def test_edit_game_tags_saves(self):
        seen = []

        def fake(title, labels, **kw):
            seen.append((labels, kw["initial"]))
            return [True, True]
        with mock.patch.object(picker, "filter_list", fake):
            self.assertTrue(tagui.edit_game_tags(B, "B"))
        self.assertEqual(seen, [(["🐝 Cave (0 games)", "🚀 Shmups (1 games)"], [False, True])])
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])

    def test_unchanged_returns_false(self):
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: kw["initial"]):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        with mock.patch.object(picker, "filter_list", return_value=None):
            self.assertFalse(tagui.edit_game_tags(B, "B"))

    def test_edit_game_tags_new_tag(self):
        calls = []

        def fake(title, labels, **kw):
            calls.append(labels)
            return ("n", None) if len(calls) == 1 else kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(ui, "ask", side_effect=["Pixel Art", "🎨"]):
            self.assertTrue(tagui.edit_game_tags(A, "A"))
        self.assertEqual(tags.all_tags()["pixel-art"], {"name": "Pixel Art", "emoji": "🎨"})
        self.assertEqual(tags.tags_of(A), ["pixel-art"])
        self.assertIn("🎨 Pixel Art (0 games)", calls[1])

    def test_new_tag_refused(self):
        for answers in (["", "🎨"], ["Pixel", ""], ["shmups", "🎨"], ["Pixel", "🐝"]):
            self.notes.clear()
            calls = []

            def fake(title, labels, **kw):
                calls.append(1)
                return ("n", None) if len(calls) == 1 else None
            with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", side_effect=answers):
                self.assertFalse(tagui.edit_game_tags(A, "A"))
            self.assertEqual(len(self.notes), 1, answers)
            self.assertEqual(list(tags.all_tags()), ["cave", "shmups"])

    def test_emoji_only_name_gets_its_own_message(self):
        calls = []
        with mock.patch.object(picker, "filter_list", lambda t, l, **kw: ("n", None) if not calls.append(1) and len(calls) == 1 else None), \
                mock.patch.object(ui, "ask", side_effect=["🎨", "🎨"]):
            self.assertFalse(tagui.edit_game_tags(A, "A"))
        self.assertIn("no letters or digits", self.notes[0])
        self.assertNotIn("already", self.notes[0])

    def test_unmounted_share_systemexit(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=[True, True]), \
                mock.patch.object(tags, "change_game_tags", side_effect=SystemExit("share not mounted")):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)
        self.assertIs(tags.load(), before)

    def test_edit_game_tags_storage_error(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=[True, True]), \
                mock.patch.object(tags, "change_game_tags", side_effect=OSError("down")):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)
        self.assertIs(tags.load(), before)
        self.assertEqual(tags.tags_of(B), ["shmups"])


    def test_saving_keeps_tags_another_machine_added(self):
        root = helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"},
                     "rpg": {"name": "RPG", "emoji": "🐉"}},
            "games": {B: {"tags": ["shmups"]}}, "declined": {}})
        tags.load()
        with open(os.path.join(root, tags.KEY), "w", encoding="utf-8") as f:  # another machine adds cave to B
            f.write(tags.dump({"tags": tags.load()["tags"], "games": {B: {"tags": ["cave", "shmups"]}}, "declined": {}}))
        with mock.patch.object(picker, "filter_list", return_value=[False, True, True]):  # rpg checked, cave unseen
            self.assertTrue(tagui.edit_game_tags(B, "B"))
        self.assertEqual(tags.tags_of(B), ["cave", "rpg", "shmups"])

    def test_malformed_tags_json_in_storage_is_noted(self):
        root = helpers.storage_tags(self, {"tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}},
                                           "games": {}, "declined": {}})
        tags.load()
        with open(os.path.join(root, tags.KEY), "w", encoding="utf-8") as f:  # broken after this run read it
            f.write("{nope")
        with mock.patch.object(picker, "filter_list", return_value=[True]):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)

    def test_a_disc_row_edits_its_games_record(self):
        helpers.storage_tags(self, {"tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
                                    "games": {B: {"tags": ["shmups"], "files": ["nes/B (Disc 2).zip"]}}, "declined": {}})
        seen = []

        def fake(title, labels, **kw):
            seen.append(kw["initial"])
            return [True, True]
        with mock.patch.object(picker, "filter_list", fake):
            self.assertTrue(tagui.edit_game_tags("nes/B (Disc 2).zip", "B"))
        self.assertEqual(seen, [[False, True]])
        self.assertEqual(set(tags.load()["games"]), {B})
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])


class TagFilterTest(unittest.TestCase):
    C = "nes/C (USA).zip"

    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"},
                     "rpg": {"name": "RPG", "emoji": "🐉"}},
            "games": {A: {"tags": ["shmups"], "files": ["nes/A.sav"]}, B: {"tags": ["cave", "shmups"]}},
            "declined": {}})
        self.notes = []
        self.enterContext(mock.patch.object(edit, "note", self.notes.append))

    def test_keep_needs_every_required_tag_and_none_of_the_excluded(self):
        f = tagui.TagFilter()
        self.assertTrue(all(f.keep(k) for k in (A, B, self.C)))
        f.required, f.excluded = {"shmups"}, {"cave"}
        self.assertEqual([k for k in (A, B, self.C) if f.keep(k)], [A])
        self.assertTrue(f.keep("nes/A.sav"))  # a file of a record counts as its game
        f.required = set()
        self.assertEqual([k for k in (A, B, self.C) if f.keep(k)], [A, self.C])  # untagged games aren't excluded
        f.clear()
        self.assertEqual((f.required, f.excluded), (set(), set()))
        self.assertTrue(all(f.keep(k) for k in (A, B, self.C)))

    def test_keep_follows_a_tag_change(self):
        f = tagui.TagFilter()
        f.required = {"shmups"}
        self.assertFalse(f.keep(self.C))
        tags.change_game_tags(self.C, add=["shmups"])
        self.assertTrue(f.keep(self.C))

    def test_describe(self):
        f = tagui.TagFilter()
        self.assertEqual(f.describe(), "")
        f.required, f.excluded = {"shmups"}, {"cave"}
        self.assertEqual(f.describe(), "✅ 🚀 Shmups · 🚫 🐝 Cave")

    def test_pick_cycles_a_tag_off_required_excluded_off_on_the_same_row(self):
        f, seen = tagui.TagFilter(), []
        answers = iter([1, 1, 1, None])

        def fake(title, labels, **kw):
            seen.append((labels, kw.get("cursor"), set(f.required), set(f.excluded)))
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            self.assertIsNone(f.pick({A, B, self.C}))
        self.assertEqual(seen[0][0], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)"])  # RPG has no game among the rows
        self.assertEqual(seen[1][0], ["⬜ 🐝 Cave (1)", "✅ 🚀 Shmups (2)"])
        self.assertEqual(seen[2][0], ["⬜ 🐝 Cave (1)", "🚫 🚀 Shmups (2)"])
        self.assertEqual(seen[3][0], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)"])
        self.assertEqual([s[1] for s in seen[1:]], [1, 1, 1])
        self.assertEqual([(s[2], s[3]) for s in seen[1:]], [({"shmups"}, set()), (set(), {"shmups"}), (set(), set())])
        self.assertEqual((f.required, f.excluded), (set(), set()))

    def test_pick_c_clears_and_reopens(self):
        f, calls = tagui.TagFilter(), []
        f.required, f.excluded = {"shmups"}, {"cave"}
        answers = iter([("c", 0), None])

        def fake(title, labels, **kw):
            calls.append(labels)
            self.assertIn("c", kw["hotkeys"])
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            f.pick({A, B})
        self.assertEqual(calls[1], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)"])
        self.assertEqual((f.required, f.excluded), (set(), set()))

    def test_pick_with_no_tag_among_the_rows_notes_it(self):
        f = tagui.TagFilter()
        with mock.patch.object(picker, "filter_list") as fl:
            f.pick({self.C})
        fl.assert_not_called()
        self.assertEqual(self.notes, ["ℹ️  No tag has games among these."])


if __name__ == "__main__":
    unittest.main()
