import copy
import os
import tempfile
import unittest
from unittest import mock

import helpers  # noqa: F401  (imports isolate first)
import test_cli_sync
from helpers import DataDir, touch
from sync_roms import cli, s3, store, ui

GBA = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba", "spruce": "GBA"},
       "bios": {"files": ["gba_bios.bin"]}, "games": []}
NES = {"name": "Nintendo", "bucket": "nes", "folders": {"esde": "nes", "spruce": "FC"}, "bios": {"files": []}, "games": []}
PSX = {"name": "PlayStation", "bucket": "psx", "folders": {"onion": "PS"}, "bios": {"files": []}, "games": []}
DISCS = ["psx/Game (Disc 1).chd", "psx/Game (Disc 2).chd"]
LAYOUTS = {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"},
           "onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS", "disc_dir": ".multi-disc"},
           "spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
STORAGE = {"gba/Game.zip": 5, "nes/X.zip": 3, "BIOS/gba_bios.bin": 3, "scrapes/gba/covers/Game.png": 4,
           DISCS[0]: 5, DISCS[1]: 5, "psx/Game.m3u": 30}
CARD = "friend"


def pick(games):
    """A cards.json games value, as the card editor writes it."""
    return {b: [{"bucket": k, "title": store.key_title(k)} for k in keys] for b, keys in games.items()}


def load_manifest(names=(), keep_off=False):
    """The test systems with the card's games as saved in cards.json (its systems_off emptied, as the real one does)."""
    entry = store.saved_card(names[0]) if names else {}
    games, off = entry.get("games") or {}, store.systems_off(entry)
    systems = copy.deepcopy([GBA, NES, PSX])
    for s in systems:
        s["games"] = [] if s["bucket"] in off else [g for g in games.get(s["bucket"], []) if isinstance(g, dict)]
    return {"systems": systems, "devices": [], "layouts": LAYOUTS}


def list_sizes(prefix, sizes=True):
    return {k: v for k, v in STORAGE.items() if k.startswith(prefix)}


def stat_sizes(keys):
    return {k: STORAGE[k] for k in keys if k in STORAGE}


