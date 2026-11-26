import base64
import io
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import collections, collections_page, inventory, names, scrape_plan, store, tags  # noqa: E402

SMW = "snes/Super Mario World (USA).zip"
TAGS = {"mario": {"name": "Mario", "emoji": "🍄"}, "platformers": {"name": "Platformers", "emoji": "🏃"}}


def tag_data():
    return {"tags": TAGS, "declined": {},
            "games": {SMW: {"tags": ["mario", "platformers", "ghost"]}}}


class Page(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(tags, "load", tag_data))
        self.listing({})

    def save(self, **fields):
        collections.save_collection({"id": "mario", "name": "Mario", "description": "d", "games": [], **fields})

    def test_games_sorted_by_title_not_system(self):
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "b"},
                         {"system": "zzz", "bucket": "zzz/x.zip", "title": "A"}])
        games = collections_page.page_data()["collections"][0]["games"]
        self.assertEqual([g["title"] for g in games], ["A", "b"])

    def test_games_titles_tags_paths(self):
        self.save(games=[
            {"system": "snes", "bucket": SMW, "title": "Super </script> World"},
            {"system": "zzz", "bucket": "zzz/x.zip", "files": ["zzz/x2.zip"], "title": "X"}])
        data = collections_page.page_data()
        games = data["collections"][0]["games"]
        self.assertEqual(games[0], {"title": "Super </script> World", "system": "snes", "paths": [SMW],
                                    "tags": ["mario", "platformers"]})
        self.assertEqual(games[1]["paths"], ["zzz/x.zip", "zzz/x2.zip"])
        self.assertEqual(data["systems"]["snes"], "SNES")
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
        self.assertEqual(image.size, (150, 230))

    def test_band_is_cropped(self):
        from PIL import Image
        self.save(art="mario")
        uri = collections_page.page_data()["collections"][0]["art"]["band"]
        image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")
        top_left, bottom_left = image.getpixel((0, 0)), image.getpixel((0, image.height - 1))
        self.assertEqual(top_left[3], 255)
        self.assertEqual(bottom_left[3], 255)
        # WebP is lossy, so the colours match within a few levels rather than exactly.
        self.assertTrue(all(abs(a - b) <= 8 for a, b in zip(top_left[:3], bottom_left[:3])))

    def test_no_storage_means_no_tags(self):
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "T"}])
        with mock.patch.object(tags, "load", side_effect=SystemExit(2)), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            data = collections_page.page_data()
        self.assertEqual(data["tags"], {})
        self.assertEqual(data["collections"][0]["games"][0]["tags"], [])
        self.assertEqual(err.getvalue().count("⚠️"), 1)

    def listing(self, files):
        return self.enterContext(mock.patch.object(inventory, "files", lambda prefix, sizes=True: {
            k: v for k, v in files.items() if k.startswith(prefix)}))

    def test_every_system_has_a_short_name_and_the_page_uses_it(self):
        systems = store.repo_json("systems")
        self.assertTrue(all(isinstance(s.get("short"), str) and s["short"].strip() for s in systems))
        self.assertEqual(store.short_name({"name": "Full Name"}), "Full Name")
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"}])
        self.assertEqual(collections_page.page_data()["systems"], {"snes": "SNES"})

    def test_release_year_from_metadata(self):
        meta = {"Super Mario World (USA).zip": {"releasedate": "19901121"}, "x.sfc": {"releasedate": "unknown"}}
        self.enterContext(mock.patch.object(scrape_plan, "load_metadata", lambda system, fresh=False: meta))
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"},
                         {"system": "snes", "bucket": "snes/x.sfc", "title": "X"}])
        games = {g["title"]: g for g in collections_page.page_data()["collections"][0]["games"]}
        self.assertEqual(games["S"]["year"], "1990")
        self.assertNotIn("year", games["X"])

    def test_unreachable_storage_means_no_years(self):
        self.enterContext(mock.patch.object(scrape_plan, "load_metadata", side_effect=SystemExit(2)))
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"}])
        data = collections_page.page_data()
        self.assertNotIn("year", data["collections"][0]["games"][0])

    def test_sizes_rom_and_art(self):
        self.listing({SMW: 1000, "snes/other.zip": 5,
                      "scrapes/snes/covers/Super Mario World (USA).png": 40,
                      "scrapes/snes/videos/Super Mario World (USA).mp4": 200,
                      "scrapes/snes/onion/Super Mario World (USA).png": 9999,
                      "scrapes/snes/spruce/Super Mario World (USA).qoi": 9999,
                      "scrapes/snes/metadata.json": 7777, "scrapes/snes/matches.json": 7777,
                      "scrapes/snes/covers/Other.png": 3})
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"}])
        c = collections_page.page_data()["collections"][0]
        self.assertEqual(c["games"][0]["size"], {"rom": 1000, "art": 240})
        self.assertEqual(c["size"], {"rom": 1000, "art": 240})

    def test_sizes_multi_disc_and_unknown(self):
        self.listing({"psx/a (Disc 1).chd": 100, "psx/a (Disc 2).chd": 150, "psx/a.m3u": 1,
                      "scrapes/psx/covers/a.png": 10, "scrapes/psx/covers/a (Disc 2).png": 5,
                      "BIOS/psx/x.bin": 99999})
        self.save(games=[
            {"system": "psx", "bucket": "psx/a.m3u", "files": ["psx/a (Disc 1).chd", "psx/a (Disc 2).chd"], "title": "A"},
            {"system": "psx", "bucket": "psx/missing.chd", "title": "M"}])
        games = {g["title"]: g for g in collections_page.page_data()["collections"][0]["games"]}
        self.assertEqual(games["A"]["size"], {"rom": 251, "art": 15})
        self.assertNotIn("size", games["M"])
        self.assertEqual(collections_page.page_data()["collections"][0]["size"], {"rom": 251, "art": 15})

    def test_zero_byte_media_not_counted(self):
        self.listing({SMW: 10, "scrapes/snes/covers/Super Mario World (USA).png": 0})
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"}])
        self.assertEqual(collections_page.page_data()["collections"][0]["games"][0]["size"], {"rom": 10, "art": 0})

    def test_unreachable_storage_means_no_sizes(self):
        self.save(games=[{"system": "snes", "bucket": SMW, "title": "S"}])
        with mock.patch.object(inventory, "files", side_effect=SystemExit(2)), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            data = collections_page.page_data()
        self.assertNotIn("size", data["collections"][0]["games"][0])
        self.assertEqual(data["collections"][0]["size"], {"rom": 0, "art": 0})
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

    def test_one_open_row_with_sticky_header(self):
        self.assertIn("position: sticky; top: var(--bar-h", self.html)
        self.assertIn("overflow: clip", self.html)
        self.assertNotIn("<details", self.html)
        self.assertNotIn("overflow: hidden; min-width", self.html)

    def test_size_column_and_sort(self):
        for needle in ('["year", "Year", "col-year"]', '["size", "Size", "col-size"]', "col[0] === \"size\" ? -1 : 1", "Art data", "formatSize", "pills"):
            self.assertIn(needle, self.html)

    def test_reads_and_writes_hash(self):
        for needle in ("replaceState", "hashchange", "URLSearchParams"):
            self.assertIn(needle, self.html)


