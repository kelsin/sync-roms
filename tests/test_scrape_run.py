import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import runtime, s3, scrape_online, scrape_plan, scrape_state, screenscraper, store, ui, upload, usersettings  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba", "screenscraper": 12, "full_system": True, "folders": {}}
NES = {"name": "NES", "bucket": "nes", "screenscraper": 3, "full_system": True, "folders": {}}
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 8
CREDS = {"screenscraper_user": "me", "screenscraper_password": "hunter2",
         "screenscraper_devid": "dev", "screenscraper_devpassword": "devpw"}


def game(gid, name, media=("box-2D", "ss")):
    return {"id": gid, "noms": [{"region": "wor", "text": name}],
            "medias": [{"type": t, "region": "wor", "url": f"http://media/{gid}/{t}"} for t in media]}


class FakeClient:
    def __init__(self, games, quota_at=None, fail_urls=(), errors=None):
        self.games = games  # ROM file name -> game dict
        self.quota_at = quota_at  # ROM file name whose lookup hits the daily quota
        self.fail_urls = set(fail_urls)
        self.errors = errors or {}  # ROM file name -> list of exceptions raised by its lookups, in order
        self.lookups, self.downloads, self.games_asked = [], [], []

    def quota(self):
        return screenscraper.Quota(2, 0, 1000)

    def lookup(self, system_id, rom_name, size, md5=None, sha1=None, crc=None):
        self.lookups.append(rom_name)
        if rom_name == self.quota_at:
            raise screenscraper.QuotaExceeded("quota")
        if self.errors.get(rom_name):
            raise self.errors[rom_name].pop(0)
        if rom_name not in self.games:
            raise screenscraper.NotFound("not found")
        return self.games[rom_name]

    def game(self, game_id):
        self.games_asked.append(game_id)
        for g in self.games.values():
            if g["id"] == game_id:
                return g
        raise screenscraper.NotFound("not found")

    def download(self, url, dest):
        self.downloads.append(url)
        if url in self.fail_urls:
            raise screenscraper.ApiError("ScreenScraper request failed (HTTP 500)")
        with open(dest, "wb") as f:
            f.write(PNG)


