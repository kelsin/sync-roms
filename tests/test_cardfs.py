import collections
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import cardfs, downloads, scrape_plan, vita  # noqa: E402
from helpers import touch  # noqa: E402


class CardFsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.scans, self.stats = collections.Counter(), []
        real_scandir, real_stat = os.scandir, os.stat

        def scandir(path="."):
            self.scans[os.path.relpath(path, self.dir)] += 1
            return real_scandir(path)

        def stat(path, *a, **k):
            if str(path).startswith(self.dir):
                self.stats.append(path)
            return real_stat(path, *a, **k)
        for name, value in (("scandir", scandir), ("stat", stat)):
            patcher = mock.patch.object(os, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        caching = cardfs.caching()
        caching.__enter__()
        self.addCleanup(caching.__exit__, None, None, None)

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def test_a_planning_pass_lists_each_folder_once_without_a_stat_per_file(self):
        for rel in ("gba/A.zip", "gba/B.zip", "gba/Old.zip", "snes/C.zip", "snes/sub/D.zip", "psvita/G.zip",
                    "media/covers/A.png", "media/covers/Old.png"):
            touch(self.path(*rel.split("/")), b"xxxxx")
        self.scans.clear()
        self.stats.clear()
        jobs = [(f"{s}/{n}", self.path(s, n), 5) for s, n in (("gba", "A.zip"), ("gba", "B.zip"), ("gba", "New.zip"),
                                                               ("snes", "C.zip"), ("snes", "sub/D.zip"))]
        self.assertEqual([j[0] for j in downloads.plan_downloads(jobs)], ["gba/New.zip"])
        self.assertEqual(downloads.find_extras(self.path("gba"), ["gba/A.zip", "gba/B.zip"]), [self.path("gba", "Old.zip")])
        self.assertEqual(downloads.find_extras(self.path("snes"), ["snes/C.zip", "snes/sub/D.zip"]), [])
        self.assertTrue(downloads.has_local_files(self.path("snes")))
        self.assertEqual(scrape_plan.card_stems(self.path("gba"), False), {"A", "B", "Old"})
        self.assertEqual(cardfs.size(self.path("gba", "Old.zip")), 5)
        self.assertTrue(cardfs.is_dir(self.path("media", "covers")))
        self.assertEqual(sorted(rel for rel, _ in scrape_plan.walk_files(self.path("media", "covers"))), ["A.png", "Old.png"])
        self.assertFalse(cardfs.exists(self.path("missing", "X.zip")))
        self.assertFalse(cardfs.exists(self.path("missing", "Y.zip")))
        self.assertEqual(set(self.scans.values()), {1})
        self.assertEqual(set(self.scans), {"gba", "snes", "snes/sub", "media", "media/covers", "missing"})
        self.assertEqual(self.stats, [])

    def test_a_folder_changed_after_clear_is_listed_again(self):
        touch(self.path("gba", "A.zip"))
        self.assertFalse(cardfs.exists(self.path("gba", "B.zip")))
        touch(self.path("gba", "B.zip"))
        self.assertFalse(cardfs.exists(self.path("gba", "B.zip")))  # kept until the card is said to have changed
        cardfs.clear()
        self.assertTrue(cardfs.exists(self.path("gba", "B.zip")))
        self.assertEqual(self.scans["gba"], 2)

    def test_without_caching_every_lookup_lists_afresh(self):
        with mock.patch.object(cardfs, "_cache", None):
            touch(self.path("gba", "A.zip"))
            self.assertFalse(cardfs.exists(self.path("gba", "B.zip")))
            touch(self.path("gba", "B.zip"))
            self.assertTrue(cardfs.exists(self.path("gba", "B.zip")))

    def test_a_lookup_in_another_case_gets_what_os_stat_gets(self):
        touch(self.path("gba", "Game.zip"), b"xyz")
        other = self.path("gba", "GAME.zip")
        insensitive = os.path.exists(other)
        self.stats.clear()
        self.assertEqual(cardfs.size(other), 3 if insensitive else None)
        self.assertEqual(cardfs.exists(other), insensitive)
        self.assertEqual(cardfs.size(self.path("gba", "game.ZIP")), 3 if insensitive else None)

    def test_a_name_in_another_case_is_found_on_a_case_insensitive_card(self):
        touch(self.path("gba", "Pokémon.zip"), b"xyz")
        with mock.patch.object(os.path, "lexists", lambda path: True):  # what a case-insensitive card answers
            self.assertEqual(cardfs.size(self.path("gba", "POKÉMON.zip")), 3)
            self.assertTrue(downloads.is_current(self.path("gba", "pokémon.zip"), 3))

    def test_two_names_in_other_cases_match_neither(self):
        names = {"Game.zip": mock.Mock(name="a"), "GAME.zip": mock.Mock(name="b")}
        with mock.patch.object(cardfs, "_scan", lambda folder: (names, {"game.zip": list(names)})), \
                mock.patch.object(os.path, "lexists", lambda path: True):
            self.assertFalse(cardfs.exists(self.path("gba", "game.zip")))

    def test_walk_matches_os_walk_and_does_not_enter_a_linked_folder(self):
        for rel in ("a/1", "a/b/2", "c/3", "4"):
            touch(self.path(*rel.split("/")))
        os.symlink(self.path("a"), self.path("link"))
        want = [(root, sorted(dirs), sorted(files)) for root, dirs, files in os.walk(self.dir)]
        got = [(root, sorted(dirs), sorted(files)) for root, dirs, files in cardfs.walk(self.dir)]
        self.assertEqual(sorted(got), sorted(want))
        pruned = []
        for root, dirs, _ in cardfs.walk(self.dir):
            dirs[:] = [d for d in dirs if d != "a"]
            pruned.append(os.path.relpath(root, self.dir))
        self.assertEqual(sorted(pruned), [".", "c"])

    def test_vita_lists_its_folder_once(self):
        touch(self.path("psvita", "A.zip"), b"x")
        touch(self.path("psvita", "A.psvita"), b"PCSE00000")
        touch(self.path("psvita", "B.psvita"), b"PCSE00001")
        self.scans.clear()
        self.stats.clear()
        self.assertEqual(vita.add_psvita_files([self.path("psvita")]), [])
        self.assertEqual(dict(self.scans), {"psvita": 1})
        self.assertEqual(self.stats, [])


if __name__ == "__main__":
    unittest.main()
