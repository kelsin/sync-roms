import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
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

    def test_typed_category_matches_an_existing_one_ignoring_case(self):
        with mock.patch.object(ui, "ask", return_value=" cave "), mock.patch("builtins.print"):
            self.assertEqual(setedit.ask_category(games(), "x"), "Cave")
        with mock.patch.object(ui, "ask", return_value="Fresh"), mock.patch("builtins.print"):
            self.assertEqual(setedit.ask_category(games(), "x"), "Fresh")

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

    def test_ctrl_c_with_changes_goes_to_the_review(self):
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks = iter([1, KeyboardInterrupt, None])  # "New set", Ctrl-C, keep editing, then Esc to review
        opened = {}

        def pick(*a, **k):
            value = next(picks)
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value

        def add_game(game_set, systems, keys_of):
            game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})

        with mock.patch.object(setedit, "need_tools"), mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(setedit, "edit_one", add_game), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(ui, "ask", side_effect=["My Set", "about it"]), \
                mock.patch.object(ui, "choose", side_effect=["e", "o"]) as choose, mock.patch("builtins.print"), \
                mock.patch.object(setedit, "open_pr", lambda after, found: opened.update(after=after, found=found) or "url"):
            self.assertEqual(setedit.edit_sets(), 0)  # keep editing ended the interrupt: the later Done ends normally
        self.assertEqual(choose.call_count, 2)
        self.assertEqual([(k, s) for k, s, _ in opened["found"]], [("new", "my-set")])

    def stopped(self, picks, answers):
        """Run the editor on no sets until it stops with KeyboardInterrupt; picks and answers may hold Ctrl-C.
        Returns the review prompts shown and the PRs opened."""
        picks, opened = iter(picks), []

        def pick(*a, **k):
            value = next(picks)
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value
        with mock.patch.object(setedit, "need_tools"), mock.patch.object(setedit, "repo_sets", return_value={}), \
                mock.patch.object(setedit, "edit_one", lambda g, s, k: g["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(ui, "ask", side_effect=["My Set", ""]), \
                mock.patch.object(ui, "choose", side_effect=answers) as choose, mock.patch("builtins.print"), \
                mock.patch.object(setedit, "open_pr", lambda after, found: opened.append(found) or "url"), \
                self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        return choose.call_count, len(opened)

    def test_ctrl_c_review_that_opens_or_discards_still_stops(self):
        for answer, prs in (("o", 1), ("d", 0)):
            with self.subTest(answer=answer):  # "New set" (no sets yet), then Ctrl-C
                self.assertEqual(self.stopped([0, KeyboardInterrupt], [answer]), (1, prs))

    def test_ctrl_c_after_keep_editing_reviews_again(self):  # Ctrl-C, keep editing, Ctrl-C, discard
        self.assertEqual(self.stopped([0, KeyboardInterrupt, KeyboardInterrupt], ["e", "d"]), (2, 0))

    def test_ctrl_c_at_the_review_prompt_stops(self):
        self.assertEqual(self.stopped([0, KeyboardInterrupt], [KeyboardInterrupt]), (1, 0))

    def test_ctrl_c_without_changes_reviews_nothing(self):
        with mock.patch.object(setedit, "need_tools"), mock.patch.object(setedit, "repo_sets", return_value={}), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", side_effect=KeyboardInterrupt), \
                mock.patch.object(ui, "choose") as choose, self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        choose.assert_not_called()

    def interrupted(self, picks, lists, sets=()):
        """Open set old (games()) in the real set editor; picks answer the single-choice lists, lists holds per toggle
        list (labels to switch, what it then does: KeyboardInterrupt or a hotkey). The review opens the PR.
        Returns the review prompts shown, the sets the PR got (None without one) and the ui.ask mock."""
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks, lists, opened = iter(picks), iter(lists), {}
        keys = {"gba": {"gba/A.zip", "gba/B.zip", "gba/D.zip", "gba/D2.zip"}, "gen": {"gen/C.zip", "gen/E.zip"}}

        def fake(title, labels, **kw):
            if not kw.get("multi"):
                return next(picks)
            flip, then = next(lists)
            kw["session"]["sel"] = [on != (label in flip) for label, on in zip(labels, kw["session"]["sel"])]
            if then is KeyboardInterrupt:
                raise KeyboardInterrupt
            return (then, 0)

        with mock.patch.object(setedit, "need_tools"), mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(store, "folder_keys", lambda bucket: keys.get(bucket, set())), \
                mock.patch.object(store, "load_sets", return_value=list(sets)), \
                mock.patch.object(setedit, "stocked", lambda systems: systems), \
                mock.patch.object(setedit, "file_counts", lambda systems: None), \
                mock.patch.object(ui, "ask") as ask, mock.patch.object(ui, "choose", return_value="o") as choose, \
                mock.patch("builtins.print"), \
                mock.patch.object(setedit, "open_pr", lambda after, found: opened.update(after=after) or "url"), \
                self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        return choose.call_count, opened.get("after"), ask

    def test_ctrl_c_keeps_the_open_lists_removals(self):
        reviews, after, _ = self.interrupted([0, 0], [({"Cave — Game Boy Advance — A", "Cave — Genesis — C"}, KeyboardInterrupt)])
        self.assertEqual(reviews, 1)
        self.assertEqual([g["bucket"] for g in after["old"]["games"]], ["gba/B.zip", "nes/Odd.zip"])

    def test_ctrl_c_keeps_the_add_games_lists_toggles_with_no_category(self):  # Genesis: E on, C off, Ctrl-C
        reviews, after, ask = self.interrupted([0, 1, 1], [({"E.zip", "C.zip"}, KeyboardInterrupt)])
        ask.assert_not_called()  # no category question
        self.assertEqual(reviews, 1)
        self.assertEqual(after["old"]["games"], [g for g in games() if g["bucket"] != "gen/C.zip"]
                         + [{"title": "E", "system": "gen", "bucket": "gen/E.zip"}])

    def test_ctrl_c_keeps_the_add_from_a_set_lists_toggles_with_no_category(self):
        mix = {"id": "mix", "name": "Mix", "games": [games()[0], {"title": "D", "system": "gba", "bucket": "gba/D.zip",
                                                                  "files": ["gba/D2.zip"]}]}
        reviews, after, ask = self.interrupted([0, 2, 0], [({"Cave — Game Boy Advance — A", "Game Boy Advance — D"}, KeyboardInterrupt)],
                                               sets=[mix])
        ask.assert_not_called()
        self.assertEqual(reviews, 1)
        self.assertEqual(after["old"]["games"], games()[1:] + [{"title": "D", "system": "gba", "bucket": "gba/D.zip",
                                                                "files": ["gba/D2.zip"]}])

    def test_ctrl_c_in_a_list_with_nothing_toggled_reviews_nothing(self):
        mix = {"id": "mix", "name": "Mix", "games": [games()[0]]}
        for picks in ([0, 0], [0, 1, 1], [0, 2, 0]):
            with self.subTest(picks=picks):
                self.assertEqual(self.interrupted(picks, [(set(), KeyboardInterrupt)], sets=[mix])[:2], (0, None))

    def test_command_is_wired(self):
        with mock.patch.object(setedit, "edit_sets", return_value=0) as run:
            self.assertEqual(commands.run(["sets", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["sets"], ["edit"])


if __name__ == "__main__":
    unittest.main()
