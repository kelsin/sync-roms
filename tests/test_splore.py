import io
import contextlib
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import helpers  # noqa: E402

from sync_roms import bbs, drivers, ignore, scrape_online, splore, store, ui  # noqa: E402

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


CREDS = {"screenscraper_user": "me", "screenscraper_password": "pw"}
PICO8 = {"bucket": "pico8", "name": "PICO-8", "screenscraper": 234}
NEW = "| n-0 \t| x |123|Ann | 0 | 0 |N |\r\n"


class Run(Splore):
    def setUp(self):
        super().setUp()
        self.terminal = self.enterContext(mock.patch.object(ui, "has_terminal", return_value=True))
        self.confirm = self.enterContext(mock.patch.object(ui, "confirm", return_value=True))
        self.enterContext(mock.patch.object(ui, "ASSUME_YES", False))
        self.enterContext(mock.patch.object(drivers, "can_write", return_value=True))
        self.scrape = self.enterContext(mock.patch.object(scrape_online, "run_scrape", return_value=0))
        self.enterContext(mock.patch.object(scrape_online, "make_client", return_value="client"))
        self.settings(CREDS)
        store.write_cards({"c": {"layout": "spruce", "games": {}}})

    def settings(self, data):
        os.makedirs(self.data, exist_ok=True)
        with open(os.path.join(self.data, "settings.json"), "w") as f:
            json.dump(data, f)

    def stored(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.root) for d, _, fs in os.walk(self.root) for f in fs)

    def games(self):
        return store.card_games("c").get("pico8")

    def run_splore(self, dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = splore.run("c", self.card, self.cp("Roms", "PICO8"), PICO8, dry_run)
        return code, out.getvalue()

    def test_uploads_scrapes_and_adds_the_new_cart(self):
        self.cart("bbs", "carts", "n-0.p8.png")
        self.fav(NEW)
        code, _ = self.run_splore()
        self.assertEqual(code, 0)
        self.assertIn("pico8/n-0.p8.png", self.stored())
        self.scrape.assert_called_once()
        args, kwargs = self.scrape.call_args
        size = os.path.getsize(os.path.join(self.root, "pico8", "n-0.p8.png"))
        tag = splore.inventory.tag("pico8/n-0.p8.png")
        self.assertEqual(args[1:], ({"pico8": PICO8}, {"pico8": [("n-0.p8.png", size, tag)]}, set()))
        self.assertIs(kwargs["ask"], False)
        self.assertEqual(self.games(), [{"title": "N", "bucket": "pico8/n-0.p8.png"}])

    def test_upgrade_retargets_and_is_not_scraped(self):
        self.put("pico8/x-1.p8.png")
        store.write_cards({"c": {"layout": "spruce", "games": {"pico8": [{"title": "X", "bucket": "pico8/x-1.p8.png"}]}}})
        self.cart("bbs", "carts", "x-2.p8.png")
        self.assertEqual(self.run_splore()[0], 0)
        self.assertEqual([g["bucket"] for g in self.games()], ["pico8/x-2.p8.png"])
        self.scrape.assert_not_called()

    def test_full_system_card_gets_no_entries(self):
        store.write_cards({"c": {"layout": "spruce", "games": {"pico8": {"full_system": True}}}})
        self.cart("bbs", "carts", "n-0.p8.png")
        self.run_splore()
        self.assertEqual(self.games(), {"full_system": True})

    def test_dry_run_writes_nothing(self):
        self.cart("bbs", "carts", "n-0.p8.png")
        before = (self.stored(), store.load_cards())
        code, out = self.run_splore(dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual((self.stored(), store.load_cards()), before)
        self.assertIn("new: n-0.p8.png", out)
        self.assertIn("would scrape 1", out)
        self.scrape.assert_not_called()

    def test_declined_uploads_nothing(self):
        self.confirm.return_value = False
        self.cart("bbs", "carts", "n-0.p8.png")
        self.assertEqual(self.run_splore()[0], 0)
        self.assertEqual(self.stored(), [])
        self.assertEqual(self.games(), None)

    def test_no_terminal_without_yes_skips_with_a_hint(self):
        self.terminal.return_value = False
        self.cart("bbs", "carts", "n-0.p8.png")
        code, out = self.run_splore()
        self.assertEqual(code, 0)
        self.assertEqual(self.stored(), [])
        self.assertIn("--yes", out)
        self.confirm.assert_not_called()

    def test_no_credentials_skips_the_scrape(self):
        self.settings({})
        self.cart("bbs", "carts", "n-0.p8.png")
        self.fav(NEW)
        code, out = self.run_splore()
        self.assertEqual(code, 0)
        self.assertIn("pico8/n-0.p8.png", self.stored())
        self.scrape.assert_not_called()
        self.assertIn("sync-roms scrape pico8", out)
        self.assertEqual(self.games(), [{"title": "N", "bucket": "pico8/n-0.p8.png"}])

    def test_scrape_that_exits_is_a_warning(self):
        self.scrape.side_effect = SystemExit(3)
        self.cart("bbs", "carts", "n-0.p8.png")
        self.fav(NEW)
        self.assertEqual(self.run_splore()[0], 1)
        self.assertEqual(self.games(), [{"title": "N", "bucket": "pico8/n-0.p8.png"}])

    def test_storage_unreachable_is_a_warning(self):
        self.cart("bbs", "carts", "n-0.p8.png")
        with mock.patch.object(splore, "plan", side_effect=OSError("gone")):
            code, out = self.run_splore()
        self.assertEqual(code, 1)
        self.assertIn("gone", out)

    def test_import_copy_is_renamed(self):
        data = bbs._PNG + b"B"
        self.put("pico8/x-2.p8.png", data)
        self.cart("bbs", "carts", "x-2.p8.png", data=data)
        roms = self.cp("Roms", "PICO8")
        os.makedirs(roms)
        for name in ("My Game.p8.png", "Other.p8.png"):
            with open(os.path.join(roms, name), "wb") as f:
                f.write(data if name == "My Game.p8.png" else bbs._PNG + b"C")
        code, out = self.run_splore()
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(roms)), ["Other.p8.png", "x-2.p8.png"])
        self.assertIn("Renamed My Game.p8.png → x-2.p8.png", out)
        with open(os.path.join(roms, "Again.p8.png"), "wb") as f:  # x-2.p8.png is there: the copy stays
            f.write(data)
        self.run_splore()
        self.assertEqual(sorted(os.listdir(roms)), ["Again.p8.png", "Other.p8.png", "x-2.p8.png"])


if __name__ == "__main__":
    unittest.main()
