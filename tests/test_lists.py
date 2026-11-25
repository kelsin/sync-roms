import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import mirroring, picker, runtime, store  # noqa: E402


def game(bucket):
    return {"title": os.path.splitext(bucket.split("/", 1)[1])[0], "bucket": bucket}


def systems():
    return [{"bucket": "gba"}, {"bucket": "ps2"}]


def merged(lists):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = store.merge_lists(systems(), lists)
    return {s["bucket"]: s for s in out}, err.getvalue()


class MergeLists(unittest.TestCase):
    def test_lists_union(self):
        by, _ = merged([{"gba": [game("gba/A.zip")]}, {"gba": [game("gba/B.zip")], "ps2": [game("ps2/C.iso")]}])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip", "gba/B.zip"])
        self.assertEqual([g["bucket"] for g in by["ps2"]["games"]], ["ps2/C.iso"])

    def test_old_set_references_add_nothing(self):
        by, err = merged([{"gba": [game("gba/A.zip")], "sets": ["multi"]}])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip"])
        self.assertEqual((by["ps2"]["games"], err), ([], ""))

    def test_full_system_from_either_list(self):
        by, _ = merged([{"gba": {"full_system": True}}, {"gba": [game("gba/X.zip")]}])
        self.assertTrue(by["gba"]["full_system"])
        self.assertFalse(by["ps2"]["full_system"])

    def test_dedupe_by_bucket(self):
        by, _ = merged([{"gba": [game("gba/A.zip")]}, {"gba": [game("gba/A.zip")]}])
        self.assertEqual(len(by["gba"]["games"]), 1)

    def test_bad_shapes_ignored(self):
        for raw in ({"sets": "multi"}, {"sets": [1, None]}, {"gba": None}, {"gba": 5}):
            by, _ = merged([raw])
            self.assertEqual(by["gba"]["games"], [])
            self.assertEqual(by["ps2"]["games"], [])


class OddEntries(unittest.TestCase):
    def test_apply_games_drops_non_dict_entries(self):
        out = store.apply_games([{"bucket": "gba"}], {"gba": ["x", None, game("gba/A.zip")]})
        self.assertEqual(out[0]["games"], [game("gba/A.zip")])


class CardLists(DataDir):
    def test_card_games_bad_shapes(self):
        self.write_json("cards.json", {"a": {"games": None}, "b": {"games": []}, "c": "x", "d": {"games": {"gba": []}}})
        self.assertEqual([store.card_games(n) for n in "abcz"], [{}, {}, {}, {}])
        self.assertEqual(store.card_games("d"), {"gba": []})

    def test_card_excluded_bad_shapes_and_loaded_cards(self):
        cards = {"a": {"excluded": None}, "b": {"excluded": []}, "c": "x", "d": {"excluded": {"gba": ["gba/A.zip"]}}}
        self.write_json("cards.json", cards)
        self.assertEqual([store.card_excluded(n) for n in "abcz"], [{}, {}, {}, {}])
        self.assertEqual(store.card_excluded("d"), {"gba": ["gba/A.zip"]})
        self.assertEqual([store.card_excluded(n, cards) for n in "cdz"], [{}, {"gba": ["gba/A.zip"]}, {}])
        self.assertEqual([store.card_games(n, {"c": "x", "d": {"games": {"gba": []}}}) for n in "cdz"], [{}, {"gba": []}, {}])

    def test_cards_json_games_roundtrip(self):
        self.write_json("cards.json", {"c": {"games": {"gba": []}, "layout": "esde"}})
        store.update_card("c", device="x")
        self.assertEqual(store.load_cards()["c"], {"games": {"gba": []}, "layout": "esde", "device": "x"})

    def test_load_manifest_merges_named_cards(self):
        self.write_json("cards.json", {"c": {"games": {"gba": [game("gba/B.zip")]}}, "d": {"games": {"gb": [game("gb/Z.zip")]}}})
        by = {s["bucket"]: s for s in store.load_manifest(["c"])["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/B.zip"])
        self.assertEqual(by["gb"]["games"], [])
        by = {s["bucket"]: s for s in store.load_manifest()["systems"]}
        self.assertEqual(by["gba"]["games"], [])

    def test_load_manifest_ignores_a_stray_games_json(self):
        self.write_json("games.json", {"gba": [game("gba/A.zip")], "sets": ["nope"]})
        self.write_json("cards.json", {"c": {}})
        by = {s["bucket"]: s for s in store.load_manifest(["c"])["systems"]}
        self.assertTrue(all(s["games"] == [] and not s["full_system"] for s in by.values()))
        self.assertEqual(self.read("games.json"), {"gba": [game("gba/A.zip")], "sets": ["nope"]})

    def test_card_without_picks_yields_no_games(self):
        self.write_json("cards.json", {"c": {"device": "x"}})
        systems = store.load_manifest(["c"])["systems"]
        self.assertTrue(systems)
        self.assertTrue(all(s["games"] == [] and not s["full_system"] for s in systems))

    def test_card_excluded_games_are_dropped_for_that_card_only(self):
        self.write_json("cards.json", {"c": {"games": {"gba": [game("gba/A.zip"), game("gba/B.zip")]},
                                             "excluded": {"gba": ["gba/A.zip"]}},
                                       "d": {"games": {"gba": [game("gba/A.zip"), game("gba/B.zip")]}}})
        by = {s["bucket"]: s for s in store.load_manifest(["c"])["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/B.zip"])
        by = {s["bucket"]: s for s in store.load_manifest(["d"])["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip", "gba/B.zip"])

    def test_a_card_with_old_set_references_syncs_only_its_own_picks(self):
        self.write_json("cards.json", {"c": {"games": {"gba": [game("gba/A.zip")], "sets": ["mix", "gone"]}}})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            by = {s["bucket"]: s for s in store.load_manifest(["c"])["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip"])
        self.assertEqual(err.getvalue(), "")

    def test_saving_a_list_drops_old_set_references(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "games": {"sets": ["mix"]}}})
        store.save_lists({"c": {"gba": [game("gba/A.zip")], "sets": ["mix"]}})
        self.assertEqual(self.read("cards.json")["c"], {"layout": "esde", "games": {"gba": [game("gba/A.zip")]}})

    def test_all_card_names(self):
        self.write_json("cards.json", {"b": {}, "a": {}})
        self.assertEqual(store.all_card_names(), ["a", "b"])


class Wiring(unittest.TestCase):
    def test_saved_setup_without_layout_or_device(self):
        layouts = {"esde": {}}
        for saved in ({"games": {}}, {"device": "x"}, {"android_media": "never"}, None):
            self.assertIsNone(picker.saved_setup(saved, [], layouts))

    def test_mirror_unions_all_cards(self):
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(store, "all_card_names", return_value=["a", "b"]), \
                mock.patch.object(store, "load_manifest", return_value={"systems": []}) as lm, \
                mock.patch.object(mirroring, "mirror_wanted", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            open(os.path.join(root, runtime.MIRROR_MARKER), "w").close()
            mirroring.refresh_mirror(root, dry_run=True)
        lm.assert_called_once_with(["a", "b"])


if __name__ == "__main__":
    unittest.main()
