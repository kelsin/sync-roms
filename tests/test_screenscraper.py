import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import screenscraper as ss  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "screenscraper"
DEV = {"devid": "dev", "devpassword": "DEVSECRET"}
PASSWORD = "hunter2secret"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fixture(name):
    return Resp((FIX / name).read_bytes())


def http_error(code):
    return urllib.error.HTTPError("https://x.example/?sspassword=" + PASSWORD, code, "boom", {}, io.BytesIO(b"x"))


def client(opener):
    return ss.Client("testuser", PASSWORD, DEV, opener=opener)


class ParseGameTests(unittest.TestCase):
    def raw(self):
        return json.loads((FIX / "jeuinfos_found.json").read_text())["response"]["jeu"]

    def test_parse_game_maps_fields(self):
        meta, _ = ss.parse_game(self.raw(), ("us",))
        self.assertEqual(meta, {"name": "Example Quest", "desc": "An example adventure.",
                                "developer": "Example Dev", "publisher": "Example Pub",
                                "genre": "Platform", "players": "1-2", "rating": 0.8,
                                "releasedate": "1999-05-01"})

    def test_parse_game_maps_media_types_and_prefers_region(self):
        _, media = ss.parse_game(self.raw(), ("us",))
        self.assertEqual(media, {"covers": "https://screenscraper.example/media/box2d.png",
                                 "screenshots": "https://screenscraper.example/media/ss.png",
                                 "titlescreens": "https://screenscraper.example/media/title.png",
                                 "videos": "https://screenscraper.example/media/video.mp4",
                                 "manuals": "https://screenscraper.example/media/manual.pdf"})
        _, media = ss.parse_game(self.raw(), ("fr",))
        self.assertEqual(media["covers"], "https://screenscraper.example/media/box2d-wor.png")

    def test_parse_game_tolerates_missing_keys(self):
        meta, media = ss.parse_game({"id": "1", "noms": "junk", "medias": [None, {"type": "ss"}]}, ("us",))
        self.assertEqual((meta, media), ({}, {}))

    def test_year_only_date(self):
        raw = {"dates": [{"region": "jp", "text": "1998"}]}
        self.assertEqual(ss.parse_game(raw, ("jp",))[0]["releasedate"], "1998-01-01")


class ClientTests(unittest.TestCase):
    def test_lookup_returns_game(self):
        seen = []

        def opener(req, timeout=None):
            seen.append(req)
            return fixture("jeuinfos_found.json")

        g = client(opener).lookup(12, "game.gba", 100, md5="ab")
        self.assertEqual(g["id"], "12345")
        self.assertIn("md5=ab", seen[0].full_url)
        self.assertTrue(seen[0].get_header("User-agent").startswith("sync-roms/"))

    def test_lookup_not_found_raises(self):
        def http404(req, timeout=None):
            raise http_error(404)
        with self.assertRaises(ss.NotFound):
            client(http404).lookup(12, "g.gba", 1)
        with self.assertRaises(ss.NotFound):
            client(lambda req, timeout=None: fixture("jeuinfos_not_found.txt")).lookup(12, "g.gba", 1)

    def test_lookup_quota_raises_quota_exceeded(self):
        for code in (430, 431):
            def opener(req, timeout=None, code=code):
                raise http_error(code)
            with self.assertRaises(ss.QuotaExceeded):
                client(opener).lookup(12, "g.gba", 1)

    def test_quota_parse(self):
        q = client(lambda req, timeout=None: fixture("ssuserinfos.json")).quota()
        self.assertEqual(q, ss.Quota(max_threads=1, used_today=123, max_today=20000))

    def test_password_never_in_error_text(self):
        for code in (429, 500, 403):
            def opener(req, timeout=None, code=code):
                raise http_error(code)
            with self.assertRaises(ss.ApiError) as cm:
                client(opener).lookup(12, "g.gba", 1)
            self.assertNotIn(PASSWORD, str(cm.exception))
            self.assertNotIn("DEVSECRET", str(cm.exception))

        def boom(req, timeout=None):
            raise urllib.error.URLError("fail " + req.full_url)
        with self.assertRaises(ss.ApiError) as cm:
            client(boom).lookup(12, "g.gba", 1)
        self.assertNotIn(PASSWORD, str(cm.exception))
        self.assertNotIn("DEVSECRET", str(cm.exception))

    def test_search_and_game(self):
        body = json.dumps({"response": {"jeux": [{"id": "5", "noms": [{"region": "us", "text": "Foo"}]}, {"x": 1}]}})
        self.assertEqual(client(lambda r, timeout=None: Resp(body.encode())).search(12, "foo"), [(5, "Foo")])
        self.assertEqual(client(lambda r, timeout=None: fixture("jeuinfos_found.json")).game(12345)["id"], "12345")

    def test_download_writes_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            client(lambda r, timeout=None: Resp(b"data")).download("https://m.example/a.png", dest)
            self.assertEqual(Path(dest).read_bytes(), b"data")
            self.assertFalse(os.path.exists(dest + ".part"))


if __name__ == "__main__":
    unittest.main()
