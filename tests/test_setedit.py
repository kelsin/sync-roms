import io
import contextlib
import copy
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir, storage_sets  # noqa: E402
from sync_roms import commands, edit, listedit, picker, runtime, setedit, shared, store, ui  # noqa: E402

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


class Files(StorageDir):
    def test_every_set_round_trips_to_its_file(self):
        texts = {"plain": store.set_text({"name": "Plain", "games": games()}),
                 "full": store.set_text({"name": "Full ★", "description": "All of it", "art": "shmups", "games": [
                     {"title": "A", "category": "Cave", "series": "Alpha", "system": "gba", "bucket": "gba/A.zip",
                      "files": ["gba/A2.zip"], "variants": [{"bucket": "gb/A.gb", "note": "GB: x"}]}]})}
        storage_sets(self, texts, self.root)
        sets = setedit.repo_sets()
        self.assertEqual(sorted(sets), ["full", "plain"])
        for sid, game_set in sets.items():
            with open(os.path.join(self.root, "sets", sid + ".json"), encoding="utf-8") as f:
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

    def test_added_game_keeps_its_other_fields(self):
        shown = shown_without(set(), [("gen", "gen/New.zip")])
        shown["gen"]["games"][-1].update(note="try it", files=["gen/New2.zip"])
        out = setedit.reconcile(games(), shown, "Cave")
        self.assertEqual(out[3], {"title": "New", "category": "Cave", "system": "gen", "bucket": "gen/New.zip",
                                  "note": "try it", "files": ["gen/New2.zip"]})
        self.assertEqual(list(out[3])[:4], ["title", "category", "system", "bucket"])

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
    def test_diff(self):
        before = {"a": {"name": "A", "description": "", "games": games()}, "gone": {"name": "G", "description": "", "games": games()}}
        after = {"a": {"name": "A", "description": "", "games": setedit.reconcile(games(), shown_without({"gba/A.zip"}))},
                 "fresh": {"name": "Fresh", "description": "", "games": games()[:1]}}
        found = listedit.diff_lists(before, after)
        self.assertEqual([(k, s) for k, s, _ in found], [("changed", "a"), ("new", "fresh"), ("removed", "gone")])
        self.assertEqual(found[0][2], ["- A (gba/A.zip)"])

    def test_category_change_is_listed(self):
        before = {"a": {"name": "A", "description": "", "games": games()}}
        moved = games()
        setedit.recategorize(moved, moved[1], "Cave")
        lines = listedit.diff_lists(before, {"a": {"name": "A", "description": "", "games": moved}})[0][2]
        self.assertEqual(lines, ["~ B (gba/B.zip): category Other → Cave"])


    def test_series_and_other_field_changes_are_listed(self):
        before = {"a": {"name": "A", "description": "", "games": games()}}
        after = games()
        after[0]["series"] = "Alpha"
        after[1]["note"] = "x"
        after[1]["files"] = ["gba/B2.zip"]
        lines = listedit.diff_lists(before, {"a": {"name": "A", "description": "", "games": after}})[0][2]
        self.assertEqual(lines, ["~ A (gba/A.zip): series none → Alpha", "~ B (gba/B.zip): files, note changed"])

    def test_a_reorder_alone_is_listed(self):
        before = {"a": {"name": "A", "description": "", "games": games()}}
        lines = listedit.diff_lists(before, {"a": {"name": "A", "description": "", "games": games()[::-1]}})[0][2]
        self.assertEqual(lines, ["order changed"])


