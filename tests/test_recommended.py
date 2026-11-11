import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import store  # noqa: E402

SYSTEMS = store.repo_json("systems")
ALL = [s["bucket"] for s in SYSTEMS]


def dev(screen=None, screen2=None, systems=ALL):
    d = {"id": "x", "systems": list(systems)}
    if screen:
        d["screen"] = screen
    if screen2:
        d["screen2"] = screen2
    return d


class Recommended(unittest.TestCase):
    def test_native_ratio_match(self):
        got = store.recommended_systems(dev("4:3"), SYSTEMS)
        self.assertEqual(got, {s["bucket"] for s in SYSTEMS if s.get("ratio") == "4:3"})
        self.assertLessEqual({"nes", "snes", "genesis", "psx"}, got)
        self.assertNotIn("gba", got)

    def test_gba_and_game_boy_ratios(self):
        self.assertIn("gba", store.recommended_systems(dev("3:2"), SYSTEMS))
        self.assertLessEqual({"gb", "gbc"}, store.recommended_systems(dev("10:9"), SYSTEMS))

    def test_dual_screen_adds_ds_and_3ds(self):
        self.assertNotIn("nds", store.recommended_systems(dev("16:9"), SYSTEMS))
        got = store.recommended_systems(dev("16:9", "4:3"), SYSTEMS)
        self.assertLessEqual({"nds", "n3ds"}, got)

    def test_3_5_overrides(self):
        got = store.recommended_systems(dev("3:5"), SYSTEMS)
        self.assertLessEqual({"fbneo", "mame", "nds", "n3ds"}, got)

    def test_1_1_overrides(self):
        self.assertLessEqual({"gb", "gbc"}, store.recommended_systems(dev("1:1"), SYSTEMS))

    def test_no_screen_or_no_ratio_matches_nothing(self):
        self.assertEqual(store.recommended_systems(dev(), SYSTEMS), set())
        bare = [{"bucket": "a"}, {"bucket": "b", "ratio": "4:3"}]
        self.assertEqual(store.recommended_systems(dev("4:3", systems=["a", "b"]), bare), {"b"})

    def test_unknown_ids_are_dropped(self):
        got = store.recommended_systems(dev("3:5", systems=["fbneo", "ghost"]), [{"bucket": "fbneo"}])
        self.assertEqual(got, {"fbneo"})
        got = store.recommended_systems(dev("3:5"), [{"bucket": "fbneo"}])
        self.assertEqual(got, {"fbneo"})

    def test_limited_to_what_the_device_can_play(self):
        self.assertEqual(store.recommended_systems(dev("4:3", systems=["nes", "gba"]), SYSTEMS), {"nes"})

    def test_defaults_are_the_ceiling_and_overlay_does_not_widen_it(self):
        defaults = store.device_defaults(SYSTEMS)
        for d in store.repo_json("devices"):
            got = store.recommended_systems(dict(d), SYSTEMS)
            self.assertLessEqual(got, set(defaults.get(d["id"], {"systems": []})["systems"]), d["id"])
        d = dict(next(x for x in store.repo_json("devices") if x["id"] == "anbernic-rg35xx-sp"))
        base = store.recommended_systems(dict(d), SYSTEMS)
        manifest = [dict(d)]
        store.apply_device_overlay(manifest, SYSTEMS, {d["id"]: {"add": ["gba"], "remove": ["nes"]}})
        got = store.recommended_systems(manifest[0], SYSTEMS)
        self.assertNotIn("nes", got)
        self.assertNotIn("gba", got)  # added to can-play, but a 3:2 system is not 4:3
        self.assertEqual(got, base - {"nes"})


if __name__ == "__main__":
    unittest.main()
