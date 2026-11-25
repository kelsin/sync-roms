import contextlib
import io
import itertools
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import ScriptDir, load_script, storage_tags  # noqa: E402

from sync_roms import inventory, runtime, scrape_plan, tags  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "update-variants", "scripts")


find_candidates = load_script(os.path.join(SCRIPTS, "find_candidates.py"))
apply_variants = load_script(os.path.join(SCRIPTS, "apply_variants.py"))


class CheckedInStorage(ScriptDir):
    def checked(self):
        with open(os.path.join(self.root, "variants-checked.json")) as f:
            text = f.read()
        self.assertEqual(text, scrape_plan.dump_json(json.loads(text)))  # as the other shared storage files are written
        return json.loads(text)


class ApplyVariants(CheckedInStorage):
    def run_apply(self, decisions):
        path = os.path.join(self.tmp.name, "decisions.json")
        with open(path, "w") as f:
            json.dump(decisions, f)
        with contextlib.redirect_stdout(io.StringIO()):
            apply_variants.main(path)

    def test_checked_written_to_storage(self):
        self.run_apply({"checked": {"gba/A.zip": "not a variant"}})
        self.assertEqual(self.checked(), {"gba/A.zip": "not a variant"})
        self.assertFalse(os.path.exists(os.path.join(self.data, "variants-checked.json")))

    def test_merges_with_existing_storage_file(self):
        self.put("variants-checked.json", json.dumps({"gba/Old.zip": "old"}).encode())
        self.run_apply({"checked": {"gba/A.zip": "x"}})
        self.assertEqual(self.checked(), {"gba/A.zip": "x", "gba/Old.zip": "old"})


class ApplyVariantsToTags(CheckedInStorage):
    DATA = {"tags": {"rpg": {"name": "RPG", "emoji": "🗡️"}}, "declined": {},
            "games": {"gba/A.zip": {"tags": ["rpg"]}, "gba/B.zip": {"tags": ["rpg"], "variants": [
                {"bucket": "gba/B Old.zip", "note": "GBA: gone"}, {"bucket": "gba/B DX.zip", "note": "GBA: kept"}]}}}

    def setUp(self):
        super().setUp()
        storage_tags(self, self.DATA, self.root)

    def text(self):
        with open(os.path.join(self.root, tags.KEY), encoding="utf-8") as f:
            return f.read()

    def run_apply(self, decisions):
        path = os.path.join(self.tmp.name, "decisions.json")
        with open(path, "w") as f:
            json.dump(decisions, f)
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            apply_variants.main(path)
        return out.getvalue()

    def test_a_variant_is_added_to_the_record_in_tags_json(self):
        out = self.run_apply({"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour",
                                       "files": ["gba/A DX 2.zip"]}],
                              "remove": [{"game": "gba/B.zip", "bucket": "gba/B Old.zip"}]})
        games = tags.parse(self.text())["games"]
        self.assertEqual(games["gba/A.zip"], {"tags": ["rpg"], "variants": [
            {"bucket": "gba/A DX.zip", "note": "GBA: adds colour", "files": ["gba/A DX 2.zip"]}]})
        self.assertEqual(games["gba/B.zip"]["variants"], [{"bucket": "gba/B DX.zip", "note": "GBA: kept"}])
        self.assertIn("Games changed: gba/A.zip, gba/B.zip", out)
        self.assertEqual(self.checked(), {"gba/A DX.zip": "variant of gba/A.zip", "gba/A DX 2.zip": "variant of gba/A.zip"})

    def test_a_variant_already_there_changes_nothing(self):
        before = self.text()
        out = self.run_apply({"add": [{"game": "gba/B.zip", "bucket": "gba/B DX.zip", "note": "other"}]})
        self.assertEqual(self.text(), before)
        self.assertIn("Games changed: none", out)

    def test_a_game_with_no_record_is_skipped_and_reported(self):
        before = self.text()
        out = self.run_apply({"add": [{"game": "gba/Z.zip", "bucket": "gba/Z DX.zip", "note": "x"}],
                              "checked": {"gba/C.zip": "no"}})
        self.assertIn("No tags.json record, skipped: gba/Z.zip", out)
        self.assertEqual(self.text(), before)
        self.assertEqual(self.checked(), {"gba/C.zip": "no"})  # the skipped variant isn't recorded as judged

    def test_another_machines_edits_made_while_it_ran_are_kept(self):
        tags.load()  # this run's read
        theirs = json.loads(json.dumps(self.DATA))
        theirs["games"]["gba/B.zip"]["variants"].append({"bucket": "gba/B Theirs.zip", "note": "GBA: theirs"})
        del theirs["games"]["gba/A.zip"]  # untagged on the other machine
        with open(os.path.join(self.root, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump(theirs))
        out = self.run_apply({"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour"},
                                      {"game": "gba/B.zip", "bucket": "gba/B New.zip", "note": "GBA: new"}],
                              "remove": [{"game": "gba/B.zip", "bucket": "gba/B Old.zip"}]})
        games = tags.parse(self.text())["games"]
        self.assertNotIn("gba/A.zip", games)  # not recreated
        self.assertEqual([v["bucket"] for v in games["gba/B.zip"]["variants"]],
                         ["gba/B DX.zip", "gba/B Theirs.zip", "gba/B New.zip"])
        self.assertIn("Games changed: gba/B.zip", out)
        self.assertIn("No tags.json record, skipped: gba/A.zip", out)

    def test_an_unmounted_storage_folder_writes_nothing(self):
        before = self.text()
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), self.assertRaises(SystemExit) as e:
            self.run_apply({"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour"}],
                            "checked": {"gba/B.zip": "no"}})
        self.assertIn("is missing", str(e.exception))
        self.assertEqual(self.text(), before)
        self.assertFalse(os.path.exists(os.path.join(self.root, "variants-checked.json")))
        self.assertFalse(os.path.exists(self.root + "-unmounted"))


