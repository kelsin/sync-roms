import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from rich.cells import cell_len
from textual import events

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import DataDir  # noqa: E402,F401  (re-exported: other test modules still import it from here)
from helpers import feed_list, pilot_list, screen_lines, screen_text, shown_preview  # noqa: E402
from helpers import VITA_DLC as DLC, VITA_GAME as G, VITA_UPDATE as NEW  # noqa: E402
from sync_roms import edit, names, picker, runtime, s3, store, ui  # noqa: E402

def list_systems():
    return {
        "gba": {"name": "Game Boy Advance", "bucket": "gba", "full_system": False,
                "games": [{"title": "A", "bucket": "gba/A.zip"}]},
        "gen": {"name": "Genesis", "bucket": "gen", "full_system": False, "games": []},
        "ful": {"name": "Full", "bucket": "ful", "full_system": True, "games": []},
    }


MIX = {"name": "Mix", "games": [
    {"title": "Zed", "system": "gen", "bucket": "gen/Zed.zip"},
    {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
    {"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"},
    {"title": "Nope", "system": "nes", "bucket": "nes/Nope.zip"},
    {"title": "Skip", "system": "ful", "bucket": "ful/Skip.zip"},
]}


class Helpers(unittest.TestCase):
    def test_valid_card_name(self):
        for bad in ("", "  ", "a/b"):
            self.assertIsNotNone(edit.valid_card_name(bad, set()))
        self.assertIsNotNone(edit.valid_card_name("RG SP", {"RG SP"}))
        self.assertIsNone(edit.valid_card_name("RG SP", {"other"}))

    def test_system_rows_hide_vita_extras_unless_listed(self):
        s = {"bucket": "psvita", "games": [{"bucket": DLC}]}
        self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [DLC, G])
        s["games"] = []
        self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [G])

    def test_sort_key_skips_leading_articles(self):
        titles = ["Lost Vikings 2", "The Lost Vikings", "An American Tail", "A Boy and His Blob", "Theme Park",
                  "Bomberman", "Another World", "Animal Crossing"]
        self.assertEqual(sorted(titles, key=store.sort_key),
                         ["An American Tail", "Animal Crossing", "Another World", "Bomberman", "A Boy and His Blob",
                          "The Lost Vikings", "Lost Vikings 2", "Theme Park"])

    def test_system_rows_sort_without_leading_articles(self):
        s = {"bucket": "snes", "games": []}
        keys = {"snes/Lost Vikings 2 (USA).zip", "snes/The Lost Vikings (USA).zip", "snes/Mega Man X (USA).zip",
                "snes/Lost Vikings, The (Europe).zip"}
        self.assertEqual([r[1] for r in edit.system_rows(s, keys)],
                         ["snes/The Lost Vikings (USA).zip", "snes/Lost Vikings, The (Europe).zip",
                          "snes/Lost Vikings 2 (USA).zip", "snes/Mega Man X (USA).zip"])

    def test_system_rows_sort_arcade_sets_by_scraped_name(self):
        s = {"bucket": "mame", "games": []}
        scraped = {"mame": {"aaa.zip": "The Simpsons (4 Players World, set 1)", "zzz.zip": "Galaga (Namco rev. B)"}}
        with mock.patch.object(names, "_scraped", scraped):
            self.assertEqual([r[1] for r in edit.system_rows(s, {"mame/aaa.zip", "mame/zzz.zip"})],
                             ["mame/zzz.zip", "mame/aaa.zip"])

    def test_system_rows_use_arcade_names(self):
        s = {"bucket": "fbneo", "games": []}
        with mock.patch.object(names, "_scraped", {"fbneo": {"1941j.zip": "1941: Counter Attack (Japan)"}}):
            row = edit.system_rows(s, {"fbneo/1941j.zip"})[0]
        self.assertEqual(row[2], "1941: Counter Attack (Japan)")
        self.assertEqual(row[3], "1941: Counter Attack (Japan) — 1941j.zip")
        gba = edit.system_rows({"bucket": "gba", "games": [{"bucket": "gba/B.zip"}]}, {"gba/A.zip"})
        self.assertEqual([r[3] for r in gba], ["A.zip", "B.zip  ⚠️ not in storage"])

    def test_list_rows_keep_saved_title(self):
        s = {"bucket": "fbneo", "name": "FBNeo"}
        gs = {"games": [{"system": "fbneo", "bucket": "fbneo/1941j.zip", "title": "Mine"}]}
        rows = edit.list_rows(gs, {"fbneo": s}, lambda _s: {"fbneo/1941j.zip"})
        self.assertEqual(rows[0][2], "Mine")

    def test_list_rows_ignore_a_category(self):
        games = {"games": [{"title": "Z", "system": "gba", "bucket": "gba/Z.zip", "category": "First"},
                           {"title": "A", "system": "gba", "bucket": "gba/A.zip", "category": "Second"}]}
        rows = edit.list_rows(games, list_systems(), lambda s: set())
        self.assertEqual([r[1] for r in rows], ["gba/A.zip", "gba/Z.zip"])
        self.assertTrue(rows[0][3].startswith("Game Boy Advance — A"))


class Saving(DataDir):
    def test_save_lists_writes_card(self):
        store.update_card("c", device="x", layout="esde")
        store.save_lists({"c": {"gba": [{"bucket": "gba/A.zip"}]}})
        self.assertEqual(self.read("cards.json")["c"], {"device": "x", "layout": "esde", "games": {"gba": [{"bucket": "gba/A.zip"}]}})
        self.assertFalse(os.path.exists(self.path("games.json")))


class EscPrompt(unittest.TestCase):
    def test_a_poll_tick_at_the_keep_or_revert_prompt_keeps_asking(self):
        polled = []
        self.assertEqual(feed_list(["tab", "escape", None, "enter"], "t", ["a", "b"], multi=True,
                                   poll=lambda: polled.append(1)), [True, False])
        self.assertEqual(polled, [])  # the prompt waits for its key


class RevertKey(unittest.TestCase):
    def run_keys(self, keys, **kw):
        """filter_list over three rows with real keys: (its result, the status row after each key)."""
        rows = []

        def run(model):
            for k in keys:
                got = model.key(k)
                rows.append(model.line[0])
                if got is not picker.KEEP:
                    return got
            raise AssertionError("the list is still open after the last key")
        with mock.patch.object(picker, "_run", run):
            return picker.filter_list("t", ["a", "b", "c"], multi=True, diff_marks=True, **kw), rows

    def test_u_with_one_change_reverts_at_once(self):
        state, rows = self.run_keys(["space", "u", "enter"])
        self.assertEqual(state, [False, False, False])
        self.assertTrue(rows[0].startswith("+1 −0"))

    def test_u_with_several_changes_asks_first_and_y_reverts(self):
        state, rows = self.run_keys(["space", "j", "space", "u", "y", "enter"])
        self.assertEqual(rows[3], "Revert 2 change(s)? [y/N]")
        self.assertEqual(state, [False, False, False])

    def test_any_other_key_than_y_keeps_the_changes(self):
        for answer in ("n", "enter", "escape"):
            state, rows = self.run_keys(["space", "j", "space", "u", answer, "enter"])
            self.assertEqual(state, [True, True, False], answer)
            self.assertTrue(rows[4].startswith("+2 −0"), answer)

    def test_the_count_includes_changes_the_caller_keeps_in_hidden_rows(self):
        reverted = []
        state, rows = self.run_keys(["space", "u", "y", "j", "enter"], outside=(0, 1), on_revert=lambda: reverted.append(1))
        self.assertTrue(rows[0].startswith("+1 −1"))  # the counter shows them too
        self.assertEqual(rows[1], "Revert 2 change(s)? [y/N]")
        self.assertEqual(state, [False, False, False])
        self.assertEqual(reverted, [1])
        self.assertTrue(rows[3].startswith("+0 −0"))  # and they are gone from it once reverted

    def test_u_with_only_a_hidden_change_reverts_it_at_once(self):
        reverted = []
        _, rows = self.run_keys(["u", "j", "enter"], outside=(1, 0), on_revert=lambda: reverted.append(1))
        self.assertEqual(reverted, [1])
        self.assertTrue(rows[1].startswith("+0 −0"))


