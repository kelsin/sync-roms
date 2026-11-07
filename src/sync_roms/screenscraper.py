"""ScreenScraper API client and response parsing (stdlib only).

Every ScreenScraper-specific string (endpoints, JSON keys, media types, HTTP codes) is in the
CONSTANTS block below. The JSON nesting is from memory and unverified against live responses, so
parsing skips anything missing instead of failing.
"""
import http.client
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

from . import __version__

# --- ScreenScraper specifics: correct them here ------------------------------------------------------
BASE_URL = "https://api.screenscraper.fr/api2/"
SOFTNAME = "sync-roms"
EP_GAME, EP_QUOTA, EP_SEARCH = "jeuInfos.php", "ssuserInfos.php", "jeuRecherche.php"
HTTP_NOT_FOUND = 404
HTTP_QUOTA = 430  # daily scrape quota
HTTP_UNRECOGNIZED = 431  # too many unrecognized ROMs today
HTTP_RATE_LIMIT = 429  # too many requests at once: worth retrying after a pause
NOT_FOUND_PREFIX = "Erreur : Rom"  # plain-text body of a miss (may come with HTTP 200)
# ScreenScraper media type -> scrape_plan.MEDIA_TYPES name. box-3D, support-2D, mixrbv1/2 are unverified.
MEDIA_MAP = {"box-2D": "covers", "box-3D": "3dboxes", "box-2D-back": "backcovers", "ss": "screenshots",
             "sstitle": "titlescreens", "marquee": "marquees", "wheel": "marquees", "wheel-hd": "marquees",
             "video": "videos", "manuel": "manuals", "fanart": "fanart", "support-2D": "physicalmedia",
             "mixrbv1": "miximages", "mixrbv2": "miximages"}
FALLBACK_NAME_REGIONS = ("wor", "us", "ss", "eu", "jp")
FALLBACK_MEDIA_REGIONS = ("wor", "us", "eu", "jp", "cus")
TYPE_PREFERENCE = ("wheel-hd", "wheel", "marquee")  # several types fill marquees: in a region tie, the first listed wins
ROM_HASHES = (("md5", "rommd5"), ("sha1", "romsha1"), ("crc", "romcrc"))  # what we send -> the matched ROM's field
LANGUAGES = ("en",)
NOTGAME = "ZZZ(NOTGAME)"
RATING_MAX = 20
TIMEOUT = 60
HOST = "screenscraper.fr"  # every request and redirect goes to it or a subdomain, over https
API_MAX = 16 << 20  # bytes an API response may have
MEDIA_MAX = 50 << 20  # bytes a media file may have
VIDEO_MAX = 512 << 20  # bytes a video may have
# -----------------------------------------------------------------------------------------------------


class Quota(NamedTuple):
    max_threads: int
    used_today: int
    max_today: int


