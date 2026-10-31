import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "src", "sync_roms", "data")
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import scrape_files, scrape_plan  # noqa: E402

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
        return scrape_plan.plan_scrapes("muos", rels, LISTING, kw.get("meta", META), root, "/card/ROMS/gba", lambda rom: True)

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
            jobs, _, texts = scrape_plan.plan_scrapes("muos", ["A.zip"], LISTING, META, root, "/x", lambda rom: False)
        self.assertEqual((jobs, texts), ([], []))

    def test_build_plan_uses_the_catalogue_folder_and_skips_unchanged_text(self):
        with tempfile.TemporaryDirectory() as base:
            data = {"gba": (LISTING, META)}
            args = ("muos", [GBA], data, {}, {}, {"gba": ["A.zip"]}, lambda s: "/x", os.path.join(base, "ES-DE"),
                    lambda p: True, base)
            plan = scrape_plan.build_scrape_plan(*args)
            catalogue = os.path.join(base, "MUOS", "info", "catalogue", "Nintendo Game Boy Advance")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             sorted([os.path.join(catalogue, "box", "A.png"), os.path.join(catalogue, "preview", "A.jpg")]))
            self.assertEqual(len(plan["writes"]), 1)
            scrape_plan.apply_scrape_plan({"jobs": [], "extras": [], "gamelists": {}, "writes": plan["writes"]}, base)
            self.assertEqual(scrape_plan.build_scrape_plan(*args)["writes"], [])


class SlotPlanTest(unittest.TestCase):
    def test_label_goes_in_labels_named_after_the_rom(self):
        with tempfile.TemporaryDirectory() as root:
            jobs, entries, texts = scrape_plan.plan_scrapes("slot", ["A.zip", "hacks/B.zip", "C.zip"], LISTING, META, root,
                                                    "/x", lambda rom: True)
        self.assertEqual(sorted((k, os.path.relpath(p, root)) for k, p, _ in jobs),
                         [("scrapes/gba/slot/A.png", "A.png"), ("scrapes/gba/slot/hacks/B.png", "B.png")])
        self.assertEqual((entries, texts), ({}, []))

    def test_a_subfolder_rom_is_found_flat_on_the_card(self):
        with tempfile.TemporaryDirectory() as base:
            card = os.path.join(base, "Games", "GBA")
            data = {"gba": (LISTING, META)}
            asked = []
            plan = scrape_plan.build_scrape_plan("slot", [GBA], data, {}, {}, {"gba": ["hacks/B.zip"]}, lambda s: card,
                                         os.path.join(base, "ES-DE"), lambda p: asked.append(p) or True, base)
        self.assertEqual(asked, [os.path.join(card, "B.zip")])
        self.assertEqual([j[1] for j in plan["jobs"]], [os.path.join(base, "Labels", "GBA", "B.png")])

    def test_media_root_is_labels_by_slot_folder(self):
        self.assertEqual(scrape_plan.media_root_of("slot", GBA, "/card", "/card/ES-DE"), os.path.join("/card", "Labels", "GBA"))

def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")


def sysdef(bucket, muos=None, catalogue=None, slot=None):
    return {"bucket": bucket, "folders": {"muos": muos, "slot": slot}, **({"muos_catalogue": catalogue} if catalogue else {})}


class StaleMediaTest(unittest.TestCase):
    def run_stale(self, layout, systems, files, roms):
        """Paths (relative to the card) stale_media wants removed, given card files and ROM files."""
        with tempfile.TemporaryDirectory() as base:
            for rel in files + roms:
                touch(os.path.join(base, rel))
            roms_dir = os.path.join(base, "ROMS" if layout == "muos" else "Games")
            stale = scrape_plan.stale_media(layout, systems, roms_dir, os.path.join(base, "ES-DE"), base)
            return sorted(os.path.relpath(p, base) for p in stale)

    CAT = os.path.join("MUOS", "info", "catalogue")

    def test_muos_removes_art_for_roms_that_are_gone(self):
        cat = os.path.join(self.CAT, "Nintendo Game Boy Advance")
        stale = self.run_stale("muos", [sysdef("gba", "gba", "Nintendo Game Boy Advance")],
                               [f"{cat}/box/Keep.png", f"{cat}/box/Gone.png", f"{cat}/preview/Gone.jpg", f"{cat}/text/Gone.txt",
                                f"{cat}/text/Keep.txt"],
                               ["ROMS/gba/Keep.zip"])
        self.assertEqual(stale, [f"{cat}/box/Gone.png", f"{cat}/preview/Gone.jpg", f"{cat}/text/Gone.txt"])

    def test_muos_matches_names_ignoring_case(self):
        cat = os.path.join(self.CAT, "Nintendo Game Boy Advance")
        self.assertEqual(self.run_stale("muos", [sysdef("gba", "gba", "Nintendo Game Boy Advance")],
                                        [f"{cat}/box/keep.png"], ["ROMS/gba/KEEP.gba"]), [])

    def test_muos_only_touches_box_preview_and_text(self):
        cat = os.path.join(self.CAT, "Nintendo Game Boy Advance")
        files = [f"{cat}/grid/Gone.png", f"{cat}/manual/Gone.txt", f"{cat}/overlay/base/Gone.png",
                 os.path.join(self.CAT, "Folder", "Gone.png"), os.path.join(self.CAT, "Theme", "Gone.png")]
        self.assertEqual(self.run_stale("muos", [sysdef("gba", "gba", "Nintendo Game Boy Advance")], files,
                                        ["ROMS/gba/Keep.gba"]), [])

    def test_muos_systems_sharing_a_catalogue_keep_each_others_art(self):
        cat = os.path.join(self.CAT, "Arcade")
        systems = [sysdef("mame", "mame", "Arcade"), sysdef("cps1", "cps1", "Arcade")]
        stale = self.run_stale("muos", systems, [f"{cat}/box/sf2.png", f"{cat}/box/pacman.png", f"{cat}/box/gone.png"],
                               ["ROMS/mame/pacman.zip", "ROMS/cps1/sf2.zip"])
        self.assertEqual(stale, [f"{cat}/box/gone.png"])

    def test_muos_leaves_a_system_with_no_roms_alone(self):
        cat = os.path.join(self.CAT, "Nintendo Game Boy Advance")
        self.assertEqual(self.run_stale("muos", [sysdef("gba", "gba", "Nintendo Game Boy Advance")],
                                        [f"{cat}/box/Other.png"], ["ROMS/gba/.keep"]), [])

    def test_slot_removes_labels_for_roms_that_are_gone(self):
        stale = self.run_stale("slot", [sysdef("gba", slot="GBA")], ["Labels/GBA/Keep.png", "Labels/GBA/Gone.png"],
                               ["Games/GBA/Keep.gba"])
        self.assertEqual(stale, [os.path.join("Labels", "GBA", "Gone.png")])

    def test_slot_matches_names_like_slot_does(self):
        files = ["Labels/GBA/metroid fusion.png", "Labels/GBA/Metroid Fusion (USA, Europe).png"]
        self.assertEqual(self.run_stale("slot", [sysdef("gba", slot="GBA")], files,
                                        ["Games/GBA/Metroid Fusion (USA) [!].gba"]), [])

    def test_slot_leaves_other_label_files_and_folders_alone(self):
        files = ["Labels/cart_shell.txt", "Labels/GBAV/Gone.png", "Labels/GBC/Gone.png"]
        self.assertEqual(self.run_stale("slot", [sysdef("gba", slot="GBA"), sysdef("gbc", slot="GBC")], files,
                                        ["Games/GBA/Keep.gba"]), [])


