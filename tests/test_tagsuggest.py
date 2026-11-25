import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import commands, picker, shared, store, tags, tagsuggest, ui  # noqa: E402

SYSTEMS = [{"name": "Nintendo NES", "bucket": "nes", "bios": {"files": []}}]
GENRES = {"Shoot'em Up": ["shmups"], "Sports": ["sports"], "Sports / Football (Soccer)": ["sports", "soccer"],
          "Platform": ["platformers"]}
HERO = "nes/Hero (USA).zip"  # tagged
HERO_DX = "nes/Hero DX (USA).zip"  # its variant
HERO_EU = "nes/Hero (Europe).zip"  # another version: the same scraped name
SHMUP = "nes/Shmup (USA).zip"
SHMUP_BETA = "nes/Shmup (USA) (Beta).zip"
KICK = "nes/Kick (USA).zip"
KICK_WORLD = "nes/Kick (World).zip"  # same scraped name as KICK, later in sort order
METADATA = {
    "Hero (USA).zip": {"name": "Hero", "genre": "Platform / Run & Jump"},
    "Hero DX (USA).zip": {"name": "Hero DX", "genre": "Platform"},
    "Hero (Europe).zip": {"name": "Hero", "genre": "Platform"},
    "Shmup (USA).zip": {"name": "Shmup", "genre": "Shoot'em Up / Vertical"},
    "Shmup (USA) (Beta).zip": {"name": "Shmup Beta", "genre": "Shoot'em Up"},
    "Kick (USA).zip": {"name": "Kick", "genre": "Sports / Football (Soccer)"},
    "Kick (World).zip": {"name": "Kick", "genre": "Sports"},
}
TAG_DEFS = {"hero": {"name": "Hero", "emoji": "🦸"}, "platformers": {"name": "Platformers", "emoji": "🏃"},
            "shmups": {"name": "Shmups", "emoji": "🛸"}, "sports": {"name": "Sports", "emoji": "⚽"}}  # no "soccer"


class Suggest(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        self.root = self.start({})
        self.enterContext(mock.patch.dict(os.environ, {"ROMS_ROOT": self.root}))  # what commands.run applies
        self.enterContext(mock.patch.object(
            store, "repo_json", lambda name: SYSTEMS if name == "systems" else GENRES if name == "genre-tags" else []))

    def start(self, declined, root=None):
        root = helpers.storage_tags(self, {
            "tags": TAG_DEFS, "games": {HERO: {"tags": ["hero"], "variants": [{"bucket": HERO_DX, "note": "more"}]}},
            "declined": declined}, root)
        for key in (HERO, HERO_DX, HERO_EU, SHMUP, SHMUP_BETA, KICK, KICK_WORLD):
            helpers.touch(os.path.join(root, key))
        helpers.touch(os.path.join(root, "scrapes/nes/metadata.json"), json.dumps(METADATA))
        tagsuggest.reset()
        self.addCleanup(tagsuggest.reset)
        return root

    def test_pool_has_one_version_of_each_untagged_game(self):
        self.assertEqual(tagsuggest.pool(SYSTEMS[0]), {SHMUP: "Shmup", KICK: "Kick"})
        self.assertEqual(tagsuggest.untagged(SYSTEMS[0]), 2)

    def test_suggestions_are_mapped_tags_the_game_lacks(self):
        self.assertEqual(tagsuggest.suggestions(SYSTEMS),
                         {HERO: ["platformers"], SHMUP: ["shmups"], KICK: ["sports"]})  # no soccer tag

    def test_a_declined_pair_is_not_suggested(self):
        self.start({SHMUP: ["shmups"]}, self.root)
        self.assertEqual(tagsuggest.suggestions(SYSTEMS), {HERO: ["platformers"], KICK: ["sports"]})

    def test_an_existing_tag_is_not_suggested(self):
        tags.set_game_tags(SHMUP, ["shmups"])
        self.assertNotIn(SHMUP, tagsuggest.suggestions(SYSTEMS))

    def run_review(self, uncheck, confirm=True):
        """`tags suggest nes` with the rows whose label contains uncheck switched off; (code, labels, writes)."""
        shown = []

        def fake(title, labels, **kw):
            shown.extend(labels)
            return [uncheck not in label for label in labels]
        writes = mock.patch.object(shared, "update", wraps=shared.update)
        out = io.StringIO()
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "confirm", return_value=confirm), \
                writes as update, contextlib.redirect_stdout(out):
            code = commands.run(["tags", "suggest", "nes"])
        return code, shown, update.call_count, out.getvalue()

    def test_review_adds_checked_and_declines_unchecked_in_one_write_each(self):
        code, shown, writes, out = self.run_review("Shmup")
        self.assertEqual(code, 0)
        self.assertEqual(shown, ["🏃 Platformers — Nintendo NES — Hero", "🛸 Shmups — Nintendo NES — Shmup",
                                 "⚽ Sports — Nintendo NES — Kick"])
        self.assertEqual(writes, 2)
        tags.reset()
        self.assertEqual(tags.tags_of(HERO), ["hero", "platformers"])
        self.assertEqual(tags.tags_of(KICK), ["sports"])
        self.assertEqual(tags.tags_of(SHMUP), [])
        self.assertEqual(tags.load()["declined"], {SHMUP: ["shmups"]})
        self.assertIn("2", out)

    def test_review_not_confirmed_saves_nothing(self):
        code, _, writes, _ = self.run_review("Shmup", confirm=False)
        self.assertEqual((code, writes), (0, 0))

    def test_unknown_system_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e:
                commands.run(["tags", "suggest", "nope"])
        self.assertEqual(e.exception.code, 2)


class AddTags(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        helpers.storage_tags(self, {"tags": TAG_DEFS, "games": {HERO: {"tags": ["hero"]}}, "declined": {}},
                             self.root.name)

    def test_adds_each_games_tags_in_one_write(self):
        with mock.patch.object(shared, "update", wraps=shared.update) as update:
            tags.add_tags({HERO: ["platformers"], SHMUP: ["shmups", "sports"]})
        self.assertEqual(update.call_count, 1)
        self.assertEqual(tags.tags_of(HERO), ["hero", "platformers"])
        self.assertEqual(tags.tags_of(SHMUP), ["shmups", "sports"])


if __name__ == "__main__":
    unittest.main()
