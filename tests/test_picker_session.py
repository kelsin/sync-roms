"""picker.one_app: an editor's lists and prompts share one Textual app (headless here), commands run outside it."""
import asyncio
import contextlib
import io
import os
import signal
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import picker, ui  # noqa: E402


async def wait_for(pilot, cond):
    for _ in range(500):
        if cond():
            return
        await pilot.pause(0.01)
    raise AssertionError("timed out")


def showing(app, title):
    """Whether app shows the list titled title."""
    return type(app.screen).__name__ == "_ListScreen" and app.model.title == title and not app.done


def prompting(app, question):
    """Whether app shows the prompt that starts with question."""
    return type(app.screen).__name__ == "_PromptScreen" and app.model.question.startswith(question) and not app.done


@ui.uses_terminal
def at_terminal(fn, *args, **kwargs):
    """fn run as a command that may ask (git, gh): on the main thread, on the normal screen, with the app suspended."""
    return fn(*args, **kwargs)


def working(app):
    """Whether app shows "Working..." (no list is up)."""
    return type(app.screen).__name__ == "_WorkingScreen"


def wait(event):
    """In an editor: a step that lasts until the test sets event."""
    if not event.wait(10):
        raise AssertionError("timed out")


class Session(unittest.TestCase):
    def setUp(self):
        self.runs = []  # one entry per App.run
        self.events = []
        self.while_suspended = None  # called with the app as it suspends
        self.while_resuming = None  # called with the app as it resumes
        self.as_app_starts = None  # called before the app has the terminal
        self.as_app_closes = None  # called with the app once it has closed, before the session notices
        self.now = 0.0  # the session's clock for Ctrl-C: it only moves when a test moves it
        for p in (mock.patch.object(ui, "has_terminal", return_value=True),
                  mock.patch.object(picker, "_draws_images", return_value=False),
                  mock.patch.object(picker, "_now", lambda: self.now),
                  # what a session that ended without its editor (a second Ctrl-C) leaves in place, put back after
                  mock.patch.object(picker, "_session", None), mock.patch.object(ui, "terminal_runner", None),
                  mock.patch.object(ui, "prompter", None),
                  mock.patch.object(sys, "stdout", sys.stdout), mock.patch.object(sys, "stderr", sys.stderr)):
            p.start()
            self.addCleanup(p.stop)

    def run_editor(self, editor, script):
        """Run editor through picker.one_app; each app it starts runs headless and is driven by script(app, pilot)."""
        def run(app, **_):
            self.runs.append(app)
            if self.as_app_starts:
                self.as_app_starts()

            async def drive():
                async with app.run_test(size=(80, 24)) as pilot:
                    await script(app, pilot)
                    await wait_for(pilot, lambda: not app.is_running)
            asyncio.run(drive())
            if self.as_app_closes:
                self.as_app_closes(app)
            self.events.append("app closed")

        @contextlib.contextmanager
        def suspend(app):
            self.events.append("suspend")
            capture = sys.stdout, sys.stderr  # Textual's print capture, which App.suspend puts back on the way out
            if self.while_suspended:
                self.while_suspended(app)
            yield
            sys.stdout, sys.stderr = capture
            if self.while_resuming:
                self.while_resuming(app)
            self.events.append("resume")
        cls = picker._app_class()
        with mock.patch.object(cls, "run", run), mock.patch.object(cls, "suspend", suspend):
            return picker.one_app(editor)()

    def test_two_lists_in_one_session_start_one_app(self):
        def editor():
            return picker.filter_list("A", ["a0", "a1"]), picker.filter_list("B", ["b0", "b1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("j", "enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), (1, 1))
        self.assertEqual(len(self.runs), 1)

    def test_between_lists_the_app_says_working(self):
        go = threading.Event()
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            go.wait(5)
            return picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: type(app.screen).__name__ == "_WorkingScreen")
            seen.append(str(app.screen.query_one("Static").render()))
            go.set()
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), 0)
        self.assertEqual(seen, ["Working..."])

    def test_a_command_suspends_the_app_and_runs_on_the_main_thread(self):
        main = threading.current_thread()

        def answer(prompt=""):
            self.events.append(("input", threading.current_thread() is main, out.getvalue()))
            return "y"

        def editor():
            picker.filter_list("A", ["a0"])
            print("before the prompt")
            yes = at_terminal(ui.confirm, "Go on?")
            return yes, picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input", answer):
            self.assertEqual(self.run_editor(editor, script), (True, 0))
        self.assertEqual(len(self.runs), 1)
        self.assertEqual(self.events, ["suspend", ("input", True, "before the prompt\n"), "resume", "app closed"])

    def test_commands_in_a_row_share_one_suspend(self):
        def answer(prompt=""):
            self.events.append(("input", out.getvalue()))
            return "x"

        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.ask, "Name: ")
            print("between")
            at_terminal(ui.ask, "Description: ")
            return picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input", answer):
            self.assertEqual(self.run_editor(editor, script), 0)
        self.assertEqual(self.events, ["suspend", ("input", ""), ("input", "between\n"), "resume", "app closed"])

    def test_output_printed_while_the_app_runs_comes_out_after_it_in_order(self):
        def editor():
            print("one")
            picker.filter_list("A", ["a0"])
            print("two")
            print("warned", file=sys.stderr)
            print("three")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.run_editor(editor, script)
        self.assertEqual(out.getvalue(), "one\ntwo\nwarned\nthree\n")

    def test_output_streams_answer_as_themselves_in_a_session_and_are_put_back_after_it(self):
        out = io.StringIO()
        out.fileno = lambda: 7
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.run_editor(lambda: (sys.stdout.fileno(), sys.stdout.isatty()), None), (7, False))
            self.assertIs(sys.stdout, out)

    def test_a_command_before_any_list_starts_no_app(self):
        main = threading.current_thread()
        threads = []

        def answer(prompt=""):
            threads.append(threading.current_thread() is main)
            return "n"

        with mock.patch("builtins.input", answer):
            self.assertFalse(self.run_editor(lambda: at_terminal(ui.confirm, "Go on?"), None))
        self.assertEqual((threads, self.runs), ([True], []))

    def test_a_prompt_before_any_list_starts_the_app_for_it(self):
        def editor():
            return ui.confirm("Go on?"), picker.filter_list("A", ["a0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: prompting(app, "Go on? [Y/n]"))
            await pilot.press("n")
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), (False, 0))
        self.assertEqual(self.events, ["app closed"])

    def test_prompts_are_answered_in_the_app(self):
        from textual import events

        def editor():
            picker.filter_list("A", ["a0"])
            return (ui.confirm("Go on?"), ui.confirm("Delete?", default=False), ui.confirm("Keep?"),
                    ui.confirm("Save?", default=False), ui.ask("Name: "), ui.ask("Again: "),
                    ui.choose("Save these?", "sed", "s", "save/edit/discard"), ui.choose("Again?", "sed", "s"))

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Go on? [Y/n] "))
            await pilot.press("x", "enter")  # other keys are ignored; Enter gives the default
            await wait_for(pilot, lambda: prompting(app, "Delete? [y/N] "))
            await pilot.press("Y")
            await wait_for(pilot, lambda: prompting(app, "Keep?"))
            await pilot.press("escape")
            await wait_for(pilot, lambda: prompting(app, "Save?"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Name: "))
            await pilot.press("a", "space", "c", "left", "b", "home")  # home scrolls the text above
            app.post_message(events.Paste("d\ne"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Again: "))
            await pilot.press("x", "escape")
            await wait_for(pilot, lambda: prompting(app, "Save these? [S/e/d] (save/edit/discard) "))
            await pilot.press("escape", "x", "e")
            await wait_for(pilot, lambda: prompting(app, "Again?"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), (True, True, False, False, "a bdec", "", "e", "s"))
        self.assertEqual(self.events, ["app closed"])

    def test_ctrl_c_in_a_prompt_raises_in_the_editor(self):
        def editor():
            picker.filter_list("A", ["a0"])
            try:
                ui.ask("Name: ")
            except KeyboardInterrupt:
                return "interrupted", picker.filter_list("B", ["b0", "b1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Name: "))
            await pilot.press("x", "ctrl+c")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), ("interrupted", 1))
        self.assertEqual(self.events, ["app closed"])

    def test_a_prompt_shows_what_was_printed_since_the_last_answer_instead_of_after_the_session(self):
        seen = []

        def editor():
            print("before A")
            picker.filter_list("A", ["a0"])
            print("before B")  # printed before the last answer: after the session, as before
            picker.filter_list("B", ["b0"])
            print("\x1b[33mchanges:\x1b[0m")
            for n in range(40):
                print(f"  line {n}")
            print("\r50%\r100%", file=sys.stderr)
            ui.confirm("Save?")
            print("after")

        async def script(app, pilot):
            for title in "AB":
                await wait_for(pilot, lambda: showing(app, title))
                await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Save?"))
            await pilot.pause()
            scroll = app.screen.query_one("VerticalScroll")
            seen.append(scroll.scroll_y == scroll.max_scroll_y > 0)  # scrolled to the end
            await pilot.press("home")
            seen.append(scroll.scroll_y)
            seen.append(app.screen.query_one("Static").render())
            await pilot.press("y")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.run_editor(editor, script)
        self.assertEqual(seen[:2], [True, 0])
        self.assertEqual(seen[2].plain, "\n".join(["changes:"] + [f"  line {n}" for n in range(40)] + ["100%"]))
        self.assertEqual(seen[2].spans[0].style.foreground.ansi, 3)  # the colours are kept: yellow
        self.assertEqual(out.getvalue(), "before A\nbefore B\nafter\n")

    def test_a_note_shows_on_the_next_list_and_is_cleared_by_a_key(self):
        from sync_roms import edit
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            edit.note(ui.yellow("ℹ️  Saved. "))
            edit.note("")
            edit.note("Done")
            ui.confirm("Go on?")  # notes wait for a list
            picker.filter_list("B", ["b0", "b1"])
            return picker.filter_list("C", ["c0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, "Go on?"))
            await pilot.press("y")
            await wait_for(pilot, lambda: showing(app, "B"))
            seen.append(app.model.line[:2])
            await pilot.press("j")
            seen.append(app.model.line[:2])
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "C"))
            seen.append(app.model.line[:2])
            await pilot.press("enter")
        with mock.patch("builtins.input") as asked:
            self.run_editor(editor, script)
        asked.assert_not_called()
        self.assertEqual(seen, [("ℹ️  Saved. · Done", "yellow"), ("", None), ("", None)])

    def test_a_kept_note_is_shown_and_also_printed_after_the_app_closed_once(self):
        for shown in (True, False):
            with self.subTest(shown=shown):
                seen = []

                def editor():
                    picker.queue_note("🎉 PR opened: url", keep=True)
                    picker.queue_note("👋 Done.")
                    if shown:
                        picker.filter_list("A", ["a0"])

                async def script(app, pilot):
                    await wait_for(pilot, lambda: showing(app, "A"))
                    seen.append(app.model.line[0])
                    await pilot.press("enter")
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.run_editor(editor, script if shown else None)
                self.assertEqual(seen, ["🎉 PR opened: url · 👋 Done."] if shown else [])
                self.assertEqual(out.getvalue(), "🎉 PR opened: url\n" if shown else "🎉 PR opened: url\n👋 Done.\n")

    def test_a_long_prompt_wraps_so_its_legend_and_answer_stay_in_view(self):
        from textual.geometry import Region
        question = "💾 Save these changes?"
        legend = "s save · e keep editing · d discard · l list every change"
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            print("changes")
            return ui.choose(question, "sedl", "s", legend), ui.ask("Name: ")

        async def script(app, pilot):
            def shown():
                line = app.screen.query_one("#lines")
                text = "".join(strip.text for strip in line.render_lines(Region(0, 0, line.size.width, line.size.height)))
                return line.region.bottom == 24 and " ".join(text.split())
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: prompting(app, question))
            await pilot.pause()
            seen.append(shown())
            await pilot.press("e")
            await wait_for(pilot, lambda: prompting(app, "Name: "))
            await pilot.press(*"x" * 90)
            await pilot.pause()
            seen.append(shown())
            await pilot.press("enter")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.run_editor(editor, script), ("e", "x" * 90))
        self.assertTrue(seen[0].endswith(f"[S/e/d/l] ({legend})"), seen[0])
        self.assertEqual(seen[1].replace(" ", ""), "Name:" + "x" * 90)  # the cursor's cell is a space

    def test_a_note_no_list_showed_is_printed_after_the_app_closed(self):
        from sync_roms import edit

        def editor():
            print("one")
            picker.filter_list("A", ["a0"])
            print("two")
            edit.note(ui.yellow("ℹ️  Saved."))

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input") as asked:
            self.run_editor(editor, script)
        asked.assert_not_called()
        self.assertEqual(out.getvalue(), "one\ntwo\n" + ui.yellow("ℹ️  Saved.") + "\n")

    def test_ctrl_c_in_a_list_reaches_the_editor_then_the_caller_after_the_app_closed(self):
        def editor():
            try:
                picker.filter_list("A", ["a0"])
            except KeyboardInterrupt:
                self.events.append("editor saw it")
                raise

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("ctrl+c")
        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["editor saw it", "app closed"])

    def test_ctrl_c_at_a_commands_prompt_raises_in_the_editor(self):
        def editor():
            picker.filter_list("A", ["a0"])
            try:
                at_terminal(ui.confirm, "Save?")
            except KeyboardInterrupt:
                return "second Ctrl-C"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_editor(editor, script), "second Ctrl-C")
        self.assertEqual(self.events, ["suspend", "resume", "app closed"])

    def test_an_error_in_the_editor_is_raised_after_the_app_closed(self):
        def editor():
            picker.filter_list("A", ["a0"])
            raise ValueError("boom")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with self.assertRaises(ValueError):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["app closed"])

    def test_an_error_in_a_list_callback_reaches_the_editor(self):
        def editor():
            try:
                picker.filter_list("A", ["a0"], hotkeys=("x",), on_hotkey=lambda k, i: 1 / 0)
            except ZeroDivisionError:
                return "caught"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("x")
        self.assertEqual(self.run_editor(editor, script), "caught")

    def test_an_editor_that_ends_at_a_command_closes_the_app(self):
        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.confirm, "Save?")
            print("saved")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input", return_value="y"):
            self.run_editor(editor, script)
        self.assertEqual(out.getvalue(), "saved\n")
        self.assertEqual(self.events, ["suspend", "resume", "app closed"])

    def test_ctrl_c_while_working_interrupts_the_next_list_once(self):
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:  # the editors' handlers save, ask or review; their own lists work
                return "interrupted", picker.filter_list("C", ["c0", "c1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            self.events.append(working(app))  # nothing ends at the key: the step goes on
            go.set()
            await wait_for(pilot, lambda: showing(app, "C"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), ("interrupted", 1))
        self.assertEqual(self.events, [True, "app closed"])

    def test_ctrl_c_while_working_interrupts_the_next_prompt_once(self):
        from sync_roms import setedit
        at_work, go = threading.Event(), threading.Event()

        def fake_run(cmd, **kwargs):
            self.events.append(cmd[0])
            return mock.Mock(returncode=0, stdout="ok\n", stderr="")

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                ui.confirm("Save?")
            except KeyboardInterrupt:
                setedit.run(["git", "push"])  # a command after it runs
                return "interrupted", ui.confirm("Really?")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            go.set()
            await wait_for(pilot, lambda: prompting(app, "Really?"))
            self.events.append("asked")
            await pilot.press("y")
        with mock.patch.object(setedit.subprocess, "run", fake_run):
            self.assertEqual(self.run_editor(editor, script), ("interrupted", True))
        self.assertEqual(self.events, ["suspend", "git", "resume", "asked", "app closed"])  # "Save?" was never asked

    def test_ctrl_c_while_working_interrupts_the_next_command(self):
        from sync_roms import setedit
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                setedit.run(["git", "push"])
            except KeyboardInterrupt:
                return "interrupted"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            go.set()
        with mock.patch.object(setedit.subprocess, "run") as ran:
            self.assertEqual(self.run_editor(editor, script), "interrupted")
        ran.assert_not_called()


    def test_a_ctrl_c_a_second_after_the_one_the_editor_got_interrupts_its_handlers_next_list(self):
        at_work, go = [threading.Event(), threading.Event()], [threading.Event(), threading.Event()]
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            hits = 0
            for step in range(2):  # the second step is the first Ctrl-C's handler, still working
                at_work[step].set()
                wait(go[step])
                try:
                    picker.filter_list("B", ["b0"])
                except KeyboardInterrupt:
                    hits += 1
            return hits

        async def script(app, pilot):
            stopping = lambda: str(app.screen_stack[0].query_one("#stopping").render())
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work[0].is_set)
            await pilot.press("ctrl+c")
            go[0].set()
            await wait_for(pilot, at_work[1].is_set)
            await pilot.press("ctrl+c")  # less than a second after the one the handler is for: the same press
            seen.append(stopping())
            self.now += 1
            await pilot.press("ctrl+c")
            seen.append(stopping())
            go[1].set()
        self.assertEqual(self.run_editor(editor, script), 2)
        self.assertEqual(seen, ["", picker.STOPPING])

    def test_a_ctrl_c_right_behind_the_one_that_ended_a_list_is_the_same_press(self):
        from textual import events
        for later, outcome, questions in ((0, ("asked", True), ["Save? [Y/n] "]), (1, "the question was interrupted", [])):
            with self.subTest(later=later):
                handling, go = threading.Event(), threading.Event()

                def editor():
                    try:
                        picker.filter_list("A", ["a0"])
                    except KeyboardInterrupt:  # as the collections editor: its handler asks whether to save
                        handling.set()
                        wait(go)  # the handler's own work before its question
                        try:
                            return "asked", ui.confirm("Save?")
                        except KeyboardInterrupt:
                            return "the question was interrupted"

                async def script(app, pilot):
                    await wait_for(pilot, lambda: showing(app, "A"))
                    app.post_message(events.Key("ctrl+c", "\x03"))
                    await wait_for(pilot, handling.is_set)
                    self.now += later
                    app.post_message(events.Key("ctrl+c", "\x03"))
                    await pilot.pause()
                    go.set()
                    if questions:
                        await wait_for(pilot, lambda: prompting(app, questions[0]))
                        await pilot.press("y")
                self.assertEqual(self.run_editor(editor, script), outcome)

    def test_the_same_press_second_ends_at_the_editors_next_request(self):
        from textual import events
        at_work, go = threading.Event(), threading.Event()

        def editor():
            try:
                picker.filter_list("A", ["a0"])
            except KeyboardInterrupt:
                picker.filter_list("C", ["c0"])  # the handler's own list: its next request
                at_work.set()
                wait(go)
                try:
                    picker.filter_list("D", ["d0"])
                except KeyboardInterrupt:
                    return "interrupted again"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            app.post_message(events.Key("ctrl+c", "\x03"))
            await wait_for(pilot, lambda: showing(app, "C"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")  # the clock has not moved, but the editor has asked for a list since
            go.set()
        self.assertEqual(self.run_editor(editor, script), "interrupted again")

    def test_a_ctrl_c_kept_while_a_list_was_up_counts_from_the_end_of_that_list(self):
        from textual import events
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                return "handler ran"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            app.session.interrupt()  # the SIGINT handler's call (kill -INT) while list A is up
            self.now += 5  # the list stays up for 5 s
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            self.events.append(str(app.screen_stack[0].query_one("#stopping").render()))
            app.post_message(events.Key("ctrl+c", "\x03"))  # the first Ctrl-C typed on this step: not the one that quits
            await pilot.pause()
            self.events.append(app.is_running and not app.session.abandoned)
            go.set()
        try:
            got = self.run_editor(editor, script)
        except KeyboardInterrupt:
            got = "the editor was abandoned"
        go.set()
        self.assertEqual((got, self.events), ("handler ran", [picker.STOPPING, True, "app closed"]))

    def test_the_working_screen_says_what_ctrl_c_does_until_the_editor_gets_it(self):
        at_work, go, handling, handled = (threading.Event() for _ in range(4))
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            print("📡 Listing gba ...")
            at_work.set()
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                handling.set()
                wait(handled)

        async def script(app, pilot):
            lines = lambda: [str(app.screen_stack[0].query_one(line).render()) for line in ("#last", "#stopping")]
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: at_work.is_set() and lines()[0])
            seen.append(lines())
            await pilot.press("ctrl+c")
            seen.append(lines())
            self.now += 1  # from now on another Ctrl-C quits, and the screen says so
            app.call_later(app.stopping)
            await wait_for(pilot, lambda: picker.QUIT_NOW in lines()[1])
            seen.append(lines())
            go.set()
            await wait_for(pilot, handling.is_set)
            await wait_for(pilot, lambda: not lines()[1])
            seen.append(lines())
            handled.set()
        with contextlib.redirect_stdout(io.StringIO()):
            self.run_editor(editor, script)
        self.assertEqual(seen, [["📡 Listing gba ...", ""], ["📡 Listing gba ...", picker.STOPPING],
                                ["📡 Listing gba ...", picker.STOPPING + "\n" + picker.QUIT_NOW], ["📡 Listing gba ...", ""]])
        self.assertIn("stopping when this step ends", picker.STOPPING)
        self.assertIn("Ctrl-C again to quit now", picker.QUIT_NOW)

    def test_two_ctrl_c_in_one_write_while_working_interrupt_once_and_the_handler_saves(self):
        from textual import events
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:  # as the card editor does: it saves the toggles of the list that was open
                self.events.append("handler saved")
                return picker.filter_list("C", ["c0", "c1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            app.post_message(events.Key("ctrl+c", "\x03"))
            app.post_message(events.Key("ctrl+c", "\x03"))
            await pilot.pause()
            self.events.append(app.is_running and working(app))
            go.set()
            await wait_for(pilot, lambda: showing(app, "C"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), 1)
        self.assertEqual(self.events, [True, "handler saved", "app closed"])

    def test_a_held_ctrl_c_while_working_does_not_quit(self):
        from textual import events
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                return "interrupted", picker.filter_list("C", ["c0", "c1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            for _ in range(18):  # the key repeats every 30 ms for half a second
                app.post_message(events.Key("ctrl+c", "\x03"))
                await pilot.pause()
                self.now += 0.03
            self.events.append(app.is_running and working(app))
            go.set()
            await wait_for(pilot, lambda: showing(app, "C"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), ("interrupted", 1))
        self.assertEqual(self.events, [True, "app closed"])

    def test_an_editor_that_ends_after_a_ctrl_c_while_working_ends_interrupted(self):
        at_work, go = threading.Event(), threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            at_work.set()
            wait(go)
            self.events.append("editor done")  # what it saved stays saved
            return "done"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            go.set()
        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["editor done", "app closed"])

    def test_a_ctrl_c_read_as_the_app_closes_ends_the_command_interrupted(self):
        from textual import events
        # typed during the editor's last step, read by the app's input only as it stops: too late for the app itself
        self.as_app_closes = lambda app: app.post_message(events.Key("ctrl+c", "\x03"))

        def editor():
            picker.filter_list("A", ["a0"])
            self.events.append("editor done")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["editor done", "app closed"])

    def test_a_second_ctrl_c_a_second_later_while_working_ends_the_session_without_the_editor(self):
        from textual import events
        at_work, go = threading.Event(), threading.Event()
        threads = []
        handler = signal.getsignal(signal.SIGINT)

        def editor():
            picker.filter_list("A", ["a0"])
            threads.append(threading.current_thread())
            at_work.set()
            wait(go)  # a step that does not end (a stalled share)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            self.now = 0.99
            await pilot.press("ctrl+c")  # within a second of the first: the same gesture
            self.events.append(app.is_running)
            self.now = 1.0
            app.post_message(events.Key("ctrl+c", "\x03"))
        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, [True, "app closed"])
        self.assertTrue(threads[0].is_alive())  # still in its step
        self.assertIs(signal.getsignal(signal.SIGINT), handler)
        go.set()
        threads[0].join(10)
        self.assertFalse(threads[0].is_alive())

    def test_an_abandoned_editor_gets_ctrl_c_from_every_call_and_prints_nothing(self):
        from textual import events
        from sync_roms import edit, setedit
        at_work, go = threading.Event(), threading.Event()
        threads, got = [], []

        def editor():
            picker.filter_list("A", ["a0"])
            print("before")
            threads.append(threading.current_thread())
            at_work.set()
            wait(go)
            print("after")
            print("warned", file=sys.stderr)
            for call in (lambda: picker.filter_list("B", ["b0"]), lambda: ui.confirm("Save?"), lambda: edit.note("ℹ️  Saved."),
                         lambda: setedit.run(["git", "push"]), lambda: picker.one_app(lambda: picker.filter_list("C", ["c0"]))()):
                try:
                    got.append(call())
                except KeyboardInterrupt:
                    got.append("interrupted")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, at_work.is_set)
            await pilot.press("ctrl+c")
            self.now += 1
            app.post_message(events.Key("ctrl+c", "\x03"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), mock.patch("builtins.input") as asked, \
                mock.patch.object(setedit.subprocess, "run") as ran:
            with self.assertRaises(KeyboardInterrupt):
                self.run_editor(editor, script)
            go.set()
            threads[0].join(10)
            print("the command goes on")  # only the editor's thread is silenced
        self.assertFalse(threads[0].is_alive())
        self.assertEqual(got, ["interrupted", "interrupted", None, "interrupted", "interrupted"])  # the note is queued
        self.assertEqual(out.getvalue(), "before\nthe command goes on\n")
        self.assertEqual((asked.call_count, ran.call_count, len(self.runs)), (0, 0, 1))

    def test_two_ctrl_c_at_once_end_the_list_once(self):
        from textual import events

        def editor():
            try:
                picker.filter_list("A", ["a0"])
            except KeyboardInterrupt:
                return ui.confirm("Save?")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            app.post_message(events.Key("ctrl+c", "\x03"))
            app.post_message(events.Key("ctrl+c", "\x03"))
            await wait_for(pilot, lambda: prompting(app, "Save?"))
            await pilot.press("y")
        self.assertIs(self.run_editor(editor, script), True)
        self.assertEqual(self.events, ["app closed"])

    def test_keys_behind_the_one_that_ended_a_list_reach_nothing_but_ctrl_c(self):
        from textual import events
        for key in ("enter", "escape", "x", "ctrl+c"):
            with self.subTest(key=key):
                self.events = []

                def editor():
                    try:
                        picker.filter_list("A", ["a0"], hotkeys=("x",))
                    except KeyboardInterrupt:
                        return "interrupted"  # as without a session: a Ctrl-C right behind Enter turns the pick into it
                    return picker.filter_list("B", ["b0", "b1"])

                async def script(app, pilot):
                    await wait_for(pilot, lambda: showing(app, "A"))
                    app.post_message(events.Key("enter", "\r"))
                    app.post_message(events.Key(key, None))
                    if key == "ctrl+c":
                        return
                    await wait_for(pilot, lambda: showing(app, "B"))
                    await pilot.pause(0.1)
                    self.assertTrue(showing(app, "B"))
                    await pilot.press("j", "enter")
                self.assertEqual(self.run_editor(editor, script), "interrupted" if key == "ctrl+c" else 1)

    def test_keys_typed_while_working_reach_the_next_list_in_order(self):
        go = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            wait(go)
            return picker.filter_list("B", ["b0", "b1"], multi=True)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: working(app))
            await pilot.press("j", "space", "enter")
            go.set()
        self.assertEqual(self.run_editor(editor, script), [False, True])

    def test_keys_typed_while_working_before_a_prompt_are_dropped(self):
        go = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            wait(go)
            return ui.confirm("Go on?"), picker.filter_list("B", ["b0", "b1"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: working(app))
            await pilot.press("n", "j", "enter")
            go.set()
            await wait_for(pilot, lambda: prompting(app, "Go on?"))
            await pilot.pause(0.1)
            self.assertTrue(prompting(app, "Go on?"))
            await pilot.press("y")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.pause(0.1)
            self.assertTrue(showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), (True, 0))

    def test_ctrl_c_just_after_a_command_interrupts_the_next_list_at_once(self):
        def answer(prompt=""):
            picker._session.interrupt()  # the SIGINT handler's call for a Ctrl-C just after the answer
            return "n"

        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.confirm, "Delete?", default=False)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                return "interrupted"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", answer):
            self.assertEqual(self.run_editor(editor, script), "interrupted")

    def test_a_ctrl_c_as_the_app_starts_interrupts_its_first_list(self):
        self.as_app_starts = lambda: picker._session.interrupt()  # the SIGINT handler's call: the terminal is not the app's yet
        at_work, go = threading.Event(), threading.Event()

        def editor():
            try:
                picker.filter_list("A", ["a0"])
            except KeyboardInterrupt:
                at_work.set()
                wait(go)  # its handler works: a Ctrl-C on "Working..." counts as after any other list
                try:
                    picker.filter_list("B", ["b0"])
                except KeyboardInterrupt:
                    return "twice"

        async def script(app, pilot):
            await wait_for(pilot, at_work.is_set)
            self.now += 1  # sooner, it would be the same press as the one its handler is for
            await pilot.press("ctrl+c")
            self.events.append(str(app.screen_stack[0].query_one("#stopping").render()) == picker.STOPPING)
            go.set()
        self.assertEqual(self.run_editor(editor, script), "twice")
        self.assertEqual(self.events, [True, "app closed"])

    def test_ctrl_c_on_working_drops_the_keys_typed_ahead(self):
        go = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            wait(go)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:  # an editor that goes on to a list after the interrupt
                pass
            return picker.filter_list("C", ["c0", "c1"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: working(app))
            await pilot.press("j", "enter", "ctrl+c")
            go.set()
            await wait_for(pilot, lambda: showing(app, "C"))
            await pilot.pause(0.1)
            self.assertTrue(showing(app, "C"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), 0)

    def test_a_replayed_key_that_opens_help_drops_the_rest(self):
        go = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            wait(go)
            return picker.filter_list("B", ["b0", "b1"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: working(app))
            await pilot.press("question_mark", "j", "j", "enter")
            go.set()
            await wait_for(pilot, lambda: type(app.screen).__name__ == "_HelpScreen")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), 0)

    def test_a_ctrl_c_as_the_app_resumes_interrupts_the_next_list(self):
        self.while_resuming = lambda app: app.session.interrupt()  # SIGINT as the app comes back, after the prompts

        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.confirm, "Delete?", default=False)
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                return "interrupted"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", return_value="n"):
            self.assertEqual(self.run_editor(editor, script), "interrupted")

    def test_keys_typed_while_the_app_suspends_are_dropped(self):
        from textual import events
        for key in ("enter", "ctrl+c"):
            with self.subTest(key=key):
                self.events = []
                self.while_suspended = lambda app: app.post_message(events.Key(key, None))  # read as the input stops

                def editor():
                    picker.filter_list("A", ["a0"])
                    at_terminal(ui.confirm, "Delete?", default=False)
                    return picker.filter_list("B", ["b0", "b1"])

                async def script(app, pilot):
                    await wait_for(pilot, lambda: showing(app, "A"))
                    await pilot.press("enter")
                    await wait_for(pilot, lambda: showing(app, "B"))
                    await pilot.pause(0.1)
                    self.assertTrue(showing(app, "B"))
                    await pilot.press("j", "enter")
                with mock.patch("builtins.input", return_value="n"):
                    self.assertEqual(self.run_editor(editor, script), 1)

    def test_output_around_commands_and_later_lists_stays_in_order(self):
        def editor():
            print("one")
            picker.filter_list("A", ["a0"])
            print("two")
            at_terminal(ui.confirm, "Go on?")
            print("three")
            picker.filter_list("B", ["b0"])
            print("four", file=sys.stderr)
            picker.filter_list("C", ["c0"])
            print("five")

        async def script(app, pilot):
            for title in "ABC":
                await wait_for(pilot, lambda: showing(app, title))
                await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), mock.patch("builtins.input", return_value="y"):
            self.run_editor(editor, script)
        self.assertEqual(out.getvalue(), "one\ntwo\nthree\nfour\nfive\n")

    def test_the_terminal_is_probed_for_images_only_for_a_list_with_a_preview(self):
        probed = mock.Mock(side_effect=lambda: self.events.append("probe") or False)

        def editor():
            picker.filter_list("A", ["a0"])
            picker.filter_list("B", ["b0"], preview=lambda i: None)
            return picker.filter_list("C", ["c0"], preview=lambda i: None)

        async def script(app, pilot):
            for title in "ABC":
                await wait_for(pilot, lambda: showing(app, title))
                await pilot.press("enter")
        with mock.patch.object(picker, "_draws_images", probed):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["suspend", "probe", "resume", "app closed"])
        self.events = []
        with mock.patch.object(picker, "_draws_images", probed):
            self.run_editor(lambda: picker.filter_list("A", ["a0"]), lambda app, pilot: pilot.press("enter"))
        self.assertEqual(self.events, ["app closed"])

    def test_a_preview_that_comes_after_its_list_ended_is_dropped(self):
        import tempfile
        from PIL import Image
        started, gate, returned = threading.Event(), threading.Event(), threading.Event()
        seen = []

        def preview(i):
            started.set()
            wait(gate)
            returned.set()
            return path

        def editor():
            picker.filter_list("A", ["a0"], preview=preview)
            return picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await wait_for(pilot, started.is_set)
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            gate.set()
            await wait_for(pilot, returned.is_set)
            await pilot.pause(0.1)
            seen.append(app.error)
            await pilot.press("enter")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (45, 108), "red").save(path)
            with mock.patch.object(picker, "_draws_images", return_value=True), \
                    mock.patch.object(sys, "__stdout__", io.StringIO()), mock.patch.object(picker, "PREVIEW_IDLE_MS", 1):
                self.assertEqual(self.run_editor(editor, script), 0)
        self.assertEqual(seen, [None])

    def test_a_ctrl_c_as_the_app_comes_back_from_asking_about_images_interrupts_that_list(self):
        self.while_resuming = lambda app: app.session.interrupt()  # SIGINT as the app resumes after the probe

        def editor():
            picker.filter_list("A", ["a0"])
            try:
                picker.filter_list("B", ["b0"], preview=lambda i: None)
            except KeyboardInterrupt:
                return "interrupted"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), "interrupted")
        self.assertEqual(self.events, ["suspend", "resume", "app closed"])

    def test_sigint_at_a_commands_prompt_raises_in_it(self):
        handler = signal.getsignal(signal.SIGINT)

        def answer(prompt=""):
            signal.raise_signal(signal.SIGINT)
            return "y"

        def editor():
            picker.filter_list("A", ["a0"])
            try:
                at_terminal(ui.confirm, "Save?")
            except KeyboardInterrupt:
                return "interrupted"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", answer):
            self.assertEqual(self.run_editor(editor, script), "interrupted")
        self.assertIs(signal.getsignal(signal.SIGINT), handler)

    def test_a_sigint_while_the_editor_works_counts_as_the_key(self):
        for presses, outcome in ((1, "interrupted"), (2, KeyboardInterrupt)):
            with self.subTest(presses=presses):
                self.events = []
                at_work, go = threading.Event(), threading.Event()
                threads = []

                def editor():
                    picker.filter_list("A", ["a0"])
                    threads.append(threading.current_thread())
                    at_work.set()
                    wait(go)
                    try:
                        picker.filter_list("B", ["b0"])
                    except KeyboardInterrupt:
                        return "interrupted"

                async def script(app, pilot):
                    await wait_for(pilot, lambda: showing(app, "A"))
                    await pilot.press("enter")
                    await wait_for(pilot, at_work.is_set)
                    signal.raise_signal(signal.SIGINT)  # `kill -INT` from outside: the handler runs inside the app's loop
                    await wait_for(pilot, lambda: str(app.screen_stack[0].query_one("#stopping").render()) == picker.STOPPING)
                    if presses == 1:
                        go.set()
                    else:
                        self.now += 1
                        signal.raise_signal(signal.SIGINT)
                if outcome == "interrupted":
                    self.assertEqual(self.run_editor(editor, script), outcome)
                else:
                    with self.assertRaises(outcome):
                        self.run_editor(editor, script)
                    go.set()
                    threads[0].join(10)
                self.assertEqual(self.events, ["app closed"])

    def kicks(self):
        """A function that sends the main thread SIGINT from the editor's thread, as the terminal's Ctrl-C does while
        the app has not taken it (no list yet, or suspended), and waits for the session's handler to have run."""
        handled = threading.Semaphore(0)
        handle = picker._Session.on_sigint

        def on_sigint(session, signum, frame):
            try:
                handle(session, signum, frame)
            finally:
                handled.release()

        def kick():
            signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)
            if not handled.acquire(timeout=10):
                raise AssertionError("timed out")
        patch = mock.patch.object(picker._Session, "on_sigint", on_sigint)
        patch.start()
        self.addCleanup(patch.stop)
        return kick

    def test_a_ctrl_c_before_the_first_list_interrupts_it(self):
        kick = self.kicks()

        def editor():
            kick()
            kick()  # a double press: within a second of the first it is the same gesture
            try:
                picker.filter_list("A", ["a0"])
            except KeyboardInterrupt:
                return "interrupted"
        self.assertEqual(self.run_editor(editor, None), "interrupted")
        self.assertEqual(self.runs, [])

    def test_a_second_ctrl_c_before_the_first_list_ends_the_session_without_the_editor(self):
        kick = self.kicks()
        go = threading.Event()
        threads = []

        def editor():
            threads.append(threading.current_thread())
            kick()
            self.now += 1
            kick()
            wait(go)

        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, None)
        self.assertTrue(threads[0].is_alive())
        self.assertEqual(self.runs, [])
        go.set()
        threads[0].join(10)

    def test_a_second_ctrl_c_between_commands_ends_the_session_without_the_editor(self):
        kick = self.kicks()
        go = threading.Event()
        threads = []

        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.confirm, "Go on?")  # the app stays suspended after it, until the next list
            threads.append(threading.current_thread())
            kick()
            self.now += 1
            kick()
            wait(go)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", return_value="y"), self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["suspend", "resume", "app closed"])
        self.assertTrue(threads[0].is_alive())
        go.set()
        threads[0].join(10)

    def test_a_ctrl_c_kept_while_a_commands_prompt_was_up_counts_from_its_answer(self):
        kick = self.kicks()

        def answer(prompt=""):
            picker._session.interrupt()  # a SIGINT in the instant before the prompt took the terminal
            self.now += 5  # the prompt stays up for 5 s
            return "y"

        def editor():
            picker.filter_list("A", ["a0"])
            at_terminal(ui.confirm, "Go on?")
            kick()  # the first Ctrl-C on the step after it: not the one that quits
            try:
                picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                return "handler ran"

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        with mock.patch("builtins.input", answer):
            try:
                got = self.run_editor(editor, script)
            except KeyboardInterrupt:
                got = "the editor was abandoned"
        self.assertEqual(got, "handler ran")

    def test_ctrl_c_twice_while_the_editor_waits_for_a_command_only_interrupts_it(self):
        def twice(app):  # as the app suspends: the editor is not at work, it waits for the prompt
            app.session.interrupt()
            self.now += 1
            app.session.interrupt()
        self.while_suspended = twice

        def editor():
            picker.filter_list("A", ["a0"])
            try:
                at_terminal(ui.confirm, "Save?")
            except KeyboardInterrupt:
                return "interrupted", picker.filter_list("B", ["b0", "b1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        with mock.patch("builtins.input") as asked:
            self.assertEqual(self.run_editor(editor, script), ("interrupted", 1))
        asked.assert_not_called()

    def test_working_shows_the_last_line_printed_as_plain_text(self):
        go = threading.Event()
        seen = []

        def editor():
            picker.filter_list("A", ["a0"])
            print("📡 Listing gba ...")
            print(ui.yellow("⚠️  \x1b[2Jslow"), file=sys.stderr)
            go.wait(5)
            return picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            last = lambda: str(app.screen_stack[0].query_one("#last").render())
            await wait_for(pilot, lambda: "slow" in last())
            seen.append(last())
            go.set()
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(self.run_editor(editor, script), 0)
        self.assertEqual(seen, ["⚠️  slow"])
        self.assertEqual(out.getvalue(), "📡 Listing gba ...\n" + ui.yellow("⚠️  \x1b[2Jslow") + "\n")

    def test_the_set_editors_commands_use_the_normal_screen_but_its_tool_check(self):
        from sync_roms import setedit
        main = threading.current_thread()

        def fake_run(cmd, **kwargs):
            self.events.append((cmd[0], threading.current_thread() is main))
            return mock.Mock(returncode=0, stdout="ok\n", stderr="")

        def editor():
            picker.filter_list("A", ["a0"])
            setedit.need_tools()
            setedit.run(["git", "push"])
            return picker.filter_list("B", ["b0"])

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        with mock.patch.object(setedit.subprocess, "run", fake_run), mock.patch.object(setedit.shutil, "which", return_value="x"):
            self.run_editor(editor, script)
        self.assertEqual(self.events, [("gh", False), "suspend", ("git", True), "resume", "app closed"])  # gh asks nothing

    def test_nested_editors_share_the_session(self):
        inner = picker.one_app(lambda: picker.filter_list("B", ["b0"]))

        def editor():
            return picker.filter_list("A", ["a0"]), inner()

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "B"))
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), (0, 0))
        self.assertEqual(len(self.runs), 1)

    def test_without_a_terminal_the_editor_runs_as_is(self):
        main = threading.current_thread()
        with mock.patch.object(ui, "has_terminal", return_value=False):
            self.assertIs(picker.one_app(threading.current_thread)(), main)


