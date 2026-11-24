import contextlib
import datetime
import io
import json
import shutil
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import picker, saves, saves_manage, store, ui  # noqa: E402

GB = {"bucket": "gb", "folders": {"muos": "GB"}}
NOMUOS = {"bucket": "gb", "folders": {"onion": "GB"}}


class OpsTest(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.src = self.enterContext(tempfile.TemporaryDirectory())

    def stash(self, game="Game", system="gba", day=1, rel=None, files=None, card="X"):
        entries = []
        for name, data in (files or {f"{game}.srm": "save", f"{game}.state.auto": "st"}).items():
            p = os.path.join(self.src, system, game, name)
            helpers.touch(p, data)
            e = {"path": p, "name": name, "kind": saves.classify(name)[1]}
            if rel:
                e.update(rel=rel, core="mGBA")
            entries.append(e)
        now = datetime.datetime(2026, 1, day, 0, 0, 0)
        return saves.write_stash(card, "muos" if rel else "onion", system, game, "gpSP", entries, now=now)

    def meta(self, d):
        with open(os.path.join(d, "stash.json")) as f:
            return json.load(f)

    def row_for(self, d):
        return next(r for r in saves_manage.list_rows() if r["dir"] == d)

    def test_list_rows_reports_missing_extra_and_size(self):
        d = self.stash(files={"Game.srm": "four", "Game.state.auto": "st"})
        os.remove(os.path.join(d, "Game.state.auto"))
        helpers.touch(os.path.join(d, "junk.txt"), "x")
        (row,) = saves_manage.list_rows()
        self.assertEqual((row["missing"], row["extra"], row["size"], row["unreadable"]),
                         (["Game.state.auto"], ["junk.txt"], 4, False))

    def test_list_rows_lists_unreadable_last(self):
        self.stash(game="Zed")
        bad = os.path.join(saves.stash_root(), "gba", "Game", "20260101-000000-X")
        helpers.touch(os.path.join(bad, "Game.srm"), "abc")
        helpers.touch(os.path.join(bad, "stash.json"), "{")
        rows = saves_manage.list_rows()
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]["unreadable"])
        last = rows[-1]
        self.assertIs(last["unreadable"], True)
        self.assertEqual((last["rel_dir"], last["files"], last["size"], last["dir"]),
                         ("gba/Game/20260101-000000-X", ["Game.srm", "stash.json"], 4, bad))

    def test_set_label_writes_and_removes(self):
        d = self.stash()
        row = self.row_for(d)
        saves_manage.set_label(row, " boss ", dry_run=True)
        self.assertNotIn("note", self.meta(d))
        row = self.row_for(d)
        saves_manage.set_label(row, " boss ")
        self.assertEqual(self.meta(d)["note"], "boss")
        self.assertEqual(row["note"], "boss")
        saves_manage.set_label(row, "")
        self.assertNotIn("note", self.meta(d))
        self.assertNotIn("note", row)

    def test_move_rewrites_system_and_keeps_game_and_note(self):
        d = self.stash()
        row = self.row_for(d)
        saves_manage.set_label(row, "boss")
        new = saves_manage.move(row, GB, [GB])
        self.assertEqual(new, os.path.join(saves.stash_root(), "gb", "Game", os.path.basename(d)))
        self.assertTrue(os.path.isfile(os.path.join(new, "Game.srm")))
        m = self.meta(new)
        self.assertEqual((m["system"], m["game"], m["note"]), ("gb", "Game", "boss"))
        self.assertFalse(os.path.exists(os.path.join(saves.stash_root(), "gba")))
        self.assertEqual((row["dir"], row["system"]), (new, "gb"))

    def test_move_dry_run_changes_nothing(self):
        d = self.stash()
        row = self.row_for(d)
        new = saves_manage.move(row, GB, [GB], dry_run=True)
        self.assertEqual(new, os.path.join(saves.stash_root(), "gb", "Game", os.path.basename(d)))
        self.assertFalse(os.path.exists(os.path.dirname(new)))
        self.assertTrue(os.path.isdir(d))
        self.assertEqual(row["system"], "gba")

    def test_move_suffixes_a_taken_folder(self):
        d = self.stash()
        other = self.stash(system="gb")
        self.assertEqual(os.path.basename(d), os.path.basename(other))
        new = saves_manage.move(self.row_for(d), GB, [GB])
        self.assertEqual(new, other + "-2")
        self.assertTrue(os.path.isfile(os.path.join(other, "Game.srm")))
        self.assertEqual(self.meta(other)["system"], "gb")

    def test_move_refuses_an_unsafe_game_name(self):
        for game in ("..", "../../x", "a/b"):
            d = self.stash()
            data = self.meta(d)
            data["game"] = game
            with open(os.path.join(d, "stash.json"), "w") as f:
                json.dump(data, f)
            row = {"dir": d, "unreadable": False, **data}
            with self.assertRaises(ValueError):
                saves_manage.move(row, GB, [GB])
            self.assertTrue(os.path.isdir(d))
            shutil.rmtree(d)

    def test_move_restores_the_folder_when_the_write_fails(self):
        d = self.stash()
        row = self.row_for(d)
        with mock.patch.object(saves_manage, "_write", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                saves_manage.move(row, GB, [GB])
        self.assertTrue(os.path.isfile(os.path.join(d, "Game.srm")))
        self.assertEqual((row["dir"], row["system"]), (d, "gba"))
        self.assertEqual(self.meta(d)["system"], "gba")

    def test_move_same_system_returns_none(self):
        d = self.stash()
        self.assertIsNone(saves_manage.move(self.row_for(d), {"bucket": "gba", "folders": {}}, []))
        self.assertTrue(os.path.isdir(d))

    def test_move_pickles_switches_rel(self):
        d = self.stash(rel="GBA/Hacks")
        new = saves_manage.move(self.row_for(d), GB, [GB])
        self.assertEqual([f["rel"] for f in self.meta(new)["files"]], ["GB/Hacks", "GB/Hacks"])

    def test_move_refuses_a_pickles_stash_without_muos_folder(self):
        d = self.stash(rel="GBA/Hacks")
        before = self.meta(d)
        with self.assertRaises(ValueError):
            saves_manage.move(self.row_for(d), NOMUOS, [NOMUOS])
        self.assertEqual(self.meta(d), before)

    def test_move_refuses_an_unreadable_row(self):
        bad = os.path.join(saves.stash_root(), "gba", "Game", "20260101-000000-X")
        helpers.touch(os.path.join(bad, "Game.srm"), "abc")
        (row,) = saves_manage.list_rows()
        with self.assertRaises(ValueError):
            saves_manage.move(row, GB, [GB])
        self.assertTrue(os.path.isdir(bad))

    def stray(self):
        """A valid stash.json directly in a system folder, beside real stashes."""
        real = self.stash()
        sysdir = os.path.join(saves.stash_root(), "gba")
        shutil.copy(os.path.join(real, "stash.json"), os.path.join(sysdir, "stash.json"))
        return real, sysdir

    def test_list_rows_ignores_a_stash_json_at_the_wrong_depth(self):
        real, sysdir = self.stray()
        self.assertEqual([r["dir"] for r in saves_manage.list_rows()], [real])

    def test_delete_and_move_refuse_a_row_at_the_wrong_depth(self):
        real, sysdir = self.stray()
        row = {**self.row_for(real), "dir": sysdir}
        with self.assertRaises(ValueError):
            saves_manage.delete([row])
        with self.assertRaises(ValueError):
            saves_manage.move(row, GB, [GB])
        self.assertTrue(os.path.isdir(real))
        self.assertTrue(os.path.isfile(os.path.join(sysdir, "stash.json")))

    def test_delete_removes_folder_and_empty_parents(self):
        a, b = self.stash(day=1), self.stash(day=2)
        self.assertEqual(saves_manage.delete([self.row_for(a)]), 1)
        self.assertFalse(os.path.exists(a))
        self.assertTrue(os.path.isdir(os.path.dirname(b)))
        self.assertEqual(saves_manage.delete([self.row_for(b)]), 1)
        self.assertFalse(os.path.exists(os.path.join(saves.stash_root(), "gba")))
        self.assertTrue(os.path.isdir(saves.stash_root()))

    def test_delete_refuses_outside_stash_root(self):
        outside = os.path.join(self.src, "elsewhere")
        helpers.touch(os.path.join(outside, "x.srm"), "x")
        with self.assertRaises(ValueError):
            saves_manage.delete([{"dir": outside, "unreadable": True}])
        self.assertTrue(os.path.isdir(outside))

    def test_delete_warns_and_goes_on_when_a_folder_is_gone(self):
        a, b = self.stash(day=1), self.stash(day=2)
        rows = [self.row_for(a), self.row_for(b)]
        shutil.rmtree(a)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(saves_manage.delete(rows), 1)
        self.assertFalse(os.path.exists(b))
        self.assertIn("⚠️", err.getvalue())

    def test_delete_dry_run_keeps_everything(self):
        d = self.stash()
        self.assertEqual(saves_manage.delete([self.row_for(d)], dry_run=True), 1)
        self.assertTrue(os.path.isfile(os.path.join(d, "Game.srm")))

    def test_prune_picks_all_but_newest(self):
        self.stash(day=1)
        self.stash(day=2)
        self.stash(day=3)
        self.stash(game="Other", day=1)
        rows = saves_manage.list_rows()
        picks = saves_manage.prune_picks(rows, 1)
        got = {(r["game"], r["stashed"][:10]) for r, p in zip(rows, picks) if p}
        self.assertEqual(got, {("Game", "2026-01-01"), ("Game", "2026-01-02")})

    def test_prune_keeps_every_stash_of_a_kept_run(self):
        def row(core, stashed, card="X"):
            return {"system": "gba", "game": "Game", "stashed": stashed, "card": card, "files": [{"core": core}]}
        rows = [row("a", "2026-01-02"), row("b", "2026-01-02"), row("a", "2026-01-01")]  # one run made two stashes
        self.assertEqual(saves_manage.prune_picks(rows, 1), [False, False, True])
        rows.append(row("a", "2026-01-02", card="Y"))  # another card's run at the same time is its own run
        self.assertEqual(saves_manage.prune_picks(rows, 2), [False, False, True, False])

    def test_prune_skips_unreadable(self):
        bad = os.path.join(saves.stash_root(), "gba", "Game", "20260101-000000-X")
        helpers.touch(os.path.join(bad, "Game.srm"), "abc")
        self.assertEqual(saves_manage.prune_picks(saves_manage.list_rows(), 0), [False])

    def test_inside(self):
        self.assertTrue(saves_manage.inside(os.path.join(saves.stash_root(), "gba")))
        self.assertFalse(saves_manage.inside(saves.stash_root()))
        self.assertFalse(saves_manage.inside(self.src))


class SessionFree:
    """picker.one_app runs its function in place (no Textual app) while has_terminal is true."""
    def run(self, fn, args, kwargs):
        return fn(*args, **kwargs)


SYSTEMS = [{"name": "Game Boy", "bucket": "gb", "folders": {"muos": "GB"}},
           {"name": "Game Boy Advance", "bucket": "gba", "folders": {"muos": "GBA"}}]


class ManageCommandTest(helpers.Cmd):
    def setUp(self):
        super().setUp()
        self.src = self.enterContext(tempfile.TemporaryDirectory())
        catalog = {"layouts": {}, "systems": SYSTEMS, "devices": []}
        for p in (mock.patch.object(store, "load_catalog", lambda: catalog),
                  mock.patch.object(ui, "has_terminal", lambda: True),
                  mock.patch.object(picker, "_Session", SessionFree)):
            self.enterContext(p)
        self.calls = []

    def lists(self, *answers):
        """picker.filter_list answers in turn: a value, or a callable(labels) giving one; calls are kept."""
        it = iter(answers)

        def fake(title, labels, multi=False, **kw):
            self.calls.append((title, list(labels), kw))
            a = next(it)
            return a(labels) if callable(a) else a
        self.enterContext(mock.patch.object(picker, "filter_list", fake))

    def stash(self, game="Game", system="gba", day=1):
        entries = []
        for name, data in {f"{game}.srm": "save", f"{game}.state.auto": "st"}.items():
            p = os.path.join(self.src, system, game, name)
            helpers.touch(p, data)
            entries.append({"path": p, "name": name, "kind": saves.classify(name)[1]})
        return saves.write_stash("X", "onion", system, game, "gpSP", entries,
                                 now=datetime.datetime(2026, 1, day, 0, 0, 0))

    def test_no_stashes_says_so(self):
        code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertIn("No stashed saves", out)

    def test_delete_highlighted_after_confirm(self):
        d = self.stash()
        self.lists(("d", 0), None)
        with mock.patch.object(ui, "confirm", lambda *a, **k: True):
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(d))
        self.assertIn("Deleted 1 stash(es)", out)

    def test_delete_declined_keeps_it(self):
        d = self.stash()
        self.lists(("d", 0), None)
        with mock.patch.object(ui, "confirm", lambda *a, **k: False):
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isdir(d))
        self.assertIn("Nothing changed", out)

    def test_yes_skips_the_question(self):
        d = self.stash()
        self.lists(("d", 0), None)
        with mock.patch.object(ui, "confirm", side_effect=AssertionError("asked")):
            code, out, err = self.run_cmd("saves", "manage", "--yes")
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(d))

    def test_dry_run_deletes_nothing(self):
        d = self.stash()
        self.lists(("d", 0), None)
        with mock.patch.object(ui, "confirm", lambda *a, **k: True):
            code, out, err = self.run_cmd("saves", "manage", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(d, "Game.srm")))
        self.assertIn("Would delete 1", out)

    def test_move_to_another_system(self):
        d = self.stash()
        self.lists(("m", 0), 0, None)
        code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[1][1], ["Game Boy", "Game Boy Advance"])
        self.assertEqual(self.calls[1][2]["cursor"], 1)
        self.assertTrue(os.path.isfile(os.path.join(saves.stash_root(), "gb", "Game", os.path.basename(d), "Game.srm")))
        self.assertFalse(os.path.exists(d))
        self.assertIn("moved 1", out)

    def test_move_clears_the_picks(self):
        self.stash(game="A"), self.stash(game="B")

        def pick_both(labels):
            self.calls[-1][2]["session"]["sel"][:] = [True, True]
            return ("m", 0)

        def after_move(labels):
            self.assertEqual(self.calls[-1][2]["session"]["sel"], [False, False])
            return None
        self.lists(pick_both, 0, after_move)
        code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertIn("moved 2", out)

    def test_unchanged_label_is_not_written(self):
        d = self.stash()
        with open(os.path.join(d, "stash.json")) as f:
            data = json.load(f)
        data["note"] = "boss"
        helpers.touch(os.path.join(d, "stash.json"), json.dumps(data))

        def label(labels):
            self.calls[-1][2]["on_note"](0, " boss ")
            return None
        self.lists(label)
        with mock.patch.object(saves_manage, "_write", side_effect=AssertionError("written")):
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertIn("Nothing changed", out)

    def test_prune_rejects_a_superscript_digit(self):
        self.stash()
        self.lists(("p", 0), None)
        with mock.patch.object(ui, "ask", lambda *a, **k: "\u00b2"):
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)

    def test_esc_at_the_keep_question_picks_nothing(self):
        self.stash(day=1)
        self.stash(day=2)

        def after(labels):
            self.assertEqual(self.calls[-1][2]["session"]["sel"], [False, False])  # keep-1 would pick the older one
            return None
        self.lists(("p", 0), after)
        with mock.patch.object(ui, "ask", return_value=None) as asked:
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertTrue(asked.call_args.kwargs["cancellable"])

    def test_dry_run_move_counts_a_stash_once(self):
        self.stash()
        self.lists(("m", 0), 0, ("m", 0), 0, None)
        code, out, err = self.run_cmd("saves", "manage", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("move 1,", out)

    def test_label_writes_the_note(self):
        d = self.stash()

        def label(labels):
            kw = self.calls[-1][2]
            self.assertEqual(kw["note_text"](0), "")
            self.assertIn("boss", kw["on_note"](0, "boss"))
            return None
        self.lists(label)
        code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        with open(os.path.join(d, "stash.json")) as f:
            self.assertEqual(json.load(f)["note"], "boss")
        self.assertIn("labelled 1", out)

    def test_prune_then_delete(self):
        old, mid, new = self.stash(day=1), self.stash(day=2), self.stash(day=3)

        def picks(labels):
            self.assertEqual(self.calls[-1][2]["session"]["sel"], [False, True, True])
            return ("d", 0)
        self.lists(("p", 0), picks, None)
        with mock.patch.object(ui, "ask", lambda *a, **k: "1"), mock.patch.object(ui, "confirm", lambda *a, **k: True):
            code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertEqual([os.path.exists(d) for d in (old, mid, new)], [False, False, True])
        self.assertIn("Deleted 2 stash(es)", out)

    def test_enter_lists_files(self):
        self.stash()
        self.lists(("enter", 0), None, None)
        code, out, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[1][1], ["Game.srm", "Game.state.auto"])
        self.assertIn("Nothing changed", out)

    def test_needs_a_terminal(self):
        self.stash()
        with mock.patch.object(ui, "has_terminal", lambda: False):
            code, _, err = self.run_cmd("saves", "manage")
        self.assertEqual(code, 2)
        self.assertIn("`saves manage` needs a terminal", err)


if __name__ == "__main__":
    unittest.main()
