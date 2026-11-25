import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import cli, commands, edit, picker, store, tageditor, tags, ui  # noqa: E402

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

    def test_art_picks_through_the_collection_picker(self):
        def pick(collection):
            collection["art"] = "surprise"
        with mock.patch.object(tageditor, "pick_art", pick):
            self.run_editor(["Shmups", "art", None, None])
        self.assertEqual(tags.all_tags()["shmups"]["art"], "surprise")

    def test_merge_into_another_tag(self):
        self.run_editor(["Shmups", "Merge", "Cave"], confirms=[True])
        self.assertNotIn("shmups", tags.all_tags())
        self.assertEqual(tags.tags_of(B), ["cave"])
        self.assertEqual(tags.tags_of(A), ["cave"])

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
        def add(listing, shown, keys_of, label):
            listing["games"].append({"system": "nes", "bucket": B, "files": ["nes/B (Disc 2).zip"]})
        with mock.patch.object(tageditor, "add_from_tag", add):
            self.run_editor(["Cave", "from another tag", None, None])
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])
        self.assertEqual(tags.record(B)["files"], ["nes/B (Disc 2).zip"])

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
        self.assertEqual(commands.second_words()["tags"], ["edit"])
        self.assertEqual(cli.canonical("tag"), "tags")

    def test_sets_edit_is_gone(self):
        self.assertNotIn("sets", commands.COMMANDS)
        self.assertNotIn("sets", cli.SUBCOMMANDS)
        self.assertEqual(cli.canonical("set"), "set")
        with self.assertRaises(SystemExit):
            commands.run(["sets", "edit"])


if __name__ == "__main__":
    unittest.main()