class SlotLabelUploadTest(unittest.TestCase):
    SYSTEMS = [sysdef("gba", slot="GBA"), sysdef("gb", slot="GB")]

    def plan(self, files, roms, existing=None):
        with tempfile.TemporaryDirectory() as labels:
            for f in files:
                touch(os.path.join(labels, f))
            files, present, unmatched = scrape_files.plan_slot_upload(labels, self.SYSTEMS, roms, existing or {})
            return [k for k, *_ in files], present, [os.path.relpath(u, labels) for u in unmatched]

    def test_labels_named_after_a_rom_go_to_the_slot_folder(self):
        keys, present, unmatched = self.plan(["GBA/A.png", "GB/B.png", "GBA/Nope.png", "GBA/A.txt"],
                                             {"gba": {"A.zip"}, "gb": {"B.gb"}})
        self.assertEqual(sorted(keys), ["scrapes/gb/slot/B.png", "scrapes/gba/slot/A.png"])
        self.assertEqual((present, unmatched), (0, ["GBA/Nope.png"]))

    def test_same_size_is_present_and_a_different_size_is_replaced(self):
        keys, present, _ = self.plan(["GBA/A.png", "GBA/B.png"], {"gba": {"A.zip", "B.zip"}},
                                     {"scrapes/gba/slot/A.png": 1, "scrapes/gba/slot/B.png": 99})
        self.assertEqual((keys, present), (["scrapes/gba/slot/B.png"], 1))


class DerivedUploadTest(unittest.TestCase):
    def derived(self, files, system="gba", roms=("A.zip", "hacks/B.zip"), existing=None):
        with tempfile.TemporaryDirectory() as es:
            for f in files:
                touch(os.path.join(es, "downloaded_media", system, f))
            plan = scrape_files.plan_upload(es, {system: set(roms)}, existing or {}, {})
        return plan

    def test_game_boy_art_makes_onion_and_slot_art(self):
        plan = self.derived(["covers/A.png"])
        self.assertEqual(sorted((k, box) for k, _, _, box in plan["derived"]),
                         [("scrapes/gba/onion/A.png", (250, 360)), ("scrapes/gba/slot/A.png", (1280, 661))])

    def test_game_boy_and_color_labels_are_the_cart_size(self):
        for system in ("gb", "gbc"):
            plan = self.derived(["covers/A.png"], system, ("A.gb",))
            slot = [d for d in plan["derived"] if "/slot/" in d[0]]
            self.assertEqual([d[3] for d in slot], [(1024, 901)])

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


class UnsafeKeyTest(unittest.TestCase):
    def test_theme_key_with_dotdot_is_skipped(self):
        listing = {"scrapes/esde/themes/ok/a.xml": 1, "scrapes/esde/themes/../../evil": 2}
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()):
            jobs, _ = scrape_plan.plan_esde_extras(root, listing, {})
        self.assertEqual([k for k, _, _ in jobs], ["scrapes/esde/themes/ok/a.xml"])


class ShareSettingTest(unittest.TestCase):
    def test_names_must_be_plain_identifiers(self):
        self.assertTrue(scrape_plan.share_setting("ScraperFoo_1"))
        self.assertFalse(scrape_plan.share_setting('Scrape" evil="1'))
        self.assertFalse(scrape_plan.share_setting("Scrape Foo"))


if __name__ == "__main__":
    unittest.main()
