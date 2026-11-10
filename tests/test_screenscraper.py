import http.client
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
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
        self.assertEqual(media, {"covers": "https://neoclone.screenscraper.fr/media/box2d.png",
                                 "screenshots": "https://neoclone.screenscraper.fr/media/ss.png",
                                 "titlescreens": "https://neoclone.screenscraper.fr/media/title.png",
                                 "videos": "https://neoclone.screenscraper.fr/media/video.mp4",
                                 "manuals": "https://neoclone.screenscraper.fr/media/manual.pdf"})
        _, media = ss.parse_game(self.raw(), ("fr",))
        self.assertEqual(media["covers"], "https://neoclone.screenscraper.fr/media/box2d-wor.png")

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
               "medias": [{"type": "ss", "region": "wor", "url": "https://neoclone.screenscraper.fr/ss.png"}]}
        self.assertEqual(ss.parse_game(raw, ()), ({}, {}))
        self.assertTrue(ss.is_notgame(raw))
        self.assertFalse(ss.is_notgame(self.raw()))

    def test_malformed_media_entries_skipped(self):
        raw = {"medias": [{"type": ["ss"], "url": "u"}, {"type": {"a": 1}, "url": "u"},
                          {"type": "ss", "region": ["wor"], "url": "https://neoclone.screenscraper.fr/ss.png"}]}
        self.assertEqual(ss.parse_game(raw, ())[1], {"screenshots": "https://neoclone.screenscraper.fr/ss.png"})

    def test_rating_clamped_and_finite(self):
        for note, want in (("40", 1.0), ("-5", None), ("nan", None), ("inf", None), ("10", 0.5)):
            with self.subTest(note=note):
                self.assertEqual(ss.parse_game({"note": {"text": note}}, ())[0].get("rating"), want)

    def test_video_prefers_region(self):
        raw = {"medias": [{"type": "video", "region": "jp", "url": "https://neoclone.screenscraper.fr/jp.mp4"},
                          {"type": "video", "region": "us", "url": "https://neoclone.screenscraper.fr/us.mp4"}]}
        self.assertEqual(ss.parse_game(raw, ("us",))[1]["videos"], "https://neoclone.screenscraper.fr/us.mp4")

    def test_marquee_prefers_wheel_hd_then_wheel_then_marquee(self):
        def media(*types):
            return {"medias": [{"type": t, "region": "wor", "url": f"https://neoclone.screenscraper.fr/{t}.png"} for t in types]}
        self.assertEqual(ss.parse_game(media("marquee", "wheel", "wheel-hd"), ())[1]["marquees"], "https://neoclone.screenscraper.fr/wheel-hd.png")
        self.assertEqual(ss.parse_game(media("marquee", "wheel"), ())[1]["marquees"], "https://neoclone.screenscraper.fr/wheel.png")
        self.assertEqual(ss.parse_game(media("wheel", "marquee"), ())[1]["marquees"], "https://neoclone.screenscraper.fr/wheel.png")

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


class CappedResp(Resp):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(length)} if length is not None else {}


class TextTests(unittest.TestCase):
    def test_control_characters_stripped(self):
        raw = {"noms": [{"region": "wor", "text": "Ga\x00me\x1f \ufffeOne\x0b"}], "synopsis": [{"langue": "en", "text": "a\tb\nc\x07"}]}
        meta, _ = ss.parse_game(raw, ())
        self.assertEqual(meta, {"name": "Game One", "desc": "a\tb\nc"})


