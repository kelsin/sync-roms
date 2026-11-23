"""spruce_fixes.highlight_last_collection against copies of PyUI's files (fixtures): spruceOS 4.6.0 and Development,
each with spruceOS PR 2070 applied (`4.6.0-patched`, `development-patched`), and Development with the earlier "Reopen
last collection" patch sync-roms applied (`old-patched`). Delete with the fix."""
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
from sync_roms.spruce_fixes import highlight_last_collection as fix  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "spruce-highlight-last-collection")
FILES = [rel for rel, *_ in fix.EDITS]
OLD_FILES = [rel for rel, *_ in fix.OLD]
ROMS_MENU = "main-ui/menus/games/roms_menu_common.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def card(self, *versions):
        """Copy the fixture versions onto the card, later ones over earlier ones."""
        for version in versions:
            shutil.copytree(os.path.join(FIXTURES, version), self.base, dirs_exist_ok=True)

    def path(self, rel, root=None):
        return os.path.join(root or os.path.join(self.base, fix.ROOT), *rel.split("/"))

    def read(self, rel, version=None):
        with open(self.path(rel, version and os.path.join(FIXTURES, version, fix.ROOT)), "rb") as f:
            return f.read()

    def run_fixes(self, dry_run=False):
        with mock.patch("sys.stdout", new=StringIO()) as out, mock.patch("sys.stderr", new=StringIO()) as err:
            count = spruce_fixes.run("spruce", self.base, dry_run)
        cardfs.flush()
        lines = [x for x in (out.getvalue() + err.getvalue()).splitlines() if "Highlight last collection" in x]
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

    def edit(self, rel, old, new):
        data = self.read(rel)
        self.assertIn(old, data)
        with open(self.path(rel), "wb") as f:
            f.write(data.replace(old, new))


class ApplyTests(Base):
    def assert_matches(self, version):
        self.card(version)
        before = self.snapshot()
        count, line, err = self.run_fixes()
        self.assertEqual(count, 3)
        self.assertIn("applied to 3 file(s)", line)
        self.assertEqual(err, "")
        for rel in FILES:
            self.assertEqual(self.read(rel), self.read(rel, f"{version}-patched"), rel)
        changed = {rel for rel, data in self.snapshot().items() if before[rel] != data}
        self.assertEqual(changed, {os.path.join(fix.ROOT, *rel.split("/")) for rel in FILES})

    def test_development_matches_the_pull_request(self):
        self.assert_matches("development")

    def test_4_6_0_matches_the_pull_request(self):
        """4.6.0-patched is the PR's diff applied to 4.6.0 (its hunks for the ROM deletion handler, which 4.6.0
        doesn't have, left out)."""
        self.assert_matches("4.6.0")

    def test_earlier_setting_is_taken_out(self):
        self.card("development", "old-patched")
        count, line, err = self.run_fixes()
        self.assertEqual(count, 7)
        self.assertIn("applied to 7 file(s)", line)
        self.assertEqual(err, "")
        for rel in FILES:
            self.assertEqual(self.read(rel), self.read(rel, "development-patched"), rel)
        for rel in set(OLD_FILES) - set(FILES):
            self.assertEqual(self.read(rel), self.read(rel, "development"), rel)

    def test_lf_files_stay_lf(self):
        self.card("development")
        for rel in FILES:
            data = self.read(rel).replace(b"\r\n", b"\n")
            with open(self.path(rel), "wb") as f:
                f.write(data)
        count, _, _ = self.run_fixes()
        self.assertEqual(count, 3)
        for rel in FILES:
            self.assertEqual(self.read(rel), self.read(rel, "development-patched").replace(b"\r\n", b"\n"), rel)


class SkipTests(Base):
    def test_already_applied(self):
        for version in ("4.6.0", "development"):
            with self.subTest(version):
                shutil.rmtree(self.base)
                self.card(version, f"{version}-patched")
                before = self.snapshot()
                count, line, err = self.run_fixes()
                self.assertEqual(count, 0)
                self.assertIn("the card's PyUI already has it", line)
                self.assertIn("remove this fix once every card shows this", line)
                self.assertEqual(err, "")
                self.assertEqual(self.snapshot(), before)

    def test_second_sync_does_nothing(self):
        self.card("development", "old-patched")
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

    def test_unknown_version(self):
        self.card("development")
        self.edit("main-ui/menus/games/collections_menu.py", b'"Collections",', b'"Collection",')
        self.assert_untouched("main-ui/menus/games/collections_menu.py isn't as expected")

    def test_another_state_write(self):
        self.card("4.6.0")
        self.edit(ROMS_MENU, b"                elif(ControllerInput.SELECT == selected.get_input()",
                  b"                    PyUiState.set_last_game_selection(page_name, None, '')\r\n"
                  b"                elif(ControllerInput.SELECT == selected.get_input()")
        self.assert_untouched(f"{ROMS_MENU} isn't as expected")

    def test_changed_deletion_handler(self):
        self.card("development")
        self.edit(ROMS_MENU, b"                next_game.rom_file_path,", b"                next_game.rom_path,")
        self.assert_untouched(f"{ROMS_MENU} isn't as expected")

    def test_missing_file(self):
        self.card("development")
        os.remove(self.path("main-ui/menus/games/game_select_menu.py"))
        self.assert_untouched("main-ui/menus/games/game_select_menu.py is missing")

    def test_half_patched(self):
        self.card("development")
        shutil.copy(self.path(ROMS_MENU, os.path.join(FIXTURES, "development-patched", fix.ROOT)), self.path(ROMS_MENU))
        self.assert_untouched("only some of its files have the change")

    def test_half_old_patch(self):
        self.card("development")
        shutil.copy(self.path("lang/English.json", os.path.join(FIXTURES, "old-patched", fix.ROOT)),
                    self.path("lang/English.json"))
        self.assert_untouched("only some of its files have the earlier Reopen last collection setting")

    def test_old_patch_edited(self):
        self.card("development", "old-patched")
        self.edit("main-ui/menus/language/language.py", b'"reopenLastCollection","Reopen last collection"',
                  b'"reopenLastCollection","Reopen"')
        self.assert_untouched("language.py isn't as the earlier Reopen last collection patch left it")

    def test_mixed_line_ends(self):
        self.card("development")
        self.edit("main-ui/menus/games/game_select_menu.py", b"\r\nclass ", b"\nclass ")
        self.assert_untouched("game_select_menu.py has mixed line ends")

    def test_no_pyui(self):
        count, line, err = self.run_fixes()
        self.assertEqual((count, err), (0, ""))
        self.assertIn("PyUI isn't on the card", line)

    def test_dry_run_writes_nothing(self):
        self.card("4.6.0")
        before = self.snapshot()
        count, line, _ = self.run_fixes(dry_run=True)
        self.assertEqual(count, 3)
        self.assertIn("would apply to 3 file(s)", line)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
