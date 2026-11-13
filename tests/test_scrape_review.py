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
from test_scrape_run import GBA, RunBase, game  # noqa: E402
from sync_roms import ignore, inventory, runtime, s3, scrape_files, scrape_online, scrape_review, scrape_state, screenscraper, ui  # noqa: E402

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

    def test_search_scrapes_without_asking_again(self):
        self.answers("s", "", "k", "k", "k")
        seen = []
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)
        self.patch(scrape_online, "match_command", lambda args: seen.append(args.confirmed) or 1)
        self.review()
        self.assertEqual(seen, [True])

    def test_failed_match_with_an_old_saved_match_stays_pending(self):
        scrape_state.save_match("gb", "a.zip", 42)  # the same game, saved before; the forced run fails
        self.answers("s", "", "k", "k", "k")
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)
        self.patch(scrape_online, "match_command", lambda args: 1)
        self.review()
        self.assertEqual(self.pending(), KEYS)

    def test_search_error_returns_to_prompt(self):
        self.answers("s", "", "k", "k", "k")

        def resolve(client, system, query):
            raise screenscraper.ApiError("server down")
        self.patch(scrape_online, "resolve_manual", resolve)
        self.review()
        self.assertIn("server down", self.out.getvalue())
        self.assertEqual(self.pending(), KEYS)

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

    def test_shows_each_items_position(self):
        self.answers("k", "k", "k")
        self.review()
        for pos in ("1 of 3", "2 of 3", "3 of 3"):
            self.assertIn(pos, self.out.getvalue())

    def test_quit_applies_queued_ignores_and_stops(self):
        self.answers("i", "q")  # a third question would find no answer
        self.assertEqual(self.review(), 0)
        self.assertEqual(self.added, [{"gb": ["a.zip"]}])
        self.assertEqual(self.pending(), ["gb/b.zip", "gb/c.zip"])
        self.assertNotIn("3 of 3", self.out.getvalue())

    def test_back_takes_back_the_last_ignore_and_shows_that_item_again(self):
        self.answers("i", "k", "b", "k", "k", "k")
        self.review()
        self.assertEqual(self.added, [])
        self.assertEqual(self.pending(), KEYS)
        self.assertEqual(self.out.getvalue().count("1 of 3"), 2)

    def test_back_with_no_ignore_says_so(self):
        self.answers("b", "k", "k", "k")
        self.review()
        self.assertIn("No ignore to take back", self.out.getvalue())
        self.assertEqual(self.out.getvalue().count("1 of 3"), 1)

    def test_back_over_a_search_says_it_stays(self):
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)

        def match(args):
            scrape_state.save_match(args.system, args.rom, 42)
            return 0
        self.patch(scrape_online, "match_command", match)
        self.answers("i", "s", "", "b", "k", "k")  # a ignored, b searched, back at c to a, then a and c kept
        self.review()
        self.assertIn("gb/b.zip was scraped from a search; that stays", self.out.getvalue())
        self.assertEqual(self.out.getvalue().count("2 of 3"), 1)  # not shown again
        self.assertEqual(self.added, [])
        self.assertEqual(self.pending(), ["gb/a.zip", "gb/c.zip"])

    def test_unknown_answer_says_so(self):
        self.answers("x", "k", "k", "k")
        self.review()
        self.assertIn("Unknown answer 'x'", self.out.getvalue())

    def test_kept_items_come_after_the_unseen_ones_next_time(self):
        self.answers("k", "q")
        self.review()
        self.assertEqual(scrape_state.kept(), {"gb/a.zip"})
        self.out = io.StringIO()
        self.answers("k", "k", "i")
        self.review()
        out = self.out.getvalue()
        self.assertLess(out.index("gb/b.zip"), out.index("gb/c.zip"))
        self.assertLess(out.index("gb/c.zip"), out.index("gb/a.zip"))
        self.assertEqual(scrape_state.kept(), {"gb/b.zip", "gb/c.zip"})  # the ignored one's mark is gone
        self.assertEqual(self.pending(), ["gb/b.zip", "gb/c.zip"])

    def test_item_line_is_on_stderr_under_quiet(self):
        self.answers("q")
        err = io.StringIO()
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(err):
            self.review()
        self.assertIn("gb/a.zip", err.getvalue())
        self.assertIn("1 of 3", err.getvalue())

    def quiet_review(self):
        err = io.StringIO()
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(err):
            self.review()
        return err.getvalue()

    def test_failed_search_reason_on_stderr_under_quiet(self):
        def resolve(client, system, query):
            raise screenscraper.ApiError("server down")
        self.patch(scrape_online, "resolve_manual", resolve)
        self.answers("s", "", "q")
        self.assertIn("server down", self.quiet_review())

    def test_failed_match_says_not_scraped_under_quiet(self):
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)
        self.patch(scrape_online, "match_command", lambda args: 1)
        self.answers("s", "", "q")
        self.assertIn("gb/a.zip was not scraped", self.quiet_review())

    def test_kept_list_with_bad_entries_is_read_as_its_strings(self):
        self.write_json("scrape-notgames.json", {**scrape_state.notgames(), "kept": [["x"], {"y": 1}, 3, "gb/a.zip"]})
        self.assertEqual(scrape_state.kept(), {"gb/a.zip"})
        self.answers("q")
        self.review()
        self.assertIn("gb/b.zip", self.out.getvalue())  # a.zip is kept, so b.zip comes first

    def test_new_notgame_mark_drops_the_kept_mark(self):
        scrape_state.keep("gb", "a.zip")
        scrape_state.mark_notgame("gb", "a.zip", INFO)
        self.assertEqual(scrape_state.kept(), set())

    def test_ignore_all_after_a_search_skips_the_searched_rom(self):
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)

        def match(args):
            scrape_state.save_match(args.system, args.rom, 42)
            return 0
        self.patch(scrape_online, "match_command", match)
        asked = []
        self.patch(ui, "confirm", lambda question, **k: asked.append(question) or True)
        self.answers("i", "s", "", "b", "I")  # a ignored, b searched, back to a, then ignore a and the rest
        self.review()
        self.assertEqual(asked, ["   Ignore this and the 1 remaining ROM(s)?"])
        self.assertEqual(self.added, [{"gb": ["a.zip", "c.zip"]}])

    def test_nested_step_backs(self):
        self.answers("i", "i", "b", "b", "k", "k", "k")
        self.review()
        self.assertEqual(self.added, [])
        self.assertEqual(self.out.getvalue().count("1 of 3"), 2)
        self.assertEqual(self.out.getvalue().count("2 of 3"), 3)  # shown, back to it, and after a again
        self.assertEqual(self.pending(), KEYS)


