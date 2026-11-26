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
        self.real_forbidden = list(isolate.FORBIDDEN)  # the real folders stay guarded while these tests run
        patch = mock.patch.object(isolate, "FORBIDDEN", [*self.real_forbidden, isolate._norm(self.forbidden)])
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
        self.refused(os.path.join(self.forbidden, "secret"))

    def symlink(self, target, link):
        with mock.patch.object(isolate, "FORBIDDEN", self.real_forbidden):  # making a link to the forbidden folder is itself refused
            os.symlink(target, link)

    def test_directory_replaced_by_symlink_refused(self):
        folder = os.path.join(self.tmp, "folder")
        ready = os.path.join(self.tmp, "ready")
        self.symlink(self.tmp, ready)  # made first, so the rename below is the only event that can empty the cache
        os.makedirs(os.path.join(folder, "forbidden"))
        with open(os.path.join(folder, "forbidden", "secret"), "w"):
            pass  # folder/forbidden is a plain directory, and its lookup is cached
        self.assertIn(os.path.join(folder, "forbidden"), isolate._cache)
        shutil.rmtree(folder)
        os.rename(ready, folder)  # now folder/forbidden is the forbidden folder
        self.refused(os.path.join(folder, "forbidden", "secret"))

    def test_renaming_a_directory_empties_the_cache(self):
        a = os.path.join(self.tmp, "a")
        os.makedirs(os.path.join(a, "sub"))
        with open(os.path.join(a, "sub", "f"), "w"):
            pass
        self.assertIn(os.path.join(a, "sub"), isolate._cache)
        os.rename(a, os.path.join(self.tmp, "b"))
        self.assertNotIn(os.path.join(a, "sub"), isolate._cache)

    def test_renaming_a_regular_file_keeps_the_cache(self):
        with open(os.path.join(self.safe, "f"), "w"):
            pass
        self.assertIn(self.safe, isolate._cache)
        os.replace(os.path.join(self.safe, "f"), os.path.join(self.safe, "g"))
        self.assertIn(self.safe, isolate._cache)

    def test_rename_event_paths_not_cached_before_it_happens(self):
        # M -> old, old/forbidden/a -> tmp; renaming M/forbidden/a onto M makes M/forbidden the forbidden folder. The
        # hook empties the cache for the rename, so its own paths must not refill it with their pre-rename parents.
        old = os.path.join(self.tmp, "old")
        os.makedirs(os.path.join(old, "forbidden"))
        m = os.path.join(self.tmp, "M")
        self.symlink(old, m)
        self.symlink(self.tmp, os.path.join(old, "forbidden", "a"))
        os.rename(os.path.join(m, "forbidden", "a"), m)
        self.assertEqual(os.path.realpath(os.path.join(m, "forbidden", "secret")), os.path.join(self.forbidden, "secret"))
        self.refused(os.path.join(m, "forbidden", "secret"))

    def test_symlink_over_a_missing_directory_refused(self):
        ghost = os.path.join(self.tmp, "ghost")
        with self.assertRaises(FileNotFoundError):
            open(os.path.join(ghost, "forbidden", "secret"))  # the missing directory's lookup is cached
        self.assertIn(os.path.join(ghost, "forbidden"), isolate._cache)
        self.symlink(self.tmp, ghost)  # now ghost/forbidden is the forbidden folder
        self.refused(os.path.join(ghost, "forbidden", "secret"))

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
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.safe)
        self.refused(os.path.join("..", "forbidden", "secret"))
        self.assertTrue(isolate._inside(os.path.join("..", "forbidden", "secret")))

    def test_cached_norm_equals_norm(self):
        self.symlink(self.forbidden, os.path.join(self.safe, "dirlink"))
        self.symlink("nowhere", os.path.join(self.safe, "dangling"))
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.safe)
        for p in ("x", "./x", "x/", "../forbidden/secret", "dirlink/secret", "dirlink", "dirlink/", "dangling", "dangling/x",
                  "missing/deeper/x", "dirlink/../x", self.safe + "//x", os.sep, "."):
            for _ in range(2):  # cold, then warm
                self.assertEqual(isolate._norm_cached(p), isolate._norm(p), p)


if __name__ == "__main__":
    unittest.main()