class EditBase(DataDir):
    """The edit_manifest() driver the flow tests build on; holds no tests, so subclasses don't rerun any."""

    def run_edit(self, picks, confirmed, name="newcard", extra=None, asked=None):
        """extra: card fields the new card gets when saved; asked: gets the keyword arguments of each ui.confirm."""
        picks = iter(picks)
        real_save = store.save_card

        def save(card, *setup):
            real_save(card, *setup)
            if extra:
                store.update_card(card, **extra)

        def confirm(*a, **k):
            if asked is not None:
                asked.append(k)
            return confirmed
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch("builtins.input", return_value=name), \
                mock.patch.object(picker, "choose_setup", return_value=(None, "esde")), \
                mock.patch.object(store, "save_card", side_effect=save), \
                mock.patch.object(ui, "confirm", side_effect=confirm), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s" if confirmed else "d"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()


class SaveReview(EditBase):
    def test_esc_at_the_save_review_means_keep_editing(self):
        asked, picks = [], iter([3, 0, None, 4])

        def fake(title, options, *a, **k):
            if k.get("multi"):
                return [not k["initial"][0]] + list(k["initial"][1:])
            return next(picks)
        answers = iter(["l", "d"])  # the full review's own question after l too

        def choose(question, letters, default, legend="", **k):
            asked.append(k)
            return next(answers)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=fake), mock.patch.object(edit, "note"), \
                mock.patch.object(ui, "choose", side_effect=choose), contextlib.redirect_stdout(io.StringIO()):
            edit.edit_manifest()
        self.assertEqual(asked, [{"esc": "e"}, {"esc": "e"}])


class EditFlow(EditBase):
    def test_new_card_left_empty_and_declined_is_removed(self):
        # top menu: Cards; "New card" is option 0 with no cards; the card editor Esc; back; the top menu Esc to finish
        self.assertEqual(self.run_edit([0, 0, None, None, None], confirmed=False), 0)
        self.assertNotIn("newcard", self.read("cards.json"))

    def test_new_card_left_empty_and_cancelled_is_kept(self):
        asked = []
        self.assertEqual(self.run_edit([0, 0, None, None, None], confirmed=None, asked=asked), 0)
        self.assertIn("newcard", self.read("cards.json"))
        self.assertEqual(asked, [{"cancellable": True}])

    def test_the_keep_question_is_not_asked_for_a_card_with_collections_or_guest(self):
        for extra in ({"collections": ["x"]}, {"guest": True}):
            with self.subTest(extra):
                asked = []
                self.run_edit([0, 0, None, None, None], confirmed=False, extra=extra, asked=asked)
                self.assertEqual(asked, [])
                self.assertIn("newcard", self.read("cards.json"))
                os.remove(self.path("cards.json"))

    def test_new_card_saved_with_setup(self):
        self.assertEqual(self.run_edit([0, 0, None, None, None], confirmed=True), 0)
        self.assertEqual(self.read("cards.json")["newcard"], {"device": "full", "layout": "esde"})
        self.assertFalse(os.path.exists(self.path("games.json")))

    def test_no_changes_nothing_saved(self):
        self.assertEqual(self.run_edit([4], confirmed=True), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))


