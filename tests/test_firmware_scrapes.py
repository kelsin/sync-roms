import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "src", "sync_roms", "data")
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba",
       "folders": {"esde": "gba", "muos": "gba", "slot": "GBA"}, "muos_catalogue": "Nintendo Game Boy Advance"}
LISTING = {
    "scrapes/gba/covers/A.png": 5, "scrapes/gba/screenshots/A.jpg": 6, "scrapes/gba/3dboxes/A.png": 7,
    "scrapes/gba/slot/A.png": 8, "scrapes/gba/covers/hacks/B.png": 9, "scrapes/gba/slot/hacks/B.png": 3,
}
META = {"A.zip": {"name": "A", "desc": "An adventure."}}


def systems():
    with open(os.path.join(DATA, "systems.json")) as f:
        return json.load(f)


class DataTest(unittest.TestCase):
    def test_muos_systems_name_their_catalogue(self):
        for s in systems():
            self.assertEqual(bool(s["folders"]["muos"]), "muos_catalogue" in s, s["bucket"])


class MuosPlanTest(unittest.TestCase):
    def plan(self, rels, root, **kw):
        return cli.plan_scrapes("muos", rels, LISTING, kw.get("meta", META), root, "/card/ROMS/gba", lambda rom: True)

    def test_box_preview_and_text_go_in_the_catalogue(self):
        with tempfile.TemporaryDirectory() as root:
            jobs, entries, texts = self.plan(["A.zip"], root)
        self.assertEqual(sorted((k, os.path.relpath(p, root)) for k, p, _ in jobs), [
            ("scrapes/gba/covers/A.png", os.path.join("box", "A.png")),
            ("scrapes/gba/screenshots/A.jpg", os.path.join("preview", "A.jpg")),
        ])
        self.assertEqual(entries, {})  # muOS has no gamelist
        self.assertEqual([(os.path.relpath(p, root), t) for p, t in texts], [(os.path.join("text", "A.txt"), "An adventure.\n")])

    def test_rom_in_a_subfolder_gets_flat_catalogue_names(self):
        with tempfile.TemporaryDirectory() as root:
            jobs, _, _ = self.plan(["hacks/B.zip"], root)
        self.assertEqual([os.path.relpath(p, root) for _, p, _ in jobs], [os.path.join("box", "B.png")])

    def test_only_roms_on_the_card_are_planned(self):
        with tempfile.TemporaryDirectory() as root:
            jobs, _, texts = cli.plan_scrapes("muos", ["A.zip"], LISTING, META, root, "/x", lambda rom: False)
        self.assertEqual((jobs, texts), ([], []))

    def test_build_plan_uses_the_catalogue_folder_and_skips_unchanged_text(self):
        with tempfile.TemporaryDirectory() as base:
            data = {"gba": (LISTING, META)}
            args = ("muos", [GBA], data, {}, {}, {"gba": ["A.zip"]}, lambda s: "/x", os.path.join(base, "ES-DE"),
                    lambda p: True, base)
            plan = cli.build_scrape_plan(*args)
            catalogue = os.path.join(base, "MUOS", "info", "catalogue", "Nintendo Game Boy Advance")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             sorted([os.path.join(catalogue, "box", "A.png"), os.path.join(catalogue, "preview", "A.jpg")]))
            self.assertEqual(len(plan["writes"]), 1)
            cli.apply_scrape_plan({"jobs": [], "extras": [], "gamelists": {}, "writes": plan["writes"]}, base)
            self.assertEqual(cli.build_scrape_plan(*args)["writes"], [])


class SlotPlanTest(unittest.TestCase):
    def test_label_goes_in_labels_named_after_the_rom(self):
        with tempfile.TemporaryDirectory() as root:
            jobs, entries, texts = cli.plan_scrapes("slot", ["A.zip", "hacks/B.zip", "C.zip"], LISTING, META, root,
                                                    "/x", lambda rom: True)
        self.assertEqual(sorted((k, os.path.relpath(p, root)) for k, p, _ in jobs),
                         [("scrapes/gba/slot/A.png", "A.png"), ("scrapes/gba/slot/hacks/B.png", "B.png")])
        self.assertEqual((entries, texts), ({}, []))

    def test_a_subfolder_rom_is_found_flat_on_the_card(self):
        with tempfile.TemporaryDirectory() as base:
            card = os.path.join(base, "Games", "GBA")
            data = {"gba": (LISTING, META)}
            asked = []
            plan = cli.build_scrape_plan("slot", [GBA], data, {}, {}, {"gba": ["hacks/B.zip"]}, lambda s: card,
                                         os.path.join(base, "ES-DE"), lambda p: asked.append(p) or True, base)
        self.assertEqual(asked, [os.path.join(card, "B.zip")])
        self.assertEqual([j[1] for j in plan["jobs"]], [os.path.join(base, "Labels", "GBA", "B.png")])

    def test_media_root_is_labels_by_slot_folder(self):
        self.assertEqual(cli.media_root_of("slot", GBA, "/card", "/card/ES-DE"), os.path.join("/card", "Labels", "GBA"))

    def test_stale_media_is_left_alone(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "Labels", "GBA"))
            open(os.path.join(base, "Labels", "GBA", "Gone.png"), "w").close()
            os.makedirs(os.path.join(base, "Games", "GBA"))
            self.assertEqual(cli.stale_media("slot", [GBA], os.path.join(base, "Games"), ""), [])


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"png")


class DerivedUploadTest(unittest.TestCase):
    def derived(self, files, system="gba", roms=("A.zip", "hacks/B.zip"), existing=None):
        with tempfile.TemporaryDirectory() as es:
            for f in files:
                touch(os.path.join(es, "downloaded_media", system, f))
            plan = cli.plan_upload(es, {system: set(roms)}, existing or {}, {})
        return plan

    def test_game_boy_art_makes_onion_and_slot_art(self):
        plan = self.derived(["covers/A.png"])
        self.assertEqual(sorted((k, box) for k, _, _, box in plan["derived"]),
                         [("scrapes/gba/onion/A.png", (250, 360)), ("scrapes/gba/slot/A.png", (1280, 661))])

    def test_game_boy_and_color_labels_are_the_cart_size(self):
        for system in ("gb", "gbc"):
            plan = self.derived(["covers/A.png"], system, ("A.gb",))
            slot = [d for d in plan["derived"] if "/slot/" in d[0]]
            self.assertEqual([d[3] for d in slot], [(1024, 914)])

    def test_a_rom_in_a_subfolder_gets_slot_art_only(self):
        plan = self.derived(["covers/hacks/B.png"])
        self.assertEqual([k for k, *_ in plan["derived"]], ["scrapes/gba/slot/hacks/B.png"])

    def test_other_systems_get_no_slot_art(self):
        plan = self.derived(["covers/A.png"], "snes", ("A.sfc",))
        self.assertEqual([k for k, *_ in plan["derived"]], ["scrapes/snes/onion/A.png"])

    def test_existing_art_is_counted_not_recreated(self):
        plan = self.derived(["covers/A.png"], existing={"scrapes/gba/slot/A.png": 1})
        self.assertEqual([k for k, *_ in plan["derived"]], ["scrapes/gba/onion/A.png"])
        self.assertEqual(plan["derived_present"], 1)

    def test_cover_is_preferred_over_a_screenshot(self):
        plan = self.derived(["screenshots/A.png", "covers/A.png"])
        self.assertTrue(all(src.endswith(os.path.join("covers", "A.png")) for _, src, _, _ in plan["derived"]))


if __name__ == "__main__":
    unittest.main()
