"""Shared test bases and helpers. Importing this module imports isolate first, so the run is hermetic."""
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, commands, picker, runtime, store, ui, usersettings  # noqa: E402

SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []},
          "games": [{"bucket": "gba/Game.zip"}]}
MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}
ENV = ("ROMS_BUCKET", "ROMS_ENDPOINT", "ROMS_PROFILE", "ROMS_WRITE_PROFILE")


def list_sizes(prefix, sizes=True):
    return {"gba/Game.zip": 5} if prefix == "gba/" else {}


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def feed_list(keys, *args, **kwargs):
    """picker.filter_list(*args, **kwargs) without a screen: its list model gets keys in turn (Textual key names or
    characters; None: a poll tick, no key came). Returns the list's result."""
    def run(model):
        for k in keys:
            got = model.tick() if k is None else model.key(k)
            if got is not picker.KEEP:
                return got
        raise AssertionError("the list is still open after the last key")
    with mock.patch.object(picker, "_run", run):
        return picker.filter_list(*args, **kwargs)


def pilot_list(script, *args, size=(80, 24), **kwargs):
    """picker.filter_list(*args, **kwargs) on a headless Textual screen of size (80x24) that the async script(pilot)
    drives. Returns (or raises) what filter_list does."""
    def run(app, **_):
        async def drive():
            async with app.run_test(size=size) as pilot:
                await script(pilot)
            return app.return_value
        return asyncio.run(drive())
    with mock.patch.object(picker._app_class(), "run", run):
        return picker.filter_list(*args, **kwargs)


def screen_lines(app):
    """The list screen's rows as [(text, Rich style)] runs of non-blank text."""
    lines = app.screen_stack[0].query_one("_ListLines")
    return [[(s.text, str(s.style)) for s in strip if s.text.strip()] for strip in lines.render_lines(lines.region)]


def screen_text(app):
    """The list screen's rows as plain text, each as wide as the list (trailing blanks kept)."""
    lines = app.screen_stack[0].query_one("_ListLines")
    return ["".join(s.text for s in strip) for strip in lines.render_lines(lines.region)]


def script_for(shell):
    """The completion script `sync-roms completion <shell>` prints."""
    out = mock.MagicMock()
    with mock.patch("builtins.print", out):
        commands.completion_cmd(mock.Mock(shell=shell, what=None))
    return "".join(c.args[0] if c.args else "\n" for c in out.call_args_list)


class DataDir(RealDataDirGuard):
    """store.data_dir() is a throwaway folder (self.tmp)."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(store, "data_dir", lambda: self.tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def read(self, name):
        with open(self.path(name)) as f:
            return json.load(f)

    def write_json(self, name, data):
        write_json(self.path(name), data)


class Cmd(DataDir):
    def run_cmd(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = commands.run(list(argv))
            except SystemExit as e:
                code = e.code
            finally:
                ui.ASSUME_YES = False
        return code, out.getvalue(), err.getvalue()


class StorageDir(RealDataDirGuard):
    """A throwaway storage folder (self.root) and data folder (self.data), wired in as runtime.ROOT and store.data_dir()."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "storage")
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        for p in (mock.patch.object(runtime, "ROOT", self.root), mock.patch.object(runtime, "_mirror_root", None),
                  mock.patch.object(store, "data_dir", return_value=self.data)):
            p.start()
            self.addCleanup(p.stop)

    def put(self, key, data=b"abc"):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path


class Isolated(RealDataDirGuard):
    """Runs cli.sync() with a given argv and settings.json, leaving the process-wide settings as they were."""

    def setUp(self):
        super().setUp()
        for name in ("BUCKET", "ENDPOINT", "PROFILE", "WRITE_PROFILE"):
            p = mock.patch.object(runtime, name, getattr(runtime, name))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        for name in ENV:
            os.environ.pop(name, None)
        runtime.OVERRIDES.clear()
        self.addCleanup(runtime.OVERRIDES.clear)

    def sync(self, argv, settings=None, **patches):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(sys, "argv", ["sync-roms"] + argv))
            st.enter_context(mock.patch.object(usersettings, "load_settings", lambda: dict(settings or {})))
            for target, name, value in patches.values():
                st.enter_context(mock.patch.object(target, name, value))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                code = cli.sync()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()
