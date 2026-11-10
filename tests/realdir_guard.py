"""A test base that fails loudly unless the test runs hermetically (the data folder resolves inside the throwaway
home). Touching the real folder is stopped by isolate's audit hook; nothing here reads it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402


class RealDataDirGuard(unittest.TestCase):
    """Subclasses call super().setUp() first, before any patch of store.data_dir."""

    def setUp(self):
        isolate.assert_hermetic()
        self.addCleanup(lambda: self.assertEqual(isolate.VIOLATIONS, []))
        super().setUp()
