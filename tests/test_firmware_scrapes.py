import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import mirroring, scrape_files, scrape_plan, store, ui  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba",
       "folders": {"esde": "gba"}}
LISTING = {
    "scrapes/gba/covers/A.png": 5, "scrapes/gba/screenshots/A.jpg": 6, "scrapes/gba/3dboxes/A.png": 7,
    "scrapes/gba/covers/hacks/B.png": 9,
}
META = {"A.zip": {"name": "A", "desc": "An adventure."}}


def systems():
    return store.repo_json("systems")


class ArcadeGamelistTest(unittest.TestCase):
    def test_mame_entries_take_their_name_from_metadata(self):
        meta = {"1942.zip": {"name": "1942", "desc": "d"}}
        _, entries, _ = scrape_plan.plan_scrapes("esde", ["1942.zip", "x.zip"], {}, meta, "/m", "/r", lambda rom: True)
        self.assertEqual(entries, {"1942.zip": {"name": "1942", "desc": "d"}})


class ApplyFailureTest(unittest.TestCase):
    def test_quiet_still_shows_a_gamelist_that_could_not_be_written(self):
        plan = {"jobs": [], "gamelists": {"/card/gamelist.xml": {}}, "writes": []}
        with mock.patch.object(scrape_plan, "update_gamelist", side_effect=OSError("disk full")), \
                mock.patch.object(ui, "QUIET", True), contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(scrape_plan.apply_scrape_plan(plan, "/card"), (1, False))
        self.assertIn("/card/gamelist.xml: disk full", err.getvalue())
        self.assertNotIn("disk full", out.getvalue())


class ApplyWroteTest(unittest.TestCase):
    def apply(self, gamelists, base="/card", jobs=(), failed=0):
        plan = {"jobs": list(jobs), "gamelists": gamelists, "writes": []}
        with mock.patch.object(scrape_plan, "update_gamelist", lambda path, entries: path.endswith("new.xml")), \
                mock.patch.object(scrape_plan.downloads, "run_downloads", lambda *a: failed), \
                contextlib.redirect_stdout(io.StringIO()):
            return scrape_plan.apply_scrape_plan(plan, base)

    def test_unchanged_gamelists_are_not_a_write(self):
        self.assertEqual(self.apply({"/card/gba/old.xml": {}}), (0, False))

    def test_a_written_gamelist_on_the_card_is_a_write(self):
        self.assertEqual(self.apply({"/card/gba/new.xml": {}}), (0, True))

    def test_a_gamelist_off_the_card_is_not_a_write(self):
        self.assertEqual(self.apply({"/home/me/ES-DE/new.xml": {}}), (0, False))

    def test_a_download_that_succeeded_is_a_write_and_all_failing_is_not(self):
        job = ("k", "/card/x", 1)
        self.assertEqual(self.apply({}, jobs=[job, job], failed=1), (1, True))
        self.assertEqual(self.apply({}, jobs=[job], failed=1), (1, False))


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


class StaleMediaTest(unittest.TestCase):
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

    def test_art_makes_onion_art(self):
        self.assertEqual([(k, box) for k, _, box in self.derived({"covers": "c.png"})], [("scrapes/gba/onion/A.png", (250, 360))])

    def test_a_rom_in_a_subfolder_gets_no_onion_art(self):
        self.assertEqual(self.derived({"covers": "c.png"}, stem="hacks/B"), [])

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

    def test_mirror_wanted_includes_the_newest_surprise_app_zip(self):
        listings = {"os/onion/": {"os/onion/Surprise-v0.2.0.zip": 8, "os/onion/Surprise-v0.10.0.zip": 9,
                                  "os/onion/Surprise-eadef4e.zip": 1, "os/onion/Themes/t/a.png": 2}}
        manifest = {"systems": []}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})):
            wanted = mirroring.mirror_wanted(manifest)
        self.assertEqual(wanted, {"os/onion/Surprise-v0.10.0.zip": 9})


if __name__ == "__main__":
    unittest.main()


class Pico8CartImageTest(unittest.TestCase):
    PICO = {"name": "PICO-8", "bucket": "pico8", "folders": {l: "pico8" for l in ("esde", "knulli", "onion", "allium")}}
    LISTING = {}

    def plan(self, layout, rels, listing=None, meta=None):
        with tempfile.TemporaryDirectory() as base:
            with mock.patch.object(scrape_plan.downloads.inventory, "stat", return_value={f"pico8/{r}": 3 for r in rels}):
                plan = scrape_plan.build_scrape_plan(layout, [self.PICO], {"pico8": (dict(self.LISTING if listing is None else listing), meta or {})}, {"pico8": rels},
                                                     lambda s: os.path.join(base, "ROMs", "pico8"), os.path.join(base, "ES-DE"),
                                                     lambda p: True, base)
            jobs = [(k, os.path.relpath(p, base)) for k, p, _ in plan["jobs"]]
            return jobs, {r: e for g in plan["gamelists"].values() for r, e in g.items()}

    def test_esde_uses_the_cart_as_the_mix_image(self):
        jobs, _ = self.plan("esde", ["a.p8.png", "b.p8"])
        self.assertEqual(jobs, [("pico8/a.p8.png", os.path.join("ES-DE", "downloaded_media", "pico8", "miximages", "a.p8.png"))])

    def test_knulli_points_its_image_at_the_cart(self):
        jobs, entries = self.plan("knulli", ["a.p8.png", "b.p8", "sub/c.p8.png"])
        self.assertEqual(jobs, [])
        self.assertEqual(entries, {"a.p8.png": {"image": "./a.p8.png"}, "sub/c.p8.png": {"image": "./sub/c.p8.png"}})

    def test_onion_and_allium_copy_the_cart_into_imgs(self):
        for layout in ("onion", "allium"):
            jobs, entries = self.plan(layout, ["a.p8.png", "sub/c.p8.png"])
            self.assertEqual(jobs, [("pico8/a.p8.png", os.path.join("ROMs", "pico8", "Imgs", "a.p8.png"))])
            self.assertEqual(entries["a.p8.png"]["image"], "./Imgs/a.p8.png")
            self.assertNotIn("sub/c.p8.png", entries)

    def test_pico8_is_scraped(self):
        self.assertEqual(next(s for s in systems() if s["bucket"] == "pico8")["screenscraper"], 234)

    def test_a_scraped_picture_replaces_the_cart(self):
        meta = {"a.p8.png": {"name": "A"}}
        jobs, _ = self.plan("esde", ["a.p8.png", "b.p8.png"], {"scrapes/pico8/miximages/a.p8.png": 1}, meta)
        self.assertEqual([k for k, _ in jobs], ["scrapes/pico8/miximages/a.p8.png", "pico8/b.p8.png"])
        jobs, entries = self.plan("knulli", ["a.p8.png", "b.p8.png"], {"scrapes/pico8/miximages/a.p8.png": 1}, meta)
        self.assertEqual([k for k, _ in jobs], ["scrapes/pico8/miximages/a.p8.png"])
        self.assertEqual(entries["a.p8.png"], {"name": "A", "image": "./images/a.p8-image.png"})
        self.assertEqual(entries["b.p8.png"], {"image": "./b.p8.png"})
        jobs, entries = self.plan("onion", ["a.p8.png", "b.p8.png"], {"scrapes/pico8/onion/a.p8.png": 1}, meta)
        self.assertEqual([k for k, _ in jobs], ["scrapes/pico8/onion/a.p8.png", "pico8/b.p8.png"])
        self.assertEqual(entries["a.p8.png"]["image"], "./Imgs/a.p8.png")