class CommandTest(helpers.Cmd):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(tags, "load", tag_data))
        self.opened = self.enterContext(mock.patch("webbrowser.open", return_value=True))

    def save(self, name):
        collections.save_collection({"id": "mario", "name": name, "description": "d", "games": []})

    def page(self, *args):
        return self.run_cmd("collections", "page", *args)[0]

    def test_writes_and_opens(self):
        self.save("Plumber Picks")
        self.assertEqual(self.page(), 0)
        path = collections_page.DEFAULT_PATH()
        self.assertEqual(path, os.path.join(store.data_dir(), "share", "collections", "index.html"))
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Plumber Picks", html)
        self.assertNotIn('id="page-data">{}<', html)
        self.opened.assert_called_once_with(pathlib.Path(path).as_uri())

    def test_out_writes_elsewhere(self):
        self.save("Plumber Picks")
        out = os.path.join(self.enterContext(tempfile.TemporaryDirectory()), "x", "page.html")
        self.assertEqual(self.page("--out", out), 0)
        with open(out, encoding="utf-8") as f:
            self.assertIn("Plumber Picks", f.read())
        self.assertFalse(os.path.exists(collections_page.DEFAULT_PATH()))
        self.opened.assert_called_once_with(pathlib.Path(out).as_uri())

    def test_script_tag_escaped(self):
        self.save("</script><b>")
        self.page()
        with open(collections_page.DEFAULT_PATH(), encoding="utf-8") as f, \
                open(collections_page.TEMPLATE, encoding="utf-8") as t:
            html, template = f.read(), t.read()
        self.assertEqual(html.count("</script>"), template.count("</script>"))
        self.assertNotIn("<b>", html.split('id="page-data">')[1].split("</script>")[0])

    def test_dry_run_refused(self):
        self.assertEqual(self.page("--dry-run"), 2)


if __name__ == "__main__":
    unittest.main()
