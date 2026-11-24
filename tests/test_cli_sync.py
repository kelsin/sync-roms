import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from helpers import MANIFEST, SYSTEM, DataDir, list_sizes, touch  # noqa: E402
from sync_roms import cli, downloads, inventory, s3, scrape_plan, store, usersettings  # noqa: E402

REAL_LOAD_CARDS = store.load_cards


class SyncSmokeTest(DataDir):
    def run_sync(self, dry_run, prepare=None, patches=(), yes=True, args=(), after=None, card_dir=None):
        """The exit code; what went to stderr is in self.err. after(card) runs before the card folder goes.
        card_dir: sync this folder (kept) instead of a fresh one."""
        with contextlib.nullcontext(card_dir) if card_dir else tempfile.TemporaryDirectory() as card:
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
                        (cli.clean, {"eject": lambda: None}),
                        (cli.surprise, {"run_surprise": lambda *a, **k: [], "fill_surprises": lambda *a, **k: []})) + tuple(patches):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                self.out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
                self.err = st.enter_context(contextlib.redirect_stderr(io.StringIO()))
                try:
                    code = cli.sync()
                except SystemExit as e:
                    code = e.code
            if after:
                after(card)
            return code

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

        def run_surprise(card, setup, chosen, interactive, dry_run, to_fetch=None, card_match=None, on_guest=None):
            calls.append(([s["bucket"] for s in chosen], to_fetch(SYSTEM, ["gba/Game.zip", "gba/New.zip"])))
            return []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.surprise, {"run_surprise": run_surprise}),
                   (cli.inventory, {"cached": lambda prefix: {"gba/Game.zip": 5, "gba/New.zip": 7}}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(calls, [(["gba", "vectrex"], {"gba/New.zip"})])

    def test_the_editor_can_tell_which_storage_games_are_already_on_the_card(self):
        calls = []

        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            for name in ("kept.GBA", "Stray.gba"):
                with open(os.path.join(card, "ROMs", "gba", name), "wb") as f:
                    f.write(b"x")

        def run_surprise(card, setup, chosen, interactive, dry_run, to_fetch=None, card_match=None, on_guest=None):
            calls.append(card_match(SYSTEM, ["gba/Kept.gba", "gba/Other.gba"]))
            calls.append(card_match({**SYSTEM, "bucket": "nes", "folders": {}}, ["nes/A.nes"]))
            return []
        patches = ((cli.surprise, {"run_surprise": run_surprise}),)
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(calls, [{"gba/Kept.gba"}, set()])

    def card_matches(self, layout, folder, files, keys, system_id="psx"):
        """What card_match answers for keys, with files (paths under the system folder) on the card."""
        got = []
        system = {**SYSTEM, "name": "PS", "bucket": system_id, "folders": {"esde": folder, "onion": folder, "nextui": folder}}

        def prepare(card):
            for f in files:
                path = os.path.join(card, "Roms" if layout == "onion" else "ROMs", folder, f)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(b"x")

        def run_surprise(card, setup, chosen, interactive, dry_run, to_fetch=None, card_match=None, on_guest=None):
            got.append(card_match(system, keys))
            return []
        layouts = {layout: {"label": layout, "roms_dir": "Roms" if layout == "onion" else "ROMs", "bios_dir": "BIOS",
                            **({"disc_dir": ".multi-disc"} if layout == "esde" else {}),
                            **({"disc_folders": True} if layout == "nextui" else {})}}
        patches = ((store, {"load_manifest": lambda names=(): {**MANIFEST, "systems": [system], "layouts": layouts}}),
                   (cli.picker, {"saved_setup": lambda *a: (None, layout)}),
                   (cli.surprise, {"run_surprise": run_surprise}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        return got[0]

    def test_a_nextui_dry_run_plans_an_old_named_folder_as_renamed(self):
        system = {**SYSTEM, "name": "Game Gear", "bucket": "gba", "folders": {"nextui": "Sega Game Gear (GG)"}}
        layouts = {"nextui": {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios"}}

        def prepare(card):
            touch(os.path.join(card, "Roms", "Game Gear (GG)", "Game.zip"), b"x" * 5)
        patches = ((store, {"load_manifest": lambda names=(): {**MANIFEST, "systems": [system], "layouts": layouts}}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "nextui")}),
                   (cli.inventory, {"cached": lambda prefix: {"gba/Game.zip": 5}}))
        self.assertEqual(self.run_sync(True, prepare=prepare, patches=patches, args=["--json"]), 0, self.err.getvalue())
        plan = json.loads(self.out.getvalue())
        self.assertEqual((plan["downloads"], plan["delete"]), ([], []))

    def test_a_disc_in_the_layouts_disc_folder_matches_its_key(self):
        discs = ["psx/Game (Disc 1).chd", "psx/Game (Disc 2).chd"]
        keys = discs + ["psx/Game.m3u", "psx/Other.chd"]
        found = self.card_matches("esde", "psx", [".multi-disc/Game (Disc 1).chd", ".multi-disc/Game (Disc 2).chd",
                                                  "Game.m3u"], keys)
        self.assertEqual(found, set(keys[:3]))

    def test_a_disc_game_in_a_folder_of_its_own_matches_its_keys(self):
        keys = ["psx/Game (Disc 1).chd", "psx/Game (Disc 2).chd", "psx/Game.m3u", "psx/Solo.cue", "psx/Solo.bin",
                "psx/Other.chd"]
        found = self.card_matches("nextui", "Sony PlayStation (PS)",
                                  ["Game/Game (Disc 1).chd", "Game/Game (Disc 2).chd", "Game/Game.m3u", "Solo/Solo.cue",
                                   "Solo/Solo.bin"], keys)
        self.assertEqual(found, set(keys[:5]))

    def test_a_name_in_another_unicode_form_matches(self):
        import unicodedata
        found = self.card_matches("onion", "PSX", [unicodedata.normalize("NFD", "Pokémon.chd")], ["psx/Pokémon.chd"])
        self.assertEqual(found, {"psx/Pokémon.chd"})

    def test_surprises_are_filled_from_systems_without_games_too(self):
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}
        surprises = [{"system": "gba", "bucket": "gba/Other.zip", "title": "Other"}]

        class Cards(dict):  # every card name has surprises already, so the card is not a fresh one
            def get(self, name, default=None):
                return {"surprises": surprises}
        calls = []
        patches = ((store, {"load_manifest": lambda names=(): manifest, "load_cards": Cards}),
                   (cli.surprise, {"fill_surprises": lambda card, setup, chosen, dry_run: calls.append(
                       [s["bucket"] for s in chosen]) or []}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)
        self.assertEqual(calls, [["gba", "vectrex"]])

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

    def test_systems_with_no_nextui_folder_are_skipped_and_the_others_still_sync(self):
        n64 = {"name": "Nintendo 64", "bucket": "n64", "folders": {"nextui": None}, "bios": {"files": []},
               "games": [{"bucket": "n64/Game.z64"}]}
        gba = {**SYSTEM, "folders": {"nextui": "Game Boy Advance (GBA)"}}
        manifest = {"systems": [gba, n64], "devices": [],
                    "layouts": {"nextui": {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios"}}}
        lines, synced = [], []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "nextui")}),
                   (cli.surprise, {"fill_surprises": lambda card, setup, chosen, dry_run: synced.append(
                       [s["bucket"] for s in chosen]) or []}),
                   (cli.ui, {"dim": lambda text: lines.append(text) or text}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)
        self.assertEqual(sum("1 system(s) have no NextUI folder" in x for x in lines), 1)
        self.assertEqual(synced, [["gba"]])

    def test_the_systems_synced_are_those_the_device_runs_that_have_a_folder_by_name(self):
        """In a dry run (the systems as first read) and a real one (read again once the card's games are saved). The
        skipped count leaves out a system the device doesn't run."""
        def system(name, bucket, folder):
            return {"name": name, "bucket": bucket, "folders": {"nextui": folder}, "bios": {"files": []},
                    "games": [{"bucket": f"{bucket}/Game.zip"}]}
        systems = [system("Zeta", "zeta", "Zeta (Z)"), system("Game Boy Advance", "gba", "Game Boy Advance (GBA)"),
                   system("Nintendo 64", "n64", None), system("Super Nintendo", "snes", None),
                   system("Arcade", "fbneo", "Arcade (FBN)")]
        device = {"id": "dev", "name": "Dev", "systems": ["zeta", "gba", "n64"], "note": ""}
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                manifest = {"systems": list(systems), "devices": [device],
                            "layouts": {"nextui": {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios"}}}
                lines, synced = [], []
                patches = ((store, {"load_manifest": lambda names=(): manifest}),
                           (cli.picker, {"saved_setup": lambda *a: (device, "nextui")}),
                           (cli.surprise, {"fill_surprises": lambda card, setup, chosen, dry_run: synced.append(
                               [s["bucket"] for s in chosen]) or []}),
                           (cli.ui, {"dim": lambda text: lines.append(text) or text}))
                self.assertEqual(self.run_sync(dry_run, patches=patches), 0)
                self.assertEqual([x for x in lines if "system(s) have no" in x],
                                 ["  1 system(s) have no NextUI folder and are skipped"])
                self.assertEqual(synced, [["gba", "zeta"]])

    def test_nextui_bios_goes_in_per_tag_folders(self):
        """Each BIOS file lands in Bios/<TAG>/ for the system's tag and its extra tags; subpaths are kept; ROM files stay put."""
        gba = {**SYSTEM, "folders": {"nextui": "Game Boy Advance (GBA)"}, "nextui_bios_tags": ["MGBA"],
               "bios": {"files": ["gba_bios.bin"]}}
        fbn = {"name": "FinalBurn Neo", "bucket": "fbneo", "folders": {"nextui": "Arcade (FBN)"},
               "bios": {"files": ["fbneo/samples/x.zip"], "rom_files": ["neogeo.zip"]}, "games": [{"bucket": "fbneo/Game.zip"}]}
        manifest = {"systems": [gba, fbn], "devices": [],
                    "layouts": {"nextui": {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios", "bios_by_tag": True}}}
        listing = {"gba/": {"gba/Game.zip": 5}, "fbneo/": {"fbneo/Game.zip": 5},
                   "BIOS/": {"BIOS/gba_bios.bin": 3, "BIOS/fbneo/samples/x.zip": 4, "BIOS/neogeo.zip": 2}}
        bios = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "nextui")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, *a: (bios.extend(todo) if label == "BIOS" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: listing.get(prefix, {})}),
                   (cli.ui, {"choose": lambda q, *a, **k: "n"}))
        self.run_sync(False, patches=patches)
        got = sorted((k, p.split(os.sep + "Bios" + os.sep)[-1] if os.sep + "Bios" + os.sep in p else "Roms/" + p.split(os.sep + "Roms" + os.sep)[-1])
                     for k, p, _ in bios)
        self.assertEqual(got, sorted([
            ("BIOS/gba_bios.bin", "GBA/gba_bios.bin"), ("BIOS/gba_bios.bin", "MGBA/gba_bios.bin"),
            ("BIOS/fbneo/samples/x.zip", "FBN/fbneo/samples/x.zip"),
            ("BIOS/neogeo.zip", "Roms/Arcade (FBN)/neogeo.zip")]))

    def test_an_old_nextui_folder_is_renamed_instead_of_downloaded_again(self):
        old, new = "Super Nintendo (SFC)", "Super Nintendo Entertainment System (SFC)"
        snes = {"name": "Super Nintendo", "bucket": "snes", "folders": {"nextui": new}, "bios": {"files": []},
                "games": [{"bucket": "snes/game.sfc"}]}
        manifest = {"systems": [snes], "devices": [],
                    "layouts": {"nextui": {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios", "bios_by_tag": True}}}
        roms = []

        def prepare(card):
            os.makedirs(os.path.join(card, "Roms", old))
            with open(os.path.join(card, "Roms", old, "game.sfc"), "wb") as f:
                f.write(b"x" * 5)

        def after(card):
            self.assertEqual(os.listdir(os.path.join(card, "Roms")), [new])
            self.assertTrue(os.path.exists(os.path.join(card, "Roms", new, "game.sfc")))
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "nextui")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, label, *a: (roms.extend(todo) if label == "ROMs" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"snes/game.sfc": 5} if prefix == "snes/" else {}}),
                   (cli.ui, {"choose": lambda q, *a, **k: "n"}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches, after=after), 0)
        self.assertEqual(roms, [])

    def disc_folder_sync(self, layout_name, folder, card):
        """A real-run sync of a two-disc bin/cue game, a one-disc bin/cue game and a lone .chd onto card; returns the
        downloaded paths relative to the card and the ROM present() checks the scrape plan made."""
        names = ["Final Fantasy VII (USA) (Disc 1).cue", "Final Fantasy VII (USA) (Disc 1).bin",
                 "Final Fantasy VII (USA) (Disc 2).cue", "Final Fantasy VII (USA) (Disc 2).bin",
                 "Final Fantasy VII (USA).m3u", "Tony Hawk (USA).cue", "Tony Hawk (USA).bin", "Lone (USA).chd"]
        sizes = {"psx/" + n: 3 + i for i, n in enumerate(names)}
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {layout_name: folder}, "bios": {"files": []},
               "games": [{"bucket": k} for k in sizes]}
        layout = {"label": "X", "roms_dir": "Roms", "bios_dir": "Bios"}
        if layout_name == "nextui":
            layout["disc_folders"] = True
        manifest = {"systems": [psx], "devices": [], "layouts": {layout_name: layout}}
        got, present = [], []

        def download(job, *a):
            got.append(os.path.relpath(job[1], card))
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "w") as f:
                f.write("x" * job[2])

        def build_scrape_plan(layout_name, systems, data, rom_rels, dest_of, es_dir, check, base, recheck=None, hidden=None):
            present.append(check(os.path.join(dest_of(psx), "Final Fantasy VII (USA).m3u")))
            return {"jobs": [], "gamelists": {}, "writes": []}
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.picker, {"saved_setup": lambda *a: (None, layout_name)}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes_=True: sizes if prefix == "psx/" else {}, "download": download}),
                   (cli.scrape_plan, {"load_scrape_data": lambda chosen: {}, "build_scrape_plan": build_scrape_plan}),
                   (cli, {"free_space": lambda path: 10**9}), (cli.downloads, {"run_downloads": downloads.run_downloads}))
        self.assertEqual(self.run_sync(False, patches=patches, card_dir=card), 0)
        return sorted(got), present

    def test_nextui_keeps_each_disc_game_in_its_own_folder(self):
        with tempfile.TemporaryDirectory() as card:
            got, present = self.disc_folder_sync("nextui", "Sony PlayStation (PS)", card)
            ff7 = os.path.join("Roms", "Sony PlayStation (PS)", "Final Fantasy VII (USA)")
            th = os.path.join("Roms", "Sony PlayStation (PS)", "Tony Hawk (USA)")
            self.assertEqual(got, sorted([
                os.path.join(ff7, "Final Fantasy VII (USA).m3u"),
                os.path.join(ff7, "Final Fantasy VII (USA) (Disc 1).cue"), os.path.join(ff7, "Final Fantasy VII (USA) (Disc 1).bin"),
                os.path.join(ff7, "Final Fantasy VII (USA) (Disc 2).cue"), os.path.join(ff7, "Final Fantasy VII (USA) (Disc 2).bin"),
                os.path.join(th, "Tony Hawk (USA).cue"), os.path.join(th, "Tony Hawk (USA).bin"),
                os.path.join("Roms", "Sony PlayStation (PS)", "Lone (USA).chd")]))
            self.assertEqual(present[-1], True)  # the scrape plan finds the playlist in its folder
            again, _ = self.disc_folder_sync("nextui", "Sony PlayStation (PS)", card)
            self.assertEqual(again, [])
            self.assertTrue(all(os.path.exists(os.path.join(card, p)) for p in got))

    def test_esde_keeps_disc_games_loose(self):
        with tempfile.TemporaryDirectory() as card:
            got, _ = self.disc_folder_sync("esde", "psx", card)
            self.assertEqual(len(got), 8)
            self.assertTrue(all(os.path.dirname(p) == os.path.join("Roms", "psx") for p in got))

    def test_loose_discs_from_an_earlier_nextui_sync_move_into_the_game_folder(self):
        with tempfile.TemporaryDirectory() as card:
            self.disc_folder_sync("esde", "Sony PlayStation (PS)", card)  # the same files, loose in the system folder
            got, _ = self.disc_folder_sync("nextui", "Sony PlayStation (PS)", card)
            self.assertEqual(got, [])
            ps = os.path.join(card, "Roms", "Sony PlayStation (PS)")
            self.assertEqual(sorted(os.listdir(ps)), ["Final Fantasy VII (USA)", "Lone (USA).chd", "Tony Hawk (USA)"])
            self.assertEqual(len(os.listdir(os.path.join(ps, "Final Fantasy VII (USA)"))), 5)

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

    def test_no_delete_lists_unwanted_roms_and_keeps_them(self):
        old, asked = [], []

        def prepare(card):
            self.old_rom(100)(card)
            old.append(os.path.join(card, "ROMs", "gba", "Old.zip"))

        patches = ((cli, {"free_space": lambda path: 1000}),
                   (cli.ui, {"choose": lambda *a, **k: asked.append(a) or "y"}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches, args=["--no-delete"],
                                       after=lambda card: self.assertTrue(os.path.exists(old[0]))), 0)
        self.assertEqual(asked, [])
        self.assertIn("--no-delete: keeping 1 local ROM(s)", self.out.getvalue())
        self.assertIn("Old.zip", self.out.getvalue())

    def test_no_delete_rejects_other_commands(self):
        self.assertNotEqual(self.run_sync(False, args=["--no-delete", "--devices"]), 0)

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

    def test_raofflineproxy_apk_is_left_out_when_the_card_has_it_off(self):
        for flag, expected in ((True, ["os/android/APKs/Obtainium.apk", "os/android/APKs/RAOfflineProxy-v3.apk"]), (False, ["os/android/APKs/Obtainium.apk"])):
            got = []
            apks = {"os/android/APKs/": 0, "os/android/APKs/Obtainium.apk": 5, "os/android/APKs/RAOfflineProxy-v3.apk": 6}
            patches = ((cli, {"free_space": lambda path: 10**9}),
                       (store, {"load_cards": lambda: type("AnyCard", (dict,), {"get": lambda self, k, d=None: {"raofflineproxy": flag}})()}),
                       (cli.downloads, {"run_downloads": lambda todo, label, icon, base, *a: (got.extend(j[0] for j in todo) if label == "Android" else None) or 0}),
                       (cli.s3, {"list_sizes": lambda prefix, sizes=True: apks if prefix == "os/android/APKs/" else list_sizes(prefix)}),
                       (cli.ui, {"choose": lambda q, *a, **k: "n"}))
            with self.subTest(flag):
                self.run_sync(False, patches=patches)
                self.assertEqual(got, expected)

    def test_raofflineproxy_apk_is_copied_for_a_missing_or_malformed_card_entry(self):
        apks = {"os/android/APKs/": 0, "os/android/APKs/Obtainium.apk": 5, "os/android/APKs/RAOfflineProxy-v3.apk": 6}
        for entry in (None, [], "", 0):  # no entry in cards.json, or one that isn't an object: the setting is on
            got = []
            patches = ((cli, {"free_space": lambda path: 10**9}),
                       (store, {"load_cards": lambda: type("AnyCard", (dict,), {"get": lambda self, k, d=None: entry})()}),
                       (cli.downloads, {"run_downloads": lambda todo, label, icon, base, *a: (got.extend(j[0] for j in todo) if label == "Android" else None) or 0}),
                       (cli.s3, {"list_sizes": lambda prefix, sizes=True: apks if prefix == "os/android/APKs/" else list_sizes(prefix)}),
                       (cli.ui, {"choose": lambda q, *a, **k: "n"}))
            with self.subTest(entry=entry):
                self.run_sync(False, patches=patches)
                self.assertEqual(got, ["os/android/APKs/Obtainium.apk", "os/android/APKs/RAOfflineProxy-v3.apk"])

    ZIP = "pico-8_0.2.7_raspi.zip"

    def run_pico8(self, games, copied, dry_run=False, prepare=None, asked=None, device=None, extra_systems=()):
        """Sync a Knulli card with the given pico8 games while storage holds the PICO-8 zip; copied gets the zip's card path."""
        pico = {"name": "PICO-8", "bucket": "pico8", "folders": {"knulli": "pico8"}, "bios": {"files": []}, "games": games}
        layouts = {"knulli": {"label": "Knulli", "roms_dir": "roms", "bios_dir": "bios"}}
        manifest = {**MANIFEST, "layouts": layouts, "systems": [pico, *extra_systems], "devices": [device] if device else MANIFEST.get("devices", [])}
        files = inventory.files
        card_dir = []

        def fake_files(prefix, sizes=True):
            return {"os/pico8/" + self.ZIP: 5} if prefix == "os/pico8/" else files(prefix, sizes)

        def download(job):
            copied.append(os.path.relpath(job[1], card_dir[0]))
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            open(job[1], "wb").write(b"x" * 5)

        def prep(card):
            card_dir.append(card)
            if prepare:
                prepare(card)
        patches = ((store, {"load_manifest": lambda names=(): manifest, "load_cards": REAL_LOAD_CARDS}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.picker, {"saved_setup": lambda *a: (device, "knulli")}),
                   (inventory, {"files": fake_files}),
                   (s3, {"download": download,
                         "list_sizes": lambda prefix, sizes=True: {"pico8/a.p8.png": 5} if prefix == "pico8/" else {}}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n" if asked is not None else "n"}))
        self.run_sync(dry_run, prepare=prep, patches=patches)

    def test_pico8_zip_on_card_with_no_games(self):
        cards = []
        self.run_pico8([], cards)
        self.assertIn(os.path.join("roms", "pico8", self.ZIP), cards)

    def test_pico8_folder_extras_keep_installer_files(self):
        def prepare(card):
            folder = os.path.join(card, "roms", "pico8")
            os.makedirs(folder)
            for n in ("Splore.png", self.ZIP, "other.p8"):
                open(os.path.join(folder, n), "w").close()
            store.update_card(os.path.basename(card), pico8=self.ZIP)
        asked = []
        self.run_pico8([{"bucket": "pico8/a.p8.png"}], [], prepare=prepare, asked=asked)
        text = " ".join(asked) + self.out.getvalue()
        self.assertIn("other.p8", text)
        self.assertNotIn("Splore.png", text)
        self.assertNotIn(self.ZIP, text)

    def test_pico8_installer_files_kept_when_the_device_drops_pico8(self):
        gba = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"knulli": "gba"}, "bios": {"files": []}, "games": [{"bucket": "gba/Game.zip"}]}
        device = {"id": "x", "name": "X", "systems": ["gba"], "note": "", "firmwares": ["knulli"]}

        def prepare(card):
            folder = os.path.join(card, "roms", "pico8")
            os.makedirs(folder)
            for n in ("Splore.png", self.ZIP, "other.p8"):
                open(os.path.join(folder, n), "w").close()
            store.update_card(os.path.basename(card), pico8=self.ZIP)
        asked = []
        self.run_pico8([], [], prepare=prepare, asked=asked, device=device, extra_systems=[gba])
        text = " ".join(asked) + self.out.getvalue()
        self.assertIn("other.p8", text)
        self.assertNotIn("Splore.png", text)
        self.assertNotIn(self.ZIP, text)

    def test_pico8_dry_run(self):
        cards = []
        self.run_pico8([{"bucket": "pico8/a.p8.png"}], cards, dry_run=True)
        self.assertEqual(cards, [])
        self.assertIn(os.path.join("roms", "pico8", self.ZIP), self.out.getvalue())

    def driver_sync(self, layout, writable=True, dry_run=False, gpu="adreno-650", saved=None, args=()):
        """Sync a card with a device with the gpu (an Adreno 650) and the saved drivers list on the card (and in cards.json);
        (copied (key, path) pairs, refresh calls, cards.json updates)."""
        got, refreshed, updates = [], [], []
        device = {"id": "rp5", "name": "RP5", "systems": ["gba"], "note": "", "firmwares": [layout], **({"gpu": gpu} if gpu else {})}

        class Cards(dict):  # every card has the saved drivers list
            def get(self, key, default=None):
                return {"drivers": saved} if saved else default

        def prepare(card):
            os.makedirs(os.path.join(card, "Drivers"))
            for name in saved or ():
                open(os.path.join(card, "Drivers", name), "w").close()
        layouts = {layout: {"label": layout, "roms_dir": "ROMs", "bios_dir": "BIOS"}}
        manifest = {**MANIFEST, "layouts": layouts, "devices": [device], "systems": [{**SYSTEM, "folders": {layout: "gba"}}]}
        data = {"drivers": [{"id": i, "name": f"Driver {i}", "repo": f"o/{i}", "asset": "zip"} for i in "ab"],
                "gpus": {"adreno-650": {"drivers": ["a", "b"]}}}
        patches = ((cli, {"free_space": lambda path: 10**9}),
                   (store, {"load_manifest": lambda names=(): manifest, "update_card": lambda card, **v: updates.append(v),
                            "load_cards": lambda: Cards()}),
                   (cli.picker, {"saved_setup": lambda *a: (device, layout)}),
                   (cli.drivers, {"load": lambda: data, "can_write": lambda: writable, "stored_tag": lambda i: "v1",
                                  "refresh": lambda entries, dry_run: refreshed.append(([d["id"] for d in entries], dry_run))}),
                   (cli.downloads, {"run_downloads": lambda todo, label, icon, base, *a: (got.extend((j[0], j[1]) for j in todo) if label == "Drivers" else None) or 0}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"os/drivers/a.zip": 5, "os/drivers/a.tag": 3, "os/drivers/b.zip": 7, "os/drivers/b.tag": 3}
                             if prefix == "os/drivers/" else list_sizes(prefix)}),
                   (cli.ui, {"choose": lambda q, *a, **k: "n"}))
        self.run_sync(dry_run, prepare=prepare, patches=patches, args=args)
        return got, refreshed, updates

    def test_drivers_are_copied_to_drivers_on_esde_cards(self):
        got, refreshed, updates = self.driver_sync("esde")
        self.assertEqual([(k, os.path.basename(p), os.path.basename(os.path.dirname(p))) for k, p in got],
                         [("os/drivers/a.zip", "a-v1.zip", "Drivers"), ("os/drivers/b.zip", "b-v1.zip", "Drivers")])
        self.assertEqual(refreshed, [(["a", "b"], False)])
        self.assertIn("🎮 Drivers:", self.out.getvalue())
        self.assertIn({"drivers": ["a-v1.zip", "b-v1.zip"]}, updates)

    def test_old_drivers_are_removed_when_a_card_gets_none(self):
        for layout, gpu in (("esde", None), ("knulli", "adreno-650")):
            with self.subTest(layout=layout, gpu=gpu):
                got, refreshed, updates = self.driver_sync(layout, gpu=gpu, saved=["a-v1.zip"])
                self.assertEqual((got, refreshed), ([], []))
                self.assertIn("🧹 Removed old driver a-v1.zip", self.out.getvalue())
                self.assertIn({"drivers": []}, updates)

    def test_old_drivers_dry_run_removes_nothing(self):
        _, _, updates = self.driver_sync("esde", gpu=None, saved=["a-v1.zip"], dry_run=True)
        self.assertIn("would delete", self.out.getvalue())
        self.assertNotIn("Removed old driver", self.out.getvalue())
        self.assertEqual(updates, [])

    def test_no_delete_keeps_old_drivers_listed(self):
        with mock.patch.object(cli.ui, "dim", lambda t: t):
            _, _, updates = self.driver_sync("esde", gpu=None, saved=["a-v1.zip"], args=["--no-delete"])
        self.assertIn("--no-delete: keeping 1 old driver(s)", self.out.getvalue())
        self.assertNotIn("Removed old driver", self.out.getvalue())
        self.assertEqual(updates, [])

    def test_a_card_without_drivers_saves_no_list(self):
        _, _, updates = self.driver_sync("esde", gpu=None)
        self.assertFalse([u for u in updates if "drivers" in u])

    def test_knulli_cards_get_no_drivers(self):
        got, refreshed, updates = self.driver_sync("knulli")
        self.assertEqual((got, refreshed), ([], []))
        self.assertNotIn("Drivers", self.out.getvalue())
        self.assertFalse([u for u in updates if "drivers" in u])

    def test_no_write_access_copies_what_storage_has_without_github(self):
        with mock.patch.object(cli.drivers.github, "json", side_effect=AssertionError("GitHub called")):
            got, refreshed, _ = self.driver_sync("esde", writable=False)
        self.assertEqual(refreshed, [])
        self.assertEqual(len(got), 2)
        self.assertIn("no write access to storage: copying the drivers it has", self.out.getvalue())

    def test_dry_run_reports_drivers_and_saves_nothing(self):
        got, refreshed, updates = self.driver_sync("esde", dry_run=True)
        self.assertEqual(refreshed, [(["a", "b"], True)])
        self.assertIn("os/drivers/a.zip", self.out.getvalue())
        self.assertFalse([u for u in updates if "drivers" in u])

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

    def test_a_file_whose_path_would_leave_its_card_folder_is_skipped_with_a_warning(self):
        """A ROM, a BIOS file and a theme file. The ROM that isn't in storage is still the one reported missing."""
        system = {**SYSTEM, "folders": {"onion": "GBA"}, "bios": {"files": ["ok.bin", "../evil.bin"]},
                  "games": [{"bucket": "gba/Game.zip"}, {"bucket": "gba/../evil.zip"}, {"bucket": "gba/Gone.zip"}]}
        listings = {"gba/": {"gba/Game.zip": 5, "gba/../evil.zip": 5}, "BIOS/": {"BIOS/ok.bin": 3, "BIOS/../evil.bin": 3},
                    "os/onion/Themes/": {"os/onion/Themes/A/config.json": 5, "os/onion/Themes/../evil.json": 5}}
        manifest = {**MANIFEST, "systems": [system],
                    "layouts": {"onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS", "themes_dir": "Themes"}}}
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                got = []
                patches = ((cli, {"free_space": lambda path: 10**9}),
                           (store, {"load_manifest": lambda names=(): manifest}),
                           (cli.picker, {"saved_setup": lambda *a: (None, "onion")}),
                           (cli.downloads, {"run_downloads": lambda todo, *a: got.extend(j[0] for j in todo) or 0}),
                           (cli.s3, {"list_sizes": lambda prefix, sizes=True: listings.get(prefix, {})}))
                self.assertEqual(self.run_sync(dry_run, patches=patches), 0)
                lines = self.out.getvalue().split("\n")
                self.assertEqual([line for line in lines if "skipping" in line],
                                 [f"  ⚠️  skipping unsafe path: '../evil.{ext}'" for ext in ("zip", "bin", "json")])
                self.assertEqual([line.strip() for line in lines if "evil" in line and "skipping" not in line], [])
                self.assertEqual([line.strip() for line in lines[lines.index("  ⚠️  1 ROM(s) listed in manifest but not in storage") + 1:]
                                  if line.startswith("       ")], ["gba/Gone.zip"])
                if not dry_run:
                    self.assertEqual(got, ["gba/Game.zip", "BIOS/ok.bin", "os/onion/Themes/A/config.json"])

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

    def test_the_stale_media_check_gets_every_system_by_name_only_when_the_card_syncs_them_all(self):
        """The check reads the manifest's own list of systems: a card that syncs all of them has it in name order, any
        other card in the manifest's order."""
        zeta = {"name": "Zeta", "bucket": "zeta", "folders": {"esde": "zeta"}, "bios": {"files": []}, "games": []}
        n64 = {"name": "Nintendo 64", "bucket": "n64", "folders": {}, "bios": {"files": []}, "games": []}
        device = {"id": "dev", "name": "Dev", "systems": ["zeta", "gba"], "note": ""}
        for systems, setup, want in (([zeta, SYSTEM], None, ["gba", "zeta"]),
                                     ([zeta, SYSTEM, n64], None, ["zeta", "gba", "n64"]),
                                     ([zeta, SYSTEM], device, ["zeta", "gba"])):
            for dry_run in (True, False):
                with self.subTest(systems=len(systems), device=bool(setup), dry_run=dry_run):
                    manifest, seen = {**MANIFEST, "systems": list(systems), "devices": [device]}, []
                    patches = ((store, {"load_manifest": lambda names=(): manifest}),
                               (cli.picker, {"saved_setup": lambda *a: (setup, "esde")}),
                               (scrape_plan, {"stale_media": lambda layout, all_systems, *a: seen.append(
                                   [s["bucket"] for s in all_systems]) or []}))
                    self.assertEqual(self.run_sync(dry_run, patches=patches), 0)
                    self.assertEqual(seen, [want])

    def card_rom(self, rel, size):
        """A prepare that puts a file of size bytes at ROMs/rel on the card, keeping the card's path in self.card."""
        def prepare(card):
            self.card = card
            os.makedirs(os.path.join(card, "ROMs", os.path.dirname(rel)), exist_ok=True)
            with open(os.path.join(card, "ROMs", rel), "wb") as f:
                f.write(b"x" * size)
        return prepare

    def sync_card_files(self, rel, size, dry_run=False, args=()):
        """Sync gba/Game.zip (5 bytes) to a card holding ROMs/rel and an empty vectrex system: (downloaded keys, delete
        prompts, what --json printed, the card's files after the sync)."""
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}
        got, asked, emitted, files = [], [], [], []

        def after(*a):
            files.extend(sorted(os.path.relpath(os.path.join(root, f), os.path.join(self.card, "ROMs"))
                                for root, _, names in os.walk(os.path.join(self.card, "ROMs")) for f in names))
            return 0
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.downloads, {"run_downloads": lambda todo, *a: got.extend(k for k, _, _ in todo) or 0}),
                   (cli.vita, {"add_psvita_files": lambda dests, wrote=None: after() or []}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "y", "emit_json": emitted.append}))
        if dry_run:
            patches += ((cli.pico8, {"run": lambda *a, **k: after()}),)
        self.assertEqual(self.run_sync(dry_run, prepare=self.card_rom(rel, size), patches=patches, args=args), 0)
        return got, [q for q in asked if q.startswith("Delete these")], emitted, files

    def saves_sync_deletes(self, retroarch):
        """A dry-run --json sync of gba/Game.zip to a card with saves beside it and beside a dropped Old.zip, the
        layout's RetroArch folders being retroarch: the file names it would delete."""
        layout = {**MANIFEST["layouts"]["esde"], "retroarch": retroarch}
        manifest = {**MANIFEST, "layouts": {"esde": layout}}
        names = ("Game.zip", "Game.srm", "Old.zip", "Old.srm", "Old.state1", "Old.state1.png")

        def prepare(card):
            for name in names:
                self.card_rom(os.path.join("gba", name), 5 if name == "Game.zip" else 1)(card)
        emitted = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}), (cli.ui, {"emit_json": emitted.append}))
        self.assertEqual(self.run_sync(True, prepare=prepare, patches=patches, args=["--json"]), 0)
        return sorted(os.path.basename(d if isinstance(d, str) else d["path"]) for d in emitted[0]["delete"])

    def test_saves_beside_the_roms_are_never_offered_for_deletion(self):
        """ROCKNIX: RetroArch saves and states sit in the ROM folders, so they are never extras."""
        self.assertEqual(self.saves_sync_deletes({"dir": "ROMs", "saves": "{system}", "states": "savestates/{system}"}),
                         ["Old.zip"])

    def test_stray_saves_in_other_layouts_rom_folders_are_still_extras(self):
        self.assertEqual(self.saves_sync_deletes({"dir": "RetroArch", "saves": "saves", "states": "states"}),
                         ["Game.srm", "Old.srm", "Old.state1", "Old.state1.png", "Old.zip"])

    def test_a_card_file_in_another_case_is_renamed_not_deleted_or_downloaded(self):
        got, deletes, _, files = self.sync_card_files(os.path.join("gba", "GAME.zip"), 5)
        self.assertEqual((got, deletes), ([], []))
        self.assertEqual(files, [os.path.join("gba", "Game.zip")])

    def test_a_dry_run_reports_the_rename_and_changes_nothing(self):
        got, _, emitted, files = self.sync_card_files(os.path.join("gba", "GAME.zip"), 5, dry_run=True, args=["--json"])
        self.assertEqual(files, [os.path.join("gba", "GAME.zip")])
        roms = os.path.join(self.card, "ROMs", "gba")
        self.assertEqual(emitted[0]["rename"], [{"from": os.path.join(roms, "GAME.zip"), "to": os.path.join(roms, "Game.zip")}])
        self.assertEqual((emitted[0]["downloads"], emitted[0]["delete"]), ([], []))
        self.sync_card_files(os.path.join("gba", "GAME.zip"), 5, dry_run=True)
        self.assertIn(f"would rename {os.path.join(self.card, 'ROMs', 'gba', 'GAME.zip')}", self.out.getvalue())

    def test_a_file_of_the_same_name_and_size_elsewhere_is_moved_not_downloaded(self):
        got, deletes, _, files = self.sync_card_files(os.path.join("vectrex", "game.zip"), 5)
        self.assertEqual((got, deletes), ([], []))
        self.assertEqual(files, [os.path.join("gba", "Game.zip")])

    def test_a_dry_run_reports_the_move_as_neither_a_download_nor_a_delete(self):
        _, _, emitted, files = self.sync_card_files(os.path.join("vectrex", "Game.zip"), 5, dry_run=True, args=["--json"])
        self.assertEqual(files, [os.path.join("vectrex", "Game.zip")])
        roms = os.path.join(self.card, "ROMs")
        self.assertEqual(emitted[0]["rename"], [{"from": os.path.join(roms, "vectrex", "Game.zip"),
                                                 "to": os.path.join(roms, "gba", "Game.zip")}])
        self.assertEqual((emitted[0]["downloads"], emitted[0]["delete"], emitted[0]["totals"]["files"]), ([], [], 0))
        self.sync_card_files(os.path.join("vectrex", "Game.zip"), 5, dry_run=True)
        self.assertIn(f"would move {os.path.join(self.card, 'ROMs', 'vectrex', 'Game.zip')}", self.out.getvalue())

    def test_a_file_of_the_same_name_and_another_size_is_deleted_and_downloaded(self):
        got, deletes, _, files = self.sync_card_files(os.path.join("vectrex", "Game.zip"), 3)
        self.assertEqual((got, deletes), (["gba/Game.zip"], ["Delete these 1 local file(s) (3 B)?"]))
        self.assertEqual(files, [])

    def test_a_move_that_fails_is_downloaded_instead(self):
        real_replace = os.replace

        def replace(src, dst):
            if os.path.join("ROMs", "vectrex") in src:
                raise PermissionError("busy")
            return real_replace(src, dst)
        with mock.patch.object(cli.os, "replace", replace):
            got, _, _, _ = self.sync_card_files(os.path.join("vectrex", "Game.zip"), 5)
        self.assertEqual(got, ["gba/Game.zip"])
        self.assertIn("busy", self.err.getvalue())

    def test_a_rename_that_fails_is_a_failure(self):
        def fail(path, new):
            raise PermissionError("busy")
        with mock.patch.object(cli.downloads, "rename_on_card", fail):
            empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
            patches = ((store, {"load_manifest": lambda names=(): {**MANIFEST, "systems": [SYSTEM, empty]}}),
                       (cli, {"free_space": lambda path: 10**9}))
            code = self.run_sync(False, prepare=self.card_rom(os.path.join("gba", "GAME.zip"), 5), patches=patches)
        self.assertEqual(code, 1)
        self.assertIn("busy", self.err.getvalue())

    def test_a_dry_run_does_not_delete_loose_discs_the_real_run_tucks_away(self):
        discs = ["Fahrenheit (USA) (Disc 1) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx"}, "bios": {"files": []},
               "games": [{"bucket": "psx/" + d} for d in discs]}
        layouts = {"esde": {**MANIFEST["layouts"]["esde"], "disc_dir": ".multi-disc"}}
        manifest = {**MANIFEST, "systems": [psx], "layouts": layouts}

        def prepare(card):
            for d in discs:
                self.card_rom(os.path.join("psx", d), 4)(card)
        emitted = []
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"psx/" + d: 4 for d in discs} if prefix == "psx/" else {}}),
                   (cli.ui, {"emit_json": emitted.append}))
        self.assertEqual(self.run_sync(True, prepare=prepare, patches=patches, args=["--json"]), 0)
        self.assertEqual((emitted[0]["downloads"], emitted[0]["delete"], emitted[0]["rename"]), ([], [], []))

    def playlist_sync(self, on_card=None):
        """A real-run ES-DE sync (disc folder .multi-disc) of a two-disc game; returns the playlists written through
        store.replace_file as {name: text} (a list of names when written twice). on_card: {card file: text} there before the sync."""
        discs = ["Fahrenheit (USA) (Disc 1) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]
        m3u_name, text = "Fahrenheit (USA) (Sega CD).m3u", "".join(d + "\n" for d in discs)
        keys = ["psx/" + d for d in discs] + ["psx/" + m3u_name]
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx"}, "bios": {"files": []},
               "games": [{"bucket": k} for k in keys]}
        layouts = {"esde": {**MANIFEST["layouts"]["esde"], "disc_dir": ".multi-disc"}}
        manifest = {**MANIFEST, "systems": [psx], "layouts": layouts}
        sizes = {"psx/" + d: 4 for d in discs}
        sizes["psx/" + m3u_name] = len(text)
        writes, card = [], []
        self.direct = []  # playlists downloaded straight onto the card

        def prepare(root):
            card.append(root)
            for rel, content in (on_card or {}).items():
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                with open(os.path.join(root, rel), "w") as f:
                    f.write(content)

        def download(job, *a):
            if job[1].endswith(".m3u") and job[1].startswith(card[0]):
                self.direct.append(job[1])
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "w") as f:
                f.write(text if job[1].endswith(".m3u") else "x" * job[2])
        real_replace = store.replace_file

        def replace_file(path, data, **kw):
            writes.append((os.path.basename(path), data.decode()))
            return real_replace(path, data, **kw)
        patches = ((store, {"load_manifest": lambda names=(): manifest, "replace_file": replace_file}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes_=True: sizes if prefix == "psx/" else {}, "download": download}),
                   (cli, {"free_space": lambda path: 10**9}), (cli.downloads, {"run_downloads": downloads.run_downloads}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        return [w for w in writes if w[0].endswith(".m3u")]

    def test_a_playlist_is_written_once_already_prefixed(self):
        discs = ["Fahrenheit (USA) (Disc 1) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]
        self.assertEqual(self.playlist_sync(), [("Fahrenheit (USA) (Sega CD).m3u", "".join(f".multi-disc/{d}\n" for d in discs))])
        self.assertEqual(self.direct, [])

    def test_an_old_unprefixed_playlist_is_still_fixed(self):
        discs = ["Fahrenheit (USA) (Disc 1) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]
        name = "Fahrenheit (USA) (Sega CD).m3u"
        card = {f"ROMs/psx/.multi-disc/{d}": "xxxx" for d in discs}
        card["ROMs/psx/" + name] = "".join(d + "\n" for d in discs)
        self.assertEqual(self.playlist_sync(card), [(name, "".join(f".multi-disc/{d}\n" for d in discs))])

    def test_an_already_prefixed_playlist_is_left_alone(self):
        discs = ["Fahrenheit (USA) (Disc 1) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]
        name = "Fahrenheit (USA) (Sega CD).m3u"
        card = {f"ROMs/psx/.multi-disc/{d}": "xxxx" for d in discs}
        card["ROMs/psx/" + name] = "".join(f".multi-disc/{d}\n" for d in discs)
        self.assertEqual(self.playlist_sync(card), [])

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
        def build(layout, systems, data, rels, dest_of, es_dir, present, base, recheck=None):
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
        self.assertIn("Not enough space: 2.0 KB to download, 1000 B free", self.err.getvalue())
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

    def test_the_media_plan_after_the_downloads_is_the_full_plan_without_rechecking_current_media(self):
        def prepare(card):
            os.makedirs(os.path.join(card, "ES-DE", "downloaded_media", "gba", "covers"))
            with open(os.path.join(card, "ES-DE", "downloaded_media", "gba", "covers", "Game.png"), "wb") as f:
                f.write(b"x" * 3)
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Game.zip"), "wb") as f:
                f.write(b"x" * 5)
        sizes = {"scrapes/gba/covers/Game.png": 3, "scrapes/gba/marquees/Game.png": 4}
        real_build, real_current = scrape_plan.build_scrape_plan, downloads.is_current
        plans, checked = [], []

        def build(*a, recheck=None):
            checked.append([])
            plan = real_build(*a, recheck=recheck)
            if recheck is not None:
                checked.append([])
                plans.append((plan, real_build(*a)))  # what a plan that checks every media file has
            return plan

        def is_current(path, *a):
            if "downloaded_media" in path:
                checked[-1].append(os.path.basename(os.path.dirname(path)))
            return real_current(path, *a)
        patches = ((s3, {"list_sizes": lambda prefix, sizes_=True: dict(sizes) if prefix == "scrapes/gba/" else list_sizes(prefix)}),
                   (scrape_plan, {"build_scrape_plan": build}), (downloads, {"is_current": is_current}),
                   (cli, {"free_space": lambda path: 10**9}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        (plan, full), = plans
        self.assertEqual(plan, full)
        self.assertEqual([k for k, _, _ in plan["jobs"]], ["scrapes/gba/marquees/Game.png"])
        self.assertEqual(sorted(checked[0]), ["covers", "marquees"])
        self.assertEqual(checked[1], ["marquees"])  # the cover found current before the downloads is not looked at again

    def scrape_sync_io(self, dry_run):
        """An ES-DE sync with scrapes of gba/Game.zip (on the card, with its cover) and gba/New.zip: ({card folder:
        times listed}, card files given to os.stat, the card's files after the sync)."""
        manifest = {**MANIFEST, "systems": [{**SYSTEM, "games": SYSTEM["games"] + [{"bucket": "gba/New.zip"}]}]}
        sizes = {"gba/Game.zip": 5, "gba/New.zip": 5, "scrapes/gba/covers/Game.png": 3, "scrapes/gba/covers/New.png": 3}
        scans, stats, files, card, walking = {}, [], [], [], []
        real_scandir, real_stat = os.scandir, os.stat

        def prepare(root):
            card.append(root)
            for rel, size in (("ROMs/gba/Game.zip", 5), ("ES-DE/downloaded_media/gba/covers/Game.png", 3)):
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                with open(os.path.join(root, rel), "wb") as f:
                    f.write(b"x" * size)

        def scandir(path="."):
            if card and str(path).startswith(card[0]) and not walking:
                rel = os.path.relpath(path, card[0])
                scans[rel] = scans.get(rel, 0) + 1
            return real_scandir(path)

        def stat(path, *a, **k):
            if card and str(path).startswith(card[0]) and os.path.splitext(str(path))[1]:  # a card file, not a folder
                stats.append(os.path.relpath(path, card[0]))
            return real_stat(path, *a, **k)

        def download(job, *a):
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(b"x" * job[2])

        def cards():  # the sync's last step reads the cards too: the files then are the ones it leaves
            walking.append(True)
            files[:] = sorted(os.path.relpath(os.path.join(root, f), card[0]) for root, _, names in os.walk(card[0]) for f in names)
            walking.clear()
            return {}
        patches = ((store, {"load_manifest": lambda names=(): manifest, "load_cards": cards}),
                   (s3, {"list_sizes": lambda prefix, sizes_=True: {k: v for k, v in sizes.items() if k.startswith(prefix)}}),
                   (cli, {"free_space": lambda path: 10**9, "report_failures": lambda f: None}),
                   (cli.downloads, {"run_downloads": downloads.run_downloads}), (cli.s3, {"download": download}),
                   (os, {"scandir": scandir, "stat": stat}))
        self.assertEqual(self.run_sync(dry_run, prepare=prepare, patches=patches), 0)
        return scans, stats, files

    def test_a_dry_run_lists_each_card_folder_once_and_stats_no_card_file(self):
        scans, stats, files = self.scrape_sync_io(True)
        for folder in ("ROMs/gba", "ES-DE/downloaded_media/gba/covers"):
            self.assertEqual(scans.get(folder), 1, folder)
        self.assertEqual(set(scans.values()), {1})
        self.assertEqual(stats, [])
        self.assertNotIn(os.path.join("ROMs", "gba", "New.zip"), files)

    def test_a_rom_downloaded_by_the_sync_gets_its_media_and_keeps_it(self):
        scans, _, files = self.scrape_sync_io(False)
        self.assertIn(os.path.join("ES-DE", "downloaded_media", "gba", "covers", "New.png"), files)
        self.assertIn(os.path.join("ROMs", "gba", "New.zip"), files)
        self.assertLessEqual(max(scans.values()), 3)  # planning, after the downloads, after the scraped data

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

    def test_onion_sync_of_a_pick_storage_lacks_finishes_without_a_system_folder(self):
        layouts = {"onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS", "disc_dir": ".multi-disc"}}
        manifest = {**MANIFEST, "layouts": layouts,
                    "systems": [{**SYSTEM, "folders": {"onion": "GBA"}, "games": [{"bucket": "gba/Gone.zip"}]}]}
        patches = ((store, {"load_manifest": lambda names=(), m=manifest: m}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "onion")}),
                   (cli, {"free_space": lambda path: 10**9}))
        found = []
        self.assertEqual(self.run_sync(False, patches=patches, after=lambda card: found.append(
            os.path.exists(os.path.join(card, "Roms", "GBA")))), 0)
        self.assertEqual(found, [False])

    def test_onion_sync_installs_surprise_app_and_list(self):
        layouts = {"onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        manifest = {**MANIFEST, "layouts": layouts, "systems": [{**SYSTEM, "folders": {"onion": "GBA"}}]}
        app = io.BytesIO()
        with zipfile.ZipFile(app, "w") as z:
            for name in ("App/Surprise/config.json", "App/Surprise/surprise"):
                z.writestr(name, b"x")
        files = inventory.files

        def fake_files(prefix, sizes=True):
            return {"os/onion/Surprise-v0.1.0.zip": 5} if prefix == "os/onion/" else files(prefix, sizes)

        def download(job, *a):
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(app.getvalue() if job[0].startswith("os/onion/") else b"x" * 5)

        def prepare(card):
            os.makedirs(os.path.join(card, "Emu", "GBA"))
            with open(os.path.join(card, "Emu", "GBA", "config.json"), "w") as f:
                f.write('{"rompath": "../../Roms/GBA", "launch": "launch.sh"}')
            store.update_card(os.path.basename(card), surprises=[
                {"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}, {"system": "gba", "title": "No bucket"}])

        patches = ((store, {"load_manifest": lambda names=(): manifest, "load_cards": REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "onion")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (inventory, {"files": fake_files}),
                   (cli.downloads, {"run_downloads": downloads.run_downloads}),
                   (cli.s3, {"download": download}))
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                found = []
                self.assertEqual(self.run_sync(dry_run, prepare=prepare, patches=patches, after=lambda card: found.extend(
                    os.path.exists(os.path.join(card, *p.split("/"))) for p in ("App/Surprise/surprise", "Roms/surprise.json"))), 0)
                self.assertEqual(found, [not dry_run, not dry_run])
                if not dry_run:
                    self.assertIn("Surprise-v0.1.0.zip", self.out.getvalue())

    def test_spruce_sync_stages_spruceos(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        files = inventory.files
        order = []

        def fake_files(prefix, sizes=True):
            return {"os/spruceos/spruceV4.6.0.7z": 5} if prefix == "os/spruceos/" else files(prefix, sizes)

        def download(job, *a):
            order.append(job[0])
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(b"x" * 5)

        flush = cli.cardfs.flush
        for games in (SYSTEM["games"], []):  # a sync, and a card with nothing to sync
            manifest = {**MANIFEST, "layouts": layouts, "systems": [{**SYSTEM, "games": games, "folders": {"spruce": "GBA"}}]}
            patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": REAL_LOAD_CARDS}),
                       (cli.picker, {"saved_setup": lambda *a: (None, "spruce")}),
                       (cli, {"free_space": lambda path: 10**9}),
                       (inventory, {"files": fake_files}),
                       (cli.downloads, {"run_downloads": downloads.run_downloads}),
                       (cli.cardfs, {"flush": lambda: order.append("flush") or flush()}),
                       (cli.s3, {"download": download}))
            for dry_run in (False, True):
                with self.subTest(games=bool(games), dry_run=dry_run):
                    found = []
                    order.clear()
                    self.assertEqual(self.run_sync(dry_run, patches=patches, after=lambda card: found.append(
                        (os.path.exists(os.path.join(card, "spruceV4.6.0.7z")),
                         (store.load_cards().get(os.path.basename(card)) or {}).get("spruce_os")))), 0)
                    self.assertEqual(found, [(False, None)] if dry_run else [(True, "spruceV4.6.0.7z")])
                    last = self.out.getvalue().strip().splitlines()[-1]
                    if dry_run:
                        self.assertNotIn("EZ Updater", self.out.getvalue())
                    else:  # the reminder is the sync's last line
                        self.assertIn("spruceV4.6.0.7z is on the card: run Apps → EZ Updater", last)
                    if games and not dry_run:  # staged after the card's other writes
                        self.assertGreater(order.index("os/spruceos/spruceV4.6.0.7z"), order.index("flush"))

    def test_spruce_sync_stages_boot_logos_for_the_cards_device(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        device = {**next(d for d in store.repo_json("devices") if d["id"] == "miyoo-a30"), "systems": [SYSTEM["bucket"]], "note": ""}
        manifest = {**MANIFEST, "layouts": layouts, "devices": [device],
                    "systems": [{**SYSTEM, "folders": {"spruce": "GBA"}}]}
        touch(os.path.join(store.data_dir(), "bootlogos", "640x480", "K.png"), b"k")
        patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (device, "spruce")}))
        found = []
        code = self.run_sync(False, patches=patches,
                             prepare=lambda card: os.makedirs(os.path.join(card, "App", "BootLogo", "Imgs")),
                             after=lambda card: found.append(os.path.isfile(os.path.join(card, "App", "BootLogo", "Imgs", "K.png"))))
        self.assertEqual((code, found), (0, [True]))

    def test_spruce_sync_hides_fbneo_bios_zips_and_clears_the_old_folder(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        fbneo = {**SYSTEM, "name": "FinalBurn Neo", "bucket": "fbneo", "folders": {"spruce": "ARCADE"},
                 "bios": {"files": [], "rom_files": ["fbneo/pgm.zip"]}, "games": [{"bucket": "fbneo/b.zip"}]}
        listed = {"fbneo/": {"fbneo/b.zip": 1}, "BIOS/": {"BIOS/fbneo/pgm.zip": 1}}
        files = inventory.files

        def fake_files(prefix, sizes=True):
            return listed[prefix] if prefix in listed else files(prefix, sizes)

        def download(job, *a):
            touch(job[1])

        config = {"ignoreList": ["neogeo.zip"]}

        def prepare(card):
            touch(os.path.join(card, "Emu", "ARCADE", "config.json"), json.dumps(config, indent=2) + "\n")
            touch(os.path.join(card, "Roms", "FBNEO", "old.zip"))

        manifest = {**MANIFEST, "layouts": layouts, "systems": [fbneo]}
        patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "spruce")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.ui, {"choose": lambda *a, **k: "y"}),
                   (inventory, {"files": fake_files, "stat": lambda keys: {k: 1 for k in keys}}),
                   (cli.downloads, {"run_downloads": downloads.run_downloads}),
                   (cli.s3, {"download": download}))
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                found = {}

                def after(card):
                    arcade = os.path.join(card, "Roms", "ARCADE")
                    found["roms"] = sorted(os.listdir(arcade)) if os.path.isdir(arcade) else []
                    found["old"] = os.path.exists(os.path.join(card, "Roms", "FBNEO", "old.zip"))
                    with open(os.path.join(card, "Emu", "ARCADE", "config.json")) as f:
                        found["config"] = json.load(f)
                    found["owned"] = (store.load_cards().get(os.path.basename(card)) or {}).get("spruce_emu")
                self.assertEqual(self.run_sync(dry_run, prepare=prepare, patches=patches, after=after), 0)
                if dry_run:
                    self.assertEqual(found["config"], config)
                    self.assertTrue(found["old"])
                    self.assertIn("Emu/ARCADE/config.json", self.out.getvalue())
                    self.assertIn("would delete", self.out.getvalue())
                else:
                    self.assertEqual(found["roms"], ["b.zip", "pgm.zip"])
                    self.assertFalse(found["old"])
                    self.assertEqual(found["config"]["ignoreList"], ["neogeo.zip", "pgm.zip"])
                    self.assertEqual(found["owned"], {"ARCADE": ["pgm.zip"]})

    def test_onion_card_with_nothing_to_sync_removes_a_stale_surprise_list(self):
        layouts = {"onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        manifest = {**MANIFEST, "layouts": layouts, "systems": [{**SYSTEM, "games": [], "folders": {"onion": "GBA"}}]}
        patches = ((store, {"load_manifest": lambda names=(): manifest, "load_cards": REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (None, "onion")}))
        for fields in ({"surprise": False, "surprises": [{"system": "gba", "bucket": "gba/Game.zip", "title": "G"}]},
                       {"surprises": []}):
            with self.subTest(fields=fields):
                def prepare(card):
                    os.makedirs(os.path.join(card, "Roms"))
                    open(os.path.join(card, "Roms", "surprise.json"), "w").close()
                    store.update_card(os.path.basename(card), **fields)
                found = []
                self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches, after=lambda card: found.append(
                    os.path.exists(os.path.join(card, "Roms", "surprise.json")))), 0)
                self.assertIn("has nothing to sync", self.out.getvalue())
                self.assertEqual(found, [False])

    def test_a_card_with_nothing_to_sync_exits_1_however_many_installs_failed(self):
        manifest = {**MANIFEST, "systems": [{**SYSTEM, "games": []}]}
        patches = ((store, {"load_manifest": lambda names=(): manifest}),
                   (cli.pico8, {"run": lambda *a, **k: 1}),
                   (cli.onion_surprise, {"install": lambda *a, **k: 1}),
                   (cli.raofflineproxy, {"install": lambda *a, **k: 1}))
        self.assertEqual(self.run_sync(False, patches=patches), 1)
        self.assertIn("has nothing to sync", self.out.getvalue())

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
        def run_downloads(todo, label, icon, base, failures=None, *a):
            failures.extend((j[0], "boom") for j in todo)
            return len(todo)
        patches = ((cli, {"free_space": lambda path: 10**9}), (cli.downloads, {"run_downloads": run_downloads}))
        self.assertEqual(self.run_sync(False, patches=patches), 1)
        self.assertRegex(self.err.getvalue().splitlines()[-1], r"^⚠️  Done with 1 failure\(s\): downloaded 0 file\(s\) \(0 B\) in \d+m\d\ds$")

    def test_a_settings_file_that_cannot_be_written_is_a_failure_and_the_card_is_not_ejected(self):
        def fail():
            if not calls:
                calls.append(1)
                raise OSError("disk full")  # the end of the sync; the exit of caching() finds nothing left
        calls = []

        class Settings(dict):
            asked = []

            def get(self, key, default=None):
                self.asked.append(key)
                return default
        patches = ((cli.cardfs, {"flush": fail}), (usersettings, {"load_settings": Settings}))
        self.assertEqual(self.run_sync(False, patches=patches), 1)
        self.assertRegex(self.out.getvalue().splitlines()[-1] + self.err.getvalue(), r"Done with 1 failure")
        self.assertIn("disk full", self.err.getvalue() + self.out.getvalue())
        self.assertNotIn("eject", Settings.asked)  # eject is only considered when nothing failed
        Settings.asked.clear()
        self.assertEqual(self.run_sync(False, patches=((usersettings, {"load_settings": Settings}),)), 0)
        self.assertIn("eject", Settings.asked)

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
                   (cli.vita, {"add_psvita_files": lambda dests, wrote=None: []}),
                   (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "y",
                             "confirm": lambda q, default=True: asked.append(q) or True}))
        self.assertEqual(self.run_sync(False, prepare=prepare, patches=patches), 0)
        self.assertEqual(sorted(jobs), sorted([dlc, new]))
        self.assertTrue(any(q.startswith("Delete these 1") for q in asked), asked)


class ShownPathsTest(unittest.TestCase):
    """The card files a sync deletes are listed dimmed, 5 spaces in: the first few, then the rest counted."""

    def shown(self, call, count):
        with tempfile.TemporaryDirectory() as card:
            paths = [os.path.join(card, f"{i:02}.zip") for i in range(count)]
            for path in paths:
                open(path, "w").close()
            with mock.patch.object(cli.ui, "_COLOR", True), mock.patch.object(cli.ui, "choose", lambda *a: "n"), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                call(paths)
        dimmed = [line for line in out.getvalue().split("\n") if line.startswith("\x1b[2m")]
        return dimmed[:-1], dimmed[-1], [f"\x1b[2m     {p}\x1b[0m" for p in paths]

    def test_unwanted_roms_show_the_first_ten(self):
        head, last, lines = self.shown(cli.delete_extras, 12)
        self.assertEqual((head, last), (lines[:10], "\x1b[2m     … and 2 more\x1b[0m"))
        head, last, lines = self.shown(cli.delete_extras, 10)
        self.assertEqual(head + [last], lines)

    def test_stale_media_show_the_first_five(self):
        head, last, lines = self.shown(cli.remove_stale_media, 7)
        self.assertEqual((head, last), (lines[:5], "\x1b[2m     … and 2 more\x1b[0m"))
        head, last, lines = self.shown(cli.remove_stale_media, 5)
        self.assertEqual(head + [last], lines)


class BiosFoldersTest(unittest.TestCase):
    def test_flat_layout(self):
        self.assertEqual(downloads.bios_folders({"folders": {"esde": "gba"}}, "esde", {}, "BIOS"), ["BIOS"])

    def test_nextui_tag_and_extra_tags(self):
        gba = {"folders": {"nextui": "Game Boy Advance (GBA)"}, "nextui_bios_tags": ["MGBA"]}
        self.assertEqual(downloads.bios_folders(gba, "nextui", {"bios_by_tag": True}, "Bios"),
                         [os.path.join("Bios", "GBA"), os.path.join("Bios", "MGBA")])

    def test_nextui_system_without_tag(self):
        self.assertEqual(downloads.bios_folders({"folders": {"nextui": None}}, "nextui", {"bios_by_tag": True}, "Bios"), [])


if __name__ == "__main__":
    unittest.main()
