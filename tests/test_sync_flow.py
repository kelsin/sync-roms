import contextlib
import io
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import cli, clean, downloads, s3, scrape_plan, store, ui, usersettings  # noqa: E402
from test_cli_sync import MANIFEST, list_sizes  # noqa: E402


def captured(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*a, **kw)
    return result, out.getvalue()


class CleanDirsTest(unittest.TestCase):
    def run_clean(self, dot_clean, tty=False, yes=True):
        calls = []
        with tempfile.TemporaryDirectory() as root, contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(clean, "_clean_root", root))
            st.enter_context(mock.patch.object(clean.shutil, "which", lambda n: "/usr/bin/dot_clean"))
            st.enter_context(mock.patch.object(clean, "dot_clean", dot_clean))
            st.enter_context(mock.patch.object(clean.subprocess, "run", lambda *a, **k: calls.append(a[0]) or mock.Mock(returncode=0)))
            st.enter_context(mock.patch.object(clean.sys.stdin, "isatty", lambda: tty))
            st.enter_context(mock.patch.object(ui, "ASSUME_YES", yes))
            st.enter_context(mock.patch.object(ui, "confirm", lambda *a, **k: True))
            _, out = captured(clean.clean_dirs)
        return calls, out

    def test_announces_finalizing_card(self):
        _, out = self.run_clean(lambda p: (True, []))
        self.assertIn("Finalizing card", out)

    def test_ctrl_c_during_cleaning_is_caught(self):
        def boom(path):
            raise KeyboardInterrupt
        _, out = self.run_clean(boom)
        self.assertIn("Skipped", out)

    def test_sudo_is_not_run_without_a_terminal(self):
        calls, out = self.run_clean(lambda p: (False, ["/x/._a"]))
        self.assertFalse([c for c in calls if c[0] == "sudo"])
        self.assertIn("sudo mdutil", out)

    def test_sudo_is_not_run_with_yes(self):
        calls, _ = self.run_clean(lambda p: (False, ["/x/._a"]), tty=True)
        self.assertFalse([c for c in calls if c[0] == "sudo"])

    def test_sudo_runs_on_a_terminal(self):
        calls, _ = self.run_clean(lambda p: (False, ["/x/._a"]), tty=True, yes=False)
        self.assertTrue([c for c in calls if c[0] == "sudo"])


class DownloadInterruptTest(unittest.TestCase):
    def run_interrupted(self, draws_that_interrupt):
        release, n = threading.Event(), []

        def download(job, cb):
            release.wait(5)

        def draw(self_, done):
            n.append(done)
            if len(n) in draws_that_interrupt:
                raise KeyboardInterrupt
            if len(n) >= 4:
                release.set()

        exits = []

        def hard_exit():
            release.set()
            exits.append(1)
            raise SystemExit(130)

        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(s3, "download", download))
            st.enter_context(mock.patch.object(ui.ProgressBar, "draw", draw))
            st.enter_context(mock.patch.object(downloads, "hard_exit", hard_exit))
            st.enter_context(mock.patch.object(downloads.time, "sleep", lambda s: None))
            try:
                captured(downloads.run_downloads, [("gba/a.zip", "/tmp/x/a.zip", 5)], "ROMs", "i", "/tmp/x")
            except (KeyboardInterrupt, SystemExit):
                pass
        return n, exits

    def test_bar_keeps_drawing_while_waiting_for_in_flight_files(self):
        n, exits = self.run_interrupted({1})
        self.assertGreaterEqual(len(n), 3)
        self.assertEqual(exits, [])

    def test_second_ctrl_c_aborts_immediately(self):
        _, exits = self.run_interrupted({1, 2})
        self.assertEqual(exits, [1])


class PrepareDirsTest(unittest.TestCase):
    def test_dry_run_does_not_ask_to_continue(self):
        layout = {"label": "X", "roms_dir": "ROMs", "bios_dir": "BIOS"}
        with tempfile.TemporaryDirectory() as base, mock.patch.object(ui, "confirm", side_effect=AssertionError("asked")):
            res, _ = captured(cli.prepare_dirs, base, layout, True)
        self.assertIsNotNone(res)


