import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402
from sync_roms import s3, scrape_online, scrape_plan, scrape_state, screenscraper, store, ui, upload, usersettings  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba", "screenscraper": 12, "full_system": True, "folders": {}}
NES = {"name": "NES", "bucket": "nes", "screenscraper": 3, "full_system": True, "folders": {}}
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 8
CREDS = {"screenscraper_user": "me", "screenscraper_password": "hunter2"}


def game(gid, name, media=("box-2D", "ss")):
    return {"id": gid, "noms": [{"region": "wor", "text": name}],
            "medias": [{"type": t, "region": "wor", "url": f"http://media/{gid}/{t}"} for t in media]}


class FakeClient:
    def __init__(self, games, quota_at=None, fail_urls=(), errors=None):
        self.games = games  # ROM file name -> game dict
        self.quota_at = quota_at  # ROM file name whose lookup hits the daily quota
        self.fail_urls = set(fail_urls)
        self.errors = errors or {}  # ROM file name -> list of exceptions raised by its lookups, in order
        self.download_errors = {}  # URL -> exception its download raises
        self.quota_errors = []
        self.threads = 2
        self.lookups, self.downloads, self.games_asked, self.quota_calls = [], [], [], 0

    def quota(self):
        self.quota_calls += 1
        if self.quota_errors:
            raise self.quota_errors.pop(0)
        return screenscraper.Quota(self.threads, 0, 1000)

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

    def download(self, url, dest, limit=None, stop=None):
        self.downloads.append(url)
        if url in self.fail_urls:
            raise screenscraper.ApiError("ScreenScraper request failed (HTTP 500)")
        if url in self.download_errors:
            raise self.download_errors[url]
        with open(dest, "wb") as f:
            f.write(PNG)


