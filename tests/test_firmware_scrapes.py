import contextlib
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import mirroring, scrape_files, scrape_plan, store, ui  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba",
       "folders": {"esde": "gba", "muos": "gba"}, "muos_catalogue": "Nintendo Game Boy Advance"}
LISTING = {
    "scrapes/gba/covers/A.png": 5, "scrapes/gba/screenshots/A.jpg": 6, "scrapes/gba/3dboxes/A.png": 7,
    "scrapes/gba/covers/hacks/B.png": 9,
}
META = {"A.zip": {"name": "A", "desc": "An adventure."}}


def systems():
    return store.repo_json("systems")


class DataTest(unittest.TestCase):
    def test_muos_systems_name_their_catalogue(self):
        for s in systems():
            self.assertEqual(bool(s["folders"]["muos"]), "muos_catalogue" in s, s["bucket"])


class ArcadeGamelistTest(unittest.TestCase):
    def test_mame_entries_take_their_name_from_metadata(self):
        meta = {"1942.zip": {"name": "1942", "desc": "d"}}
        _, entries, _ = scrape_plan.plan_scrapes("esde", ["1942.zip", "x.zip"], {}, meta, "/m", "/r", lambda rom: True)
        self.assertEqual(entries, {"1942.zip": {"name": "1942", "desc": "d"}})


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


FAVORITED = ('<?xml version="1.0"?>\n<gameList>\n'
             '\t<game>\n\t\t<path>./A.zip</path>\n\t\t<name>Old A</name>\n\t\t<favorite>true</favorite>\n'
             '\t\t<playcount>3</playcount>\n\t</game>\n'
             '\t<game>\n\t\t<path>./Gone.zip</path>\n\t\t<name>Gone</name>\n\t\t<favorite>true</favorite>\n\t</game>\n'
             '</gameList>\n')


class FavoritesKeptTest(unittest.TestCase):
    """ES-DE keeps favorites in its gamelists; nothing a sync does may drop one already on the card."""

    def setUp(self):
        self.path = os.path.join(self.enterContext(tempfile.TemporaryDirectory()), "gamelist.xml")
        with open(self.path, "w") as f:
            f.write(FAVORITED)

    def games(self):
        root = ET.parse(self.path).getroot()
        return {g.findtext("path"): {c.tag: c.text for c in g} for g in root.findall("game")}

    def test_a_rescrape_keeps_the_favorite_and_play_count(self):
        self.assertTrue(scrape_plan.update_gamelist(self.path, {"A.zip": {"name": "New A", "desc": "d"}}))
        a = self.games()["./A.zip"]
        self.assertEqual((a["name"], a["desc"], a["favorite"], a["playcount"]), ("New A", "d", "true", "3"))

    def test_a_favorite_whose_rom_is_not_synced_stays(self):
        scrape_plan.update_gamelist(self.path, {"A.zip": {"name": "New A"}, "B.zip": {"name": "B"}})
        games = self.games()
        self.assertEqual(games["./Gone.zip"], {"path": "./Gone.zip", "name": "Gone", "favorite": "true"})
        self.assertNotIn("favorite", games["./B.zip"])

    def test_an_unchanged_scrape_leaves_the_file_as_it_is(self):
        self.assertFalse(scrape_plan.update_gamelist(self.path, {"A.zip": {"name": "Old A"}}))
        with open(self.path) as f:
            self.assertEqual(f.read(), FAVORITED)

    def test_scraped_metadata_never_sets_favorite(self):
        self.assertNotIn("favorite", scrape_plan.gamelist_fields({"name": "A", "favorite": "false"}))

    def test_stale_media_never_removes_an_es_de_gamelist_in_use(self):
        for roms in (["ROMs/gba/A.zip"], []):  # a system with ROMs, and one emptied on the card
            with tempfile.TemporaryDirectory() as base:
                es = os.path.join(base, "ES-DE")
                touch(os.path.join(es, "gamelists", "gba", "gamelist.xml"))
                os.makedirs(os.path.join(base, "ROMs", "gba"))
                for rel in roms:
                    touch(os.path.join(base, rel))
                stale = scrape_plan.stale_media("esde", [GBA], os.path.join(base, "ROMs"), es, base)
                self.assertNotIn(os.path.join(es, "gamelists", "gba", "gamelist.xml"), stale)


