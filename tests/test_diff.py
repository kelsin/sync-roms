import io
import os
import sys
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli  # noqa: E402


def make_zip(files, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class ZipFingerprintTest(unittest.TestCase):
    def test_ignores_names_and_compression(self):
        a = make_zip({"Game.nes": b"abc" * 100}, zipfile.ZIP_DEFLATED)
        b = make_zip({"Game (En).nes": b"abc" * 100}, zipfile.ZIP_STORED)
        self.assertEqual(cli.zip_fingerprint(io.BytesIO(a)), cli.zip_fingerprint(io.BytesIO(b)))

    def test_different_content(self):
        a = make_zip({"g.nes": b"abc"})
        b = make_zip({"g.nes": b"abd"})
        self.assertNotEqual(cli.zip_fingerprint(io.BytesIO(a)), cli.zip_fingerprint(io.BytesIO(b)))


def Z(x):
    return ("zip", ((x, 0),))


class PlanReplaceTest(unittest.TestCase):
    def plan(self, local, remote, prints):
        return cli.plan_replace(local, {p: (n, '"e"') for p, n in remote.items()},
                                lambda p: Z(prints[p]), lambda p, s, e: Z(prints[p]))

    def test_sorts_files_into_the_five_cases(self):
        local = {"same.zip": 1, "renamed.zip": 2, "new.zip": 3, "changed.zip": 4}
        remote = {"same.zip": 1, "old.zip": 5, "changed.zip": 6, "extra.zip": 7}
        prints = {"renamed.zip": "r", "old.zip": "r", "new.zip": "n", "changed.zip": "c1", "extra.zip": "x"}
        remote_prints = dict(prints, **{"changed.zip": "c2"})
        renames, new, changed, only_bucket = cli.plan_replace(
            local, {p: (n, '"e"') for p, n in remote.items()},
            lambda p: Z(prints[p]), lambda p, s, e: Z(remote_prints[p]))
        self.assertEqual(renames, [("old.zip", "renamed.zip")])
        self.assertEqual(new, ["new.zip"])
        self.assertEqual(changed, ["changed.zip"])
        self.assertEqual(only_bucket, ["extra.zip"])

    def test_same_path_and_size_is_checked_only_when_the_hashes_differ(self):
        local, remote = {"a.zip": 5, "b.zip": 5}, {"a.zip": (5, '"1"'), "b.zip": (5, '"2"')}
        prints = {"a.zip": "x", "b.zip": "x"}
        remote_prints = {"a.zip": "x", "b.zip": "y"}
        asked = []
        result = cli.plan_replace(local, remote, lambda p: Z(prints[p]), lambda p, s, e: Z(remote_prints[p]),
                                  lambda p, etag: asked.append(p) or p == "b.zip")
        self.assertEqual(result, ([], [], ["b.zip"], []))
        self.assertEqual(sorted(asked), ["a.zip", "b.zip"])

    def test_same_content_at_same_path_is_not_a_rename(self):
        fp = {"a.zip": "x"}
        self.assertEqual(self.plan({"a.zip": 5}, {"a.zip": 6}, fp), ([], [], [], []))

    def test_bucket_file_at_a_rename_target_is_overwritten_not_offered_for_deletion(self):
        prints = {"b.zip": "x", "a.zip": "x"}
        remote_prints = {"a.zip": "x", "b.zip": "y"}
        renames, new, changed, only_bucket = cli.plan_replace(
            {"b.zip": 1}, {"a.zip": (1, '"e"'), "b.zip": (2, '"e"')},
            lambda p: Z(prints[p]), lambda p, s, e: Z(remote_prints[p]))
        self.assertEqual((renames, new, changed, only_bucket), ([("a.zip", "b.zip")], [], [], []))


class PlanDiffTest(unittest.TestCase):
    def test_renames_and_same_files_are_ignored(self):
        local = {"same.zip": 10, "new name.zip": 20, "only local.zip": 30}
        remote = {"same.zip": (10, '"a"'), "old name.zip": (25, '"b"'), "only bucket.zip": (40, '"c"')}
        prints = {"new name.zip": ("zip", ((1, 1),)), "only local.zip": ("zip", ((2, 2),)),
                  "old name.zip": ("zip", ((1, 1),)), "only bucket.zip": ("zip", ((3, 3),))}
        calls = []

        def local_print(p):
            calls.append(p)
            return prints[p]

        only_local, only_bucket = cli.plan_diff(local, remote, local_print, lambda p, size, etag: prints[p])
        self.assertEqual(only_local, ["only local.zip"])
        self.assertEqual(only_bucket, ["only bucket.zip"])
        self.assertNotIn("same.zip", calls)

    def test_same_path_different_size_but_same_content(self):
        fp = ("zip", ((1, 1),))
        self.assertEqual(cli.plan_diff({"a.zip": 5}, {"a.zip": (6, '"x"')}, lambda p: fp, lambda p, s, e: fp), ([], []))

    def test_raw_files_compare_md5_when_known(self):
        self.assertTrue(cli.same_content(("raw", 5, "x"), ("raw", 5, None)))
        self.assertFalse(cli.same_content(("raw", 5, "x"), ("raw", 5, "y")))
        self.assertFalse(cli.same_content(("raw", 5, "x"), ("raw", 6, "x")))
        self.assertFalse(cli.same_content(("raw", 5, "x"), ("zip", ())))


if __name__ == "__main__":
    unittest.main()