class RunBase(StorageDir):
    systems = [GBA]

    def setUp(self):
        super().setUp()
        self.client = FakeClient({"a.zip": game(1, "Alpha"), "b.zip": game(2, "Beta"), "c.zip": game(3, "Gamma"),
                                  "d.zip": game(4, "Delta")})
        self.settings = dict(CREDS)
        self.confirm = mock.Mock(return_value=True)
        self.out = io.StringIO()
        self.err = io.StringIO()
        for p in (mock.patch.object(store, "load_manifest", side_effect=lambda *a: {"systems": self.systems}),
                  mock.patch.object(usersettings, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(screenscraper, "Client", side_effect=lambda *a, **k: self.client),
                  mock.patch.object(ui, "confirm", self.confirm),
                  mock.patch.object(scrape_plan, "can_shrink", return_value=True),
                  mock.patch.object(scrape_plan, "shrink_png", side_effect=lambda src, dst, box=None: shutil.copyfile(src, dst)),
                  mock.patch.object(scrape_online, "RETRY_WAIT", 0)):
            p.start()
            self.addCleanup(p.stop)
        threads = set(threading.enumerate())
        self.addCleanup(self.join_threads, threads)  # runs before the patches stop

    def join_threads(self, before):
        """No worker thread may outlive the test (it would run unpatched)."""
        for t in set(threading.enumerate()) - before:
            t.join(5)
            self.assertFalse(t.is_alive(), f"thread {t.name} outlived the test")

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
        self.settings = {"screenscraper_user": "me"}
        with self.assertRaises(SystemExit) as cm:
            self.run_scrape()
        self.assertEqual(cm.exception.code, 3)
        err = self.err.getvalue()
        self.assertIn("screenscraper_password", err)
        self.assertIn("scrape --set-credentials", err)
        self.assertNotIn("hunter2", err + self.out.getvalue())
        self.assertEqual(self.stored(), set())


class FixRoundOneTest(RunBase):
    def test_unknown_error_text_never_printed(self):
        self.put("gba/a.zip")
        url = "http://media/1/ss?ssid=me&sspassword=hunter2&devpassword=devpw"
        self.client.games["a.zip"]["medias"][1]["url"] = url
        self.client.download_errors[url] = ValueError("bad URL " + url)
        self.assertEqual(self.run_scrape(), 1)
        printed = self.out.getvalue() + self.err.getvalue()
        self.assertIn("a.zip", printed)
        self.assertIn("ValueError", printed)
        self.assertNotIn("hunter2", printed)
        self.assertNotIn("devpw", printed)
        self.assertEqual(self.metadata(), {})

    def test_manual_match_overrides_unknown_ledger(self):
        self.put("gba/a.zip")
        scrape_state.mark_unknown("gba", "a.zip")
        self.assertEqual(self.run_scrape(dry_run=True), 0)
        self.assertIn("Nothing to scrape", self.out.getvalue())
        scrape_state.save_match("gba", "a.zip", 1)
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))

    def test_scraped_rom_leaves_unknown_ledger(self):
        self.put("gba/a.zip")
        self.put("gba/zzz.zip")
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("gba", "zzz.zip")
        self.assertEqual(self.run_scrape(retry=True), 0)
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "zzz.zip"))

    def test_failed_upload_leaves_no_metadata_entry(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        real = upload.run_copies

        def run_copies(todo):
            bad = [j for j in todo if "/a." in j[0]]
            return real([j for j in todo if j not in bad]) + len(bad)
        with mock.patch.object(upload, "run_copies", side_effect=run_copies):
            self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(set(self.metadata()), {"b.zip"})
        self.assertIn("a.zip", self.out.getvalue())

    def test_ctrl_c_stops_queued_roms(self):
        for r in "abcdef":
            self.put(f"gba/{r}.zip")
            self.client.games.setdefault(f"{r}.zip", game(ord(r), r))
        self.client.threads = 1
        self.put("scrapes/gba/metadata.json", b'{"old.zip": {"name": "Old"}}')
        self.client.errors = {"a.zip": [KeyboardInterrupt()]}
        with self.assertRaises(KeyboardInterrupt):
            self.run_scrape()
        # the one worker may have taken b.zip before the stop was set; nothing queued after it starts
        self.assertEqual(self.client.lookups[0], "a.zip")
        self.assertLessEqual(set(self.client.lookups), {"a.zip", "b.zip"})
        self.assertEqual(threading.active_count(), 1)  # the workers were joined before the error left the run
        self.assertEqual(self.metadata(), {"old.zip": {"name": "Old"}})
        self.assertFalse(any("/a." in k for k in self.stored()))

    def test_quota_call_retried_when_rate_limited(self):
        self.put("gba/a.zip")
        self.client.quota_errors = [screenscraper.RateLimited("429"), screenscraper.RateLimited("429")]
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.client.quota_calls, 3)
        self.assertEqual(set(self.metadata()), {"a.zip"})

    def test_storage_error_fails_cleanly_and_keeps_earlier_batches(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        real, calls = upload.run_copies, []

        def run_copies(todo):
            calls.append(todo)
            if len(calls) == 2:
                raise OSError("disk gone ?sspassword=hunter2")
            return real(todo)
        with mock.patch.object(scrape_online, "BATCH", 1), \
                mock.patch.object(upload, "run_copies", side_effect=run_copies), self.assertRaises(SystemExit) as cm:
            self.run_scrape()
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(set(self.metadata()), {"a.zip"})
        self.assertNotIn("hunter2", self.out.getvalue() + self.err.getvalue())


class FinalReviewTest(RunBase):
    def read(self, key):
        with open(os.path.join(self.root, key), "rb") as f:
            return f.read()

    def test_notgame_result_is_pending_and_writes_nothing(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = dict(game(1, "ZZZ(notgame):Test Cart"), id=1)
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(scrape_state.notgames()["gba/a.zip"]["name"], "Test Cart")
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertEqual(self.metadata(), {})
        self.assertEqual(self.client.downloads, [])
        self.assertEqual(self.stored(), set())

    def test_game_with_no_data_fails_and_writes_no_empty_entry(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.client.games["a.zip"] = {"id": 1}
        self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(set(self.metadata()), {"b.zip"})
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertIn("a.zip", self.out.getvalue())

    def test_existing_media_and_derived_art_kept(self):
        self.put("gba/a.zip")
        self.put("scrapes/gba/covers/a.jpg", b"old cover")
        self.put("scrapes/gba/onion/a.png", b"old onion")
        self.put("scrapes/gba/slot/a.png", b"old slot")
        self.assertEqual(self.run_scrape(), 0)
        self.assertNotIn("http://media/1/box-2D", self.client.downloads)
        self.assertIn("http://media/1/ss", self.client.downloads)
        self.assertEqual(self.read("scrapes/gba/covers/a.jpg"), b"old cover")
        self.assertEqual(self.read("scrapes/gba/onion/a.png"), b"old onion")
        self.assertEqual(self.read("scrapes/gba/slot/a.png"), b"old slot")
        self.assertNotIn("scrapes/gba/covers/a.png", self.stored())
        self.assertIn("scrapes/gba/screenshots/a.png", self.stored())
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})
        self.assertIn("3 media file(s) already there are kept", self.confirm.call_args.args[0])

    def test_derived_art_not_made_from_a_lesser_image_when_the_cover_exists(self):
        self.put("gba/a.zip")
        self.put("scrapes/gba/covers/a.png", b"old cover")
        self.assertEqual(self.run_scrape(), 0)
        self.assertFalse(any("/onion/" in k or "/slot/" in k for k in self.stored()))

    def test_bodies_that_are_not_media_are_not_stored(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D", "ss", "video", "manuel"))
        bodies = {"http://media/1/box-2D": b"<html>error</html>", "http://media/1/ss": b"NOMEDIA",
                  "http://media/1/video": PNG, "http://media/1/manuel": PNG}
        real = self.client.download

        def download(url, dest, limit=None, stop=None):
            real(url, dest)
            with open(dest, "wb") as f:
                f.write(bodies[url])
        self.client.download = download
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.stored(), {"scrapes/gba/metadata.json"})
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})

    def test_real_video_and_manual_kept(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("video", "manuel"))
        bodies = {"http://media/1/video": b"\x00\x00\x00\x18ftypmp42" + b"x" * 8, "http://media/1/manuel": b"%PDF-1.4 x"}
        self.client.download = lambda url, dest, limit=None, stop=None: open(dest, "wb").write(bodies[url])
        self.assertEqual(self.run_scrape(), 0)
        self.assertLessEqual({"scrapes/gba/videos/a.mp4", "scrapes/gba/manuals/a.pdf"}, self.stored())

    def test_stop_checked_before_each_download(self):
        self.put("gba/a.zip")
        stop = scrape_online.threading.Event()
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D", "ss", "sstitle"))
        real = self.client.download
        self.client.download = lambda url, dest, **kw: real(url, dest) or stop.set()
        with tempfile.TemporaryDirectory() as tmp:
            status, _ = scrape_online.scrape_rom(self.client, GBA, ("a.zip", 3, '"x-1"'), tmp, set(), stop)
        self.assertEqual(status, "skipped")
        self.assertEqual(len(self.client.downloads), 1)

    def test_same_stem_roms_get_their_own_temp_files(self):
        self.put("gba/Game.zip")
        self.put("gba/Game.7z")
        self.client.games["Game.zip"] = game(1, "One")
        self.client.games["Game.7z"] = game(2, "Two")
        with tempfile.TemporaryDirectory() as tmp:
            stop = scrape_online.threading.Event()
            _, (_, _, one) = scrape_online.scrape_rom(self.client, GBA, ("Game.zip", 3, '"x-1"'), tmp, set(), stop)
            _, (_, _, two) = scrape_online.scrape_rom(self.client, GBA, ("Game.7z", 3, '"x-1"'), tmp, set(), stop)
            self.assertTrue(set(one.values()).isdisjoint(two.values()))
            self.assertTrue(all(os.path.exists(p) for p in list(one.values()) + list(two.values())))


