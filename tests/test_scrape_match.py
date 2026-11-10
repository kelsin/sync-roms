import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import commands, runtime, s3, scrape_online, scrape_state, screenscraper, store  # noqa: E402

SYSTEM = {"bucket": "gba", "screenscraper": 12}


class FakeClient:
    def __init__(self, found=True, hash_hit=True):
        self.calls = []
        self.found = found
        self.hash_hit = hash_hit  # the response's matched ROM carries the hashes sent

    def lookup(self, system_id, rom_name, size, md5=None, sha1=None, crc=None):
        self.calls.append(dict(system_id=system_id, rom_name=rom_name, size=size, md5=md5, sha1=sha1, crc=crc))
        if not self.found:
            raise screenscraper.NotFound("not found")
        if self.hash_hit:
            return {"id": 77, "rom": {"rommd5": md5 or "", "romsha1": sha1 or "", "romcrc": crc or ""}}
        return {"id": 77, "rom": {"rommd5": "0" * 32}}


class MatchBase(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "storage")
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        for p in (mock.patch.object(runtime, "ROOT", self.root), mock.patch.object(runtime, "_mirror_root", None),
                  mock.patch.object(store, "data_dir", return_value=self.data)):
            p.start()
            self.addCleanup(p.stop)

    def put(self, key, data=b"abc"):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path


class CandidatesTest(MatchBase):
    def test_candidates_exclude_rom_with_metadata(self):
        roms = {"gba": {"a.zip", "b.zip"}}
        out = scrape_online.find_candidates([SYSTEM], roms, {"gba": {"a.zip": {"name": "A"}}})
        self.assertEqual(out, {"gba": ["b.zip"]})

    def test_candidates_skip_unknown_unless_retry(self):
        scrape_state.mark_unknown("gba", "b.zip")
        roms = {"gba": {"a.zip", "b.zip"}}
        self.assertEqual(scrape_online.find_candidates([SYSTEM], roms, {})["gba"], ["a.zip"])
        self.assertEqual(scrape_online.find_candidates([SYSTEM], roms, {}, retry=True)["gba"], ["a.zip", "b.zip"])

    def test_subfolder_rom_key_kept(self):
        roms = {"gba": {"Disc 1/a.cue", "z.zip"}}
        out = scrape_online.find_candidates([SYSTEM], roms, {"gba": {"Disc 1/a.cue": {}}})
        self.assertEqual(out["gba"], ["z.zip"])
        out = scrape_online.find_candidates([SYSTEM], roms, {})
        self.assertEqual(out["gba"], ["Disc 1/a.cue", "z.zip"])

    def test_fill_media_adds_rom_with_metadata_missing_wanted_media(self):
        roms = {"gba": {"a.zip", "b.zip", "c.zip"}}
        meta = {"gba": {"a.zip": {}, "b.zip": {}, "c.zip": {}}}
        wanted = {"covers", "screenshots"}
        listing = {"gba": {"scrapes/gba/covers/a.png": 1, "scrapes/gba/screenshots/a.png": 1,
                           "scrapes/gba/covers/b.png": 1}}
        out = scrape_online.find_candidates([SYSTEM], roms, meta, fill=(wanted, listing))
        self.assertEqual(out["gba"], ["b.zip", "c.zip"])  # a has everything wanted
        out = scrape_online.find_candidates([SYSTEM], roms, meta, fill=({"covers"}, listing))
        self.assertEqual(out["gba"], ["c.zip"])  # skipped types aren't wanted

    def test_fill_media_still_skips_unknown(self):
        scrape_state.mark_unknown("gba", "b.zip")
        out = scrape_online.find_candidates([SYSTEM], {"gba": {"b.zip"}}, {"gba": {"b.zip": {}}},
                                            fill=({"covers"}, {"gba": {}}))
        self.assertEqual(out["gba"], [])


