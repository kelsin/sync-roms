"""GitHub requests."""
import json as _json
import urllib.request

from . import __version__


def get(url, accept=None):
    headers = {"User-Agent": f"sync-roms/{__version__}", **({"Accept": accept} if accept else {})}
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)


def json(url):
    with get(url, "application/vnd.github+json") as r:
        return _json.load(r)