class MenuActions(EditBase):
    def run_menu(self, picks, confirm=True, inputs=("renamed",), multi=None):
        picks, inputs = iter(picks), iter(inputs)

        def fake(*a, **k):
            if k.get("multi") and multi:
                return multi(k["initial"], a[1])
            return next(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch("builtins.input", side_effect=lambda *a: next(inputs)), \
                mock.patch.object(ui, "confirm", return_value=confirm), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()

    def test_rename_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.RENAME_KEY, 0), None, 4])
        self.assertEqual(list(self.read("cards.json")), ["renamed"])

    def test_delete_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.DELETE_KEY, 0), None, 4])
        self.assertEqual(self.read("cards.json"), {})

    def test_declined_delete_keeps_the_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.DELETE_KEY, 0), None, 4], confirm=False)
        self.assertIn("c", self.read("cards.json"))

    def test_done_with_no_changes_saves_nothing(self):
        self.assertEqual(self.run_menu([4]), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def change_device(self, games):
        """Save a card with these games, then give it a device that only plays gba; returns the games saved."""
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full", "games": games}})
        device = {**store.load_manifest()["devices"][0], "systems": ["gba"]}
        with mock.patch.object(picker, "choose_setup", return_value=(device, "esde")):
            self.assertEqual(self.run_menu([0, (edit.SETUP_KEY, 0), None, 4]), 0)  # Cards, v on the card, back, Done
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["device"], device["id"])
        return entry["games"]

    def test_changing_the_device_keeps_a_full_systems_saved_game_list(self):
        stash = {"full_system": True, "games": [{"bucket": "gba/A.zip"}]}
        saved = self.change_device({"gba": stash, "gb": [{"bucket": "gb/B.gb"}]})
        self.assertEqual(saved, {"gba": stash})  # gb goes: the device can't play it

    def test_changing_the_device_keeps_entries_of_unknown_systems(self):
        unknown = [{"bucket": "nosuchsystem/X.zip"}]
        saved = self.change_device({"gb": [{"bucket": "gb/B.gb"}], "nosuchsystem": unknown})
        self.assertEqual(saved, {"nosuchsystem": unknown})

    def device_case(self):
        dev = store.load_manifest()["devices"][0]
        base = store.device_defaults()[dev["id"]]["systems"]
        ids = [s["bucket"] for s in sorted(store.load_manifest()["systems"], key=store.system_sort_key)]
        return dev, base, ids

    def test_returning_to_the_defaults_drops_the_overlay_entry(self):
        dev, base, ids = self.device_case()
        extra = next(x for x in ids if x not in base)
        self.write_json("device-systems.json", {dev["id"]: {"add": [extra]}})
        self.run_menu([3, 0, None, 4], multi=lambda initial, labels: [x in base for x in ids])
        self.assertEqual(self.read("device-systems.json"), {})

    def test_opening_a_device_and_changing_nothing_is_not_an_edit(self):
        dev, base, ids = self.device_case()
        extra = next(x for x in ids if x not in base)
        self.write_json("device-systems.json", {dev["id"]: {"add": [extra]}})
        self.run_menu([3, 0, None, 4], multi=lambda initial, labels: list(initial))
        self.assertEqual(self.read("device-systems.json"), {dev["id"]: {"add": [extra]}})
        self.assertFalse(os.path.exists(self.path("device-systems.json.bak")))

    def top_titles(self, picks):
        seen = []

        def fake(title, options, *a, **k):
            seen.append((title, list(options)))
            return next(picks)
        picks = iter(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch.object(edit, "note"), contextlib.redirect_stdout(io.StringIO()):
            edit.edit_manifest()
        return seen

    def test_top_menu_entries_are_exactly_cards_tags_collections_and_device_systems(self):
        top = self.top_titles([None])[0][1]
        self.assertEqual(top, ["💳 Cards", "🏷️ Tags", "💖 Collections", "🧩 Device systems",
                               "✅ Done (review & save)", "🚪 Quit (card games are already saved)"])

    def test_choosing_tags_calls_edit_tags_and_a_failure_returns_to_the_menu(self):
        from sync_roms import tageditor
        with mock.patch.object(tageditor, "edit_tags", side_effect=SystemExit(3)) as run:
            self.assertEqual(self.run_menu([1, 4]), 0)
        run.assert_called_once()

    def test_choosing_collections_opens_the_collection_editor(self):
        from sync_roms import collectionedit
        with mock.patch.object(collectionedit, "edit_collections", return_value=0) as run:
            self.assertEqual(self.run_menu([2, 4]), 0)
        run.assert_called_once()

    def test_choosing_device_systems_opens_the_device_list(self):
        seen = self.top_titles([3, None, 4])
        self.assertIn("recommended systems", seen[1][0])

    def cursors_of(self, picks, prefix):
        """edit_manifest() with filter_list answering picks in turn (a multi list: unchanged); the cursor each list whose
        title starts with prefix was opened on."""
        picks, cursors = iter(picks), []

        def fake(title, options, *a, **k):
            if title.startswith(prefix):
                cursors.append(k.get("cursor"))
            return list(k["initial"]) if k.get("multi") else next(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=fake), mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            edit.edit_manifest()
        return cursors

    def test_the_card_list_reopens_on_the_row_just_used(self):
        from sync_roms import cardedit
        self.write_json("cards.json", {x: {"layout": "esde", "device": "full"} for x in "abc"})
        with mock.patch.object(cardedit, "edit_card"):
            self.assertEqual(self.cursors_of([0, 2, 1, None, 4], "💳 Which"), [0, 2, 1])

    def test_the_device_list_reopens_on_the_row_just_used(self):
        self.assertEqual(self.cursors_of([3, 2, 1, None, 4], "🧩 Which"), [0, 2, 1])

    def test_choosing_a_card_calls_the_card_editor(self):
        from sync_roms import cardedit
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        with mock.patch.object(cardedit, "edit_card") as run:
            self.run_menu([0, 0, None, 4])
        self.assertEqual(run.call_args[0][0], "c")

    def test_unwritable_cards_json_refuses_to_edit(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{oops")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_menu([4])
        self.assertNotEqual(cm.exception.code, 0)


class ListRows(unittest.TestCase):
    def test_rows_sorted_by_system_skip_unknown(self):
        rows = edit.list_rows(MIX, list_systems(), lambda s: {"gba/A.zip", "gen/Zed.zip"})
        self.assertEqual([r[1] for r in rows], ["ful/Skip.zip", "gba/A.zip", "gba/Gone.zip", "gen/Zed.zip"])
        self.assertIn("not in storage", rows[2][3])
        self.assertNotIn("not in storage", rows[1][3])

    def test_toggle_adds_and_removes(self):
        by = list_systems()
        rows = edit.list_rows(MIX, by, lambda s: set())
        with mock.patch.object(picker, "filter_list", return_value=[True, False, True, True]) as fl:
            edit.toggle_games("t", rows)
        self.assertEqual(fl.call_args.kwargs["initial"], [True, True, False, False])
        self.assertEqual(fl.call_args.kwargs["locked"], [True, False, False, False])
        self.assertEqual(fl.call_args.kwargs["locked_note"], [edit.FULL_SYSTEM_NOTE, "", "", ""])
        self.assertIs(fl.call_args.kwargs["select_all"], True)  # on unless the caller turns it off
        self.assertEqual(by["ful"]["games"], [])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/Gone.zip"])
        self.assertEqual([g["bucket"] for g in by["gen"]["games"]], ["gen/Zed.zip"])

    def test_toggle_games_shows_variant_notes(self):
        by = list_systems()
        listing = {"name": "Mix", "games": [{"title": "A", "system": "gba", "bucket": "gba/A.zip"},
                                            {"title": "Zed", "system": "gen", "bucket": "gen/Zed.zip"}]}
        variants = {"gba/A.zip": [{"bucket": "gb/A.gb", "note": "GB: x"}]}
        parents = {"gb/A.gb": {"bucket": "gba/A.zip", "system": "gba", "title": "A"}}
        rows = edit.list_rows(listing, by, lambda s: set())
        with mock.patch.object(edit.tags, "variant_index", return_value=(variants, parents)), \
                mock.patch.object(store, "repo_json", return_value=list(by.values())), \
                mock.patch.object(picker, "filter_list", return_value=[False, False]) as fl:
            edit.toggle_games("t", rows)
        row_note = fl.call_args.kwargs["row_note"]
        a = [r[1] for r in rows].index("gba/A.zip")
        z = [r[1] for r in rows].index("gen/Zed.zip")
        self.assertEqual(row_note(a), "\u21b3 Variant: GB: x")
        self.assertEqual(row_note(z), "")

    def test_locked_rows_cannot_toggle(self):
        keys = iter(["tab", "ctrl+a", "escape", "y"])
        state = self.run_list(keys, locked=[True, False])
        self.assertEqual(state, [False, True])

    def test_multi_esc_keeps_state(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "y"])), [True, False])

    def test_multi_esc_without_changes_just_leaves(self):
        self.assertEqual(self.run_list(iter(["escape"])), [False, False])

    def test_multi_esc_can_revert(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "u"])), [False, False])

    def test_multi_esc_any_other_key_keeps_editing(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "z", "enter"])), [True, False])

    def test_ctrl_r_reverts_the_list(self):
        self.assertEqual(self.run_list(iter(["tab", "u", "enter"])), [False, False])

    def test_space_toggles_in_normal_mode_and_is_text_while_typing(self):
        self.assertEqual(self.run_list(iter(["space", "enter"])), [True, False])
        self.assertEqual(self.run_list(iter(["/", "y", "enter", "space", "enter"])), [False, True])
        self.assertEqual(self.run_list(iter(["/", "x", "space", "y", "enter", "escape", "space", "enter"])), [True, False])  # "x y" matches nothing; Esc clears it

    def test_view_cycle_shows_only_changed_rows(self):
        # toggle row 0, then ^O twice: "changed only" lists just it, and Tab then toggles that row back
        self.assertEqual(self.run_list(iter(["tab", "ctrl+o", "ctrl+o", "tab", "enter"])), [False, False])

    def test_hotkey_returns_pair(self):
        self.assertEqual(self.run_list(iter(["f"]), multi=False, hotkeys=("f",)), ("f", 0))
        self.assertEqual(self.run_list(iter(["j", "f"]), multi=False, hotkeys=("f",)), ("f", 1))

    def test_hotkey_ignored_without_rows(self):
        self.assertIsNone(self.run_list(iter(["/", "z", "enter", "f", "escape", "escape"]), multi=False, hotkeys=("f",)))

    def run_list(self, keys, locked=None, multi=True, hotkeys=()):
        return feed_list(keys, "t", ["x", "y"], multi=multi, locked=locked, hotkeys=hotkeys)


class VariantLine(unittest.TestCase):
    def test_variant_line_texts(self):
        variants = {"snes/CT.zip": [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"},
                                    {"bucket": "psx/CT.chd", "note": "PS1: anime scenes"}]}
        parents = {"nds/CT.zip": {"bucket": "snes/CT.zip", "system": "snes", "title": "Chrono Trigger"},
                   "psx/CT.chd": {"bucket": "snes/CT.zip", "system": "snes", "title": "Chrono Trigger"}}
        names = {"snes": "SNES", "nds": "Nintendo DS"}
        one = {"snes/CT.zip": variants["snes/CT.zip"][:1]}
        line = lambda key, v=variants, on=None: edit.variant_line(key, v, parents, names, on)  # noqa: E731
        self.assertEqual(line("snes/CT.zip", one), "↳ Variant: DS: adds the Lost Sanctum")
        self.assertEqual(line("snes/CT.zip", one, lambda b: False), "↳ Variant: DS: adds the Lost Sanctum (v adds it)")
        self.assertEqual(line("snes/CT.zip", one, lambda b: True),
                         "↳ Variant: DS: adds the Lost Sanctum · ✅ on the card (v removes it)")
        self.assertEqual(line("snes/CT.zip", on=lambda b: False),
                         "↳ 2 variants (v picks): DS: adds the Lost Sanctum; PS1: anime scenes")
        self.assertEqual(line("snes/CT.zip"), "↳ Variants: DS: adds the Lost Sanctum; PS1: anime scenes")
        self.assertEqual(line("nds/CT.zip"), "Variant of SNES — Chrono Trigger")
        self.assertEqual(line("gba/none.zip"), "")
        both = {"nds/CT.zip": [{"bucket": "x/Y.zip", "note": "n"}]}
        self.assertEqual(line("nds/CT.zip", both), "↳ Variant: n")


