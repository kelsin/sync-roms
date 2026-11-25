import base64
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import collections, collections_page, names, tags  # noqa: E402

SMW = "snes/Super Mario World (USA).zip"
TAGS = {"mario": {"name": "Mario", "emoji": "🍄"}, "platformers": {"name": "Platformers", "emoji": "🏃"}}


def tag_data():
    return {"tags": TAGS, "declined": {},
            "games": {SMW: {"tags": ["mario", "platformers", "ghost"]}}}


class Page(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(tags, "load", tag_data))

    def save(self, **fields):
        collections.save_collection({"id": "mario", "name": "Mario", "description": "d", "games": [], **fields})

    def test_games_titles_tags_paths(self):
        self.save(games=[
            {"system": "snes", "bucket": SMW, "title": "Super </script> World"},
            {"system": "zzz", "bucket": "zzz/x.zip", "files": ["zzz/x2.zip"], "title": "X"}])
        data = collections_page.page_data()
        games = data["collections"][0]["games"]
        self.assertEqual(games[0], {"title": "Super </script> World", "system": "snes", "paths": [SMW],
                                    "tags": ["mario", "platformers"]})
        self.assertEqual(games[1]["paths"], ["zzz/x.zip", "zzz/x2.zip"])
        self.assertEqual(data["systems"]["snes"], "Nintendo SNES (Super Nintendo)")
        self.assertEqual(data["tags"], {"mario": {"name": "Mario", "emoji": "🍄"},
                                        "platformers": {"name": "Platformers", "emoji": "🏃"}})

    def test_title_falls_back_to_names_title(self):
        self.save(games=[{"system": "snes", "bucket": SMW}])
        with mock.patch.object(names, "title", return_value="Scraped"):
            data = collections_page.page_data()
        self.assertEqual(data["collections"][0]["games"][0]["title"], "Scraped")

    def test_art_uris(self):
        self.save(art="mario")
        art = collections_page.page_data()["collections"][0]["art"]
        self.assertEqual(set(art), {"band", "box", "totk"})
        for uri in art.values():
            self.assertTrue(uri.startswith("data:image/webp;base64,"))
        self.save(art="nope")
        self.assertEqual(collections_page.page_data()["collections"][0]["art"], {})

    def test_band_is_shrunk(self):
        from PIL import Image
        self.save(art="mario")
        uri = collections_page.page_data()["collections"][0]["art"]["band"]
        image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
        self.assertEqual(image.width, 150)

    def test_no_storage_means_no_tags(self):
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "T"}])
        with mock.patch.object(tags, "load", side_effect=SystemExit(2)), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            data = collections_page.page_data()
        self.assertEqual(data["tags"], {})
        self.assertEqual(data["collections"][0]["games"][0]["tags"], [])
        self.assertEqual(err.getvalue().count("⚠️"), 1)

    def test_unknown_system_name_falls_back(self):
        self.save(games=[{"system": "zzz", "bucket": "zzz/x.zip", "title": "X"}])
        self.assertEqual(collections_page.page_data()["systems"]["zzz"], "zzz")


TEMPLATE = os.path.join(os.path.dirname(collections_page.__file__), "data", "collections-page.html")
DATA_BLOCK = '<script type="application/json" id="page-data">{}</script>'


class TemplateTest(unittest.TestCase):
    def setUp(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            self.html = f.read()

    def test_empty_data_block(self):
        self.assertEqual(self.html.count(DATA_BLOCK), 1)

    def test_no_external_urls(self):
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)

    def test_no_innerhtml(self):
        self.assertNotIn("innerHTML", self.html)

    def test_reads_and_writes_hash(self):
        for needle in ("replaceState", "hashchange", "URLSearchParams"):
            self.assertIn(needle, self.html)


if __name__ == "__main__":
    unittest.main()
