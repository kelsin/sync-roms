import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import MANIFEST, SYSTEM, CardDir, DataDir, touch  # noqa: E402  (imports isolate first)
import test_cli_sync  # noqa: E402
from unittest import mock  # noqa: E402
from sync_roms import cli, portmaster, portmaster_catalog, scrape_plan, store  # noqa: E402

PORTS = {"name": "Ports", "bucket": "ports", "folders": {"spruce": "PORTS", "knulli": "ports"}, "bios": {"files": []}, "games": []}
PORTMASTER_DEVICES = {
    "anbernic-rg-cubexx", "anbernic-rg-sp", "anbernic-rg-28xx", "anbernic-rg-34xx", "anbernic-rg-34xxsp",
    "anbernic-rg-35xx-2024", "anbernic-rg-35xxh", "anbernic-rg-35xx-plus", "anbernic-rg-35xx-pro", "anbernic-rg-35xxsp",
    "anbernic-rg-40xxh", "anbernic-rg-40xxv", "magicx-zero40", "miyoo-flip", "trimui-brick", "trimui-brick-hammer",
    "trimui-brick-pro", "trimui-smart-pro", "trimui-smart-pro-s"}
FILES = ["PORTS/Celeste.sh", "PORTS/celeste/port.json", "PORTS/Imgs/Celeste.png", "PORTS/autoinstall/x.txt"]


def device_of(device_id):
    return {**next(d for d in store.repo_json("devices") if d["id"] == device_id), "systems": [SYSTEM["bucket"]], "note": ""}


class PortsAppliesTest(unittest.TestCase):
    def test_ports_applies_only_on_portmaster_spruce_devices(self):
        rg, a30 = device_of("anbernic-rg-35xxh"), device_of("miyoo-a30")
        self.assertEqual([store.system_applies(PORTS, rg, "spruce"), store.system_applies(PORTS, a30, "spruce"),
                          store.system_applies(PORTS, rg, "knulli"), store.system_applies(PORTS, None, "spruce")],
                         [True, False, False, False])
        self.assertTrue(portmaster.owns_folder(PORTS))

    def test_devices_flag_portmaster_on_64bit_spruce_devices(self):
        self.assertEqual({d["id"] for d in store.repo_json("devices") if d.get("portmaster")}, PORTMASTER_DEVICES)

    def test_stale_media_keeps_ports_imgs(self):
        with tempfile.TemporaryDirectory() as base:
            roms = os.path.join(base, "Roms")
            for rel in FILES:
                touch(os.path.join(roms, rel))
            self.assertEqual(scrape_plan.stale_media("spruce", [PORTS], roms, None, base), [])
            self.assertEqual(scrape_plan.prune_empty_systems("spruce", [PORTS], roms), [])
            self.assertTrue(all(os.path.exists(os.path.join(roms, rel)) for rel in FILES))


