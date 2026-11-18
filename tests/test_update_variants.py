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
from helpers import StorageDir  # noqa: E402

from sync_roms import inventory, store, usersettings  # noqa: E402

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


class FindCandidates(CheckedInStorage):
    def run_find(self, *argv):
        # only main()'s own check sees a cache; later calls (the cache patch after a write) see none
        stored = ["gba/New.zip", "gba/Seen.zip"]
        with mock.patch.object(sys, "argv", ["find_candidates.py", *argv]), \
                mock.patch.object(inventory, "current", side_effect=itertools.chain([object()], itertools.repeat(None))), \
                mock.patch.object(inventory, "files", side_effect=lambda p, sizes=True: stored if p == "gba/" else []), \
                mock.patch.object(store, "repo_set_files", return_value=[]), \
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
