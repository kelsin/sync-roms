import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "update-variants",
                      "scripts", "find_candidates.py")
tool = helpers.load_script(SCRIPT)

A, B, C = "nes/Zelda.nes", "gba/Zelda.gba", "snes/Other.sfc"


def rec(*tags, **extra):
    return {"tags": list(tags), **extra}


class Candidates(unittest.TestCase):
    def find(self, records, stored, checked=None):
        return tool.find(records, set(stored), checked or {})

    def cands(self, out, game):
        return [c["bucket"] for m in out["matches"] if m["game"] == game for c in m["candidates"]]

    def test_tagged_rom_is_offered_for_a_related_game_not_itself(self):
        out = self.find({A: rec("x"), B: rec("x")}, [A, B])
        self.assertEqual(self.cands(out, A), [B])
        self.assertEqual(self.cands(out, B), [A])
        self.assertEqual(out["unmatched"], 0)

    def test_listed_variant_files_and_own_files_are_not_offered(self):
        records = {A: rec("x", variants=[{"bucket": B, "note": "GBA: adds"}], files=["nes/Zelda (Disc 2).nes"]),
                   C: rec("x")}
        out = self.find(records, [A, B, C, "nes/Zelda (Disc 2).nes"])
        self.assertEqual(out["matches"], [])

    def test_variant_of_one_game_can_still_match_another(self):
        records = {A: rec("x", variants=[{"bucket": B, "note": "n"}]), "gba/Zelda.gba2": rec("x")}
        out = self.find({**records, "snes/Zelda.sfc": rec("x")}, [A, B, "snes/Zelda.sfc"])
        self.assertEqual(self.cands(out, A), ["snes/Zelda.sfc"])

    def test_a_record_is_not_offered_for_a_game_that_is_already_its_variant(self):
        out = self.find({A: rec("x", variants=[{"bucket": B, "note": "GBA: adds"}]), B: rec("x")}, [A, B])
        self.assertEqual(out["matches"], [])

    def test_untagged_rom_is_offered_and_unmatched_counted(self):
        out = self.find({A: rec("x")}, [A, B, C])
        self.assertEqual(self.cands(out, A), [B])
        self.assertEqual(out["unmatched"], 1)

    def test_checked_rom_is_not_offered(self):
        out = self.find({A: rec("x"), B: rec("x")}, [A, B], {B: "judged"})
        self.assertEqual(self.cands(out, A), [])
        self.assertEqual(self.cands(out, B), [A])

    def test_stale_variant(self):
        out = self.find({A: rec("x", variants=[{"bucket": B, "note": "n"}])}, [A])
        self.assertEqual(out["stale"], [{"game": A, "bucket": B}])


if __name__ == "__main__":
    unittest.main()