class HashAndMatchTest(MatchBase):
    def test_folder_backend_hashes_file_and_caches(self):
        self.put("gba/a.zip", b"abc")
        h = scrape_online.hash_file("gba", "a.zip", 3, 5)
        self.assertEqual(h, {"md5": "900150983cd24fb0d6963f7d28e17f72",
                             "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d", "crc": "352441C2"})
        with mock.patch.object(s3, "read_range", side_effect=AssertionError("read again")):
            self.assertEqual(scrape_online.hash_file("gba", "a.zip", 3, 5), h)

    def test_hashing_stops_between_chunks(self):
        self.put("gba/a.zip", b"abcdef")
        stop = scrape_online.threading.Event()
        real = s3.read_range
        with mock.patch.object(scrape_online, "CHUNK", 2), \
                mock.patch.object(s3, "read_range", side_effect=lambda *a: stop.set() or real(*a)) as rr:
            with self.assertRaises(screenscraper.Stopped):
                scrape_online.hash_file("gba", "a.zip", 6, 5, stop)
        self.assertEqual(rr.call_count, 1)
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 6, 5))

    def test_hash_reads_in_chunks(self):
        self.put("gba/a.zip", b"abc")
        with mock.patch.object(scrape_online, "CHUNK", 2), mock.patch.object(s3, "read_range", wraps=s3.read_range) as rr:
            scrape_online.hash_file("gba", "a.zip", 3, 5)
        self.assertEqual([c.args for c in rr.call_args_list], [("gba/a.zip", 0, 2), ("gba/a.zip", 2, 3)])

    def test_s3_uses_etag_md5_only_when_single_part(self):
        client = FakeClient()
        with mock.patch.object(runtime, "ROOT", None), mock.patch.object(s3, "read_root", return_value=None):
            self.assertEqual(scrape_online.match(client, SYSTEM, "a.zip", 3, '"900150983cd24fb0d6963f7d28e17f72"'), (77, "hash"))
        self.assertEqual(client.calls[0]["md5"], "900150983cd24fb0d6963f7d28e17f72")

    def test_hashes_sent_but_not_matched_is_name_size(self):
        client = FakeClient(hash_hit=False)
        with mock.patch.object(s3, "read_root", return_value=None):
            self.assertEqual(scrape_online.match(client, SYSTEM, "a.zip", 3, '"900150983cd24fb0d6963f7d28e17f72"'), (77, "name+size"))
        self.assertEqual(client.calls[0]["md5"], "900150983cd24fb0d6963f7d28e17f72")
        self.put("gba/a.zip", b"abc")
        self.assertEqual(scrape_online.match(client, SYSTEM, "a.zip", 3, "5-3"), (77, "name+size"))

    def test_folder_hash_match_is_labelled_hash(self):
        self.put("gba/a.zip", b"abc")
        self.assertEqual(scrape_online.match(FakeClient(), SYSTEM, "a.zip", 3, "5-3"), (77, "hash"))

    def test_s3_multipart_etag_falls_back_to_name_size(self):
        client = FakeClient()
        with mock.patch.object(s3, "read_root", return_value=None):
            self.assertEqual(scrape_online.match(client, SYSTEM, "a.zip", 3, '"abc123-4"'), (77, "name+size"))
        self.assertIsNone(client.calls[0]["md5"])

    def test_folder_never_uses_fake_etag(self):
        self.put("gba/a.zip", b"abc")
        client = FakeClient()
        scrape_online.match(client, SYSTEM, "a.zip", 3, "5-3")
        self.assertEqual(client.calls[0]["md5"], "900150983cd24fb0d6963f7d28e17f72")
        self.assertNotEqual(client.calls[0]["md5"], "5-3")

    def test_mirror_hashes_with_real_etag_and_invalidates_on_mtime(self):
        path = self.put("gba/a.zip", b"abc")
        os.utime(path, (1000, 1000))
        client = FakeClient()
        with mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "_mirror_root", self.root):
            scrape_online.match(client, SYSTEM, "a.zip", 3, '"d41d8cd98f00b204e9800998ecf8427e"')
            self.assertEqual(client.calls[0]["md5"], "900150983cd24fb0d6963f7d28e17f72")
            with open(path, "wb") as f:
                f.write(b"xyz")
            os.utime(path, (2000, 2000))
            scrape_online.match(client, SYSTEM, "a.zip", 3, '"d41d8cd98f00b204e9800998ecf8427e"')
        self.assertNotEqual(client.calls[1]["md5"], client.calls[0]["md5"])

    def test_manual_match_wins(self):
        scrape_state.save_match("gba", "a.zip", 999)
        client = FakeClient()
        self.assertEqual(scrape_online.match(client, SYSTEM, "a.zip", 3, "5-3"), (999, "manual"))
        self.assertEqual(client.calls, [])

    def test_name_size_match_is_labelled(self):
        client = FakeClient()
        with mock.patch.object(s3, "read_root", return_value=None):
            game_id, how = scrape_online.match(client, SYSTEM, "sub/a.zip", 3, "x-1")
        self.assertEqual((game_id, how), (77, "name+size"))
        self.assertEqual(client.calls[0]["rom_name"], "a.zip")

    def test_not_found_raises(self):
        with mock.patch.object(s3, "read_root", return_value=None):
            with self.assertRaises(screenscraper.NotFound):
                scrape_online.match(FakeClient(found=False), SYSTEM, "a.zip", 3, "x-1")

    def test_s3_never_calls_read_range_for_hashing(self):
        with mock.patch.object(s3, "read_root", return_value=None), \
                mock.patch.object(s3, "read_range", side_effect=AssertionError("hashed on S3")):
            scrape_online.match(FakeClient(), SYSTEM, "a.zip", 3, '"abc-2"')


