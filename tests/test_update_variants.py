import contextlib
import importlib.util
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
from helpers import StorageDir, storage_sets  # noqa: E402

from sync_roms import inventory, runtime, shared, store, usersettings  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "update-variants", "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


find_candidates = load("find_candidates")
apply_variants = load("apply_variants")


class CheckedInStorage(StorageDir):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(usersettings, "apply_settings")
        p.start()
        self.addCleanup(p.stop)

    def checked(self):
        with open(os.path.join(self.root, "variants-checked.json")) as f:
            return json.load(f)


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


class ApplyVariantsToSets(CheckedInStorage):
    SET = {"name": "S", "games": [{"title": "A", "system": "gba", "bucket": "gba/A.zip"}]}

    def setUp(self):
        super().setUp()
        storage_sets(self, {"s": self.SET, "t": {"name": "T", "games": []}}, self.root)

    def text(self, set_id):
        with open(os.path.join(self.root, "sets", f"{set_id}.json"), encoding="utf-8") as f:
            return f.read()

    def run_apply(self, decisions):
        path = os.path.join(self.tmp.name, "decisions.json")
        with open(path, "w") as f:
            json.dump(decisions, f)
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            apply_variants.main(path)
        return out.getvalue()

    def test_a_variant_is_written_to_the_set_in_storage_and_its_local_copy(self):
        before = self.text("t")
        out = self.run_apply({"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour"}]})
        want = {**self.SET, "games": [{**self.SET["games"][0],
                                       "variants": [{"bucket": "gba/A DX.zip", "note": "GBA: adds colour"}]}]}
        self.assertEqual(self.text("s"), store.set_text(want))
        with open(shared.local_path("sets/s.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), store.set_text(want))
        self.assertEqual(self.text("t"), before)
        self.assertIn("Sets changed: s", out)
        self.assertEqual(store.set_files()[0]["games"], want["games"])
        self.assertEqual(self.checked(), {"gba/A DX.zip": "variant of gba/A.zip"})

    def test_an_unmounted_storage_folder_writes_nothing(self):
        before = self.text("s")
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), self.assertRaises(SystemExit) as e:
            self.run_apply({"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour"}],
                            "checked": {"gba/B.zip": "no"}})
        self.assertIn("is missing", str(e.exception))
        self.assertEqual(self.text("s"), before)
        self.assertFalse(os.path.exists(os.path.join(self.root, "variants-checked.json")))
        self.assertFalse(os.path.exists(self.root + "-unmounted"))


class ApplyVariantsStale(ApplyVariantsToSets):
    ADD = {"add": [{"game": "gba/A.zip", "bucket": "gba/A DX.zip", "note": "GBA: adds colour"}], "checked": {"gba/B.zip": "no"}}

    def test_sets_read_from_the_local_copies_change_nothing(self):
        before = self.text("s")
        with mock.patch.object(store, "sets_from_fallback", return_value=True), self.assertRaises(SystemExit) as e:
            self.run_apply(self.ADD)
        self.assertIn("local copies", str(e.exception))
        self.assertEqual(self.text("s"), before)
        self.assertFalse(os.path.exists(os.path.join(self.root, "variants-checked.json")))

    def test_a_set_changed_in_storage_while_it_ran_changes_nothing(self):
        theirs = store.set_text({"name": "S", "games": [{"title": "A", "system": "gba", "bucket": "gba/A.zip"},
                                                        {"title": "B", "system": "gba", "bucket": "gba/B.zip"}]})
        real = store.set_files

        def read_then_change():  # another machine saves the set after this run read it
            out = real()
            with open(os.path.join(self.root, "sets", "s.json"), "w", encoding="utf-8") as f:
                f.write(theirs)
            return out
        with mock.patch.object(store, "set_files", side_effect=read_then_change), self.assertRaises(SystemExit) as e:
            self.run_apply(self.ADD)
        self.assertIn("s changed in storage", str(e.exception))
        self.assertEqual(self.text("s"), theirs)
        self.assertFalse(os.path.exists(os.path.join(self.root, "variants-checked.json")))

    def test_a_storage_error_while_checking_changes_nothing(self):
        before = self.text("s")
        store.set_files()  # read (and their local copies saved) before storage stops answering
        with mock.patch.object(shared, "read", side_effect=OSError("timed out")), self.assertRaises(SystemExit) as e:
            self.run_apply(self.ADD)
        self.assertIn("timed out", str(e.exception))
        self.assertEqual(self.text("s"), before)


class FindCandidates(CheckedInStorage):
    def run_find(self, *argv):
        # only main()'s own check sees a cache; later calls (the cache patch after a write) see none
        stored = ["gba/New.zip", "gba/Seen.zip"]
        with mock.patch.object(sys, "argv", ["find_candidates.py", *argv]), \
                mock.patch.object(inventory, "current", side_effect=itertools.chain([object()], itertools.repeat(None))), \
                mock.patch.object(inventory, "files", side_effect=lambda p, sizes=True: stored if p == "gba/" else []), \
                mock.patch.object(store, "set_files", return_value=[]), \
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


if __name__ == "__main__":
    unittest.main()
