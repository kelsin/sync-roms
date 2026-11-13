import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, downloads, s3, scrape_plan, store, usersettings  # noqa: E402

SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []},
          "games": [{"bucket": "gba/Game.zip"}]}
MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}


def list_sizes(prefix, sizes=True):
    return {"gba/Game.zip": 5} if prefix == "gba/" else {}


class SyncSmokeTest(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(store, "data_dir", lambda: tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def run_sync(self, dry_run, prepare=None, patches=(), yes=True, args=()):
        """The exit code; what went to stderr is in self.err."""
        with tempfile.TemporaryDirectory() as card:
            if prepare:
                prepare(card)
            argv = ["sync-roms", card] + (["--yes"] if yes else []) + (["--dry-run"] if dry_run else []) + list(args)
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: {}}),
                        (store, {"load_manifest": lambda names=(): MANIFEST, "load_cards": lambda: {}, "save_card": lambda *a: None}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: (None, "esde")}),
                        (cli.downloads, {"run_downloads": lambda *a: 0}),
                        (cli.clean, {"clean_android_media": lambda *a: None, "eject": lambda: None}),
                        (cli.surprise, {"run_surprise": lambda *a, **k: []})) + tuple(patches):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                self.out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
                self.err = st.enter_context(contextlib.redirect_stderr(io.StringIO()))
                try:
                    return cli.sync()
                except SystemExit as e:
                    return e.code

    def test_dry_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(True), 0)

    def test_real_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(False), 0)

    def test_every_system_with_games_is_synced_and_the_editor_gets_what_is_not_on_the_card(self):
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}
        calls = []

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Game.zip"), "wb") as f:
                f.write(b"x" * 5)

        def run_surprise(card, setup, chosen, interactive, dry_run, to_fetch=None):
            calls.append(([s["bucket"] for s in chosen], to_fetch(SYSTEM, ["gba/Game.zip", "gba/New.zip"])))
            return []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.surprise, {"run_surprise": run_surprise}),
                   (cli.inventory, {"cached": lambda prefix: {"gba/Game.zip": 5, "gba/New.zip": 7}}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(calls, [(["gba"], {"gba/New.zip"})])

    def test_card_with_no_picks_syncs_no_games_and_says_so(self):
        empty = {**SYSTEM, "games": []}
        manifest = {**MANIFEST, "systems": [empty]}
        lines = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.ui, {"dim": lambda text: lines.append(text) or text}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)
        self.assertEqual(sum("has no games picked" in x for x in lines), 1)
        lines.clear()
        self.assertEqual(self.run_sync(False, patches=((cli.ui, {"dim": lambda text: lines.append(text) or text}),)), 0)
        self.assertFalse(any("no games picked" in x for x in lines))

    def old_rom(self, size):
        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Old.zip"), "wb") as f:
                f.write(b"x" * size)
        return prepare

    def test_unwanted_roms_are_deleted_before_the_space_check(self):
        asked, old = [], []

        def prepare(card):
            self.old_rom(100)(card)
            old.append(os.path.join(card, "ROMs", "gba", "Old.zip"))

        patches = ((cli, {"free_space": lambda path: 1000 if old and not os.path.exists(old[0]) else 3}),
                   (cli.ui, {"confirm": lambda q, default=True: asked.append(q) or True,
                             "choose": lambda *a, **k: "y"}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertFalse(os.path.exists(old[0]))
        self.assertFalse(any("Try anyway" in q for q in asked), asked)

    def test_roms_of_systems_with_nothing_to_sync_are_extras(self):
        """A system with no games listed keeps no ROMs on the card."""
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}

        def prepare(card):
            for rel in ("gba/Game.zip", "vectrex/Old.zip"):
                os.makedirs(os.path.join(card, "ROMs", os.path.dirname(rel)), exist_ok=True)
                open(os.path.join(card, "ROMs", rel), "w").close()
        asked = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
        self.run_sync(False, prepare=prepare, patches=patches)
        self.assertEqual([q for q in asked if q.startswith("Delete these")], ["Delete these 1 local file(s) (0 B)?"])

    def test_bios_of_unchosen_systems_with_roms_on_the_card_is_synced(self):
        """BIOS is added for a system whose ROMs are on the card even when this sync doesn't pick it."""
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx"}, "bios": {"files": ["scph1001.bin"]}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, psx]}

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "psx"), exist_ok=True)
            open(os.path.join(card, "ROMs", "psx", "Old.cue"), "w").close()
        bios = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, *a: (bios.extend(todo) if label == "BIOS" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"BIOS/scph1001.bin": 5} if prefix == "BIOS/" else list_sizes(prefix)}),
                   (cli.ui, {"choose": lambda q, *a, **k: "n"}))
        self.run_sync(False, prepare=prepare, patches=patches)
        self.assertEqual([j[0] for j in bios], ["BIOS/scph1001.bin"])

    def test_rom_files_go_in_the_rom_folder_and_are_not_extras(self):
        """A system's rom_files come from BIOS/ into its ROM folder; one already there isn't offered for deletion."""
        gamate = {"name": "Gamate", "bucket": "gamate", "folders": {"esde": "gamate"},
                  "bios": {"files": [], "rom_files": ["gamate.zip"]}, "games": [{"bucket": "gamate/Game.zip"}]}
        manifest = {**MANIFEST, "systems": [gamate]}

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gamate"))
            open(os.path.join(card, "ROMs", "gamate", "gamate.zip"), "w").close()
        bios, asked = [], []
        listing = {"gamate/": {"gamate/Game.zip": 5}, "BIOS/": {"BIOS/gamate.zip": 3}}
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, *a: (bios.extend(todo) if label == "BIOS" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: listing.get(prefix, {})}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
        self.run_sync(False, prepare=prepare, patches=patches)
        self.assertEqual([(k, os.path.relpath(p, os.path.dirname(os.path.dirname(os.path.dirname(p))))) for k, p, _ in bios],
                         [("BIOS/gamate.zip", os.path.join("ROMs", "gamate", "gamate.zip"))])
        self.assertFalse([q for q in asked if q.startswith("Delete these")], asked)

    def test_rom_files_alone_are_extras_and_do_not_count_as_roms(self):
        """With no games to sync, a system's ROM-folder BIOS file is removed and doesn't pull in its BIOS."""
        gamate = {"name": "Tiger Gamate", "bucket": "gamate", "folders": {"esde": "gamate"},
                  "bios": {"files": ["other.bin"], "rom_files": ["gamate.zip"]}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, gamate]}

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gamate"))
            open(os.path.join(card, "ROMs", "gamate", "gamate.zip"), "w").close()
        bios, asked = [], []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, *a: (bios.extend(todo) if label == "BIOS" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"BIOS/gamate.zip": 3, "BIOS/other.bin": 1} if prefix == "BIOS/" else list_sizes(prefix)}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
        self.run_sync(False, prepare=prepare, patches=patches)
        self.assertEqual(bios, [])
        self.assertEqual([q for q in asked if q.startswith("Delete these")], ["Delete these 1 local file(s) (0 B)?"])

    def test_android_files_are_copied_to_apks_on_esde_cards(self):
        got = []
        patches = ((cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, icon, base, *a: (got.extend((j[0], j[1]) for j in todo) if label == "Android" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"os/android/APKs/": 0, "os/android/APKs/Obtainium.apk": 5} if prefix == "os/android/APKs/" else list_sizes(prefix)}),
                   (cli.ui, {"choose": lambda q, *a, **k: "n"}))
        self.run_sync(False, patches=patches)
        self.assertEqual([k for k, _ in got], ["os/android/APKs/Obtainium.apk"])
        self.assertEqual(os.path.basename(os.path.dirname(got[0][1])), "APKs")

    def test_themes_are_copied_to_themes_on_onion_cards_only(self):
        listing = lambda prefix, sizes=True: ({"os/onion/Themes/": 0, "os/onion/Themes/A/config.json": 5, "os/onion/Themes/A/.DS_Store": 1}
                                  if prefix == "os/onion/Themes/" else list_sizes(prefix))
        for layout, expected in (("onion", ["os/onion/Themes/A/config.json"]), ("allium", []), ("esde", [])):
            with self.subTest(layout=layout):
                got = []
                layouts = {"esde": MANIFEST["layouts"]["esde"],
                           "onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS", "themes_dir": "Themes"},
                           "allium": {"label": "Allium", "roms_dir": "Roms", "bios_dir": "BIOS"}}
                manifest = {**MANIFEST, "layouts": layouts, "systems": [{**SYSTEM, "folders": {layout: "GBA"}}]}
                patches = ((cli, {"free_space": lambda path: 10**9}),
                           (store, {"load_manifest": lambda names=(), manifest=manifest: manifest}),
                           (cli.picker, {"saved_setup": lambda *a, layout=layout: (None, layout)}),
                           (cli.downloads, {"run_downloads": lambda todo, label, icon, base, *a: (got.extend((j[0], j[1]) for j in todo) if label == "Themes" else None) or 0}),
                           (cli.s3, {"list_sizes": listing}),
                           (cli.ui, {"choose": lambda q, *a, **k: "n"}))
                self.run_sync(False, patches=patches)
                self.assertEqual([k for k, _ in got], expected)
                if expected:
                    self.assertTrue(got[0][1].endswith(os.path.join("Themes", "A", "config.json")))

    def test_roms_of_systems_the_device_dropped_are_extras(self):
        """A system the card's device no longer lists is scanned too, so its leftovers are offered for deletion."""
        dropped = {"name": "Arcade", "bucket": "fbneo", "folders": {"esde": "fbneo"}, "bios": {"files": []}, "games": [{"bucket": "fbneo/a.zip"}]}
        device = {"id": "dev", "name": "Dev", "systems": ["gba"], "note": ""}
        manifest = {**MANIFEST, "systems": [SYSTEM, dropped], "devices": [device]}

        def prepare(card):
            for rel in ("gba/Game.zip", "fbneo/a.zip"):
                os.makedirs(os.path.join(card, "ROMs", os.path.dirname(rel)), exist_ok=True)
                open(os.path.join(card, "ROMs", rel), "w").close()
        asked = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (device, "esde")}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
        self.run_sync(False, prepare=prepare, patches=patches)
        self.assertEqual([q for q in asked if q.startswith("Delete these")], ["Delete these 1 local file(s) (0 B)?"])

    def test_declining_the_space_prompt_exits_0(self):
        patches = ((cli, {"free_space": lambda path: 3}),
                   (cli.ui, {"confirm": lambda q, default=True: False, "has_terminal": lambda: True}))
        self.assertEqual(self.run_sync(False, patches=patches, yes=False), 0)

    def test_quiet_shows_why_it_asks_try_anyway(self):
        patches = ((cli, {"free_space": lambda path: 3}),
                   (cli.ui, {"confirm": lambda q, default=True: False, "has_terminal": lambda: True}))
        self.assertEqual(self.run_sync(False, patches=patches, yes=False, args=["--quiet"]), 0)
        self.assertIn("Not enough space", self.err.getvalue())

    def test_not_enough_space_fails_when_it_cannot_ask(self):
        for yes, terminal in ((True, True), (False, False)):
            with self.subTest(yes=yes, terminal=terminal):
                patches = ((cli, {"free_space": lambda path: 3}),
                           (cli.ui, {"has_terminal": lambda: terminal, "confirm": mock.Mock(side_effect=AssertionError("asked"))}))
                self.assertEqual(self.run_sync(False, patches=patches, yes=yes), 1)
                self.assertIn("Not enough space", self.err.getvalue())

    def scrape_patches(self, loads=None):
        """Patches that make the card's scraped data one 2000-byte cover for Game.zip."""
        def build(layout, systems, data, rels, dest_of, es_dir, present, base):
            return {"jobs": [("scrapes/gba/covers/Game.png", os.path.join(es_dir, "downloaded_media", "gba", "covers", "Game.png"), 2000)],
                    "gamelists": {}, "writes": []}

        def load(systems):
            if loads is not None:
                loads.append(1)
            return {s["bucket"]: ({}, {}) for s in systems}
        return ((scrape_plan, {"build_scrape_plan": build, "load_scrape_data": load}),)

    def test_the_confirmed_total_includes_scraped_media(self):
        asked, loads = [], []
        patches = self.scrape_patches(loads) + ((cli, {"free_space": lambda path: 10**9}),
                                                (cli.ui, {"confirm": lambda q, default=True: asked.append(q) or True}))
        self.assertEqual(self.run_sync(False, patches=patches, yes=False), 0)
        self.assertIn("⬇️  Download 2 file(s) (2.0 KB)?", asked)
        self.assertEqual(loads, [1])
        self.assertEqual(self.out.getvalue().count("Scraped data:"), 1)

    def test_scraped_media_count_toward_the_space_check(self):
        patches = self.scrape_patches() + ((cli, {"free_space": lambda path: 1000}),)
        self.assertEqual(self.run_sync(False, patches=patches), 1)
        self.assertIn("Not enough space: 2.0 KB to download, 1000 B free", self.err.getvalue())

    def test_dry_run_shows_free_space_and_whether_it_fits(self):
        patches = self.scrape_patches() + ((cli, {"free_space": lambda path: 1000}),)
        self.assertEqual(self.run_sync(True, patches=patches), 0)
        out = self.out.getvalue()
        self.assertIn("Free on the card: 1000 B", out)
        self.assertIn("Not enough space: 2.0 KB to download, 1000 B free", out)
        self.assertIn("Would download 2 file(s) (2.0 KB)", out)
        self.assertEqual(out.count("Scraped data:"), 1)

    def test_dry_run_counts_the_roms_it_would_delete_as_freed(self):
        patches = ((cli, {"free_space": lambda path: 1000}), (cli.ui, {"choose": lambda *a, **k: "n"}))
        self.assertEqual(self.run_sync(True, prepare=self.old_rom(100), patches=patches), 0)
        self.assertIn("Free on the card: 1.1 KB", self.out.getvalue())

    def test_scraped_media_sizes_are_read_once_in_a_real_run(self):
        statted = []

        def prepare(card):
            os.makedirs(os.path.join(card, "ES-DE", "downloaded_media", "gba", "covers"))
            with open(os.path.join(card, "ES-DE", "downloaded_media", "gba", "covers", "Game.png"), "wb") as f:
                f.write(b"x" * 3)
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Game.zip"), "wb") as f:
                f.write(b"x" * 5)
        sizes = {"scrapes/gba/covers/Game.png": 3, "scrapes/gba/marquees/Game.png": 4}

        def list_scrapes(prefix, sizes_=True):
            return {k: None for k in sizes} if prefix == "scrapes/gba/" else list_sizes(prefix)

        def stat_sizes(keys):
            statted.extend(keys)
            return {k: sizes[k] for k in keys if k in sizes}
        patches = ((s3, {"list_sizes": list_scrapes, "stat_sizes": stat_sizes}), (cli, {"free_space": lambda path: 10**9}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(sorted(statted), sorted(sizes))

    def test_no_android_line_on_a_card_without_android_files(self):
        layouts = {"onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        manifest = {**MANIFEST, "layouts": layouts, "systems": [{**SYSTEM, "folders": {"onion": "GBA"}}]}
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "onion")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": downloads.run_downloads}),
                   (cli.s3, {"download": lambda job, *a: os.makedirs(os.path.dirname(job[1]), exist_ok=True) or open(job[1], "wb").close()}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)
        self.assertNotIn("Android", self.out.getvalue())
        self.assertEqual(self.out.getvalue().count("Scraped data"), 1)

    def test_a_run_ends_with_what_it_downloaded(self):
        manifest = {**MANIFEST, "systems": [{**SYSTEM, "games": SYSTEM["games"] + [{"bucket": "gba/Gone.zip"}]}]}
        patches = ((store, {"load_manifest": lambda names=(): manifest}), (cli, {"free_space": lambda path: 10**9}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)
        self.assertRegex(self.out.getvalue().splitlines()[-1], r"^🎉 Done: downloaded 1 file\(s\) \(5 B\) in \d+m\d\ds; 1 listed ROM\(s\) not in storage$")

    def test_a_run_with_nothing_to_do_says_so_at_the_end(self):
        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Game.zip"), "wb") as f:
                f.write(b"x" * 5)
        self.assertEqual(self.run_sync(False, prepare=prepare), 0)
        self.assertRegex(self.out.getvalue().splitlines()[-1], r"^🎉 Done: downloaded 0 file\(s\) \(0 B\) in \d+m\d\ds$")

    def test_a_run_with_failures_ends_with_them_and_what_did_download(self):
        def run_downloads(todo, label, icon, base, failures=None):
            failures.extend((j[0], "boom") for j in todo)
            return len(todo)
        patches = ((cli, {"free_space": lambda path: 10**9}), (cli.downloads, {"run_downloads": run_downloads}))
        self.assertEqual(self.run_sync(False, patches=patches), 1)
        self.assertRegex(self.out.getvalue().splitlines()[-1], r"^⚠️  Done with 1 failure\(s\): downloaded 0 file\(s\) \(0 B\) in \d+m\d\ds$")

    def test_vita_game_syncs_its_dlc_and_newest_update_and_drops_the_old_update(self):
        game = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
        old = "psvita/G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip"
        new = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
        dlc = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
        listing = {game: 4, old: 5, new: 6, dlc: 7}
        vita_system = {"name": "Vita", "bucket": "psvita", "folders": {"esde": "psvita"}, "bios": {"files": []},
                       "games": [{"bucket": game}]}
        manifest = {**MANIFEST, "systems": [vita_system]}
        jobs, asked = [], []

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "psvita"))
            for key in (game, old):
                with open(os.path.join(card, "ROMs", key), "wb") as f:
                    f.write(b"x" * listing[key])

        def run_downloads(todo, *args, **kwargs):
            jobs.extend(job[0] for job in todo)
            return 0
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (s3, {"list_sizes": lambda prefix, sizes=True: dict(listing) if prefix == "psvita/" else {}}),
                   (cli.downloads, {"run_downloads": run_downloads}),
                   (cli.vita, {"add_psvita_files": lambda dests: []}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "y",
                             "confirm": lambda q, default=True: asked.append(q) or True}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(sorted(jobs), sorted([dlc, new]))
        self.assertTrue(any(q.startswith("Delete these 1") for q in asked), asked)


if __name__ == "__main__":
    unittest.main()
