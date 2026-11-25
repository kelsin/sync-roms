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
        tags.set_game_tags(A, ["cave", "shmups"])
        self.assertEqual(tagui.column([A, B]), [("🐝🚀", ""), ("🚀", "")])
        with mock.patch.object(tags, "emoji_of", return_value="12345678"):
            self.assertEqual(tagui.column([A]), [("12345678", "")])

    def test_unknown_key_row(self):
        tags.set_game_tags("nes/Gone.zip", ["cave"])
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

    def test_edit_game_tags_storage_error(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=[True, True]), \
                mock.patch.object(tags, "set_game_tags", side_effect=OSError("down")):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)
        self.assertIs(tags.load(), before)
        self.assertEqual(tags.tags_of(B), ["shmups"])


if __name__ == "__main__":
    unittest.main()
