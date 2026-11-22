import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import tempfile  # noqa: E402
from sync_roms import muos_collections  # noqa: E402


class MountTests(unittest.TestCase):
    def test_mount_defaults_to_sd1(self):
        self.assertEqual(muos_collections.mount({}), "/mnt/mmc")

    def test_mount_sd2(self):
        self.assertEqual(muos_collections.mount({"muos_storage": "sd2"}), "/mnt/sdcard")

    def test_mount_unknown_is_none(self):
        self.assertIsNone(muos_collections.mount({"muos_storage": "usb"}))

    def test_mount_non_string_is_none(self):
        self.assertIsNone(muos_collections.mount({"muos_storage": ["sd1"]}))


class EntryTests(unittest.TestCase):
    def test_fnv1a32_known_values(self):
        self.assertEqual(muos_collections.fnv1a32(b""), 2166136261)
        self.assertEqual(muos_collections.fnv1a32(b"a"), 0xE40C292C)

    def test_entry_lines_for_a_top_level_rom(self):
        self.assertEqual(muos_collections.entry_lines("/mnt/mmc", "GBA", "Game.gba"),
                         ["/mnt/mmc/ROMS/GBA/Game.gba", "GBA", "Game"])

    def test_entry_lines_for_a_subfolder_rom(self):
        lines = muos_collections.entry_lines("/mnt/mmc", "GBA", "hacks/Game.gba")
        self.assertEqual(lines[0], "/mnt/mmc/ROMS/GBA/hacks/Game.gba")
        self.assertEqual(lines[1], "GBA/hacks")

    def test_entry_path_name_has_stem_and_eight_hex_digits(self):
        path = muos_collections.entry_path("/card", "Fav", "GBA", "Game.gba", "/mnt/mmc")
        self.assertRegex(path, r"^/card/MUOS/info/collection/Fav/Game-[0-9A-F]{8}\.cfg$")

    def test_hash_is_over_utf8_bytes(self):
        path = muos_collections.entry_path("", "Fav", "GBA", "Pok\u00e9mon.gba", "/mnt/mmc")
        line = "/mnt/mmc/ROMS/GBA/Pok\u00e9mon.gba"
        self.assertTrue(path.endswith(f"-{muos_collections.fnv1a32(line.encode('utf-8')):08X}.cfg"))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def folder(self, name):
        path = os.path.join(self.base, "MUOS", "info", "collection", name)
        os.makedirs(path, exist_ok=True)
        return path

    def test_plan_skips_an_unowned_existing_collection_folder(self):
        open(os.path.join(self.folder("Fav"), "Mine-00000000.cfg"), "w").close()
        wanted = {"Fav": {"MUOS/info/collection/Fav/Game-00000000.cfg": "x"}}
        plan = muos_collections.plan(self.base, wanted, [])
        self.assertEqual(plan["writes"], [])
        self.assertEqual(plan["owned"], [])
        self.assertEqual(len(plan["warnings"]), 1)

    def test_plan_deletes_a_dropped_collection_files(self):
        cfg = os.path.join(self.folder("Old"), "Game-00000000.cfg")
        open(cfg, "w").close()
        plan = muos_collections.plan(self.base, {}, ["Old"])
        self.assertEqual(plan["deletes"], [cfg])
        self.assertEqual(plan["disable"], {"Old"})

    def test_a_dropped_then_wanted_again_collection_is_written_without_a_warning(self):
        rel = "MUOS/info/collection/Old/Game-00000000.cfg"
        cfg = os.path.join(self.folder("Old"), "Game-00000000.cfg")
        open(cfg, "w").close()
        muos_collections.apply(muos_collections.plan(self.base, {}, ["Old"]))
        self.assertFalse(os.path.exists(os.path.dirname(cfg)))
        os.makedirs(os.path.dirname(cfg))  # an empty folder left by hand is free to take too
        plan = muos_collections.plan(self.base, {"Old": {rel: "a\nb\nc"}}, [])
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["owned"], ["Old"])
        self.assertEqual(len(plan["writes"]), 1)

    def test_plan_writes_and_applies_an_owned_collection(self):
        rel = "MUOS/info/collection/Fav/Game-00000000.cfg"
        plan = muos_collections.plan(self.base, {"Fav": {rel: "a\nb\nc"}}, [])
        self.assertEqual(plan["owned"], ["Fav"])
        muos_collections.apply(plan)
        with open(os.path.join(self.base, rel), newline="") as f:
            self.assertEqual(f.read(), "a\nb\nc")
        self.assertEqual(muos_collections.plan(self.base, {"Fav": {rel: "a\nb\nc"}}, ["Fav"])["writes"], [])

    def test_wanted_builds_entries_for_games_on_the_card(self):
        systems = [{"bucket": "gba", "folders": {"muos": "GBA"}}]
        colls = [{"name": "Fav", "games": [{"system": "gba", "bucket": "gba/Game.gba"}]}]
        got = muos_collections.wanted(colls, systems, lambda s, rel: True, "/mnt/mmc")
        (path, text), = got["Fav"].items()
        self.assertEqual(text, "/mnt/mmc/ROMS/GBA/Game.gba\nGBA\nGame")
        self.assertTrue(path.startswith("MUOS/info/collection/Fav/Game-"))

    def test_wanted_merges_names_that_sanitise_alike_and_drops_an_empty_one(self):
        systems = [{"bucket": "gba", "folders": {"muos": "GBA"}}, {"bucket": "ngp", "folders": {"muos": None}}]
        games = [{"system": "gba", "bucket": "gba/A.gba"}, {"system": "ngp", "bucket": "ngp/N.ngp"},
                 {"system": "gba", "bucket": "gba/Gone.gba"}, {"system": "gba", "bucket": "gba/A.gba"}]
        colls = [{"name": "Fa.v", "games": games}, {"name": "Fav", "games": [{"system": "gba", "bucket": "gba/sub/B.gba"}]},
                 {"name": "...", "games": games}, {"name": "Empty", "games": games[1:3]}]
        got = muos_collections.wanted(colls, systems, lambda s, rel: rel != "Gone.gba", "/mnt/mmc")
        self.assertEqual(list(got), ["Fav"])
        self.assertEqual(list(got["Fav"].values()),
                         ["/mnt/mmc/ROMS/GBA/A.gba\nGBA\nA", "/mnt/mmc/ROMS/GBA/sub/B.gba\nGBA/sub\nB"])

    def test_the_skipped_collection_is_warned_about_before_the_recorded_names(self):
        open(os.path.join(self.folder("Mine"), "Mine-00000000.cfg"), "w").close()
        cfg = os.path.join(self.folder("Old"), "Game-00000000.cfg")
        open(cfg, "w").close()
        wanted = {"Mine": {"MUOS/info/collection/Mine/Game-00000000.cfg": "x"}}
        plan = muos_collections.plan(self.base, wanted, ["a/b", "Old", "Old", ""])
        self.assertEqual([w.split(";")[0].split(" that ")[0] for w in plan["warnings"]],
                         ["muOS already has a collection folder Mine", "ignoring the recorded collection name 'a/b'",
                          "ignoring the recorded collection name ''"])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([cfg], {"Old"}, []))

    def test_an_entry_that_differs_only_in_size_or_text_is_rewritten(self):
        rel = "MUOS/info/collection/Fav/Game-00000000.cfg"
        muos_collections.apply(muos_collections.plan(self.base, {"Fav": {rel: "a\nb\nc"}}, []))
        for text in ("a\nb\ncd", "a\nb\nd"):
            plan = muos_collections.plan(self.base, {"Fav": {rel: text}}, ["Fav"])
            self.assertEqual(plan["writes"], [(os.path.join(self.base, rel), text)])


if __name__ == "__main__":
    unittest.main()