if __name__ == "__main__":
    unittest.main()


def run_list(keys, *args, **kwargs):
    return feed_list(keys, "t", *args, **kwargs)


class Keys(unittest.TestCase):
    LABELS = ["alpha", "beta", "gamma", "delta"]

    def test_vim_and_emacs_movement(self):
        self.assertEqual(run_list(["j", "j", "enter"], self.LABELS), 2)
        self.assertEqual(run_list(["ctrl+n", "ctrl+n", "ctrl+p", "enter"], self.LABELS), 1)
        self.assertEqual(run_list(["G", "k", "enter"], self.LABELS), 2)
        self.assertEqual(run_list(["G", "g", "enter"], self.LABELS), 0)

    def test_page_and_half_page_movement(self):
        labels = [f"row {i}" for i in range(50)]  # the list model shows 20 rows until a screen sizes it
        self.assertEqual(run_list(["ctrl+d", "enter"], labels), 10)
        self.assertEqual(run_list(["ctrl+f", "enter"], labels), 20)
        self.assertEqual(run_list(["ctrl+f", "ctrl+u", "enter"], labels), 10)
        self.assertEqual(run_list(["ctrl+f", "ctrl+f", "ctrl+b", "enter"], labels), 20)
        self.assertEqual(run_list(["ctrl+f", "ctrl+f", "ctrl+d", "enter"], labels), 49)  # stops on the last row
        self.assertEqual(run_list(["ctrl+d", "ctrl+b", "enter"], labels), 0)  # and on the first
        self.assertEqual(run_list(["ctrl+u", "enter"], labels), 0)
        self.assertEqual(run_list(["ctrl+d", "ctrl+d", "ctrl+u", "ctrl+f", "enter"], labels), 30)

    def test_a_hotkey_wins_over_a_movement_key(self):
        self.assertEqual(run_list(["j", "g"], self.LABELS, hotkeys=("g",)), ("g", 1))
        self.assertEqual(run_list(["ctrl+d"], self.LABELS, hotkeys=("ctrl+d",)), ("ctrl+d", 0))

    def test_letters_only_filter_after_slash(self):
        self.assertEqual(run_list(["b", "enter"], self.LABELS), 0)
        self.assertEqual(run_list(["/", "g", "a", "m", "enter", "enter"], self.LABELS), 2)

    def test_enter_while_typing_keeps_the_filter_in_a_single_list(self):
        self.assertEqual(run_list(["/", "t", "a", "ctrl+n", "enter", "enter"], self.LABELS), 3)  # beta, delta
        self.assertEqual(run_list(["/", "t", "a", "enter", "j", "enter"], self.LABELS), 3)  # j moves: no longer typing
        self.assertIsNone(run_list(["/", "x", "enter", "escape", "escape"], self.LABELS))  # nothing shown: Enter only stops typing

    def test_escape_while_typing_clears_the_filter(self):
        self.assertEqual(run_list(["/", "t", "a", "escape", "j", "enter"], self.LABELS), 1)

    def test_a_does_nothing_without_select_all(self):
        initial = [True, False, False, False]
        for key in ("a", "ctrl+a"):
            self.assertEqual(run_list([key, "enter"], self.LABELS, multi=True, initial=initial, select_all=False), initial)
        self.assertEqual(run_list(["a", "enter"], self.LABELS, multi=True, initial=initial), [True] * 4)

    def test_enter_while_typing_keeps_the_filter_in_a_multi_list(self):
        self.assertEqual(run_list(["/", "t", "a", "enter", "space", "enter"], self.LABELS, multi=True),
                         [False, True, False, False])

    def test_tab_while_typing_keeps_the_filter(self):
        self.assertEqual(run_list(["/", "t", "a", "tab", "j", "f"], self.LABELS, hotkeys=("f",)), ("f", 3))

    def test_tab_while_typing_keeps_the_filter_where_tab_is_a_hotkey(self):
        pressed = []

        def on_hotkey(key, i):
            pressed.append((key, i))
            return True
        # typing: Tab only keeps the filter; then Tab is the list's hotkey, on the filtered row
        self.assertIsNone(run_list(["/", "b", "tab", "tab", "escape", "escape"], self.LABELS, hotkeys=(" ", "\t"),
                                   on_hotkey=on_hotkey))
        self.assertEqual(pressed, [("\t", 1)])

    def test_esc_clears_filter_before_going_back(self):
        self.assertEqual(run_list(["/", "b", "tab", "escape", "enter"], self.LABELS), 0)
        self.assertIsNone(run_list(["/", "b", "tab", "escape", "escape"], self.LABELS))

    def test_session_keeps_the_filter_row_and_scroll(self):
        session = {}
        run_list(["/", "t", "a", "enter", "j", "space", "enter"], self.LABELS, multi=True, session=session)
        self.assertEqual((session["query"], session["row"], session["top"]), ("ta", 3, 0))
        self.assertEqual(run_list(["space", "enter"], self.LABELS, multi=True, session=dict(session)),
                         [False, False, False, False])  # starts filtered, on delta: space switches it back off
        labels = [f"row {n}" for n in range(60)]
        session = {"row": 40, "top": 30}
        self.assertEqual(run_list(["enter"], labels, session=session), 40)
        self.assertEqual(session["top"], 30)  # the row stays where it was on the screen

    def test_filter_line_editing(self):
        self.assertEqual(run_list(["/", "x", "y", "ctrl+u", "d", "e", "enter", "enter"], self.LABELS), 3)  # ^U clears
        self.assertEqual(run_list(["/", "g", "a", "space", "x", "ctrl+w", "ctrl+w", "d", "enter", "enter"], self.LABELS), 3)  # ^W kills words

    def test_line_key(self):
        self.assertEqual(picker.line_key("abc def", 7, "ctrl+w"), ("abc ", 4))
        self.assertEqual(picker.line_key("abc", 3, "ctrl+a"), ("abc", 0))
        self.assertEqual(picker.line_key("abc", 1, "ctrl+k"), ("a", 1))
        self.assertEqual(picker.line_key("abc", 1, "ctrl+d"), ("ac", 1))
        self.assertEqual(picker.line_key("ac", 1, "b"), ("abc", 2))
        self.assertIsNone(picker.line_key("ac", 1, "ctrl+n"))
        self.assertEqual(picker.line_key("abc", 3, "ctrl+h"), ("ab", 2))  # ^H under the kitty keyboard protocol

    def test_multi_toggle_all_none_and_hotkeys(self):
        self.assertEqual(run_list(["space", "j", "tab", "enter"], self.LABELS, multi=True), [True, True, False, False])
        self.assertEqual(run_list(["a", "a", "j", "space", "enter"], self.LABELS, multi=True), [False, True, False, False])
        self.assertEqual(run_list(["j", "f"], self.LABELS, hotkeys=("f",)), ("f", 1))

    def test_hidden_rows_until_e(self):
        got = run_list(["z", "G", "space", "enter"], self.LABELS, multi=True, hidden=[False, False, False, True])
        self.assertEqual(got, [False, False, False, True])
        self.assertEqual(run_list(["G", "space", "enter"], self.LABELS, multi=True, hidden=[False, False, False, True]),
                         [False, False, True, False])

    def test_space_and_tab_hotkeys_are_named_by_their_character(self):
        self.assertEqual(run_list(["space"], self.LABELS, hotkeys=(" ", "\t")), (" ", 0))
        self.assertEqual(run_list(["j", "tab"], self.LABELS, hotkeys=(" ", "\t")), ("\t", 1))

    def test_w_edits_the_rows_note(self):
        notes = []

        def on_note(i, text):
            notes.append((i, text))
            return "saved"
        keys = ["j", "w", "space", "x", "ctrl+a", "a", "enter", "w", "z", "escape", "enter"]
        self.assertEqual(run_list(keys, self.LABELS, multi=True, on_note=on_note, note_text=lambda i: "b"),
                         [False] * 4)
        self.assertEqual(notes, [(1, "ab x")])


