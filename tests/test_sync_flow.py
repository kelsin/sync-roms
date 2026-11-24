import contextlib
import io
import itertools
import os
import plistlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import budget, cli, clean, downloads, frontend, ignore, inventory, mirroring, runtime, s3, scrape_plan, store, ui, usersettings  # noqa: E402
from sync_roms import collections as collections_mod  # noqa: E402
from helpers import MANIFEST, list_sizes  # noqa: E402


GAME = {"title": "Game", "system": "gba", "bucket": "gba/Game.zip"}
FAVS = {"id": "favs", "name": "Favs", "games": [GAME]}
REAL_LOAD_COLLECTIONS = collections_mod.load_collections
REAL_BUILD_SCRAPE_PLAN, REAL_APPLY_SCRAPE_PLAN = scrape_plan.build_scrape_plan, scrape_plan.apply_scrape_plan
REAL_STALE_MEDIA = scrape_plan.stale_media
REAL_LOAD_CARDS, REAL_SAVE_CARD, REAL_UPDATE_CARD = store.load_cards, store.save_card, store.update_card
REAL_SAVED_SETUP = cli.picker.saved_setup
SCRAPED = {"gba": ({"scrapes/gba/covers/Game.png": 5}, {"Game.zip": {"name": "The Game"}})}


def read_from(card_dir, *parts):
    path = os.path.join(card_dir, *parts)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def captured(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*a, **kw)
    return result, out.getvalue()


