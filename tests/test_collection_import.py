import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import Cmd  # noqa: E402
from sync_roms import collection_import, collections, ui  # noqa: E402

RUBY = {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}
EMERALD = {"title": "Emerald", "system": "gba", "bucket": "gba/Emerald.zip"}
FF7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]}


def write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


class ReadTest(Cmd):
    def test_valid_file(self):
        p = self.path("in.json")
        write(p, {"name": "Couch", "description": "d", "art": "rpg", "games": [RUBY]})
        self.assertEqual(collection_import.read(p), {"name": "Couch", "description": "d", "art": "rpg", "games": [RUBY]})

    def test_missing_name_or_list_or_bad_json_raise(self):
        p = self.path("in.json")
        for data in ({"games": []}, [], {"name": "X", "games": None}, "{"):
            write(p, data)
            with self.assertRaises(ValueError):
                collection_import.read(p)
        with self.assertRaises(ValueError):
            collection_import.read(self.path("missing.json"))

    def test_malformed_games_dropped(self):
        p = self.path("in.json")
        write(p, {"name": "Couch", "games": [RUBY, {"system": "gba"}, 5]})
        with mock.patch.object(ui, "warn") as warn:
            self.assertEqual(collection_import.read(p)["games"], [RUBY])
        warn.assert_called_once()


class MergeTest(unittest.TestCase):
    def test_differences_by_bucket_in_order(self):
        mine = {"name": "M", "games": [RUBY, EMERALD]}
        theirs = {"name": "T", "games": [FF7, {**RUBY, "note": "x"}]}
        self.assertEqual(collection_import.differences(mine, theirs), ([FF7], [EMERALD]))

    def test_merged_appends_keeps_mine_and_files(self):
        mine = {"id": "m", "name": "M", "description": "mine", "art": "rpg", "games": [{**RUBY, "note": "mine"}]}
        theirs = {"name": "T", "description": "theirs", "games": [{**RUBY, "note": "theirs"}, FF7]}
        before = json.dumps([mine, theirs])
        out = collection_import.merged(mine, theirs)
        self.assertEqual(out, {"id": "m", "name": "M", "description": "mine", "art": "rpg",
                               "games": [{**RUBY, "note": "mine"}, FF7]})
        self.assertEqual(out["games"][1]["files"], FF7["files"])
        self.assertEqual(json.dumps([mine, theirs]), before)


class ImportCmdTest(Cmd):
    def setUp(self):
        super().setUp()
        self.file = self.path("Couch (1).json")
        write(self.file, {"name": "Couch", "games": [RUBY, FF7]})

    def mine(self):
        collections.save_collection({"id": "couch", "name": "Couch", "description": "my desc",
                                     "games": [{**RUBY, "note": "keep"}, EMERALD]})

    def answer(self, *answers, terminal=True):
        self.enterContext(mock.patch.object(ui, "has_terminal", return_value=terminal))
        self.enterContext(mock.patch.object(ui, "_input", side_effect=list(answers)))

    def test_free_id_imported_under_slug_of_name(self):
        code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("Imported Couch", out)
        self.assertEqual(self.read("collections/couch.json"), {"name": "Couch", "games": [RUBY, FF7]})

    def test_taken_yes_merges(self):
        self.mine()
        code, out, _ = self.run_cmd("collections", "import", self.file, "--yes")
        self.assertEqual(code, 0)
        self.assertIn("Only in the file (1):", out)
        self.assertIn("PlayStation: FF7", out)
        self.assertIn("Only in yours (1):", out)
        self.assertIn("Game Boy Advance: Emerald", out)
        self.assertIn("Merged 1 games into Couch", out)
        self.assertEqual(self.read("collections/couch.json"),
                         {"name": "Couch", "description": "my desc", "games": [{**RUBY, "note": "keep"}, EMERALD, FF7]})

    def test_taken_replace_keeps_backup(self):
        self.mine()
        self.answer("r")
        code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("Replaced Couch", out)
        self.assertEqual(self.read("collections/couch.json"), {"name": "Couch", "games": [RUBY, FF7]})
        self.assertEqual(self.read("collections/couch.json.bak")["description"], "my desc")

    def test_taken_rename_reasks_until_free(self):
        self.mine()
        self.answer("n", "couch", "Sofa")
        with mock.patch.object(ui, "warn") as warn:
            code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("already a collection", warn.call_args_list[0][0][0])
        self.assertIn("Imported Sofa", out)
        self.assertEqual(self.read("collections/sofa.json"), {"name": "Sofa", "games": [RUBY, FF7]})
        self.assertEqual(self.read("collections/couch.json")["description"], "my desc")

    def test_taken_rename_empty_skips(self):
        self.mine()
        self.answer("n", "")
        code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("Skipped Couch", out)
        self.assertEqual(sorted(os.listdir(self.path("collections"))), ["couch.json"])

    def test_taken_skip(self):
        self.mine()
        before = self.read("collections/couch.json")
        self.answer("s")
        code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("Skipped Couch", out)
        self.assertEqual(self.read("collections/couch.json"), before)

    def test_identical_doesnt_ask(self):
        collections.save_collection({"id": "couch", "name": "Couch", "games": [RUBY, FF7]})
        self.answer()
        code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("nothing differs", out)
        self.assertIn("Skipped Couch", out)

    def test_taken_without_terminal_warns_and_skips(self):
        self.mine()
        before = self.read("collections/couch.json")
        self.answer(terminal=False)
        code, out, err = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("--yes", err)
        self.assertIn("Skipped Couch", out)
        self.assertEqual(self.read("collections/couch.json"), before)

    def test_dry_run_writes_nothing(self):
        other = self.path("other.json")
        write(other, {"name": "Party", "games": [EMERALD]})
        self.mine()
        before = self.read("collections/couch.json")
        code, out, _ = self.run_cmd("collections", "import", self.file, other, "--dry-run", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("Would merge 1 games into Couch", out)
        self.assertIn("Would import Party", out)
        self.assertEqual(self.read("collections/couch.json"), before)
        self.assertEqual(sorted(os.listdir(self.path("collections"))), ["couch.json"])

    def test_same_run_sees_earlier_files(self):
        other = self.path("again.json")
        write(other, {"name": "Couch", "games": [RUBY, FF7]})
        code, out, _ = self.run_cmd("collections", "import", self.file, other)
        self.assertEqual(code, 0)
        self.assertIn("Imported Couch", out)
        self.assertIn("nothing differs", out)

    def test_surprise_name_skipped(self):
        write(self.file, {"name": "Surprise", "games": []})
        with mock.patch.object(ui, "warn") as warn:
            code, out, _ = self.run_cmd("collections", "import", self.file)
        self.assertEqual(code, 0)
        self.assertIn("Surprise is used", warn.call_args[0][0])
        self.assertIn("Skipped Surprise", out)
        self.assertFalse(os.path.exists(self.path("collections")))

    def test_every_file_unreadable_exits_2(self):
        write(self.file, "{")
        code, _, err = self.run_cmd("collections", "import", self.file, self.path("missing.json"))
        self.assertEqual(code, 2)
        self.assertIn("Couch (1).json", err)

    def test_one_readable_file_exits_0(self):
        code = self.run_cmd("collections", "import", self.file, self.path("missing.json"))[0]
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