class Save(StorageDir):
    """Done saves to storage: the new and changed sets' files are written (with their local copies), removed ones deleted."""

    def setUp(self):
        super().setUp()
        storage_sets(self, {"keep": {"name": "Keep", "games": games()}, "edit": {"name": "Edit", "games": games()},
                            "gone": {"name": "Gone", "games": games()}}, self.root)
        self.note = self.enterContext(mock.patch.object(edit, "note"))

    def path(self, sid):
        return os.path.join(self.root, "sets", sid + ".json")

    def run_editor(self, answer="s"):
        """Edit (drop A from Edit), delete Gone, add New with one game, then review and answer."""
        picks = iter([0, ("d", 1), 2, None])  # sorted by name: Edit, Gone, Keep; then New set, Esc to review

        def edit_one(game_set, systems, keys_of):
            if game_set["name"] == "Edit":
                game_set["games"] = game_set["games"][1:]
            else:
                game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})

        with mock.patch.object(setedit, "edit_one", edit_one), mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "confirm", return_value=True), \
                mock.patch.object(ui, "ask", side_effect=["New", ""]), \
                mock.patch.object(ui, "choose", return_value=answer), \
                mock.patch("subprocess.run", side_effect=AssertionError("no git or gh")), \
                mock.patch("shutil.which", side_effect=AssertionError("no git or gh")), \
                mock.patch.object(picker, "queue_note", return_value=False), mock.patch("builtins.print") as out:
            code = setedit.edit_sets()
        return code, str(out.call_args_list)

    def test_saving_writes_changed_and_new_sets_and_deletes_removed_ones(self):
        with open(self.path("keep"), encoding="utf-8") as f:
            keep = f.read()
        mtime = os.stat(self.path("keep")).st_mtime_ns
        code, out = self.run_editor()
        self.assertEqual(code, 0)
        self.assertIn("Saved", out)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["edit.json", "keep.json", "new.json"])
        with open(self.path("edit"), encoding="utf-8") as f:
            self.assertEqual(f.read(), store.set_text({"name": "Edit", "description": "", "games": games()[1:]}))
        with open(self.path("new"), encoding="utf-8") as f:
            self.assertEqual(f.read(), store.set_text({"name": "New", "description": "", "games": [
                {"title": "X", "system": "gba", "bucket": "gba/X.zip"}]}))
        with open(self.path("keep"), encoding="utf-8") as f:
            self.assertEqual(f.read(), keep)
        self.assertEqual(os.stat(self.path("keep")).st_mtime_ns, mtime)  # unchanged: not rewritten
        for sid in ("edit", "new"):  # the local copies follow
            with open(shared.local_path(f"sets/{sid}.json"), encoding="utf-8") as f, open(self.path(sid), encoding="utf-8") as g:
                self.assertEqual(f.read(), g.read())
        self.assertFalse(os.path.exists(shared.local_path("sets/gone.json")))
        self.assertEqual(sorted(s["id"] for s in store.set_files()), ["edit", "keep", "new"])  # the cache was reset

    def test_discard_writes_nothing(self):
        code, _ = self.run_editor("d")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["edit.json", "gone.json", "keep.json"])
        self.assertIn("Not saved", self.note.call_args.args[0])

    def test_save_sets_on_an_unmounted_storage_folder_writes_nothing(self):
        def stamps():
            folder = os.path.join(self.root, "sets")
            return {n: os.stat(os.path.join(folder, n)).st_mtime_ns for n in os.listdir(folder)}
        start = stamps()
        after = {"edit": {"name": "Edit", "description": "", "games": games()[1:]}}
        for found in ([("changed", "edit", ["edited"]), ("removed", "gone", ["4 game(s)"])],
                      [("removed", "gone", ["4 game(s)"])]):
            with self.subTest(found=found), mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), \
                    self.assertRaises(FileNotFoundError):
                setedit.save_sets({}, after, found)
        self.assertEqual(stamps(), start)
        self.assertFalse(os.path.exists(self.root + "-unmounted"))

    def test_save_sets_keeps_before_in_step_with_what_was_saved(self):
        before = setedit.repo_sets()
        after = {"edit": {"name": "Edit", "description": "", "games": games()[1:]}, "keep": before["keep"]}
        found = listedit.diff_lists(before, after)
        with mock.patch("builtins.print"):
            setedit.save_sets(before, after, found)
        self.assertEqual(before, after)
        self.assertEqual(listedit.diff_lists(before, after), [])

    def test_a_storage_error_at_the_review_is_a_note_and_the_edits_are_kept(self):
        picks = iter([3, None, 6])  # New set (after Edit, Gone, Keep), Esc to review (fails), then Quit (a set more now)

        def add_then_unmount(game_set, systems, keys_of):  # the share goes away after the editor read the sets
            game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})
            unmount = mock.patch.object(runtime, "ROOT", self.root + "-unmounted")
            unmount.start()
            self.addCleanup(unmount.stop)
        with mock.patch.object(setedit, "edit_one", add_then_unmount), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=["New", ""]), \
                mock.patch.object(ui, "choose", return_value="s"), mock.patch.object(ui, "confirm", return_value=True) as confirm, \
                mock.patch("builtins.print"):
            self.assertEqual(setedit.edit_sets(), 0)
        notes = [c.args[0] for c in self.note.call_args_list]
        self.assertIn("Couldn't save", notes[0])
        self.assertIn("-unmounted is missing", notes[0])
        confirm.assert_called_once()  # quitting asks: the edits are still pending
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["edit.json", "gone.json", "keep.json"])
        self.assertFalse(os.path.exists(os.path.join(self.root + "-unmounted")))