def sysdef(bucket, muos=None, catalogue=None):
    return {"bucket": bucket, "folders": {"muos": muos}, **({"muos_catalogue": catalogue} if catalogue else {})}


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

    def test_spruce_writes_a_miyoogamelist_with_the_name_and_qoi_image(self):
        meta = {"a.zip": {"name": "A", "developer": "Dev", "rating": 0.8}}
        _, entries, _ = scrape_plan.plan_scrapes("spruce", ["a.zip", "b.zip", "sub/c.zip"], {"scrapes/gba/spruce/a.qoi": 5},
                                                 meta, "/m", "/r", lambda rom: True)
        self.assertEqual(entries, {"a.zip": {"name": "A", "image": "./Imgs/a.qoi"}})
        self.assertEqual(scrape_plan.GAMELIST_FILES["spruce"], "miyoogamelist.xml")

    def test_spruce_removes_alliums_gamelist_once_its_own_exists(self):
        self.assertEqual(self.run_onion("spruce", ["Roms/GBA/gamelist.xml", "Roms/GBA/miyoogamelist.xml"]),
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
    def derived(self, found, system="gba", stem="A", size=None):
        return scrape_files.derived_art(system, stem, found, size)

    def test_art_makes_onion_and_spruce_art(self):
        self.assertEqual([(k, box) for k, _, box in self.derived({"covers": "c.png"})], [
            ("scrapes/gba/onion/A.png", (250, 360)), ("scrapes/gba/spruce/A.qoi", (640, 480)),
            ("scrapes/gba/spruce_med/A.qoi", (400, 300)), ("scrapes/gba/spruce_small/A.qoi", (200, 200))])

    def test_miximage_is_used_when_there_is_no_cover(self):
        self.assertEqual({src for _, src, _ in self.derived({"miximages": "m.png"})}, {"m.png"})

    def test_cover_is_preferred_over_a_miximage(self):
        self.assertEqual({src for _, src, _ in self.derived({"miximages": "m.png", "covers": "c.png"})}, {"c.png"})

    def test_pico8_falls_back_to_the_cart_picture(self):
        self.assertEqual({src for _, src, _ in self.derived({"cart": "c.p8.png"}, "pico8", "foo.p8")}, {"c.p8.png"})
        self.assertEqual({src for _, src, _ in self.derived({"cart": "c.p8.png", "covers": "c.png"}, "pico8", "foo.p8")}, {"c.png"})
        self.assertEqual({src for _, src, _ in self.derived({"cart": "c.p8.png"})}, set())

    def test_three_dboxes_and_screenshots_are_no_longer_used(self):
        self.assertEqual(self.derived({"3dboxes": "d.png", "screenshots": "s.png"}), [])

    def test_a_rom_in_a_subfolder_gets_no_art(self):
        self.assertEqual(self.derived({"covers": "c.png"}, stem="hacks/B"), [])

    def test_small_source_gets_only_the_large_spruce_tier(self):
        self.assertEqual([k for k, _, _ in self.derived({"covers": "c.png"}, size=(150, 100))],
                         ["scrapes/gba/onion/A.png", "scrapes/gba/spruce/A.qoi"])

    def test_no_spruce_art_without_pillow(self):
        with mock.patch.object(scrape_plan, "can_make_qoi", return_value=False):
            self.assertEqual([k for k, _, _ in self.derived({"covers": "c.png"})], ["scrapes/gba/onion/A.png"])


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

    def test_metadata_that_is_not_an_object_syncs_as_no_metadata(self):
        key = "scrapes/gba/metadata.json"
        for text in ("{nope", "[]", '["A.zip"]', "5", '"A.zip"', "null"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as base, \
                    mock.patch.object(scrape_plan.s3, "list_sizes", return_value={key: 1}), \
                    mock.patch.object(scrape_plan.s3, "fetch_texts", return_value={key: text}):
                data = scrape_plan.load_scrape_data([GBA])
                self.assertEqual(data, {"gba": ({key: 1}, {})})
                plan = scrape_plan.build_scrape_plan("esde", [GBA], data, {"gba": ["A.zip"]},
                                                     lambda s: os.path.join(base, "ROMs", "gba"), os.path.join(base, "ES-DE"),
                                                     lambda p: True, base)
                self.assertEqual((plan["jobs"], dict(plan["gamelists"]), plan["writes"]), ([], {}, []))

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

    def test_mirror_wanted_includes_the_newest_spruceos_7z(self):
        listings = {"os/spruceos/": {"os/spruceos/spruceV4.5.6.7z": 1, "os/spruceos/spruceV4.6.0.7z": 2,
                                     "os/spruceos/spruceOTA-v4.5.6-to-v4.6.0.7z": 3}}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})):
            wanted = mirroring.mirror_wanted({"systems": []})
        self.assertEqual(wanted, {"os/spruceos/spruceV4.6.0.7z": 2})

    def test_mirror_wants_listed_and_current_themes(self):
        pre = "os/spruceos/themes/"
        listing = {pre + "A/config.json": 1, pre + "A/x.png": 2, pre + "B/config.json": 3, pre + "C/config.json": 4,
                   pre + "D/config.json": 5, pre + "A/": 0}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listing if p == pre else {}), \
                mock.patch.object(mirroring.spruce_themes, "default_list", return_value=["A"]), \
                mock.patch.object(mirroring.store, "load_cards", return_value={"c": {"spruce_theme": "C"}, "d": "x"}):
            wanted = mirroring.mirror_wanted({"systems": []})
        self.assertEqual(wanted, {pre + "A/config.json": 1, pre + "A/x.png": 2, pre + "C/config.json": 4})

    def test_mirror_wanted_includes_the_android_apks(self):
        listings = {"os/android/APKs/": {"os/android/APKs/": 0, "os/android/APKs/obtainium.json": 1, "os/android/APKs/ES-DE.apk": 2,
                                         "os/android/APKs/RAOfflineProxy-v3.1.0.apk": 3}}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})):
            wanted = mirroring.mirror_wanted({"systems": []})
        self.assertEqual(wanted, {"os/android/APKs/obtainium.json": 1, "os/android/APKs/ES-DE.apk": 2,
                                  "os/android/APKs/RAOfflineProxy-v3.1.0.apk": 3})

    def test_mirror_wanted_includes_the_newest_raofflineproxy_file_of_each_layout(self):
        listings = {"os/allium/": {"os/allium/RAOfflineProxy-Allium-v3.9.0.zip": 1, "os/allium/RAOfflineProxy-Allium-v3.10.0.zip": 2},
                    "os/muOS/": {"os/muOS/RAOfflineProxy-muOS-v3.1.0.muxapp": 3, "os/muOS/muos.img.gz": 9},
                    "os/knulli/": {"os/knulli/RAOfflineProxy-Knulli-v3.1.0-Install.sh": 4, "os/knulli/knulli.img.gz": 9},
                    "os/onion/": {"os/onion/RAOfflineProxy-Onion-v3.1.0.zip": 5}}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})):
            wanted = mirroring.mirror_wanted({"systems": []})
        self.assertEqual(wanted, {"os/allium/RAOfflineProxy-Allium-v3.10.0.zip": 2, "os/muOS/RAOfflineProxy-muOS-v3.1.0.muxapp": 3,
                                  "os/knulli/RAOfflineProxy-Knulli-v3.1.0-Install.sh": 4, "os/onion/RAOfflineProxy-Onion-v3.1.0.zip": 5})