class GuestSyncTest(DataDir):
    run_sync = test_cli_sync.SyncSmokeTest.run_sync

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = os.path.join(tmp.name, CARD)
        os.makedirs(self.base)
        self.jobs = []

    def card_file(self, rel, data=b"x" * 5):
        path = os.path.join(self.base, rel)
        touch(path, data)
        return path

    def save(self, **entry):
        store.write_cards({CARD: {"device": "full", "layout": "esde", **entry}})

    def saved(self):
        return store.saved_card(CARD)

    def picks(self):
        """{system: [bucket keys]} of the card's saved games."""
        return {b: [g["bucket"] for g in games] for b, games in self.saved()["games"].items()}

    def sync(self, dry_run=False, layout="esde", patches=(), yes=True, args=(), editor=None):
        def run_downloads(todo, *a, **k):
            self.jobs.extend(todo)
            return 0
        base = ((store, {"load_manifest": load_manifest, "load_cards": test_cli_sync.REAL_LOAD_CARDS}),
                (s3, {"list_sizes": list_sizes, "stat_sizes": stat_sizes}),
                (cli.picker, {"saved_setup": lambda *a: (None, layout)}),
                (cli.downloads, {"run_downloads": run_downloads}))
        if editor:
            base += ((cli.cardedit, {"edit_card": editor}), (ui, {"has_terminal": lambda: True}),
                     (ui, {"confirm": lambda *a, **k: True, "choose": lambda *a, **k: "y"}))
        code = self.run_sync(dry_run, patches=base + tuple(patches), yes=yes, args=args, card_dir=self.base)
        self.assertEqual(code, 0, self.out.getvalue() + self.err.getvalue())
        return code

    def job_keys(self):
        return sorted(k for k, _, _ in self.jobs)

    def test_guest_flag_saves_guest_on_the_card(self):
        self.save()
        self.sync(dry_run=True, args=["--guest"])
        self.assertNotIn("guest", self.saved())
        self.sync(args=["--guest"])
        self.assertIs(self.saved()["guest"], True)

    def test_guest_sync_seeds_picks_from_the_card(self):
        self.save(guest=True, games=pick({"nes": ["nes/X.zip"]}), excluded={"gba": ["gba/A.zip"]}, systems_off=["gba"])
        self.card_file("ROMs/gba/Game.zip")
        self.card_file("ROMs/gba/Mine.zip")
        self.sync()
        self.assertEqual(self.picks(), {"gba": ["gba/Game.zip"]})
        self.assertNotIn("excluded", self.saved())
        self.assertNotIn("systems_off", self.saved())

    def test_a_guest_dry_run_plans_from_the_seed_and_saves_nothing(self):
        self.save(guest=True, games=pick({"nes": ["nes/X.zip"]}))
        self.card_file("ROMs/gba/Game.zip")
        self.sync(dry_run=True)
        self.assertEqual(self.picks(), {"nes": ["nes/X.zip"]})
        self.assertNotIn("nes/X.zip", self.out.getvalue())
        self.assertIn("BIOS/gba_bios.bin", self.out.getvalue())

    def test_guest_sync_with_yes_deletes_nothing(self):
        self.save(guest=True)
        game, mine = self.card_file("ROMs/gba/Game.zip"), self.card_file("ROMs/gba/Mine.zip")
        cover = self.card_file("ES-DE/downloaded_media/gba/covers/Other.png")
        self.sync()
        for path in (game, mine, cover):
            self.assertTrue(os.path.exists(path), path)
        self.assertEqual(self.job_keys(), ["BIOS/gba_bios.bin"])  # the card's own ROMs get no scrapes

    def test_guest_sync_deletes_only_deselected_recognized_roms(self):
        self.save(guest=True)
        game, mine = self.card_file("ROMs/gba/Game.zip"), self.card_file("ROMs/gba/Mine.zip")
        cover = self.card_file("ES-DE/downloaded_media/gba/covers/Game.png", b"c" * 4)
        other = self.card_file("ES-DE/downloaded_media/gba/covers/Other.png")

        def editor(card, *a, **k):
            store.update_card(card, games={})
        self.sync(yes=False, editor=editor)
        self.assertFalse(os.path.exists(game))
        self.assertTrue(os.path.exists(mine))
        self.assertFalse(os.path.exists(cover))
        self.assertTrue(os.path.exists(other))

    def test_guest_sync_keeps_the_media_of_a_deselected_rom_kept_at_the_prompt(self):
        self.save(guest=True)
        game = self.card_file("ROMs/gba/Game.zip")
        cover = self.card_file("ES-DE/downloaded_media/gba/covers/Game.png", b"c" * 4)

        def editor(card, *a, **k):
            store.update_card(card, games={})
        self.sync(yes=False, editor=editor, patches=((ui, {"choose": lambda *a, **k: "n"}),))
        self.assertTrue(os.path.exists(game))
        self.assertTrue(os.path.exists(cover))

    def test_guest_sync_keeps_a_picture_another_rom_on_the_card_uses(self):
        self.save(guest=True)
        game = self.card_file("ROMs/gba/Game.zip")
        self.card_file("ROMs/gba/Game.gba")  # the friend's own, same stem
        cover = self.card_file("ES-DE/downloaded_media/gba/covers/Game.png", b"c" * 4)

        def editor(card, *a, **k):
            store.update_card(card, games={})
        self.sync(yes=False, editor=editor)
        self.assertFalse(os.path.exists(game))
        self.assertTrue(os.path.exists(cover))

    def test_x_skips_a_system(self):
        self.save(guest=True)
        game = self.card_file("ROMs/gba/Game.zip")

        def editor(card, *a, **k):
            store.update_card(card, games=pick({"nes": ["nes/X.zip"]}), systems_off=["gba"])  # nes: the sync goes on
        self.sync(yes=False, editor=editor)
        self.assertTrue(os.path.exists(game))
        self.assertFalse([k for k in self.job_keys() if k.startswith(("gba/", "scrapes/gba/"))])
        self.assertNotIn("BIOS/gba_bios.bin", self.job_keys())

    def test_guest_sync_leaves_a_same_named_file_of_another_size(self):
        self.save(guest=True)
        game = self.card_file("ROMs/gba/Game.zip", b"x")

        def editor(card, *a, **k):
            store.update_card(card, games=pick({"gba": ["gba/Game.zip"]}))  # picked on purpose: still never overwritten
        self.sync(yes=False, editor=editor)
        self.assertEqual(self.picks(), {"gba": ["gba/Game.zip"]})
        self.assertEqual(os.path.getsize(game), 1)
        self.assertNotIn("gba/Game.zip", self.job_keys())

    def test_guest_sync_does_not_redownload_a_differently_spelled_rom(self):
        """On a case-sensitive card the storage spelling isn't found by name; the seed's card path is used instead.
        The test folder may be case-insensitive (macOS), so cardfs gets a case-sensitive view of it."""
        self.save(guest=True)
        self.card_file("ROMs/gba/GAME.ZIP")
        listdir = os.listdir

        def lexists(path):
            folder, name = os.path.split(path)
            try:
                return name in listdir(folder or ".")
            except OSError:
                return False
        self.sync(patches=((cli.cardfs.os.path, {"lexists": lexists}),))
        self.assertEqual(self.picks(), {"gba": ["gba/Game.zip"]})
        self.assertNotIn("gba/Game.zip", self.job_keys())

    def test_guest_sync_never_overwrites_bios_or_media(self):
        self.save(guest=True)
        self.card_file("ROMs/gba/Game.zip")
        self.card_file("BIOS/gba_bios.bin", b"b")
        self.card_file("ES-DE/downloaded_media/gba/covers/Game.png", b"c")
        self.sync()
        self.assertEqual(self.job_keys(), [])

    def test_a_seeded_rom_storage_lost_since_is_reported_missing(self):
        self.save(guest=True)
        self.card_file("ROMs/gba/Game.zip")
        self.sync(patches=((cli.store, {"list_system": lambda s: {}}),))
        self.assertIn("gba/Game.zip", self.out.getvalue() + self.err.getvalue())
        self.assertNotIn("gba/Game.zip", self.job_keys())

    def test_guest_sync_leaves_loose_discs_where_they_are(self):
        self.save(guest=True, layout="onion")
        loose = [self.card_file(f"Roms/PS/{os.path.basename(k)}") for k in DISCS]

        def editor(card, *a, **k):
            store.update_card(card, games=pick({"psx": [*DISCS, "psx/Game.m3u"]}))
        self.sync(layout="onion", yes=False, editor=editor)
        for path in loose:
            self.assertTrue(os.path.exists(path), path)
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(path), ".multi-disc", os.path.basename(path))))

    def test_guest_sync_adds_a_new_pick(self):
        self.save(guest=True)

        def editor(card, *a, **k):
            store.update_card(card, games=pick({"nes": ["nes/X.zip"]}))
        self.sync(yes=False, editor=editor)
        self.assertIn("nes/X.zip", self.job_keys())

    def test_guest_sync_skips_settings_steps(self):
        self.save(guest=True, layout="spruce")
        self.card_file("Roms/GBA/Game.zip")
        skipped = {(cli.pico8, "run"): 0, (cli.onion_surprise, "install"): 0, (cli.raofflineproxy, "install"): 0,
                   (cli.spruce_settings, "install"): 0, (cli.spruce_wifi, "install"): 0, (cli.spruce_syncthing, "run"): 0,
                   (cli.spruce_os, "install"): 0, (cli.spruce_bootlogo, "install"): 0, (cli.spruce_fixes, "run"): False,
                   (cli.spruce_themes, "plan"): None, (cli.drivers, "for_device"): [], (cli.frontend, "plan_collections"): None,
                   (cli.spruce_collections, "plan"): None, (cli.onion_surprise, "write_list"): False,
                   (cli.surprise, "run_surprise"): [], (cli.surprise, "fill_surprises"): []}
        mocks = {key: mock.Mock(return_value=value) for key, value in skipped.items()}
        emu = mock.Mock(wraps=cli.spruce_emu.plan)
        patches = tuple((mod, {name: m}) for (mod, name), m in mocks.items()) + ((cli.spruce_emu, {"plan": emu}),)
        for dry_run in (True, False):
            self.sync(dry_run=dry_run, layout="spruce", patches=patches)
        for (mod, name), m in mocks.items():
            self.assertFalse(m.called, f"{mod.__name__}.{name}")
        self.assertEqual(emu.call_count, 2)

    def test_turning_guest_on_in_the_editor_reseeds(self):
        self.save(games=pick({"nes": ["nes/X.zip"]}))
        self.card_file("ROMs/gba/Game.zip")

        manifests = mock.Mock(wraps=load_manifest)

        def run_surprise(card, setup, chosen, interactive, dry_run, to_fetch=None, card_match=None, on_guest=None):
            store.update_card(card, guest=True)
            before = manifests.call_count
            on_guest()
            self.assertEqual(manifests.call_count, before, "reloaded while the editor is open")
            self.assertEqual(self.picks(), {"gba": ["gba/Game.zip"]})  # the editor shows the seed
            return []
        fill = mock.Mock(return_value=[])
        self.sync(patches=((store, {"load_manifest": manifests}),
                           (cli.surprise, {"run_surprise": run_surprise, "fill_surprises": fill})))
        self.assertEqual(self.picks(), {"gba": ["gba/Game.zip"]})
        self.assertFalse(fill.called)
        self.assertNotIn("nes/X.zip", self.job_keys())

    def test_turning_guest_off_mid_sync_keeps_this_run_guest(self):
        self.save(guest=True)
        mine = self.card_file("ROMs/gba/Mine.zip")
        sweep = mock.Mock(return_value=[])

        def editor(card, *a, **k):
            cards = store.load_cards()
            cards[card].pop("guest")
            store.write_cards(cards)
        self.sync(yes=False, editor=editor, patches=((cli.downloads, {"find_extras": sweep}),))
        self.assertFalse(sweep.called)
        self.assertTrue(os.path.exists(mine))


if __name__ == "__main__":
    unittest.main()
