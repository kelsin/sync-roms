import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import mirroring, scrape_files, scrape_plan, store, ui  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba",
       "folders": {"esde": "gba", "muos": "gba", "slot": "GBA"}, "muos_catalogue": "Nintendo Game Boy Advance"}
LISTING = {
    "scrapes/gba/covers/A.png": 5, "scrapes/gba/screenshots/A.jpg": 6, "scrapes/gba/3dboxes/A.png": 7,
    "scrapes/gba/slot/A.png": 8, "scrapes/gba/covers/hacks/B.png": 9, "scrapes/gba/slot/hacks/B.png": 3,
}
META = {"A.zip": {"name": "A", "desc": "An adventure."}}


def systems():
    return store.repo_json("systems")


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
            args = ("muos", [GBA], data, {"gba": ["A.zip"]}, lambda s: "/x", os.path.join(base, "ES-DE"),
                    lambda p: True, base)
            plan = scrape_plan.build_scrape_plan(*args)
            catalogue = os.path.join(base, "MUOS", "info", "catalogue", "Nintendo Game Boy Advance")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             sorted([os.path.join(catalogue, "box", "A.png"), os.path.join(catalogue, "preview", "A.jpg")]))
            self.assertEqual(len(plan["writes"]), 1)
            scrape_plan.apply_scrape_plan({"jobs": [], "gamelists": {}, "writes": plan["writes"]}, base)
            self.assertEqual(scrape_plan.build_scrape_plan(*args)["writes"], [])


class ApplyFailureTest(unittest.TestCase):
    def test_quiet_still_shows_a_gamelist_that_could_not_be_written(self):
        plan = {"jobs": [], "gamelists": {"/card/gamelist.xml": {}}, "writes": []}
        with mock.patch.object(scrape_plan, "update_gamelist", side_effect=OSError("disk full")), \
                mock.patch.object(ui, "QUIET", True), contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(scrape_plan.apply_scrape_plan(plan, "/card"), 1)
        self.assertIn("/card/gamelist.xml: disk full", err.getvalue())
        self.assertNotIn("disk full", out.getvalue())