class CheckNoticeTest(RealDataDirGuard):
    def test_check_notes_systems_without_screenscraper_id_but_passes(self):
        real = store.repo_json

        def fake(name):
            data = real(name)
            if name == "systems":
                data = [{k: v for k, v in data[0].items() if k != "screenscraper"}] + data[1:]
            return data
        out = io.StringIO()
        with mock.patch.object(store, "repo_json", side_effect=fake), \
                mock.patch.object(store, "data_dir", return_value=tempfile.gettempdir() + "/nonexistent-sync-roms"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = commands.check_cmd(SimpleNamespace(bucket_keys=False))
        self.assertEqual(code, 0)
        first = real("systems")[0]["bucket"]
        self.assertIn("no ScreenScraper system id", out.getvalue())
        self.assertRegex(out.getvalue(), rf"\b{first}\b")


class ResolveManualTest(unittest.TestCase):
    def test_integer_is_game_id(self):
        self.assertEqual(scrape_online.resolve_manual(FakeClient(), SYSTEM, " 123 "), 123)

    def test_zero_is_no_game(self):
        with self.assertRaises(screenscraper.NotFound):
            scrape_online.resolve_manual(FakeClient(), SYSTEM, "0")

    def test_search_pick(self):
        client = mock.Mock()
        client.search.return_value = [(1, "One"), (2, "Two")]
        with mock.patch("sync_roms.ui.ask", return_value="2"), mock.patch("builtins.print"):
            self.assertEqual(scrape_online.resolve_manual(client, SYSTEM, "two"), 2)
        client.search.assert_called_once_with(12, "two")


class SystemIdTest(unittest.TestCase):
    def test_shipped_ids_are_integers(self):
        with open(os.path.join(ROOT, "src", "sync_roms", "data", "systems.json")) as f:
            systems = json.load(f)
        ids = [s["screenscraper"] for s in systems if "screenscraper" in s]
        self.assertTrue(ids)
        self.assertTrue(all(type(i) is int for i in ids))

    def test_check_rejects_non_integer_id(self):
        real = store.repo_json

        def fake(name):
            data = real(name)
            if name == "systems":
                data = [dict(data[0], screenscraper="12")] + data[1:]
            return data
        with mock.patch.object(store, "repo_json", side_effect=fake), \
                mock.patch.object(store, "data_dir", return_value=tempfile.gettempdir() + "/nonexistent-sync-roms"):
            self.assertTrue(any("screenscraper must be an integer" in p for p in commands.check_data()))


if __name__ == "__main__":
    unittest.main()
