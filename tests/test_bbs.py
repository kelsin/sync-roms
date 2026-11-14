import contextlib
import datetime
import io
import json
import os
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

    def run_download(self, pages, count=None, dry_run=False, carts=None, errors=()):
        patch, fetched = self.serve(pages, carts, errors)
        out, err = io.StringIO(), io.StringIO()
        with patch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ui.ASSUME_YES = True
            try:
                code = bbs.download_pico8(mock.Mock(count=count, dry_run=dry_run, yes=True))
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

    def test_not_a_png_is_skipped(self):
        code, _, err, _ = self.run_download([PAGE1, EMPTY], carts={"molemole-1.p8.png": b"<html>"})
        self.assertIn("molemole-1.p8.png", err)
        self.assertEqual(self.stored(), {"pico8/x-2.p8.png", META})
        self.assertEqual(list(self.meta()), ["x-2.p8.png"])

    def test_listing_error_keeps_the_pages_read(self):
        code, out, err, _ = self.run_download([PAGE1], errors={bbs.page_url(2)})
        self.assertIn("503", err)
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", "pico8/x-2.p8.png", META})

    def test_failed_cart_keeps_the_ones_before_it(self):
        code, _, err, _ = self.run_download([PAGE1, EMPTY], errors={bbs.cart_url("x-2.p8.png")})
        self.assertEqual(code, 1)
        self.assertIn("x-2.p8.png", err)
        self.assertEqual(self.stored(), {"pico8/molemole-1.p8.png", META})
        self.assertEqual(self.meta(), {"molemole-1.p8.png": {"name": "Mole Mole", "developer": "Adam Atomic"}})


if __name__ == "__main__":
    unittest.main()