if __name__ == "__main__":
    unittest.main()


class Pico8CartImageTest(unittest.TestCase):
    PICO = {"name": "PICO-8", "bucket": "pico8", "folders": {l: "pico8" for l in ("esde", "knulli", "rocknix", "onion", "allium")}}
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

    def test_rocknix_points_its_image_at_the_cart(self):
        jobs, entries = self.plan("rocknix", ["a.p8.png", "b.p8", "sub/c.p8.png"])
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


class RocknixMediaTest(unittest.TestCase):
    def test_gamelist_is_gamelist_xml(self):
        self.assertEqual(scrape_plan.GAMELIST_FILES["rocknix"], "gamelist.xml")
        self.assertIn("rocknix", scrape_plan.SCRAPE_LAYOUTS)

    def test_media_is_planned_like_knulli(self):
        listing = {"scrapes/gba/miximages/A.png": 1, "scrapes/gba/covers/A.png": 2, "scrapes/gba/videos/A.mp4": 3}
        meta = {"A.zip": {"name": "A"}}
        got = {l: scrape_plan.plan_scrapes(l, ["A.zip"], listing, meta, "/media", "/card/roms/gba", lambda r: True)
               for l in ("knulli", "rocknix")}
        self.assertEqual(got["rocknix"], got["knulli"])
        jobs, entries, _ = got["rocknix"]
        self.assertEqual(entries["A.zip"]["image"], "./images/A-image.png")
        self.assertEqual(entries["A.zip"]["video"], "./videos/A-video.mp4")
        self.assertTrue(any(j[1].endswith(os.path.join("images", "A-thumb.png")) for j in jobs))

    def test_stale_media_is_found_in_the_rom_folder(self):
        with tempfile.TemporaryDirectory() as base:
            for rel in ("roms/gba/A.zip", "roms/gba/images/A-image.png", "roms/gba/videos/Gone-video.mp4",
                        "roms/gba/manuals/Gone.pdf"):
                touch(os.path.join(base, rel))
            system = {"bucket": "gba", "folders": {"rocknix": "gba"}}
            stale = scrape_plan.stale_media("rocknix", [system], os.path.join(base, "roms"), os.path.join(base, "ES-DE"), base)
            self.assertEqual(sorted(os.path.relpath(p, base) for p in stale),
                             ["roms/gba/manuals/Gone.pdf", "roms/gba/videos/Gone-video.mp4"])


