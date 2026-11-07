"""ScreenScraper API client and response parsing (stdlib only).

Every ScreenScraper-specific string (endpoints, JSON keys, media types, HTTP codes) is in the
CONSTANTS block below. The JSON nesting is from memory and unverified against live responses, so
parsing skips anything missing instead of failing.
"""
import json
import os
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
HTTP_QUOTA = (430, 431)  # daily scrape quota, too many unrecognized ROMs
NOT_FOUND_PREFIX = "Erreur : Rom"  # plain-text body of a miss (may come with HTTP 200)
# ScreenScraper media type -> scrape_plan.MEDIA_TYPES name. box-3D, support-2D, mixrbv1/2 are unverified.
MEDIA_MAP = {"box-2D": "covers", "box-3D": "3dboxes", "box-2D-back": "backcovers", "ss": "screenshots",
             "sstitle": "titlescreens", "marquee": "marquees", "wheel": "marquees", "wheel-hd": "marquees",
             "video": "videos", "manuel": "manuals", "fanart": "fanart", "support-2D": "physicalmedia",
             "mixrbv1": "miximages", "mixrbv2": "miximages"}
FALLBACK_NAME_REGIONS = ("wor", "us", "ss", "eu", "jp")
FALLBACK_MEDIA_REGIONS = ("wor", "us", "eu", "jp", "cus")
LANGUAGES = ("en",)
VIDEO_TYPE = "videos"
NOTGAME = "ZZZ(NOTGAME)"
RATING_MAX = 20
TIMEOUT = 60
# -----------------------------------------------------------------------------------------------------


class Quota(NamedTuple):
    max_threads: int
    used_today: int
    max_today: int


class NotFound(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class ApiError(Exception):
    pass


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _text(v):
    if isinstance(v, dict):
        v = v.get("text")
    return v.strip() if isinstance(v, str) else ""


def _dicts(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _unwrap(data):
    """The game dict from a whole response, or from the game dict itself."""
    if isinstance(data, dict):
        data = data.get("response", data)
        data = data.get("jeu", data) if isinstance(data, dict) else data
    return data if isinstance(data, dict) else {}


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
    prefs = tuple(regions) + FALLBACK_NAME_REGIONS
    meta = {}
    name = _pick(raw.get("noms"), "region", prefs)
    if name and name != NOTGAME:
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
        rating = round(float(_text(raw.get("note"))) / RATING_MAX, 2)
        if rating > 0:
            meta["rating"] = rating
    except ValueError:
        pass
    date = _release_date(_pick(raw.get("dates"), "region", prefs))
    if date:
        meta["releasedate"] = date

    media_prefs = tuple(regions) + FALLBACK_MEDIA_REGIONS
    best = {}  # folder -> (rank, url)
    for m in _dicts(raw.get("medias")):
        folder = MEDIA_MAP.get(m.get("type"))
        url = m.get("url")
        if not folder or not isinstance(url, str) or not url:
            continue
        region = m.get("region")
        rank = media_prefs.index(region) if region in media_prefs else len(media_prefs) + (region is not None)
        if folder not in best or (folder != VIDEO_TYPE and rank < best[folder][0]):
            best[folder] = (rank, url)
    return meta, {f: u for f, (_, u) in best.items()}


class Client:
    def __init__(self, user, password, dev, opener=urllib.request.urlopen):
        self._auth = {"devid": dev["devid"], "devpassword": dev["devpassword"], "softname": SOFTNAME,
                      "ssid": user, "sspassword": password}
        self._opener = opener

    def _open(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": f"sync-roms/{__version__}"})
        try:
            return self._opener(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code == HTTP_NOT_FOUND:
                raise NotFound("not found") from None
            if e.code in HTTP_QUOTA:
                raise QuotaExceeded(f"ScreenScraper quota exceeded (HTTP {e.code})") from None
            raise ApiError(f"ScreenScraper request failed (HTTP {e.code})") from None
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"ScreenScraper request failed ({type(e).__name__})") from None

    def _get(self, endpoint, **params):
        query = urllib.parse.urlencode({**self._auth, "output": "json", **params})
        with self._open(f"{BASE_URL}{endpoint}?{query}") as resp:
            body = resp.read().decode("utf-8", "replace")
        if body.lstrip().startswith(NOT_FOUND_PREFIX):
            raise NotFound("not found")
        try:
            return json.loads(body)
        except ValueError:
            raise ApiError("ScreenScraper returned an unreadable response") from None

    def quota(self):
        data = self._get(EP_QUOTA)
        user = data.get("response", {}).get("ssuser", {}) if isinstance(data, dict) else {}
        user = user if isinstance(user, dict) else {}
        return Quota(_int(user.get("maxthreads"), 1), _int(user.get("requeststoday")),
                     _int(user.get("maxrequestsperday")))

    def lookup(self, system_id, rom_name, size, md5=None, sha1=None, crc=None):
        params = {"systemeid": system_id, "romnom": rom_name, "romtaille": size}
        params.update({k: v for k, v in (("md5", md5), ("sha1", sha1), ("crc", crc)) if v})
        game = _unwrap(self._get(EP_GAME, **params))
        if not game:
            raise NotFound("not found")
        return game

    def game(self, game_id):
        game = _unwrap(self._get(EP_GAME, gameid=game_id))
        if not game:
            raise NotFound("not found")
        return game

    def search(self, system_id, name):
        data = self._get(EP_SEARCH, systemeid=system_id, recherche=name)
        games = data.get("response", {}).get("jeux", []) if isinstance(data, dict) else []
        out = []
        for g in _dicts(games):
            title = _pick(g.get("noms"), "region", FALLBACK_NAME_REGIONS)
            if g.get("id") and title and title != NOTGAME:
                out.append((_int(g["id"]), title))
        return out

    def download(self, url, dest):
        part = dest + ".part"
        try:
            with self._open(url) as resp, open(part, "wb") as f:
                while chunk := resp.read(1 << 16):
                    f.write(chunk)
            os.replace(part, dest)
        finally:
            if os.path.exists(part):
                os.remove(part)
