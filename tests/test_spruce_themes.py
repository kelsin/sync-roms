import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from sync_roms import external, inventory, runtime, spruce_themes, ui  # noqa: E402

PREFIX = runtime.SPRUCE_THEMES_PREFIX
NAME = "2CleanMini_by_Sheezie.7z"
FOLDER = "2CleanMini by Sheezie"


def asset(name=NAME, updated="2026-01-01T00:00:00Z", size=10):
    return {"name": name, "size": size, "updated_at": updated, "browser_download_url": f"https://example.invalid/{name}"}


class Themes(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.warned = []
        self.enterContext(mock.patch.object(ui, "warn", self.warned.append))
        self.enterContext(mock.patch.object(external, "find_tool", return_value="/bin/7z"))
        self.archives = {}  # asset name -> (folder or None, {rel: bytes})
        self.downloads = []

    def run_update(self, assets, dry_run=False):
        def download(url, path):
            self.downloads.append(url)
            with open(path, "wb") as f:
                f.write(url.encode())

        def unpack(archive, out):
            with open(archive) as f:
                name = f.read().rsplit("/", 1)[1]
            folder, files = self.archives[name]
            for rel, data in files.items():
                path = os.path.join(out, "mnt", "SDCARD", "Themes", folder or "x", rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
            return folder
        with mock.patch.object(spruce_themes, "_release", return_value=assets), \
                mock.patch.object(spruce_themes, "_download", download), \
                mock.patch.object(spruce_themes, "_unpack", unpack), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.out = out
            return spruce_themes.update_storage(dry_run)

    def state(self):
        return self.read_json(runtime.SPRUCE_THEMES_STATE)

    def exists(self, key):
        return os.path.exists(os.path.join(self.root, key))

    def test_new_asset_uploaded(self):
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertEqual(self.state(), {NAME: {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER}})

    def test_unchanged_asset_skipped(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER}}).encode())
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertEqual(self.downloads, [])

    def test_changed_asset_replaces_folder(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "old", "size": 10, "folder": FOLDER}}).encode())
        self.put(f"{PREFIX}{FOLDER}/old.png")
        self.archives[NAME] = (FOLDER, {"new.png": b"n", "sub/a.png": b"a"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/old.png"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/new.png"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/sub/a.png"))

    def test_removed_asset_folder_deleted(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.put(f"{PREFIX}Gone/config.json")
        self.assertEqual(self.run_update([]), 0)
        self.assertFalse(self.exists(f"{PREFIX}Gone/config.json"))
        self.assertEqual(self.state(), {})

    def test_custom_folder_untouched(self):
        self.put(f"{PREFIX}Mine/config.json")
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.run_update([asset()])
        self.assertTrue(self.exists(f"{PREFIX}Mine/config.json"))

    def test_release_folder_matching_custom_folder_skipped(self):
        self.put(f"{PREFIX}{FOLDER}/mine.png")
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 1)
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/mine.png"))
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertFalse(self.exists(runtime.SPRUCE_THEMES_STATE) and self.state())
        self.assertIn(FOLDER, self.warned[0])

    def test_folder_recorded_for_another_asset_skipped(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Other.7z": {"updated_at": "x", "size": 1, "folder": FOLDER}}).encode())
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset(), asset("Other.7z", "x", 1)]), 1)
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/config.json"))

    def test_folder_renamed_inside_updated_asset(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "old", "size": 10, "folder": "Old Name"}}).encode())
        self.put(f"{PREFIX}Old Name/config.json")
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertFalse(self.exists(f"{PREFIX}Old Name/config.json"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertEqual(self.state()[NAME]["folder"], FOLDER)

    def test_malformed_state_entry_is_ignored(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Bad.7z": {"size": 1}}).encode())
        self.assertEqual(self.run_update([]), 0)

    def test_bad_member_paths_skipped(self):
        self.archives["Bad.7z"] = (None, {"a": b"a"})
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset("Bad.7z"), asset()]), 1)
        self.assertEqual(self.state().keys(), {NAME})
        self.assertFalse(self.exists(f"{PREFIX}x"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertIn("Bad.7z", self.warned[0])

    def test_dry_run_changes_nothing(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.put(f"{PREFIX}Gone/config.json")
        self.assertEqual(self.run_update([asset()], dry_run=True), 0)
        text = self.out.getvalue()
        self.assertIn(f"{NAME}: add", text)
        self.assertIn("Gone.7z: remove", text)
        self.assertTrue(self.exists(f"{PREFIX}Gone/config.json"))
        self.assertEqual(list(self.state()), ["Gone.7z"])
        self.assertEqual(self.downloads, [])

    def test_no_7z_warns(self):
        with mock.patch.object(external, "find_tool", return_value=None):
            self.assertEqual(self.run_update([asset()]), 1)
        self.assertIn("sync-roms tools install", self.warned[0])
        self.assertFalse(self.exists(runtime.SPRUCE_THEMES_STATE))

    def test_unmounted_root_changes_nothing(self):
        gone = os.path.join(self.root, "gone")
        with mock.patch.object(runtime, "ROOT", gone):
            self.assertEqual(self.run_update([asset()]), 1)
        self.assertFalse(os.path.exists(gone))
        self.assertEqual(self.downloads, [])


if __name__ == "__main__":
    unittest.main()
