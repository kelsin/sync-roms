import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

from sync_roms import bbs, ignore, store, ui, usersettings  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "bbs-featured.html")


def cart(file, post="1"):
    return {"post": post, "title": file, "author": "a", "file": file}


class ParsePage(unittest.TestCase):
    def test_first_row_and_order(self):
        with open(FIXTURE, encoding="utf-8") as f:
            carts = bbs.parse_page(f.read())
        self.assertEqual(len(carts), 30)
        self.assertEqual(carts[0], {"post": "165759", "title": "Mole Mole",
                                    "author": "Adam Atomic", "file": "molemole-1.p8.png"})
        self.assertEqual(carts[1]["file"], "death_of_kairos-0.p8.png")
        self.assertEqual(carts[1]["author"], "voidgazerBon")

    def test_no_rows(self):
        self.assertEqual(bbs.parse_page("<html>pdat=[\n\t];\n</html>"), [])
        self.assertEqual(bbs.parse_page("<html></html>"), [])

    def test_quote_styles_and_empty_slots(self):
        html = ("pdat=[\n['9', 2, \"Say `hi`\",'/bbs/thumbs/pico8_x-2.png',,[\"a\",],"
                "'it\\'s',\"Au\\\"thor\",`b`],\n];")
        row = bbs.parse_page(html)
        self.assertEqual(row[0]["title"], "Say `hi`")
        self.assertEqual(row[0]["file"], "x-2.p8.png")