class CleanDirsTest(unittest.TestCase):
    def run_clean(self, delete, tty=False, yes=True, spotlight=True):
        calls = []
        with tempfile.TemporaryDirectory() as root, contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(clean, "_clean_root", root))
            st.enter_context(mock.patch.object(clean.sys, "platform", "darwin"))
            st.enter_context(mock.patch.object(clean.shutil, "which", lambda n: "/usr/bin/mdutil"))
            st.enter_context(mock.patch.object(clean, "delete_appledouble", delete))
            st.enter_context(mock.patch.object(clean, "spotlight_active", lambda p: spotlight))
            st.enter_context(mock.patch.object(clean.time, "sleep", lambda s: None))
            st.enter_context(mock.patch.object(clean.subprocess, "run", lambda *a, **k: calls.append(a[0]) or mock.Mock(returncode=0)))
            st.enter_context(mock.patch.object(clean.sys.stdin, "isatty", lambda: tty))
            st.enter_context(mock.patch.object(ui, "ASSUME_YES", yes))
            st.enter_context(mock.patch.object(ui, "confirm", lambda *a, **k: True))
            _, out = captured(clean.clean_dirs)
        return calls, out

    def test_announces_finalizing_card(self):
        _, out = self.run_clean(lambda p: [])
        self.assertIn("Finalizing card", out)

    def test_ctrl_c_during_cleaning_is_caught(self):
        def boom(path):
            raise KeyboardInterrupt
        _, out = self.run_clean(boom)
        self.assertIn("Skipped", out)

    def run_real_walk(self, removable=True):
        """clean_dirs with the real walk over a card holding ._a and ROMs/._b, counting the card walks and removals."""
        walks, removed, real_scandir, real_remove, real_delete = [], [], os.scandir, os.remove, clean.delete_appledouble

        def scandir(path):
            if isinstance(path, str):  # os.listdir also goes through scandir, by file descriptor
                walks.append(path)
            return real_scandir(path)

        def remove(path):
            if not removable:
                raise PermissionError("busy")
            removed.append(os.path.basename(path))
            real_remove(path)

        def with_files(root):
            os.makedirs(os.path.join(root, "ROMs"), exist_ok=True)
            for name in ("._a", os.path.join("ROMs", "._b")):
                open(os.path.join(root, name), "w").close()
            return real_delete(root)
        with mock.patch.object(clean.os, "scandir", scandir), mock.patch.object(clean.os, "remove", remove):
            _, out = self.run_clean(with_files, spotlight=False)
        return walks, removed, out

    def test_the_walk_deletes_nested_files_and_skips_the_folders_macos_keeps(self):
        with tempfile.TemporaryDirectory() as root:
            kept = [os.path.join(root, d, "._k") for d in (".Spotlight-V100", ".fseventsd", ".Trashes")]
            gone = [os.path.join(root, "._a"), os.path.join(root, "ROMs", "gba", "._b")]
            for path in kept + gone + [os.path.join(root, "ROMs", "game.zip")]:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            link = os.path.join(root, "link")
            os.symlink(os.path.join(root, "ROMs"), link)
            left, _ = captured(clean.delete_appledouble, root)
            self.assertEqual(left, [])
            self.assertEqual([os.path.exists(p) for p in gone], [False, False])
            self.assertEqual([os.path.exists(p) for p in kept], [True] * 3)
            self.assertTrue(os.path.exists(os.path.join(root, "ROMs", "game.zip")))

    def test_the_walk_returns_the_files_it_could_not_delete(self):
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, "._a"), "w").close()
            with mock.patch.object(clean.os, "remove", side_effect=PermissionError("busy")):
                left, _ = captured(clean.delete_appledouble, root)
            self.assertEqual(left, [os.path.join(root, "._a")])

    def walk_with_clock(self, out, step):
        """Walk a card with a ._ file in Roms/PS and Roms/GBA, each clock reading step seconds after the last, printing to out."""
        with tempfile.TemporaryDirectory() as root:
            for d in ("Roms/PS", "Roms/GBA"):
                os.makedirs(os.path.join(root, d))
                open(os.path.join(root, d, "._a"), "w").close()
            with mock.patch.object(clean.time, "monotonic", side_effect=itertools.count(0, step)), \
                    mock.patch.object(clean.shutil, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                    contextlib.redirect_stdout(out):
                left = clean.delete_appledouble(root)
            return left, out.getvalue(), root

    def test_the_walk_redraws_its_progress_in_place_on_a_terminal(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        left, out, root = self.walk_with_clock(Tty(), ui.POLL)
        self.assertEqual(left, [])
        self.assertIn("\r\033[J  🧼 ", out)
        self.assertRegex(out, r"\d+ folders · \d+ ._ deleted · Roms")
        self.assertTrue(out.endswith(f"\r\033[J  ✅ {root}\n"))

    def test_the_walk_prints_a_plain_progress_line_off_a_terminal(self):
        left, out, root = self.walk_with_clock(io.StringIO(), ui.PLAIN_INTERVAL)
        self.assertRegex(out, r"progress: \d+ folders checked, \d+ ._ file\(s\) deleted")
        self.assertNotIn("\033", out)
        self.assertTrue(out.endswith(f"  ✅ {root}\n"))

    def test_a_fast_walk_prints_no_progress(self):
        with tempfile.TemporaryDirectory() as root:
            _, out = captured(clean.delete_appledouble, root)
            self.assertEqual(out, f"  ✅ {root}\n")

    def test_a_card_that_already_has_the_guard_files_is_not_written_to(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".fseventsd"))
            for name in (".metadata_never_index", os.path.join(".fseventsd", "no_log")):
                open(os.path.join(root, name), "w").close()
            stale_log = os.path.join(root, ".fseventsd", "0000")
            open(stale_log, "w").close()
            with mock.patch.object(clean, "_clean_root", root), mock.patch.object(clean.sys, "platform", "linux"), \
                    mock.patch("builtins.open", side_effect=AssertionError("wrote")), \
                    mock.patch.object(clean.os, "remove", side_effect=AssertionError("removed")):
                clean._clean_card()
            self.assertTrue(os.path.exists(stale_log))

    def test_a_retry_removes_the_files_left_without_walking_the_card_again(self):
        walks, removed, out = self.run_real_walk()
        self.assertEqual(len(walks), 2)  # the root and ROMs, in the one walk
        self.assertEqual(sorted(removed), ["._a", "._b"])
        self.assertNotIn("still there", out)

    def test_files_that_cannot_be_removed_are_listed_after_the_retries_without_walking_again(self):
        with contextlib.redirect_stderr(io.StringIO()):
            walks, _, out = self.run_real_walk(removable=False)
        self.assertEqual(len(walks), 2)
        self.assertEqual(out.count("Removing the 2 ._ file(s) left"), clean.DELETE_RETRIES)
        self.assertIn("2 ._ file(s) are still there after deleting", out)

    def test_sudo_is_skipped_when_spotlight_is_off(self):
        calls, out = self.run_clean(lambda p: [], tty=True, yes=False, spotlight=False)
        self.assertFalse([c for c in calls if c[0] == "sudo"])
        self.assertNotIn("sudo mdutil", out)

    def test_sudo_is_not_run_without_a_terminal(self):
        calls, out = self.run_clean(lambda p: ["/x/._a"])
        self.assertFalse([c for c in calls if c[0] == "sudo"])
        self.assertIn("sudo mdutil", out)

    def test_sudo_is_not_run_with_yes(self):
        calls, _ = self.run_clean(lambda p: ["/x/._a"], tty=True)
        self.assertFalse([c for c in calls if c[0] == "sudo"])

    def test_sudo_runs_on_a_terminal(self):
        calls, _ = self.run_clean(lambda p: ["/x/._a"], tty=True, yes=False)
        self.assertTrue([c for c in calls if c[0] == "sudo"])

    def test_quiet_shows_the_sudo_command_with_its_question(self):
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(io.StringIO()) as err:
            _, out = self.run_clean(lambda p: [], tty=True, yes=False)
        self.assertIn("sudo mdutil -i off", err.getvalue())
        self.assertNotIn("sudo mdutil", out)

    def test_quiet_lists_the_files_left(self):
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(io.StringIO()) as err:
            _, _, out = self.run_real_walk(removable=False)
        self.assertIn("still there after deleting", err.getvalue())
        self.assertIn("._b", err.getvalue())
        self.assertNotIn("._b", out)


class CompletionOrderTest(unittest.TestCase):
    def test_a_file_that_finishes_first_prints_first_while_a_slow_one_is_listed(self):
        jobs = [("gba/slow.zip", "/tmp/x/gba/slow.zip", 5), ("gba/fast.zip", "/tmp/x/gba/fast.zip", 5)]
        fast_printed, seen = threading.Event(), []
        real_say = ui.ProgressBar.say

        def say(self_, line):
            if "fast.zip" in line:
                seen.append([n for n, _, _ in self_.active()])
                fast_printed.set()
            real_say(self_, line)

        def download(job, callback=None, wrote=None):
            if "slow" in job[0]:
                assert fast_printed.wait(5)

        with mock.patch.object(s3, "download", download), mock.patch.object(ui.ProgressBar, "say", say), \
                mock.patch.object(ui, "POLL", 0.001):
            failed, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        self.assertEqual(failed, 0)
        lines = [l for l in out.splitlines() if "✅" in l]
        self.assertIn("[1/2]", lines[0]); self.assertIn("gba/fast.zip", lines[0])
        self.assertIn("[2/2]", lines[1]); self.assertIn("gba/slow.zip", lines[1])
        self.assertEqual(seen, [["gba/slow.zip"]])

    def test_many_instant_files_each_print_once(self):
        jobs = [(f"gba/{n}.zip", f"/tmp/x/gba/{n}.zip", 1) for n in range(20)]
        with mock.patch.object(s3, "download", lambda *a, **k: None), mock.patch.object(ui, "POLL", 0.001):
            _, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        for n in range(20):
            self.assertEqual(out.count(f"gba/{n}.zip"), 1)
        self.assertIn("[20/20]", out)

    def test_a_failure_prints_when_it_happens(self):
        jobs = [("gba/slow.zip", "/tmp/x/gba/slow.zip", 5), ("gba/bad.zip", "/tmp/x/gba/bad.zip", 5)]
        bad_printed = threading.Event()
        real_say = ui.ProgressBar.say

        def say(self_, line):
            if "bad.zip" in line:
                bad_printed.set()
            real_say(self_, line)

        def download(job, callback=None, wrote=None):
            if "bad" in job[0]:
                raise OSError("boom")
            assert bad_printed.wait(5)

        with mock.patch.object(s3, "download", download), mock.patch.object(ui.ProgressBar, "say", say), \
                mock.patch.object(ui, "POLL", 0.001):
            failed, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        self.assertEqual(failed, 1)
        self.assertLess(out.index("bad.zip"), out.index("✅"))


class DownloadInterruptTest(unittest.TestCase):
    def run_interrupted(self, draws_that_interrupt, fail=False):
        release, n = threading.Event(), []

        def download(job, cb, wrote=None):
            release.wait(5)
            if fail:
                raise OSError("boom")

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
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
            self.out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:
                downloads.run_downloads([("gba/a.zip", "/tmp/x/a.zip", 5)], "ROMs", "i", "/tmp/x")
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

    def test_in_flight_files_that_finish_after_ctrl_c_are_listed(self):
        self.run_interrupted({1})
        self.assertIn("✅ gba/a.zip", self.out.getvalue().split("Interrupted", 1)[1])

    def test_quiet_shows_an_in_flight_file_that_fails_after_ctrl_c(self):
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(io.StringIO()) as err:
            self.run_interrupted({1}, fail=True)
        self.assertIn("gba/a.zip", err.getvalue())

    def test_a_file_that_finishes_after_ctrl_c_leaves_the_in_flight_list(self):
        started, release_a, release_b, a_said = threading.Semaphore(0), threading.Event(), threading.Event(), threading.Event()
        after, interrupted, real_say = [], [], ui.ProgressBar.say

        def download(job, cb, wrote=None):
            started.release()
            (release_a if "a.zip" in job[0] else release_b).wait(5)

        def say(self_, line):
            if "✅ gba/a.zip" in line:
                a_said.set()
            real_say(self_, line)

        def draw(self_, done):
            if not interrupted:
                started.acquire(timeout=5)
                started.acquire(timeout=5)
                interrupted.append(1)
                raise KeyboardInterrupt
            release_a.set()  # only once the in-flight list is taken, so a.zip is still in it
            if a_said.is_set():
                after.append([n for n, _, _ in self_.active()])
                if len(after) >= 2:
                    release_b.set()

        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(s3, "download", download))
            st.enter_context(mock.patch.object(ui.ProgressBar, "say", say))
            st.enter_context(mock.patch.object(ui.ProgressBar, "draw", draw))
            st.enter_context(mock.patch.object(downloads.time, "sleep", lambda s: None))
            st.enter_context(mock.patch.object(runtime, "WORKERS", 2))
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
            st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            jobs = [("gba/a.zip", "/tmp/x/a.zip", 5), ("gba/b.zip", "/tmp/x/b.zip", 5)]
            with self.assertRaises(KeyboardInterrupt):
                downloads.run_downloads(jobs, "ROMs", "i", "/tmp/x")
        self.assertTrue(after)
        self.assertEqual(after[0], ["gba/b.zip"])

    def test_abort_removes_the_part_files_of_unfinished_downloads_and_flushes(self):
        started, release, seen = threading.Semaphore(0), threading.Event(), []

        def download(job, cb, wrote=None):
            open(job[1] + ".part", "wb").close()
            started.release()
            release.wait(5)

        def draw(self_, done):
            if not seen:
                started.acquire(timeout=5)
                started.acquire(timeout=5)
            seen.append(done)
            if len(seen) <= 2:
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as st:
            out = io.StringIO()
            out.flush = mock.Mock()

            def hard_exit():
                seen.append((sorted(os.listdir(tmp)), out.flush.called))
                release.set()
                raise SystemExit(130)
            st.enter_context(mock.patch.object(s3, "download", download))
            st.enter_context(mock.patch.object(ui.ProgressBar, "draw", draw))
            st.enter_context(mock.patch.object(downloads, "hard_exit", hard_exit))
            st.enter_context(mock.patch.object(downloads.time, "sleep", lambda s: None))
            st.enter_context(mock.patch.object(runtime, "WORKERS", 2))
            st.enter_context(contextlib.redirect_stdout(out))
            jobs = [("gba/a.zip", os.path.join(tmp, "a.zip"), 5), ("gba/b.zip", os.path.join(tmp, "b.zip"), 5)]
            with self.assertRaises(SystemExit):
                downloads.run_downloads(jobs, "ROMs", "i", tmp)
        self.assertEqual(seen[-1], ([], True))


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


