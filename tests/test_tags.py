import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from sync_roms import store, tags, usersettings  # noqa: E402

TAGS = {"shmups": {"name": "Shmups", "emoji": "🚀", "description": "Shoot them up"},
        "cave": {"name": "Cave", "emoji": "🐝"}}
A, B, C = "nes/A (USA).zip", "nes/B (USA).zip", "snes/C (USA).sfc"


def sample():
    return {"tags": json.loads(json.dumps(TAGS)),
            "games": {B: {"tags": ["shmups"]},
                      A: {"tags": ["cave", "shmups"], "files": ["nes/A (Disc 2).zip"],
                          "variants": [{"bucket": "nes/A [T-En].zip", "note": "fan translation"}]}},
            "declined": {C: ["cave"]}}


class Format(unittest.TestCase):
    def test_round_trip(self):
        data = sample()
        text = tags.dump(data)
        self.assertEqual(tags.parse(text), data)
        self.assertTrue(text.endswith("\n"))
        lines = text.splitlines()
        self.assertEqual(sum(A in line for line in lines), 1)
        self.assertLess(text.index(A), text.index(B))

    def test_parse_drops_malformed(self):
        data = tags.parse(json.dumps({
            "tags": {"ok": {"name": "Ok", "emoji": "x"}, "noemoji": {"name": "N"}},
            "games": {A: {"tags": "ok"}, B: {"tags": ["ok"]}},
            "declined": {C: "ok"}}))
        self.assertEqual(list(data["tags"]), ["ok"])
        self.assertEqual(list(data["games"]), [B])
        self.assertEqual(data["declined"], {})
        with self.assertRaises(ValueError):
            tags.parse("{nope")


