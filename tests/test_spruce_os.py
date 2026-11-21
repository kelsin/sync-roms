import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import spruce_os, store  # noqa: E402

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

    def run_install(self, layout="spruce", dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.failures = spruce_os.install("c", layout, self.card, dry_run)
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
        out = self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [V46])
        with open(self.cp(V46), "rb") as f:
            self.assertEqual(f.read(), b"new")
        self.assertEqual(self.recorded(), V46)
        self.assertIn(V46, out)
        self.assertIn("EZ Updater", out)

    def test_once_per_version_even_after_the_updater_removed_it(self):
        self.put(P + V46, b"new")
        store.update_card("c", spruce_os=V46)
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(os.listdir(self.card), [])

    def test_same_file_already_on_the_card_is_recorded_without_copying(self):
        self.put(P + V46, b"new")
        self.touch(self.cp(V46), b"abc")
        with mock.patch.object(spruce_os.s3, "download") as dl:
            self.run_install()
        dl.assert_not_called()
        self.assertEqual(self.recorded(), V46)

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
        self.assertIn(V46, out)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())

    def test_failed_copy_warns_and_keeps_the_old_file(self):
        store.update_card("c", spruce_os="spruceV4.5.6.7z")
        self.touch(self.cp("spruceV4.5.6.7z"))
        self.put(P + V46, b"new")
        with mock.patch.object(spruce_os.s3, "download", side_effect=OSError("No space left")):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertEqual(self.recorded(), "spruceV4.5.6.7z")
        self.assertEqual(os.listdir(self.card), ["spruceV4.5.6.7z"])


if __name__ == "__main__":
    unittest.main()