class ClientTests(unittest.TestCase):
    def test_http_431_is_its_own_quota_condition(self):
        def opener(req, timeout=None):
            raise http_error(431)
        with self.assertRaises(ss.TooManyUnrecognized) as cm:
            client(opener).lookup(12, "g.gba", 1)
        self.assertIsInstance(cm.exception, ss.QuotaExceeded)

        def opener430(req, timeout=None):
            raise http_error(430)
        with self.assertRaises(ss.QuotaExceeded) as cm:
            client(opener430).lookup(12, "g.gba", 1)
        self.assertNotIsInstance(cm.exception, ss.TooManyUnrecognized)

    def test_deeply_nested_body_is_unreadable(self):
        body = b"[" * 200000 + b"]" * 200000
        with self.assertRaises(ss.ApiError) as cm:
            client(lambda r, timeout=None: Resp(body)).quota()
        self.assertIn("unreadable", str(cm.exception))

    def test_api_body_capped(self):
        with mock.patch.object(ss, "API_MAX", 100):
            with self.assertRaises(ss.ApiError) as cm:
                client(lambda r, timeout=None: Resp(b"{" + b" " * 200 + b"}")).quota()
            self.assertIn("too large", str(cm.exception))
            with self.assertRaises(ss.ApiError):
                client(lambda r, timeout=None: CappedResp(b"{}", length=1000)).quota()

    def test_media_download_capped_and_partial_removed(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            url = "https://neoclone.screenscraper.fr/a.png"
            with mock.patch.object(ss, "MEDIA_MAX", 100):
                with self.assertRaises(ss.ApiError) as cm:
                    client(lambda r, timeout=None: Resp(b"x" * 300)).download(url, dest)
                self.assertIn("too large", str(cm.exception))
                with self.assertRaises(ss.ApiError):
                    client(lambda r, timeout=None: CappedResp(b"x", length=1000)).download(url, dest)
                client(lambda r, timeout=None: Resp(b"x" * 300)).download(url, dest, limit=1000)
            self.assertEqual(os.listdir(d), ["a.png"])

    def test_refused_media_is_its_own_error(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ss, "MEDIA_MAX", 10):
            dest = os.path.join(d, "a.png")
            with self.assertRaises(ss.MediaRefused):
                client(lambda r, timeout=None: Resp(b"x" * 30)).download("https://neoclone.screenscraper.fr/a.png", dest)
            with self.assertRaises(ss.MediaRefused):
                client(lambda r, timeout=None: Resp(b"x")).download("https://evil.example/a.png", dest)
        with self.assertRaises(ss.ApiError) as cm, mock.patch.object(ss, "API_MAX", 10):
            client(lambda r, timeout=None: Resp(b"{" + b" " * 30 + b"}")).quota()
        self.assertNotIsInstance(cm.exception, ss.MediaRefused)

    def test_download_stops_between_chunks(self):
        stop = threading.Event()

        class Slow(Resp):
            def read(self, n=-1):
                stop.set()
                return super().read(4)
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            with self.assertRaises(ss.Stopped):
                client(lambda r, timeout=None: Slow(b"x" * 100)).download("https://neoclone.screenscraper.fr/a.png", dest, stop=stop)
            self.assertEqual(os.listdir(d), [])

    def test_media_urls_must_be_https_screenscraper(self):
        ok = []
        opener = lambda r, timeout=None: ok.append(r.full_url) or Resp(b"x")  # noqa: E731
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            for url in ("http://neoclone.screenscraper.fr/a.png", "ftp://neoclone.screenscraper.fr/a.png",
                        "https://evil.example/a.png", "https://screenscraper.fr.evil.example/a.png",
                        "https://evilscreenscraper.fr/a.png"):
                with self.subTest(url=url), self.assertRaises(ss.ApiError) as cm:
                    client(opener).download(url + "?sspassword=" + PASSWORD, dest)
                self.assertNotIn(PASSWORD, str(cm.exception))
                self.assertNotIn("evil", str(cm.exception))
            for url in ("https://screenscraper.fr/a.png", "https://neoclone.screenscraper.fr/a.png"):
                client(opener).download(url, dest)
        self.assertEqual(len(ok), 2)

    def test_default_opener_keeps_connections_alive(self):
        self.assertIsInstance(ss.Client("u", "p", DEV)._opener, ss.KeepAlive)

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
            for url, opener in ((f"https://neoclone.screenscraper.fr/a b{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"https://neoclone.screenscraper.fr/a\x01{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"file:///etc/passwd{secret}", lambda r, timeout=None: Resp(b"x")),
                                (f"https://neoclone.screenscraper.fr/a{secret}", truncated)):
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
                client(lambda r, timeout=None: fixture("jeuinfos_not_found.txt")).download("https://neoclone.screenscraper.fr/a.png", dest)
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(os.path.exists(dest + ".part"))

    def test_download_writes_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "a.png")
            client(lambda r, timeout=None: Resp(b"data")).download("https://neoclone.screenscraper.fr/a.png", dest)
            self.assertEqual(Path(dest).read_bytes(), b"data")
            self.assertFalse(os.path.exists(dest + ".part"))



class FakeResp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status, self.reason, self.headers = status, "msg", headers or {}
        self._body = io.BytesIO(body)
        self._size = len(body)

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, amt=None):
        return self._body.read() if amt is None else self._body.read(amt)

    def isclosed(self):
        return self._body.tell() >= self._size

    def close(self):
        pass


class FakeConn:
    def __init__(self, net, host, port, timeout):
        self.net, self.host, self.timeout, self.sock, self.paths = net, host, timeout, None, []

    def connect(self):
        self.net.connects += 1
        if self.net.fail_connects:
            self.net.fail_connects -= 1
            raise TimeoutError()
        self.sock = mock.Mock()

    def request(self, method, path, headers=None):
        if self.sock is None:
            self.connect()
        self.paths.append(path)

    def getresponse(self):
        out = self.net.script.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    def close(self):
        self.sock = None


class FakeNet:
    """Stands in for http.client.HTTPSConnection: counts connections and answers requests from a script."""

    def __init__(self, *script):
        self.script, self.conns, self.connects, self.fail_connects = list(script), [], 0, 0

    def __call__(self, host, port, timeout=None):
        self.conns.append(FakeConn(self, host, port, timeout))
        return self.conns[-1]