class Urls(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(bbs.page_url(1), bbs.LISTING)
        self.assertEqual(bbs.page_url(2), bbs.LISTING + "&page=2")
        self.assertEqual(bbs.cart_url("molemole-1.p8.png"),
                         "https://www.lexaloffle.com/bbs/cposts/mo/molemole-1.p8.png")


class Identity(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(bbs.identity("molemole-1.p8.png"), ("molemole", 1))
        self.assertEqual(bbs.identity("pico8tetris.p8.png"), ("pico8tetris", 0))
        self.assertEqual(bbs.identity("2048-3.p8.png"), ("2048", 3))


class Classify(unittest.TestCase):
    def test_new(self):
        new, up = bbs.classify([cart("a-0.p8.png")], set(), set())
        self.assertEqual([c["file"] for c in new], ["a-0.p8.png"])
        self.assertEqual(up, [])

    def test_upgrade(self):
        c = cart("molemole-2.p8.png")
        new, up = bbs.classify([c], {"pico8/molemole-1.p8.png"}, set())
        self.assertEqual(new, [])
        self.assertEqual(up, [("pico8/molemole-1.p8.png", c)])

    def test_same_and_older_skipped(self):
        keys = {"pico8/a-2.p8.png"}
        self.assertEqual(bbs.classify([cart("a-2.p8.png"), cart("a-1.p8.png")],
                                      keys, set()), ([], []))

    def test_ignored_skipped(self):
        self.assertEqual(bbs.classify([cart("a-5.p8.png")], set(),
                                      {"pico8/a-1.p8.png"}), ([], []))

    def test_duplicate_base_once(self):
        first, second = cart("a-1.p8.png", "1"), cart("a-2.p8.png", "2")
        new, up = bbs.classify([first, second], set(), set())
        self.assertEqual(new, [first])


OLD, NEW = "pico8/molemole-1.p8.png", "pico8/molemole-2.p8.png"


class Retarget(helpers.StorageDir):
    def write(self, *parts, data):
        path = os.path.join(self.data, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        helpers.write_json(path, data)
        return path

    def read(self, *parts):
        with open(os.path.join(self.data, *parts)) as f:
            return json.load(f)

    def test_rewrites_every_personal_file(self):
        game = {"title": "Mole Mole", "bucket": OLD, "files": [OLD, "pico8/x.p8.png"]}
        other = {"title": "Other", "bucket": "pico8/other-1.p8.png"}
        self.write("cards.json", data={"c": {"games": {"pico8": [game, other], "sets": ["a"]},
                                             "surprises": [{"system": "pico8", "bucket": OLD, "title": "Mole Mole"}]}})
        today = datetime.date.today().isoformat()
        self.write("surprises.json", data=[{"system": "pico8", "bucket": OLD, "title": "Mole Mole",
                                            "card": "c", "date": today}])
        self.write("collections", "mine.json", data={"name": "Mine", "art": "x", "games": [
            {"system": "pico8", "bucket": OLD, "title": "Mole Mole"}]})
        untouched = self.write("collections", "other.json", data={"name": "Other", "games": [
            {"system": "pico8", "bucket": "pico8/other-1.p8.png", "title": "Other"}]})
        os.utime(untouched, (1, 1))
        with mock.patch.object(store, "load_sets", return_value=[
                {"id": "s1", "games": [{"bucket": "x"}, {"bucket": "y", "files": [OLD]}]},
                {"id": "s2", "games": [{"bucket": "z"}]}]):
            self.assertEqual(bbs.retarget(OLD, NEW, "Mole Mole 2"), ["s1"])
        card = self.read("cards.json")["c"]
        self.assertEqual(card["games"]["pico8"], [
            {"title": "Mole Mole 2", "bucket": NEW, "files": [NEW, "pico8/x.p8.png"]}, other])
        self.assertEqual(card["games"]["sets"], ["a"])
        self.assertEqual(card["surprises"], [{"system": "pico8", "bucket": NEW, "title": "Mole Mole 2"}])
        hist = self.read("surprises.json")
        self.assertEqual((hist[0]["bucket"], hist[0]["title"]), (NEW, "Mole Mole 2"))
        mine = self.read("collections", "mine.json")
        self.assertEqual((mine["games"][0]["bucket"], mine["games"][0]["title"], mine["art"]), (NEW, "Mole Mole 2", "x"))
        self.assertEqual(os.stat(untouched).st_mtime, 1)

    def test_rewrites_a_cards_exclusions_without_duplicates(self):
        self.write("cards.json", data={
            "c": {"excluded": {"pico8": ["pico8/a.p8.png", OLD], "gba": ["gba/x.zip"]}},
            "d": {"excluded": {"pico8": [NEW, OLD]}}})
        with mock.patch.object(store, "load_sets", return_value=[]):
            bbs.retarget(OLD, NEW, "Mole Mole 2")
        cards = self.read("cards.json")
        self.assertEqual(cards["c"]["excluded"], {"pico8": ["pico8/a.p8.png", NEW], "gba": ["gba/x.zip"]})
        self.assertEqual(cards["d"]["excluded"], {"pico8": [NEW]})

    def test_rewrites_the_list_kept_under_a_full_system(self):
        self.write("cards.json", data={"c": {"games": {"pico8": {"full_system": True, "games": [
            {"title": "Mole Mole", "bucket": OLD}]}}}})
        with mock.patch.object(store, "load_sets", return_value=[]):
            bbs.retarget(OLD, NEW, "Mole Mole 2")
        self.assertEqual(self.read("cards.json")["c"]["games"]["pico8"], {"full_system": True, "games": [
            {"title": "Mole Mole 2", "bucket": NEW}]})

    def test_names_the_sets_whose_variants_name_the_old_cart(self):
        with mock.patch.object(store, "load_sets", return_value=[
                {"id": "s1", "games": [{"bucket": "x", "variants": [{"bucket": "y", "note": "n"}]}]},
                {"id": "s2", "games": [{"bucket": "z", "variants": [{"bucket": OLD, "note": "n"}]}]}]):
            self.assertEqual(bbs.retarget(OLD, NEW, "Mole Mole 2"), ["s2"])

    def test_nothing_named_writes_nothing(self):
        path = self.write("cards.json", data={"c": {"games": {"pico8": [{"title": "T", "bucket": "pico8/o.p8.png"}]}}})
        os.utime(path, (1, 1))
        with mock.patch.object(store, "load_sets", return_value=[]):
            self.assertEqual(bbs.retarget(OLD, NEW, "T"), [])
        self.assertEqual(os.stat(path).st_mtime, 1)


PNG = b"\x89PNG\r\n\x1a\n" + b"cart"
META = "scrapes/pico8/metadata.json"


def page(*rows):
    """A listing page whose pdat rows are (file stem, title, author)."""
    body = ",\n".join(f"['{i}', 1, `{title}`, '/bbs/thumbs/pico8_{stem}.png', 0, 0, 'd', 7, '{author}']"
                      for i, (stem, title, author) in enumerate(rows))
    return f"<html>pdat=[\n{body},\n];</html>".encode()


PAGE1 = page(("molemole-1", "Mole Mole", "Adam Atomic"), ("x-2", "X Two", "Ex"))
PAGE2 = page(("pico8tetris", "Tetris", "T"))
EMPTY = page()


class Download(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.object(usersettings, "ensure_bucket"),
                  mock.patch.object(ignore, "keys", return_value=frozenset())):
            p.start()
            self.addCleanup(p.stop)

    def serve(self, pages, carts=None, errors=()):
        """bbs._fetch serving listing pages in turn and carts by URL (PNG by default); URLs in errors raise."""
        listing = list(pages)
        fetched = []

        def fetch(url):
            fetched.append(url)
            if url in errors:
                raise urllib.error.HTTPError(url, 503, "busy", None, None)
            if url.startswith(bbs.LISTING):
                return listing.pop(0)
            return (carts or {}).get(url.rsplit("/", 1)[-1], PNG)
        return mock.patch.object(bbs, "_fetch", fetch), fetched

    def run_download(self, pages, count=None, dry_run=False, carts=None, errors=(), yes=True, answer=None):
        patch, fetched = self.serve(pages, carts, errors)
        out, err = io.StringIO(), io.StringIO()
        with patch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ui.ASSUME_YES = yes
            try:
                with mock.patch.object(ui, "_input", side_effect=answer or EOFError):
                    code = bbs.download_pico8(mock.Mock(count=count, dry_run=dry_run, yes=yes))
            finally:
                ui.ASSUME_YES = False
        return code, out.getvalue(), err.getvalue(), fetched

    def stored(self):
        found = set()
        for dp, _, fns in os.walk(self.root):
            found |= {os.path.relpath(os.path.join(dp, f), self.root) for f in fns}
        return found

    def meta(self):
        with open(os.path.join(self.root, META)) as f:
            return json.load(f)

    def test_reads_every_page_until_an_empty_one(self):
        code, out, _, fetched = self.run_download([PAGE1, PAGE2, EMPTY], dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(fetched, [bbs.page_url(1), bbs.page_url(2), bbs.page_url(3)])
        for file in ("molemole-1.p8.png", "x-2.p8.png", "pico8tetris.p8.png"):
            self.assertIn(f"new: {file}", out)

    def test_count_stops_after_that_many_carts(self):
        code, out, _, fetched = self.run_download([PAGE1, PAGE2, EMPTY], count=1)
        self.assertEqual(code, 0)
        self.assertEqual(fetched, [bbs.page_url(1), bbs.cart_url("molemole-1.p8.png")])
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", META})

    def test_confirmation_defaults_to_no(self):
        code, _, _, _ = self.run_download([PAGE1, EMPTY], yes=False)
        self.assertEqual(self.stored(), set())
        code, _, _, _ = self.run_download([PAGE1, EMPTY], yes=False, answer=["y"])
        self.assertIn("pico8/molemole-1.p8.png", self.stored())

    def test_failed_retarget_keeps_the_old_revision(self):
        self.put("pico8/x-1.p8.png")
        with mock.patch.object(bbs, "retarget", side_effect=OSError("disk full")):
            code, _, err, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual(code, 1)
        self.assertIn("disk full", err)
        self.assertEqual(self.stored(), {"pico8/x-1.p8.png", "pico8/x-2.p8.png", META})

    def test_dry_run_lists_and_writes_nothing(self):
        self.put("pico8/x-1.p8.png")
        self.put("pico8/pico8tetris.p8.png")
        code, out, _, fetched = self.run_download([PAGE1, PAGE2, EMPTY], dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("new: molemole-1.p8.png", out)
        self.assertIn("upgrade: pico8/x-1.p8.png → x-2.p8.png", out)
        self.assertNotIn("pico8tetris", out)
        self.assertEqual(self.stored(), {"pico8/x-1.p8.png", "pico8/pico8tetris.p8.png"})
        self.assertFalse(any(not u.startswith(bbs.LISTING) for u in fetched))

    def test_new_cart_uploaded_with_its_metadata(self):
        self.put(META, json.dumps({"other.p8.png": {"name": "Other", "genre": "g"}}).encode())
        code, _, _, _ = self.run_download([page(("molemole-1", "Mole Mole", "Adam Atomic")), EMPTY])
        self.assertEqual(code, 0)
        with open(os.path.join(self.root, "pico8/molemole-1.p8.png"), "rb") as f:
            self.assertEqual(f.read(), PNG)
        self.assertEqual(self.meta(), {"other.p8.png": {"name": "Other", "genre": "g"},
                                       "molemole-1.p8.png": {"name": "Mole Mole", "developer": "Adam Atomic"}})

    def test_upgrade_replaces_the_old_revision(self):
        self.put("pico8/x-1.p8.png")
        self.put("scrapes/pico8/covers/x-1.p8.png")
        self.put("scrapes/pico8/covers/x-10.p8.png")
        self.put(META, json.dumps({"x-1.p8.png": {"name": "X", "developer": "old", "genre": "g"}}).encode())
        with mock.patch.object(bbs, "retarget", return_value=["s1"]) as retarget:
            code, _, err, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual(code, 0)
        retarget.assert_called_once_with("pico8/x-1.p8.png", "pico8/x-2.p8.png", "X Two")
        self.assertIn("s1", err)
        self.assertEqual(self.stored(), {"pico8/x-2.p8.png", "scrapes/pico8/covers/x-2.p8.png",
                                         "scrapes/pico8/covers/x-10.p8.png", META})
        self.assertEqual(self.meta(), {"x-2.p8.png": {"name": "X Two", "developer": "Ex", "genre": "g"}})

    def test_upgrade_moves_the_old_revisions_files_in_any_scrapes_folder(self):
        self.put("pico8/x-1.p8.png")
        self.put("scrapes/pico8/extras/x-1.p8.png")  # not a media type
        self.put("scrapes/pico8/covers/sub/x-1.p8.jpg")
        with mock.patch.object(bbs, "retarget", return_value=[]):
            code, _, _, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual(code, 0)
        self.assertEqual(self.stored(), {"pico8/x-2.p8.png", "scrapes/pico8/extras/x-2.p8.png",
                                         "scrapes/pico8/covers/sub/x-2.p8.jpg", META})

    def test_upgrade_moves_the_manual_match_and_forgets_the_old_revisions_scrape_state(self):
        self.put("pico8/x-1.p8.png")
        hashes = {"size": 3, "mtime": 1, "hashes": {"md5": "a"}}
        state = {"matches": {"x-1.p8.png": 77, "o.p8.png": 5}, "unknown": {"x-1.p8.png": True, "o.p8.png": True},
                 "nomedia": {"x-1.p8.png": ["miximages"], "o.p8.png": ["videos"]},
                 "hashes": {"x-1.p8.png": hashes, "o.p8.png": hashes}}
        for name, data in state.items():
            self.put(f"scrapes/pico8/{name}.json", json.dumps(data).encode())
        self.put("scrapes/notgames.json", json.dumps({"pico8/x-1.p8.png": {"name": "X"}, "pico8/o.p8.png": {"name": "O"},
                                                      "kept": ["pico8/o.p8.png", "pico8/x-1.p8.png"]}).encode())
        with mock.patch.object(bbs, "retarget", return_value=[]):
            code, _, err, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual((code, err), (0, ""))

        def saved(key):
            with open(os.path.join(self.root, "scrapes", key)) as f:
                return json.load(f)
        self.assertEqual(saved("pico8/matches.json"), {"x-2.p8.png": 77, "o.p8.png": 5})
        self.assertEqual(saved("pico8/unknown.json"), {"o.p8.png": True})
        self.assertEqual(saved("pico8/nomedia.json"), {"o.p8.png": ["videos"]})
        self.assertEqual(saved("pico8/hashes.json"), {"o.p8.png": hashes})
        self.assertEqual(saved("notgames.json"), {"pico8/o.p8.png": {"name": "O"}, "kept": ["pico8/o.p8.png"]})

    def test_not_a_png_is_skipped(self):
        code, _, err, _ = self.run_download([PAGE1, EMPTY], carts={"molemole-1.p8.png": b"<html>"})
        self.assertIn("molemole-1.p8.png", err)
        self.assertEqual(self.stored(), {"pico8/x-2.p8.png", META})
        self.assertEqual(list(self.meta()), ["x-2.p8.png"])

    def test_listing_error_keeps_the_pages_read(self):
        code, out, err, _ = self.run_download([PAGE1], errors={bbs.page_url(2)})
        self.assertEqual(code, 1)
        self.assertIn("503", err)
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", "pico8/x-2.p8.png", META})

    def test_listing_error_on_page_one_fails(self):
        code, out, err, _ = self.run_download([], errors={bbs.page_url(1)})
        self.assertEqual(code, 1)
        self.assertIn("503", err)
        self.assertNotIn("every Featured", out)
        self.assertEqual(self.stored(), set())

    def test_file_name_that_isnt_a_plain_name_is_skipped(self):
        code, out, err, fetched = self.run_download([page(("../../../x", "Bad", "B"), ("a/b", "Bad", "B")), EMPTY])
        self.assertEqual(code, 0)
        self.assertIn("plain name", err)
        self.assertEqual([u for u in fetched if not u.startswith(bbs.LISTING)], [])
        self.assertEqual(self.stored(), set())
        with contextlib.redirect_stderr(io.StringIO()):
            carts = bbs.parse_page(page(("ok-1", "Ok", "O"), ("../x", "Bad", "B")).decode())
        self.assertEqual([c["file"] for c in carts], ["ok-1.p8.png"])

    def test_failed_delete_of_the_old_revision_keeps_the_new_one_whole(self):
        self.put("pico8/x-1.p8.png")
        self.put("scrapes/pico8/covers/x-1.p8.png")
        with mock.patch.object(bbs, "retarget", return_value=[]) as retarget, \
                mock.patch.object(bbs.s3, "delete_keys", side_effect=OSError("denied")):
            code, _, err, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual(code, 1)
        self.assertIn("pico8/x-1.p8.png", err)
        retarget.assert_called_once_with("pico8/x-1.p8.png", "pico8/x-2.p8.png", "X Two")
        self.assertEqual(self.meta(), {"x-2.p8.png": {"name": "X Two", "developer": "Ex"}})
        self.assertEqual(self.stored(), {"pico8/x-1.p8.png", "pico8/x-2.p8.png",
                                         "scrapes/pico8/covers/x-2.p8.png", META})

    def flaky_meta(self, failing):
        """s3.put_text failing on its failing-th call (1-based); the keys it was called with go in self.writes."""
        put_text, self.writes = bbs.s3.put_text, []

        def flaky(key, text):
            self.writes.append(key)
            if len(self.writes) == failing:
                raise OSError("disk full")
            return put_text(key, text)
        return mock.patch.object(bbs.s3, "put_text", flaky)

    def test_failed_move_of_the_manual_match_keeps_it_on_the_old_revision(self):
        self.put("pico8/x-1.p8.png")
        self.put("scrapes/pico8/matches.json", json.dumps({"x-1.p8.png": 77}).encode())
        with mock.patch.object(bbs, "retarget", return_value=[]), self.flaky_meta(2):
            _, _, err, _ = self.run_download([page(("x-2", "X Two", "Ex")), EMPTY])
        self.assertEqual(self.writes, [META, "scrapes/pico8/matches.json"])
        self.assertIn("disk full", err)
        with open(os.path.join(self.root, "scrapes/pico8/matches.json")) as f:
            self.assertEqual(json.load(f), {"x-1.p8.png": 77})

    def test_metadata_is_written_once_per_batch_and_at_the_end(self):
        for every, writes in ((25, 1), (2, 2)):
            shutil.rmtree(self.root)
            os.makedirs(self.root)
            with self.subTest(every=every), mock.patch.object(bbs, "META_EVERY", every), self.flaky_meta(0):
                code, _, _, _ = self.run_download([PAGE1, PAGE2, EMPTY])
                self.assertEqual(code, 0)
                self.assertEqual(self.writes, [META] * writes)
                self.assertEqual(sorted(self.meta()), ["molemole-1.p8.png", "pico8tetris.p8.png", "x-2.p8.png"])

    def test_failed_metadata_write_takes_the_batchs_carts_back_out(self):
        with mock.patch.object(bbs, "META_EVERY", 2), self.flaky_meta(2):
            code, _, err, _ = self.run_download([PAGE1, PAGE2, EMPTY])
        self.assertEqual(code, 1)
        self.assertIn("disk full", err)
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", "pico8/x-2.p8.png", META})
        self.assertEqual(sorted(self.meta()), ["molemole-1.p8.png", "x-2.p8.png"])

    def test_failed_metadata_write_keeps_the_old_revision_and_its_metadata(self):
        self.put("pico8/x-1.p8.png")
        self.put(META, json.dumps({"x-1.p8.png": {"name": "X", "developer": "old"}}).encode())
        with mock.patch.object(bbs, "retarget", side_effect=AssertionError("retargeted")), self.flaky_meta(1):
            code, _, err, _ = self.run_download([PAGE1, EMPTY])
        self.assertEqual(code, 1)
        self.assertEqual(self.stored(), {"pico8/x-1.p8.png", META})
        self.assertEqual(self.meta(), {"x-1.p8.png": {"name": "X", "developer": "old"}})

    def test_ctrl_c_still_writes_the_metadata_of_the_carts_put_in_storage(self):
        fetch = self.serve([PAGE1, PAGE2, EMPTY])[0].new

        def interrupted(url):
            if url == bbs.cart_url("pico8tetris.p8.png"):
                raise KeyboardInterrupt
            return fetch(url)
        with mock.patch.object(bbs, "_fetch", interrupted), contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(ui, "ASSUME_YES", True), self.assertRaises(KeyboardInterrupt):
            bbs.download_pico8(mock.Mock(count=None, dry_run=False, yes=True))
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", "pico8/x-2.p8.png", META})
        self.assertEqual(sorted(self.meta()), ["molemole-1.p8.png", "x-2.p8.png"])

    def test_failed_cart_keeps_the_ones_before_it(self):
        code, _, err, _ = self.run_download([PAGE1, EMPTY], errors={bbs.cart_url("x-2.p8.png")})
        self.assertEqual(code, 1)
        self.assertIn("x-2.p8.png", err)
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", META})
        self.assertEqual(self.meta(), {"molemole-1.p8.png": {"name": "Mole Mole", "developer": "Adam Atomic"}})


if __name__ == "__main__":
    unittest.main()
