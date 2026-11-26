import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402


class HookCacheTests(unittest.TestCase):
    """The audit hook caches directory lookups; the guard must still refuse the real folders."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="isolate-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.forbidden = os.path.join(self.tmp, "forbidden")
        os.mkdir(self.forbidden)
        open(os.path.join(self.forbidden, "secret"), "w").close()
        self.safe = os.path.join(self.tmp, "safe")
        os.mkdir(self.safe)
        patch = mock.patch.object(isolate, "FORBIDDEN", [isolate._norm(self.forbidden)])
        patch.start()
        self.addCleanup(patch.stop)
        isolate._cache.clear()
        self.addCleanup(isolate._cache.clear)
        before = list(isolate.VIOLATIONS)
        self.addCleanup(lambda: isolate.VIOLATIONS.__setitem__(slice(None), before))  # this test's own refusals

    def refused(self, path):
        with self.assertRaises(AssertionError):
            open(path).close()

    def test_forbidden_file_refused_with_warm_cache(self):
        for name in ("a", "b"):
            with open(os.path.join(self.safe, name), "w"):
                pass
        self.refused(os.path.join(self.forbidden, "secret"))
        self.assertTrue(os.path.isdir(self.safe))
        self.refused(os.path.join(self.forbidden, "secret"))

    def symlink(self, target, link):
        with mock.patch.object(isolate, "FORBIDDEN", []):  # making a link to the forbidden folder is itself refused
            os.symlink(target, link)

    def test_directory_replaced_by_symlink_refused(self):
        folder = os.path.join(self.tmp, "folder")
        os.makedirs(os.path.join(folder, "forbidden"))
        with open(os.path.join(folder, "forbidden", "secret"), "w"):
            pass  # folder/forbidden is a plain directory, and its lookup is cached
        shutil.rmtree(folder)
        ready = os.path.join(self.tmp, "ready")
        self.symlink(self.tmp, ready)
        os.rename(ready, folder)  # now folder/forbidden is the forbidden folder
        self.refused(os.path.join(folder, "forbidden", "secret"))

    def test_symlink_as_last_component_refused(self):
        link = os.path.join(self.safe, "link")
        self.symlink(os.path.join(self.forbidden, "secret"), link)
        self.refused(link)

    def test_relative_path_and_allowed_file(self):
        path = os.path.join(self.safe, "ok")
        with open(path, "w"):
            pass
        with open(path):
            pass
        self.assertFalse(isolate._inside(os.path.relpath(path)))


if __name__ == "__main__":
    unittest.main()
