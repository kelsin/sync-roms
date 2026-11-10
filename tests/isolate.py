"""Imported first by every test module: points the sync-roms data folder and the home folder at a throwaway one, so no
test reads or writes the real settings.json, cards.json, games.json or ~/.aws. REAL_DATA_DIR is where they really live."""
import atexit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from sync_roms import store  # noqa: E402

REAL_DATA_DIR = store.data_dir()

if not os.environ.get("SYNC_ROMS_TEST_HOME"):
    _home = tempfile.mkdtemp(prefix="sync-roms-test-home-")
    atexit.register(shutil.rmtree, _home, ignore_errors=True)
    os.environ["SYNC_ROMS_TEST_HOME"] = _home
    for var in ("HOME", "USERPROFILE", "APPDATA", "XDG_DATA_HOME"):
        os.environ[var] = _home
    for var in ("ROMS_PROFILE", "ROMS_WRITE_PROFILE", "AWS_PROFILE", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        os.environ.pop(var, None)
