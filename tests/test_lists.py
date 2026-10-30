import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli as sync_roms  # noqa: E402


def game(bucket):
    return {"title": os.path.splitext(bucket.split("/", 1)[1])[0], "bucket": bucket}


def systems():
    return [{"bucket": "gba"}, {"bucket": "ps2"}]


def merged(lists, sets=()):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = sync_roms.merge_lists(systems(), lists, list(sets))
    return {s["bucket"]: s for s in out}, err.getvalue()


MULTI = {"id": "multi", "name": "Multi", "games": [
    {"title": "Multi", "system": "ps2", "bucket": "ps2/M.m3u", "files": ["ps2/M (Disc 1).chd", "ps2/M (Disc 2).chd"]},
    {"title": "Other", "system": "nes", "bucket": "nes/O.zip"},
]}


class MergeLists(unittest.TestCase):
    def test_core_plus_card_union(self):
        by, _ = merged([{"gba": [game("gba/A.zip")]}, {"gba": [game("gba/B.zip")], "ps2": [game("ps2/C.iso")]}])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip", "gba/B.zip"])
        self.assertEqual([g["bucket"] for g in by["ps2"]["games"]], ["ps2/C.iso"])

    def test_set_ref_expands_with_files(self):
        by, _ = merged([{"sets": ["multi"]}], [MULTI])
        self.assertEqual([g["bucket"] for g in by["ps2"]["games"]],
                         ["ps2/M.m3u", "ps2/M (Disc 1).chd", "ps2/M (Disc 2).chd"])
        self.assertEqual(by["gba"]["games"], [])

    def test_full_system_from_either_list(self):
        by, _ = merged([{"gba": {"full_system": True}}, {"gba": [game("gba/X.zip")]}])
        self.assertTrue(by["gba"]["full_system"])
        self.assertFalse(by["ps2"]["full_system"])

    def test_dedupe_by_bucket(self):
        by, _ = merged([{"gba": [game("gba/A.zip")]}, {"gba": [game("gba/A.zip")]}, {"sets": ["s"]}],
                       [{"id": "s", "games": [{"system": "gba", "bucket": "gba/A.zip"}]}])
        self.assertEqual(len(by["gba"]["games"]), 1)

    def test_unknown_set_warns(self):
        by, err = merged([{"sets": ["nope"]}], [MULTI])
        self.assertIn("nope", err)
        self.assertEqual(by["ps2"]["games"], [])

    def test_bad_shapes_ignored(self):
        for raw in ({"sets": "multi"}, {"sets": [1, None]}, {"gba": None}, {"gba": 5}):
            by, _ = merged([raw], [MULTI])
            self.assertEqual(by["gba"]["games"], [])
            self.assertEqual(by["ps2"]["games"], [])


class CardLists(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(sync_roms, "data_dir", lambda: self.tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, name, data):
        with open(os.path.join(self.tmp.name, name), "w") as f:
            json.dump(data, f)

    def test_card_games_bad_shapes(self):
        self.write("cards.json", {"a": {"games": None}, "b": {"games": []}, "c": "x", "d": {"games": {"gba": []}}})
        self.assertEqual([sync_roms.card_games(n) for n in "abcz"], [{}, {}, {}, {}])
        self.assertEqual(sync_roms.card_games("d"), {"gba": []})

    def test_cards_json_games_roundtrip(self):
        self.write("cards.json", {"c": {"games": {"gba": []}, "layout": "esde"}})
        sync_roms.update_card("c", device="x")
        self.assertEqual(sync_roms.load_cards()["c"], {"games": {"gba": []}, "layout": "esde", "device": "x"})

    def test_load_manifest_merges_named_cards(self):
        self.write("games.json", {"gba": [game("gba/A.zip")]})
        self.write("cards.json", {"c": {"games": {"gba": [game("gba/B.zip")]}}, "d": {"games": {"gb": [game("gb/Z.zip")]}}})
        by = {s["bucket"]: s for s in sync_roms.load_manifest(["c"])["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip", "gba/B.zip"])
        self.assertEqual(by["gb"]["games"], [])
        by = {s["bucket"]: s for s in sync_roms.load_manifest()["systems"]}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip"])

    def test_all_card_names(self):
        self.write("cards.json", {"b": {}, "a": {}})
        self.assertEqual(sync_roms.all_card_names(), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
