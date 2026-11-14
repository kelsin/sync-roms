import datetime
import json
import os
import unittest
from unittest import mock

import helpers

from sync_roms import bbs, store

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


if __name__ == "__main__":
    unittest.main()