class TextualPrintHook(unittest.TestCase):
    """_ListApp overrides Textual's private App._print to keep what the editor prints while the app shows, and drops
    stale keys by comparing their stamp with textual._time.get_time. If a Textual upgrade changes either, these fail."""

    def test_app_print_has_the_signature_the_override_uses(self):
        import inspect
        from textual.app import App
        self.assertEqual(list(inspect.signature(App._print).parameters), ["self", "text", "stderr"])
        self.assertIs(inspect.signature(App._print).parameters["stderr"].default, False)

    def test_print_and_stderr_inside_a_running_app_reach_app_print(self):
        from textual.app import App
        got = []

        class Probe(App):
            def _print(self, text, stderr=False):
                got.append((text, stderr))

        async def drive():
            app = Probe()
            async with app.run_test():
                print("out")
                print("err", file=sys.stderr)
        asyncio.run(drive())
        self.assertEqual([g for g in got if g[0].strip()], [("out", False), ("err", True)])

    def test_key_events_are_stamped_with_the_clock_the_session_compares(self):
        from textual import events
        from textual._time import get_time
        before = get_time()
        key = events.Key("enter", "\r")
        self.assertTrue(before <= key.time <= get_time())


class Previews(unittest.TestCase):
    """The image pane loads the highlighted row's picture off the UI thread, once the row has stayed put."""

    def setUp(self):
        import tempfile
        from PIL import Image
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.paths = [os.path.join(tmp.name, f"{i}.png") for i in range(4)]
        for path in self.paths:
            Image.new("RGB", (45, 108), "red").save(path)
        for p in (mock.patch.object(sys, "__stdout__", io.StringIO()),  # not a terminal: the import would probe it
                  mock.patch.object(picker, "_draws_images", return_value=True)):
            p.start()
            self.addCleanup(p.stop)

    def run_list(self, script, preview):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from helpers import pilot_list
        return pilot_list(script, "A", ["a0", "a1", "a2", "a3"], preview=preview)

    def pane(self, pilot):
        return pilot.app.screen_stack[0].query_one("#preview")

    def test_only_the_row_the_cursor_rests_on_is_loaded_and_not_on_the_ui_thread(self):
        from helpers import shown_preview
        calls = []

        def preview(i):
            calls.append((i, threading.get_ident()))
            return self.paths[i]

        async def script(pilot):
            await pilot.press("j", "j", "j")  # well within the idle time: nothing loads while the cursor moves
            self.assertIsNone(self.pane(pilot).image)
            await shown_preview(pilot, self.paths[3])
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 300):
            self.assertEqual(self.run_list(script, preview), 3)
        self.assertEqual([i for i, _ in calls], [3])
        self.assertNotEqual(calls[0][1], threading.get_ident())

    def test_a_slow_preview_doesnt_hold_up_keys_and_a_stale_one_is_not_shown(self):
        from helpers import shown_preview
        started = threading.Event()
        gates = [threading.Event() for _ in self.paths]
        returned = threading.Event()

        def preview(i):
            started.set()
            wait(gates[i])
            if i == 0:
                returned.set()
            return self.paths[i]

        async def script(pilot):
            await wait_for(pilot, started.is_set)  # row 0's picture is loading
            await pilot.press("j", "j")  # handled while it still loads
            self.assertEqual(pilot.app.model.cur, 2)
            gates[0].set()  # its result comes after the cursor moved on, and is dropped
            await wait_for(pilot, returned.is_set)
            await pilot.pause(0.1)
            self.assertIsNone(self.pane(pilot).image)
            gates[1].set()
            gates[2].set()
            await shown_preview(pilot, self.paths[2])
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 1):
            self.assertEqual(self.run_list(script, preview), 2)


    def run_fixed(self, script, preview, rows=8):
        from helpers import pilot_list
        from textual_image._terminal import CellSize
        with mock.patch("textual_image._terminal.get_cell_size", return_value=CellSize(10, 20)):
            return pilot_list(script, "A", [f"a{i}" for i in range(rows)], preview=preview, preview_width=300)

    def test_a_fixed_width_preview_prefetches_the_nearby_rows_after_the_current_one(self):
        calls = []

        def preview(i):
            calls.append(i)
            return self.paths[i % 4]

        async def script(pilot):
            await pilot.press("j", "j", "j")
            await wait_for(pilot, lambda: len(calls) == 7)
            await pilot.pause(0.1)
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 300):
            self.assertEqual(self.run_fixed(script, preview), 3)
        self.assertEqual(calls, [3, 4, 2, 5, 1, 6, 0])

    def test_moving_stops_the_old_rows_prefetch(self):
        calls = []
        reached, hold = threading.Event(), threading.Event()

        def preview(i):
            calls.append((i, threading.get_ident()))
            if len(calls) == 2:  # row 0's first neighbour: held while the cursor moves on
                reached.set()
                wait(hold)
            return self.paths[i % 4]

        async def script(pilot):
            await wait_for(pilot, reached.is_set)
            await pilot.press("j")
            await pilot.pause(0.05)
            hold.set()
            await wait_for(pilot, lambda: len(calls) == 7)
            await pilot.pause(0.1)
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 1):
            self.assertEqual(self.run_fixed(script, preview), 1)
        first, second = calls[0][1], calls[2][1]
        self.assertEqual([i for i, t in calls if t == first], [0, 1])
        self.assertEqual([i for i, t in calls if t == second], [1, 2, 0, 3, 4])

    def test_a_prefetch_error_is_ignored(self):
        calls = []

        def preview(i):
            calls.append(i)
            if i == 1:
                raise OSError("boom")
            return self.paths[i % 4]

        async def script(pilot):
            await wait_for(pilot, lambda: len(calls) == 4)
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 1):
            self.assertEqual(self.run_fixed(script, preview), 0)
        self.assertEqual(calls, [0, 1, 2, 3])

    def test_a_preview_without_a_fixed_width_prefetches_nothing(self):
        from helpers import shown_preview
        calls = []

        def preview(i):
            calls.append(i)
            return self.paths[i]

        async def script(pilot):
            await pilot.press("j")
            await shown_preview(pilot, self.paths[1])
            await pilot.pause(0.2)
            await pilot.press("enter")
        with mock.patch.object(picker, "PREVIEW_IDLE_MS", 300):
            self.assertEqual(self.run_list(script, preview), 1)
        self.assertEqual(calls, [1])


class OutsideASession(unittest.TestCase):

    def test_a_ctrl_c_right_behind_enter_interrupts_the_list(self):
        from textual import events
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from helpers import pilot_list

        async def script(pilot):
            await pilot.pause()
            pilot.app.post_message(events.Key("enter", "\r"))
            pilot.app.post_message(events.Key("ctrl+c", "\x03"))
            await pilot.pause(0.2)
        with self.assertRaises(KeyboardInterrupt):
            pilot_list(script, "A", ["a0", "a1"])

    def test_a_note_prints_and_waits_for_enter(self):
        from sync_roms import edit
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input") as asked:
            edit.note("ℹ️  Saved.")
        self.assertEqual(out.getvalue(), "ℹ️  Saved.\n")
        asked.assert_called_once()
        self.assertIn("Press Enter", asked.call_args.args[0])

    def test_each_list_runs_its_own_app(self):
        runs = []

        def run(app, **_):
            runs.append(app)
            return 0
        with mock.patch.object(picker._app_class(), "run", run):
            picker.filter_list("A", ["a0"])
            picker.filter_list("B", ["b0"])
        self.assertEqual(len(runs), 2)
        self.assertIsNot(*runs)


if __name__ == "__main__":
    unittest.main()