class EjectTest(unittest.TestCase):
    def run_eject(self, info, unmount_code=0, platform="darwin", root="/Volumes/CARD"):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[:2] == ["diskutil", "info"]:
                return mock.Mock(returncode=0 if info is not None else 1, stdout=plistlib.dumps(info or {}))
            return mock.Mock(returncode=unmount_code, stdout="", stderr="Unmount of disk4 failed: at least one volume could not be unmounted")
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(clean, "_eject_root", root))
            st.enter_context(mock.patch.object(clean.sys, "platform", platform))
            st.enter_context(mock.patch.object(clean.shutil, "which", lambda n: "/usr/sbin/diskutil"))
            st.enter_context(mock.patch.object(clean.os.path, "ismount", lambda p: p in ("/", "/Volumes/CARD")))
            st.enter_context(mock.patch.object(clean.os.path, "realpath", lambda p: p))
            st.enter_context(mock.patch.object(clean.os, "chdir", lambda p: None))
            st.enter_context(mock.patch.object(clean.subprocess, "run", run))
            _, out = captured(clean.eject)
        return calls, out

    def test_unmounts_the_whole_disk_of_a_removable_card(self):
        calls, out = self.run_eject({"RemovableMediaOrExternalDevice": True, "ParentWholeDisk": "disk4"}, root="/Volumes/CARD/sub")
        self.assertEqual(calls, [["diskutil", "info", "-plist", "/Volumes/CARD"], ["diskutil", "unmountDisk", "disk4"]])
        self.assertIn("Safe to remove", out)

    def test_leaves_an_internal_disk_mounted(self):
        calls, out = self.run_eject({"RemovableMediaOrExternalDevice": False, "Internal": True, "ParentWholeDisk": "disk3"})
        self.assertEqual(calls, [["diskutil", "info", "-plist", "/Volumes/CARD"]])
        self.assertEqual(out, "")

    def test_leaves_a_network_share_mounted(self):
        calls, _ = self.run_eject(None)
        self.assertEqual(len(calls), 1)

    def test_a_folder_on_the_boot_volume_is_never_unmounted(self):
        calls, _ = self.run_eject({}, root="/Users/me/card")
        self.assertEqual(calls, [])

    def test_a_busy_card_says_why(self):
        _, out = self.run_eject({"Ejectable": True, "ParentWholeDisk": "disk4"}, unmount_code=1)
        self.assertIn("could not be unmounted", out)
        self.assertIn("diskutil unmountDisk disk4", out)

    def test_quiet_still_says_why_a_busy_card_stayed_mounted(self):
        with mock.patch.object(ui, "QUIET", True), contextlib.redirect_stderr(io.StringIO()) as err:
            self.run_eject({"Ejectable": True, "ParentWholeDisk": "disk4"}, unmount_code=1)
        self.assertIn("could not be unmounted", err.getvalue())
        self.assertIn("diskutil unmountDisk disk4", err.getvalue())

    def test_does_nothing_off_a_mac(self):
        calls, _ = self.run_eject({"Ejectable": True, "ParentWholeDisk": "disk4"}, platform="linux")
        self.assertEqual(calls, [])