class FindCandidates(CheckedInStorage):
    def run_find(self, *argv, stored=("gba/New.zip", "gba/Seen.zip")):
        # only main()'s own check sees a cache; later calls (the cache patch after a write) see none
        with mock.patch.object(sys, "argv", ["find_candidates.py", *argv]), \
                mock.patch.object(inventory, "current", side_effect=itertools.chain([object()], itertools.repeat(None))), \
                mock.patch.object(inventory, "files", side_effect=lambda p, sizes=True: [k for k in stored if k.startswith(p)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            find_candidates.main()
        return out.getvalue()

    def test_baseline_marks_unlisted_in_storage(self):
        self.put("variants-checked.json", json.dumps({"gba/Seen.zip": "judged"}).encode())
        self.run_find("--baseline")
        checked = self.checked()
        self.assertEqual(checked["gba/Seen.zip"], "judged")
        self.assertIn("baseline", checked["gba/New.zip"])

    def test_checked_file_reported_as_storage_key(self):
        out = json.loads(self.run_find())
        self.assertEqual(out["checked_file"], "variants-checked.json")

    def test_matches_and_stale_variants_come_from_the_tag_records(self):
        storage_tags(self, {"tags": {"rpg": {"name": "RPG", "emoji": "🗡️"}}, "declined": {}, "games": {
            "gba/Hero (USA).zip": {"tags": ["rpg"], "variants": [{"bucket": "gba/Hero Gone.zip", "note": "n"}]}}},
            self.root)
        out = json.loads(self.run_find(stored=["gba/Hero (USA).zip", "gba/Hero (Europe).zip", "gba/Other.zip"]))
        self.assertEqual(out["matches"], [{"game": "gba/Hero (USA).zip", "title": "Hero (USA)", "system": "gba",
                                           "tags": ["rpg"], "variants": [{"bucket": "gba/Hero Gone.zip", "note": "n"}],
                                           "candidates": [{"bucket": "gba/Hero (Europe).zip", "title": "Hero (Europe)"}]}])
        self.assertEqual(out["stale"], [{"game": "gba/Hero (USA).zip", "bucket": "gba/Hero Gone.zip"}])
        self.assertEqual(out["unmatched"], 1)


if __name__ == "__main__":
    unittest.main()
