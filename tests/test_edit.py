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
from helpers import feed_list, pilot_list, screen_lines, screen_text  # noqa: E402
from sync_roms import edit, picker, runtime, s3, store, ui  # noqa: E402

SETS = {"s": {"id": "s", "name": "Mix", "games": [{"system": "gba", "bucket": "gba/A.zip", "files": ["gba/A2.zip"]}]}}


G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
NEW = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
H = "psvita/H [PCSE00001] [USA] [NoNpDRM].zip"


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

    def test_system_rows_hide_vita_extras_unless_listed(self):
        s = {"bucket": "psvita", "games": [{"bucket": DLC}]}
        self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [DLC, G])
        s["games"] = []
        self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [G])

    def test_system_rows_use_arcade_names(self):
        s = {"bucket": "fbneo", "games": []}
        row = edit.system_rows(s, {"fbneo/1941j.zip"})[0]
        self.assertEqual(row[2], "1941: Counter Attack (Japan)")
        self.assertIn("1941j.zip", row[3])

    def test_set_rows_keep_saved_title(self):
        s = {"bucket": "fbneo", "name": "FBNeo"}
        gs = {"games": [{"system": "fbneo", "bucket": "fbneo/1941j.zip", "title": "Mine"}]}
        rows = edit.set_rows(gs, {"fbneo": s}, lambda _s: {"fbneo/1941j.zip"})
        self.assertEqual(rows[0][2], "Mine")

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

    def test_enter_while_typing_picks_in_a_single_list(self):
        self.assertEqual(run_list(["/", "t", "a", "ctrl+n", "enter"], self.LABELS), 3)  # beta, delta
        self.assertIsNone(run_list(["/", "x", "enter", "escape", "escape"], self.LABELS))  # nothing shown: Enter only stops typing

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
                seen.append(pilot.app.screen.query_one("#preview").image)
                await pilot.press("j")
                seen.append(pilot.app.screen.query_one("#preview").image)
                await pilot.press("j")
                seen.append(pilot.app.screen.query_one("#preview").image)
                await pilot.press("enter")
            # not a terminal: textual-image would probe the real one on import
            with mock.patch.object(sys, "__stdout__", io.StringIO()), \
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
                for _ in range(3):
                    seen.append(pilot.app.screen.query_one("#preview").image)
                    await pilot.press("j")
                await pilot.press("enter")
            with mock.patch.object(sys, "__stdout__", io.StringIO()), \
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
        for line in ("a               toggle all shown", "o               view: all / on / changed",
                     "u               revert this list", "w               edit the row's note", "?               this help",
                     "s               narrow the list to a set's games"):
            self.assertIn(line, text[0])
        self.assertNotIn("Space toggle", text[0])  # the hint isn't repeated once the keys are described

    def test_without_key_help_the_help_lists_the_hint(self):
        self.assertIn("  d delete", picker.help_lines(False, "Enter open · d delete"))

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
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]).strip())
            await pilot.press("escape")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (45, 108), "red").save(path)
            with mock.patch.object(sys, "__stdout__", io.StringIO()), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                pilot_list(script, "t", self.LABELS, multi=True, esc_asks=False, status=lambda _s: status,
                           preview=(lambda i: path) if preview else None)
        return rows[0]

    def test_pending_counts_come_first_and_the_view_stays_ahead_of_the_position_at_80_columns(self):
        row = self.bottom_text(self.STATUS)
        self.assertTrue(row.startswith("+0 −0 · " + self.STATUS + " · view: all "), row)
        self.assertTrue(row.endswith(" row 1 · 3/3 shown"), row)

    def test_pending_counts_come_first_and_the_view_stays_ahead_of_the_position_beside_the_image_pane(self):
        status = "💾 1 GB used · 3 files"  # with pending and view, it fits the 60 columns the pane leaves
        self.assertEqual(self.bottom_text(status, preview=True), "+0 −0 · " + status + " · view: all")

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
    EXTRAS = [[("  📦 Shmups", "cyan"), ("  1.2 GB", "dim")], [("  12 MB", "dim")]]

    def rendered(self, size=(80, 24), preview=False, **kwargs):
        """The list's lines as plain text (title, filter and hint first), and the list's width."""
        from PIL import Image
        out = []

        async def script(pilot):
            out.extend(screen_text(pilot.app))
            out.append(pilot.app.screen_stack[0].query_one("_ListLines").size.width)
            await pilot.press("escape")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (45, 108), "red").save(path)
            with mock.patch.object(sys, "__stdout__", io.StringIO()), \
                    mock.patch("sync_roms.picker._draws_images", return_value=True):
                pilot_list(script, "t", [self.LONG, "Short"], multi=True, esc_asks=False, extras=self.EXTRAS, size=size,
                           preview=(lambda i: path) if preview else None, **kwargs)
        return out[:-1], out[-1]

    def test_a_long_label_is_cut_with_an_ellipsis_and_the_extras_end_at_the_right_edge(self):
        for size, preview in (((80, 24), False), ((80, 24), True), ((100, 24), False)):
            lines, width = self.rendered(size, preview)
            long_row, short_row = lines[3], lines[4]
            self.assertLess(width, cell_len("⬜ " + self.LONG + "  📦 Shmups  1.2 GB"), (size, preview))  # too long for the row
            self.assertEqual(cell_len(long_row), width)
            self.assertTrue(long_row.startswith("⬜ Pocket Monsters"), long_row)
            self.assertTrue(long_row.endswith("…  📦 Shmups  1.2 GB"), long_row)  # the label gives way, the size stays last
            self.assertEqual(cell_len(short_row), width)
            self.assertTrue(short_row.startswith("⬜ Short "), short_row)
            self.assertTrue(short_row.endswith(" 12 MB"), short_row)  # sizes line up on the right

    def test_a_label_that_fits_is_whole_and_padded_to_the_extras(self):
        lines, width = self.rendered((120, 24))
        self.assertEqual(width, 120)
        self.assertEqual(lines[3], "⬜ " + self.LONG + " " * 8 + "  📦 Shmups  1.2 GB")
        self.assertEqual(lines[4], "⬜ Short" + " " * 105 + "  12 MB")

    def test_the_cut_counts_cells_and_never_splits_a_wide_character(self):
        from rich.text import Text
        label = "⬜ ポケットモンスター 金 (Japan) (Rev 1)"
        for width in range(28, 60):  # from 28 the label keeps its MIN_LABEL cells with the size beside it
            row = picker.fit_row(Text(label), Text("  1.2 GB"), width)
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
        lines, _ = self.rendered(filters="📦 Shmups only (c shows all)")
        self.assertEqual(lines[0].rstrip(), "t")
        self.assertEqual(lines[1].rstrip(), "🔎   📦 Shmups only (c shows all)")

    def test_a_restored_scroll_is_clamped_so_the_list_is_filled(self):
        seen = []
        session = {"sel": [True] * 25 + [False] * 5, "view_mode": 1, "row": 22, "top": 10}  # top 10 was for all 30 rows
        with mock.patch.object(picker, "_run", seen.append):
            picker.filter_list("t", [str(i) for i in range(30)], multi=True, session=session)
        m = seen[0]
        self.assertEqual((m.view, len(m.vis), m.vis[m.cur], m.top), (20, 25, 22, 5))  # rows 5..24: no blank rows