class TextualList(unittest.TestCase):
    """filter_list on a headless Textual screen."""
    LABELS = ["alpha", "beta", "gamma"]

    def run_keys(self, keys, *args, **kwargs):
        async def script(pilot):
            await pilot.press(*keys)
        return pilot_list(script, "t", self.LABELS, *args, **kwargs)

    def test_single_mode_picks_the_highlighted_row(self):
        self.assertEqual(self.run_keys(["j", "enter"]), 1)

    def test_multi_mode_returns_the_states(self):
        self.assertEqual(self.run_keys(["space", "enter"], multi=True), [True, False, False])

    def test_textual_keeps_none_of_the_lists_keys(self):
        self.assertEqual(self.run_keys(["ctrl+n", "ctrl+n", "ctrl+p", "ctrl+q", "enter"]), 1)
        self.assertEqual(self.run_keys(["tab", "j", "tab", "enter"], multi=True), [True, True, False])

    def bottom_row(self, **kwargs):
        rows = []

        async def script(pilot):
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]))
            await pilot.press("j")
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]))
        pilot_list(script, "t", ["a", "b"], multi=True, **kwargs)
        return rows

    def test_row_note_shows_for_the_highlighted_row(self):
        before, after = self.bottom_row(row_note=lambda i: "↳ Variant: x" if i == 1 else "")
        self.assertNotIn("↳ Variant: x", before)
        self.assertIn("↳ Variant: x", after)

    def test_locked_note_wins_over_row_note(self):
        before, _ = self.bottom_row(locked=[True, False], locked_note="L", row_note=lambda i: "R")
        self.assertIn("🔒 L", before)
        self.assertNotIn("R", before.replace("🔒 L", ""))

    def test_preview_image_follows_the_cursor(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            paths = [os.path.join(tmp, f"{n}.png") for n in "ab"]
            for path in paths:
                Image.new("RGB", (45, 108), "red").save(path)
            seen = []

            async def script(pilot):
                seen.append(await shown_preview(pilot, paths[0]))
                await pilot.press("j")
                seen.append(await shown_preview(pilot, paths[1]))
                await pilot.press("j")
                await pilot.pause(0.1)
                seen.append(pilot.app.screen.query_one("#preview").image)
                await pilot.press("enter")
            # not a terminal: textual-image would probe the real one on import
            with mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                got = pilot_list(script, "t", self.LABELS, preview=lambda i: paths[i] if i < 2 else None)
        self.assertEqual((got, seen), (2, [paths[0], paths[1], None]))

    def test_preview_image_that_wont_load_shows_nothing(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.png")
            Image.new("RGB", (45, 108), "red").save(good)
            empty = os.path.join(tmp, "empty.png")
            open(empty, "wb").close()
            paths = [os.path.join(tmp, "missing.png"), good, empty]
            seen = []

            async def script(pilot):
                for i in range(3):
                    if i == 1:
                        await shown_preview(pilot, good)
                    else:
                        await pilot.pause(0.1)
                    image = pilot.app.screen.query_one("#preview").image
                    seen.append(image and image.filename)
                    await pilot.press("j")
                await pilot.press("enter")
            with mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                got = pilot_list(script, "t", self.LABELS, preview=lambda i: paths[i] if i < 3 else None)
        self.assertEqual((got, seen), (2, [None, good, None]))

    def test_no_preview_pane_without_terminal_graphics(self):
        panes = []

        async def script(pilot):
            panes.append(len(pilot.app.screen.query("#preview")))
            await pilot.press("enter")
        with mock.patch("sync_roms.picker._draws_images", return_value=False):
            got = pilot_list(script, "t", self.LABELS, preview=lambda i: "unused.png")
        self.assertEqual((got, panes), (0, [0]))

    def preview_layout(self, picture, size=(80, 24), resize_to=None, **kwargs):
        """Lay out a list previewing one picture of size picture (cells 10x20 px); returns per layout (before and
        after resize_to) the pane's (shown, region, class names), the image's pixel size and the list's width."""
        from PIL import Image
        from textual_image._terminal import CellSize
        seen = []

        async def look(pilot):
            await pilot.pause()
            pane = pilot.app.screen.query_one("#preview")
            seen.append((pane.display, tuple(pane.region) if pane.display else None, sorted(pane.classes),
                         pane.image.size, pilot.app.screen.query_one("_ListLines").region.width))

        async def script(pilot):
            await shown_preview(pilot)
            await look(pilot)
            if resize_to:
                await pilot.resize_terminal(*resize_to)
                await pilot.pause(0.05)
                await look(pilot)
            await pilot.press("enter")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", picture, "red").save(path)
            with mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True), \
                    mock.patch("textual_image._terminal.get_cell_size", return_value=CellSize(10, 20)):
                pilot_list(script, "t", self.LABELS, size=size, preview=lambda i: path, **kwargs)
        return seen

    def test_game_preview_is_300px_wide_in_its_own_column_at_the_top_right(self):
        [(shown, region, classes, pixels, list_width)] = self.preview_layout((600, 400), preview_width=300)
        self.assertEqual((shown, region, pixels, list_width), (True, (50, 0, 30, 10), (300, 200), 50))  # 300/10, 200/20
        self.assertIn("fixed", classes)

    def test_game_preview_shows_nothing_when_the_terminal_is_too_narrow_or_too_short(self):
        for picture, size in (((600, 400), (60, 24)),  # 30 cells leave the list fewer than MIN_LIST_WIDTH
                              ((300, 480), (80, 24))):  # 24 rows tall: no room above the status line
            [(shown, _, _, _, list_width)] = self.preview_layout(picture, size=size, preview_width=300)
            self.assertEqual((shown, list_width), (False, size[0]), (picture, size))

    def test_game_preview_column_comes_and_goes_as_the_terminal_resizes(self):
        before, after = self.preview_layout((600, 400), size=(60, 24), resize_to=(80, 24), preview_width=300)
        self.assertEqual((before[0], before[4]), (False, 60))
        self.assertEqual((after[0], after[1], after[4]), (True, (50, 0, 30, 10), 50))

    def test_other_previews_keep_the_auto_pane_beside_the_list(self):
        [(shown, region, classes, pixels, list_width)] = self.preview_layout((45, 108))
        self.assertEqual((shown, pixels, classes), (True, (45, 108), []))  # an 800 px cap doesn't grow it
        self.assertEqual(region[1:], (0, region[2], 24))  # the whole height
        self.assertEqual(region[0] + region[2], 80)
        self.assertEqual(list_width, region[0])
        pane_css = picker._app_class().CSS
        self.assertIn("_ListScreen #preview { width: auto; max-width: 34%; height: 100%; }", pane_css)

    def test_a_wide_preview_keeps_its_shape_when_the_pane_is_width_capped(self):
        [(shown, region, _, pixels, list_width)] = self.preview_layout((640, 480))
        # 34% of 80 is 27 cells (270 px); 270 x 202 px is 10 rows of 20 px, not the whole height
        self.assertEqual((shown, region, list_width), (True, (53, 0, 27, 10), 53))

    def test_block_fallbacks_dont_count_as_drawing_images(self):
        from sync_roms import picker
        with mock.patch.object(sys, "__stdout__", io.StringIO()), \
                mock.patch.dict(os.environ, {"TMUX": ""}):  # not a terminal: the import probes it
            from textual_image import renderable
            for kind, draws in ((renderable.HalfcellImage, False), (renderable.UnicodeImage, False),
                                (renderable.TGPImage, True), (renderable.SixelImage, True)):
                with mock.patch.object(renderable, "Image", kind):
                    self.assertEqual(picker._draws_images(), draws)

    def test_no_textual_image_probe_inside_tmux_without_an_answer(self):
        from sync_roms import picker
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-501/default,1,0"}), \
                mock.patch.object(picker, "_probe_through_tmux", return_value=False), \
                mock.patch.dict(sys.modules, {"textual_image.renderable": None}):  # importing it would fail
            self.assertFalse(picker._draws_images())

    def test_tmux_probe_keeps_the_outer_terminals_answer(self):
        import contextlib
        import types
        from sync_roms import picker
        from textual_image import _terminal as term
        if hasattr(term.probe_terminal, "_result"):
            saved = term.probe_terminal._result
            self.addCleanup(setattr, term.probe_terminal, "_result", saved)
        else:
            self.addCleanup(lambda: hasattr(term.probe_terminal, "_result") and delattr(term.probe_terminal, "_result"))
        # what Ghostty sent back through tmux: Kitty graphics OK, cell size, and its own device attributes (no Sixel)
        replies = "\x1b_Gi=31;OK\x1b\\\x1b[6;20;10t\x1b[?62;22;52c"

        @contextlib.contextmanager
        def capture(timeout):
            yield types.SimpleNamespace(sequence=replies)
        stdout = mock.MagicMock()
        stdout.isatty.return_value = True
        with mock.patch.object(sys, "__stdout__", stdout), mock.patch.object(term, "capture_until_primary_da", capture):
            self.assertTrue(picker._probe_through_tmux())
        self.assertEqual(term.probe_terminal(), term.TerminalCapabilities(term.CellSize(10, 20), sixel=False, tgp=True))
        written = stdout.write.call_args.args[0]
        self.assertNotIn("\x1b[c", written.replace("\x1b\x1b[c", ""))  # every query goes through tmux

    def test_tmux_probe_without_an_answer_means_no_images(self):
        from sync_roms import picker
        from textual_image import _terminal as term
        stdout = mock.MagicMock()
        stdout.isatty.return_value = True
        with mock.patch.object(sys, "__stdout__", stdout), \
                mock.patch.object(term, "capture_until_primary_da", side_effect=TimeoutError):
            self.assertFalse(picker._probe_through_tmux())

    def test_textual_failure_exits_instead_of_looking_like_esc(self):
        from sync_roms import picker

        def failing_run(app, **kwargs):
            app._return_code = 1  # what App.run does after printing a traceback
        with mock.patch.object(picker._app_class(), "run", failing_run):
            with self.assertRaises(SystemExit) as raised:
                picker._run(mock.Mock())
        self.assertEqual(raised.exception.code, 1)

    def test_ctrl_z_suspends_and_the_list_keeps_running(self):
        from sync_roms import picker
        with mock.patch.object(picker._app_class(), "action_suspend_process") as suspend:
            self.assertEqual(self.run_keys(["ctrl+z", "j", "enter"]), 1)
        suspend.assert_called_once_with()

    def test_ctrl_c_raises_keyboard_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_keys(["space", "ctrl+c"], multi=True)

    def test_help_scrolls_and_closes_on_esc_q_or_question_mark(self):
        from textual.containers import VerticalScroll
        seen = []

        async def script(pilot):
            for close in ("escape", "q", "?"):
                await pilot.press("?")
                scroll = pilot.app.screen.query_one(VerticalScroll)
                footer = pilot.app.screen.query_one("#help-footer")
                seen.append((footer.region.bottom <= 24, scroll.max_scroll_y > 0))
                await pilot.press("j", "end")
                seen.append((type(pilot.app.screen).__name__, scroll.scroll_y > 0))
                await pilot.press(close)
                seen.append(type(pilot.app.screen).__name__)
            await pilot.press("enter")
        hint = "Space toggle · Enter done · s set · m meta · p past · v variant"
        help_keys = [(k, f"the {k} key") for k in "smpcvxyz"]  # 26 lines of help on 24 rows
        self.assertEqual(pilot_list(script, "t", self.LABELS, multi=True, hint=hint, hotkeys=tuple("smpcvxyz"),
                                    key_help=help_keys, on_note=lambda i, t: "", hidden=[False, False, True]),
                         [False, False, False])  # the j only scrolled the help
        self.assertEqual(seen, [(True, True), ("_HelpScreen", True), "_ListScreen"] * 3)

    def test_help_lists_the_default_keys_a_caller_hint_hides_and_the_callers_keys(self):
        text = []

        async def script(pilot):
            await pilot.press("?")
            text.append(str(pilot.app.screen.query_one("#help-text").render()))
            await pilot.press("escape", "enter")
        pilot_list(script, "t", self.LABELS, multi=True, hint="Space toggle · Enter done · s set", hotkeys=("s",),
                   key_help=[("s", "narrow the list to a set's games")], on_note=lambda i, t: "")
        for line in ("a               toggle all shown (all off if all are on)", "o               view: all / on / changed",
                     "u               revert this list and hidden rows (asks if more than one change)",
                     "w               edit the row's note", "?               this help",
                     "s               narrow the list to a set's games"):
            self.assertIn(line, text[0])
        self.assertNotIn("Space toggle", text[0])  # the hint isn't repeated once the keys are described

    def test_a_key_the_caller_describes_has_one_line(self):
        lines = picker.help_lines(False, "", key_help=[("Enter", "the system's games")])
        self.assertEqual([l for l in lines if l.startswith("Enter")], ["Enter           the system's games"])
        lines = picker.help_lines(True, "", key_help=[("Space/Tab/Enter", "put it on the card or take it off")])
        self.assertEqual([l for l in lines if l.startswith(("Enter", "Space"))], ["Space/Tab/Enter put it on the card or take it off"])
        self.assertIn("Esc/q/^G        clear the filter, then go back", lines)
        self.assertIn("/               filter (Enter or Tab keeps it, Esc clears it)", lines)

    def test_without_key_help_the_help_lists_the_hint(self):
        self.assertIn("  d delete", picker.help_lines(False, "Enter open · d delete"))

    def test_the_hint_leaves_out_keys_every_list_has(self):
        lines = picker.help_lines(False, "/ filter · j/k move · Enter continue · d delete")
        self.assertEqual(lines[lines.index("This screen:") + 1:], ["  Enter continue", "  d delete"])

    def test_help_says_what_esc_asks_and_what_locked_rows_do(self):
        lines = picker.help_lines(True, "", esc_asks=True, has_locked=True)
        self.assertIn("Esc/q/^G        clear the filter, then go back (asks whether to keep changes)", lines)
        self.assertTrue(any(l.startswith("🔒") for l in lines))
        lines = picker.help_lines(True, "")
        self.assertIn("Esc/q/^G        clear the filter, then go back", lines)
        self.assertFalse(any(l.startswith("🔒") for l in lines))

    def test_every_hint_starts_with_help(self):
        hints = []

        async def script(pilot):
            hints.append(" ".join(t for t, _ in screen_lines(pilot.app)[2]))
            await pilot.press("escape")
        for kwargs in ({}, {"multi": True, "esc_asks": False}, {"hint": "Enter open · d delete"}):
            pilot_list(script, "t", self.LABELS, **kwargs)
        self.assertEqual(len(hints), 3)
        for hint in hints:
            self.assertTrue(hint.startswith("? help ·"), hint)  # the last part a narrow list cuts

    def test_status_shows_the_row_and_counts_after_a_callers_status(self):
        rows = []

        async def script(pilot):
            await pilot.press("/", "e", "ctrl+n")
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]))
            await pilot.press("escape", "escape")
        pilot_list(script, "t", self.LABELS + ["delta"], status=lambda _s: "💾 1 GB")
        pilot_list(script, "t", self.LABELS + ["delta"], status=lambda _s: "💾 " + "x" * 100)  # longer than the screen
        self.assertTrue(rows[0].startswith("💾 1 GB"), rows[0])
        self.assertTrue(rows[0].endswith("row 2 · 2/4 shown"), rows[0])  # beta, delta
        self.assertEqual(rows[1], "💾 " + "x" * 77)  # no room: the position gives way, the status is cut as before

    STATUS = "💾 123.4 GB / 512 GB · 812 files"

    def bottom_text(self, status, preview=None):
        from PIL import Image
        rows = []

        async def script(pilot):
            if preview:
                await shown_preview(pilot)
                await pilot.pause()  # laid out beside it
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]).strip())
            await pilot.press("escape")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (45, 108), "red").save(path)
            with mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                pilot_list(script, "t", self.LABELS, multi=True, esc_asks=False, status=lambda _s: status,
                           preview=(lambda i: path) if preview else None)
        return rows[0]

    def test_pending_counts_come_first_and_the_view_stays_ahead_of_the_position_at_80_columns(self):
        row = self.bottom_text(self.STATUS)
        self.assertTrue(row.startswith("+0 −0 · " + self.STATUS + " · view: all "), row)
        self.assertTrue(row.endswith(" row 1 · 3/3 shown"), row)

    def test_pending_counts_come_first_and_the_view_stays_ahead_of_the_position_beside_the_image_pane(self):
        status = "💾 1 GB used · 3 files"  # in the 60 columns the pane leaves, only the compact position fits beside it
        row = self.bottom_text(status, preview=True)
        self.assertTrue(row.startswith("+0 −0 · " + status + " · view: all "), row)
        self.assertTrue(row.endswith(" 1 · 3/3"), row)

    def test_status_counts_what_the_filter_shows(self):
        rows = []

        async def script(pilot):
            await pilot.press("/", "m", "m")
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]))
            await pilot.press("escape", "escape")
        pilot_list(script, "t", self.LABELS)
        self.assertEqual([r.strip() for r in rows], ["row 1 · 1/3 shown"])

    def test_typing_shows_the_cursor_in_the_filter(self):
        lines = []

        async def script(pilot):
            await pilot.press("/", "b", "e", "ctrl+b")
            lines.extend(screen_lines(pilot.app)[1])
            await pilot.press("enter", "enter")
        self.assertEqual(pilot_list(script, "t", self.LABELS), 1)
        self.assertIn(("e", "reverse default on default"), lines)

    def test_paste_goes_into_the_filter_and_is_ignored_otherwise(self):
        async def script(pilot):
            pilot.app.screen.post_message(events.Paste("q"))  # not typing: no keys pressed (q would go back)
            await pilot.press("/")
            pilot.app.screen.post_message(events.Paste("gam\nma"))
            await pilot.pause()
            await pilot.press("enter", "enter")
        self.assertEqual(pilot_list(script, "t", self.LABELS), 2)

    def test_a_callback_error_comes_out_of_filter_list(self):
        def on_hotkey(key, i):
            raise ValueError("boom")
        with self.assertRaisesRegex(ValueError, "boom"):
            self.run_keys(["f"], hotkeys=("f",), on_hotkey=on_hotkey)


