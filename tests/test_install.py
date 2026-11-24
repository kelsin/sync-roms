import argparse
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import external, install, store  # noqa: E402

P = "os/spruceos/"
V46 = "spruceV4.6.0.7z"


class Plan(helpers.CardDir):
    def test_plan_keeps_roms_any_case(self):
        for d in ("ROMS", ".Trashes", "App", "miyoo"):
            os.makedirs(self.cp(d))
        for f in ("._x", "autorun.inf"):
            helpers.touch(self.cp(f))
        deleted, kept = install.plan(self.card)
        self.assertEqual(deleted, [self.cp("App"), self.cp("autorun.inf"), self.cp("miyoo")])
        self.assertEqual(kept, sorted(self.cp(n) for n in ("ROMS", ".Trashes", "._x")))

    def test_plan_keeps_only_roms(self):
        for d in ("Saves", "Themes", "Roms", "BIOS", "App"):
            os.makedirs(self.cp(d))
        deleted, kept = install.plan(self.card)
        self.assertEqual(deleted, [self.cp(n) for n in ("App", "BIOS", "Saves", "Themes")])
        self.assertEqual(kept, [self.cp("Roms")])


class UnpackedSize(unittest.TestCase):
    def test_unpacked_size_sums_sizes(self):
        listing = ("Path = x.7z\nPhysical Size = 99\nHeaders Size = 9\n\n"
                   "Path = a\nSize = 10\nPacked Size = 7\n\nPath = b\nSize = 5\n")
        done = subprocess.CompletedProcess([], 0, stdout=listing, stderr="")
        with mock.patch.object(install.external, "find_tool", return_value="7z"), \
                mock.patch.object(install.subprocess, "run", return_value=done):
            self.assertEqual(install.unpacked_size("x.7z"), 15)

    def test_unpacked_size_is_none_when_7z_fails_or_lists_nothing(self):
        for code, listing in ((2, "Path = a\nSize = 10\n"), (0, "")):
            done = subprocess.CompletedProcess([], code, stdout=listing, stderr="")
            with mock.patch.object(install.external, "find_tool", return_value="7z"), \
                    mock.patch.object(install.subprocess, "run", return_value=done):
                self.assertIsNone(install.unpacked_size("x.7z"))


@unittest.skipIf(external.find_tool("7z") is None, "needs 7z")
class Unpack(helpers.CardDir):
    def test_unpack_skips_existing(self):
        src = os.path.join(self.tmp.name, "src")
        helpers.touch(os.path.join(src, "Saves", "spruce", "spruce-config.json"), "new")
        helpers.touch(os.path.join(src, "App", "a"), "a")
        archive = os.path.join(self.tmp.name, V46)
        subprocess.run([external.find_tool("7z"), "a", archive, "Saves", "App"], cwd=src, check=True,
                       stdout=subprocess.DEVNULL)
        helpers.touch(self.cp("Saves", "spruce", "spruce-config.json"), "old")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(install.unpack(archive, self.card, install.unpacked_size(archive)))
        with open(self.cp("Saves", "spruce", "spruce-config.json")) as f:
            self.assertEqual(f.read(), "old")
        self.assertTrue(os.path.isfile(self.cp("App", "a")))

    def test_check_passes_a_whole_archive_and_fails_a_broken_one(self):
        src = os.path.join(self.tmp.name, "src")
        helpers.touch(os.path.join(src, "App", "a"), "a")
        archive = os.path.join(self.tmp.name, V46)
        subprocess.run([external.find_tool("7z"), "a", archive, "App"], cwd=src, check=True, stdout=subprocess.DEVNULL)
        broken = os.path.join(self.tmp.name, "broken.7z")
        helpers.touch(broken, b"not a 7z")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(install.check(archive, 1))
            self.assertIsNotNone(install.check(broken, 1))

    def test_unpack_reports_a_broken_archive(self):
        archive = os.path.join(self.tmp.name, V46)
        helpers.touch(archive, b"not a 7z")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNotNone(install.unpack(archive, self.card, 1))
        self.assertIsNone(install.unpacked_size(archive))