class EmudeckPlanTest(unittest.TestCase):
    def test_media_goes_in_emulation_tools_and_the_gamelist_in_es_de_on_this_computer(self):
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as appdata:
            data = {"gba": (LISTING, META)}
            system = {**GBA, "folders": {**GBA["folders"], "emudeck": "gba"}}
            plan = scrape_plan.build_scrape_plan("emudeck", [system], data, {"gba": ["A.zip"]}, lambda s: "/x",
                                                 appdata, lambda p: True, base)
            media = os.path.join(base, "Emulation", "tools", "downloaded_media", "gba")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             sorted([os.path.join(media, "covers", "A.png"), os.path.join(media, "screenshots", "A.jpg"),
                                     os.path.join(media, "3dboxes", "A.png")]))
            self.assertEqual(dict(plan["gamelists"]),
                             {os.path.join(appdata, "gamelists", "gba", "gamelist.xml"): {"A.zip": {"name": "A", "desc": "An adventure."}}})
        self.assertEqual(plan["writes"], [])

    def test_emudeck_gamelist_folder_is_es_de_name(self):
        with tempfile.TemporaryDirectory() as base:
            system = {"bucket": "wiiu", "folders": {"emudeck": "wiiu/roms"}}
            plan = scrape_plan.build_scrape_plan("emudeck", [system], {"wiiu": ({}, {"A.wua": {"name": "A"}})},
                                                 {"wiiu": ["A.wua"]}, lambda s: "/x", "/appdata", lambda p: True, base)
        self.assertEqual(list(plan["gamelists"]), [os.path.join("/appdata", "gamelists", "wiiu", "gamelist.xml")])

    def test_stale_media_is_found_in_the_emudeck_media_folder(self):
        with tempfile.TemporaryDirectory() as base:
            media = os.path.join(base, "Emulation", "tools", "downloaded_media", "wiiu", "covers")
            touch(os.path.join(media, "Keep.png"))
            touch(os.path.join(media, "Gone.png"))
            touch(os.path.join(base, "Emulation", "roms", "wiiu", "roms", "Keep.rpx"))
            system = {"bucket": "wiiu", "folders": {"emudeck": "wiiu/roms"}}
            stale = scrape_plan.stale_media("emudeck", [system], os.path.join(base, "Emulation", "roms"),
                                            os.path.join(base, "ES-DE"), base)
        self.assertEqual([os.path.basename(p) for p in stale], ["Gone.png"])


    def test_stale_media_clears_the_older_bucket_named_esde_folders(self):
        with tempfile.TemporaryDirectory() as base:
            es = os.path.join(base, "ES-DE")
            touch(os.path.join(es, "downloaded_media", "sg-1000", "covers", "A.png"))
            touch(os.path.join(es, "downloaded_media", "sg1000", "covers", "A.png"))  # from before the rename
            touch(os.path.join(es, "gamelists", "sg1000", "gamelist.xml"))
            touch(os.path.join(base, "ROMs", "sg-1000", "A.sg"))
            system = {"bucket": "sg1000", "folders": {"esde": "sg-1000"}}
            stale = scrape_plan.stale_media("esde", [system], os.path.join(base, "ROMs"), es, base)
            self.assertEqual(sorted(os.path.relpath(p, es) for p in stale),
                             [os.path.join("downloaded_media", "sg1000", "covers", "A.png"),
                              os.path.join("gamelists", "sg1000", "gamelist.xml")])


    def test_stale_media_clears_the_older_bucket_named_emudeck_gamelist_only_with_es_de(self):
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as appdata:
            media = os.path.join(base, "Emulation", "tools", "downloaded_media")
            touch(os.path.join(media, "sg-1000", "covers", "A.png"))
            touch(os.path.join(media, "sg1000", "covers", "A.png"))  # from before the rename
            touch(os.path.join(appdata, "gamelists", "sg1000", "gamelist.xml"))
            touch(os.path.join(base, "Emulation", "roms", "sg-1000", "A.sg"))
            system = {"bucket": "sg1000", "folders": {"emudeck": "sg-1000"}}
            roms = os.path.join(base, "Emulation", "roms")
            self.assertEqual(sorted(scrape_plan.stale_media("emudeck", [system], roms, appdata, base)),
                             sorted([os.path.join(media, "sg1000", "covers", "A.png"),
                                     os.path.join(appdata, "gamelists", "sg1000", "gamelist.xml")]))
            self.assertEqual(scrape_plan.stale_media("emudeck", [system], roms, None, base),
                             [os.path.join(media, "sg1000", "covers", "A.png")])


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
            plan = scrape_plan.build_scrape_plan("slot", [GBA], data, {"gba": ["hacks/B.zip"]}, lambda s: card,
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

    def run_onion(self, layout, files):
        with tempfile.TemporaryDirectory() as base:
            for rel in files + ["Roms/GBA/Game.zip"]:
                touch(os.path.join(base, rel))
            system = {"bucket": "gba", "folders": {layout: "GBA"}}
            stale = scrape_plan.stale_media(layout, [system], os.path.join(base, "Roms"), os.path.join(base, "ES-DE"), base)
            return sorted(os.path.relpath(p, base) for p in stale)

    def test_allium_removes_onions_gamelist_once_its_own_exists(self):
        self.assertEqual(self.run_onion("allium", ["Roms/GBA/gamelist.xml", "Roms/GBA/miyoogamelist.xml"]),
                         ["Roms/GBA/miyoogamelist.xml"])

    def test_allium_keeps_onions_gamelist_until_its_own_exists(self):
        self.assertEqual(self.run_onion("allium", ["Roms/GBA/miyoogamelist.xml"]), [])

    def test_allium_removes_onions_recent_and_favorite_lists_from_the_roms_root(self):
        files = ["Roms/recentlist-hidden.json", "Roms/favorite.json"]
        self.assertEqual(self.run_onion("allium", files), sorted(files))
        self.assertEqual(self.run_onion("onion", files), [])

    def test_onion_removes_alliums_gamelist_once_its_own_exists(self):
        self.assertEqual(self.run_onion("onion", ["Roms/GBA/gamelist.xml", "Roms/GBA/miyoogamelist.xml"]),
                         ["Roms/GBA/gamelist.xml"])

    def run_empty_onion(self, layout):
        with tempfile.TemporaryDirectory() as base:
            files = ["Roms/GBA/gamelist.xml", "Roms/GBA/miyoogamelist.xml", "Roms/GBA/Imgs/Old.png", "Roms/GBA/cache6.db"]
            for rel in files:
                touch(os.path.join(base, rel))
            roms_dir = os.path.join(base, "Roms")
            systems = [{"bucket": "gba", "folders": {layout: "GBA"}}]
            stale = scrape_plan.stale_media(layout, systems, roms_dir, os.path.join(base, "ES-DE"), base)
            for p in stale:
                os.remove(p)
            removed = scrape_plan.prune_empty_systems(layout, systems, roms_dir)
            return sorted(os.path.relpath(p, base) for p in stale), removed, os.path.exists(os.path.join(roms_dir, "GBA"))

    def test_onion_family_clears_an_empty_system_and_its_folder(self):
        for layout in ("onion", "allium"):
            stale, removed, exists = self.run_empty_onion(layout)
            self.assertEqual(stale, ["Roms/GBA/Imgs/Old.png", "Roms/GBA/cache6.db", "Roms/GBA/gamelist.xml",
                                     "Roms/GBA/miyoogamelist.xml"], layout)
            self.assertEqual((len(removed), exists), (1, False), layout)

    def test_a_system_with_roms_keeps_its_folder_and_gamelists(self):
        self.assertEqual(self.run_onion("allium", ["Roms/GBA/gamelist.xml"]), [])
        with tempfile.TemporaryDirectory() as base:
            touch(os.path.join(base, "Roms/GBA/Game.zip"))
            system = {"bucket": "gba", "folders": {"allium": "GBA"}}
            self.assertEqual(scrape_plan.prune_empty_systems("allium", [system], os.path.join(base, "Roms")), [])
            self.assertTrue(os.path.exists(os.path.join(base, "Roms/GBA/Game.zip")))

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


def system_of(bucket):
    return next(s for s in systems() if s["bucket"] == bucket)


class SharedFolderTest(unittest.TestCase):
    """3ds and n3ds share ES-DE's n3ds ROM folder, so they share its media and gamelist folders too."""

    def test_media_and_gamelist_go_in_the_shared_folder(self):
        data = {"3ds": ({"scrapes/3ds/covers/A.png": 5}, {"A.3ds": {"name": "A"}}),
                "n3ds": ({"scrapes/n3ds/covers/B.png": 5}, {"B.3ds": {"name": "B"}})}
        with tempfile.TemporaryDirectory() as base:
            es = os.path.join(base, "ES-DE")
            plan = scrape_plan.build_scrape_plan("esde", [system_of("3ds"), system_of("n3ds")], data,
                                                 {"3ds": ["A.3ds"], "n3ds": ["B.3ds"]}, lambda s: "/x", es,
                                                 lambda p: True, base)
            media = os.path.join(es, "downloaded_media", "n3ds", "covers")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             [os.path.join(media, "A.png"), os.path.join(media, "B.png")])
            self.assertEqual(list(plan["gamelists"]), [os.path.join(es, "gamelists", "n3ds", "gamelist.xml")])
            self.assertEqual(sorted(next(iter(plan["gamelists"].values()))), ["A.3ds", "B.3ds"])

    def test_emudeck_and_esde_use_the_folder_name(self):
        self.assertEqual(scrape_plan.media_root_of("emudeck", system_of("3ds"), "/c", "/c/ES-DE"),
                         os.path.join("/c", scrape_plan.EMUDECK_MEDIA, "n3ds"))
        self.assertEqual(scrape_plan.media_root_of("esde", system_of("sg1000"), "/c", "/c/ES-DE"),
                         os.path.join("/c/ES-DE", "downloaded_media", "sg-1000"))
        self.assertEqual(scrape_plan.esde_name({"bucket": "wiiu", "folders": {"emudeck": "wiiu/roms"}}, "emudeck"),
                         "wiiu")

    def test_stale_media_looks_in_the_shared_folder(self):
        with tempfile.TemporaryDirectory() as base:
            es = os.path.join(base, "ES-DE")
            touch(os.path.join(base, "ROMs", "n3ds", "A.3ds"))
            touch(os.path.join(es, "downloaded_media", "n3ds", "covers", "A.png"))
            touch(os.path.join(es, "downloaded_media", "n3ds", "covers", "Gone.png"))
            stale = scrape_plan.stale_media("esde", [system_of("3ds"), system_of("n3ds")],
                                            os.path.join(base, "ROMs"), es, base)
        self.assertEqual([os.path.basename(p) for p in stale], ["Gone.png"])