class NarrowRows(unittest.TestCase):
    LONG = "Pocket Monsters - Super Long Adventure (Japan) (Rev 1) (Virtual Console) [T-En by Someone]"  # 90
    EXTRAS = [[("  📦 Shmups", "cyan"), ("  1.2 GB", "dim")], [("", "cyan"), ("  12 MB", "dim")]]

    def rendered(self, size=(80, 24), preview=False, **kwargs):
        """The list's lines as plain text (title, filter and hint first), and the list's width."""
        from PIL import Image
        out = []

        async def script(pilot):
            if preview:
                await shown_preview(pilot)
                await pilot.pause()  # laid out beside it
            out.extend(screen_text(pilot.app))
            out.append(pilot.app.screen_stack[0].query_one("_ListLines").size.width)
            await pilot.press("escape")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (45, 108), "red").save(path)
            with mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                pilot_list(script, "t", [self.LONG, "Short"], multi=True, esc_asks=False, extras=self.EXTRAS, size=size,
                           preview=(lambda i: path) if preview else None, **kwargs)
        return out[:-1], out[-1]

    def test_a_long_label_is_cut_with_an_ellipsis_and_the_extras_are_columns_after_it(self):
        for size, preview in (((80, 24), False), ((80, 24), True), ((100, 24), False)):
            lines, width = self.rendered(size, preview)
            long_row, short_row = lines[3], lines[4]
            self.assertLess(width, cell_len("⬜ " + self.LONG + "  📦 Shmups  1.2 GB"), (size, preview))  # too long for the row
            self.assertEqual(cell_len(long_row), width)
            self.assertTrue(long_row.startswith("⬜ Pocket Monsters"), long_row)
            self.assertTrue(long_row.endswith("…  📦 Shmups  1.2 GB"), long_row)  # the label gives way, the size stays last
            self.assertEqual(cell_len(short_row), width)
            self.assertTrue(short_row.startswith("⬜ Short "), short_row)
            self.assertEqual(cell_len(short_row[:short_row.index("12 MB")]), cell_len(long_row[:long_row.index("1.2 GB")]),
                             short_row)  # the sizes are one column, left-aligned

    def test_rows_are_a_left_aligned_table_when_the_labels_fit(self):
        lines, width = self.rendered((120, 24))
        self.assertEqual(width, 120)
        self.assertEqual(lines[3].rstrip(), "⬜ " + self.LONG + "  📦 Shmups  1.2 GB")
        self.assertEqual(lines[4].rstrip(), "⬜ Short" + " " * 85 + " " * 11 + "  12 MB")  # label column, empty set column

    def test_the_cut_counts_cells_and_never_splits_a_wide_character(self):
        from rich.text import Text
        label = "⬜ ポケットモンスター 金 (Japan) (Rev 1)"
        for width in range(28, 60):  # from 28 the label keeps its MIN_LABEL cells with the size beside it
            row = picker.fit_row(Text(label), Text("  1.2 GB"), width, label_width=width)  # a column as wide as it goes
            self.assertEqual(row.cell_len, width, width)
            self.assertTrue(row.plain.endswith("  1.2 GB"), row.plain)
            self.assertTrue(row.plain.startswith("⬜ ポケ"), row.plain)
            whole = label + " " * (width - cell_len(label) - 8) + "  1.2 GB"
            self.assertTrue(row.plain == whole or row.plain.split("  1.2 GB")[0].rstrip().endswith("…"), row.plain)

    def test_when_even_the_extras_do_not_fit_the_label_keeps_its_minimum_and_the_end_is_cut(self):
        from rich.text import Text
        row = picker.fit_row(Text("⬜ " + self.LONG), Text("  📦 A very long set name that takes the row  1.2 GB"), 40)
        self.assertEqual(row.cell_len, 40)
        self.assertTrue(row.plain.startswith("⬜ Pocket Monsters…"), row.plain)  # MIN_LABEL cells of the label
        self.assertTrue(row.plain.endswith("…"), row.plain)
        self.assertEqual(picker.fit_row(Text("⬜ ab"), Text("  " + "x" * 60), 30).plain, "⬜ ab  " + "x" * 22 + "…")

    def test_extras_keep_their_colors_and_the_highlight_spans_the_row(self):
        from rich.text import Text
        row = picker.fit_row(Text("⬜ " + self.LONG, "reverse"), Text("  1.2 GB", "reverse dim"), 40)
        self.assertEqual([(row.plain[s.start:s.end], str(s.style)) for s in row.spans][-1], ("  1.2 GB", "reverse dim"))
        self.assertTrue(all("reverse" in str(s.style) for s in row.spans) and row.style == "reverse")

    def test_filters_show_on_the_filter_line(self):
        lines, _ = self.rendered(filters="📦 Shmups only (c clear filters)")
        self.assertEqual(lines[0].rstrip(), "t")
        self.assertEqual(lines[1].rstrip(), "🔎   📦 Shmups only (c clear filters)")

    def test_a_restored_scroll_is_clamped_so_the_list_is_filled(self):
        seen = []
        session = {"sel": [True] * 25 + [False] * 5, "view_mode": 1, "row": 22, "top": 10}  # top 10 was for all 30 rows
        with mock.patch.object(picker, "_run", seen.append):
            picker.filter_list("t", [str(i) for i in range(30)], multi=True, session=session)
        m = seen[0]
        self.assertEqual((m.view, len(m.vis), m.vis[m.cur], m.top), (20, 25, 22, 5))  # rows 5..24: no blank rows