class SaveStale(StorageDir):
    """Saving never writes back sets that may be older than storage's."""
    path = Save.path

    def setUp(self):
        super().setUp()
        storage_sets(self, {"keep": {"name": "Keep", "games": games()}, "edit": {"name": "Edit", "games": games()},
                            "gone": {"name": "Gone", "games": games()}}, self.root)
        self.note = self.enterContext(mock.patch.object(edit, "note"))

    def listing(self):
        folder = os.path.join(self.root, "sets")
        out = {}
        for n in os.listdir(folder):
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                out[n] = f.read()
        return out

    def changes(self, before):
        after = {**copy.deepcopy(before), "edit": {"name": "Edit", "description": "", "games": games()[1:]},
                 "new": {"name": "New", "description": "", "games": games()}}
        del after["gone"]
        return after, listedit.diff_lists(before, after)

    def test_a_set_another_machine_changed_saves_nothing(self):
        for sid, text in (("edit", store.set_text({"name": "Edit", "games": games()[2:]})),  # changed
                          ("gone", None),  # already deleted
                          ("new", store.set_text({"name": "New", "games": []}))):  # created meanwhile
            with self.subTest(sid=sid):
                before = setedit.repo_sets()
                after, found = self.changes(before)
                if text is None:
                    os.remove(self.path(sid))
                else:
                    with open(self.path(sid), "w", encoding="utf-8") as f:
                        f.write(text)
                start = self.listing()
                with self.assertRaises(setedit.Stale) as e, mock.patch("builtins.print"):
                    setedit.save_sets(before, after, found)
                self.assertIn(f"{sid} already in storage" if sid == "new" else f"{sid} changed in storage", str(e.exception))
                self.assertEqual(self.listing(), start)
                storage_sets(self, {"keep": {"name": "Keep", "games": games()}, "edit": {"name": "Edit", "games": games()},
                                    "gone": {"name": "Gone", "games": games()}}, self.root)
                if os.path.exists(self.path("new")):
                    os.remove(self.path("new"))

    def test_a_new_set_another_machine_added_names_the_cache_update(self):
        before = setedit.repo_sets()
        after, found = self.changes(before)
        with open(self.path("new"), "w", encoding="utf-8") as f:
            f.write(store.set_text({"name": "New", "games": []}))
        with self.assertRaises(setedit.Stale) as e, mock.patch("builtins.print"):
            setedit.save_sets(before, after, found)
        self.assertIn("new already in storage", str(e.exception))
        self.assertIn("sync-roms cache update", str(e.exception))

    def test_a_new_set_whose_id_has_a_file_that_isnt_utf8_saves_nothing(self):
        text = '{"name": "Café", "games": []}'.encode("latin-1")
        path = self.put("sets/b.json", text)
        with contextlib.redirect_stderr(io.StringIO()):
            before = setedit.repo_sets()  # b.json is skipped, so the id looks free
        after = {**copy.deepcopy(before), "b": {"name": "B", "description": "", "games": games()}}
        with self.assertRaises(setedit.Stale) as e:
            setedit.save_sets(before, after, listedit.diff_lists(before, after))
        self.assertIn("b already in storage", str(e.exception))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), text)

    def run_editor(self, picks, edit_one, choose="s"):
        picks = iter(picks)
        with mock.patch.object(setedit, "edit_one", edit_one), mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "choose", return_value=choose), \
                mock.patch.object(ui, "confirm", return_value=True) as confirm, \
                mock.patch.object(picker, "queue_note", return_value=False), mock.patch("builtins.print"):
            code = setedit.edit_sets()
        return code, confirm

    def test_after_a_stale_refusal_reopening_the_editor_saves(self):
        theirs = games()[:2]

        def edit_and_race(game_set, systems, keys_of):  # another machine saves Edit while this one edits it
            game_set["games"] = game_set["games"][1:]
            with open(self.path("edit"), "w", encoding="utf-8") as f:
                f.write(store.set_text({"name": "Edit", "games": theirs}))
        code, confirm = self.run_editor([0, None, 5], edit_and_race)  # open Edit, Esc to review (refused), Quit
        self.assertEqual(code, 0)
        self.assertIn("changed in storage", self.note.call_args_list[0].args[0])
        self.assertIn("reopen the sets editor", self.note.call_args_list[0].args[0])
        confirm.assert_called_once()  # the edits were still pending

        def drop_first(game_set, systems, keys_of):
            game_set["games"] = game_set["games"][1:]
        code, _ = self.run_editor([0, None], drop_first)  # reopened in the same run: storage's Edit, saved
        self.assertEqual(code, 0)
        with open(self.path("edit"), encoding="utf-8") as f:
            self.assertEqual(f.read(), store.set_text({"name": "Edit", "games": theirs[1:]}))

    def test_a_failing_write_profile_keeps_the_edits_and_writes_nothing(self):
        from sync_roms import s3

        def no_profile(*a, **k):
            ui.fail("AWS profile 'roms' not found; define it in ~/.aws/config and ~/.aws/credentials", 3)

        def drop_first(game_set, systems, keys_of):
            game_set["games"] = game_set["games"][1:]
        start = self.listing()
        with mock.patch.object(s3, "put_text", no_profile), contextlib.redirect_stderr(io.StringIO()):
            code, confirm = self.run_editor([0, None, 5], drop_first)  # open Edit, Esc to review (fails), Quit
        self.assertEqual(code, 0)
        self.assertIn("Couldn't save the sets to storage", self.note.call_args_list[0].args[0])
        confirm.assert_called_once()  # the edits were still pending
        self.assertEqual(self.listing(), start)

    def test_sets_read_from_the_local_copies_save_nothing(self):
        before = setedit.repo_sets()
        after, found = self.changes(before)
        start = self.listing()
        with self.assertRaises(setedit.Stale) as e:
            setedit.save_sets(before, after, found, from_fallback=True)
        self.assertIn("local copies", str(e.exception))
        self.assertEqual(self.listing(), start)

    def test_the_editor_notes_a_stale_read_and_keeps_the_edits(self):
        picks = iter([3, None, 6])  # New set (after Edit, Gone, Keep), Esc to review (refused), then Quit
        with mock.patch.object(setedit, "edit_one", lambda g, s, k: g["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(store, "sets_from_fallback", return_value=True), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=["New", ""]), \
                mock.patch.object(ui, "choose", return_value="s"), mock.patch.object(ui, "confirm", return_value=True) as confirm, \
                mock.patch("builtins.print"):
            self.assertEqual(setedit.edit_sets(), 0)
        note = self.note.call_args_list[0].args[0]
        self.assertIn("local copies", note)
        self.assertIn("nothing was saved", note)
        confirm.assert_called_once()  # quitting asks: the edits are still pending
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["edit.json", "gone.json", "keep.json"])


class DeleteSet(StorageDir):
    def test_deletes_only_that_object_its_copy_and_rereads(self):
        storage_sets(self, {"a": {"name": "A", "games": games()}, "b": {"name": "B", "games": games()}}, self.root)
        self.put("sets/a.json.bak", b"x")
        self.assertEqual([s["id"] for s in store.set_files()], ["a", "b"])
        with mock.patch("builtins.print"):
            store.delete_set("a")
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "sets"))), ["a.json.bak", "b.json"])
        self.assertFalse(os.path.exists(shared.local_path("sets/a.json")))
        self.assertEqual([s["id"] for s in store.set_files()], ["b"])

    def test_an_unmounted_storage_folder_raises(self):
        storage_sets(self, {"a": {"name": "A", "games": games()}}, self.root)
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), self.assertRaises(FileNotFoundError):
            store.delete_set("a")
        self.assertTrue(os.path.exists(os.path.join(self.root, "sets", "a.json")))


