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

from sync_roms import inventory, runtime, scrape_state, usersettings  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "migrate_scrape_state", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "migrate_scrape_state.py"))
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


class MigrateTest(StorageDir):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(usersettings, "apply_settings")
        p.start()
        self.addCleanup(p.stop)
        os.makedirs(self.data)
        self.old = {
            "scrape-matches.json": {"gba/a.zip": 5, "snes/b.zip": 7},
            "scrape-unknown.json": {"gba/u.zip": True},
            "scrape-nomedia.json": {"gba/a.zip": ["box"]},
            "scrape-hashes.json": {"gba/a.zip": {"size": 1, "mtime": 2, "hashes": {"crc": "x"}}},
            "scrape-notgames.json": {"gba/n.zip": "demo", "kept": ["gba/k.zip"]},
            "variants-checked.json": {"gba/v.zip": "judged"},
        }
        for name, data in self.old.items():
            self.write_old(name, data)

    def write_old(self, name, data):
        with open(os.path.join(self.data, name), "w") as f:
            json.dump(data, f)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = migrate.main(list(args))
        return code, out.getvalue()

    def stored(self, key):
        with open(os.path.join(self.root, key)) as f:
            return json.load(f)

    def tree(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.root) for f in fs)

    def test_dry_run_writes_nothing(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.tree(), [])
        self.assertIn("scrapes/gba/matches.json", out)
        self.assertIn("--apply", out)

    def test_apply_writes_per_system_files(self):
        self.run_main("--apply")
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 5})
        self.assertEqual(self.stored("scrapes/snes/matches.json"), {"b.zip": 7})
        self.assertEqual(self.stored("scrapes/gba/unknown.json"), {"u.zip": True})
        self.assertEqual(self.stored("scrapes/gba/nomedia.json"), {"a.zip": ["box"]})
        self.assertEqual(self.stored("scrapes/gba/hashes.json")["a.zip"]["size"], 1)
        self.assertEqual(self.stored("scrapes/notgames.json"), {"gba/n.zip": "demo", "kept": ["gba/k.zip"]})
        self.assertEqual(self.stored("variants-checked.json"), {"gba/v.zip": "judged"})

    def test_second_apply_changes_nothing(self):
        self.run_main("--apply")
        mtimes = {p: os.stat(p).st_mtime_ns for p in self.tree()}
        _, out = self.run_main("--apply")
        self.assertEqual({p: os.stat(p).st_mtime_ns for p in self.tree()}, mtimes)
        self.assertNotIn("(written)", out)

    def test_existing_storage_entries_survive(self):
        self.put("scrapes/gba/matches.json", json.dumps({"a.zip": 99, "z.zip": 1}).encode())
        self.put("scrapes/notgames.json", json.dumps({"gba/o.zip": "x", "kept": ["gba/j.zip"]}).encode())
        self.run_main("--apply")
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 99, "z.zip": 1})
        self.assertEqual(self.stored("scrapes/notgames.json"),
                         {"gba/o.zip": "x", "gba/n.zip": "demo", "kept": ["gba/j.zip", "gba/k.zip"]})

    def test_old_files_are_left_alone(self):
        self.run_main("--apply")
        for name, data in self.old.items():
            with open(os.path.join(self.data, name)) as f:
                self.assertEqual(json.load(f), data)

    def test_missing_old_files_are_skipped(self):
        for name in self.old:
            os.remove(os.path.join(self.data, name))
        self.run_main("--apply")
        self.assertEqual(self.tree(), [])

    def test_malformed_old_file_stops_before_writing(self):
        with open(os.path.join(self.data, "scrape-hashes.json"), "w") as f:
            f.write("[")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_main("--apply")
        self.assertEqual(self.tree(), [])

    def test_rom_path_with_slash_stays_whole(self):
        self.write_old("scrape-matches.json", {"psx/Game (Disc 1)/track.bin": 3})
        self.run_main("--apply")
        self.assertEqual(self.stored("scrapes/psx/matches.json"), {"Game (Disc 1)/track.bin": 3})

    def test_malformed_keys_are_counted(self):
        self.write_old("scrape-unknown.json", {"nokey": True, "gba/": True, "gba/u.zip": True})
        _, out = self.run_main()
        self.assertIn("skipped 2 malformed key(s) in scrape-unknown.json", out)
        self.assertEqual(self.tree(), [])

    def test_apply_saves_the_storage_cache(self):
        quiet = contextlib.redirect_stdout(io.StringIO())
        with quiet:
            inventory.update()  # a cache exists before the migration
        self.run_main("--apply")
        inventory.reset()  # the next run reads the cache file again
        scrape_state.reset()
        self.assertIn("scrapes/gba/unknown.json", inventory.files("scrapes/"))
        self.assertEqual(scrape_state.unknown(), {"gba/u.zip"})

    def test_unmounted_storage_fails(self):
        missing = os.path.join(self.tmp.name, "gone")
        with mock.patch.object(runtime, "ROOT", missing):
            for args in ((), ("--apply",)):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as c:
                    self.run_main(*args)
                self.assertEqual(c.exception.code, 1)
        self.assertFalse(os.path.exists(missing))
        self.assertEqual(self.tree(), [])


if __name__ == "__main__":
    unittest.main()