class TagColumn(DataDir):
    """toggle_games shows the tag emoji of every row and t edits the highlighted row's tags."""
    S = {"name": "NES", "bucket": "nes", "games": []}
    ROWS = [(S, "nes/A (USA).zip", "A", "A"), (S, "nes/B (USA).zip", "B", "B")]

    def setUp(self):
        super().setUp()
        from helpers import storage_tags
        from sync_roms import tags
        self.tags = tags
        storage_tags(self, {"tags": {"x": {"name": "X", "emoji": "🐝"}}, "games": {"nes/B (USA).zip": {"tags": ["x"]}},
                            "declined": {}})

    def test_rows_show_the_column_and_t_edits_then_reopens(self):
        seen, asked = [], []

        def fake(title, labels, **kw):
            seen.append(kw)
            return ("t", 1) if len(seen) == 1 else kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(edit.tagui, "edit_game_tags", side_effect=lambda *a: asked.append(a)):
            self.assertIsNone(edit.toggle_games("t", self.ROWS))
        self.assertEqual([e[-1] for e in seen[0]["extras"]], [("", ""), ("🐝", "")])
        self.assertIn("t", seen[0]["hotkeys"])
        self.assertIn("t tags", seen[0]["hint"])
        self.assertEqual(asked, [("nes/B (USA).zip", "B")])
        self.assertEqual(len(seen), 2)

    def test_t_bulk_tags_every_shown_row_and_only_where_the_filter_applies(self):
        tagui = edit.tagui
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)
        tagui.FILTER.required = {"x"}
        seen, bulk = [], []
        answers = iter([("T", None)])

        def fake(title, labels, **kw):
            seen.append(kw)
            return next(answers, None) or kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(tagui, "bulk_tag", side_effect=lambda keys: bulk.append(keys)):
            edit.toggle_games("t", self.ROWS)
            edit.toggle_games("t", self.ROWS, tag_filter=False)
        self.assertIn("T", seen[0]["hotkeys"])
        self.assertIn("T tag all shown", seen[0]["hint"])
        self.assertEqual(bulk, [["nes/B (USA).zip"]])  # the shown rows only
        self.assertEqual(len(seen), 3)  # reopened after the bulk tag
        self.assertNotIn("T", seen[2]["hotkeys"])
        self.assertNotIn("T tag", seen[2]["hint"])

    def test_when_filtered_turns_a_on_only_while_a_tag_filter_is_set(self):
        tagui = edit.tagui
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)
        seen = []
        answers = iter([("s", None), ("c", None)])

        def fake(title, labels, **kw):
            seen.append((kw["select_all"], "a all shown" in kw["hint"]))
            return next(answers, None) or kw["session"]["sel"]

        def pick(row_keys):
            tagui.FILTER.required = {"x"}
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(tagui.FILTER, "pick", pick):
            edit.toggle_games("t", self.ROWS, select_all=edit.WHEN_FILTERED)
        self.assertEqual(seen, [(False, False), (True, True), (False, False)])

    def test_toggle_games_hides_rows_the_filter_rejects(self):
        self.tags.change_game_tags("nes/A (USA).zip", add=["x"])
        tagui = edit.tagui
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)
        tagui.FILTER.required = {"x"}
        seen = []
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append((l, kw)) or kw["session"]["sel"]):
            edit.toggle_games("t", self.ROWS)
        self.assertEqual(seen[0][0], ["A", "B"])
        tagui.FILTER.required = {"x"}
        self.tags.change_game_tags("nes/A (USA).zip", remove=["x"])
        seen.clear()
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append((l, kw)) or kw["session"]["sel"]):
            edit.toggle_games("t", self.ROWS, filters="mine")
        self.assertEqual(seen[0][0], ["B"])
        self.assertIn("✅ 🐝 X · 1 of 2 shown (c clear filters)", seen[0][1]["filters"])
        self.assertIn("mine", seen[0][1]["filters"])
        self.assertIn("s", seen[0][1]["hotkeys"])
        self.assertIn("c", seen[0][1]["hotkeys"])

    def test_toggle_games_s_and_c_handled_inside(self):
        tagui = edit.tagui
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)
        calls, seen = [], []
        answers = iter([("s", 0), ("c", 0)])

        def fake(title, labels, **kw):
            seen.append(kw["session"])
            kw["session"]["query"] = "q"
            return next(answers, None) or kw["session"]["sel"]
        place = {}
        with mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(tagui, "handle_key", side_effect=lambda *a: calls.append(a) or True):
            self.assertIsNone(edit.toggle_games("t", self.ROWS, place=place))
        self.assertEqual([c[0] for c in calls], ["s", "c"])
        self.assertEqual(calls[0][1], ["nes/A (USA).zip", "nes/B (USA).zip"])
        self.assertIs(calls[0][2], place)
        self.assertEqual(len(seen), 3)

    def test_toggle_games_no_matches_shows_banner_and_message(self):
        tagui = edit.tagui
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)
        tagui.FILTER.required = {"x"}
        self.tags.change_game_tags("nes/B (USA).zip", remove=["x"])
        seen = []
        answers = iter([("c", None)])

        def fake(title, labels, **kw):
            seen.append((labels, kw["filters"]))
            return next(answers, None) or kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake):
            edit.toggle_games("t", self.ROWS)
        self.assertEqual(seen[0][0], [])
        self.assertIn("✅ 🐝 X · 0 of 2 shown (c clear filters)", seen[0][1])
        self.assertIn("no games match the tag filter", seen[0][1])
        self.assertEqual(seen[1], (["A", "B"], ""))

    def test_tag_filter_false_shows_every_row_without_s_c_or_banner(self):
        tagui = edit.tagui
        tagui.FILTER.required = {"x"}
        self.tags.change_game_tags("nes/B (USA).zip", remove=["x"])
        seen = []
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append((l, kw)) or kw["session"]["sel"]):
            edit.toggle_games("t", self.ROWS, tag_filter=False)
            edit.toggle_games("t", self.ROWS)
        self.assertEqual(seen[0][0], ["A", "B"])
        self.assertNotIn("s", seen[0][1]["hotkeys"])
        self.assertNotIn("c", seen[0][1]["hotkeys"])
        self.assertEqual(seen[0][1]["filters"], tagui.PAUSED)  # a filter is set: say it is paused here
        self.assertEqual(seen[1][0], [])
        self.assertIn("s filter by tag", seen[1][1]["hint"])  # default callers: s and c are in the hint ? lists

    def test_a_caller_with_key_help_still_gets_s_t_c_and_the_live_keys_in_the_hint(self):
        seen = []
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append(kw) or kw["session"]["sel"]):
            edit.toggle_games("t", self.ROWS, key_help=[("m", "meta")], hint="Space toggle · Enter done · m meta")
        self.assertEqual(seen[0]["hint"], "Space toggle · Enter done · s filter by tag · t edit tags · T tag all shown · c clear filters"
                                          " · / filter · w note · a all shown · m meta")

    def test_notes_off_drops_w(self):
        seen = []
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append(kw) or kw["session"]["sel"]):
            edit.toggle_games("t", self.ROWS, notes=False)
            edit.toggle_games("t", self.ROWS)
        self.assertIsNone(seen[0]["on_note"])
        self.assertNotIn("w note", seen[0]["hint"])
        self.assertIn("t tags", seen[0]["hint"])
        self.assertIsNotNone(seen[1]["on_note"])
        self.assertIn("w note", seen[1]["hint"])

    def test_other_keys_are_still_returned(self):
        with mock.patch.object(picker, "filter_list", return_value=("s", 0)):
            self.assertEqual(edit.toggle_games("t", self.ROWS, hotkeys=("s",)), "s")

    def test_unknown_key_row(self):
        self.tags.change_game_tags("nes/Gone.zip", add=["x"])
        rows = [(self.S, "nes/Gone.zip", "Gone", "Gone")]
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, l, **kw: seen.append(kw) or kw["session"]["sel"]):
            seen = []
            edit.toggle_games("t", rows)
        self.assertEqual(seen[0]["extras"][0][-1], ("🐝", ""))
