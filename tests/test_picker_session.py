"""picker.one_app: an editor's lists share one Textual app (headless here), prompts run outside it."""
import asyncio
import contextlib
import io
import os
import queue
import sys
import threading
import time
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


class Session(unittest.TestCase):
    def setUp(self):
        self.runs = []  # one entry per App.run
        self.events = []
        for p in (mock.patch.object(ui, "has_terminal", return_value=True),
                  mock.patch.object(picker, "_draws_images", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def run_editor(self, editor, script):
        """Run editor through picker.one_app; each app it starts runs headless and is driven by script(app, pilot)."""
        def run(app, **_):
            self.runs.append(app)

            async def drive():
                async with app.run_test(size=(80, 24)) as pilot:
                    await script(app, pilot)
                    await wait_for(pilot, lambda: not app.is_running)
            asyncio.run(drive())
            self.events.append("app closed")

        @contextlib.contextmanager
        def suspend(app):
            self.events.append("suspend")
            yield
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

    def test_a_prompt_suspends_the_app_and_runs_on_the_main_thread(self):
        main = threading.current_thread()

        def answer(prompt=""):
            self.events.append(("input", threading.current_thread() is main, out.getvalue()))
            return "y"

        def editor():
            picker.filter_list("A", ["a0"])
            print("before the prompt")
            yes = ui.confirm("Go on?")
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

    def test_prompts_in_a_row_share_one_suspend(self):
        def answer(prompt=""):
            self.events.append(("input", out.getvalue()))
            return "x"

        def editor():
            picker.filter_list("A", ["a0"])
            ui.ask("Name: ")
            print("between")
            ui.ask("Description: ")
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

    def test_a_prompt_before_any_list_starts_no_app(self):
        main = threading.current_thread()
        threads = []

        def answer(prompt=""):
            threads.append(threading.current_thread() is main)
            return "n"

        with mock.patch("builtins.input", answer):
            self.assertFalse(self.run_editor(lambda: ui.confirm("Go on?"), None))
        self.assertEqual((threads, self.runs), ([True], []))

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

    def test_ctrl_c_at_a_prompt_raises_in_the_editor(self):
        def editor():
            picker.filter_list("A", ["a0"])
            try:
                ui.confirm("Save?")
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

    def test_an_editor_that_ends_at_a_prompt_closes_the_app(self):
        def editor():
            picker.filter_list("A", ["a0"])
            ui.confirm("Save?")
            print("saved")

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input", return_value="y"):
            self.run_editor(editor, script)
        self.assertEqual(out.getvalue(), "saved\n")
        self.assertEqual(self.events, ["suspend", "resume", "app closed"])

    def test_ctrl_c_while_working_interrupts_the_work_at_once(self):
        started = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            try:
                started.set()
                for _ in range(1000):  # ten seconds of "work", unless interrupted
                    time.sleep(0.01)
                return "finished"
            except KeyboardInterrupt:
                yes = ui.confirm("Save?")  # the editors' handlers ask, save or review, then stop
                return "interrupted", yes

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, started.is_set)
            await pilot.press("ctrl+c")
        begun = time.monotonic()
        with mock.patch("builtins.input", return_value="y"):
            self.assertEqual(self.run_editor(editor, script), ("interrupted", True))
        self.assertLess(time.monotonic() - begun, 5)

    def test_ctrl_c_while_working_that_escapes_the_editor_reaches_the_caller_once(self):
        started = threading.Event()

        def editor():
            picker.filter_list("A", ["a0"])
            started.set()
            for _ in range(1000):
                time.sleep(0.01)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, started.is_set)
            await pilot.press("ctrl+c")
            await pilot.press("ctrl+c")  # a second one while the first unwinds
        with self.assertRaises(KeyboardInterrupt):
            self.run_editor(editor, script)
        self.assertEqual(self.events, ["app closed"])

    def test_ctrl_c_while_handing_over_a_list_takes_it_back(self):
        class Late(queue.Queue):
            """A reply queue whose wait is cut short by the Ctrl-C that came just before the list."""
            def get(self, *args, **kwargs):
                raise KeyboardInterrupt

        def editor():
            picker.filter_list("A", ["a0"])
            try:
                with mock.patch.object(picker.queue, "Queue", Late):
                    picker.filter_list("B", ["b0"])
            except KeyboardInterrupt:
                pass
            return picker.filter_list("C", ["c0", "c1"], cursor=1)

        async def script(app, pilot):
            await wait_for(pilot, lambda: showing(app, "A"))
            await pilot.press("enter")
            await wait_for(pilot, lambda: showing(app, "C"))
            self.events.append([type(s).__name__ for s in app.screen_stack])
            await pilot.press("enter")
        self.assertEqual(self.run_editor(editor, script), 1)
        self.assertEqual(self.events[0], ["_WorkingScreen", "_ListScreen"])  # B is gone

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

    def test_commands_the_set_editor_runs_use_the_normal_screen(self):
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
        self.assertEqual(self.events, ["suspend", ("gh", True), ("git", True), "resume", "app closed"])

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
    """_ListApp overrides Textual's private App._print to keep what the editor prints while the app shows. If a Textual
    upgrade renames it or changes how print reaches it, these fail: see _ListApp._print."""

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


class OutsideASession(unittest.TestCase):
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
