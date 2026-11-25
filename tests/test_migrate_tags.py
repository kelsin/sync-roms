import importlib.util
import itertools
import os
import unittest

from sync_roms import themeart

_spec = importlib.util.spec_from_file_location(
    "migrate_sets_to_tags", os.path.join(os.path.dirname(__file__), "..", "tools", "migrate_sets_to_tags.py"))
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)

_pool = itertools.count(0x1F300)


def emoji_for(*names):
    """A fresh emoji for each name, standing in for the EMOJI table."""
    return {n: chr(next(_pool)) for n in names}


def game(bucket, **kw):
    return {"title": bucket, "system": bucket.partition("/")[0], "bucket": bucket, **kw}


ART = {"a": "favorites", "b": "backlog", "mario": "completed", "vn": "kids"}  # arts with an emoji, so sets differ


def make_set(set_id, name, games, **kw):
    return {"id": set_id, "name": name, "description": "", "games": games, "art": ART.get(set_id, set_id), **kw}


def many(system, n, **kw):
    return [game(f"{system}/g{i}.zip", **kw) for i in range(n)]


class BuildTests(unittest.TestCase):
    def test_set_becomes_tag(self):
        data, _ = migrate.build([make_set("shmups", "Shmups", many("snes", 2), art="shmups", description="Shoot")], {})
        self.assertEqual(data["tags"]["shmups"], {"name": "Shmups", "emoji": themeart.art_emoji("shmups", themeart.SET_EMOJI),
                                                  "description": "Shoot", "art": "shmups"})
        self.assertEqual(data["games"]["snes/g0.zip"]["tags"], ["shmups"])

    def test_series_threshold(self):
        sets = [make_set("a", "A", many("x", 15, series="Big") + many("y", 14, series="Small") + many("z", 3, series="Tiny")),
                make_set("b", "B", [game("q/1.zip", category="Tiny")])]
        data, report = migrate.build(sets, emoji_for("Big", "Tiny"))
        self.assertIn("big", data["tags"])
        self.assertNotIn("small", data["tags"])
        self.assertEqual({r["name"]: r["detail"] for r in report["pruned"]}["Small"], "fewer than 15 games")
        self.assertEqual({r["name"]: r["detail"] for r in report["merged"]}["Tiny"], "Tiny")
        self.assertEqual(data["games"]["z/g0.zip"]["tags"], ["a", "tiny"])

    def test_system_generic_and_ft_genre_categories_pruned(self):
        sets = [make_set("a", "A", [game("x/1.zip", category="Saturn"), game("x/2.zip", category="Other"),
                                    game("x/3.zip", category="RPG")])]
        data, report = migrate.build(sets, {})
        self.assertEqual(sorted(data["tags"]), ["a"])
        self.assertEqual(sorted(r["name"] for r in report["pruned"]), ["Other", "RPG", "Saturn"])

    def test_alias_merges(self):
        sets = [make_set("mario", "Mario", [game("x/1.zip", series="Super Mario")]),
                make_set("vn", "Visual Novels", [game("x/2.zip", category="Visual Novel")])]
        data, report = migrate.build(sets, {})
        self.assertEqual(sorted(data["tags"]), ["mario", "vn"])
        self.assertEqual(data["games"]["x/1.zip"]["tags"], ["mario"])
        self.assertEqual({r["name"]: r["detail"] for r in report["merged"]},
                         {"Super Mario": "Mario", "Visual Novel": "Visual Novels"})

    def test_game_record_is_union(self):
        v1 = {"bucket": "v/1.zip", "note": "one"}
        v2 = {"bucket": "v/2.zip", "note": "two"}
        sets = [make_set("a", "A", [game("x/1.zip", files=["x/1b.zip"], variants=[v1])]),
                make_set("b", "B", [game("x/1.zip", files=["x/1b.zip", "x/1c.zip"], variants=[v1, v2])])]
        data, _ = migrate.build(sets, {})
        rec = data["games"]["x/1.zip"]
        self.assertEqual(rec["tags"], ["a", "b"])
        self.assertEqual(rec["files"], ["x/1b.zip", "x/1c.zip"])
        self.assertEqual([v["bucket"] for v in rec["variants"]], ["v/1.zip", "v/2.zip"])

    def test_emoji_unique_and_complete(self):
        self.assertEqual(len(set(migrate.EMOJI.values())), len(migrate.EMOJI))
        self.assertNotIn(themeart.SET_EMOJI, migrate.EMOJI.values())
        self.assertTrue(set(themeart._emoji().values()).isdisjoint(migrate.EMOJI.values()))  # no set's or art's emoji
        sets = [make_set("a", "A", [game("x/1.zip", category=n) for n in migrate.EMOJI])]
        data, _ = migrate.build(sets)
        emojis = [t["emoji"] for t in data["tags"].values()]
        self.assertEqual(len(set(emojis)), len(emojis))
        with self.assertRaises(ValueError):
            migrate.build([make_set("a", "A", [game("x/1.zip", category="Nope")])])


if __name__ == "__main__":
    unittest.main()