class ExitCodes(helpers.CardDir):
    def fake_7z(self, code):
        tool = os.path.join(self.tmp.name, f"7z-{code}")
        helpers.touch(tool, f"#!/bin/sh\necho 'first line' >&2\necho 'WARNING: attributes' >&2\nexit {code}\n")
        os.chmod(tool, 0o755)
        return tool

    def unpack_with(self, code):
        err = io.StringIO()
        with mock.patch.object(install.external, "find_tool", return_value=self.fake_7z(code)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            return install.unpack("x.7z", self.card, 1), err.getvalue()

    def test_exit_code_1_is_a_warning(self):
        result, err = self.unpack_with(1)
        self.assertIsNone(result)
        self.assertIn("WARNING: attributes", err)

    def test_exit_code_2_is_a_failure(self):
        self.assertEqual(self.unpack_with(2)[0], "WARNING: attributes")


class Run(helpers.CardDir):
    def setUp(self):
        super().setUp()
        store.update_card("card", device="full", layout="spruce", boot_logos=["a.png"],
                          spruce_themes_installed=["ART_BOOK_NEXT", "TechDweeb_BMO"])
        for d in ("App", "Roms/GBA", "Themes/ART_BOOK_NEXT", "Themes/TechDweeb_BMO"):
            os.makedirs(self.cp(d))
        helpers.touch(self.cp("App", "f"), b"12345")
        self.enterContext(mock.patch.object(install.inventory, "files", return_value={P + V46: 100}))
        self.downloads = self.enterContext(mock.patch.object(install.downloads, "run_downloads", return_value=0))
        self.enterContext(mock.patch.object(install.external, "find_tool", return_value="7z"))
        self.enterContext(mock.patch.object(install, "unpacked_size", return_value=1000))
        self.unpack = self.enterContext(mock.patch.object(install, "unpack", return_value=None))
        self.check = self.enterContext(mock.patch.object(install, "check", return_value=None))
        self.mounted = self.enterContext(mock.patch.object(install, "_mounted", return_value=True))
        self.tmpdir = os.path.join(self.tmp.name, "install-tmp")

        def mkdtemp(**_):
            os.makedirs(self.tmpdir)
            return self.tmpdir
        self.enterContext(mock.patch.object(install.tempfile, "mkdtemp", side_effect=mkdtemp))

    def run_cmd(self, dry_run=False, yes=True, terminal=False):
        args = argparse.Namespace(card=self.card, dry_run=dry_run, yes=yes)
        self.out, self.err = io.StringIO(), io.StringIO()
        with mock.patch.object(install.ui, "has_terminal", return_value=terminal), \
                contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            try:
                return install.run(args)
            except SystemExit as e:
                return e.code

    def entry(self):
        return store.load_cards()["card"]

    def test_run_refuses_a_folder_that_isnt_mounted(self):
        self.mounted.return_value = False
        for dry_run in (True, False):
            self.assertEqual(self.run_cmd(dry_run=dry_run), 2)
            self.assertIn(f"{self.card} isn't a mounted card", self.err.getvalue())
        self.mounted.assert_called_with(self.card)
        self.downloads.assert_not_called()
        self.assertTrue(os.path.isdir(self.cp("App")))

    def test_run_damaged_archive_deletes_nothing(self):
        self.check.return_value = "ERROR: CRC Failed"
        self.assertEqual(self.run_cmd(), 1)
        self.assertIn("CRC Failed", self.out.getvalue())
        self.check.assert_called_once_with(os.path.join(self.tmpdir, V46), 1000)
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.assertFalse(os.path.exists(self.tmpdir))
        self.unpack.assert_not_called()

    def test_run_rejects_other_layout(self):
        store.update_card("card", layout="onion")
        self.assertEqual(self.run_cmd(), 2)
        self.assertIn("supports only spruce cards; card is onion", self.err.getvalue())
        self.assertTrue(os.path.isdir(self.cp("App")))

    def test_run_without_a_release_in_storage_fails(self):
        install.inventory.files.return_value = {}
        self.assertEqual(self.run_cmd(), 1)
        self.downloads.assert_not_called()
        self.assertTrue(os.path.isdir(self.cp("App")))

    def test_run_dry_run_touches_nothing(self):
        self.assertEqual(self.run_cmd(dry_run=True, yes=False), 0)
        self.downloads.assert_not_called()
        self.unpack.assert_not_called()
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.assertTrue(os.path.isdir(self.cp("Themes", "TechDweeb_BMO")))
        self.assertNotIn("spruce_os", self.entry())
        out = self.out.getvalue()
        self.assertIn("App", out)
        self.assertIn("Themes", out)
        self.assertIn("5 B", out)
        self.assertIn(V46, out)
        self.assertIn("Dry run: nothing downloaded, deleted or unpacked", out)

    def test_run_without_terminal_or_yes_exits_2(self):
        self.assertEqual(self.run_cmd(yes=False), 2)
        self.downloads.assert_not_called()
        self.assertTrue(os.path.isdir(self.cp("App")))

    def test_run_download_failure_deletes_nothing(self):
        self.downloads.side_effect = lambda todo, label, icon, base, failures: failures.append((todo[0][0], "boom")) or 1
        self.assertEqual(self.run_cmd(), 1)
        self.assertIn("boom", self.out.getvalue())
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.assertFalse(os.path.exists(self.tmpdir))
        self.unpack.assert_not_called()

    def test_run_declined_deletes_nothing(self):
        with mock.patch.object(install.ui, "confirm", return_value=False) as confirm:
            self.assertEqual(self.run_cmd(yes=False, terminal=True), 1)
        self.assertIn(f"Delete 2 items from {self.card} and install spruceOS {V46}?", confirm.call_args.args[0])
        self.assertIs(confirm.call_args.kwargs.get("default"), False)
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.assertFalse(os.path.exists(self.tmpdir))
        self.unpack.assert_not_called()
        self.assertNotIn("spruce_os", self.entry())

    def test_run_without_room_on_the_card_deletes_nothing(self):
        with mock.patch.object(install.downloads, "free_space", return_value=0):
            self.assertEqual(self.run_cmd(), 1)
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.unpack.assert_not_called()

    def test_run_installs_and_records(self):
        self.assertEqual(self.run_cmd(), 0)
        todo = self.downloads.call_args.args[0]
        self.assertEqual(todo, [(P + V46, os.path.join(self.tmpdir, V46), 100)])
        self.unpack.assert_called_once_with(os.path.join(self.tmpdir, V46), self.card, 1000)
        self.assertFalse(os.path.exists(self.cp("App")))
        self.assertFalse(os.path.exists(self.cp("Themes", "TechDweeb_BMO")))
        self.assertTrue(os.path.isdir(self.cp("Roms", "GBA")))
        self.assertFalse(os.path.exists(self.cp("Themes")))
        self.assertFalse(os.path.exists(self.tmpdir))
        entry = self.entry()
        self.assertEqual(entry["spruce_os"], V46)
        self.assertEqual(entry["layout"], "spruce")
        self.assertIn(f"spruceOS {V46} installed on card", self.out.getvalue())

    def test_run_clears_theme_and_logo_records(self):
        self.assertEqual(self.run_cmd(), 0)
        entry = self.entry()
        self.assertNotIn("boot_logos", entry)
        self.assertNotIn("spruce_themes_installed", entry)
        self.assertEqual(entry["spruce_os"], V46)

    def test_run_unreadable_archive_deletes_nothing(self):
        install.unpacked_size.return_value = None
        self.assertEqual(self.run_cmd(), 1)
        self.assertIn("can't read", self.out.getvalue())
        self.assertTrue(os.path.isdir(self.cp("App")))
        self.assertFalse(os.path.exists(self.tmpdir))
        self.unpack.assert_not_called()

    def test_run_unpack_failure_exits_3(self):
        self.unpack.return_value = "ERROR: broken"
        self.assertEqual(self.run_cmd(), 3)
        self.assertIn("ERROR: broken", self.out.getvalue())
        self.assertIn("card has no spruceOS now", self.out.getvalue())
        self.assertNotIn("spruce_os", self.entry())
        self.assertFalse(os.path.exists(self.tmpdir))

    def test_run_deletion_failure_exits_3_before_unpacking(self):
        with mock.patch.object(install.convert, "remove_media", return_value=[(self.cp("App"), OSError("busy"))]):
            self.assertEqual(self.run_cmd(), 3)
        self.assertIn("busy", self.err.getvalue())
        self.unpack.assert_not_called()
        self.assertNotIn("spruce_os", self.entry())


if __name__ == "__main__":
    unittest.main()
