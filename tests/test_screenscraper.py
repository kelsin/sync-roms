import http.client
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

    def test_response_without_a_game_parses_to_nothing(self):
        raw = {"response": {"serveurs": {"x": {"text": "1"}}, "ssuser": {"id": "me"}, "noms": [{"region": "wor", "text": "No"}]}}
        self.assertEqual(ss.parse_game(raw, ()), ({}, {}))

    def test_notgame_placeholder_parses_to_nothing(self):
        raw = {"id": "9", "noms": [{"region": "wor", "text": ss.NOTGAME}],
               "medias": [{"type": "ss", "region": "wor", "url": "https://m.example/ss.png"}]}
        self.assertEqual(ss.parse_game(raw, ()), ({}, {}))
        self.assertTrue(ss.is_notgame(raw))
        self.assertFalse(ss.is_notgame(self.raw()))

    def test_malformed_media_entries_skipped(self):
        raw = {"medias": [{"type": ["ss"], "url": "u"}, {"type": {"a": 1}, "url": "u"},
                          {"type": "ss", "region": ["wor"], "url": "https://m.example/ss.png"}]}
        self.assertEqual(ss.parse_game(raw, ())[1], {"screenshots": "https://m.example/ss.png"})

    def test_rating_clamped_and_finite(self):
        for note, want in (("40", 1.0), ("-5", None), ("nan", None), ("inf", None), ("10", 0.5)):
            with self.subTest(note=note):
                self.assertEqual(ss.parse_game({"note": {"text": note}}, ())[0].get("rating"), want)

    def test_video_prefers_region(self):
        raw = {"medias": [{"type": "video", "region": "jp", "url": "https://m.example/jp.mp4"},
                          {"type": "video", "region": "us", "url": "https://m.example/us.mp4"}]}
        self.assertEqual(ss.parse_game(raw, ("us",))[1]["videos"], "https://m.example/us.mp4")

    def test_marquee_prefers_wheel_hd_then_wheel_then_marquee(self):
        def media(*types):
            return {"medias": [{"type": t, "region": "wor", "url": f"https://m.example/{t}.png"} for t in types]}
        self.assertEqual(ss.parse_game(media("marquee", "wheel", "wheel-hd"), ())[1]["marquees"], "https://m.example/wheel-hd.png")
        self.assertEqual(ss.parse_game(media("marquee", "wheel"), ())[1]["marquees"], "https://m.example/wheel.png")
        self.assertEqual(ss.parse_game(media("wheel", "marquee"), ())[1]["marquees"], "https://m.example/wheel.png")

    def test_to_int_is_public(self):
        self.assertEqual((ss.to_int(" 7 "), ss.to_int("x"), ss.to_int(None, 1)), (7, 0, 1))

    def test_rom_hash_matches(self):
        sent = {"md5": "abcdef", "sha1": "0123", "crc": "0000BEEF"}
        self.assertTrue(ss.rom_hash_matches({"rom": {"rommd5": "ABCDEF"}}, sent))
        self.assertTrue(ss.rom_hash_matches({"roms": [{"romcrc": "beef"}]}, sent))
        self.assertTrue(ss.rom_hash_matches({"rom": {"romsha1": {"text": "0123"}}}, sent))
        self.assertFalse(ss.rom_hash_matches({"rom": {"rommd5": "999"}}, sent))
        self.assertFalse(ss.rom_hash_matches({"id": "1"}, sent))
        self.assertFalse(ss.rom_hash_matches({"rom": {"rommd5": "abcdef"}}, {}))
        self.assertFalse(ss.rom_hash_matches({"rom": ["junk"], "roms": "junk"}, sent))


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

    def test_rate_limit_raises_rate_limited_api_error(self):
        def opener(req, timeout=None):
            raise http_error(429)
        with self.assertRaises(ss.RateLimited) as cm:
            client(opener).lookup(12, "g.gba", 1)
        self.assertIsInstance(cm.exception, ss.ApiError)

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

        def invalid(req, timeout=None):
            raise http.client.InvalidURL("bad " + req.full_url)
        with self.assertRaises(ss.ApiError) as cm:
            client(invalid).lookup(12, "g.gba", 1)
        self.assertNotIn(PASSWORD, str(cm.exception))
        self.assertNotIn("DEVSECRET", str(cm.exception))

        def truncated(req, timeout=None):
            class Cut(Resp):
                def read(self, n=-1):
                    raise http.client.IncompleteRead(req.full_url.encode())
            return Cut(b"")
        secret = f"?ssid=me&sspassword={PASSWORD}&devpassword=DEVSECRET"
        with tempfile.TemporaryDirectory() as d:
            for url, opener in ((f"https://m.example/a b{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"https://m.example/a\x01{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"file:///etc/passwd{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"https://m.example/a{secret}", truncated)):
                with self.subTest(url=url[:30]), self.assertRaises(ss.ApiError) as cm:
                    client(opener).download(url, os.path.join(d, "a.png"))
                self.assertNotIn(PASSWORD, str(cm.exception))
                self.assertNotIn("DEVSECRET", str(cm.exception))
                self.assertFalse(os.path.exists(os.path.join(d, "a.png.part")))

    def test_search_and_game(self):
        body = json.dumps({"response": {"jeux": [{"id": "5", "noms": [{"region": "us", "text": "Foo"}]}, {"x": 1}]}})
        self.assertEqual(client(lambda r, timeout=None: Resp(body.encode())).search(12, "foo"), [(5, "Foo")])
        self.assertEqual(client(lambda r, timeout=None: fixture("jeuinfos_found.json")).game(12345)["id"], "12345")

    def test_response_without_game_or_id_is_an_error(self):
        for body in ({"response": {"serveurs": {}, "ssuser": {"id": "me"}}},
                     {"response": {"jeu": {"noms": [{"region": "wor", "text": "No id"}]}}},
                     {"response": {"jeu": {"id": "0", "noms": [{"region": "wor", "text": "Zero"}]}}},
                     {"response": {"jeu": {"id": True}}}):
            opener = lambda r, timeout=None, body=body: Resp(json.dumps(body).encode())  # noqa: E731
            with self.subTest(body=body):
                with self.assertRaises(ss.ApiError):
                    client(opener).lookup(12, "g.gba", 1)
                with self.assertRaises(ss.ApiError):
                    client(opener).game(5)

    def test_malformed_bodies_raise_api_error_or_parse_empty(self):
        for body in ([1, 2], {"response": [1]}, {"response": {"jeu": [1]}}, {"response": {"ssuser": [1], "jeux": {"a": 1}}}, "text"):
            opener = lambda r, timeout=None, body=body: Resp(json.dumps(body).encode())  # noqa: E731
            with self.subTest(body=body):
                with self.assertRaises(ss.ApiError):
                    client(opener).lookup(12, "g.gba", 1)
                self.assertEqual(client(opener).quota(), ss.Quota(1, 0, 0))
                self.assertEqual(client(opener).search(12, "x"), [])

    def test_download_not_found_text_raises_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            with self.assertRaises(ss.NotFound):
                client(lambda r, timeout=None: fixture("jeuinfos_not_found.txt")).download("https://m.example/a.png", dest)
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(os.path.exists(dest + ".part"))

    def test_download_writes_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            client(lambda r, timeout=None: Resp(b"data")).download("https://m.example/a.png", dest)
            self.assertEqual(Path(dest).read_bytes(), b"data")
            self.assertFalse(os.path.exists(dest + ".part"))


if __name__ == "__main__":
    unittest.main()
