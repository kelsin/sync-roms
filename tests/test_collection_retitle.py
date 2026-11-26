import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import collection_retitle, collections, commands, scrape_plan, s3  # noqa: E402

SMW = "snes/Super Mario World (USA).zip"


class Retitle(helpers.DataDir):
    def setUp(self):
        super().setUp()
        meta = {"snes": {"Super Mario World (USA).zip": {"name": "Super Mario World"}}}
        self.enterContext(mock.patch.object(scrape_plan, "load_metadata", lambda system, fresh=False: meta.get(system, {})))

    def save(self, cid, games):
        collections.save_collection({"id": cid, "name": cid, "description": "d", "games": games})

    def titles(self, cid):
        return [g["title"] for c in collections.load_collections() if c["id"] == cid for g in c["games"]]

    def run_cmd(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = commands.run(["collections", "retitle", *args])
        return code, out.getvalue()

    def test_updates_from_metadata_and_falls_back(self):
        self.save("a", [{"system": "snes", "bucket": SMW, "title": "Super Mario World (USA)", "note": "n", "files": ["snes/x.zip"]},
                        {"system": "snes", "bucket": "snes/Other (USA).sfc", "title": "old"}])
        code, out = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertEqual(self.titles("a"), ["Super Mario World", "Other (USA)"])
        self.assertIn("Super Mario World (USA) -> Super Mario World", out)
        self.assertIn("Retitled 2 game", out)
        game = collections.load_collections()[0]["games"][0]
        self.assertEqual((game["note"], game["files"]), ("n", ["snes/x.zip"]))

    def test_untouched_collection_not_rewritten(self):
        self.save("b", [{"system": "snes", "bucket": SMW, "title": "Super Mario World"}])
        with mock.patch.object(collections, "save_collection") as save:
            self.run_cmd()
        save.assert_not_called()

    def test_dry_run_writes_nothing(self):
        self.save("a", [{"system": "snes", "bucket": SMW, "title": "x"}])
        with mock.patch.object(collections, "save_collection") as save:
            code, out = self.run_cmd("--dry-run")
        save.assert_not_called()
        self.assertIn("Would retitle 1 game", out)
        self.assertEqual(self.titles("a"), ["x"])

    def test_unreachable_storage_fails(self):
        self.save("a", [{"system": "snes", "bucket": SMW, "title": "x"}])
        with mock.patch.object(scrape_plan, "load_metadata", side_effect=OSError("gone")), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cmd()
        self.assertEqual(self.titles("a"), ["x"])

    def test_refresh_runs_it_after_scrape_clean(self):
        steps = list(commands.REFRESH_STEPS)
        self.assertEqual(steps[steps.index(["scrape", "clean", "--yes"]) + 1], ["collections", "retitle"])


if __name__ == "__main__":
    unittest.main()