class DerivedArtTest(unittest.TestCase):
    def derived(self, found, system="gba", stem="A"):
        return [(k, src, box) for k, src, box in scrape_files.derived_art(system, stem, found)]

    def test_game_boy_art_makes_onion_and_slot_art(self):
        self.assertEqual([(k, box) for k, _, box in self.derived({"covers": "c.png"})],
                         [("scrapes/gba/onion/A.png", (250, 360)), ("scrapes/gba/slot/A.png", (1280, 661))])

    def test_game_boy_and_color_labels_are_the_cart_size(self):
        for system in ("gb", "gbc"):
            slot = [box for k, _, box in self.derived({"covers": "c.png"}, system) if "/slot/" in k]
            self.assertEqual(slot, [(1024, 901)])

    def test_a_rom_in_a_subfolder_gets_slot_art_only(self):
        self.assertEqual([k for k, *_ in self.derived({"covers": "c.png"}, stem="hacks/B")], ["scrapes/gba/slot/hacks/B.png"])

    def test_other_systems_get_no_slot_art(self):
        self.assertEqual([k for k, *_ in self.derived({"covers": "c.png"}, "snes")], ["scrapes/snes/onion/A.png"])

    def test_cover_is_preferred_over_a_screenshot(self):
        self.assertEqual({src for _, src, _ in self.derived({"screenshots": "s.png", "covers": "c.png"})}, {"c.png"})


