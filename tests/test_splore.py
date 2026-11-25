import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import helpers  # noqa: E402

from sync_roms import bbs, ignore, splore  # noqa: E402

LINE = "| x-2 \t| x |123|Ann | 0 | 0 |My Game |\r\n"


class Splore(helpers.CardDir):
    def setUp(self):
        super().setUp()
        self.ignored = set()
        self.enterContext(mock.patch.object(ignore, "keys", side_effect=lambda: frozenset(self.ignored)))

    def cart(self, *parts, data=bbs._PNG + b"x"):
        path = self.cp(*splore.CACHE, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def fav(self, text):
        path = self.cp(*splore.CACHE, "favourites.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            f.write(text)

    def files(self):
        return [c["file"] for c in splore.cached(self.card)]

    def test_highest_revision_per_cart(self):
        self.cart("bbs", "carts", "x-1.p8.png")
        self.cart("bbs", "carts", "x-2.p8.png")
        self.cart("bbs", "1", "15133.p8.png")
        self.assertEqual(self.files(), ["15133.p8.png", "x-2.p8.png"])

    def test_skips_partial_odd_and_non_png(self):
        self.cart("bbs", "carts", "temp-y-0.p8.png")
        self.cart("bbs", "carts", "bad name.p8.png")
        self.cart("bbs", "carts", "z-0.p8.png", data=b"not png")
        self.assertEqual(self.files(), [])

    def test_favourites_fields(self):
        self.fav(LINE + "|bbs/1/15133.p8.png|\n")
        self.assertEqual(splore.favourites(self.card), {"x": ("My Game", "Ann"), "15133": (None, None)})

    def test_titles_come_from_favourites(self):
        self.cart("bbs", "carts", "x-2.p8.png")
        self.fav(LINE)
        [c] = splore.cached(self.card)
        self.assertEqual((c["title"], c["author"]), ("My Game", "Ann"))

    def test_plan_new_upgrade_and_already_held(self):
        self.put("pico8/x-1.p8.png")
        self.put("pico8/w-3.p8.png")
        for n in ("x-2", "w-3", "w-1", "n-0"):
            self.cart("bbs", "carts", n + ".p8.png")
        new, up = splore.plan(self.card)
        self.assertEqual([c["file"] for c in new], ["n-0.p8.png"])
        self.assertEqual([(k, c["file"]) for k, c in up], [("pico8/x-1.p8.png", "x-2.p8.png")])

    def test_plan_skips_ignored(self):
        self.ignored = {"pico8/n-0.p8.png"}
        self.cart("bbs", "carts", "n-0.p8.png")
        self.assertEqual(splore.plan(self.card), ([], []))

    def test_no_cache_folder(self):
        self.assertEqual(splore.cached(self.card), [])
        self.assertEqual(splore.favourites(self.card), {})


if __name__ == "__main__":
    unittest.main()
