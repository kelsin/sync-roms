import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import DataDir  # noqa: E402,F401  (re-exported: other test modules still import it from here)
from sync_roms import edit, picker, runtime, s3, sizecache, store, ui  # noqa: E402

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
    def test_curses_error_at_the_keep_or_revert_prompt_keeps_editing(self):
        import curses

        class Screen:
            def __init__(self, keys):
                self.keys = iter(keys)

            def getmaxyx(self):
                return 24, 80

            def get_wch(self):
                k = next(self.keys)
                if isinstance(k, Exception):
                    raise k
                return k

            def __getattr__(self, name):
                return lambda *a, **k: None
        screen = Screen(["\t", "\x1b", curses.error("no input"), "\n"])
        with mock.patch.object(picker.ui, "require_terminal", create=True), \
                mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
                mock.patch.object(curses, "has_colors", return_value=False), \
                mock.patch.object(curses, "wrapper", side_effect=lambda f: f(screen)):
            self.assertEqual(picker.filter_list("t", ["a", "b"], multi=True), [True, False])


class EditBase(DataDir):
    """The edit_manifest() driver the flow tests build on; holds no tests, so subclasses don't rerun any."""

    def run_edit(self, picks, confirmed, name="newcard"):
        picks = iter(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch.object(sizecache, "refresh_async"), \
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
        self.assertEqual(self.run_edit([3], confirmed=True), 0)
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
                mock.patch.object(sizecache, "refresh_async"), \
                mock.patch("builtins.input", side_effect=lambda *a: next(inputs)), \
                mock.patch.object(ui, "confirm", return_value=confirm), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()

    def test_rename_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.RENAME_KEY, 0), None, 3])
        self.assertEqual(list(self.read("cards.json")), ["renamed"])

    def test_delete_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.DELETE_KEY, 0), None, 3])
        self.assertEqual(self.read("cards.json"), {})

    def test_declined_delete_keeps_the_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([0, (edit.DELETE_KEY, 0), None, 3], confirm=False)
        self.assertIn("c", self.read("cards.json"))

    def test_done_with_no_changes_saves_nothing(self):
        self.assertEqual(self.run_menu([3]), 0)
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
        self.run_menu([2, 0, None, 3], multi=lambda initial, labels: [x in base for x in ids])
        self.assertEqual(self.read("device-systems.json"), {})

    def test_opening_a_device_and_changing_nothing_is_not_an_edit(self):
        dev, base, ids = self.device_case()
        extra = next(x for x in ids if x not in base)
        self.write_json("device-systems.json", {dev["id"]: {"add": [extra]}})
        self.run_menu([2, 0, None, 3], multi=lambda initial, labels: list(initial))
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

    def test_top_menu_entries_are_exactly_cards_sets_and_device_systems(self):
        top = self.top_titles([None])[0][1]
        self.assertEqual(top, ["💳 Cards", "📦 Sets", "🧩 Device systems", "✅ Done (review & save)", "🚪 Quit without saving"])

    def test_choosing_sets_calls_edit_sets_and_a_failure_returns_to_the_menu(self):
        from sync_roms import setedit
        with mock.patch.object(setedit, "edit_sets", side_effect=SystemExit(3)) as run:
            self.assertEqual(self.run_menu([1, 3]), 0)
        run.assert_called_once()

    def test_choosing_device_systems_opens_the_device_list(self):
        seen = self.top_titles([2, None, 3])
        self.assertIn("recommended systems", seen[1][0])

    def test_choosing_a_card_calls_the_card_editor(self):
        from sync_roms import cardedit
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        with mock.patch.object(cardedit, "edit_card") as run:
            self.run_menu([0, 0, None, 3])
        self.assertEqual(run.call_args[0][0], "c")

    def test_unwritable_cards_json_refuses_to_edit(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{oops")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_menu([3])
        self.assertNotEqual(cm.exception.code, 0)


class SetRefs(unittest.TestCase):
    def test_toggle_set_ref(self):
        self.assertEqual(edit.toggle_set_ref(["a"], "b"), ["a", "b"])
        self.assertEqual(edit.toggle_set_ref(["a", "b"], "a"), ["b"])


if __name__ == "__main__":
    unittest.main()


class Screen:
    """A fake curses screen that feeds scripted keys."""
    def __init__(self, keys):
        self.keys = iter(keys)

    def getmaxyx(self):
        return 24, 80

    def get_wch(self):
        return next(self.keys)

    def __getattr__(self, name):
        return lambda *a, **k: None


def run_list(keys, *args, **kwargs):
    import curses
    with mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
            mock.patch.object(curses, "has_colors", return_value=False), \
            mock.patch.object(curses, "wrapper", side_effect=lambda f: f(Screen(keys))):
        return picker.filter_list("t", *args, **kwargs)


class Keys(unittest.TestCase):
    LABELS = ["alpha", "beta", "gamma", "delta"]

    def test_vim_and_emacs_movement(self):
        self.assertEqual(run_list(["j", "j", "\n"], self.LABELS), 2)
        self.assertEqual(run_list(["\x0e", "\x0e", "\x10", "\n"], self.LABELS), 1)
        self.assertEqual(run_list(["G", "k", "\n"], self.LABELS), 2)
        self.assertEqual(run_list(["G", "g", "\n"], self.LABELS), 0)

    def test_letters_only_filter_after_slash(self):
        self.assertEqual(run_list(["b", "\n"], self.LABELS), 0)
        self.assertEqual(run_list(["/", "g", "a", "m", "\n", "\n"], self.LABELS), 2)

    def test_esc_clears_filter_before_going_back(self):
        self.assertEqual(run_list(["/", "b", "\n", "\x1b", "\n"], self.LABELS), 0)
        self.assertIsNone(run_list(["/", "b", "\n", "\x1b", "\x1b"], self.LABELS))

    def test_filter_line_editing(self):
        self.assertEqual(run_list(["/", "x", "y", "\x15", "d", "e", "\n", "\n"], self.LABELS), 3)  # ^U clears
        self.assertEqual(run_list(["/", "g", "a", " ", "x", "\x17", "\x17", "d", "\n", "\n"], self.LABELS), 3)  # ^W kills words

    def test_line_key(self):
        self.assertEqual(picker.line_key("abc def", 7, "\x17"), ("abc ", 4))
        self.assertEqual(picker.line_key("abc", 3, "\x01"), ("abc", 0))
        self.assertEqual(picker.line_key("abc", 1, "\x0b"), ("a", 1))
        self.assertEqual(picker.line_key("abc", 1, "\x04"), ("ac", 1))
        self.assertEqual(picker.line_key("ac", 1, "b"), ("abc", 2))
        self.assertIsNone(picker.line_key("ac", 1, "\x0e"))

    def test_multi_toggle_all_none_and_hotkeys(self):
        self.assertEqual(run_list([" ", "j", "\t", "\n"], self.LABELS, multi=True), [True, True, False, False])
        self.assertEqual(run_list(["a", "a", "j", " ", "\n"], self.LABELS, multi=True), [False, True, False, False])
        self.assertEqual(run_list(["j", "f"], self.LABELS, hotkeys=("f",)), ("f", 1))

    def test_hidden_rows_until_e(self):
        got = run_list(["z", "G", " ", "\n"], self.LABELS, multi=True, hidden=[False, False, False, True])
        self.assertEqual(got, [False, False, False, True])
        self.assertEqual(run_list(["G", " ", "\n"], self.LABELS, multi=True, hidden=[False, False, False, True]),
                         [False, False, True, False])

    def test_pick_systems_returns_indexes_and_actions(self):
        rows = [("a", True, 1, 2), ("b", False, 0, 0), ("c", True, 1, 2)]
        import curses
        for keys, want in ((["j", " ", "\n"], [2]), (["j", "e"], ("games", 2)), (["D"], ("clear", None)), (["q"], None)):
            with mock.patch.object(picker.ui, "require_terminal"), mock.patch.object(curses, "curs_set"), \
                    mock.patch.object(curses, "use_default_colors"), mock.patch.object(curses, "has_colors", return_value=False), \
                    mock.patch.object(curses, "wrapper", side_effect=lambda f, k=keys: f(Screen(k))):
                self.assertEqual(picker.pick_systems(rows, editable=True), want)
