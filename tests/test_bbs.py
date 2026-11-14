import os
import unittest

from sync_roms import bbs

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


if __name__ == "__main__":
    unittest.main()
