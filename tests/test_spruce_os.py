import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import s3, spruce_os, store  # noqa: E402

P = "os/spruceos/"
V46 = "spruceV4.6.0.7z"


class Newest(unittest.TestCase):
    def test_newest_compares_versions_as_numbers(self):
        listing = {P + n: 1 for n in ("spruceV4.6.0.7z", "spruceV4.10.0.7z", "spruceOTA-v4.5.6-to-v4.6.0.7z",
                                      "spruceos-installer-windows.exe", "old/spruceV9.0.0.7z")}
        self.assertEqual(spruce_os.newest(listing), P + "spruceV4.10.0.7z")
        self.assertIsNone(spruce_os.newest({}))


class Install(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)
        store.update_card("c", layout="spruce")

    def cp(self, *parts):
        return os.path.join(self.card, *parts)

    def run_install(self, layout="spruce", dry_run=False, **kw):
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = spruce_os.install("c", layout, self.card, dry_run, **kw)
        return out.getvalue()

    def recorded(self):
        return (store.load_cards().get("c") or {}).get("spruce_os")

    def snapshot(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.card) for f in fs)

    def touch(self, path, data=b"x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def test_other_layouts_get_nothing(self):
        self.put(P + V46, b"new")
        self.run_install("onion")
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())

    def test_no_release_in_storage_does_nothing(self):
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [])

    def test_stages_the_newest_7z_at_the_card_root(self):
        self.put(P + V46, b"new")
        wrote = []
        out = self.run_install(wrote=wrote)
        self.assertEqual(wrote, [self.cp(V46)])
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [V46])
        with open(self.cp(V46), "rb") as f:
            self.assertEqual(f.read(), b"new")
        self.assertEqual(self.recorded(), V46)
        self.assertIn(V46, out)
        self.assertIn("EZ Updater", out)
        self.assertIn(f"🌲 Staging spruceOS {V46} (3 B)…", out)

    def test_stages_nothing_without_room_for_it(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.put(P + V46, b"new")
        with mock.patch.object(spruce_os.downloads, "free_space", return_value=spruce_os.MARGIN + 2):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertEqual(os.listdir(self.card), ["spruceV4.5.6.7z"])
        self.assertEqual(self.recorded(), "spruceV4.5.6.7z")
        self.assertIn(V46, self.err.getvalue())
        self.assertIn("64.0 MB", self.err.getvalue())

    def test_a_file_already_on_the_card_needs_no_room(self):
        self.put(P + V46, b"new")
        self.touch(self.cp(V46), b"abc")
        with mock.patch.object(spruce_os.downloads, "free_space", return_value=0):
            self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.recorded(), V46)

    def test_no_delete_keeps_the_old_staged_file(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.put(P + V46, b"new")
        out = self.run_install(keep=True)
        self.assertEqual(sorted(os.listdir(self.card)), ["spruceV4.5.6.7z", V46])
        self.assertEqual(self.recorded(), V46)
        self.assertIn("keeping", out)
        self.assertIn("spruceV4.5.6.7z", out)

    def test_once_per_version_even_after_the_updater_removed_it(self):
        self.put(P + V46, b"new")
        store.update_card("c", spruce_os=V46)
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [])

    def test_same_file_already_on_the_card_is_recorded_without_copying(self):
        self.put(P + V46, b"new")
        self.touch(self.cp(V46), b"abc")
        with mock.patch.object(s3, "download") as dl:
            self.run_install()
        dl.assert_not_called()
        self.assertEqual(self.recorded(), V46)
        with open(self.cp(V46), "rb") as f:
            self.assertEqual(f.read(), b"abc")

    def test_newer_version_removes_only_the_one_sync_staged(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.touch(self.cp("spruceV4.0.0.7z"))
        self.put(P + V46, b"new")
        self.run_install()
        self.assertEqual(sorted(os.listdir(self.card)), ["spruceV4.0.0.7z", V46])

    def test_recorded_name_outside_the_pattern_is_never_removed(self):
        self.put(P + V46, b"new")
        outside = os.path.join(self.tmp.name, "outside.7z")
        for record, path in (("Roms", self.cp("Roms", "game.zip")), ("../outside.7z", outside)):
            with self.subTest(record):
                self.touch(path)
                store.update_card("c", spruce_os=record)
                self.run_install()
                self.assertTrue(os.path.isfile(path))

    def test_dry_run_writes_nothing(self):
        self.put(P + V46, b"new")
        out = self.run_install(dry_run=True)
        self.assertIn("Dry run", out)
        self.assertIn(f"{V46} (3 B)", out)
        self.assertNotIn("delete", out)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())

    def test_dry_run_says_it_would_delete_the_old_staged_file(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.put(P + V46, b"new")
        out = self.run_install(dry_run=True)
        self.assertIn("and delete spruceV4.5.6.7z", out)
        self.assertEqual(os.listdir(self.card), ["spruceV4.5.6.7z"])
        self.assertIn("keeping spruceV4.5.6.7z", self.run_install(dry_run=True, keep=True))

    def test_failed_copy_warns_and_keeps_the_old_file(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.put(P + V46, b"new")
        with mock.patch.object(s3, "download", side_effect=OSError("No space left")):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertEqual(self.recorded(), "spruceV4.5.6.7z")
        self.assertEqual(os.listdir(self.card), ["spruceV4.5.6.7z"])


if __name__ == "__main__":
    unittest.main()