class ReviewCommandTest(ReviewBase):
    def run_cmd(self, system=None, tty=True):
        with mock.patch.object(sys.stdin, "isatty", lambda: tty), contextlib.redirect_stdout(self.out):
            return scrape_review.review_command(argparse.Namespace(system=system))

    def test_review_command_nothing_pending(self):
        for key in KEYS:
            scrape_state.clear_notgame("gb", key.split("/", 1)[1])
        self.assertEqual(self.run_cmd(), 0)
        self.assertIn("No non-game or unknown ROMs to review", self.out.getvalue())

    def test_review_command_needs_a_terminal(self):
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            self.run_cmd(tty=False)
        self.assertEqual(e.exception.code, 2)

    def test_review_command_skips_gone_or_ignored(self):
        self.patch(s3, "read_root", lambda: "/storage")
        self.patch(inventory, "stat", lambda keys: {"gb/b.zip": 5})  # a.zip and c.zip are gone or ignored
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append((keys, sizes)) or 0)
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual(seen, [(["gb/b.zip"], {"gb/b.zip": 5})])
        self.assertEqual(self.pending(), ["gb/b.zip"])

    def test_review_command_bucket_without_cache_lists_sizes(self):
        self.patch(runtime, "ROOT", None)
        self.patch(runtime, "_mirror_root", None)
        self.patch(inventory, "current", lambda: None)
        self.patch(s3, "list_sizes", lambda prefix, sizes=True: {"gb/a.zip": 7} if prefix == "gb/" else {})
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append(sizes) or 0)
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual(seen, [{"gb/a.zip": 7}])

    def test_review_command_keeps_marks_when_storage_cannot_be_read(self):
        self.patch(s3, "read_root", lambda: os.path.join(self.tmp.name, "unmounted"))
        self.patch(inventory, "current", lambda: None)
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            self.run_cmd()
        self.assertEqual(e.exception.code, 3)
        self.assertEqual(self.pending(), KEYS)

    def test_review_command_one_system(self):
        scrape_state.mark_notgame("nds", "x.zip", INFO)
        self.patch(s3, "read_root", lambda: "/storage")
        self.patch(inventory, "stat", lambda keys: {k: 1 for k in keys})
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append(keys) or 0)
        self.run_cmd(system="gb")
        self.assertEqual(seen, [KEYS])