class PlainOutputTest(unittest.TestCase):
    def test_plain_strips_emoji(self):
        self.assertEqual(ui.plain("  [1/2] ✅ gba/a.zip"), "  [1/2] ok gba/a.zip")
        self.assertEqual(ui.plain("🎉 Done!"), "Done!")
        self.assertEqual(ui.plain("⚠️  careful"), "warning: careful")

    def test_non_tty_progress_prints_periodic_lines(self):
        times = iter([0, 1, 31, 32, 62])
        with mock.patch.object(ui.time, "monotonic", lambda: next(times)):
            bar = ui.ProgressBar(4, lambda: 0.5)
            bar.shown = False
            _, out = captured(lambda: [bar.draw(1) for _ in range(4)])
        self.assertEqual(out.count("progress:"), 2)


class SyncFlowTest(unittest.TestCase):
    def run_sync(self, cards=None, yes=True, dry_run=False, plan=None, picks=None, stale=(), extra=()):
        updates, picked = [], []
        with tempfile.TemporaryDirectory() as card_dir:
            card = os.path.basename(card_dir)
            argv = ["sync-roms", card_dir] + (["--yes"] if yes else []) + (["--dry-run"] if dry_run else [])
            cards = {card: v for v in [cards or {}]} if cards is not None else {}
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: {}}),
                        (store, {"load_manifest": lambda names=(): MANIFEST, "load_cards": lambda: cards,
                                 "save_card": lambda *a: None,
                                 "update_card": lambda name, **v: updates.append(v)}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: (None, "esde"),
                                      "pick_systems": lambda rows, present, state, editable: picked.append(present) or [0]}),
                        (cli.downloads, {"run_downloads": lambda *a: 0, "plan_downloads": lambda jobs, unzip=False: plan if plan is not None else jobs}),
                        (cli.clean, {"clean_android_media": lambda *a: None}),
                        (scrape_plan, {"stale_media": lambda *a: [os.path.join(card_dir, s) for s in stale]})):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                st.enter_context(mock.patch.object(ui, "confirm", lambda *a, **k: True))
                st.enter_context(mock.patch.object(scrape_plan, "SCRAPE_LAYOUTS", {"esde"}))
                st.enter_context(mock.patch.object(scrape_plan, "load_scrape_data", lambda *a: ({}, {})))
                st.enter_context(mock.patch.object(scrape_plan, "build_scrape_plan", lambda *a: {"jobs": [], "extras": [], "gamelists": {}, "writes": []}))
                st.enter_context(mock.patch.object(scrape_plan, "apply_scrape_plan", lambda *a: 0))
                for s in stale:
                    open(os.path.join(card_dir, s), "w").close()
                code, out = captured(cli.sync)
                root = cli.clean._clean_root
                left = [s for s in stale if os.path.exists(os.path.join(card_dir, s))]
        return code, out, updates, picked, root, left

    def test_nothing_downloaded_skips_card_cleaning(self):
        _, _, _, _, root, _ = self.run_sync(plan=[])
        self.assertIsNone(root)

    def test_download_marks_the_card_for_cleaning(self):
        _, _, _, _, root, _ = self.run_sync()
        self.assertIsNotNone(root)

    def test_stale_media_listed_before_removal(self):
        _, out, _, _, _, left = self.run_sync(stale=("a.png", "b.png"))
        self.assertIn("2 media file(s)", out)
        self.assertIn("a.png", out)
        self.assertLess(out.index("a.png"), out.index("Removed 2"))
        self.assertEqual(left, [])

    def test_picker_selection_is_saved_for_the_card(self):
        _, _, updates, _, _, _ = self.run_sync(cards={"device": "full"}, yes=False)
        self.assertIn({"systems": ["gba"]}, updates)

    def test_dry_run_does_not_save_the_selection(self):
        _, _, updates, _, _, _ = self.run_sync(cards={}, yes=False, dry_run=True)
        self.assertNotIn({"systems": ["gba"]}, updates)

    def test_saved_selection_starts_the_picker(self):
        _, _, _, picked, _, _ = self.run_sync(cards={"systems": ["gba"]}, yes=False)
        self.assertEqual(picked, [[0]])

    def test_yes_with_saved_selection_skips_the_picker(self):
        code, _, _, picked, _, _ = self.run_sync(cards={"systems": ["gba"]})
        self.assertEqual((code, picked), (0, []))


if __name__ == "__main__":
    unittest.main()
