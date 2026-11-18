import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402

from sync_roms import inventory, runtime, usersettings  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "migrate_sets", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "migrate_sets.py"))
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)

A = '{"name": "A",   "games": [{"bucket": "gba/a.zip"}]}\n'  # odd spacing: must not be re-serialised
B = '{"games": []}'


class MigrateSetsTest(StorageDir):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(usersettings, "apply_settings")
        p.start()
        self.addCleanup(p.stop)
        os.makedirs(self.data)
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.src)
        self.src_file("a.json", A)
        self.src_file("b.json", B)

    def src_file(self, name, text):
        with open(os.path.join(self.src, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = migrate.main(["--from", self.src, *args])
        return code, out.getvalue()

    def stored(self, name):
        with open(os.path.join(self.root, "sets", name), encoding="utf-8", newline="") as f:
            return f.read()

    def tree(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.root) for f in fs)

    def test_dry_run_writes_nothing(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.tree(), [])
        self.assertIn("sets/a.json", out)
        self.assertIn("--apply", out)

    def test_apply_writes_byte_for_byte(self):
        self.run_main("--apply")
        self.assertEqual(self.stored("a.json"), A)
        self.assertEqual(self.stored("b.json"), B)

    def test_existing_sets_are_kept(self):
        self.put("sets/a.json", b'{"games": [1]}')
        _, out = self.run_main("--apply")
        self.assertEqual(self.stored("a.json"), '{"games": [1]}')
        self.assertEqual(self.stored("b.json"), B)
        self.assertIn("kept 1 already in storage", out)

    def test_bad_file_aborts_before_writes(self):
        for bad in ("[", "[]", '{"games": 1}'):
            self.src_file("c.json", bad)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as c:
                self.run_main("--apply")
            self.assertEqual(c.exception.code, 1)
            self.assertEqual(self.tree(), [])

    def test_source_files_are_left_alone(self):
        self.run_main("--apply")
        with open(os.path.join(self.src, "a.json"), encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), A)
        self.assertEqual(sorted(os.listdir(self.src)), ["a.json", "b.json"])

    def test_second_apply_writes_nothing(self):
        self.run_main("--apply")
        mtimes = {p: os.stat(p).st_mtime_ns for p in self.tree()}
        _, out = self.run_main("--apply")
        self.assertEqual({p: os.stat(p).st_mtime_ns for p in self.tree()}, mtimes)
        self.assertNotIn("(written)", out)
        self.assertIn("kept 2 already in storage", out)

    def test_apply_saves_the_storage_cache(self):
        with contextlib.redirect_stdout(io.StringIO()):
            inventory.update()
        self.run_main("--apply")
        inventory.reset()
        self.assertEqual(sorted(inventory.files("sets/")), ["sets/a.json", "sets/b.json"])

    def test_unmounted_storage_fails(self):
        missing = os.path.join(self.tmp.name, "gone")
        with mock.patch.object(runtime, "ROOT", missing):
            for args in ((), ("--apply",)):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as c:
                    self.run_main(*args)
                self.assertEqual(c.exception.code, 1)
        self.assertFalse(os.path.exists(missing))

    def test_copy_is_byte_exact_with_non_ascii_and_crlf(self):
        self.src_file("c.json", '{"name": "Pok\u00e9mon ゲーム",\r\n "games": []}\r\n')
        self.run_main("--apply")
        with open(os.path.join(self.root, "sets", "c.json"), "rb") as f:
            with open(os.path.join(self.src, "c.json"), "rb") as g:
                self.assertEqual(f.read(), g.read())

    def test_dotfiles_subfolders_and_other_files_are_ignored(self):
        self.src_file("._a.json", "\x00binary")
        self.src_file("notes.txt", "x")
        os.makedirs(os.path.join(self.src, "sub.json"))
        self.src_file(os.path.join("sub.json", "d.json"), B)
        self.run_main("--apply")
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["a.json", "b.json"])

    def test_non_utf8_storage_file_fails_cleanly(self):
        self.put("sets/a.json", b"\xff\xfe")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as c:
            self.run_main("--apply")
        self.assertEqual(c.exception.code, 1)
        self.assertEqual(self.tree(), [os.path.join(self.root, "sets", "a.json")])

    def test_default_source_is_the_repos_sets(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(migrate.__file__)))
        self.assertEqual(os.path.realpath(migrate.DEFAULT_FROM), os.path.realpath(os.path.join(repo, "src", "sync_roms", "data", "sets")))


if __name__ == "__main__":
    unittest.main()