class MatchReplaceTest(RunBase):
    def run_match(self, rom="a.zip", game_q="7"):
        args = SimpleNamespace(system="gba", rom=rom, game=game_q, skip_media=[], dry_run=False)
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            return scrape_online.match_command(args)

    def test_declining_saves_no_match(self):
        self.put("gba/a.zip")
        self.client.games["x"] = game(7, "Seven")
        self.confirm.return_value = False
        self.assertEqual(self.run_match(), 0)
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertEqual(self.stored(), set())

    def test_existing_entry_is_replaced_not_merged(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.put("scrapes/gba/metadata.json", json.dumps({"a.zip": {"name": "Wrong", "desc": "wrong game"},
                                                         "b.zip": {"name": "Beta"}}).encode())
        self.put("scrapes/gba/covers/a.jpg", b"wrong cover")
        self.put("scrapes/gba/fanart/a.png", b"wrong fanart")
        self.put("scrapes/gba/covers/b.png", b"b cover")
        self.client.games["x"] = game(7, "Seven")
        self.assertEqual(self.run_match(), 0)
        self.assertIn("Replace", self.confirm.call_args.args[0])
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Seven"}, "b.zip": {"name": "Beta"}})
        have = self.stored()
        self.assertIn("scrapes/gba/covers/a.png", have)
        self.assertNotIn("scrapes/gba/covers/a.jpg", have)
        self.assertNotIn("scrapes/gba/fanart/a.png", have)
        self.assertIn("scrapes/gba/covers/b.png", have)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 7)


