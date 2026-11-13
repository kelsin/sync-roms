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
    def test_media_goes_in_emulation_tools_with_no_gamelist(self):
        with tempfile.TemporaryDirectory() as base:
            data = {"gba": (LISTING, META)}
            plan = scrape_plan.build_scrape_plan("emudeck", [GBA], data, {"gba": ["A.zip"]}, lambda s: "/x",
                                                 os.path.join(base, "ES-DE"), lambda p: True, base)
            media = os.path.join(base, "Emulation", "tools", "downloaded_media", "gba")
            self.assertEqual(sorted(j[1] for j in plan["jobs"]),
                             sorted([os.path.join(media, "covers", "A.png"), os.path.join(media, "screenshots", "A.jpg"),
                                     os.path.join(media, "3dboxes", "A.png")]))
        self.assertEqual((plan["gamelists"], plan["writes"]), ({}, []))

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


class SlotLabelCommandTest(unittest.TestCase):
    SYSTEMS = [sysdef("gba", slot="GBA"), sysdef("genesis")]

    def run_upload(self, files, folders=("Labels",), dry_run=False, confirm=True):
        with tempfile.TemporaryDirectory() as card:
            for f in files:
                touch(os.path.join(card, f))
            args = mock.Mock(base_dir=card, dry_run=dry_run)
            with mock.patch.object(scrape_files.store, "load_manifest", return_value={"systems": self.SYSTEMS}), \
                    mock.patch.object(scrape_files, "bucket_roms", return_value={"gba": {"A.zip"}}) as roms, \
                    mock.patch.object(scrape_files.s3, "list_sizes", return_value={}), \
                    mock.patch.object(scrape_files.ui, "confirm", return_value=confirm), \
                    mock.patch.object(scrape_files.upload, "run_uploads", return_value=0) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                code = scrape_files.upload_scrapes(args)
        return code, roms, run

    def test_uploads_the_labels_of_slot_systems_only(self):
        code, roms, run = self.run_upload(["Labels/GBA/A.png"])
        self.assertEqual(code, 0)
        self.assertEqual([s["bucket"] for s in roms.call_args[0][0]], ["gba"])
        self.assertEqual([j[0] for j in run.call_args[0][0]], ["scrapes/gba/slot/A.png"])

    def test_dry_run_and_cancel_upload_nothing(self):
        self.assertFalse(self.run_upload(["Labels/GBA/A.png"], dry_run=True)[2].called)
        self.assertFalse(self.run_upload(["Labels/GBA/A.png"], confirm=False)[2].called)

    def test_an_es_de_folder_takes_the_scrape_path(self):
        with tempfile.TemporaryDirectory() as card:
            touch(os.path.join(card, "ES-DE", "gamelists", "x"))
            touch(os.path.join(card, "Labels", "GBA", "A.png"))
            with mock.patch.object(scrape_files, "upload_slot_labels") as slot, \
                    mock.patch.object(scrape_files.store, "load_cards", return_value={}), \
                    mock.patch.object(scrape_files.store, "load_manifest", side_effect=SystemExit("scrape path")):
                with self.assertRaises(SystemExit):
                    scrape_files.upload_scrapes(mock.Mock(base_dir=card, dry_run=True))
            slot.assert_not_called()


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

    def test_upload_splits_the_shared_folder_by_system(self):
        gamelist = ("<gameList><game><path>./A.3ds</path><name>A</name></game>"
                    "<game><path>./B.3ds</path><name>B</name></game></gameList>")
        with tempfile.TemporaryDirectory() as es:
            touch(os.path.join(es, "downloaded_media", "n3ds", "covers", "A.png"))
            touch(os.path.join(es, "downloaded_media", "n3ds", "covers", "B.png"))
            os.makedirs(os.path.join(es, "gamelists", "n3ds"))
            with open(os.path.join(es, "gamelists", "n3ds", "gamelist.xml"), "w") as f:
                f.write(gamelist)
            roms = {"3ds": {"A.3ds"}, "n3ds": {"B.3ds"}}
            plan = scrape_files.plan_upload(es, roms, {}, {})
            wanted = scrape_files._upload_text_keys(es, {"scrapes/3ds/metadata.json": 1,
                                                         "scrapes/n3ds/metadata.json": 1}, roms)
        self.assertEqual(sorted(k for k, *_ in plan["files"]),
                         ["scrapes/3ds/covers/A.png", "scrapes/n3ds/covers/B.png"])
        self.assertEqual(sorted(k for k, *_ in plan["texts"]), ["scrapes/3ds/metadata.json", "scrapes/n3ds/metadata.json"])
        self.assertEqual(sorted(wanted), ["scrapes/3ds/metadata.json", "scrapes/n3ds/metadata.json"])


