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
from sync_roms import saves, saves_manage  # noqa: E402

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

    def test_prune_skips_unreadable(self):
        bad = os.path.join(saves.stash_root(), "gba", "Game", "20260101-000000-X")
        helpers.touch(os.path.join(bad, "Game.srm"), "abc")
        self.assertEqual(saves_manage.prune_picks(saves_manage.list_rows(), 0), [False])

    def test_inside(self):
        self.assertTrue(saves_manage.inside(os.path.join(saves.stash_root(), "gba")))
        self.assertFalse(saves_manage.inside(saves.stash_root()))
        self.assertFalse(saves_manage.inside(self.src))


if __name__ == "__main__":
    unittest.main()