class SeriesEditor(unittest.TestCase):
    def series_games(self):
        return [{"title": "A", "category": "Cave", "series": "Alpha", "system": "gba", "bucket": "gba/A.zip"},
                {"title": "B", "series": "Alpha", "system": "gba", "bucket": "gba/B.zip"},
                {"title": "C", "system": "gen", "bucket": "gen/C.zip"}]

    def run_editor(self, picks, lists, ask=()):
        game_set = {"name": "S", "games": self.series_games()}
        picks, lists, seen = iter(picks), iter(lists), []

        def fake(title, labels, **kw):
            if not kw.get("multi"):
                return next(picks)
            flip, then = next(lists)
            seen.append((list(labels), kw.get("filters"), kw.get("hotkeys"), kw.get("hint"), kw.get("key_help")))
            kw["session"]["sel"] = [on != (label in flip) for label, on in zip(labels, kw["session"]["sel"])]
            return (then, 0) if then else kw["session"]["sel"]

        keys = {"gba": {"gba/A.zip", "gba/B.zip"}, "gen": {"gen/C.zip"}}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(edit, "note"), \
                mock.patch.object(store, "repo_json", side_effect=lambda n: [] if n == "series" else SYSTEMS), \
                mock.patch.object(ui, "ask", side_effect=list(ask)), mock.patch("builtins.print"), \
                mock.patch.object(setedit.cardedit, "pick_series", return_value="Alpha"):
            try:
                setedit.edit_one(game_set, SYSTEMS, lambda b: keys[b])
            except StopIteration:
                pass
        return game_set, seen

    def test_r_narrows_to_the_series_c_clears_and_hidden_games_are_kept(self):
        game_set, seen = self.run_editor([0, None], [(set(), setedit.cardedit.SERIES_KEY), ({"Game Boy Advance — B"}, setedit.cardedit.CLEAR_KEY),
                                                     (set(), None)])
        self.assertEqual(len(seen[0][0]), 3)
        self.assertEqual(len(seen[1][0]), 2)  # narrowed to Alpha
        self.assertIn("Alpha", seen[1][1])
        self.assertEqual(len(seen[2][0]), 3)  # cleared
        self.assertEqual(seen[2][1], "")
        self.assertEqual(seen[0][2], (setedit.cardedit.SERIES_KEY, setedit.cardedit.CLEAR_KEY))
        self.assertIn("series", seen[0][3])
        self.assertIn("c clear filters", seen[0][3])
        self.assertEqual(seen[1][1], "Alpha (c clear filters)")
        self.assertEqual([k for k, _ in seen[0][4]], ["r", "c"])  # what ? lists
        self.assertEqual([g["bucket"] for g in game_set["games"]], ["gba/A.zip", "gen/C.zip"])  # B off, C kept
        self.assertEqual(game_set["games"][0]["series"], "Alpha")

    def test_set_a_games_series_keeps_key_order_and_empty_clears(self):
        game_set, _ = self.run_editor([4, 2, 4, 0, None], [], ask=["Beta", ""])
        c = game_set["games"][2]
        self.assertEqual(c["series"], "Beta")
        self.assertEqual(list(c), ["title", "series", "system", "bucket"])
        self.assertNotIn("series", game_set["games"][0])  # A's cleared by the empty answer
        self.assertEqual(setedit.set_series(game_set["games"], game_set["games"][0], "Gamma")["series"], "Gamma")
        self.assertEqual(list(game_set["games"][0]), ["title", "category", "series", "system", "bucket"])


    def test_esc_at_the_series_question_keeps_the_series(self):
        game_set, _ = self.run_editor([4, 0, None], [], ask=[None])
        self.assertEqual(game_set["games"][0]["series"], "Alpha")

    def test_esc_at_the_category_question_keeps_the_category(self):
        game_set, _ = self.run_editor([3, 0, None], [], ask=[None])
        self.assertEqual(game_set["games"][0]["category"], "Cave")

    def test_empty_at_the_category_question_still_removes_it(self):
        game_set, _ = self.run_editor([3, 0, None], [], ask=[""])
        self.assertNotIn("category", game_set["games"][0])


