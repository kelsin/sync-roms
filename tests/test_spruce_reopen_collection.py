"""spruce_fixes.reopen_collection against copies of PyUI's files from spruceOS 4.6.0 and Development (fixtures), and
Development with spruceOS PR 2070 applied (`patched`). Delete with the fix."""
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardfs, spruce_fixes  # noqa: E402
from sync_roms.spruce_fixes import reopen_collection  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "spruce-reopen-collection")
FILES = [rel for rel, *_ in reopen_collection.PATCHES]


class Base(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def card(self, *versions):
        """Copy the fixture versions onto the card, later ones over earlier ones."""
        for version in versions:
            shutil.copytree(os.path.join(FIXTURES, version), self.base, dirs_exist_ok=True)

    def path(self, rel, root=None):
        return os.path.join(root or os.path.join(self.base, reopen_collection.ROOT), *rel.split("/"))

    def read(self, rel, root=None):
        with open(self.path(rel, root), "rb") as f:
            return f.read()

    def run_fixes(self, dry_run=False):
        with mock.patch("sys.stdout", new=StringIO()) as out, mock.patch("sys.stderr", new=StringIO()) as err:
            count = spruce_fixes.run("spruce", self.base, dry_run)
        cardfs.flush()
        lines = [x for x in (out.getvalue() + err.getvalue()).splitlines() if "Reopen last collection" in x]
        self.assertEqual(len(lines), 1)
        self.assertIn("https://github.com/spruceUI/spruceOS/pull/2070", lines[0])
        return count, lines[0], err.getvalue()

    def snapshot(self):
        found = {}
        for folder, _, files in os.walk(self.base):
            for name in files:
                with open(os.path.join(folder, name), "rb") as f:
                    found[os.path.relpath(os.path.join(folder, name), self.base)] = f.read()
        return found


class ApplyTests(Base):
    def test_development_matches_the_pull_request(self):
        self.card("development")
        count, line, err = self.run_fixes()
        self.assertEqual(count, 5)
        self.assertIn("applied to 5 file(s)", line)
        self.assertEqual(err, "")
        patched = os.path.join(FIXTURES, "patched", reopen_collection.ROOT)
        for rel in FILES:
            self.assertEqual(self.read(rel), self.read(rel, patched), rel)

    def test_4_6_0_is_patched_in_place(self):
        self.card("4.6.0")
        before = {rel: self.read(rel) for rel in FILES}
        count, line, _ = self.run_fixes()
        self.assertEqual(count, 5)
        for rel in FILES:
            after = self.read(rel)
            self.assertGreater(len(after), len(before[rel]))
            # only lines added: every original line is still there, in order
            old, new = before[rel].split(b"\r\n"), after.split(b"\r\n")
            it = iter(new)
            self.assertTrue(all(any(line == x for x in it) for line in old), rel)
        menu = self.read("main-ui/menus/games/collections_menu.py")
        self.assertIn(b"from devices.miyoo.user_config import UserConfig\r\n", menu)
        self.assertIn(b"    def _run_rom_selection_for_rom_list(self, page_name, rom_list, refresh_rom_list=None):\r\n",
                      menu)
        self.assertIn(b'    "reopenLastCollection": "Reopen last collection",\r\n', self.read("lang/English.json"))

    def test_crlf_kept(self):
        for version in ("4.6.0", "development"):
            with self.subTest(version):
                shutil.rmtree(self.base)
                self.card(version)
                self.run_fixes()
                for rel in FILES:
                    data = self.read(rel)
                    self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), rel)

    def test_lf_files_stay_lf(self):
        self.card("development")
        for rel in FILES:
            data = self.read(rel).replace(b"\r\n", b"\n")
            with open(self.path(rel), "wb") as f:
                f.write(data)
        count, _, _ = self.run_fixes()
        self.assertEqual(count, 5)
        for rel in FILES:
            self.assertNotIn(b"\r", self.read(rel), rel)

    def test_no_junk_left(self):
        self.card("4.6.0")
        before = set(self.snapshot())
        self.run_fixes()
        self.assertEqual(set(self.snapshot()), before)


class SkipTests(Base):
    def test_already_applied(self):
        self.card("development", "patched")
        before = self.snapshot()
        count, line, err = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("the card's PyUI already has it", line)
        self.assertIn("remove this fix once every card shows this", line)
        self.assertEqual(err, "")
        self.assertEqual(self.snapshot(), before)

    def test_second_sync_does_nothing(self):
        self.card("4.6.0")
        self.run_fixes()
        before = self.snapshot()
        count, line, _ = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("already has it", line)
        self.assertEqual(self.snapshot(), before)

    def assert_untouched(self, reason):
        before = self.snapshot()
        count, line, err = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("isn't a version it knows", err)
        self.assertIn(reason, line)
        self.assertEqual(self.snapshot(), before)

    def edit(self, rel, old, new):
        data = self.read(rel)
        self.assertIn(old, data)
        with open(self.path(rel), "wb") as f:
            f.write(data.replace(old, new))

    def test_unknown_version(self):
        self.card("development")
        self.edit("main-ui/devices/miyoo/user_config.py", b'cls.config["ignoreArticlesWhenSorting"] = value',
                  b'cls.config["ignoreArticles"] = value')
        self.assert_untouched("main-ui/devices/miyoo/user_config.py isn't as expected")

    def test_changed_super_method(self):
        self.card("4.6.0")
        self.edit("main-ui/menus/games/roms_menu_common.py", b"def _run_rom_selection_for_rom_list(self, page_name,",
                  b"def _run_rom_selection_for_rom_list(self, page,")
        self.assert_untouched("roms_menu_common.py isn't as expected")

    def test_missing_file(self):
        self.card("development")
        os.remove(self.path("main-ui/menus/language/language.py"))
        self.assert_untouched("main-ui/menus/language/language.py is missing")

    def test_half_patched(self):
        self.card("development")
        shutil.copy(os.path.join(FIXTURES, "patched", reopen_collection.ROOT, "lang", "English.json"),
                    self.path("lang/English.json"))
        self.assert_untouched("only some of its files have the change")

    def test_mixed_line_ends(self):
        self.card("development")
        self.edit("lang/English.json", b"{\r\n", b"{\n")
        self.assert_untouched("lang/English.json has mixed line ends")

    def test_no_pyui(self):
        count, line, err = self.run_fixes()
        self.assertEqual((count, err), (0, ""))
        self.assertIn("PyUI isn't on the card", line)

    def test_dry_run_writes_nothing(self):
        self.card("4.6.0")
        before = self.snapshot()
        count, line, _ = self.run_fixes(dry_run=True)
        self.assertEqual(count, 5)
        self.assertIn("would apply to 5 file(s)", line)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
