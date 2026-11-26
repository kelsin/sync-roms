"""Imported first by every test module: makes the run hermetic. HOME, XDG and AWS settings point into a throwaway
folder, SYNC_ROMS_*/ROMS_* variables are cleared, and an audit hook fails any test that touches the real data folder
or the real ~/.aws, resolving symlinks with a per-directory cache that renames and symlinks empty (REAL_DATA_DIR is
only a path here; nothing in it is ever read)."""
import atexit
import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

TEST_HOME_VAR = "SYNC_ROMS_TEST_HOME"
REAL_VAR = "SYNC_ROMS_TEST_REAL_DIRS"  # exported so a nested run (a child process) keeps the same forbidden paths


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


if not os.environ.get(TEST_HOME_VAR):
    _real_home = os.path.expanduser("~")
    _xdg = os.environ.get("XDG_DATA_HOME")
    _forbidden = [os.path.join(_xdg, "sync-roms") if _xdg else os.path.join(_real_home, ".sync-roms"),
                  os.path.join(_real_home, ".sync-roms"), os.path.join(_real_home, ".aws")]
    if sys.platform == "win32" and os.environ.get("APPDATA"):  # where store.data_dir() looks on Windows
        _forbidden.append(os.path.join(os.environ["APPDATA"], "sync-roms"))
    os.environ[REAL_VAR] = os.pathsep.join(dict.fromkeys(_forbidden))
    _home = tempfile.mkdtemp(prefix="sync-roms-test-home-")
    atexit.register(shutil.rmtree, _home, ignore_errors=True)
    os.environ[TEST_HOME_VAR] = _home
    for var in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
                "XDG_STATE_HOME"):
        os.environ[var] = _home
    for var in list(os.environ):
        if var.startswith(("SYNC_ROMS_", "ROMS_", "AWS_")) and var not in (TEST_HOME_VAR, REAL_VAR):
            del os.environ[var]
    os.environ.pop("ESDE_APPDATA_DIR", None)  # EmuDeck's ES-DE folder resolves into the throwaway home
    # a missing file, not the real one, if some code reads these directly
    os.environ["AWS_CONFIG_FILE"] = os.path.join(_home, ".aws", "config")
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(_home, ".aws", "credentials")

from sync_roms import store  # noqa: E402  (after the environment is cleared: runtime reads ROMS_* at import)
from sync_roms import ignore, names, tags, tagui  # noqa: E402

ignore._keys = frozenset()  # no test reads the ignore list from storage unless it calls ignore.reset()
names._scraped = {s: {} for s in names.SYSTEMS}  # no test reads scraped names from storage unless it calls names.reset()
tags._set(tags._empty())  # no tags: tests that need some put them in storage (helpers.storage_tags)

# The tag filter, recent tags and `.` are process-wide: every test starts without them. TestCase.run is the one place
# every test goes through: unittest has no public per-test hook, many setUp overrides don't call super(), and
# _callSetUp is private.
if not getattr(unittest.TestCase, "_sync_roms_filter_reset", False):
    _run = unittest.TestCase.run

    def _run_without_tag_filter(self, result=None):
        tagui.FILTER.clear()
        tagui.RECENT.clear()
        tagui.LAST.clear()
        return _run(self, result)

    unittest.TestCase.run = _run_without_tag_filter
    unittest.TestCase._sync_roms_filter_reset = True

TEST_HOME = os.environ[TEST_HOME_VAR]
FORBIDDEN = [_norm(p) for p in os.environ[REAL_VAR].split(os.pathsep) if p]
REAL_DATA_DIR = FORBIDDEN[0]  # the real data folder, as a path only

_TWO_PATHS = {"os.rename", "os.symlink", "os.link", "shutil.copyfile", "shutil.copytree", "shutil.move"}
_EVENTS = {"open", "os.listdir", "os.scandir", "os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.chmod", "os.chdir",
           "os.truncate", "os.utime", "os.symlink", "os.link", "shutil.copyfile", "shutil.copytree", "shutil.move",
           "shutil.rmtree", "glob.glob", "os.walk"}


_cache = {}  # absolute directory -> _norm(directory); emptied by _audit whenever a directory could resolve differently
_generation = 0  # bumped with every emptying, so a lookup that raced one isn't stored. Limit: a lookup on another thread
# that starts between this thread's hook and its rename syscall can still store a pre-rename entry; a pre-event hook
# can't close that, and it takes a thread swapping a directory for a symlink into the real folders mid-lookup


_FORGET = {"os.symlink", "os.rename", "os.link", "shutil.move"}


def _norm_cached(path):
    """_norm(path) with the parent directory's resolution cached: only the last component is checked each time."""
    if sys.platform == "win32":  # ntpath.realpath also resolves junctions and short names in the last component
        return _norm(path)
    path = os.path.abspath(path)
    parent, name = os.path.split(path)
    if not name:
        return _norm(path)
    resolved = _cache.get(parent)
    if resolved is None:
        generation = _generation
        resolved = _norm(parent)
        if generation == _generation:
            _cache[parent] = resolved
    joined = os.path.join(resolved, name)
    if os.path.islink(joined):  # a symlink as the last component can point anywhere
        return _norm(path)
    return os.path.normcase(joined)


def _forget_directories(event, args):
    """Empties the cache before an event that can change what a cached directory resolves to: any symlink, and a
    rename, link or move of anything but a regular file (renaming a file can't, and atomic writes do it all the time).
    Returns whether it emptied the cache."""
    global _generation
    if event != "os.symlink":
        try:
            if all(fd == -1 for fd in args[2:4]) and stat.S_ISREG(os.lstat(args[0]).st_mode):
                return False
        except Exception:  # can't be stat'ed: empty it
            pass
    _generation += 1
    _cache.clear()
    return True


def _inside(path, norm=None):
    p = (norm or _norm_cached)(path)
    return any(p == f or p.startswith(f + os.sep) for f in FORBIDDEN)


VIOLATIONS = []  # every blocked access, so a test that swallows the error still fails (see RealDataDirGuard)


def _audit(event, args):
    if event not in _EVENTS:
        return
    norm = _norm if event in _FORGET and _forget_directories(event, args) else None  # nothing cached before the event happens
    paths = args[:2] if event in _TWO_PATHS else args[:1]  # later args (an open mode, flags) aren't paths
    for a in paths:
        if isinstance(a, (str, bytes, os.PathLike)) and _inside(os.fsdecode(a), norm):
            msg = f"test touched the real {os.fsdecode(a)} ({event}); tests must stay inside {TEST_HOME}"
            VIOLATIONS.append(msg)
            raise AssertionError(msg)


if not getattr(sys, "_sync_roms_audit", False):
    sys._sync_roms_audit = True
    sys.addaudithook(_audit)


def assert_hermetic():
    """Fails loudly unless the unpatched data folder and home resolve inside the throwaway home (no disk access)."""
    for what, path in (("store.data_dir()", store.data_dir()), ("~", os.path.expanduser("~"))):
        if _norm(path) != _norm(TEST_HOME) and not _norm(path).startswith(_norm(TEST_HOME) + os.sep):
            raise AssertionError(f"{what} resolves to {path}, outside the test home {TEST_HOME}: import isolate first")