class UnknownReviewTest(ReviewBase):
    def setUp(self):
        super().setUp()
        scrape_state.mark_unknown("gb", "u.zip")
        scrape_state.flush_unknown()

    def test_unknown_shown_as_unknown(self):
        self.answers("k")
        self.review(["gb/u.zip"])
        self.assertIn("❔ gb/u.zip", self.out.getvalue())
        self.assertIn("doesn't know this ROM", self.out.getvalue())

    def test_ignore_clears_unknown(self):
        self.answers("i")
        self.review(["gb/u.zip"])
        self.assertEqual(self.added, [{"gb": ["u.zip"]}])
        self.assertEqual(scrape_state.unknown(), set())

    def test_search_match_clears_unknown(self):
        self.answers("s", "")
        self.patch(scrape_online, "resolve_manual", lambda *a: 42)

        def match(args):
            scrape_state.save_match(args.system, args.rom, 42)
            return 0
        self.patch(scrape_online, "match_command", match)
        self.review(["gb/u.zip"])
        self.assertEqual(scrape_state.unknown(), set())

    def run_cmd(self, metadata):
        self.patch(s3, "read_root", lambda: "/storage")
        self.patch(inventory, "stat", lambda keys: {k: 1 for k in keys})
        self.patch(scrape_online, "load_metadata", lambda name: metadata)
        self.patch(scrape_review, "_systems", lambda name: {"gb": GB})
        seen = []
        self.patch(scrape_review, "review", lambda systems, keys, sizes, client=None: seen.append(keys) or 0)
        with mock.patch.object(sys.stdin, "isatty", lambda: True), contextlib.redirect_stdout(self.out):
            scrape_review.review_command(argparse.Namespace(system=None))
        return seen

    def test_review_command_includes_unknown(self):
        self.assertEqual(self.run_cmd({}), [KEYS + ["gb/u.zip"]])

    def test_review_command_drops_unknown_with_metadata(self):
        self.assertEqual(self.run_cmd({"u.zip": {}}), [KEYS])
        self.assertEqual(scrape_state.unknown(), set())


