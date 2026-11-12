import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

from textual import events

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import DataDir  # noqa: E402,F401  (re-exported: other test modules still import it from here)
from helpers import feed_list, pilot_list, screen_lines  # noqa: E402
from sync_roms import edit, picker, runtime, s3, store, ui  # noqa: E402

SETS = {"s": {"id": "s", "name": "Mix", "games": [{"system": "gba", "bucket": "gba/A.zip", "files": ["gba/A2.zip"]}]}}


class Helpers(unittest.TestCase):
    def test_valid_card_name(self):
        for bad in ("", "  ", "a/b"):
            self.assertIsNotNone(edit.valid_card_name(bad, set()))
        self.assertIsNotNone(edit.valid_card_name("RG SP", {"RG SP"}))
        self.assertIsNone(edit.valid_card_name("RG SP", {"other"}))

    def test_dump_list_shapes(self):
        systems = [{"bucket": "gba", "full_system": True, "games": [{"bucket": "gba/A.zip"}]},
                   {"bucket": "ps2", "full_system": False, "games": [{"bucket": "ps2/B.iso"}]},
                   {"bucket": "nes", "full_system": False, "games": []}]
        self.assertEqual(store.dump_list(systems, ["s"]),
                         {"gba": {"full_system": True}, "ps2": [{"bucket": "ps2/B.iso"}], "sets": ["s"]})
        self.assertEqual(store.dump_list(systems[2:], []), {})

    def test_cover_notes(self):
        keys = edit.cover_notes(SETS, ["s"])
        self.assertEqual(keys["gba/A.zip"], "Full set: Mix")


class Saving(DataDir):
    def test_save_lists_writes_card(self):
        store.update_card("c", device="x", layout="esde")
        store.save_lists({"c": {"sets": ["s"]}})
        self.assertEqual(self.read("cards.json")["c"], {"device": "x", "layout": "esde", "games": {"sets": ["s"]}})
        self.assertFalse(os.path.exists(self.path("games.json")))


class EscPrompt(unittest.TestCase):
    def test_a_poll_tick_at_the_keep_or_revert_prompt_keeps_asking(self):
        polled = []
        self.assertEqual(feed_list(["tab", "escape", None, "enter"], "t", ["a", "b"], multi=True,
                                   poll=lambda: polled.append(1)), [True, False])
        self.assertEqual(polled, [])  # the prompt waits for its key


class EditBase(DataDir):
    """The edit_manifest() driver the flow tests build on; holds no tests, so subclasses don't rerun any."""

    def run_edit(self, picks, confirmed, name="newcard"):
        picks = iter(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch("builtins.input", return_value=name), \
                mock.patch.object(picker, "choose_setup", return_value=(None, "esde")), \
                mock.patch.object(ui, "confirm", return_value=confirmed), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s" if confirmed else "d"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()


class EditFlow(EditBase):
    def test_new_card_left_empty_and_declined_is_removed(self):
        # top menu: Cards; "New card" is option 0 with no cards; the card editor Esc; back; the top menu Esc to finish
        self.assertEqual(self.run_edit([0, 0, None, None, None], confirmed=False), 0)
        self.assertNotIn("newcard", self.read("cards.json"))

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

    def test_top_menu_entries_are_exactly_cards_sets_collections_and_device_systems(self):
        top = self.top_titles([None])[0][1]
        self.assertEqual(top, ["💳 Cards", "📦 Sets", "💖 Collections", "🧩 Device systems",
                               "✅ Done (review & save)", "🚪 Quit without saving"])

    def test_choosing_sets_calls_edit_sets_and_a_failure_returns_to_the_menu(self):
        from sync_roms import setedit
        with mock.patch.object(setedit, "edit_sets", side_effect=SystemExit(3)) as run:
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


class SetRefs(unittest.TestCase):
    def test_toggle_set_ref(self):
        self.assertEqual(edit.toggle_set_ref(["a"], "b"), ["a", "b"])
        self.assertEqual(edit.toggle_set_ref(["a", "b"], "a"), ["b"])


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

    def test_letters_only_filter_after_slash(self):
        self.assertEqual(run_list(["b", "enter"], self.LABELS), 0)
        self.assertEqual(run_list(["/", "g", "a", "m", "enter", "enter"], self.LABELS), 2)

    def test_esc_clears_filter_before_going_back(self):
        self.assertEqual(run_list(["/", "b", "enter", "escape", "enter"], self.LABELS), 0)
        self.assertIsNone(run_list(["/", "b", "enter", "escape", "escape"], self.LABELS))

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

    def test_ctrl_c_raises_keyboard_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_keys(["space", "ctrl+c"], multi=True)

    def test_help_closes_on_any_key(self):
        shown = []

        async def script(pilot):
            await pilot.press("?")
            shown.append(type(pilot.app.screen).__name__)
            await pilot.press("j")
            shown.append(type(pilot.app.screen).__name__)
            await pilot.press("enter")
        self.assertEqual(pilot_list(script, "t", self.LABELS), 0)  # the j only closed the help
        self.assertEqual(shown, ["_HelpScreen", "_ListScreen"])

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
