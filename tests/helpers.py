"""Shared test bases and helpers. Importing this module imports isolate first, so the run is hermetic."""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, commands, inventory, picker, runtime, store, ui, usersettings  # noqa: E402

SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []},
          "games": [{"bucket": "gba/Game.zip"}]}
MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}
ENV = ("ROMS_BUCKET", "ROMS_ENDPOINT", "ROMS_PROFILE", "ROMS_WRITE_PROFILE")
# A Vita game with its DLC and newest update (vita.py tells them apart by these tags), and another game
VITA_GAME = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
VITA_DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
VITA_UPDATE = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
VITA_OTHER = "psvita/H [PCSE00001] [USA] [NoNpDRM].zip"


def list_sizes(prefix, sizes=True):
    return {"gba/Game.zip": 5} if prefix == "gba/" else {}


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def touch(path, data=b"x"):
    """Write data (bytes, or text for a str) to path, making its folders."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def http_error(test, url, code, msg, fp=None):
    """A urllib HTTPError that is closed when the test ends. One left open warns (ResourceWarning) when the garbage
    collector gets to it, which can be while a later test is capturing stderr."""
    err = urllib.error.HTTPError(url, code, msg, {}, fp)
    test.addCleanup(err.close)
    return err


def load_script(path):
    """Import the Python file at path as a module named after it (a skill or tools script, which isn't a package)."""
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def feed_list(keys, *args, **kwargs):
    """picker.filter_list(*args, **kwargs) without a screen: its list model gets keys in turn (Textual key names or
    characters; None: a poll tick, no key came). Returns the list's result."""
    def run(model):
        for k in keys:
            got = model.tick() if k is None else model.key(k)
            if got is not picker.KEEP and got is not picker.UNCHANGED:
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


async def shown_preview(pilot, path=None):
    """Wait until the list's image pane shows the picture at path (any picture when path is None, a loaded one is a
    PIL image) and return its file name (None for a resized one)."""
    for _ in range(500):
        image = pilot.app.screen_stack[0].query_one("#preview").image
        if image is not None and (path is None or image.filename == path):
            return getattr(image, "filename", None)  # a resized picture (preview_width) has none
        await pilot.pause(0.01)
    raise AssertionError("no preview came")


def screen_lines(app):
    """The list screen's rows as [(text, Rich style)] runs of non-blank text."""
    screen, out = app.screen_stack[0], []
    for name in ("_ListHeader", "_ListLines", "_ListFooter"):
        widget = screen.query_one(name)
        out += [[(s.text, str(s.style)) for s in strip if s.text.strip()] for strip in widget.render_lines(widget.region.at_offset((0, 0)))]
    return out


def screen_text(app):
    """The list screen as plain text: the header and its border, the rows between the borders (as wide as the list, trailing
    blanks kept), then the bottom border, the tag lines and the status row."""
    screen = app.screen_stack[0]
    out = []
    for name in ("_ListHeader", "_ListLines", "_ListFooter"):
        widget = screen.query_one(name)
        out += ["".join(s.text for s in strip) for strip in widget.render_lines(widget.region.at_offset((0, 0)))]
    return out


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
        self.enterContext(mock.patch.object(store, "data_dir", lambda: self.tmp.name))

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


class StorageFolder(DataDir):
    """runtime.ROOT is a throwaway storage folder holding gba/a.zip (1 byte), gba/b.zip (2) and BIOS/x.bin (3)."""

    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        for key, size in (("gba/a.zip", 1), ("gba/b.zip", 2), ("BIOS/x.bin", 3)):
            self.put(key, size)
        for name, value in (("ROOT", self.root.name), ("BUCKET", None), ("ENDPOINT", None), ("_mirror_root", None)):
            self.enterContext(mock.patch.object(runtime, name, value))

    def put(self, key, size):
        touch(os.path.join(self.root.name, key), b"x" * size)

    def build(self, full=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return inventory.update(full)


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
            self.enterContext(p)

    def put(self, key, data=b"abc"):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def read_json(self, key):
        with open(os.path.join(self.root, key)) as f:
            return json.load(f)


class CardDir(StorageDir):
    """A StorageDir with an empty card folder (self.card), for the installers that put something on card "c" and
    record it in that card's FIELD (set by the subclass)."""

    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)

    def cp(self, *parts):
        return os.path.join(self.card, *parts)

    def recorded(self):
        return (store.load_cards().get("c") or {}).get(self.FIELD)

    def snapshot(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.card) for f in fs)


class ScriptDir(StorageDir):
    """A StorageDir for a script's main(): usersettings.apply_settings does nothing, so storage stays this folder."""

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))

    def run_script(self, main, *args):
        """main(*args) with its output captured: (what it returned, what it printed)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(*args)
        return code, out.getvalue()


def storage_tags(test, data, root=None):
    """Put tags in storage as tags.json and make tags.load() read them (once, as a run does).

    data: the tags data (written with tags.dump), a str (the file's exact text) or None (no file). root: the storage
    folder already wired in as runtime.ROOT; without it a throwaway one is made and wired in, its local copies going
    to store.data_dir() (patch that first). Returns the storage folder."""
    from sync_roms import inventory, tags
    if root is None:
        root = test.enterContext(tempfile.TemporaryDirectory())
        for name, value in (("ROOT", root), ("BUCKET", None), ("ENDPOINT", None), ("_mirror_root", None)):
            test.enterContext(mock.patch.object(runtime, name, value))
    path = os.path.join(root, tags.KEY)
    if data is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else tags.dump(data))
    inventory.reset()
    test.addCleanup(inventory.reset)
    tags.reset()
    test.addCleanup(tags._set, tags._empty())  # back to no tags, as isolate leaves it
    return root


class Isolated(RealDataDirGuard):
    """Runs cli.sync() with a given argv and settings.json, leaving the process-wide settings as they were."""

    def setUp(self):
        super().setUp()
        for name in ("BUCKET", "ENDPOINT", "PROFILE", "WRITE_PROFILE"):
            self.enterContext(mock.patch.object(runtime, name, getattr(runtime, name)))
        self.enterContext(mock.patch.dict(os.environ))
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
