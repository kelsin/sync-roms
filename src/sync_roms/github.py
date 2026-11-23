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


def length(response):
    """The response's Content-Length as an int, or None."""
    value = getattr(response, "headers", None) and response.headers.get("Content-Length")
    return int(value) if value and value.isdigit() else None


def save(response, path, callback=None):
    """Stream an open response to path in chunks, calling callback(bytes) per chunk."""
    with open(path, "wb") as f:
        while chunk := response.read(1 << 16):
            f.write(chunk)
            if callback:
                callback(len(chunk))


def download(url, path, callback=None):
    """Stream url to path, calling callback(bytes) per chunk. Returns the Content-Length, or None when there is none."""
    with get(url) as r:
        save(r, path, callback)
        return length(r)