class NextUIMediaTest(unittest.TestCase):
    GBA_NX = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"nextui": "Game Boy Advance (GBA)"}}
    PICO_NX = {"name": "PICO-8", "bucket": "pico8", "folders": {"nextui": "PICO-8 (P8)"}}

    def plan(self, rels, listing, meta=None, present=lambda rom: True):
        return scrape_plan.plan_scrapes("nextui", rels, listing, meta or {}, "/media", "/card/Roms/GBA", present)

    def test_art_goes_in_the_system_folders_dot_media(self):
        jobs, entries, texts = self.plan(["Game.gba"], {"scrapes/gba/onion/Game.png": 5, "scrapes/gba/covers/Game.png": 9},
                                         {"Game.gba": {"name": "Game"}})
        self.assertEqual(jobs, [("scrapes/gba/onion/Game.png", os.path.join("/card/Roms/GBA", ".media", "Game.png"), 5)])
        self.assertEqual((entries, texts), ({}, []))

    def test_a_game_in_a_subfolder_is_named_by_its_playlist_in_the_system_folders_media(self):
        jobs, entries, _ = self.plan(["Final Fantasy VII/Final Fantasy VII.m3u"],
                                     {"scrapes/psx/onion/Final Fantasy VII/Final Fantasy VII.png": 3})
        self.assertEqual([p for _, p, _ in jobs], [os.path.join("/card/Roms/GBA", ".media", "Final Fantasy VII.png")])
        self.assertEqual(entries, {})

    def test_a_rom_in_a_subfolder_gets_art_in_that_subfolders_media(self):
        jobs, _, _ = self.plan(["Hacks/Game.gba", "Hacks/More/Deep.gba"],
                               {"scrapes/gba/onion/Hacks/Game.png": 3, "scrapes/gba/onion/Hacks/More/Deep.png": 4})
        self.assertEqual([p for _, p, _ in jobs], [os.path.join("/card/Roms/GBA", "Hacks", ".media", "Game.png"),
                                                   os.path.join("/card/Roms/GBA", "Hacks", "More", ".media", "Deep.png")])

    def test_a_game_folder_in_a_subfolder_gets_art_beside_the_folder(self):
        jobs, _, _ = self.plan(["Hacks/Game/Game.cue"], {"scrapes/psx/onion/Hacks/Game/Game.png": 3})
        self.assertEqual([p for _, p, _ in jobs], [os.path.join("/card/Roms/GBA", "Hacks", ".media", "Game.png")])

    def test_a_playlist_not_named_after_its_folder_gets_art_in_the_folder(self):
        jobs, _, _ = self.plan(["Pack/Game.m3u"], {"scrapes/psx/onion/Pack/Game.png": 3})
        self.assertEqual([p for _, p, _ in jobs], [os.path.join("/card/Roms/GBA", "Pack", ".media", "Game.png")])

    def test_a_rom_not_on_the_card_gets_no_art(self):
        jobs, _, _ = self.plan(["Game.gba"], {"scrapes/gba/onion/Game.png": 5}, present=lambda rom: False)
        self.assertEqual(jobs, [])

    def test_the_layout_has_no_gamelist(self):
        self.assertIsNone(scrape_plan.GAMELIST_FILES["nextui"])
        self.assertIn("nextui", scrape_plan.SCRAPE_LAYOUTS)

    def test_scrape_cost_counts_the_art(self):
        self.assertEqual(scrape_plan.scrape_cost("nextui", "gba", "Game.gba", {"scrapes/gba/onion/Game.png": 5,
                                                                              "scrapes/gba/covers/Game.png": 9}), 5)

    def build(self, system, rels, listing, base):
        with mock.patch.object(scrape_plan.downloads.inventory, "stat", return_value={f"{system['bucket']}/{r}": 3 for r in rels}):
            return scrape_plan.build_scrape_plan(
                "nextui", [system], {system["bucket"]: (dict(listing), {r: {"name": "N"} for r in rels})}, {system["bucket"]: rels},
                lambda s: os.path.join(base, "Roms", s["folders"]["nextui"]), os.path.join(base, "ES-DE"), lambda p: True, base)

    def test_a_sync_plans_no_gamelist(self):
        with tempfile.TemporaryDirectory() as base:
            plan = self.build(self.GBA_NX, ["Game.gba"], {"scrapes/gba/onion/Game.png": 5}, base)
            self.assertEqual(plan["gamelists"], {})
            self.assertEqual([os.path.relpath(p, base) for _, p, _ in plan["jobs"]],
                             [os.path.join("Roms", "Game Boy Advance (GBA)", ".media", "Game.png")])
            self.assertEqual(scrape_plan.apply_scrape_plan({**plan, "jobs": []}, base), (0, False))

    def test_a_pico8_cart_with_no_picture_is_its_own_art(self):
        with tempfile.TemporaryDirectory() as base:
            plan = self.build(self.PICO_NX, ["a.p8.png", "b.p8.png", "c.p8"], {"scrapes/pico8/onion/b.p8.png": 5}, base)
            self.assertEqual(sorted((k, os.path.relpath(p, base)) for k, p, _ in plan["jobs"]),
                             [("pico8/a.p8.png", os.path.join("Roms", "PICO-8 (P8)", ".media", "a.p8.png")),
                              ("scrapes/pico8/onion/b.p8.png", os.path.join("Roms", "PICO-8 (P8)", ".media", "b.p8.png"))])
            self.assertEqual(plan["gamelists"], {})

    def test_a_pico8_cart_in_a_subfolder_is_its_own_art_in_that_subfolder(self):
        with tempfile.TemporaryDirectory() as base:
            plan = self.build(self.PICO_NX, ["Jam/a.p8.png"], {}, base)
            self.assertEqual([(k, os.path.relpath(p, base)) for k, p, _ in plan["jobs"]],
                             [("pico8/Jam/a.p8.png", os.path.join("Roms", "PICO-8 (P8)", "Jam", ".media", "a.p8.png"))])

    def stale(self, files, roms=("Game.gba",)):
        with tempfile.TemporaryDirectory() as base:
            for rel in [os.path.join("Game Boy Advance (GBA)", r) for r in roms] + \
                    [os.path.join("Game Boy Advance (GBA)", f) for f in files]:
                touch(os.path.join(base, "Roms", rel))
            stale = scrape_plan.stale_media("nextui", [self.GBA_NX], os.path.join(base, "Roms"), None, base)
            return sorted(os.path.relpath(p, os.path.join(base, "Roms", "Game Boy Advance (GBA)")) for p in stale)

    def test_stale_media_removes_only_orphan_pngs(self):
        self.assertEqual(self.stale([".media/Old.png", ".media/Game.png", ".media/notes.txt", ".hidden"]),
                         [os.path.join(".media", "Old.png")])

    def test_stale_media_keeps_art_of_games_in_subfolders(self):
        self.assertEqual(self.stale([".media/FF.png"], roms=("FF/FF.m3u", "FF/FF (Disc 1).chd")), [])

    def test_stale_media_checks_each_subfolders_media(self):
        self.assertEqual(self.stale(["Hacks/.media/Hack.png", "Hacks/.media/Gone.png", ".media/Hack.png"],
                                    roms=("Game.gba", "Hacks/Hack.gba")),
                         [os.path.join(".media", "Hack.png"), os.path.join("Hacks", ".media", "Gone.png")])


