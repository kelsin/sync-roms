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
from sync_roms import cli, s3, store, usersettings  # noqa: E402

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

    def run_sync(self, dry_run, picks=lambda rows, present, state, editable: [0], edit_card_system=None, prepare=None, patches=()):
        with tempfile.TemporaryDirectory() as card:
            if prepare:
                prepare(card)
            argv = ["sync-roms", card, "--yes"] + (["--dry-run"] if dry_run else [])
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: {}}),
                        (store, {"load_manifest": lambda names=(): MANIFEST, "load_cards": lambda: {}, "save_card": lambda *a: None}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: (None, "esde"), "pick_systems": picks}),
                        (cli.downloads, {"run_downloads": lambda *a: 0}),
                        (cli.clean, {"clean_android_media": lambda *a: None}),
                        (cli.surprise, {"run_surprise": lambda *a, **k: []})) + tuple(patches):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                if edit_card_system:
                    st.enter_context(mock.patch.object(cli.edit, "edit_card_system", edit_card_system))
                st.enter_context(contextlib.redirect_stdout(io.StringIO()))
                return cli.sync()

    def test_dry_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(True), 0)

    def test_real_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(False), 0)

    def test_games_key_edits_the_cards_games_then_reopens_the_picker(self):
        answers, edited, states = iter([("games", 0), [0]]), [], []

        def picks(rows, present, state, editable):
            states.append(state)
            state.setdefault("sel", [False])
            return next(answers)
        self.assertEqual(self.run_sync(False, picks, lambda *a: edited.append(a) or True), 0)
        self.assertEqual([a[1] for a in edited], ["gba"])
        self.assertIs(states[0], states[1])
        self.assertTrue(states[1]["sel"][0])

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

    def test_dry_run_picker_is_not_editable(self):
        flags = []
        self.run_sync(True, lambda rows, present, state, editable: flags.append(editable) or [0])
        self.assertEqual(flags, [False])

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
        """A system with no games listed, selected or not, keeps no ROMs on the card."""
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}

        def prepare(card):
            for rel in ("gba/Game.zip", "vectrex/Old.zip"):
                os.makedirs(os.path.join(card, "ROMs", os.path.dirname(rel)), exist_ok=True)
                open(os.path.join(card, "ROMs", rel), "w").close()
        for picked in ([0], [0, 1]):
            with self.subTest(picked=picked):
                asked = []
                patches = ((store, {"load_manifest": lambda names=(): manifest}),
                           (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
                self.run_sync(False, lambda rows, present, state, editable: picked, prepare=prepare, patches=patches)
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
        self.run_sync(False, lambda rows, present, state, editable: [0], prepare=prepare, patches=patches)
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
        patches = ((cli, {"free_space": lambda path: 3}), (cli.ui, {"confirm": lambda q, default=True: False}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)


if __name__ == "__main__":
    unittest.main()
