import importlib.util
import itertools
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import store, themeart  # noqa: E402

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
        self.assertEqual(data["tags"]["shmups"], {"name": "Shmups", "emoji": themeart.art_emoji("shmups", migrate.NO_ART_EMOJI),
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
        self.assertEqual(sorted(set(data["tags"]) - set(migrate.EXTRA_TAGS)), ["a"])
        self.assertEqual(sorted(r["name"] for r in report["pruned"]), ["Other", "RPG", "Saturn"])

    def test_alias_merges(self):
        sets = [make_set("mario", "Mario", [game("x/1.zip", series="Super Mario")]),
                make_set("vn", "Visual Novels", [game("x/2.zip", category="Visual Novel")])]
        data, report = migrate.build(sets, {})
        self.assertEqual(sorted(set(data["tags"]) - set(migrate.EXTRA_TAGS)), ["mario", "vn"])
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
        self.assertNotIn(migrate.NO_ART_EMOJI, migrate.EMOJI.values())
        sets = [make_set("a", "A", [game("x/1.zip", category=n) for n in migrate.EMOJI])]
        data, _ = migrate.build(sets)
        emojis = [t["emoji"] for t in data["tags"].values()]
        self.assertEqual(len(set(emojis)), len(emojis))
        with self.assertRaises(ValueError):
            migrate.build([make_set("a", "A", [game("x/1.zip", category="Nope")])])

    def test_extra_tags_have_no_games(self):
        data, _ = migrate.build([make_set("a", "A", many("x", 1))], {})
        self.assertEqual(data["tags"]["rpg"], {"name": "Role-Playing Games", "emoji": "\u2694\ufe0f"})
        self.assertEqual(data["tags"]["action-adventure"], {"name": "Action Adventure", "emoji": "\U0001F93A"})
        self.assertEqual(data["tags"]["simulation"], {"name": "Simulation", "emoji": "\U0001F6E0\ufe0f"})
        self.assertEqual(data["tags"]["educational"], {"name": "Educational", "emoji": "\U0001F393"})
        self.assertFalse({i for rec in data["games"].values() for i in rec["tags"]} & set(migrate.EXTRA_TAGS))

    def test_extra_tag_emoji_clash_raises(self):
        a = make_set("a", "A", many("x", 1), art="favorites")
        with mock.patch.object(themeart, "art_emoji", return_value=migrate.EXTRA_TAGS["rpg"]["emoji"]):
            with self.assertRaises(ValueError):
                migrate.build([a], {})

    def test_extra_tag_id_clash_raises(self):
        with self.assertRaises(ValueError):
            migrate.build([make_set("rpg", "RPG Set", many("x", 1), art="shmups")], {})


class ReadSetsTests(helpers.StorageFolder):
    def test_read_sets(self):
        for set_id, game_set in (("b", make_set("b", "Bee", [game("x/1.zip")], art="shmups")),
                                 ("a", make_set("a", "Aye", many("y", 2)))):
            helpers.touch(os.path.join(self.root.name, "sets", set_id + ".json"),
                          json.dumps({k: v for k, v in game_set.items() if k != "id"}))
        sets = migrate.read_sets()
        self.assertEqual([s["id"] for s in sets], ["a", "b"])
        self.assertEqual([s["name"] for s in sets], ["Aye", "Bee"])
        self.assertEqual(sets[1]["art"], "shmups")
        self.assertEqual(sets[0]["art"], "favorites")
        self.assertEqual([g["bucket"] for g in sets[0]["games"]], ["y/g0.zip", "y/g1.zip"])


class DeleteSetsTests(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        self.sets = [make_set("a", "Aye", many("y", 2)), make_set("b", "Bee", [game("x/1.zip")], art="shmups")]
        self.texts = {}
        for s in self.sets:
            self.texts[s["id"]] = json.dumps({k: v for k, v in s.items() if k != "id"})
            helpers.touch(os.path.join(self.root.name, "sets", s["id"] + ".json"), self.texts[s["id"]])
        helpers.touch(os.path.join(self.root.name, "sets", "notes.txt"), "keep")
        self.archive = os.path.join(store.data_dir(), "sets-archive")

    def put_tags(self, data):
        helpers.storage_tags(self, data, self.root.name)

    def set_exists(self, set_id):
        return os.path.exists(os.path.join(self.root.name, "sets", set_id + ".json"))

    def test_missing_game_refuses_and_deletes_nothing(self):
        data, _ = migrate.build(migrate.read_sets())
        del data["games"]["x/1.zip"]
        self.put_tags(data)
        with self.assertRaises(SystemExit) as cm:
            migrate.delete_sets(False)
        self.assertIn("x/1.zip", str(cm.exception))
        self.assertTrue(self.set_exists("a") and self.set_exists("b"))
        self.assertFalse(os.path.exists(self.archive))

    def test_missing_tag_refuses(self):
        data, _ = migrate.build(migrate.read_sets())
        del data["tags"]["b"]
        self.put_tags(data)
        with self.assertRaises(SystemExit) as cm:
            migrate.delete_sets(False)
        self.assertIn("b", str(cm.exception))
        self.assertTrue(self.set_exists("a") and self.set_exists("b"))

    def test_complete_tags_delete_and_archive(self):
        data, _ = migrate.build(migrate.read_sets())
        self.put_tags(data)
        self.assertEqual(migrate.delete_sets(False), ["sets/a.json", "sets/b.json"])
        self.assertFalse(self.set_exists("a") or self.set_exists("b"))
        self.assertTrue(os.path.exists(os.path.join(self.root.name, "sets", "notes.txt")))
        for set_id, text in self.texts.items():
            with open(os.path.join(self.archive, set_id + ".json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), text)

    def test_dry_run_changes_nothing(self):
        data, _ = migrate.build(migrate.read_sets())
        self.put_tags(data)
        self.assertEqual(migrate.delete_sets(True), ["sets/a.json", "sets/b.json"])
        self.assertTrue(self.set_exists("a") and self.set_exists("b"))
        self.assertFalse(os.path.exists(self.archive))


if __name__ == "__main__":
    unittest.main()
