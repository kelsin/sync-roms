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
from sync_roms import ignore, tags  # noqa: E402

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
export_tool = helpers.load_script(os.path.join(TOOLS, "export_tag_review.py"))
apply_tool = helpers.load_script(os.path.join(TOOLS, "apply_tag_proposals.py"))

TAGS = {"shmups": {"name": "Shmups", "emoji": "🚀", "description": "Shoot them up"},
        "cave": {"name": "Cave", "emoji": "🐝"}}
A, B, C = "nes/A.zip", "nes/B.zip", "snes/C.sfc"


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Export(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        helpers.storage_tags(self, {"tags": TAGS, "games": {A: {"tags": ["cave"]}}, "declined": {}},
                             root=self.root.name)
        self.out = self.enterContext(tempfile.TemporaryDirectory())

    def test_export_chunks_systems_at_400(self):
        for i in range(401):
            self.put(f"nes/g{i:03d}.zip", 1)
        self.put(A.split("/", 1)[0] + "/A.zip", 1)
        export_tool.export(self.out, ["nes", "gba"])
        names = sorted(os.listdir(os.path.join(self.out, "systems")))
        self.assertEqual(names, ["gba-1.json", "nes-1.json", "nes-2.json"])
        first = read(os.path.join(self.out, "systems", "nes-1.json"))
        second = read(os.path.join(self.out, "systems", "nes-2.json"))
        self.assertEqual((len(first), len(second)), (400, 2))
        row = next(r for r in first if r["key"] == A)
        self.assertEqual(row, {"key": A, "title": "A", "tags": ["cave"]})
        self.assertEqual(read(os.path.join(self.out, "vocabulary.json"))["shmups"],
                         {"name": "Shmups", "description": "Shoot them up"})

    def test_export_leaves_out_ignored_roms(self):
        self.put("nes/keep.zip", 1)
        self.put("nes/skip.zip", 1)
        write(os.path.join(self.root.name, ignore.KEY), {"nes": ["skip.zip"]})
        ignore.reset()
        self.addCleanup(ignore.reset)
        export_tool.export(self.out, ["nes"])
        keys = [r["key"] for r in read(os.path.join(self.out, "systems", "nes-1.json"))]
        self.assertEqual(keys, ["nes/keep.zip"])


def fixture():
    vocab = {"shmups": {"name": "Shmups", "description": ""}, "cave": {"name": "Cave", "description": ""}}
    games = {A: {"title": "Alpha", "tags": {"cave"}}, B: {"title": "Beta", "tags": set()},
             C: {"title": "Gamma", "tags": {"shmups"}}}
    return vocab, games


class Summary(unittest.TestCase):
    def test_summary_counts_per_tag(self):
        vocab, games = fixture()
        props = [{"add": {A: ["shmups", "cave"], B: ["shmups"]}, "remove": {C: ["shmups"]}}]
        result = apply_tool.plan(vocab, games, props)
        self.assertEqual(result["changes"], {A: (["shmups"], []), B: (["shmups"], []), C: ([], ["shmups"])})
        text = apply_tool.summary_text(vocab, games, result)
        self.assertIn("shmups (Shmups): +2 -1", text)
        self.assertIn("Alpha", text)
        self.assertIn("Gamma", text)
        self.assertNotIn("cave (Cave)", text)  # already had it: no change

    def test_summary_reports_unknown_ids_and_keys(self):
        vocab, games = fixture()
        props = [{"add": {A: ["nope"], "nes/Z.zip": ["cave"]}, "new_tags": {"fresh": {"name": "Fresh"}}}]
        result = apply_tool.plan(vocab, games, props)
        self.assertEqual(result["changes"], {})
        self.assertEqual((result["unknown_tags"], result["unknown_keys"]), (["nope"], ["nes/Z.zip"]))
        text = apply_tool.summary_text(vocab, games, result)
        self.assertIn("nope", text)
        self.assertIn("nes/Z.zip", text)
        self.assertIn("fresh", text)


class Apply(helpers.StorageFolder):
    def setUp(self):
        super().setUp()
        self.storage = helpers.storage_tags(
            self, {"tags": TAGS, "games": {A: {"tags": ["cave"]}, C: {"tags": ["shmups"]}}, "declined": {}},
            root=self.root.name)
        self.out = self.enterContext(tempfile.TemporaryDirectory())
        write(os.path.join(self.out, "vocabulary.json"), {k: {"name": v["name"], "description": ""} for k, v in TAGS.items()})
        write(os.path.join(self.out, "systems", "nes-1.json"),
              [{"key": A, "title": "A", "tags": ["cave"]}, {"key": B, "title": "B", "tags": []}])
        write(os.path.join(self.out, "systems", "snes-1.json"), [{"key": C, "title": "C", "tags": ["shmups"]}])

    def run_tool(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as out, mock.patch.object(apply_tool.usersettings, "apply_settings"):
            code = apply_tool.main([self.out, *argv])
        return code, out.getvalue()

    def stored(self):
        with open(os.path.join(self.storage, tags.KEY), encoding="utf-8") as f:
            return tags.parse(f.read())["games"]

    def test_apply_calls_change_game_tags_per_game(self):
        write(os.path.join(self.out, "proposals", "nes-1.json"),
              {"add": {B: ["shmups", "cave"]}, "remove": {A: ["cave"]}})
        write(os.path.join(self.out, "proposals", "snes-1.json"), {"add": {C: ["cave"]}})
        calls = []
        real = tags.change_game_tags
        with mock.patch.object(tags, "change_game_tags",
                               side_effect=lambda k, add=(), remove=(): calls.append((k, list(add), list(remove))) or real(k, add, remove)):
            code, _ = self.run_tool("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(calls), [(A, [], ["cave"]), (B, ["cave", "shmups"], []), (C, ["cave"], [])])
        games = self.stored()
        self.assertEqual(games[B]["tags"], ["cave", "shmups"])
        self.assertNotIn(A, games)
        self.assertEqual(games[C]["tags"], ["cave", "shmups"])

    def test_summary_writes_nothing(self):
        write(os.path.join(self.out, "proposals", "nes-1.json"), {"add": {B: ["cave"]}})
        before = self.stored()
        code, text = self.run_tool("--summary")
        self.assertEqual(code, 0)
        self.assertIn("cave (Cave): +1", text)
        self.assertEqual(self.stored(), before)

    def test_apply_never_creates_tags(self):
        write(os.path.join(self.out, "proposals", "nes-1.json"),
              {"add": {B: ["fresh"]}, "new_tags": {"fresh": {"name": "Fresh", "emoji": "x", "description": ""}}})
        code, text = self.run_tool("--apply")
        self.assertEqual(code, 0)
        self.assertIn("fresh", text)
        with open(os.path.join(self.storage, tags.KEY), encoding="utf-8") as f:
            data = tags.parse(f.read())
        self.assertEqual(set(data["tags"]), set(TAGS))
        self.assertNotIn(B, data["games"])


if __name__ == "__main__":
    unittest.main()