class SpruceQoiTest(unittest.TestCase):
    GBA = {"bucket": "gba", "folders": {"spruce": "GBA"}}
    ALL = {"scrapes/gba/onion/a.png": 1, "scrapes/gba/spruce/a.qoi": 2, "scrapes/gba/spruce_med/a.qoi": 3,
           "scrapes/gba/spruce_small/a.qoi": 4}
    META = {"a.zip": {"name": "A"}}

    def plan(self, layout, listing, rels=("a.zip",), meta=None):
        return scrape_plan.plan_scrapes(layout, list(rels), listing, self.META if meta is None else meta, "/m", "/r", lambda rom: True)

    def test_spruce_installs_qoi_in_three_folders(self):
        jobs, _, _ = self.plan("spruce", self.ALL)
        self.assertEqual(jobs, [("scrapes/gba/spruce/a.qoi", os.path.join("/r", "Imgs", "a.qoi"), 2),
                                ("scrapes/gba/spruce_med/a.qoi", os.path.join("/r", "Imgs_med", "a.qoi"), 3),
                                ("scrapes/gba/spruce_small/a.qoi", os.path.join("/r", "Imgs_small", "a.qoi"), 4)])

    def test_spruce_installs_only_the_tiers_storage_has(self):
        jobs, _, _ = self.plan("spruce", {"scrapes/gba/spruce/a.qoi": 2, "scrapes/gba/spruce_small/a.qoi": 4})
        self.assertEqual([j[1] for j in jobs], [os.path.join("/r", "Imgs", "a.qoi"), os.path.join("/r", "Imgs_small", "a.qoi")])

    def test_spruce_rom_with_only_an_onion_png_gets_no_image(self):
        jobs, entries, _ = self.plan("spruce", {"scrapes/gba/onion/a.png": 1})
        self.assertEqual(jobs, [])
        self.assertEqual(entries, {"a.zip": {"name": "A"}})

    def test_spruce_gamelist_points_image_at_the_qoi(self):
        _, entries, _ = self.plan("spruce", self.ALL)
        self.assertEqual(entries, {"a.zip": {"name": "A", "image": "./Imgs/a.qoi"}})

    def test_spruce_gamelist_replaces_a_stale_png_image_tag(self):
        _, entries, _ = self.plan("spruce", self.ALL)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "miyoogamelist.xml")
            with open(path, "w") as f:
                f.write("<gameList><game><path>./a.zip</path><name>A</name><image>./Imgs/a.png</image></game></gameList>")
            scrape_plan.update_gamelist(path, entries)
            with open(path) as f:
                text = f.read()
        self.assertIn("<image>./Imgs/a.qoi</image>", text)
        self.assertNotIn("a.png", text)

    def test_spruce_rom_in_a_subfolder_gets_no_art(self):
        jobs, entries, _ = self.plan("spruce", {k.replace("/a.", "/sub/a."): v for k, v in self.ALL.items()},
                                     ["sub/a.zip"], {"sub/a.zip": {"name": "A"}})
        self.assertEqual((jobs, entries), ([], {}))

    def test_onion_still_installs_the_png(self):
        jobs, entries, _ = self.plan("onion", self.ALL)
        self.assertEqual(jobs, [("scrapes/gba/onion/a.png", os.path.join("/r", "Imgs", "a.png"), 1)])
        self.assertEqual(entries, {"a.zip": {"name": "A", "image": "./Imgs/a.png"}})

    def test_allium_and_nextui_unchanged(self):
        jobs, entries, _ = self.plan("allium", self.ALL)
        self.assertEqual(jobs, [("scrapes/gba/onion/a.png", os.path.join("/r", "Imgs", "a.png"), 1)])
        self.assertEqual(entries["a.zip"]["image"], "./Imgs/a.png")
        jobs, entries, _ = self.plan("nextui", self.ALL)
        self.assertEqual(jobs, [("scrapes/gba/onion/a.png", os.path.join("/r", ".media", "a.png"), 1)])
        self.assertEqual(entries, {})

    def stale(self, files, rom="Roms/GBA/a.zip"):
        with tempfile.TemporaryDirectory() as base:
            for rel in [*files, rom]:
                touch(os.path.join(base, rel))
            stale = scrape_plan.stale_media("spruce", [self.GBA], os.path.join(base, "Roms"), os.path.join(base, "ES-DE"), base)
            return sorted(os.path.relpath(p, base) for p in stale)

    def test_stale_spruce_pngs_are_removed(self):
        self.assertEqual(self.stale(["Roms/GBA/Imgs/a.png", "Roms/GBA/Imgs/a.jpg", "Roms/GBA/Imgs/a.qoi"]),
                         ["Roms/GBA/Imgs/a.jpg", "Roms/GBA/Imgs/a.png"])

    def test_stale_spruce_qoi_of_a_gone_rom(self):
        files = [f"Roms/GBA/{d}/{n}.qoi" for d in ("Imgs", "Imgs_med", "Imgs_small") for n in ("a", "gone")]
        self.assertEqual(self.stale(files), [f"Roms/GBA/{d}/gone.qoi" for d in ("Imgs", "Imgs_med", "Imgs_small")])

    def test_onion_keeps_its_pngs(self):
        with tempfile.TemporaryDirectory() as base:
            for rel in ("Roms/GBA/a.zip", "Roms/GBA/Imgs/a.png", "Roms/GBA/Imgs_med/a.qoi"):
                touch(os.path.join(base, rel))
            self.assertEqual(scrape_plan.stale_media("onion", [{"bucket": "gba", "folders": {"onion": "GBA"}}],
                                                     os.path.join(base, "Roms"), "", base), [])

    def test_empty_spruce_system_removes_all_three_art_folders(self):
        with tempfile.TemporaryDirectory() as base:
            for d in ("Imgs", "Imgs_med", "Imgs_small"):
                os.makedirs(os.path.join(base, "Roms", "GBA", d))
            removed = scrape_plan.prune_empty_systems("spruce", [self.GBA], os.path.join(base, "Roms"))
            self.assertEqual(len(removed), 1)
            self.assertFalse(os.path.exists(os.path.join(base, "Roms", "GBA")))