class StaleFolderUploadTest(unittest.TestCase):
    """A bucket-named folder an older sync left (3ds) next to the ES-DE-named one (n3ds)."""

    def plan(self, folders):
        with tempfile.TemporaryDirectory() as es:
            for name, size in folders:
                path = os.path.join(es, "downloaded_media", name, "covers", "A.png")
                os.makedirs(os.path.dirname(path))
                with open(path, "wb") as f:
                    f.write(b"x" * size)
                os.makedirs(os.path.join(es, "gamelists", name))
                with open(os.path.join(es, "gamelists", name, "gamelist.xml"), "w") as f:
                    f.write(f"<gameList><game><path>./A.3ds</path><name>A from {name}</name></game></gameList>")
            plan = scrape_files.plan_upload(es, {"3ds": {"A.3ds"}}, {}, {})
        return plan

    def test_the_old_folder_is_skipped_when_the_new_one_is_there(self):
        plan = self.plan([("3ds", 1), ("n3ds", 2)])
        self.assertEqual([(k, size) for k, _, size in plan["files"]], [("scrapes/3ds/covers/A.png", 2)])
        self.assertEqual([k for k, *_ in plan["texts"]], ["scrapes/3ds/metadata.json"])
        self.assertIn("A from n3ds", plan["texts"][0][1])
        self.assertEqual(len({k for k, *_ in plan["derived"]}), len(plan["derived"]))
        self.assertTrue(all("n3ds" in src for _, src, _, _ in plan["derived"]))
        self.assertEqual(sorted(plan["warnings"]), ["downloaded_media/3ds is from an older sync and was skipped; remove it",
                                                    "gamelists/3ds is from an older sync and was skipped; remove it"])

    def test_only_the_old_folder_still_uploads(self):
        plan = self.plan([("3ds", 1)])
        self.assertEqual([(k, size) for k, _, size in plan["files"]], [("scrapes/3ds/covers/A.png", 1)])
        self.assertIn("A from 3ds", plan["texts"][0][1])
        self.assertEqual(plan["warnings"], [])


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

    def test_empty_placeholder_art_is_skipped(self):
        with tempfile.TemporaryDirectory() as es:
            touch(os.path.join(es, "downloaded_media", "snes", "screenshots", "A.png"))
            empty = os.path.join(es, "downloaded_media", "snes", "covers", "A.png")
            os.makedirs(os.path.dirname(empty))
            open(empty, "wb").close()
            plan = scrape_files.plan_upload(es, {"snes": {"A.sfc"}}, {}, {})
        self.assertEqual([k for k, *_ in plan["files"]], ["scrapes/snes/screenshots/A.png"])
        self.assertTrue(all(src.endswith(os.path.join("screenshots", "A.png")) for _, src, _, _ in plan["derived"]))

    def test_cover_is_preferred_over_a_screenshot(self):
        plan = self.derived(["screenshots/A.png", "covers/A.png"])
        self.assertTrue(all(src.endswith(os.path.join("covers", "A.png")) for _, src, _, _ in plan["derived"]))


class EsdeExtrasUploadTest(unittest.TestCase):
    def test_themes_collections_and_settings_are_not_uploaded(self):
        with tempfile.TemporaryDirectory() as es:
            touch(os.path.join(es, "themes", "my-theme", "theme.xml"))
            touch(os.path.join(es, "downloaded_media", "snes", "covers", "A.png"))
            os.makedirs(os.path.join(es, "collections"))
            with open(os.path.join(es, "collections", "custom-Fav.cfg"), "w") as f:
                f.write("%ROMPATH%/snes/A.sfc\n")
            os.makedirs(os.path.join(es, "settings"))
            with open(os.path.join(es, "settings", "es_settings.xml"), "w") as f:
                f.write('<?xml version="1.0"?>\n<bool name="ScraperRegionFallback" value="true" />\n')
            plan = scrape_files.plan_upload(es, {"snes": {"A.sfc"}}, {}, {})
        self.assertEqual([k for k, *_ in plan["files"]], ["scrapes/snes/covers/A.png"])
        self.assertEqual(plan["texts"], [])
        self.assertFalse(any("/esde/" in k for k, *_ in plan["files"] + plan["texts"] + plan["derived"]))

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
                    "gba/": {"gba/A.zip": 4}, "scrapes/gba/": {"scrapes/gba/covers/A.png": 5}}
        manifest = {"systems": [{"bucket": "gba", "games": [{"bucket": "gba/A.zip"}], "bios": {"files": ["gba_bios.bin"]}}]}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})) as ls:
            wanted = mirroring.mirror_wanted(manifest)
        self.assertEqual(wanted, {"gba/A.zip": 4, "scrapes/gba/covers/A.png": 5, "BIOS/gba_bios.bin": 1,
                                  "os/onion/Themes/t/a.png": 2})
        self.assertNotIn("scrapes/esde/", [c.args[0] for c in ls.call_args_list])


if __name__ == "__main__":
    unittest.main()