class Editor(unittest.TestCase):
    def setUp(self):
        self.note = self.enterContext(mock.patch.object(edit, "note"))  # what the editor says at its end
        self.addCleanup(setattr, store, "_sets", "[]")  # edit_sets resets the sets; back to none, as isolate leaves it

    def test_new_set_flow_saves(self):
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks = iter([1, None])  # "New set" (after the one existing set), then Esc to review
        saved = {}

        def add_game(game_set, systems, keys_of):
            game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})

        with mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(setedit, "edit_one", add_game), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=["My Set", "about it"]), \
                mock.patch.object(ui, "choose", return_value="s"), \
                mock.patch.object(setedit, "save_sets", lambda before, after, found, from_fallback: saved.update(after=after, found=found)), \
                mock.patch.object(picker, "queue_note", return_value=True) as queued, mock.patch("builtins.print") as out:
            self.assertEqual(setedit.edit_sets(), 0)
        self.assertEqual([(k, s) for k, s, _ in saved["found"]], [("new", "my-set")])
        self.assertEqual(saved["after"]["my-set"]["description"], "about it")
        self.assertIn("Saved 1 set(s) to storage", queued.call_args.args[0])  # on the menu, and printed after the session
        self.assertEqual(queued.call_args.kwargs, {"keep": True})
        self.assertNotIn("Saved", str(out.call_args_list))

    def test_ctrl_c_with_changes_goes_to_the_review(self):
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks = iter([1, KeyboardInterrupt, None])  # "New set", Ctrl-C, keep editing, then Esc to review
        saved = {}

        def pick(*a, **k):
            value = next(picks)
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value

        def add_game(game_set, systems, keys_of):
            game_set["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})

        with mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(setedit, "edit_one", add_game), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(ui, "ask", side_effect=["My Set", "about it"]), \
                mock.patch.object(ui, "choose", side_effect=["e", "s"]) as choose, mock.patch("builtins.print"), \
                mock.patch.object(setedit, "save_sets", lambda before, after, found, from_fallback: saved.update(after=after, found=found)):
            self.assertEqual(setedit.edit_sets(), 0)  # keep editing ended the interrupt: the later Done ends normally
        self.assertEqual(choose.call_count, 2)
        self.assertEqual([(k, s) for k, s, _ in saved["found"]], [("new", "my-set")])

    def stopped(self, picks, answers):
        """Run the editor on no sets until it stops with KeyboardInterrupt; picks and answers may hold Ctrl-C.
        Returns the review prompts shown and the saves made."""
        picks, saved = iter(picks), []

        def pick(*a, **k):
            value = next(picks)
            if value is KeyboardInterrupt:
                raise KeyboardInterrupt
            return value
        with mock.patch.object(setedit, "repo_sets", return_value={}), \
                mock.patch.object(setedit, "edit_one", lambda g, s, k: g["games"].append({"title": "X", "system": "gba", "bucket": "gba/X.zip"})), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", pick), \
                mock.patch.object(ui, "ask", side_effect=["My Set", ""]), \
                mock.patch.object(ui, "choose", side_effect=answers) as choose, mock.patch("builtins.print"), \
                mock.patch.object(setedit, "save_sets", lambda before, after, found, from_fallback: saved.append(found)), \
                self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        return choose.call_count, len(saved)

    def test_ctrl_c_review_that_saves_or_discards_still_stops(self):
        for answer, prs in (("s", 1), ("d", 0)):
            with self.subTest(answer=answer):  # "New set" (no sets yet), then Ctrl-C
                self.assertEqual(self.stopped([0, KeyboardInterrupt], [answer]), (1, prs))

    def test_ctrl_c_after_keep_editing_reviews_again(self):  # Ctrl-C, keep editing, Ctrl-C, discard
        self.assertEqual(self.stopped([0, KeyboardInterrupt, KeyboardInterrupt], ["e", "d"]), (2, 0))

    def test_ctrl_c_at_the_review_prompt_stops(self):
        self.assertEqual(self.stopped([0, KeyboardInterrupt], [KeyboardInterrupt]), (1, 0))

    def test_ctrl_c_without_changes_reviews_nothing(self):
        with mock.patch.object(setedit, "repo_sets", return_value={}), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", side_effect=KeyboardInterrupt), \
                mock.patch.object(ui, "choose") as choose, self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        choose.assert_not_called()

    def interrupted(self, picks, lists, sets=(), ask=None):
        """Open set old (games()) in the real set editor; picks answer the single-choice lists, lists holds per toggle
        list (labels to switch, what it then does: KeyboardInterrupt, a hotkey or None for Enter); ask is ui.ask's side_effect.
        The review saves.
        Returns the review prompts shown, the sets saved (None without a save) and the ui.ask mock."""
        before = {"old": {"name": "Old", "description": "", "games": games()}}
        picks, lists, saved = iter(picks), iter(lists), {}
        keys = {"gba": {"gba/A.zip", "gba/B.zip", "gba/D.zip", "gba/D2.zip"}, "gen": {"gen/C.zip", "gen/E.zip"}}

        def fake(title, labels, **kw):
            if not kw.get("multi"):
                return next(picks)
            flip, then = next(lists)
            kw["session"]["sel"] = [on != (label in flip) for label, on in zip(labels, kw["session"]["sel"])]
            if then is KeyboardInterrupt:
                raise KeyboardInterrupt
            return (then, 0) if then else kw["session"]["sel"]

        with mock.patch.object(setedit, "repo_sets", return_value=before), \
                mock.patch.object(store, "repo_json", return_value=SYSTEMS), mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(store, "folder_keys", lambda bucket: keys.get(bucket, set())), \
                mock.patch.object(store, "load_sets", return_value=list(sets)), \
                mock.patch.object(listedit, "stocked", lambda systems: systems), \
                mock.patch.object(listedit, "file_counts", lambda systems: [[] for _ in systems]), \
                mock.patch.object(ui, "ask", side_effect=ask) as ask, mock.patch.object(ui, "choose", return_value="s") as choose, \
                mock.patch("builtins.print"), \
                mock.patch.object(setedit, "save_sets", lambda before, after, found, from_fallback: saved.update(after=after)), \
                self.assertRaises(KeyboardInterrupt):
            setedit.edit_sets()
        return choose.call_count, saved.get("after"), ask

    def test_ctrl_c_keeps_the_open_lists_removals(self):
        reviews, after, _ = self.interrupted([0, 0], [({"Cave — Game Boy Advance — A", "Cave — Genesis — C"}, KeyboardInterrupt)])
        self.assertEqual(reviews, 1)
        self.assertEqual([g["bucket"] for g in after["old"]["games"]], ["gba/B.zip", "nes/Odd.zip"])

    def test_ctrl_c_keeps_the_add_games_lists_toggles_with_no_category(self):  # Genesis: E on, C off, Ctrl-C
        reviews, after, ask = self.interrupted([0, 1, 2], [({"E.zip", "C.zip"}, KeyboardInterrupt)])
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

    def test_ctrl_c_at_the_category_question_keeps_the_games_with_no_category(self):
        mix = {"id": "mix", "name": "Mix", "games": [games()[0], {"title": "D", "system": "gba", "bucket": "gba/D.zip",
                                                                  "files": ["gba/D2.zip"]}]}
        e = {"title": "E", "system": "gen", "bucket": "gen/E.zip"}
        d = {"title": "D", "system": "gba", "bucket": "gba/D.zip", "files": ["gba/D2.zip"]}
        for picks, flip, added in (([0, 1, 2], {"E.zip"}, e), ([0, 2, 0], {"Game Boy Advance — D"}, d)):
            with self.subTest(picks=picks):  # a game on, Enter, Ctrl-C at the category question
                reviews, after, ask = self.interrupted(picks, [(flip, None)], sets=[mix], ask=KeyboardInterrupt)
                ask.assert_called_once()
                self.assertEqual(reviews, 1)
                self.assertEqual(after["old"]["games"], games() + [added])

    def test_ctrl_c_in_a_list_with_nothing_toggled_reviews_nothing(self):
        mix = {"id": "mix", "name": "Mix", "games": [games()[0]]}
        for picks in ([0, 0], [0, 1, 2], [0, 2, 0]):
            with self.subTest(picks=picks):
                self.assertEqual(self.interrupted(picks, [(set(), KeyboardInterrupt)], sets=[mix])[:2], (0, None))

    def test_command_is_wired(self):
        with mock.patch.object(setedit, "edit_sets", return_value=0) as run:
            self.assertEqual(commands.run(["sets", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["sets"], ["edit"])


if __name__ == "__main__":
    unittest.main()