class EsdeExtrasCleanTest(unittest.TestCase):
    def test_text_keys_are_metadata_only(self):
        existing = {"scrapes/gba/metadata.json": 1, "scrapes/esde/collections/custom-Fav.cfg": 1,
                    "scrapes/esde/settings.json": 1, "scrapes/gba/covers/A.png": 1}
        self.assertEqual(scrape_files.text_keys(existing), ["scrapes/gba/metadata.json"])

    def test_clean_leaves_old_esde_objects_alone(self):
        existing = {"scrapes/esde/themes/t/theme.xml": 1, "scrapes/esde/settings.json": 1,
                    "scrapes/esde/collections/custom-Fav.cfg": 1}
        self.assertEqual(scrape_files.plan_clean(existing, {}, {})[:2], ([], []))


class EsdeExtrasSyncTest(unittest.TestCase):
    def test_sync_plan_has_no_esde_extras(self):
        with tempfile.TemporaryDirectory() as base:
            es = os.path.join(base, "ES-DE")
            plan = scrape_plan.build_scrape_plan("esde", [GBA], {"gba": (LISTING, META)}, {"gba": ["A.zip"]},
                                                 lambda s: os.path.join(base, "ROMs", "gba"), es, lambda p: True, base)
        self.assertEqual(set(plan), {"jobs", "gamelists", "writes"})
        self.assertFalse(any(k.startswith("scrapes/esde/") for k, *_ in plan["jobs"]))
        self.assertFalse(any(os.path.relpath(p, es).split(os.sep)[0] in ("themes", "collections", "settings")
                             for p, _ in plan["writes"]))

    def test_load_scrape_data_never_lists_scrapes_esde(self):
        with mock.patch.object(scrape_plan.s3, "list_sizes", return_value={}) as ls, \
                mock.patch.object(scrape_plan.s3, "fetch_texts", return_value={}) as ft:
            data = scrape_plan.load_scrape_data([GBA])
        self.assertEqual(data, {"gba": ({}, {})})
        self.assertEqual([c.args[0] for c in ls.call_args_list], ["scrapes/gba/"])
        ft.assert_called_once_with([])

    def test_mirror_wanted_skips_scrapes_esde_but_keeps_onion_themes(self):
        listings = {"BIOS/": {"BIOS/gba_bios.bin": 1}, "os/onion/Themes/": {"os/onion/Themes/t/a.png": 2},
                    "scrapes/esde/": {"scrapes/esde/themes/t/theme.xml": 3},
                    "os/drivers/": {"os/drivers/a.zip": 6, "os/drivers/a.tag": 7},
                    "gba/": {"gba/A.zip": 4}, "scrapes/gba/": {"scrapes/gba/covers/A.png": 5}}
        manifest = {"systems": [{"bucket": "gba", "games": [{"bucket": "gba/A.zip"}], "bios": {"files": ["gba_bios.bin"]}}]}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})) as ls:
            wanted = mirroring.mirror_wanted(manifest)
        self.assertEqual(wanted, {"gba/A.zip": 4, "scrapes/gba/covers/A.png": 5, "BIOS/gba_bios.bin": 1,
                                  "os/onion/Themes/t/a.png": 2, "os/drivers/a.zip": 6, "os/drivers/a.tag": 7})
        self.assertNotIn("scrapes/esde/", [c.args[0] for c in ls.call_args_list])


if __name__ == "__main__":
    unittest.main()
