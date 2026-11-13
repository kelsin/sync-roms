import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import diff  # noqa: E402


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
        self.assertEqual(diff.zip_fingerprint(io.BytesIO(a)), diff.zip_fingerprint(io.BytesIO(b)))

    def test_different_content(self):
        a = make_zip({"g.nes": b"abc"})
        b = make_zip({"g.nes": b"abd"})
        self.assertNotEqual(diff.zip_fingerprint(io.BytesIO(a)), diff.zip_fingerprint(io.BytesIO(b)))


def Z(x):
    return ("zip", ((x, 0),))


class PlanReplaceTest(unittest.TestCase):
    def plan(self, local, remote, prints):
        return diff.plan_replace(local, {p: (n, '"e"') for p, n in remote.items()},
                                lambda p: Z(prints[p]), lambda p, s, e: Z(prints[p]))

    def test_sorts_files_into_the_five_cases(self):
        local = {"same.zip": 1, "renamed.zip": 2, "new.zip": 3, "changed.zip": 4}
        remote = {"same.zip": 1, "old.zip": 5, "changed.zip": 6, "extra.zip": 7}
        prints = {"renamed.zip": "r", "old.zip": "r", "new.zip": "n", "changed.zip": "c1", "extra.zip": "x"}
        remote_prints = dict(prints, **{"changed.zip": "c2"})
        renames, new, changed, only_bucket = diff.plan_replace(
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
        result = diff.plan_replace(local, remote, lambda p: Z(prints[p]), lambda p, s, e: Z(remote_prints[p]),
                                  lambda p, etag: asked.append(p) or p == "b.zip")
        self.assertEqual(result, ([], [], ["b.zip"], []))
        self.assertEqual(sorted(asked), ["a.zip", "b.zip"])

    def test_same_content_at_same_path_is_not_a_rename(self):
        fp = {"a.zip": "x"}
        self.assertEqual(self.plan({"a.zip": 5}, {"a.zip": 6}, fp), ([], [], [], []))

    def test_bucket_file_at_a_rename_target_is_overwritten_not_offered_for_deletion(self):
        prints = {"b.zip": "x", "a.zip": "x"}
        remote_prints = {"a.zip": "x", "b.zip": "y"}
        renames, new, changed, only_bucket = diff.plan_replace(
            {"b.zip": 1}, {"a.zip": (1, '"e"'), "b.zip": (2, '"e"')},
            lambda p: Z(prints[p]), lambda p, s, e: Z(remote_prints[p]))
        self.assertEqual((renames, new, changed, only_bucket), ([("a.zip", "b.zip")], [], [], []))


class RawContentTest(unittest.TestCase):
    """Raw files of the same size, without an md5 on both sides, are a rename only when same_bytes says so."""

    def plan(self, local, remote, same_bytes):
        return diff.plan_replace(local, remote, lambda p: ("raw", local[p], None),
                                 lambda p, size, etag: ("raw", size, None), same_bytes=same_bytes)

    def test_same_size_different_bytes_is_not_a_rename(self):
        asked = []
        renames, new, changed, only_bucket = self.plan({"Game B (USA).gba": 4096}, {"Game A (Europe).gba": (4096, '"-"')},
                                                       lambda l, r: asked.append((l, r)) or False)
        self.assertEqual((renames, new, changed, only_bucket), ([], ["Game B (USA).gba"], [], ["Game A (Europe).gba"]))
        self.assertEqual(asked, [("Game B (USA).gba", "Game A (Europe).gba")])

    def test_same_bytes_under_a_new_name_is_a_rename(self):
        renames, new, _, only_bucket = self.plan({"b.gba": 4096}, {"a.gba": (4096, '"-"')}, lambda l, r: True)
        self.assertEqual((renames, new, only_bucket), ([("a.gba", "b.gba")], [], []))

    def test_tries_the_next_file_of_the_same_size(self):
        renames, new, _, only_bucket = self.plan({"c.gba": 9}, {"a.gba": (9, '"-"'), "b.gba": (9, '"-"')},
                                                 lambda l, r: r == "b.gba")
        self.assertEqual((renames, new, only_bucket), ([("b.gba", "c.gba")], [], ["a.gba"]))

    def test_only_same_size_pairs_are_read(self):
        asked = []
        self.plan({"b.gba": 5}, {"a.gba": (6, '"-"')}, lambda l, r: asked.append((l, r)) or True)
        self.assertEqual(asked, [])

    def test_known_md5s_need_no_read(self):
        renames, _, _, _ = diff.plan_replace({"b.gba": 5}, {"a.gba": (5, '"m"')}, lambda p: ("raw", 5, None),
                                             lambda p, size, etag: ("raw", size, "m"), md5=lambda p: "m",
                                             same_bytes=lambda l, r: self.fail("read"))
        self.assertEqual(renames, [("a.gba", "b.gba")])


class SameBytesTest(unittest.TestCase):
    """diff.same_bytes compares a local file with a storage file through s3.read_range."""

    def compare(self, local, remote, folder=None):
        import tempfile
        from unittest import mock
        from sync_roms import s3
        reads = []

        def read_range(key, start, end):
            reads.append((key, start, end))
            return remote[start:end]

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(s3, "read_range", read_range), \
                mock.patch.object(s3, "read_root", lambda: folder), \
                mock.patch.object(diff, "SAMPLE_CHUNK", 4), mock.patch.object(diff, "SAMPLES", 4):
            path = os.path.join(tmp, "b.gba")
            with open(path, "wb") as f:
                f.write(local)
            return diff.same_bytes(path, "gba/a.gba", len(local)), reads

    def test_small_file_is_compared_whole(self):
        self.assertEqual(self.compare(b"A" * 14, b"A" * 14), (True, [("gba/a.gba", s, min(s + 4, 14)) for s in (0, 4, 8, 12)]))
        self.assertFalse(self.compare(b"A" * 16, b"A" * 15 + b"B")[0])

    def test_stops_at_the_first_chunk_that_differs(self):
        same, reads = self.compare(b"A" * 16, b"B" * 16)
        self.assertEqual((same, reads), (False, [("gba/a.gba", 0, 4)]))

    def test_big_file_reads_the_first_last_and_evenly_spaced_chunks(self):
        data = bytes(range(100))
        same, reads = self.compare(data, data)
        self.assertTrue(same)
        self.assertEqual([(s, e) for _, s, e in reads], [(0, 4), (32, 36), (64, 68), (96, 100)])

    def test_big_file_differing_in_a_chunk(self):
        data = bytes(range(100))
        self.assertFalse(self.compare(data, data[:33] + b"x" + data[34:])[0])
        self.assertFalse(self.compare(data, data[:99] + b"x")[0])

    def test_big_file_in_a_folder_is_compared_whole(self):
        data = bytes(range(100))
        same, reads = self.compare(data, data, folder="/storage")
        self.assertTrue(same)
        self.assertEqual([(s, e) for _, s, e in reads], [(s, s + 4) for s in range(0, 100, 4)])
        self.assertFalse(self.compare(data, data[:10] + b"x" + data[11:], folder="/storage")[0])  # between the samples

    def test_sampled_only_for_a_big_file_in_a_bucket(self):
        from unittest import mock
        from sync_roms import s3
        with mock.patch.object(diff, "SAMPLE_CHUNK", 4), mock.patch.object(diff, "SAMPLES", 4):
            with mock.patch.object(s3, "read_root", lambda: None):
                self.assertEqual((diff.sampled(16), diff.sampled(17)), (False, True))
            with mock.patch.object(s3, "read_root", lambda: "/storage"):
                self.assertFalse(diff.sampled(17))


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

        only_local, only_bucket = diff.plan_diff(local, remote, local_print, lambda p, size, etag: prints[p])
        self.assertEqual(only_local, ["only local.zip"])
        self.assertEqual(only_bucket, ["only bucket.zip"])
        self.assertNotIn("same.zip", calls)

    def test_same_path_different_size_but_same_content(self):
        fp = ("zip", ((1, 1),))
        self.assertEqual(diff.plan_diff({"a.zip": 5}, {"a.zip": (6, '"x"')}, lambda p: fp, lambda p, s, e: fp), ([], []))

    def test_local_raw_files_are_hashed_only_when_storage_has_a_md5_of_that_size(self):
        local = {"a.bin": 5, "b.bin": 6, "c.bin": 7}
        remote = {"x.bin": (5, '"m"'), "y.bin": (6, '"-"'), "z.bin": (7, '"m"')}
        remote_prints = {"x.bin": ("raw", 5, "m"), "y.bin": ("raw", 6, None), "z.bin": ("raw", 7, "other")}
        hashed = []

        def md5(p):
            hashed.append(p)
            return "m"

        matched, only_local, only_bucket = diff.match_content(
            local, remote, lambda p: ("raw", local[p], None), lambda p, s, e: remote_prints[p], md5=md5)
        self.assertEqual(sorted(hashed), ["a.bin", "c.bin"])
        self.assertEqual(sorted(matched), [("a.bin", "x.bin"), ("b.bin", "y.bin")])
        self.assertEqual((only_local, only_bucket), (["c.bin"], ["z.bin"]))

    def test_same_path_is_matched_before_another_file_with_the_same_print(self):
        fp = ("zip", ((1, 1),))
        matched, _, _ = diff.match_content({"b.zip": 1, "a.zip": 2}, {"a.zip": (3, '"e"'), "b.zip": (4, '"e"')},
                                           lambda p: fp, lambda p, s, e: fp)
        self.assertEqual(sorted(matched), [("a.zip", "a.zip"), ("b.zip", "b.zip")])

    def test_raw_files_compare_md5_when_known(self):
        self.assertTrue(diff.same_content(("raw", 5, "x"), ("raw", 5, None)))
        self.assertFalse(diff.same_content(("raw", 5, "x"), ("raw", 5, "y")))
        self.assertFalse(diff.same_content(("raw", 5, "x"), ("raw", 6, "x")))
        self.assertFalse(diff.same_content(("raw", 5, "x"), ("zip", ())))


if __name__ == "__main__":
    unittest.main()


class IgnoredDiffTest(unittest.TestCase):
    def test_ignored_local_rom_is_not_only_local(self):
        import argparse
        import contextlib
        import io
        import tempfile
        from unittest import mock
        from sync_roms import diff, ignore, inventory, picker, store
        with tempfile.TemporaryDirectory() as root:
            for name in ("a.gba", "b.gba"):
                with open(os.path.join(root, name), "wb") as f:
                    f.write(b"x")
            out = io.StringIO()
            with mock.patch.object(ignore, "_keys", frozenset({"gba/b.gba"})), \
                    mock.patch.object(store, "load_manifest", lambda *a: {"systems": [{"name": "GBA", "bucket": "gba", "folders": {}}]}), \
                    mock.patch.object(picker, "filter_list", lambda *a, **k: 0), \
                    mock.patch.object(inventory, "etags", lambda prefix: {}), contextlib.redirect_stdout(out):
                diff.diff_command(argparse.Namespace(diff=root, system=None, json=False))
        self.assertIn("a.gba", out.getvalue())
        self.assertNotIn("b.gba", out.getvalue())