class Reads(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        helpers.storage_tags(self, sample(), root=self.root.name)

    def test_emoji_of(self):
        self.assertEqual(tags.emoji_of(A), "🐝🚀")
        self.assertEqual(tags.emoji_of("nes/A (Disc 2).zip"), "🐝🚀")
        self.assertEqual(tags.emoji_of("nes/none.zip"), "")

    def test_tags_of_and_record(self):
        self.assertEqual(tags.tags_of(A), ["cave", "shmups"])
        self.assertEqual(tags.tags_of("nes/none.zip"), [])
        self.assertIsNone(tags.record("nes/none.zip"))
        self.assertEqual(tags.record(B), {"tags": ["shmups"]})

    def test_games_with(self):
        self.assertEqual(tags.games_with({"shmups"}, {"cave"}), {B})
        self.assertEqual(tags.games_with({"shmups"}, set()), {A, B, "nes/A (Disc 2).zip"})

    def test_variant_index_shape(self):
        variants, parents = tags.variant_index()
        self.assertEqual(variants[A][0]["note"], "fan translation")
        self.assertNotIn(B, variants)
        v = "nes/A [T-En].zip"
        self.assertEqual(parents[v]["bucket"], A)
        self.assertEqual(parents[v]["system"], "nes")
        self.assertEqual(parents[v]["title"], "A (USA)")


class Writes(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        self.storage = self.root.name

    def stored(self):
        with open(os.path.join(self.storage, tags.KEY), encoding="utf-8") as f:
            return tags.parse(f.read())

    def test_last_tag_without_variants_removes_record(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.change_game_tags(B, remove={"shmups"})
        self.assertNotIn(B, self.stored()["games"])

    def test_last_tag_with_variants_keeps_empty_tags(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.change_game_tags(A, remove={"cave", "shmups"})
        self.assertEqual(self.stored()["games"][A]["tags"], [])
        self.assertTrue(self.stored()["games"][A]["variants"])

    def test_missing_file_is_empty(self):
        helpers.storage_tags(self, None, root=self.storage)
        self.assertEqual((tags.load()["tags"], tags.load()["games"]), ({}, {}))
        tags.change_game_tags(A, add={"x"})
        self.assertEqual(self.stored()["games"], {A: {"tags": ["x"]}})

    def test_write_applies_to_fresh_copy(self):
        data = sample()
        helpers.storage_tags(self, data, root=self.storage)
        tags.load()
        data["games"][C] = {"tags": ["cave"]}
        with open(os.path.join(self.storage, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump(data))
        tags.change_game_tags("gb/D.zip", add={"shmups"})
        self.assertEqual(set(self.stored()["games"]), {A, B, C, "gb/D.zip"})
        self.assertIn(C, tags.load()["games"])

    def test_delete_and_merge_clean_declined(self):
        data = sample()
        data["declined"]["gb/E.zip"] = ["shmups"]
        helpers.storage_tags(self, data, root=self.storage)
        tags.delete_tag("cave")
        s = self.stored()
        self.assertNotIn("cave", s["tags"])
        self.assertEqual(s["games"][A]["tags"], ["shmups"])
        self.assertNotIn(C, s["declined"])
        helpers.storage_tags(self, data, root=self.storage)
        tags.merge_tag("cave", "shmups")
        s = self.stored()
        self.assertNotIn("cave", s["tags"])
        self.assertEqual(s["games"][A]["tags"], ["shmups"])
        self.assertEqual(s["declined"][C], ["shmups"])

    def surprise_limits(self):
        usersettings.save_setting("surprise_tags", ["cave", "shmups"])
        store.write_cards({"c": {"surprise_tags": ["cave"]}, "d": {"surprise_tags": ["shmups"]}, "e": {}})

    def test_delete_tag_leaves_the_surprise_limits(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        self.surprise_limits()
        tags.delete_tag("cave")
        self.assertEqual(usersettings.load_settings()["surprise_tags"], ["shmups"])
        cards = store.load_cards()
        self.assertNotIn("surprise_tags", cards["c"])
        self.assertEqual(cards["d"]["surprise_tags"], ["shmups"])
        tags.delete_tag("shmups")
        self.assertNotIn("surprise_tags", usersettings.load_settings())

    def test_merge_replaces_the_tag_in_the_surprise_limits(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        self.surprise_limits()
        tags.merge_tag("cave", "shmups")
        self.assertEqual(usersettings.load_settings()["surprise_tags"], ["shmups"])
        self.assertEqual(store.load_cards()["c"]["surprise_tags"], ["shmups"])

    def test_merge_into_a_tag_storage_no_longer_has_raises(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.load()
        theirs = sample()  # another machine deleted shmups after this run read the file
        del theirs["tags"]["shmups"]
        with open(os.path.join(self.storage, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump(theirs))
        with self.assertRaises(ValueError):
            tags.merge_tag("cave", "shmups")
        self.assertIn("cave", self.stored()["tags"])

    def test_change_game_tags_keeps_tags_another_machine_added(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.load()
        theirs = sample()  # another machine gave B the cave tag after this run read the file
        theirs["games"][B]["tags"] = ["cave", "shmups"]
        with open(os.path.join(self.storage, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump(theirs))
        tags.change_game_tags(B, add={"new"}, remove={"shmups"})
        self.assertEqual(self.stored()["games"][B]["tags"], ["cave", "new"])

    def test_owner_is_the_record_a_file_belongs_to(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        self.assertEqual(tags.owner("nes/A (Disc 2).zip"), A)
        self.assertEqual(tags.owner(A), A)
        self.assertEqual(tags.owner("nes/none.zip"), "nes/none.zip")

    def test_no_surprise_limits_writes_nothing(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.delete_tag("cave")
        self.assertFalse(os.path.exists(self.path("cards.json")))
        self.assertFalse(os.path.exists(self.path("settings.json")))

    def test_define_decline(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.define_tag("bees", {"name": "Bees", "emoji": "🐝"})
        self.assertEqual(self.stored()["tags"]["bees"]["name"], "Bees")
        tags.decline({C: ["shmups"]})
        self.assertEqual(self.stored()["declined"][C], ["cave", "shmups"])

    def test_edit_variants_changes_the_fresh_file_in_one_write(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.load()
        theirs = sample()  # another machine, after this run read the file: B gets a variant, A loses its record
        theirs["games"][B]["variants"] = [{"bucket": "nes/B Theirs.zip", "note": "theirs"}]
        del theirs["games"][A]
        with open(os.path.join(self.storage, tags.KEY), "w", encoding="utf-8") as f:
            f.write(tags.dump(theirs))
        changed, missing = tags.edit_variants(
            add=[{"game": B, "bucket": "nes/B2.zip", "note": "n", "files": ["nes/B2 (Disc 2).zip"]},
                 {"game": A, "bucket": "nes/A2.zip", "note": "n"}],
            remove=[{"game": B, "bucket": "nes/B Gone.zip"}])
        self.assertEqual((changed, missing), ([B], [A]))
        games = self.stored()["games"]
        self.assertNotIn(A, games)  # not recreated
        self.assertEqual(games[B]["variants"], [{"bucket": "nes/B Theirs.zip", "note": "theirs"},
                                                {"bucket": "nes/B2.zip", "note": "n", "files": ["nes/B2 (Disc 2).zip"]}])
        tags.edit_variants(add=[], remove=[{"game": B, "bucket": "nes/B Theirs.zip"}])
        self.assertEqual([v["bucket"] for v in self.stored()["games"][B]["variants"]], ["nes/B2.zip"])

    def test_retarget(self):
        helpers.storage_tags(self, sample(), root=self.storage)
        tags.retarget(A, "nes/A2.zip")
        tags.retarget("nes/A (Disc 2).zip", "nes/A2 (Disc 2).zip")
        tags.retarget("nes/A [T-En].zip", "nes/A2 [T-En].zip")
        s = self.stored()
        self.assertNotIn(A, s["games"])
        rec = s["games"]["nes/A2.zip"]
        self.assertEqual(rec["files"], ["nes/A2 (Disc 2).zip"])
        self.assertEqual(rec["variants"][0]["bucket"], "nes/A2 [T-En].zip")
        tags.retarget(C, "snes/C2.sfc")
        self.assertIn("snes/C2.sfc", self.stored()["declined"])


if __name__ == "__main__":
    unittest.main()