class KeepAliveTests(unittest.TestCase):
    URL = "https://neoclone.screenscraper.fr/a.png?sspassword=" + PASSWORD

    def open(self, net, url=None, opener=None):
        opener = opener or ss.KeepAlive()
        with mock.patch.object(http.client, "HTTPSConnection", net):
            return opener(urllib.request.Request(url or self.URL), timeout=5)

    def test_a_threads_requests_share_one_connection(self):
        net, opener = FakeNet(FakeResp(body=b"a"), FakeResp(body=b"b")), ss.KeepAlive()
        for want in (b"a", b"b"):
            with self.open(net, opener=opener) as resp:
                self.assertEqual(resp.read(), want)
        self.assertEqual((len(net.conns), net.connects), (1, 1))
        self.assertEqual(net.conns[0].paths, ["/a.png?sspassword=" + PASSWORD] * 2)

    def test_each_thread_has_its_own_connection(self):
        net, opener = FakeNet(FakeResp(body=b"a"), FakeResp(body=b"b")), ss.KeepAlive()
        self.open(net, opener=opener).read()
        t = threading.Thread(target=lambda: self.open(net, opener=opener).read())
        t.start()
        t.join()
        self.assertEqual(len(net.conns), 2)

    def test_a_half_read_body_drops_the_connection(self):
        net, opener = FakeNet(FakeResp(body=b"abcd"), FakeResp(body=b"b")), ss.KeepAlive()
        with self.open(net, opener=opener) as resp:
            resp.read(2)
        self.open(net, opener=opener).read()
        self.assertEqual(len(net.conns), 2)

    def test_a_connection_the_server_closed_is_replaced_once(self):
        net, opener = FakeNet(FakeResp(body=b"a"), http.client.RemoteDisconnected(), FakeResp(body=b"b")), ss.KeepAlive()
        self.open(net, opener=opener).read()
        self.assertEqual(self.open(net, opener=opener).read(), b"b")
        self.assertEqual(len(net.conns), 2)

    def test_a_fresh_connection_that_fails_is_not_retried(self):
        net = FakeNet(http.client.RemoteDisconnected(), FakeResp())
        with self.assertRaises(http.client.RemoteDisconnected):
            self.open(net)
        self.assertEqual(len(net.script), 1)

    def test_opening_a_connection_is_retried(self):
        net = FakeNet(FakeResp(body=b"a"))
        net.fail_connects = ss.CONNECT_TRIES - 1
        self.assertEqual(self.open(net).read(), b"a")
        net = FakeNet(FakeResp())
        net.fail_connects = ss.CONNECT_TRIES
        with self.assertRaises(OSError):
            self.open(net)
        self.assertEqual(net.connects, ss.CONNECT_TRIES)

    def test_the_connect_timeout_is_short_and_reads_get_the_long_one(self):
        net = FakeNet(FakeResp())
        self.open(net)
        self.assertEqual(net.conns[0].timeout, ss.CONNECT_TIMEOUT)
        net.conns[0].sock.settimeout.assert_called_with(5)

    def test_error_statuses_raise_http_errors_without_the_url(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.open(FakeNet(FakeResp(status=404)))
        self.assertEqual(cm.exception.code, 404)
        self.assertNotIn(PASSWORD, str(cm.exception))

    def test_redirects_must_stay_https_screenscraper(self):
        ok = FakeNet(FakeResp(302, headers={"Location": "https://www.screenscraper.fr/b.png"}), FakeResp(body=b"b"))
        self.assertEqual(self.open(ok).read(), b"b")
        self.assertEqual([c.host for c in ok.conns], ["neoclone.screenscraper.fr", "www.screenscraper.fr"])
        for url in ("http://neoclone.screenscraper.fr/b.png", "https://evil.example/b.png"):
            with self.subTest(url=url), self.assertRaises(urllib.error.HTTPError) as cm:
                self.open(FakeNet(FakeResp(302, headers={"Location": url})))
            self.assertEqual(cm.exception.msg, ss.REDIRECT_REFUSED)
            self.assertNotIn("evil", str(cm.exception))
            self.assertNotIn(PASSWORD, str(cm.exception))
        with self.assertRaises(urllib.error.HTTPError):
            self.open(FakeNet(*[FakeResp(302, headers={"Location": "/c.png"}) for _ in range(ss.REDIRECTS + 1)]))

    def test_a_refused_redirect_is_media_refused(self):
        def refused(r, timeout=None):
            raise urllib.error.HTTPError("", 302, ss.REDIRECT_REFUSED, {}, None)
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ss.MediaRefused):
            client(refused).download("https://neoclone.screenscraper.fr/a.png", os.path.join(d, "a.png"))


if __name__ == "__main__":
    unittest.main()
