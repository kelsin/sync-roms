import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import commands, edit, picker, setedit, store, ui  # noqa: E402

SYSTEMS = [{"name": "Game Boy Advance", "bucket": "gba"}, {"name": "Genesis", "bucket": "gen"}]


def games():
    return [{"title": "A", "category": "Cave", "system": "gba", "bucket": "gba/A.zip"},
            {"title": "B", "category": "Other", "system": "gba", "bucket": "gba/B.zip", "note": "hi"},
            {"title": "C", "category": "Cave", "system": "gen", "bucket": "gen/C.zip"},
            {"title": "Odd", "system": "nes", "bucket": "nes/Odd.zip"}]


def shown_without(keys, add=()):
    shown = setedit.view({"games": games()}, SYSTEMS)
    for s in shown.values():
        s["games"] = [g for g in s["games"] if g["bucket"] not in keys]
    for system, key in add:
        shown[system]["games"].append({"title": key.split("/")[1][:-4], "bucket": key})
    return shown


class Files(unittest.TestCase):
    def test_every_repo_set_round_trips_to_its_file(self):
        folder = os.path.join(store.REPO_DATA, "sets")
        sets = setedit.repo_sets()
        self.assertTrue(sets)
        for sid, game_set in sets.items():
            with open(os.path.join(folder, sid + ".json"), encoding="utf-8") as f:
                self.assertEqual(setedit.set_text(game_set), f.read(), sid)


class Reconcile(unittest.TestCase):
    def test_removed_games_go_and_the_rest_is_untouched(self):
        out = setedit.reconcile(games(), shown_without({"gba/A.zip"}))
        self.assertEqual([g["bucket"] for g in out], ["gba/B.zip", "gen/C.zip", "nes/Odd.zip"])
        self.assertEqual(out[0]["note"], "hi")  # extra keys survive; the unknown-system entry is kept

    def test_added_game_goes_after_the_last_of_its_category(self):
        out = setedit.reconcile(games(), shown_without(set(), [("gen", "gen/New.zip")]), "Cave")
        self.assertEqual([g["bucket"] for g in out], ["gba/A.zip", "gba/B.zip", "gen/C.zip", "gen/New.zip", "nes/Odd.zip"])
        self.assertEqual(list(out[3]), ["title", "category", "system", "bucket"])

    def test_new_category_goes_last_and_no_category_is_left_out(self):
        out = setedit.reconcile(games(), shown_without(set(), [("gen", "gen/New.zip")]), "Fresh")
        self.assertEqual((out[-1]["bucket"], out[-1]["category"]), ("gen/New.zip", "Fresh"))
        out = setedit.reconcile(games(), shown_without(set(), [("gen", "gen/New.zip")]))
        self.assertEqual(out[-1], {"title": "New", "system": "gen", "bucket": "gen/New.zip"})

    def test_recategorize(self):
        g = games()
        setedit.recategorize(g, g[1], "Cave")
        self.assertEqual([x["bucket"] for x in g], ["gba/A.zip", "gen/C.zip", "gba/B.zip", "nes/Odd.zip"])
        self.assertEqual((g[2]["category"], g[2]["note"]), ("Cave", "hi"))
        setedit.recategorize(g, g[2], "")
        self.assertNotIn("category", next(x for x in g if x["bucket"] == "gba/B.zip"))


class Changes(unittest.TestCase):
    def test_diff_and_titles(self):
        before = {"a": {"name": "A", "description": "", "games": games()}, "gone": {"name": "G", "description": "", "games": games()}}
        after = {"a": {"name": "A", "description": "", "games": setedit.reconcile(games(), shown_without({"gba/A.zip"}))},
                 "fresh": {"name": "Fresh", "description": "", "games": games()[:1]}}
        found = setedit.diff_sets(before, after)
        self.assertEqual([(k, s) for k, s, _ in found], [("changed", "a"), ("new", "fresh"), ("removed", "gone")])
        self.assertEqual(found[0][2], ["- A (gba/A.zip)"])
        self.assertEqual(setedit.commit_title(found[1:2]), "feat(sets): add fresh")
        self.assertEqual(setedit.commit_title(found[2:]), "feat(sets): remove gone")
        self.assertEqual(setedit.commit_title(found[:1]), "feat(sets): update a")
        self.assertEqual(setedit.commit_title(found), "feat(sets): update 3 sets")
        self.assertIn("### a (changed)\n- - A (gba/A.zip)", setedit.pr_body(found))

    def test_category_change_is_listed(self):
        before = {"a": {"name": "A", "description": "", "games": games()}}
        moved = games()
        setedit.recategorize(moved, moved[1], "Cave")
        lines = setedit.diff_sets(before, {"a": {"name": "A", "description": "", "games": moved}})[0][2]
        self.assertEqual(lines, ["~ B (gba/B.zip): category Other → Cave"])


