import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir, storage_sets  # noqa: E402
from sync_roms import store  # noqa: E402


def set_problems(game_set, systems, series):
    """What breaks the set file format rules in one loaded set (the rules `sync-roms check` is to enforce for the sets
    in storage)."""
    name, out = game_set["id"], []
    if not game_set["name"]:
        out.append(f"{name}: no name")
    keys = [k for g in game_set["games"] for k in [g["bucket"]] + g.get("files", [])]
    if len(keys) != len(set(keys)):
        out.append(f"{name}: duplicate games")
    entry_buckets = {g["bucket"] for g in game_set["games"]}
    for g in game_set["games"]:
        if g["system"] not in systems:
            out.append(f"{name}: {g['bucket']}: unknown system")
        out.extend(f"{name}: {k} isn't under {g['system']}/" for k in [g["bucket"]] + g.get("files", [])
                   if not k.startswith(g["system"] + "/"))
        if not g["title"]:
            out.append(f"{name}: {g['bucket']}: no title")
        if "series" in g and g["series"] not in series:
            out.append(f"{name}: {g['bucket']}: unknown series")
        seen = set()
        for v in g.get("variants", []):
            system = v["bucket"].split("/")[0]
            if system not in systems:
                out.append(f"{name}: {v['bucket']}: unknown variant system")
            if not v["note"].strip():
                out.append(f"{name}: {v['bucket']}: no note")
            out.extend(f"{name}: {k} isn't under {system}/" for k in v.get("files", []) if not k.startswith(system + "/"))
            if v["bucket"] in entry_buckets:
                out.append(f"{name}: {v['bucket']}: variant is a game of the set")
            if v["bucket"] in seen:
                out.append(f"{name}: duplicate variant {v['bucket']}")
            seen.add(v["bucket"])
    return out


class SetDataTest(StorageDir):
    def setUp(self):
        super().setUp()
        self.systems = {s["bucket"] for s in store.repo_json("systems")}
        self.series = list(store.repo_json("series"))
        self.good = {"name": "Mix", "description": "d", "games": [
            {"title": "A", "category": "One", "series": self.series[0], "system": "gba", "bucket": "gba/A.zip",
             "files": ["gba/A2.zip"], "variants": [{"bucket": "nds/A.nds", "note": "DS: more", "files": ["nds/A2.nds"]}]},
            {"title": "B", "system": "snes", "bucket": "snes/B.sfc"}]}

    def loaded(self, game_set):
        storage_sets(self, {"mix": game_set}, self.root)
        return store.load_sets()

    def test_a_well_formed_set_from_storage_passes(self):
        sets = self.loaded(self.good)
        self.assertEqual(len(sets), 1)
        self.assertEqual(set_problems(sets[0], self.systems, self.series), [])

    def test_each_rule_is_caught(self):
        def broken(change):
            game_set = copy.deepcopy(self.good)
            change(game_set)
            return set_problems(self.loaded(game_set)[0], self.systems, self.series)
        a = lambda s: s["games"][0]  # noqa: E731
        cases = {
            "no name": lambda s: s.update(name=""),
            "duplicate games": lambda s: s["games"].append({"title": "A", "system": "gba", "bucket": "gba/A2.zip"}),
            "unknown system": lambda s: a(s).update(system="nope"),
            "isn't under": lambda s: a(s).update(files=["snes/X.sfc"]),
            "no title": lambda s: a(s).update(title=""),
            "unknown series": lambda s: a(s).update(series="Not A Series"),
            "unknown variant system": lambda s: a(s)["variants"][0].update(bucket="nope/A.zip"),
            "no note": lambda s: a(s)["variants"][0].update(note=" "),
            "nds/": lambda s: a(s)["variants"][0].update(files=["gba/X.zip"]),
            "variant is a game of the set": lambda s: a(s)["variants"][0].update(bucket="snes/B.sfc"),
            "duplicate variant": lambda s: a(s)["variants"].append({"bucket": "nds/A.nds", "note": "again"}),
        }
        for what, change in cases.items():
            with self.subTest(what):
                self.assertTrue(any(what in p for p in broken(change)), what)


if __name__ == "__main__":
    unittest.main()