class PortsSyncTest(DataDir):
    run_sync = test_cli_sync.SyncSmokeTest.run_sync

    def test_sync_never_sweeps_ports_folder(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        for device_id in ("miyoo-mini", "anbernic-rg-35xxh"):
            with self.subTest(device=device_id):
                device = device_of(device_id)
                manifest = {**MANIFEST, "layouts": layouts, "devices": [device],
                            "systems": [{**SYSTEM, "folders": {"spruce": "GBA"}}, PORTS]}
                patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": test_cli_sync.REAL_LOAD_CARDS}),
                           (cli.picker, {"saved_setup": lambda *a, d=device: (d, "spruce")}),
                           (cli, {"free_space": lambda path: 10**9}),
                           (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
                asked, found = [], {}
                code = self.run_sync(False, patches=patches,
                                     prepare=lambda card: [touch(os.path.join(card, "Roms", rel)) for rel in FILES],
                                     after=lambda card: found.update({rel: os.path.exists(os.path.join(card, "Roms", rel)) for rel in FILES}))
                self.assertEqual(code, 0)
                self.assertEqual(found, {rel: True for rel in FILES})
                self.assertEqual([q for q in asked if q.startswith("Delete these")], [])


ZIP, MONO = "celeste.zip", "mono-6.12.0.122-aarch64.squashfs"
FACTS = {"folder": "celeste", "items": ["Celeste.sh", "celeste"], "rtr": False, "inst": "", "runtime": [MONO],
         "md5": "x", "size": 3}


class StageTest(CardDir):
    FIELD = "portmaster_staged"

    def setUp(self):
        super().setUp()
        store.update_card("c", layout="spruce")
        self.device = device_of("anbernic-rg-35xxh")
        self.put("ports/" + ZIP, b"zip")
        self.put(portmaster.RUNTIMES + MONO, b"mono!")
        self.put("scrapes/ports/metadata.json", json.dumps({ZIP: {"name": "Celeste", "portmaster": FACTS}}).encode())
        os.makedirs(self.cp(portmaster.LIBS))

    def stage(self, picked=(ZIP,), dry_run=False, keep=False):
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()) as err:
            self.result = portmaster.stage("c", self.device, "spruce", self.card, list(picked), dry_run, keep)
        self.err = err.getvalue()
        return out.getvalue()

    def waiting(self):
        path = self.cp(portmaster.AUTOINSTALL)
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    def test_stage_copies_zip_and_runtime_to_autoinstall(self):
        out = self.stage()
        self.assertEqual(self.result, (0, ["Celeste"]))
        self.assertEqual(self.waiting(), [ZIP, MONO])
        with open(self.cp(portmaster.AUTOINSTALL, MONO), "rb") as f:
            self.assertEqual(f.read(), b"mono!")
        self.assertEqual(self.recorded(), [ZIP, MONO])
        self.assertIn("🧩 Open PortMaster on the device to install: Celeste", out)

    def test_stage_skips_installed_port_by_port_json_name(self):
        touch(self.cp(portmaster.CARD_PORTS, "anything", "port.json"), json.dumps({"name": "Celeste.ZIP", "attr": {}}))
        out = self.stage()
        self.assertEqual((self.result, self.waiting(), self.recorded()), ((0, []), [], None))
        self.assertNotIn("Open PortMaster", out)

    def test_stage_skips_installed_port_by_items(self):
        touch(self.cp(portmaster.CARD_PORTS, "celeste.sh"))
        touch(self.cp(portmaster.CARD_PORTS, "Celeste", "x"))
        self.stage()
        self.assertEqual((self.result, self.waiting()), ((0, []), []))

    def test_stage_skips_runtime_in_libs(self):
        touch(self.cp(portmaster.LIBS, MONO))
        self.stage()
        self.assertEqual(self.waiting(), [ZIP])
        self.assertEqual(self.recorded(), [ZIP])

    def test_stage_warns_about_a_runtime_storage_lacks(self):
        os.remove(os.path.join(self.root, portmaster.RUNTIMES, MONO))
        self.stage()
        self.assertEqual(self.waiting(), [ZIP])
        self.assertIn(f"run sync-roms ports download {ZIP}", self.err)

    def test_stage_warns_about_a_pick_without_facts(self):
        self.put("scrapes/ports/metadata.json", b"{}")
        self.stage()
        self.assertEqual((self.result, self.waiting()), ((1, []), []))
        self.assertIn(f"run sync-roms ports download --update {ZIP}", self.err)

    def test_stage_without_control_folder_notes_and_writes_nothing(self):
        os.rmdir(self.cp(portmaster.LIBS))
        os.rmdir(self.cp(portmaster.CONTROL))
        out = self.stage()
        self.assertIn("🧩 Boot the device once so spruceOS sets up PortMaster, then sync again", out)
        self.assertFalse(os.path.exists(self.cp(portmaster.CONTROL)))
        self.assertIsNone(self.recorded())

    def test_stage_removes_unpicked_staged_zip_unless_keep(self):
        self.stage()
        self.stage(picked=(), keep=True)
        self.assertEqual(self.waiting(), [ZIP, MONO])
        self.assertEqual(self.recorded(), [ZIP, MONO])
        self.stage(picked=())
        self.assertEqual(self.waiting(), [MONO])  # a runtime is harmless: PortMaster installs it
        self.assertEqual(self.recorded(), [MONO])

    def test_stage_leaves_files_it_did_not_stage(self):
        touch(self.cp(portmaster.AUTOINSTALL, "mine.zip"))
        self.stage(picked=())
        self.assertEqual(self.waiting(), ["mine.zip"])

    def test_staged_field_drops_files_portmaster_installed(self):
        self.stage()
        for name in (ZIP, MONO):  # PortMaster installed them
            os.remove(self.cp(portmaster.AUTOINSTALL, name))
        touch(self.cp(portmaster.CARD_PORTS, "celeste", "port.json"), json.dumps({"name": ZIP, "attr": {}}))
        touch(self.cp(portmaster.LIBS, MONO))
        self.stage()
        self.assertEqual((self.result, self.waiting(), self.recorded()), ((0, []), [], None))

    def test_malformed_port_json_warns_and_continues(self):
        bad = self.cp(portmaster.CARD_PORTS, "bad", "port.json")
        touch(bad, "{nope")
        touch(self.cp(portmaster.CARD_PORTS, "odd", "port.json"), json.dumps({"name": "x.zip"}))
        touch(self.cp(portmaster.CARD_PORTS, "good", "port.json"), json.dumps({"name": "g.zip", "attr": {"title": "G"}}))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(list(portmaster.installed(self.card)), ["good"])
        self.assertIn(bad, err.getvalue())
        self.assertIn(os.path.join("odd", "port.json"), err.getvalue())
        self.stage()
        self.assertEqual(self.waiting(), [ZIP, MONO])

    def test_dry_run_stages_nothing(self):
        self.stage()
        os.remove(self.cp(portmaster.AUTOINSTALL, MONO))
        out = self.stage(picked=(), dry_run=True)
        self.assertIn(f"🧪 Dry run: would delete the staged ports no longer picked: {ZIP}", out)
        self.assertEqual((self.waiting(), self.recorded()), ([ZIP], [ZIP, MONO]))
        os.remove(self.cp(portmaster.AUTOINSTALL, ZIP))
        out = self.stage(dry_run=True)
        self.assertIn(f"🧪 Dry run: would stage {ZIP}", out)
        self.assertIn(f"🧪 Dry run: would stage {MONO}", out)
        self.assertEqual(self.result, (0, ["Celeste"]))
        self.assertEqual((self.waiting(), self.recorded()), ([], [ZIP, MONO]))

    def test_other_cards_get_nothing(self):
        for device, layout in ((device_of("miyoo-a30"), "spruce"), (self.device, "knulli"), (None, "spruce")):
            self.assertEqual(portmaster.stage("c", device, layout, self.card, [ZIP], False, False), (0, []))
        self.assertEqual(self.waiting(), [])

    def test_pick_without_facts_keeps_what_was_staged_for_it(self):
        self.stage()
        self.put("scrapes/ports/metadata.json", b"{}")
        self.stage()
        self.assertEqual((self.result, self.waiting(), self.recorded()), ((1, []), [ZIP, MONO], [ZIP, MONO]))

    def test_pick_missing_from_storage_keeps_what_was_staged_for_it(self):
        self.stage()
        os.remove(os.path.join(self.root, "ports", ZIP))
        out = self.stage()
        self.assertEqual((self.result, self.waiting(), self.recorded()), ((1, []), [ZIP, MONO], [ZIP, MONO]))
        self.assertIn(f"ports/{ZIP} isn't in storage", self.err)
        self.assertNotIn("Open PortMaster", out)


class PortsStageSyncTest(DataDir):
    run_sync = test_cli_sync.SyncSmokeTest.run_sync

    def sync(self, args=()):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        device = {**device_of("anbernic-rg-35xxh"), "systems": [SYSTEM["bucket"], "ports"]}
        ports = {**PORTS, "games": [{"bucket": "ports/" + ZIP}]}
        manifest = {**MANIFEST, "layouts": layouts, "devices": [device],
                    "systems": [{**SYSTEM, "folders": {"spruce": "GBA"}}, ports]}
        jobs, staged = [], []

        def list_sizes(prefix, sizes=True):
            return {"gba/Game.zip": 5} if prefix == "gba/" else {"ports/" + ZIP: 3} if prefix == "ports/" else {}

        patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": test_cli_sync.REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (device, "spruce")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.s3, {"list_sizes": list_sizes}),
                   (cli.downloads, {"run_downloads": lambda todo, *a, **k: jobs.extend(todo) or 0}),
                   (cli.portmaster, {"stage": lambda *a: staged.append(a) or (0, []), "pending": lambda *a: {}}))
        for dry_run in (False, True):
            self.assertEqual(self.run_sync(dry_run, patches=patches, args=args), 0)
        return jobs, staged

    def test_sync_never_copies_port_zips_into_roms_ports(self):
        jobs, staged = self.sync()
        self.assertIn("gba/Game.zip", [j[0] for j in jobs])
        self.assertNotIn("ports/" + ZIP, [j[0] for j in jobs])
        self.assertEqual([(a[4], a[5]) for a in staged], [([ZIP], False), ([ZIP], True)])

    def test_guest_sync_skips_portmaster(self):
        jobs, staged = self.sync(("--guest",))
        self.assertEqual(staged, [])
        self.assertNotIn("ports/" + ZIP, [j[0] for j in jobs])


