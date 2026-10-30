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