class SyncFlowTest(unittest.TestCase):
    def run_sync(self, cards=None, yes=True, dry_run=False, plan=None, stale=(), extra=(),
                 manifest=MANIFEST, setup=(None, "esde"), files=(), colls=(), after=None, settings=None, prepare=None, args=()):
        updates = []
        with tempfile.TemporaryDirectory() as card_dir:
            card = self.card = os.path.basename(card_dir)
            argv = ["sync-roms", card_dir] + (["--yes"] if yes else []) + (["--dry-run"] if dry_run else []) + list(args)
            cards = {card: v for v in [cards or {}]} if cards is not None else {}
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: dict(settings or {})}),
                        (store, {"load_manifest": lambda names=(): manifest, "load_cards": lambda: cards,
                                 "save_card": lambda *a: None,
                                 "update_card": lambda name, **v: updates.append(v)}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}, "get_text": lambda key: ""}),
                        (cli.picker, {"saved_setup": lambda *a: setup}),
                        (cli.downloads, {"run_downloads": lambda *a: 0, "plan_downloads": lambda jobs, disc_dir=None: plan if plan is not None else jobs}),
                        (scrape_plan, {"stale_media": lambda *a: [os.path.join(card_dir, s) for s in stale]}),
                        (collections_mod, {"load_collections": lambda: list(colls)})):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                st.enter_context(mock.patch.object(cli.clean, "_eject_root", None))
                st.enter_context(mock.patch.object(ui, "confirm", lambda *a, **k: True))
                st.enter_context(mock.patch.object(scrape_plan, "SCRAPE_LAYOUTS", {"esde"}))
                st.enter_context(mock.patch.object(scrape_plan, "load_scrape_data", lambda systems: {}))
                st.enter_context(mock.patch.object(scrape_plan, "build_scrape_plan",
                                                   lambda layout, systems, data, rels, dest_of, es_dir, present, base, recheck=None:
                                                   {"jobs": [], "gamelists": {}, "writes": []}))
                st.enter_context(mock.patch.object(scrape_plan, "apply_scrape_plan", lambda *a: (0, False)))
                st.enter_context(mock.patch.object(cli.surprise, "run_surprise", lambda *a, **k: []))
                st.enter_context(mock.patch.object(cli.surprise, "fill_surprises", lambda *a, **k: []))
                st.enter_context(mock.patch.object(runtime, "_mirror_root", None))
                for target, name, value in extra:
                    st.enter_context(mock.patch.object(target, name, value))
                if prepare:
                    prepare(card_dir)
                for s in stale:
                    open(os.path.join(card_dir, s), "w").close()
                for rel in files:
                    os.makedirs(os.path.dirname(os.path.join(card_dir, rel)), exist_ok=True)
                    open(os.path.join(card_dir, rel), "w").close()
                code, out = captured(cli.sync)
                if after:
                    self.after = after(card_dir)
                root = cli.clean._clean_root
                self.ejected = cli.clean._eject_root
                left = [s for s in stale if os.path.exists(os.path.join(card_dir, s))]
        return code, out, updates, root, left

    def test_ignored_listed_game_is_not_reported_missing(self):
        jobs = []
        _, out, _, _, _ = self.run_sync(extra=[(ignore, "_keys", frozenset({"gba/Game.zip"})),
                                               (cli.downloads, "run_downloads", lambda todo, *a, **k: jobs.extend(todo) or 0)])
        self.assertNotIn("missing", out.lower())
        self.assertFalse([j for j in jobs if "Game.zip" in str(j[0])])

    def test_ignored_collection_game_is_left_out(self):
        self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], files=["ROMs/gba/Game.zip"],
                      extra=[(ignore, "_keys", frozenset({"gba/Game.zip"}))],
                      after=lambda d: os.path.exists(os.path.join(d, "ES-DE", "collections", "custom-Favs.cfg"))
                      and read_from(d, "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertNotIn("Game.zip", self.after or "")

    def test_header_shows_the_cache_age(self):
        tree = inventory.Tree("s3://b", inventory._clock() - 7200, {"gba/Game.zip": 5}, {})
        _, out, _, _, _ = self.run_sync(extra=[(inventory, "current", lambda: tree)])
        self.assertIn("cache updated 2 hours ago", out.splitlines()[0])

    def test_rom_missing_from_the_cache_points_at_cache_update(self):
        tree = inventory.Tree("s3://b", inventory._clock(), {"gba/Other.zip": 5}, {})
        _, out, _, _, _ = self.run_sync(extra=[(inventory, "current", lambda: tree)])
        self.assertIn("listed in manifest but not in storage", out)
        self.assertIn("sync-roms cache update", out)

    def test_rom_missing_without_a_cache_has_no_cache_pointer(self):
        _, out, _, _, _ = self.run_sync(extra=[(s3, "list_sizes", lambda prefix, sizes=True: {})])
        self.assertIn("listed in manifest but not in storage", out)
        self.assertNotIn("cache update", out)

    def test_nothing_downloaded_skips_card_cleaning(self):
        _, _, _, root, _ = self.run_sync(plan=[])
        self.assertIsNone(root)

    def scrape_sync(self, wrote):
        plan = {"jobs": [], "gamelists": {"/card/gamelist.xml": {}}, "writes": []}
        _, _, _, root, _ = self.run_sync(plan=[], extra=[
            (scrape_plan, "build_scrape_plan", lambda *a, **k: plan),
            (scrape_plan, "apply_scrape_plan", lambda *a: (0, wrote))])
        return root

    def test_a_scrape_that_wrote_nothing_skips_card_cleaning(self):
        self.assertIsNone(self.scrape_sync(False))

    def test_a_scrape_that_wrote_marks_the_card_for_cleaning(self):
        self.assertIsNotNone(self.scrape_sync(True))

    def test_download_marks_the_card_for_cleaning(self):
        _, _, _, root, _ = self.run_sync()
        self.assertIsNotNone(root)

    def install_steps(self, games, dry_run, args=(), result=0, staged=False):
        """A sync of a card with these games and nothing to download, its installer steps and the old-driver prune
        replaced by stubs that return result: (exit code, the steps as they were called, whether the card is marked for
        cleaning, output). PICO-8 says it wrote when it is given a list for that; spruceOS says so when staged."""
        calls = []

        def pico8_run(card, layout_name, base, dry_run, wrote=None):
            calls.append(("pico8", dry_run, wrote is not None))
            if wrote is not None:
                wrote.append("pico8")
            return result

        def spruce_install(card, layout_name, base, dry_run, wrote=None, keep=False):
            calls.append(("spruce", dry_run, keep))
            if staged:
                wrote.append("7z")
            return result

        def prune(card, drivers_dir, current, dry_run, keep=False):
            calls.append(("prune", dry_run, None if dry_run else keep))  # a dry run never reads keep
            return ["old.zip"]
        code, out, _, root, _ = self.run_sync(
            manifest={**MANIFEST, "systems": [{**MANIFEST["systems"][0], "games": games}]}, dry_run=dry_run, plan=[], args=args,
            extra=[(cli.pico8, "run", pico8_run), (cli.spruce_os, "install", spruce_install), (cli.drivers, "prune", prune),
                   (cli.onion_surprise, "install", lambda card, layout_name, base, dry_run, keep=False: calls.append(("surprise app", dry_run)) or result),
                   (cli.raofflineproxy, "install", lambda card, layout_name, base, dry_run: calls.append(("raofflineproxy", dry_run)) or result),
                   (cli.onion_surprise, "write_list", lambda card, layout_name, base, roms_dir, systems, dry_run: calls.append(("surprise list", dry_run))),
                   (cli.cardfs, "flush", lambda: calls.append("flush"))])
        self.assertEqual(calls.pop(), "flush")  # the one every sync ends with
        return code, calls, root is not None, out

    def test_a_card_with_nothing_to_sync_still_runs_the_installers(self):
        for dry_run in (False, True):
            for args, keep in (((), False), (("--no-delete",), True)):
                with self.subTest(dry_run=dry_run, keep=keep):
                    code, calls, marked, out = self.install_steps([], dry_run, args)
                    self.assertEqual(calls, [("pico8", dry_run, False), ("surprise app", dry_run), ("raofflineproxy", dry_run),
                                             ("surprise list", dry_run), ("spruce", dry_run, keep)])
                    self.assertEqual((code, marked), (0, False))  # PICO-8 isn't asked what it wrote: the card isn't marked
                    self.assertIn("has nothing to sync", out)
        self.assertEqual(self.install_steps([], False, result=1)[0], 1)

    def test_staging_spruceos_marks_the_card_for_cleaning(self):
        for args, marked in (((), True), (("--no-clean",), False)):
            with self.subTest(args=args):
                self.assertEqual(self.install_steps([], False, args, staged=True)[2], marked)

    def test_a_dry_run_runs_the_installers_dry_and_lists_the_old_drivers(self):
        for args, keep, line in (((), False, "would delete"), (("--no-delete",), True, "--no-delete: keeping 1 old driver(s)")):
            with self.subTest(keep=keep):
                code, calls, marked, out = self.install_steps(MANIFEST["systems"][0]["games"], True, args, result=1)
                self.assertEqual(calls, [("prune", True, None), ("pico8", True, False), ("surprise app", True), ("raofflineproxy", True),
                                         ("spruce", True, keep), ("surprise list", True)])
                self.assertEqual((code, marked), (0, False))
                self.assertEqual([x for x in out.split("\n") if "old.zip" in x or "old driver" in x][0].count(line), 1)
                self.assertEqual("would delete" in out, not keep)
                self.assertIn(os.path.join("Drivers", "old.zip"), out)

    def test_a_sync_prunes_the_old_drivers_runs_the_installers_and_stages_spruceos_last(self):
        for args, keep, line in (((), False, "🧹 Removed old driver old.zip"), (("--no-delete",), True, "--no-delete: keeping 1 old driver(s)")):
            with self.subTest(keep=keep):
                code, calls, marked, out = self.install_steps(MANIFEST["systems"][0]["games"], False, args)
                self.assertEqual(calls, [("prune", False, keep), ("pico8", False, True), ("surprise app", False), ("raofflineproxy", False),
                                         ("surprise list", False), "flush", ("spruce", False, keep)])
                self.assertEqual((code, marked), (0, True))  # PICO-8 wrote: the card is marked for cleaning
                self.assertIn(line, out)
                self.assertEqual("Removed old driver" in out, not keep)
        code, _, _, out = self.install_steps(MANIFEST["systems"][0]["games"], False, result=1)
        self.assertEqual(code, 1)
        self.assertIn("Done with 4 failure(s)", out)

    def test_stale_media_listed_before_removal(self):
        _, out, _, _, left = self.run_sync(stale=("a.png", "b.png"))
        self.assertIn("2 media file(s)", out)
        self.assertIn("a.png", out)
        self.assertLess(out.index("a.png"), out.index("Removed 2"))
        self.assertEqual(left, [])

    def test_every_system_with_games_syncs_and_no_selection_is_saved(self):
        code, _, updates, _, _ = self.run_sync(cards={"device": "full", "systems": []}, yes=False)
        self.assertEqual(code, 0)
        self.assertFalse([u for u in updates if "systems" in u])

    def test_esde_card_gets_its_collection_written_enabled_and_owned(self):
        _, _, updates, _, _ = self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], files=["ROMs/gba/Game.zip"],
                                               after=lambda d: (read_from(d, "ES-DE", "collections", "custom-Favs.cfg"),
                                                                read_from(d, "ES-DE", "settings", "es_settings.xml")))
        cfg, settings = self.after
        self.assertEqual(cfg, "%ROMPATH%/gba/Game.zip\n")
        self.assertIn('<string name="CollectionSystemsCustom" value="Favs" />', settings)
        self.assertIn({"frontend_collections": ["Favs"]}, updates)

    def test_esde_sync_keeps_the_favorites_in_the_cards_gamelist(self):
        gamelist = os.path.join("ES-DE", "gamelists", "gba", "gamelist.xml")

        def prepare(card_dir):
            os.makedirs(os.path.join(card_dir, os.path.dirname(gamelist)))
            with open(os.path.join(card_dir, gamelist), "w") as f:
                f.write('<?xml version="1.0"?>\n<gameList>\n'
                        '\t<game>\n\t\t<path>./Game.zip</path>\n\t\t<name>Game</name>\n\t\t<favorite>true</favorite>\n\t</game>\n'
                        '\t<game>\n\t\t<path>./Gone.zip</path>\n\t\t<favorite>true</favorite>\n\t</game>\n'
                        '</gameList>\n')
        self.run_sync(cards={}, files=["ROMs/gba/Game.zip"], prepare=prepare,
                      extra=[(scrape_plan, "load_scrape_data", lambda systems: SCRAPED),
                             (scrape_plan, "build_scrape_plan", REAL_BUILD_SCRAPE_PLAN),
                             (scrape_plan, "apply_scrape_plan", REAL_APPLY_SCRAPE_PLAN),
                             (scrape_plan, "stale_media", REAL_STALE_MEDIA)],
                      after=lambda d: read_from(d, gamelist))
        self.assertIn("<name>The Game</name>", self.after)  # the scrape did write the file
        self.assertEqual(self.after.count("<favorite>true</favorite>"), 2)
        self.assertIn("<path>./Gone.zip</path>", self.after)

    def test_knulli_card_writes_under_system_configs(self):
        manifest = {**MANIFEST, "systems": [{**MANIFEST["systems"][0], "folders": {"knulli": "gba"}}],
                    "layouts": {"knulli": {"label": "Knulli", "roms_dir": "roms", "bios_dir": "bios"}}}
        self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], manifest=manifest, setup=(None, "knulli"),
                      files=["roms/gba/Game.zip"],
                      after=lambda d: (read_from(d, "system", "configs", "emulationstation", "collections", "custom-Favs.cfg"),
                                       read_from(d, "system", "configs", "emulationstation", "es_settings.cfg")))
        cfg, settings = self.after
        self.assertEqual(cfg, "./roms/gba/Game.zip\n")
        self.assertIn("<config>", settings)

    def run_emudeck(self, appdata, rom_dir=lambda d: os.path.join(d, "Emulation", "roms") + "/", colls=True,
                    scrape=False, **kw):
        """A sync of an EmuDeck card, with FAVS when colls, ES-DE's data folder on this computer at appdata, its
        ROMDirectory rom_dir(card folder) (no settings file when rom_dir is None, no ROMDirectory when it returns None).
        With scrape, the card gets SCRAPED's media and gamelist; the downloads asked for go in self.fetched."""
        manifest = {**MANIFEST, "systems": [{**MANIFEST["systems"][0], "folders": {"emudeck": "gba"}}],
                    "layouts": {"emudeck": {"label": "EmuDeck", "roms_dir": "Emulation/roms", "bios_dir": "Emulation/bios"}}}
        self.fetched = []

        def prepare(card_dir):
            if rom_dir:
                used = rom_dir(card_dir)
                line = f'<string name="ROMDirectory" value="{used}" />\n' if used else ""
                os.makedirs(os.path.join(appdata, "settings"), exist_ok=True)
                with open(os.path.join(appdata, "settings", "es_settings.xml"), "w") as f:
                    f.write('<?xml version="1.0"?>\n' + line)
        scraping = [(scrape_plan, "SCRAPE_LAYOUTS", {"emudeck"}), (scrape_plan, "load_scrape_data", lambda systems: SCRAPED),
                    (scrape_plan, "build_scrape_plan", REAL_BUILD_SCRAPE_PLAN),
                    (scrape_plan, "apply_scrape_plan", REAL_APPLY_SCRAPE_PLAN),
                    (cli.downloads, "run_downloads", lambda todo, *a: self.fetched.extend(todo) or 0)] if scrape else []
        with mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": appdata}):
            return self.run_sync(cards={"collections": ["favs"]} if colls else {}, colls=[FAVS], manifest=manifest,
                                 setup=(None, "emudeck"), files=["Emulation/roms/gba/Game.zip"], prepare=prepare,
                                 extra=[(ui, "warn", self.warned.append)] + scraping, **kw)

    @staticmethod
    def skipped(reason):
        return (f"{reason}, so the card's gamelists and collections were skipped; "
                "sync on the Steam Machine or Steam Deck to get them")

    def test_emudeck_card_writes_its_collection_into_es_de_on_this_computer(self):
        self.warned = []
        with tempfile.TemporaryDirectory() as appdata:
            _, _, updates, root, _ = self.run_emudeck(appdata, plan=[], after=lambda d: os.listdir(d))
            self.assertEqual(read_from(appdata, "collections", "custom-Favs.cfg"), "%ROMPATH%/gba/Game.zip\n")
            self.assertIn('<string name="CollectionSystemsCustom" value="Favs" />',
                          read_from(appdata, "settings", "es_settings.xml"))
        self.assertEqual(self.after, ["Emulation"])
        self.assertIn({"frontend_collections": ["Favs"]}, updates)
        self.assertIsNone(root)  # nothing was written on the card
        self.assertFalse(self.warned)

    def test_emudeck_card_without_es_de_on_this_computer_warns_and_writes_nothing(self):
        for dry_run in (False, True):
            self.warned = []
            with tempfile.TemporaryDirectory() as tmp:
                appdata = os.path.join(tmp, "ES-DE")
                _, out, updates, _, _ = self.run_emudeck(appdata, rom_dir=None, dry_run=dry_run)
                self.assertFalse(os.path.exists(appdata))
            self.assertEqual(self.warned, [self.skipped(f"ES-DE isn't set up on this computer (no {appdata})")])
            self.assertNotIn("custom-Favs.cfg", out)
            self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_emudeck_card_with_an_es_de_using_other_roms_warns_and_writes_nothing(self):
        for rom_dir in (lambda d: "/elsewhere/roms", lambda d: None):
            for dry_run in (False, True):
                self.warned, cards = [], []
                with tempfile.TemporaryDirectory() as appdata:
                    _, out, updates, _, _ = self.run_emudeck(appdata, rom_dir=rom_dir, dry_run=dry_run,
                                                             after=lambda d: cards.append(d))
                    self.assertEqual(sorted(os.listdir(appdata)), ["settings"])
                    self.assertNotIn("CollectionSystemsCustom", read_from(appdata, "settings", "es_settings.xml"))
                roms = os.path.join(cards[0], "Emulation/roms")
                self.assertEqual(self.warned, [self.skipped(f"ES-DE on this computer ({appdata}) doesn't use this "
                                                            f"card's ROMs (its ROMDirectory isn't {roms})")])
                self.assertNotIn("custom-Favs.cfg", out)
                self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_emudeck_card_writes_its_gamelist_into_es_de_on_this_computer(self):
        self.warned = []
        with tempfile.TemporaryDirectory() as appdata:
            _, _, _, root, _ = self.run_emudeck(appdata, colls=False, scrape=True, plan=[])
            gamelist = read_from(appdata, "gamelists", "gba", "gamelist.xml")
        self.assertIn("<path>./Game.zip</path>", gamelist)
        self.assertIn("<name>The Game</name>", gamelist)
        self.assertIsNone(root)  # the gamelist isn't on the card
        self.assertFalse(self.warned)

    def test_emudeck_card_skips_its_gamelist_with_one_warning_when_es_de_does_not_serve_it(self):
        for colls in (False, True):
            for dry_run in (False, True):
                self.warned, cards = [], []
                with tempfile.TemporaryDirectory() as tmp:
                    appdata = os.path.join(tmp, "ES-DE")
                    self.run_emudeck(appdata, rom_dir=None, colls=colls, scrape=True, dry_run=dry_run)
                    self.assertFalse(os.path.exists(appdata))
                self.assertEqual(self.warned, [self.skipped(f"ES-DE isn't set up on this computer (no {appdata})")])
                with tempfile.TemporaryDirectory() as appdata:
                    _, out, _, _, _ = self.run_emudeck(appdata, rom_dir=lambda d: "/elsewhere/roms", colls=colls,
                                                       scrape=True, dry_run=dry_run, after=lambda d: cards.append(d))
                    self.assertEqual(os.listdir(appdata), ["settings"])
                roms = os.path.join(cards[0], "Emulation/roms")
                self.assertEqual(self.warned[1:], [self.skipped(f"ES-DE on this computer ({appdata}) doesn't use this "
                                                                f"card's ROMs (its ROMDirectory isn't {roms})")])
                if dry_run:
                    self.assertIn("0 gamelist file(s) to update", out)
                else:  # the media still goes on the card
                    self.assertIn(os.path.join(cards[0], "Emulation", "tools", "downloaded_media", "gba", "covers", "Game.png"),
                                  [p for _, p, _ in self.fetched])

    def test_emudeck_card_with_nothing_to_skip_does_not_warn(self):
        self.warned = []
        with tempfile.TemporaryDirectory() as tmp:
            self.run_emudeck(os.path.join(tmp, "ES-DE"), rom_dir=None, colls=False)
        self.assertFalse(self.warned)

    def test_dry_run_describes_and_writes_nothing(self):
        _, out, updates, _, _ = self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], dry_run=True,
                                                 after=lambda d: os.path.exists(os.path.join(d, "ES-DE", "collections")))
        self.assertIn("custom-Favs.cfg", out)
        self.assertFalse(self.after)
        self.assertFalse([u for u in updates if "frontend_collections" in u])

    def put_favs(self, card_dir):
        """The card as a first sync with FAVS left it: its collection written and enabled."""
        plan = frontend.plan_collections("esde", card_dir, {"Favs": ["%ROMPATH%/gba/Game.zip"]}, [])
        frontend.apply_collections(plan, "esde", card_dir)

    def test_an_unreadable_spruce_collections_file_keeps_the_collection_art(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        manifest = {**MANIFEST, "layouts": layouts, "systems": [{**MANIFEST["systems"][0], "folders": {"spruce": "GBA"}}]}
        pictures = [os.path.join("Collections", d, "Favs.png") for d in ("Imgs", "Imgs_med", "Imgs_small")]

        def prepare(card_dir):
            for rel in pictures:
                os.makedirs(os.path.join(card_dir, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(card_dir, rel), "wb") as f:
                    f.write(b"x")
            with open(os.path.join(card_dir, "Collections", "collections.json"), "w") as f:
                f.write("not json")

        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), contextlib.redirect_stderr(io.StringIO()) as err:
                _, out, _, _, _ = self.run_sync(cards={"collections": ["favs"], "frontend_collections": ["Favs"]}, colls=[FAVS],
                                                manifest=manifest, setup=(None, "spruce"), dry_run=dry_run, prepare=prepare,
                                                after=lambda d: [os.path.exists(os.path.join(d, rel)) for rel in pictures])
                self.assertEqual(self.after, [True] * 3)
                self.assertNotIn("would remove the art", out)
                if not dry_run:
                    self.assertIn("can't be read", err.getvalue())

    def test_a_second_identical_sync_writes_no_collection_and_skips_card_cleaning(self):
        _, out, updates, root, _ = self.run_sync(cards={"collections": ["favs"], "frontend_collections": ["Favs"]},
                                                 colls=[FAVS], files=["ROMs/gba/Game.zip"], plan=[], prepare=self.put_favs)
        self.assertNotIn("collection(s)", out)
        self.assertIsNone(root)
        self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_a_collection_edited_on_the_card_is_written_again_and_cleaned(self):
        def prepare(card_dir):
            self.put_favs(card_dir)
            with open(frontend.collection_path("esde", card_dir, "Favs"), "w") as f:
                f.write("edited\n")
        _, out, _, root, _ = self.run_sync(cards={"collections": ["favs"], "frontend_collections": ["Favs"]},
                                           colls=[FAVS], files=["ROMs/gba/Game.zip"], plan=[], prepare=prepare,
                                           after=lambda d: read_from(d, "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertIn("Wrote 1 collection(s)", out)
        self.assertEqual(self.after, "%ROMPATH%/gba/Game.zip\n")
        self.assertIsNotNone(root)

    def test_a_collection_unlisted_in_settings_by_hand_is_listed_again_and_cleaned(self):
        def prepare(card_dir):
            self.put_favs(card_dir)
            os.remove(frontend.settings_path("esde", card_dir))
        _, out, _, root, _ = self.run_sync(cards={"collections": ["favs"], "frontend_collections": ["Favs"]},
                                           colls=[FAVS], files=["ROMs/gba/Game.zip"], plan=[], prepare=prepare,
                                           after=lambda d: read_from(d, "ES-DE", "settings", "es_settings.xml"))
        self.assertNotIn("collection(s)", out)
        self.assertIn('value="Favs"', self.after)
        self.assertIsNotNone(root)

    def test_dry_run_does_not_say_an_unchanged_collection_would_be_written(self):
        _, out, _, _, _ = self.run_sync(cards={"collections": ["favs"], "frontend_collections": ["Favs"]}, colls=[FAVS],
                                        files=["ROMs/gba/Game.zip"], dry_run=True, prepare=self.put_favs)
        self.assertNotIn("would write custom-Favs.cfg", out)

    def test_a_collection_game_on_a_system_the_device_cant_play_is_ignored(self):
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx"}, "bios": {"files": []},
               "games": [{"bucket": "psx/FF7.chd"}]}
        device = {"id": "d", "name": "D", "note": "", "systems": ["gba"]}
        favs = {**FAVS, "games": [GAME, {"title": "FF7", "system": "psx", "bucket": "psx/FF7.chd"}]}
        self.run_sync(cards={"collections": ["favs"]}, colls=[favs], manifest={**MANIFEST, "systems": MANIFEST["systems"] + [psx]},
                      setup=(device, "esde"), files=["ROMs/gba/Game.zip", "ROMs/psx/FF7.chd"],
                      after=lambda d: read_from(d, "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertEqual(self.after, "%ROMPATH%/gba/Game.zip\n")

    def test_malformed_collection_games_are_skipped_at_the_end_of_the_sync(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        os.makedirs(os.path.join(data.name, "collections"))
        store.write_json(os.path.join(data.name, "collections", "favs.json"),
                         {"name": "Favs", "games": [GAME, "gba/Loose.zip", {"bucket": "gba/Other.zip"}, {"system": "gba"}]})
        with contextlib.redirect_stderr(io.StringIO()):
            code, *_ = self.run_sync(cards={"collections": ["favs"]}, files=["ROMs/gba/Game.zip"], extra=(
                (store, "data_dir", lambda: data.name), (collections_mod, "load_collections", REAL_LOAD_COLLECTIONS)),
                after=lambda d: read_from(d, "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertEqual(code, 0)
        self.assertEqual(self.after, "%ROMPATH%/gba/Game.zip\n")

    def run_with_user_files(self, cards, **kw):
        """A sync of the card entry cards with the user's own custom-F.cfg, custom-a.cfg and custom-Favs.cfg on it;
        returns (exit code, which of them are left). kw: more of run_sync's arguments."""
        names = ("F", "a", "Favs")

        def prepare(card_dir):
            for name in names:
                path = frontend.collection_path("esde", card_dir, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
        code, *_ = self.run_sync(cards=cards, prepare=prepare, colls=[FAVS], after=lambda d: [
            n for n in names if os.path.exists(frontend.collection_path("esde", d, n))], **kw)
        return code, self.after

    def test_malformed_card_collection_fields_delete_nothing(self):
        for cards in ({"frontend_collections": None}, {"frontend_collections": "Favs"}, {"collections": None},
                      {"collections": "favs", "frontend_collections": [None, 5, ""]}):
            with self.subTest(cards=cards), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.run_with_user_files(cards), (0, ["F", "a", "Favs"]))

    def test_missing_or_malformed_card_entry_writes_and_deletes_no_collections(self):
        for entry in (None, [], "", 0):  # no entry in cards.json, or one that isn't an object
            cards = type("AnyCard", (dict,), {"get": lambda self, k, d=None: entry})()
            for dry_run in (False, True):
                with self.subTest(entry=entry, dry_run=dry_run):
                    self.assertEqual(self.run_with_user_files(None, dry_run=dry_run, extra=[(store, "load_cards", lambda: cards)]),
                                     (0, ["F", "a", "Favs"]))

    def dry_run_with_cards_file(self, entry):
        """A dry run of a card whose entry in a real cards.json is entry (None: it has none), with the real saved_setup,
        save_card and update_card, so only --dry-run keeps the card from being saved.
        Returns (exit code, what it printed with the card's name as CARD, the card's entry in cards.json afterwards)."""
        data = self.enterContext(tempfile.TemporaryDirectory())

        def prepare(card_dir):
            store.write_json(os.path.join(data, "cards.json"), {} if entry is None else {os.path.basename(card_dir): entry})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out, *_ = self.run_sync(dry_run=True, prepare=prepare, extra=(
                (store, "data_dir", lambda: data), (store, "load_cards", REAL_LOAD_CARDS),
                (store, "save_card", REAL_SAVE_CARD), (store, "update_card", REAL_UPDATE_CARD),
                (cli.picker, "saved_setup", REAL_SAVED_SETUP), (cli.picker, "choose_setup", lambda manifest: (None, "esde")),
                (cli, "free_space", lambda path: 10**9)))
        with mock.patch.object(store, "data_dir", lambda: data):
            after = store.load_cards().get(self.card)
        return code, (out + err.getvalue()).replace(self.card, "CARD"), after

    def test_dry_run_of_a_card_whose_entry_is_not_an_object_runs_like_one_with_no_entry(self):
        code, expected, after = self.dry_run_with_cards_file(None)
        self.assertEqual((code, after), (0, None))
        self.assertIn("Dry run", expected)
        self.assertNotIn("Saved setup", expected)  # no entry is not a saved setup to warn about
        for entry in (["junk"], "x", 5):
            with self.subTest(entry=entry):
                self.assertEqual(self.dry_run_with_cards_file(entry), (0, expected, entry))

    def surprise_calls(self, result=(), **kw):
        calls = []
        fake = lambda card, setup, chosen, interactive, dry_run, **k: calls.append((interactive, dry_run, [s["bucket"] for s in chosen])) or list(result)  # noqa: E731
        return calls, self.run_sync(extra=((cli.surprise, "run_surprise", fake),), **kw)

    def test_yes_runs_surprise_unattended(self):
        calls, _ = self.surprise_calls(yes=True)
        self.assertEqual(calls, [(False, False, ["gba"])])

    def test_dry_run_describes_the_saved_surprises_and_saves_nothing(self):
        saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
        calls, (code, out, updates, *_) = self.surprise_calls(result=saved, cards={"surprises": saved}, yes=True, dry_run=True)
        self.assertEqual(calls, [(False, True, ["gba"])])
        self.assertEqual(code, 0)
        self.assertIn("custom-Surprise.cfg (1 game(s))", out)
        self.assertFalse([u for u in updates if "surprises" in u or "frontend_collections" in u])

    def test_terminal_run_is_interactive(self):
        with mock.patch.object(ui, "has_terminal", return_value=True):
            calls, _ = self.surprise_calls(yes=False)
        self.assertEqual(calls[0][:2], (True, False))

    def test_over_capacity_warns_and_goes_on(self):
        big = budget.Usage(2 * 10 ** 9, 1, False)
        warned = []
        code, *_ = self.run_sync(cards={"size": "1 GB"}, extra=(
            (cli.surprise, "run_surprise", lambda *a, **k: []), (cli.budget, "card_usage", lambda *a, **k: big),
            (ui, "warn", warned.append)))
        self.assertEqual(code, 0)
        self.assertIn(f"{self.card}'s picks take 2 GB of its 1 GB: 1 GB over", warned)

    def mirror_root(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        open(os.path.join(tmp, runtime.MIRROR_MARKER), "w").close()
        return tmp

    def run_editing(self, old, new, keys, **kw):
        """A sync whose Surprise step (or the editor it opens) changes the gba system from `old` to `new`;
        storage's gba/ holds `keys`. Returns (code, the ROM keys downloaded, the mirror refreshes)."""
        manifest = {**MANIFEST, "systems": [{**MANIFEST["systems"][0], **old}]}
        got, seen = [], []

        def step(*a, **k):
            manifest["systems"] = [{**MANIFEST["systems"][0], **new}]
            return []
        code, *_ = self.run_sync(manifest=manifest, extra=(
            (cli.surprise, "run_surprise", step),
            (s3, "list_sizes", lambda prefix, sizes=True: {k: 5 for k in keys} if prefix == "gba/" else {}),
            (s3, "stat_sizes", lambda wanted: {k: 5 for k in wanted if k in keys}),
            (cli.downloads, "run_downloads", lambda todo, *a: got.extend(k for k, _, _ in todo) or 0),
            (mirroring, "refresh_mirror", lambda r, dry_run=False: seen.append((r, runtime._mirror_root)) or 0)) + kw.pop("extra", ()), **kw)
        return code, got, seen

    def test_mirror_is_refreshed_again_when_the_step_changes_the_picks(self):
        root = self.mirror_root()
        code, _, seen = self.run_editing({}, {"games": [{"bucket": "gba/New.zip"}]}, ["gba/Game.zip", "gba/New.zip"],
                                         settings={"mirror": root})
        self.assertEqual(code, 0)
        self.assertEqual(seen, [(root, None), (root, None)])  # use_mirror, then after the step: both read storage

    def test_mirror_is_not_refreshed_again_when_the_picks_are_unchanged(self):
        root = self.mirror_root()
        code, _, seen = self.run_editing({}, {}, ["gba/Game.zip"], settings={"mirror": root})
        self.assertEqual(code, 0)
        self.assertEqual(seen, [(root, None)])

    def test_games_the_step_adds_are_downloaded_and_the_ones_it_drops_are_removed(self):
        code, got, _ = self.run_editing({"games": [{"bucket": "gba/Game.zip"}, {"bucket": "gba/Old.zip"}]},
                                        {"games": [{"bucket": "gba/Game.zip"}, {"bucket": "gba/New.zip"}]},
                                        ["gba/Game.zip", "gba/Old.zip", "gba/New.zip"], yes=False,
                                        files=["ROMs/gba/Old.zip"], extra=((ui, "choose", lambda *a, **k: "y"),),
                                        after=lambda d: os.path.exists(os.path.join(d, "ROMs", "gba", "Old.zip")))
        self.assertEqual(code, 0)
        self.assertIn("gba/New.zip", got)
        self.assertNotIn("gba/Old.zip", got)
        self.assertFalse(self.after)

    def test_switching_to_full_system_in_the_step_lists_the_whole_folder(self):
        root = self.mirror_root()  # reading from a folder, a game list only stats its own games
        code, got, _ = self.run_editing({}, {"full_system": True}, ["gba/Game.zip", "gba/Other.zip"], settings={"mirror": root})
        self.assertEqual(code, 0)
        self.assertEqual(sorted(got), ["gba/Game.zip", "gba/Other.zip"])

    def test_surprise_collection_comes_from_the_saved_card_after_the_editor(self):
        saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
        self.run_sync(cards={"surprises": saved}, files=["ROMs/gba/Game.zip"],
                      extra=((cli.surprise, "run_surprise", lambda *a, **k: []),),  # what the step returned before the editor
                      after=lambda d: read_from(d, "ES-DE", "collections", "custom-Surprise.cfg"))
        self.assertEqual(self.after, "%ROMPATH%/gba/Game.zip\n")

    def test_surprise_and_collections_with_art_get_theme_art(self):
        saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
        favs = {**FAVS, "art": "rpg"}
        installed, described = [], []
        art = ((cli.themeart, "install", lambda layout, base, arts: installed.append((layout, arts)) or True),
               (cli.themeart, "describe", lambda layout, base, arts: described.append((layout, arts))))
        want = [("esde", {"Favs": "rpg", "Surprise": "surprise"})]
        self.run_sync(cards={"surprises": saved, "collections": ["favs"]}, colls=[favs], files=["ROMs/gba/Game.zip"],
                      plan=[], extra=art)
        self.assertEqual(installed, want)
        self.run_sync(cards={"surprises": saved, "collections": ["favs"]}, colls=[favs], files=["ROMs/gba/Game.zip"],
                      dry_run=True, extra=art)
        self.assertEqual((installed, described), (want, want))

    def test_theme_off_installs_no_theme_art_but_still_writes_the_collections(self):
        saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
        installed = []
        art = ((cli.themeart, "install", lambda *a: installed.append(a)),)
        self.run_sync(cards={"surprises": saved, "collections": ["favs"], "theme": False}, colls=[{**FAVS, "art": "rpg"}],
                      files=["ROMs/gba/Game.zip"], plan=[], extra=art,
                      after=lambda d: (read_from(d, "ES-DE", "collections", "custom-Favs.cfg"),
                                       read_from(d, "ES-DE", "collections", "custom-Surprise.cfg")))
        self.assertEqual(installed, [])
        self.assertEqual(self.after, ("%ROMPATH%/gba/Game.zip\n", "%ROMPATH%/gba/Game.zip\n"))

    def test_collections_off_writes_no_collection_files_and_no_art(self):
        saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
        installed = []
        art = ((cli.themeart, "install", lambda *a: installed.append(a)),)
        _, _, updates, _, _ = self.run_sync(
            cards={"surprises": saved, "collections": ["favs"], "custom_collections": False},
            colls=[{**FAVS, "art": "rpg"}], files=["ROMs/gba/Game.zip"], plan=[], extra=art,
            after=lambda d: (read_from(d, "ES-DE", "collections", "custom-Favs.cfg"),
                             read_from(d, "ES-DE", "collections", "custom-Surprise.cfg")))
        self.assertEqual(installed, [])
        self.assertEqual(self.after, (None, None))
        self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_a_collection_with_art_but_no_games_on_the_card_gets_none(self):
        installed = []
        self.run_sync(cards={"collections": ["favs"], "surprise": False}, colls=[{**FAVS, "art": "rpg"}],
                      extra=((cli.themeart, "install", lambda layout, base, arts: installed.append(arts)),))
        self.assertEqual(installed, [{}])  # still run: it removes the art sync-roms wrote before

    def test_collections_without_art_get_none(self):
        installed = []
        self.run_sync(cards={"collections": ["favs"], "surprise": False}, colls=[FAVS], files=["ROMs/gba/Game.zip"],
                      extra=((cli.themeart, "install", lambda layout, base, arts: installed.append(arts)),))
        self.assertEqual(installed, [{}])

    def test_the_last_collection_s_theme_art_is_removed_with_it(self):
        def prepare(card_dir):
            self.copy = os.path.join(card_dir, "ES-DE", "themes", cli.themeart.ESDE_COPY)
            for rel in (cli.themeart.ESDE_OWNED, os.path.join("favs", "theme.xml"), os.path.join("snes", "theme.xml")):
                os.makedirs(os.path.dirname(os.path.join(self.copy, rel)), exist_ok=True)
                with open(os.path.join(self.copy, rel), "w") as f:
                    f.write("favs\n")
        code, *_ = self.run_sync(cards={"collections": [], "surprise": False, "frontend_collections": ["Favs"]}, prepare=prepare,
                                 after=lambda d: sorted(os.listdir(self.copy)))
        self.assertEqual(code, 0)
        self.assertEqual(self.after, sorted([cli.themeart.ESDE_OWNED, "snes"]))

    def test_a_dry_run_names_the_theme_art_that_would_be_removed(self):
        def prepare(card_dir):
            self.copy = os.path.join(card_dir, "ES-DE", "themes", cli.themeart.ESDE_COPY)
            for rel in (cli.themeart.ESDE_OWNED, os.path.join("favs", "theme.xml")):
                os.makedirs(os.path.dirname(os.path.join(self.copy, rel)), exist_ok=True)
                with open(os.path.join(self.copy, rel), "w") as f:
                    f.write("favs\n")
        for cards, said in (({}, True), ({"theme": False}, False)):
            _, out, *_ = self.run_sync(cards={"collections": [], "surprise": False, "frontend_collections": ["Favs"], **cards},
                                       prepare=prepare, dry_run=True, after=lambda d: sorted(os.listdir(self.copy)))
            self.assertEqual("would remove the art for favs" in out, said, cards)
            self.assertEqual(self.after, sorted([cli.themeart.ESDE_OWNED, "favs"]))

    def test_theme_off_leaves_the_theme_art_alone(self):
        def prepare(card_dir):
            self.copy = os.path.join(card_dir, "ES-DE", "themes", cli.themeart.ESDE_COPY)
            for rel in (cli.themeart.ESDE_OWNED, os.path.join("favs", "theme.xml")):
                os.makedirs(os.path.dirname(os.path.join(self.copy, rel)), exist_ok=True)
                with open(os.path.join(self.copy, rel), "w") as f:
                    f.write("favs\n")
        self.run_sync(cards={"collections": [], "surprise": False, "frontend_collections": ["Favs"], "theme": False},
                      prepare=prepare, after=lambda d: sorted(os.listdir(self.copy)))
        self.assertEqual(self.after, sorted([cli.themeart.ESDE_OWNED, "favs"]))

    def test_surprise_off_removes_its_collection_file(self):
        def prepare(card_dir):
            self.cfg = frontend.collection_path("esde", card_dir, "Surprise")
            os.makedirs(os.path.dirname(self.cfg), exist_ok=True)
            open(self.cfg, "w").close()
        code, _, updates, *_ = self.run_sync(cards={"surprise": False, "frontend_collections": ["Surprise"]}, prepare=prepare)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.cfg))
        last = [u for u in updates if "frontend_collections" in u][-1]
        self.assertNotIn("Surprise", last["frontend_collections"])

    def test_a_finished_run_ejects_the_card(self):
        self.run_sync(files=["ROMs/gba/Game.zip"])
        self.assertTrue(self.ejected)

    def test_no_eject_flag_or_setting_keeps_the_card_mounted(self):
        for kw in ({"args": ["--no-eject"]}, {"settings": {"eject": False}}, {"dry_run": True}):
            self.run_sync(files=["ROMs/gba/Game.zip"], **kw)
            self.assertIsNone(self.ejected, kw)

    def test_a_run_with_failures_keeps_the_card_mounted(self):
        self.run_sync(extra=[(cli.downloads, "run_downloads", lambda todo, *a, **k: len(todo))])
        self.assertIsNone(self.ejected)

    def test_quiet_still_reports_failures_on_stderr(self):
        def run_downloads(todo, label, icon, base, failures, *a):
            failures.extend((j[0], "boom") for j in todo)
            return len(todo)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code, out, *_ = self.run_sync(args=["--quiet"], extra=[(cli.downloads, "run_downloads", run_downloads)])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("1 file(s) failed", err.getvalue())
        self.assertIn("gba/Game.zip: boom", err.getvalue())
        self.assertIn("Done with 1 failure(s)", err.getvalue())

    def test_quiet_shows_each_failed_download(self):
        def download(job, *a):
            raise OSError("boom")
        with mock.patch.object(s3, "download", download), mock.patch.object(ui, "QUIET", True), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            failed, out = captured(downloads.run_downloads, [("gba/a.zip", "/tmp/x/a.zip", 5)], "ROMs", "i", "/tmp/x")
        self.assertEqual(failed, 1)
        self.assertIn("gba/a.zip", err.getvalue())
        self.assertNotIn("boom", out)

    def run_muos_sync(self, cards, dry_run=False):
        manifest = {**MANIFEST, "systems": [{**MANIFEST["systems"][0], "folders": {"muos": "GBA"}}],
                    "layouts": {"muos": {"label": "muOS", "roms_dir": "ROMS", "bios_dir": "MUOS/bios",
                                         "pickles": {"dir": "MUOS/pickles"}}}}
        warned = []

        def tree(card_dir):
            found = {}
            for folder, _, names in os.walk(os.path.join(card_dir, "MUOS")):
                for name in names:
                    path = os.path.join(folder, name)
                    found[os.path.relpath(path, card_dir)] = read_from(path)
            return found
        result = self.run_sync(cards=cards, colls=[FAVS], manifest=manifest, setup=(None, "muos"), dry_run=dry_run,
                               files=["ROMS/GBA/Game.zip"], after=tree, extra=[(ui, "warn", warned.append)])
        return result, warned

    def test_muos_sync_writes_collection_entries(self):
        (_, out, updates, _, _), warned = self.run_muos_sync({"collections": ["favs"]})
        entries = [p for p in self.after if p.startswith("MUOS/info/collection/Favs/")]
        self.assertEqual(len(entries), 1)
        self.assertRegex(entries[0], r"/Game-[0-9A-F]{8}\.cfg$")
        self.assertEqual(self.after[entries[0]], "/mnt/mmc/ROMS/GBA/Game.zip\nGBA\nGame")
        self.assertIn({"frontend_collections": ["Favs"]}, updates)
        self.assertIn("Wrote 1 collection(s) for muOS", out)
        self.assertEqual(warned, [])

    def test_muos_unknown_storage_warns_and_writes_nothing(self):
        (_, _, updates, _, _), warned = self.run_muos_sync({"collections": ["favs"], "muos_storage": "usb"})
        self.assertTrue(warned)
        self.assertEqual([p for p in self.after if p.startswith("MUOS/info/collection/")], [])
        self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_muos_dry_run_writes_nothing(self):
        (_, _, updates, _, _), _ = self.run_muos_sync({"collections": ["favs"]}, dry_run=True)
        self.assertEqual([p for p in self.after if p.startswith("MUOS/info/collection/")], [])
        self.assertFalse([u for u in updates if "frontend_collections" in u])


if __name__ == "__main__":
    unittest.main()