class ReviewRunTest(RunBase):
    def test_search_reuses_the_client_with_no_quota_request_or_results(self):
        self.put("gba/a.zip")
        scrape_state.mark_notgame("gba", "a.zip", INFO)
        self.client.games["x"] = game(7, "Seven")
        made = []
        answers = ["s", "7"]
        with mock.patch.object(scrape_online, "make_client", lambda: made.append(1) or self.client), \
                mock.patch.object(ui, "ask", lambda prompt: answers.pop(0)), contextlib.redirect_stdout(self.out):
            scrape_review.review({"gba": GBA}, ["gba/a.zip"], {"gba/a.zip": 3})
        self.assertEqual(made, [1])
        self.assertEqual(self.client.quota_calls, 0)
        self.assertNotIn("Results", self.out.getvalue())
        self.assertIn("gba/a.zip → Seven", self.out.getvalue())
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Seven"}})
        self.assertEqual(scrape_state.notgames(), {})

    def test_run_with_unmatched_roms_prints_the_hints(self):
        self.put("gba/a.zip")
        self.put("gba/z.zip")  # ScreenScraper doesn't know it
        self.assertEqual(self.run_scrape(), 0)
        self.assertIn("sync-roms scrape review [SYSTEM]", self.out.getvalue())
        self.assertIn("sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME", self.out.getvalue())

    def test_rom_found_by_a_later_run_loses_its_kept_mark(self):
        self.put("gba/a.zip")
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.flush_unknown()
        scrape_state.keep("gba", "a.zip")
        self.assertEqual(self.run_scrape(retry=True), 0)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})
        self.assertEqual(scrape_state.kept(), set())

    def test_run_with_every_rom_matched_prints_no_hints(self):
        self.put("gba/a.zip")
        self.assertEqual(self.run_scrape(), 0)
        self.assertNotIn("scrape review", self.out.getvalue())


class MissingCommandTest(DataDir):
    def run_cmd(self, systems, roms, metadata):
        out = io.StringIO()
        with mock.patch.object(scrape_online, "_pick_systems", lambda name: systems), \
                mock.patch.object(scrape_files, "bucket_roms", lambda systems, all_files=False: roms), \
                mock.patch.object(scrape_online, "load_metadata", lambda name: metadata[name]), \
                contextlib.redirect_stdout(out):
            code = scrape_online.missing_command(argparse.Namespace(system=None, all=False))
        return code, out.getvalue()

    def test_lists_each_rom_and_why(self):
        scrape_state.mark_notgame("gb", "n.zip", INFO)
        scrape_state.mark_unknown("gb", "u.zip")
        scrape_state.mark_unknown("gb", "m.zip")
        scrape_state.flush_unknown()
        scrape_state.save_match("gb", "m.zip", 7)
        code, out = self.run_cmd([GB], {"gb": {"done.zip", "n.zip", "u.zip", "m.zip", "new.zip"}}, {"gb": {"done.zip": {}}})
        self.assertEqual(code, 0)
        self.assertIn("gb (4): 1 non-game, 1 not on ScreenScraper, 1 matched, not scraped yet, 1 not looked up yet", out)
        for line in ("🚫 n.zip", "❔ u.zip", "🔗 m.zip", "⏳ new.zip"):
            self.assertIn(line, out)
        self.assertNotIn("done.zip", out)

    def test_system_without_screenscraper_id(self):
        nes = {"name": "NES", "bucket": "nes", "folders": {}}
        _, out = self.run_cmd([nes], {"nes": {"a.zip"}}, {"nes": {}})
        self.assertIn("nes (1): no ScreenScraper system id", out)

    def test_nothing_missing(self):
        _, out = self.run_cmd([GB], {"gb": {"a.zip"}}, {"gb": {"a.zip": {}}})
        self.assertIn("Every ROM has metadata", out)

    def test_bad_metadata_skipped(self):
        def bad(name):
            raise ValueError("bad")
        out = io.StringIO()
        with mock.patch.object(scrape_online, "_pick_systems", lambda name: [GB]), \
                mock.patch.object(scrape_files, "bucket_roms", lambda systems, all_files=False: {"gb": {"a.zip"}}), \
                mock.patch.object(scrape_online, "load_metadata", bad), contextlib.redirect_stdout(out):
            scrape_online.missing_command(argparse.Namespace(system=None, all=False))
        self.assertIn("isn't valid JSON; skipping gb", out.getvalue())


if __name__ == "__main__":
    unittest.main()