class HiddenDiscsTest(unittest.TestCase):
    PSX = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx", "onion": "PS"}}
    RELS = ["G (Disc 1).chd", "G (Disc 2).chd", "G.m3u", "sub/H (Disc 1).chd", "Solo.chd"]
    HIDDEN = {"psx": ["G (Disc 1).chd", "G (Disc 2).chd", "sub/H (Disc 1).chd"]}

    def build(self, base, layout="esde", hidden=HIDDEN, meta=None, present=lambda p: True):
        return scrape_plan.build_scrape_plan(layout, [self.PSX], {"psx": ({}, meta or {})}, {"psx": self.RELS},
                                             lambda s: os.path.join(base, "psx"), os.path.join(base, "ES-DE"),
                                             present, base, hidden=hidden)

    def entries(self, plan):
        (path, entries), = plan["gamelists"].items()
        return path, entries

    def test_discs_are_hidden_and_the_playlist_is_not(self):
        for layout in ("esde", "emudeck"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as base:
                _, entries = self.entries(self.build(base, layout))
                self.assertEqual(entries, {r: {"hidden": "true"} for r in self.HIDDEN["psx"]})

    def test_a_disc_with_scrape_data_keeps_it(self):
        with tempfile.TemporaryDirectory() as base:
            _, entries = self.entries(self.build(base, meta={"G (Disc 1).chd": {"name": "G"}}))
        self.assertEqual(entries["G (Disc 1).chd"], {"name": "G", "hidden": "true"})

    def test_only_discs_on_the_card_are_hidden(self):
        with tempfile.TemporaryDirectory() as base:
            _, entries = self.entries(self.build(base, present=lambda p: "Disc 2" not in p))
        self.assertNotIn("G (Disc 2).chd", entries)

    def test_other_layouts_hide_nothing(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(self.build(base, "onion")["gamelists"], {})

    def test_gamelist_is_kept_and_a_second_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as base:
            path, entries = self.entries(self.build(base))
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0"?>\n<gameList><game><path>./G (Disc 1).chd</path><favorite>true</favorite></game></gameList>\n')
            self.assertTrue(scrape_plan.update_gamelist(path, entries))
            root = ET.parse(path).getroot()
            first = next(g for g in root.findall("game") if g.findtext("path") == "./G (Disc 1).chd")
            self.assertEqual((first.findtext("favorite"), first.findtext("hidden")), ("true", "true"))
            self.assertFalse(any(g.findtext("path") == "./G.m3u" for g in root.findall("game")))
            self.assertFalse(scrape_plan.update_gamelist(path, entries))

    def test_hidden_only_plan_is_described_and_applied(self):
        with tempfile.TemporaryDirectory() as base:
            plan = self.build(base)
            with mock.patch("builtins.print") as pr:
                scrape_plan.describe_scrape_plan(plan)
            self.assertIn("gamelist", "\n".join(str(c.args[0]) for c in pr.call_args_list).lower())


class NoSpruceArtHintTest(unittest.TestCase):
    LISTING = {"scrapes/gba/spruce/a.qoi": 1, "scrapes/gba/onion/a.png": 1, "scrapes/gba/onion/b.png": 1,
               "scrapes/gba/covers/c.png": 1, "scrapes/gba/miximages/d.png": 1, "scrapes/gba/screenshots/e.png": 1}
    RELS = ["a.zip", "b.zip", "c.zip", "d.zip", "e.zip", "f.zip", "sub/b.zip"]

    def build(self, layout, listing=None, rels=None):
        system = {"name": "GBA", "bucket": "gba", "folders": {layout: "GBA"}}
        rels = self.RELS if rels is None else rels
        listing = self.LISTING if listing is None else listing
        with tempfile.TemporaryDirectory() as base, \
                mock.patch.object(scrape_plan.downloads.inventory, "stat", return_value={}):
            return scrape_plan.build_scrape_plan(layout, [system], {"gba": (dict(listing), {})}, {"gba": rels},
                                                 lambda s: os.path.join(base, "Roms", "GBA"), os.path.join(base, "ES-DE"),
                                                 lambda p: True, base)

    def test_counts_roms_with_a_source_picture_and_no_spruce_art(self):
        # c, d; not a (has art), b (Onion art only, which `scrape art` can't make it from), e (no picture), sub/b
        self.assertEqual(self.build("spruce")["no_spruce_art"], 2)

    def test_no_count_when_every_rom_has_spruce_art(self):
        plan = self.build("spruce", {"scrapes/gba/spruce/a.qoi": 1, "scrapes/gba/onion/a.png": 1}, ["a.zip"])
        self.assertEqual(plan["no_spruce_art"], 0)

    def test_other_layouts_have_no_count(self):
        for layout in ("onion", "allium", "nextui"):
            self.assertEqual(self.build(layout).get("no_spruce_art"), None, layout)

    def test_describe_prints_the_command(self):
        plan = {"jobs": [], "gamelists": {}, "writes": [], "no_spruce_art": 3}
        with mock.patch("builtins.print") as pr:
            scrape_plan.describe_scrape_plan(plan)
        out = "\n".join(str(c.args[0]) for c in pr.call_args_list)
        self.assertIn("3 ROM(s) have no Spruce art in storage", out)
        self.assertIn("sync-roms scrape art --for spruce", out)

    def test_describe_is_quiet_without_a_count(self):
        with mock.patch("builtins.print") as pr:
            scrape_plan.describe_scrape_plan({"jobs": [], "gamelists": {}, "writes": []})
        self.assertNotIn("Spruce art", "\n".join(str(c.args[0]) for c in pr.call_args_list))


class SprucePico8Test(Pico8CartImageTest):
    PICO = {"name": "PICO-8", "bucket": "pico8", "folders": {"spruce": "pico8", "onion": "pico8"}}

    def test_spruce_pico8_cart_picture_is_not_copied_to_imgs(self):
        jobs, entries = self.plan("spruce", ["a.p8.png"])
        self.assertEqual((jobs, entries), ([], {}))

    def test_spruce_pico8_cart_art_from_storage_is_installed_as_qoi(self):
        jobs, entries = self.plan("spruce", ["a.p8.png"], {"scrapes/pico8/spruce/a.p8.qoi": 1}, {"a.p8.png": {"name": "A"}})
        self.assertEqual(jobs, [("scrapes/pico8/spruce/a.p8.qoi", os.path.join("ROMs", "pico8", "Imgs", "a.p8.qoi"))])
        self.assertEqual(entries, {"a.p8.png": {"name": "A", "image": "./Imgs/a.p8.qoi"}})

    def test_onion_pico8_cart_without_art_still_copies_its_picture(self):
        jobs, entries = self.plan("onion", ["a.p8.png"])
        self.assertEqual(jobs, [("pico8/a.p8.png", os.path.join("ROMs", "pico8", "Imgs", "a.p8.png"))])
        self.assertEqual(entries["a.p8.png"]["image"], "./Imgs/a.p8.png")
