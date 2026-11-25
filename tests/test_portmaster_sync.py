import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import MANIFEST, SYSTEM, DataDir, touch  # noqa: E402  (imports isolate first)
import test_cli_sync  # noqa: E402
from sync_roms import cli, portmaster, scrape_plan, store  # noqa: E402

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