class RunBase(unittest.TestCase):
    systems = [GBA]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "storage")
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        self.client = FakeClient({"a.zip": game(1, "Alpha"), "b.zip": game(2, "Beta"), "c.zip": game(3, "Gamma"),
                                  "d.zip": game(4, "Delta")})
        self.settings = dict(CREDS)
        self.confirm = mock.Mock(return_value=True)
        self.out = io.StringIO()
        self.err = io.StringIO()
        for p in (mock.patch.object(runtime, "ROOT", self.root), mock.patch.object(runtime, "_mirror_root", None),
                  mock.patch.object(store, "data_dir", return_value=self.data),
                  mock.patch.object(store, "load_manifest", side_effect=lambda *a: {"systems": self.systems}),
                  mock.patch.object(usersettings, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(screenscraper, "Client", side_effect=lambda *a, **k: self.client),
                  mock.patch.object(ui, "confirm", self.confirm),
                  mock.patch.object(scrape_plan, "can_shrink", return_value=True),
                  mock.patch.object(scrape_plan, "shrink_png", side_effect=lambda src, dst, box=None: shutil.copyfile(src, dst)),
                  mock.patch.object(scrape_online, "RETRY_WAIT", 0)):
            p.start()
            self.addCleanup(p.stop)

    def put(self, key, data=b"abc"):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def run_scrape(self, **kw):
        args = SimpleNamespace(**{"system": None, "retry": False, "skip_media": [], "dry_run": False, **kw})
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            return scrape_online.scrape_command(args)

    def metadata(self, system="gba"):
        path = os.path.join(self.root, "scrapes", system, "metadata.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def stored(self, prefix="scrapes/"):
        return set(s3.list_sizes(prefix))


class ScrapeRunTest(RunBase):
    def test_dry_run_writes_nothing(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.assertEqual(self.run_scrape(dry_run=True), 0)
        self.assertEqual(self.stored(), set())
        self.assertEqual(self.client.lookups, [])
        self.confirm.assert_not_called()
        self.assertIn("a.zip", self.out.getvalue())
        self.assertIn("2 to scrape", self.out.getvalue())

    def test_media_uploaded_before_metadata_entry(self):
        self.put("gba/a.zip")
        order = []
        real_put = s3.put_text

        def put_text(key, text):
            order.append(("metadata", key, set(s3.list_sizes("scrapes/gba/covers/"))))
            return real_put(key, text)
        with mock.patch.object(upload, "run_uploads", wraps=upload.run_uploads) as ru, \
                mock.patch.object(s3, "put_text", side_effect=put_text):
            ru.side_effect = lambda todo: order.append(("media", sorted(j[0] for j in todo))) or upload.run_copies(todo)
            self.assertEqual(self.run_scrape(), 0)
        self.assertEqual([o[0] for o in order], ["media", "metadata"])
        self.assertIn("scrapes/gba/covers/a.png", order[0][1])
        self.assertEqual(order[1][2], {"scrapes/gba/covers/a.png"})
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})
        self.assertIn("scrapes/gba/screenshots/a.png", self.stored())
        self.confirm.assert_called_once()

    def test_existing_metadata_entries_preserved_and_rerun_is_noop(self):
        self.put("gba/old.zip")
        self.put("gba/a.zip")
        self.put("scrapes/gba/metadata.json", json.dumps({"old.zip": {"name": "Old", "desc": "kept"}}).encode())
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.metadata(), {"old.zip": {"name": "Old", "desc": "kept"}, "a.zip": {"name": "Alpha"}})
        self.assertEqual(self.client.lookups, ["a.zip"])
        before = self.metadata()
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.client.lookups, ["a.zip"])
        self.assertEqual(self.confirm.call_count, 1)
        self.assertEqual(self.metadata(), before)

    def test_metadata_reread_before_each_batch_write(self):
        self.put("gba/a.zip")
        real_run = upload.run_copies

        def run_copies(todo):  # someone else writes metadata.json while the batch uploads
            s3.put_text("scrapes/gba/metadata.json", json.dumps({"other.zip": {"name": "Other"}}))
            return real_run(todo)
        with mock.patch.object(upload, "run_copies", side_effect=run_copies):
            self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(set(self.metadata()), {"a.zip", "other.zip"})

    def test_quota_exceeded_stops_cleanly_and_keeps_finished_roms(self):
        for r in ("a.zip", "b.zip", "c.zip", "d.zip", "e.zip", "f.zip"):
            self.put(f"gba/{r}")
        self.client.quota_at = "c.zip"
        with mock.patch.object(scrape_online, "BATCH", 2):
            self.assertEqual(self.run_scrape(), 1)
        self.assertLessEqual({"a.zip", "b.zip"}, set(self.metadata()))  # d.zip was in flight and may finish too
        self.assertNotIn("c.zip", self.metadata())
        self.assertNotIn("e.zip", self.client.lookups)
        self.assertNotIn("f.zip", self.client.lookups)
        self.assertFalse(scrape_state.is_unknown("gba", "c.zip"))
        self.assertIn("quota", self.out.getvalue().lower())
        self.assertIn("again", self.out.getvalue().lower())

    def test_not_found_marks_unknown_and_writes_nothing_for_it(self):
        self.put("gba/a.zip")
        self.put("gba/zzz.zip")
        self.assertEqual(self.run_scrape(), 0)
        self.assertTrue(scrape_state.is_unknown("gba", "zzz.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertEqual(set(self.metadata()), {"a.zip"})
        self.assertFalse(any("/zzz." in k for k in self.stored()))
        self.assertIn("zzz.zip", self.out.getvalue())
        self.client.lookups.clear()
        self.run_scrape()
        self.assertEqual(self.client.lookups, [])
        self.run_scrape(retry=True)
        self.assertEqual(self.client.lookups, ["zzz.zip"])

    def test_skip_media_type_not_downloaded(self):
        self.put("gba/a.zip")
        self.assertEqual(self.run_scrape(skip_media=["screenshots"]), 0)
        self.assertNotIn("http://media/1/ss", self.client.downloads)
        self.assertIn("http://media/1/box-2D", self.client.downloads)
        self.assertFalse(any("/screenshots/" in k for k in self.stored()))
        self.assertEqual(set(self.metadata()), {"a.zip"})

    def test_failed_media_download_leaves_no_metadata_entry(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.client.fail_urls = {"http://media/1/ss"}
        self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(set(self.metadata()), {"b.zip"})
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertIn("a.zip", self.out.getvalue())

    def test_missing_media_type_is_not_a_failure(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D",))
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(set(self.metadata()), {"a.zip"})

    def test_network_errors_skip_only_that_rom(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.put("gba/c.zip")
        self.client.errors = {"a.zip": [ValueError("unknown url type")],
                              "b.zip": [screenscraper.ApiError("ScreenScraper request failed (HTTP 500)")]}
        self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(set(self.metadata()), {"c.zip"})
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "b.zip"))

    def test_rate_limit_is_retried(self):
        self.put("gba/a.zip")
        self.client.errors = {"a.zip": [screenscraper.RateLimited("429"), screenscraper.RateLimited("429")]}
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.client.lookups, ["a.zip"] * 3)
        self.assertEqual(set(self.metadata()), {"a.zip"})

    def test_lookup_result_reused_not_fetched_again(self):
        self.put("gba/a.zip")
        self.run_scrape()
        self.assertEqual(self.client.games_asked, [])

    def test_cancel_writes_nothing(self):
        self.put("gba/a.zip")
        self.confirm.return_value = False
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.client.lookups, [])
        self.assertEqual(self.stored(), set())

    def test_credentials_missing_fails_with_how_to_set_them(self):
        self.put("gba/a.zip")
        self.settings = {"screenscraper_user": "me", "screenscraper_password": "hunter2"}
        with self.assertRaises(SystemExit) as cm:
            self.run_scrape()
        self.assertEqual(cm.exception.code, 3)
        err = self.err.getvalue()
        self.assertIn("screenscraper_devid", err)
        self.assertIn("scrape --set-credentials", err)
        self.assertNotIn("hunter2", err + self.out.getvalue())
        self.assertEqual(self.stored(), set())


class SystemsTest(RunBase):
    systems = [GBA, NES, {"name": "No Id", "bucket": "noid", "full_system": True, "folders": {}}]

    def test_onion_and_slot_jobs_created_for_art(self):
        self.put("gba/a.zip")
        self.put("gba/sub/b.zip")
        self.put("nes/c.zip")
        self.assertEqual(self.run_scrape(), 0)
        have = self.stored()
        self.assertIn("scrapes/gba/onion/a.png", have)
        self.assertIn("scrapes/gba/slot/a.png", have)
        self.assertIn("scrapes/gba/slot/sub/b.png", have)
        self.assertNotIn("scrapes/gba/onion/sub/b.png", have)
        self.assertIn("scrapes/nes/onion/c.png", have)
        self.assertFalse(any(k.startswith("scrapes/nes/slot/") for k in have))

    def test_no_derived_art_without_shrink_tool(self):
        self.put("gba/a.zip")
        with mock.patch.object(scrape_plan, "can_shrink", return_value=False):
            self.assertEqual(self.run_scrape(), 0)
        have = self.stored()
        self.assertFalse(any("/onion/" in k or "/slot/" in k for k in have))
        self.assertIn("Pillow", self.out.getvalue())
        self.assertEqual(set(self.metadata()), {"a.zip"})

    def test_system_without_screenscraper_id_is_skipped_with_warning(self):
        self.put("noid/x.zip")
        self.put("gba/a.zip")
        self.assertEqual(self.run_scrape(), 0)
        self.assertNotIn("x.zip", self.client.lookups)
        self.assertIn("noid", self.out.getvalue())
        self.assertEqual(self.metadata("noid"), {})

    def test_system_filter(self):
        self.put("gba/a.zip")
        self.put("nes/c.zip")
        self.assertEqual(self.run_scrape(system="nes"), 0)
        self.assertEqual(self.client.lookups, ["c.zip"])

    def test_unknown_system_fails(self):
        with self.assertRaises(SystemExit):
            self.run_scrape(system="nope")


class MatchCommandTest(RunBase):
    def run_match(self, system="gba", rom="a.zip", game_q="7"):
        args = SimpleNamespace(system=system, rom=rom, game=game_q, skip_media=[], dry_run=False)
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            return scrape_online.match_command(args)

    def test_saves_match_and_scrapes_that_rom(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.client.games["x"] = game(7, "Seven")
        self.assertEqual(self.run_match(), 0)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 7)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Seven"}})
        self.assertEqual(self.client.lookups, [])
        self.assertEqual(self.client.games_asked, [7])

    def test_unknown_rom_fails(self):
        with self.assertRaises(SystemExit):
            self.run_match(rom="missing.zip")
        self.assertIsNone(scrape_state.manual_match("gba", "missing.zip"))


class ReportTest(unittest.TestCase):
    def test_counts_and_unmatched(self):
        text = scrape_online.report({"gba": ["a.zip", "b.zip", "c.zip", "d.zip"]},
                                    {"gba": {"a.zip": "hash", "b.zip": "name+size", "c.zip": "manual", "d.zip": None}})
        self.assertIn("gba: 4 to scrape", text)
        self.assertIn("1 by hash", text)
        self.assertIn("1 by name+size", text)
        self.assertIn("1 manual", text)
        self.assertIn("d.zip", text)


if __name__ == "__main__":
    unittest.main()
