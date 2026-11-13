import contextlib
import io
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
    def run_clean(self, dot_clean, tty=False, yes=True, spotlight=True):
        calls = []
        with tempfile.TemporaryDirectory() as root, contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(clean, "_clean_root", root))
            st.enter_context(mock.patch.object(clean.shutil, "which", lambda n: "/usr/bin/dot_clean"))
            st.enter_context(mock.patch.object(clean, "dot_clean", dot_clean))
            st.enter_context(mock.patch.object(clean, "spotlight_active", lambda p: spotlight))
            st.enter_context(mock.patch.object(clean.time, "sleep", lambda s: None))
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

    def test_retries_dot_clean(self):
        results = iter([(True, ["/x/._a"]), (True, [])])
        _, out = self.run_clean(lambda p: next(results))
        self.assertIn("Retrying dot_clean", out)

    def test_sudo_is_skipped_when_spotlight_is_off(self):
        calls, out = self.run_clean(lambda p: (True, []), tty=True, yes=False, spotlight=False)
        self.assertFalse([c for c in calls if c[0] == "sudo"])
        self.assertNotIn("sudo mdutil", out)

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

        def download(job, cb, wrote=None):
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
            st.enter_context(mock.patch.object(ui, "POLL", 0.001))
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
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: setup}),
                        (cli.downloads, {"run_downloads": lambda *a: 0, "plan_downloads": lambda jobs, unzip=False, disc_dir=None: plan if plan is not None else jobs}),
                        (cli.clean, {"clean_android_media": lambda *a: None}),
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
                                                   lambda layout, systems, data, rels, dest_of, es_dir, present, base:
                                                   {"jobs": [], "gamelists": {}, "writes": []}))
                st.enter_context(mock.patch.object(scrape_plan, "apply_scrape_plan", lambda *a: 0))
                st.enter_context(mock.patch.object(cli.surprise, "run_surprise", lambda *a, **k: []))
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

    def test_download_marks_the_card_for_cleaning(self):
        _, _, _, root, _ = self.run_sync()
        self.assertIsNotNone(root)

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

    def test_dry_run_describes_and_writes_nothing(self):
        _, out, updates, _, _ = self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], dry_run=True,
                                                 after=lambda d: os.path.exists(os.path.join(d, "ES-DE", "collections")))
        self.assertIn("custom-Favs.cfg", out)
        self.assertFalse(self.after)
        self.assertFalse([u for u in updates if "frontend_collections" in u])

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

    def run_with_user_files(self, cards):
        """A sync of the card entry cards with the user's own custom-F.cfg, custom-a.cfg and custom-Favs.cfg on it;
        returns (exit code, which of them are left)."""
        names = ("F", "a", "Favs")

        def prepare(card_dir):
            for name in names:
                path = frontend.collection_path("esde", card_dir, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
        code, *_ = self.run_sync(cards=cards, prepare=prepare, colls=[FAVS], after=lambda d: [
            n for n in names if os.path.exists(frontend.collection_path("esde", d, n))])
        return code, self.after

    def test_malformed_card_collection_fields_delete_nothing(self):
        for cards in ({"frontend_collections": None}, {"frontend_collections": "Favs"}, {"collections": None},
                      {"collections": "favs", "frontend_collections": [None, 5, ""]}):
            with self.subTest(cards=cards), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.run_with_user_files(cards), (0, ["F", "a", "Favs"]))

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
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        open(os.path.join(tmp.name, runtime.MIRROR_MARKER), "w").close()
        return tmp.name

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

    def test_a_collection_with_art_but_no_games_on_the_card_gets_none(self):
        installed = []
        self.run_sync(cards={"collections": ["favs"], "surprise": False}, colls=[{**FAVS, "art": "rpg"}],
                      extra=((cli.themeart, "install", lambda *a: installed.append(a)),))
        self.assertEqual(installed, [])

    def test_collections_without_art_get_none(self):
        installed = []
        self.run_sync(cards={"collections": ["favs"], "surprise": False}, colls=[FAVS], files=["ROMs/gba/Game.zip"],
                      extra=((cli.themeart, "install", lambda *a: installed.append(a)),))
        self.assertEqual(installed, [])

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


if __name__ == "__main__":
    unittest.main()