class NotFound(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class TooManyUnrecognized(QuotaExceeded):
    pass


class ApiError(Exception):
    pass


class RateLimited(ApiError):
    pass


def to_int(v, default=0):
    if isinstance(v, bool):
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _text(v):
    """Stripped text of a value or of its "text" key, without characters XML can't hold."""
    if isinstance(v, dict):
        v = v.get("text")
    return _XML_INVALID.sub("", v).strip() if isinstance(v, str) else ""


def _dicts(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _dict(v):
    return v if isinstance(v, dict) else {}


def _unwrap(data):
    """The game dict from a whole response ({} when it holds none), or from the game dict itself."""
    data = _dict(data)
    if "response" in data:
        return _dict(_dict(data["response"]).get("jeu"))
    return _dict(data["jeu"]) if "jeu" in data else data


def is_notgame(raw):
    """Whether a game dict is ScreenScraper's ZZZ(NOTGAME) placeholder."""
    return NOTGAME in (_text(n) for n in _dicts(_unwrap(raw).get("noms")))


def rom_hash_matches(raw, hashes):
    """Whether the ROM a lookup matched (jeu.rom, or one of jeu.roms) has one of the hashes we sent."""
    raw = _unwrap(raw)
    roms = ([raw["rom"]] if isinstance(raw.get("rom"), dict) else []) + _dicts(raw.get("roms"))
    for ours, theirs in ROM_HASHES:
        sent = str(hashes.get(ours) or "").lower().lstrip("0")
        if sent and any(_text(r.get(theirs)).lower().lstrip("0") == sent for r in roms):
            return True
    return False


def _pick(items, key, prefs, fallback=True):
    """Text of the item whose `key` ranks best in prefs (else the first item with text if fallback)."""
    items = [i for i in _dicts(items) if _text(i)]
    for p in prefs:
        for i in items:
            if i.get(key) == p:
                return _text(i)
    return _text(items[0]) if items and fallback else ""


def _release_date(text):
    parts = text.split("-")
    if not parts[0].isdigit() or len(parts[0]) != 4:
        return ""
    y, m, d = (parts + ["01", "01"])[:3]
    return f"{y}-{m:0>2}-{d:0>2}" if m.isdigit() and d.isdigit() else f"{y}-01-01"


def parse_game(raw, regions):
    """(metadata fields as parse_gamelist makes them, {ES-DE media folder: url}) from a game dict."""
    raw = _unwrap(raw)
    if is_notgame(raw):
        return {}, {}
    prefs = tuple(regions) + FALLBACK_NAME_REGIONS
    meta = {}
    name = _pick(raw.get("noms"), "region", prefs)
    if name:
        meta["name"] = name
    desc = _pick(raw.get("synopsis"), "langue", LANGUAGES + ("wor",))
    if desc:
        meta["desc"] = desc
    for field, key in (("developer", "developpeur"), ("publisher", "editeur"), ("players", "joueurs")):
        if _text(raw.get(key)):
            meta[field] = _text(raw[key])
    for g in _dicts(raw.get("genres")):
        genre = _pick(g.get("noms"), "langue", LANGUAGES)
        if genre:
            meta["genre"] = genre
            break
    try:
        rating = float(_text(raw.get("note"))) / RATING_MAX
        if math.isfinite(rating) and rating > 0:
            meta["rating"] = round(min(rating, 1.0), 2)
    except ValueError:
        pass
    date = _release_date(_pick(raw.get("dates"), "region", prefs))
    if date:
        meta["releasedate"] = date

    media_prefs = tuple(regions) + FALLBACK_MEDIA_REGIONS
    best = {}  # folder -> ((region rank, type rank), url)
    for m in _dicts(raw.get("medias")):
        mtype, url, region = m.get("type"), m.get("url"), m.get("region")
        folder = MEDIA_MAP.get(mtype) if isinstance(mtype, str) else None
        if not folder or not isinstance(url, str) or not url:
            continue
        region = region if isinstance(region, str) else None
        rank = (media_prefs.index(region) if region in media_prefs else len(media_prefs) + (region is not None),
                TYPE_PREFERENCE.index(mtype) if mtype in TYPE_PREFERENCE else 0)
        if folder not in best or rank < best[folder][0]:
            best[folder] = (rank, url)
    return meta, {f: u for f, (_, u) in best.items()}


def _allowed(url):
    """Whether a URL is https on screenscraper.fr or one of its subdomains."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    return parts.scheme == "https" and (host == HOST or host.endswith("." + HOST))


def _too_large(resp, limit):
    length = getattr(resp, "headers", None)
    return to_int(length.get("Content-Length") if length is not None else None) > limit


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follows only redirects to https screenscraper.fr; the refusal's text never holds a URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed(newurl):
            raise urllib.error.HTTPError("", code, "redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, user, password, dev, opener=None):
        self._auth = {"devid": dev["devid"], "devpassword": dev["devpassword"], "softname": SOFTNAME,
                      "ssid": user, "sspassword": password}
        self._opener = opener or urllib.request.build_opener(SafeRedirect).open

    def _open(self, url):
        """The response for a URL. Every error is turned into one of ours whose text never holds the URL (its query
        carries the credentials)."""
        try:
            if any(c <= " " or c == "\x7f" for c in url):
                raise ValueError("bad URL")
            if not _allowed(url):
                raise ApiError(f"ScreenScraper gave a URL that isn't https on {HOST}")
            req = urllib.request.Request(url, headers={"User-Agent": f"sync-roms/{__version__}"})
            return self._opener(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code == HTTP_NOT_FOUND:
                raise NotFound("not found") from None
            if e.code == HTTP_UNRECOGNIZED:
                raise TooManyUnrecognized(f"ScreenScraper's limit of unrecognized ROMs for today is reached (HTTP {e.code})") from None
            if e.code == HTTP_QUOTA:
                raise QuotaExceeded(f"ScreenScraper quota exceeded (HTTP {e.code})") from None
            if e.code == HTTP_RATE_LIMIT:
                raise RateLimited(f"ScreenScraper is rate limiting requests (HTTP {e.code})") from None
            raise ApiError(f"ScreenScraper request failed (HTTP {e.code})") from None
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            raise ApiError(f"ScreenScraper request failed ({type(e).__name__})") from None
        except ValueError:  # a malformed URL (http.client.InvalidURL is an HTTPException, caught above)
            raise ApiError("ScreenScraper returned a bad URL") from None

    def _get(self, endpoint, **params):
        query = urllib.parse.urlencode({**self._auth, "output": "json", **params})
        try:
            with self._open(f"{BASE_URL}{endpoint}?{query}") as resp:
                if _too_large(resp, API_MAX):
                    raise ApiError("ScreenScraper response too large")
                body = resp.read(API_MAX + 1)
        except (OSError, http.client.HTTPException) as e:  # cut short or timed out while reading
            raise ApiError(f"ScreenScraper request failed ({type(e).__name__})") from None
        if len(body) > API_MAX:
            raise ApiError("ScreenScraper response too large")
        body = body.decode("utf-8", "replace")
        if body.lstrip().startswith(NOT_FOUND_PREFIX):
            raise NotFound("not found")
        try:
            return json.loads(body)
        except (ValueError, RecursionError):
            raise ApiError("ScreenScraper returned an unreadable response") from None

    def quota(self):
        user = _dict(_dict(_dict(self._get(EP_QUOTA)).get("response")).get("ssuser"))
        return Quota(to_int(user.get("maxthreads"), 1), to_int(user.get("requeststoday")),
                     to_int(user.get("maxrequestsperday")))

    @staticmethod
    def _game(data):
        """The game in a jeuInfos response; ApiError when it holds no game with a positive id."""
        game = _unwrap(data)
        if to_int(game.get("id")) <= 0:
            raise ApiError("ScreenScraper returned no game")
        return game

    def lookup(self, system_id, rom_name, size, md5=None, sha1=None, crc=None):
        params = {"systemeid": system_id, "romnom": rom_name, "romtaille": size}
        params.update({k: v for k, v in (("md5", md5), ("sha1", sha1), ("crc", crc)) if v})
        return self._game(self._get(EP_GAME, **params))

    def game(self, game_id):
        return self._game(self._get(EP_GAME, gameid=game_id))

    def search(self, system_id, name):
        games = _dict(_dict(self._get(EP_SEARCH, systemeid=system_id, recherche=name)).get("response")).get("jeux")
        out = []
        for g in _dicts(games):
            title = _pick(g.get("noms"), "region", FALLBACK_NAME_REGIONS)
            if to_int(g.get("id")) > 0 and title and title != NOTGAME:
                out.append((to_int(g["id"]), title))
        return out

    def download(self, url, dest, limit=None):
        """Save a media file of at most limit (default MEDIA_MAX) bytes at dest. Raises NotFound when ScreenScraper answers with its
        not-found text, ApiError when the file is bigger."""
        limit = limit or MEDIA_MAX
        part = dest + ".part"
        try:
            with self._open(url) as resp, open(part, "wb") as f:
                if _too_large(resp, limit):
                    raise ApiError("ScreenScraper media too large")
                chunk, total = resp.read(1 << 16), 0
                if chunk.lstrip().startswith(NOT_FOUND_PREFIX.encode()):
                    raise NotFound("not found")
                while chunk:
                    total += len(chunk)
                    if total > limit:
                        raise ApiError("ScreenScraper media too large")
                    f.write(chunk)
                    chunk = resp.read(1 << 16)
            os.replace(part, dest)
        except (OSError, http.client.HTTPException) as e:  # cut short or timed out while reading, or a local write
            raise ApiError(f"ScreenScraper download failed ({type(e).__name__})") from None
        finally:
            if os.path.exists(part):
                os.remove(part)
