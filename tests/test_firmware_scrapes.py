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

    def test_spruce_writes_a_miyoogamelist_with_name_and_image_only(self):
        meta = {"a.zip": {"name": "A", "developer": "Dev", "rating": 0.8}}
        _, entries, _ = scrape_plan.plan_scrapes("spruce", ["a.zip", "b.zip", "sub/c.zip"], {"scrapes/gba/onion/a.png": 5},
                                                 meta, "/m", "/r", lambda rom: True)
        self.assertEqual(entries, {"a.zip": {"name": "A", "image": "./Imgs/a.png"}})
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

    def test_mirror_wanted_includes_the_newest_spruceos_7z(self):
        listings = {"os/spruceos/": {"os/spruceos/spruceV4.5.6.7z": 1, "os/spruceos/spruceV4.6.0.7z": 2,
                                     "os/spruceos/spruceOTA-v4.5.6-to-v4.6.0.7z": 3}}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})):
            wanted = mirroring.mirror_wanted({"systems": []})
        self.assertEqual(wanted, {"os/spruceos/spruceV4.6.0.7z": 2})

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
