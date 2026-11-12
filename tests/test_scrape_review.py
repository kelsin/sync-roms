import argparse
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import ignore, inventory, scrape_online, scrape_review, scrape_state, screenscraper, ui  # noqa: E402

GB = {"name": "Game Boy", "bucket": "gb", "screenscraper": 9, "folders": {}}
INFO = {"name": "Study Cart", "genre": "Educational", "year": "1999", "desc": "A study aid."}
KEYS = ["gb/a.zip", "gb/b.zip", "gb/c.zip"]


class ReviewBase(DataDir):
    def setUp(self):
        super().setUp()
        for key in KEYS:
            scrape_state.mark_notgame("gb", key.split("/", 1)[1], INFO)
        self.added = []
        self.patch(ignore, "add", lambda entries: self.added.append(entries) or 0)
        self.patch(scrape_online, "make_client", lambda: object())
        self.out = io.StringIO()

    def patch(self, target, name, value):
        p = mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def answers(self, *items):
        items = list(items)

        def ask(prompt):
            item = items.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        self.patch(ui, "ask", ask)

    def review(self, keys=KEYS):
        with contextlib.redirect_stdout(self.out):
            return scrape_review.review({"gb": GB}, keys, {k: 1024 for k in keys})

    def pending(self):
        return sorted(scrape_state.notgames())


class SearchNameTest(unittest.TestCase):
    def test_search_name_strips_tags_and_extension(self):
        self.assertEqual(scrape_review.search_name("Jeep Jamboree - Off-Road Adventure (USA).zip"),
                         "Jeep Jamboree - Off-Road Adventure")
        self.assertEqual(scrape_review.search_name("Game [b] (Rev 1).7z"), "Game")


class ReviewTest(ReviewBase):
    def test_shows_what_screenscraper_said(self):
        self.answers("k", "k", "k")
        self.review()
        self.assertIn("Study Cart · Educational · 1999", self.out.getvalue())
        self.assertIn("A study aid.", self.out.getvalue())

    def test_ignore_one_keep_one(self):
        self.answers("i", "k", "")
        self.assertEqual(self.review(), 0)
        self.assertEqual(self.added, [{"gb": ["a.zip"]}])
        self.assertEqual(self.pending(), ["gb/b.zip", "gb/c.zip"])

    def test_ignore_all_rest_after_confirm(self):
        self.answers("k", "I")
        self.patch(ui, "confirm", lambda *a, **k: True)
        self.review()
        self.assertEqual(self.added, [{"gb": ["b.zip", "c.zip"]}])
        self.assertEqual(self.pending(), ["gb/a.zip"])

    def test_ignore_all_declined_asks_again(self):
        self.answers("I", "k", "k", "k")
        self.patch(ui, "confirm", lambda *a, **k: False)
        self.review()
        self.assertEqual(self.added, [])

    def test_search_pick_scrapes_and_clears(self):
        self.answers("s", "", "k", "k")
        seen = {}

        def resolve(client, system, query):
            seen["query"] = query
            return 42

        def match(args):
            seen["game"] = args.game
            scrape_state.save_match(args.system, args.rom, 42)
            return 0
        self.patch(scrape_online, "resolve_manual", resolve)
        self.patch(scrape_online, "match_command", match)
        self.review()
        self.assertEqual(seen, {"query": "a", "game": "42"})
        self.assertEqual(self.pending(), ["gb/b.zip", "gb/c.zip"])

    def test_search_cancel_returns_to_prompt(self):
        self.answers("s", "Other Name", "k", "k", "k")

        def resolve(client, system, query):
            raise screenscraper.NotFound("cancelled")
        self.patch(scrape_online, "resolve_manual", resolve)
        self.review()
        self.assertEqual(self.added, [])
        self.assertEqual(self.pending(), KEYS)

    def test_failed_match_stays_pending(self):
        self.answers("s", "", "k", "k", "k")
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)
        self.patch(scrape_online, "match_command", lambda args: 1)
        self.review()
        self.assertEqual(self.pending(), KEYS)

    def test_ctrl_c_keeps_chosen_ignores(self):
        self.answers("i", KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.review()
        self.assertEqual(self.added, [{"gb": ["a.zip"]}])
        self.assertNotIn("gb/a.zip", self.pending())


class ReviewCommandTest(ReviewBase):
    def run_cmd(self, system=None, tty=True):
        with mock.patch.object(sys.stdin, "isatty", lambda: tty), contextlib.redirect_stdout(self.out):
            return scrape_review.review_command(argparse.Namespace(system=system))

    def test_review_command_nothing_pending(self):
        for key in KEYS:
            scrape_state.clear_notgame("gb", key.split("/", 1)[1])
        self.assertEqual(self.run_cmd(), 0)
        self.assertIn("No non-game results to review", self.out.getvalue())

    def test_review_command_needs_a_terminal(self):
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            self.run_cmd(tty=False)
        self.assertEqual(e.exception.code, 2)

    def test_review_command_skips_gone_or_ignored(self):
        self.patch(inventory, "stat", lambda keys: {"gb/b.zip": 5})  # a.zip and c.zip are gone or ignored
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append((keys, sizes)) or 0)
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual(seen, [(["gb/b.zip"], {"gb/b.zip": 5})])
        self.assertEqual(self.pending(), ["gb/b.zip"])

    def test_review_command_one_system(self):
        scrape_state.mark_notgame("nds", "x.zip", INFO)
        self.patch(inventory, "stat", lambda keys: {k: 1 for k in keys})
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append(keys) or 0)
        self.run_cmd(system="gb")
        self.assertEqual(seen, [KEYS])


if __name__ == "__main__":
    unittest.main()