class RoundTwoRunTest(RunBase):
    def test_same_stem_roms_never_share_a_batch(self):
        for r in ("Game.zip", "Game.7z", "Other.zip"):
            self.put(f"gba/{r}")
            self.client.games[r] = game(len(self.client.games) + 10, r)
        batches = []
        real = scrape_online.run_batch
        with mock.patch.object(scrape_online, "run_batch",
                               side_effect=lambda s, batch, *a, **k: batches.append([r for r, _, _ in batch]) or real(s, batch, *a, **k)):
            self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(len(batches), 2)
        for b in batches:
            stems = [os.path.splitext(r)[0] for r in b]
            self.assertEqual(len(stems), len(set(stems)))
        self.assertEqual(set(self.metadata()), {"Game.zip", "Game.7z", "Other.zip"})

    def test_next_batch_is_scraped_while_the_last_one_uploads(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        seen, real = [], upload.run_copies

        def run_copies(todo):
            if not seen:  # the first upload: the pool must already be on the second batch
                for _ in range(100):
                    if "b.zip" in self.client.lookups:
                        break
                    threading.Event().wait(0.05)
                seen.append("b.zip" in self.client.lookups)
            return real(todo)
        with mock.patch.object(scrape_online, "BATCH", 1), mock.patch.object(upload, "run_copies", side_effect=run_copies):
            self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(seen, [True])
        self.assertEqual(set(self.metadata()), {"a.zip", "b.zip"})

    def test_metadata_is_written_once_for_many_batches(self):
        for r in ("a.zip", "b.zip", "c.zip", "d.zip"):
            self.put(f"gba/{r}")
        for interval, writes in ((60, 1), (0, 4)):
            with self.subTest(interval=interval), mock.patch.object(scrape_online, "BATCH", 1), \
                    mock.patch.object(scrape_online, "METADATA_INTERVAL", interval), \
                    mock.patch.object(s3, "put_text", wraps=s3.put_text) as put:
                self.assertEqual(self.run_scrape(retry=True), 0)
                self.assertEqual([c.args[0] for c in put.call_args_list].count("scrapes/gba/metadata.json"), writes)
                self.assertEqual(set(self.metadata()), {"a.zip", "b.zip", "c.zip", "d.zip"})
            os.remove(os.path.join(self.root, "scrapes", "gba", "metadata.json"))

    def test_non_object_metadata_entry_stops_that_system(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.put("scrapes/gba/metadata.json", b'{"old.zip": null}')
        with mock.patch.object(scrape_online, "BATCH", 1):
            self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(self.client.lookups, [])  # found out before any quota is spent
        self.assertEqual(self.metadata(), {"old.zip": None})
        self.assertIn("metadata.json", self.out.getvalue())

    def test_saved_match_to_a_missing_game_is_forgotten(self):
        self.put("gba/a.zip")
        scrape_state.save_match("gba", "a.zip", 999)
        self.assertEqual(self.run_scrape(), 0)
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))
        self.assertIn("999", self.out.getvalue())
        self.assertEqual(self.metadata(), {})

    def test_quota_from_the_first_quota_call(self):
        self.put("gba/a.zip")
        self.client.quota_errors = [screenscraper.QuotaExceeded("quota")]
        self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(self.client.lookups, [])
        self.assertIn("tomorrow", self.out.getvalue())

    def test_quota_from_a_download(self):
        self.put("gba/a.zip")
        self.client.download_errors["http://media/1/box-2D"] = screenscraper.QuotaExceeded("quota")
        self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(self.metadata(), {})
        self.assertIn("quota", self.out.getvalue())
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))

    def test_431_reported_as_its_own_condition(self):
        self.put("gba/a.zip")
        self.client.quota_at = None
        self.client.errors = {"a.zip": [screenscraper.TooManyUnrecognized("431")]}
        self.assertEqual(self.run_scrape(), 1)
        self.assertIn("unrecognized", self.out.getvalue())
        self.assertNotIn("daily quota", self.out.getvalue())

    def test_quota_stops_a_sibling_roms_downloads(self):
        self.put("gba/a.zip")
        self.put("gba/b.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D", "ss", "sstitle"))
        raised = threading.Event()
        downloading = threading.Event()
        events = []
        real_event = threading.Event
        real_lookup = self.client.lookup

        def lookup(system_id, rom_name, *a, **k):
            if rom_name == "b.zip":
                downloading.wait(5)  # let a.zip's download start before the quota error
                raised.set()
                raise screenscraper.QuotaExceeded("quota")
            return real_lookup(system_id, rom_name, *a, **k)
        real_download = self.client.download

        def download(url, dest, limit=None, stop=None):
            real_download(url, dest)
            downloading.set()
            raised.wait(5)
            events[0].wait(5)  # the run's stop event, set once b.zip's quota error is seen
        self.client.lookup, self.client.download = lookup, download
        with mock.patch.object(scrape_online.threading, "Event", side_effect=lambda: events.append(real_event()) or events[-1]):
            self.assertEqual(self.run_scrape(), 1)
        self.assertEqual(self.client.downloads, ["http://media/1/box-2D"])
        self.assertEqual(self.metadata(), {})

    def test_dotted_and_subfolder_rom_keys(self):
        self.put("gba/Game v1.1 (USA).zip")
        self.put("gba/Disc 1/Saga.zip")
        self.client.games["Game v1.1 (USA).zip"] = game(1, "Dotted")
        self.client.games["Saga.zip"] = game(2, "Saga")
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.metadata(), {"Game v1.1 (USA).zip": {"name": "Dotted"}, "Disc 1/Saga.zip": {"name": "Saga"}})
        have = self.stored()
        self.assertLessEqual({"scrapes/gba/covers/Game v1.1 (USA).png", "scrapes/gba/screenshots/Disc 1/Saga.png",
                              "scrapes/gba/onion/Game v1.1 (USA).png", "scrapes/gba/slot/Disc 1/Saga.png"}, have)
        self.assertNotIn("scrapes/gba/onion/Disc 1/Saga.png", have)

    def test_videos_get_the_video_size_limit(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D", "video"))
        limits = {}
        self.client.download = lambda url, dest, limit=None, stop=None: limits.update({url: limit}) or open(dest, "wb").write(PNG)
        self.run_scrape()
        self.assertEqual(limits, {"http://media/1/box-2D": None, "http://media/1/video": screenscraper.VIDEO_MAX})


class RoundThreeTest(RunBase):
    def test_refused_media_type_skipped_rom_still_recorded(self):
        self.put("gba/a.zip")
        self.client.games["a.zip"] = game(1, "Alpha", media=("box-2D", "manuel"))
        self.client.download_errors["http://media/1/manuel"] = screenscraper.MediaRefused("ScreenScraper media too large")
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Alpha"}})
        self.assertIn("scrapes/gba/covers/a.png", self.stored())
        self.assertFalse(any("/manuals/" in k for k in self.stored()))
        self.assertIn("manuals", self.out.getvalue())
        self.assertNotIn("http://media", self.out.getvalue())
        self.client.lookups.clear()
        self.assertEqual(self.run_scrape(), 0)
        self.assertEqual(self.client.lookups, [])

    def test_stopped_download_is_skipped(self):
        self.put("gba/a.zip")
        self.client.download_errors["http://media/1/box-2D"] = screenscraper.Stopped()
        with tempfile.TemporaryDirectory() as tmp:
            status, _ = scrape_online.scrape_rom(self.client, GBA, ("a.zip", 3, '"x-1"'), tmp, set(), threading.Event())
        self.assertEqual(status, "skipped")

    def test_metadata_serialising_type_error_is_not_blamed_on_an_entry(self):
        self.put("gba/a.zip")
        with mock.patch.object(s3, "put_text", side_effect=TypeError("not serialisable")), \
                self.assertRaises(TypeError):
            self.run_scrape()
        self.assertNotIn("isn't an object", self.out.getvalue())


class MatchRoundTwoTest(RunBase):
    def run_match(self, rom="a.zip", game_q="7", skip=()):
        args = SimpleNamespace(system="gba", rom=rom, game=game_q, skip_media=list(skip), dry_run=False)
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            return scrape_online.match_command(args)

    def existing(self):
        self.put("gba/a.zip")
        self.put("scrapes/gba/metadata.json", json.dumps({"a.zip": {"name": "Wrong", "desc": "old"}}).encode())
        for key in ("covers/a.png", "fanart/a.png", "custom/a.png", "onion/a.png", "slot/a.png"):
            self.put(f"scrapes/gba/{key}", b"old " + key.encode())
        self.client.games["x"] = game(7, "Seven")

    def read(self, key):
        with open(os.path.join(self.root, key), "rb") as f:
            return f.read()

    def test_replace_keeps_custom_and_overwrites_onion_and_slot(self):
        self.existing()
        self.assertEqual(self.run_match(), 0)
        have = self.stored()
        self.assertEqual(self.read("scrapes/gba/custom/a.png"), b"old custom/a.png")
        self.assertNotIn("scrapes/gba/fanart/a.png", have)
        self.assertNotEqual(self.read("scrapes/gba/onion/a.png"), b"old onion/a.png")
        self.assertNotEqual(self.read("scrapes/gba/slot/a.png"), b"old slot/a.png")
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Seven"}})

    def test_replace_leaves_skipped_types(self):
        self.existing()
        self.assertEqual(self.run_match(skip=["fanart"]), 0)
        self.assertEqual(self.read("scrapes/gba/fanart/a.png"), b"old fanart/a.png")
        self.assertIn("left as they are", self.confirm.call_args.args[0])

    def test_replace_prompt_lists_files_and_destination(self):
        self.existing()
        self.run_match()
        question = self.confirm.call_args.args[0]
        self.assertIn(f"{self.root}/scrapes/", question)
        self.assertIn("4 file(s)", question)
        self.assertIn("scrapes/gba/fanart/a.png", self.out.getvalue())
        self.assertNotIn("scrapes/gba/custom/a.png", self.out.getvalue())

    def test_match_without_entry_says_existing_media_is_kept(self):
        self.put("gba/a.zip")
        self.put("scrapes/gba/covers/a.png", b"cover")
        self.client.games["x"] = game(7, "Seven")
        self.run_match()
        self.assertIn("1 media file(s) already there are kept", self.confirm.call_args.args[0])

    def test_replace_warns_about_same_stem_roms(self):
        self.existing()
        self.put("gba/a.7z")
        self.run_match()
        self.assertIn("a.7z", self.out.getvalue())

    def test_metadata_write_failure_deletes_nothing_and_names_the_match_rerun(self):
        self.existing()
        with mock.patch.object(s3, "put_text", side_effect=OSError("disk gone")), self.assertRaises(SystemExit):
            self.run_match()
        self.assertIn("scrapes/gba/fanart/a.png", self.stored())
        self.assertIn("sync-roms scrape match gba a.zip 7", self.err.getvalue())
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))

    def test_replace_with_unknown_game_keeps_old_entry_and_media(self):
        self.existing()
        self.assertEqual(self.run_match(game_q="999"), 1)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Wrong", "desc": "old"}})
        self.assertIn("scrapes/gba/fanart/a.png", self.stored())
        self.assertIn("no game 999", self.out.getvalue() + self.err.getvalue())

    def test_replace_with_failed_scrape_keeps_old_entry_and_media(self):
        self.existing()
        self.client.fail_urls = {"http://media/7/ss"}
        self.assertEqual(self.run_match(), 1)
        self.assertEqual(self.metadata(), {"a.zip": {"name": "Wrong", "desc": "old"}})
        self.assertEqual(self.read("scrapes/gba/fanart/a.png"), b"old fanart/a.png")
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertIn("sync-roms scrape match gba a.zip 7", self.out.getvalue())

    def test_unknown_game_id_is_not_saved_or_retried(self):
        self.put("gba/a.zip")
        self.assertEqual(self.run_match(game_q="999"), 1)
        self.assertNotIn("Done!", self.out.getvalue())
        self.assertIn("1 failure", self.out.getvalue())
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertIn("ScreenScraper has no game 999", self.out.getvalue() + self.err.getvalue())

    def test_forced_notgame_is_a_failure_with_its_own_message(self):
        self.put("gba/a.zip")
        self.client.games["x"] = dict(game(8, screenscraper.NOTGAME), id=8)
        self.assertEqual(self.run_match(game_q="8"), 1)
        out = self.out.getvalue()
        self.assertIn("8 is not a playable game", out)
        self.assertNotIn("has no game 8", out)
        self.assertNotIn("Done!", out)
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))

    def test_quota_while_searching_is_guided(self):
        self.put("gba/a.zip")
        self.client.search = mock.Mock(side_effect=screenscraper.QuotaExceeded("quota"))
        self.assertEqual(self.run_match(game_q="Some Name"), 1)
        self.assertIn("tomorrow", self.out.getvalue())


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
