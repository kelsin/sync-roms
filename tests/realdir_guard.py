"""A test base that fails loudly when a test changes the real sync-roms data folder (~/.sync-roms)."""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sync_roms import store  # noqa: E402

REAL = store.data_dir()  # read at import, before any test patches it


def snapshot():
    """{file name: (size, mtime, md5)} of the real data folder's files."""
    out = {}
    if not os.path.isdir(REAL):
        return out
    for name in sorted(os.listdir(REAL)):
        path = os.path.join(REAL, name)
        if os.path.isfile(path):
            st = os.stat(path)
            with open(path, "rb") as f:
                out[name] = (st.st_size, st.st_mtime_ns, hashlib.md5(f.read()).hexdigest())
    return out


class RealDataDirGuard(unittest.TestCase):
    """Subclasses call super().setUp() first; the check runs after every other cleanup (patches, thread joins)."""

    def setUp(self):
        before = snapshot()
        self.addCleanup(lambda: self.assertEqual(snapshot(), before, f"a test changed {REAL}"))
        super().setUp()