UT = "undertale"
UT_INST = "Copy the contents of your Steam or GOG installation to ports/undertale/assets."
GAMEDATA = "os/portmaster/gamedata/"


class GameDataTest(CardDir):
    FIELD = "portmaster_data"

    def setUp(self):
        super().setUp()
        store.update_card("c", layout="spruce")
        self.install(UT, {"name": "undertale.zip", "attr": {"title": "Undertale", "rtr": False, "inst": UT_INST}})

    def install(self, folder, port):
        touch(self.cp(portmaster.CARD_PORTS, folder, "port.json"), json.dumps(port))

    def run_data(self, picked=None, dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.result = portmaster.game_data("c", self.card, portmaster.installed(self.card), picked or {}, dry_run)
            portmaster.summary("c", self.result[1])
        return out.getvalue()

    def needed_file(self):
        path = os.path.join(self.data, "ports-needed.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_copy_never_overwrites_and_records_portmaster_data(self):
        self.put(GAMEDATA + "undertale/assets/data.win", b"data")
        self.put(GAMEDATA + "undertale/assets/mus.ogg", b"theirs")
        touch(self.cp(portmaster.CARD_PORTS, UT, "assets", "mus.ogg"), "mine")
        out = self.run_data()
        self.assertEqual(self.result, (0, []))
        with open(self.cp(portmaster.CARD_PORTS, UT, "assets", "data.win"), "rb") as f:
            self.assertEqual(f.read(), b"data")
        with open(self.cp(portmaster.CARD_PORTS, UT, "assets", "mus.ogg")) as f:
            self.assertEqual(f.read(), "mine")
        self.assertEqual(self.recorded(), [UT])
        self.assertEqual(store.load_cards()["c"]["portmaster_ports"], [UT])
        self.assertNotIn("waiting for game data", out)
        self.assertIsNone(self.needed_file())

    def test_copied_port_is_not_copied_again_when_folder_empty(self):
        self.put(GAMEDATA + "undertale/assets/data.win", b"data")
        self.run_data()
        shutil.rmtree(self.cp(portmaster.CARD_PORTS, UT, "assets"))
        out = self.run_data()
        self.assertFalse(os.path.exists(self.cp(portmaster.CARD_PORTS, UT, "assets")))
        self.assertEqual((self.result, self.recorded()), ((0, []), [UT]))
        self.assertNotIn("waiting for game data", out)

    def test_waiting_port_added_to_needed_file_and_summary_printed(self):
        picked = {ZIP: {"name": "Celeste", "portmaster": {**FACTS, "inst": 'Copy the game\'s data into "celeste/gamedata".'}}}
        out = self.run_data(picked)
        self.assertEqual(self.result[0], 0)
        self.assertEqual([(f, later) for f, _, later in self.result[1]], [(UT, False), ("celeste", True)])
        self.assertEqual(self.needed_file(), {
            UT: {"title": "Undertale", "zip": "undertale.zip", "inst": UT_INST,
                 "folder": GAMEDATA + "undertale/assets/", "cards": ["c"]},
            "celeste": {"title": "Celeste", "zip": ZIP, "inst": 'Copy the game\'s data into "celeste/gamedata".',
                        "folder": GAMEDATA + "celeste/gamedata/", "cards": ["c"]}})
        self.assertIsNone(self.recorded())
        self.assertEqual(store.load_cards()["c"]["portmaster_ports"], [UT])
        self.assertIn("🧩 Ports waiting for game data\n"
                      "Celeste (after PortMaster installs it)\n"
                      "    Copy the game's data into \"celeste/gamedata\".\n"
                      f"    Put the files in {self.root}/{GAMEDATA}celeste/gamedata/\n"
                      "Undertale\n"
                      f"    {UT_INST}\n"
                      f"    Put the files in {self.root}/{GAMEDATA}undertale/assets/\n"
                      "Already on the card? sync-roms ports done c <folder>\n"
                      "All of them: sync-roms ports needed\n", out)
        # storage gets Undertale's data: the next sync copies it and drops it from the needed list
        self.put(GAMEDATA + "undertale/assets/data.win", b"data")
        out = self.run_data(picked)
        self.assertEqual(list(self.needed_file()), ["celeste"])
        self.assertEqual(self.recorded(), [UT])
        self.assertIn("Already on the card? sync-roms ports done c celeste\n", out)

    def test_rtr_true_port_never_listed(self):
        self.install(UT, {"name": "undertale.zip", "attr": {"title": "Undertale", "rtr": True, "inst": UT_INST}})
        picked = {ZIP: {"name": "Celeste", "portmaster": {**FACTS, "rtr": True}}}
        out = self.run_data(picked)
        self.assertEqual(self.result, (0, []))
        self.assertEqual(out, "")
        self.assertIsNone(self.needed_file())
        self.assertNotIn("portmaster_ports", store.load_cards()["c"])

    def test_failed_copy_retried_next_sync(self):
        self.put(GAMEDATA + "undertale/assets/data.win", b"data")

        def fail(todo, label, icon, base, failures):
            failures.extend((j[0], "boom") for j in todo)
            return len(todo)

        with mock.patch.object(portmaster.downloads, "run_downloads", fail):
            self.run_data()
        self.assertEqual((self.result, self.recorded()), ((1, []), None))
        self.run_data()
        self.assertEqual((self.result, self.recorded()), ((0, []), [UT]))
        self.assertTrue(os.path.exists(self.cp(portmaster.CARD_PORTS, UT, "assets", "data.win")))

    def test_dry_run_writes_no_needed_file_and_copies_nothing(self):
        self.install("celeste", {"name": ZIP, "attr": {"title": "Celeste", "rtr": False, "inst": ""}})
        self.put(GAMEDATA + "celeste/Content/a.xnb", b"abc")
        out = self.run_data(dry_run=True)
        self.assertIn("🧪 Dry run: would copy 1 game data file(s) (3 B) for Celeste", out)
        self.assertIn("🧩 Ports waiting for game data\nUndertale\n", out)
        self.assertEqual([f for f, _, _ in self.result[1]], [UT])
        self.assertFalse(os.path.exists(self.cp(portmaster.CARD_PORTS, "celeste", "Content")))
        self.assertIsNone(self.needed_file())
        self.assertEqual(store.load_cards()["c"], {"layout": "spruce"})

    def test_updates_note_uses_cached_catalogue_only(self):
        self.install("celeste", {"name": ZIP, "attr": {"title": "Celeste"}, "status": {"md5": "same"}})
        self.install(UT, {"name": "undertale.zip", "attr": {"title": "Undertale"}, "status": {"md5": "old"}})
        catalog = {"ports": {ZIP: {"source": {"md5": "same"}}, "undertale.zip": {"source": {"md5": "new"}}}}
        touch(portmaster_catalog.path(), json.dumps(catalog))
        out = io.StringIO()
        with mock.patch.object(portmaster_catalog.github, "get", side_effect=AssertionError("fetched")), \
                contextlib.redirect_stdout(out):
            portmaster.updates(self.card, portmaster.installed(self.card))
            os.remove(portmaster_catalog.path())
            portmaster.updates(self.card, portmaster.installed(self.card))
        self.assertEqual(out.getvalue(), "🧩 Updates available in PortMaster on the device: Undertale\n")


class PortsOnlySyncTest(DataDir):
    run_sync = test_cli_sync.SyncSmokeTest.run_sync

    def test_card_with_only_ports_picked_is_not_told_it_has_nothing(self):
        layouts = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"}}
        device = {**device_of("anbernic-rg-35xxh"), "systems": ["ports"]}
        manifest = {**MANIFEST, "layouts": layouts, "devices": [device],
                    "systems": [{**PORTS, "games": [{"bucket": "ports/" + ZIP}]}]}
        waiting = [("celeste", {"title": "Celeste", "inst": "", "folder": GAMEDATA + "celeste/"}, True)]
        patches = ((store, {"load_manifest": lambda names=(), m=manifest: m, "load_cards": test_cli_sync.REAL_LOAD_CARDS}),
                   (cli.picker, {"saved_setup": lambda *a: (device, "spruce")}),
                   (cli, {"free_space": lambda path: 10**9}),
                   (cli.s3, {"list_sizes": lambda prefix, sizes=True: {"ports/" + ZIP: 3} if prefix == "ports/" else {}}),
                   (cli.portmaster, {"stage": lambda *a: print("🧩 Open PortMaster on the device to install: Celeste") or (0, ["Celeste"]),
                                     "pending": lambda *a: {}, "game_data": lambda *a: (0, waiting)}))
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                self.assertEqual(self.run_sync(dry_run, patches=patches), 0)
                out = self.out.getvalue()
                self.assertIn("Open PortMaster on the device to install: Celeste", out)
                self.assertNotIn("has nothing to sync", out)
                self.assertIn("🧩 Ports waiting for game data\nCeleste (after PortMaster installs it)\n", out)