class PullRequest(unittest.TestCase):
    def run_pr(self, fail_on=None):
        calls, seen = [], {}

        def fake(cmd, cwd=None, **kw):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "clone"]:
                tmp = cmd[4]
                seen["tmp"] = tmp
                os.makedirs(os.path.join(tmp, setedit.SETS_DIR))
                with open(os.path.join(tmp, setedit.SETS_DIR, "gone.json"), "w") as f:
                    f.write("{}")
            if fail_on and cmd[:2] == fail_on:
                return mock.Mock(returncode=1, stdout="", stderr="boom")
            if cmd[:3] == ["gh", "pr", "create"]:
                seen["files"] = sorted(os.listdir(os.path.join(seen["tmp"], setedit.SETS_DIR)))
                with open(os.path.join(seen["tmp"], setedit.SETS_DIR, "fresh.json")) as f:
                    seen["fresh"] = f.read()
                return mock.Mock(returncode=0, stdout="https://github.com/x/y/pull/1\n", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        after = {"fresh": {"name": "Fresh", "description": "d", "games": games()[:1]}}
        found = [("new", "fresh", ["+ A"]), ("removed", "gone", ["1 game(s)"])]
        with mock.patch("subprocess.run", fake):
            try:
                url = setedit.open_pr(after, found)
            except SystemExit as e:
                url = e.code
        return url, calls, seen

    def test_clones_writes_commits_pushes_and_opens(self):
        url, calls, seen = self.run_pr()
        self.assertEqual(url, "https://github.com/x/y/pull/1")
        self.assertEqual([c[:2] for c in calls], [["gh", "repo"], ["git", "checkout"], ["git", "add"], ["git", "commit"],
                                                  ["git", "push"], ["gh", "pr"]])
        self.assertEqual(seen["files"], ["fresh.json"])
        self.assertIn('"name": "Fresh"', seen["fresh"])
        self.assertEqual(calls[3][3], "feat(sets): update 2 sets")
        self.assertFalse(os.path.exists(seen["tmp"]))

    def test_failure_stops_and_cleans_up(self):
        code, calls, seen = self.run_pr(fail_on=["git", "push"])
        self.assertEqual(code, 1)
        self.assertNotIn(["gh", "pr"], [c[:2] for c in calls])
        self.assertFalse(os.path.exists(seen["tmp"]))


class Editor(unittest.TestCase):
    def test_new_set_flow_opens_a_pr(self):
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks = iter([1, None])  # "New set" (after the one existing set), then Esc to review
        opened = {}

        def add_game(game_set, systems, keys_of):
            game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})

        with mock.patch.object(setedit, "need_tools"), mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(setedit, "edit_one", add_game), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=["My Set", "about it"]), \
                mock.patch.object(ui, "choose", return_value="o"), \
                mock.patch.object(setedit, "open_pr", lambda after, found: opened.update(after=after, found=found) or "url"):
            self.assertEqual(setedit.edit_sets(), 0)
        self.assertEqual([(k, s) for k, s, _ in opened["found"]], [("new", "my-set")])
        self.assertEqual(opened["after"]["my-set"]["description"], "about it")

    def test_command_is_wired(self):
        with mock.patch.object(setedit, "edit_sets", return_value=0) as run:
            self.assertEqual(commands.run(["sets", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["sets"], ["edit"])


if __name__ == "__main__":
    unittest.main()
