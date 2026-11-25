"""PortMaster's ports.json catalogue: cached on disk, refreshed when old, searched by title, genre and description."""
import http.client
import json
import os
import time

from . import github, store, ui

URL = "https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json"
MAX_AGE = 86400
_HTTP_ERRORS = (OSError, http.client.HTTPException)


def path():
    return os.path.join(store.cache_dir(), "portmaster", "ports.json")


def _read(file):
    try:
        with open(file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load(refresh=False, fetch=True):
    """The catalogue, fetched when missing, older than MAX_AGE or refresh (and fetch is true); the cached copy
    when the fetch fails (warned about). None when there is nothing to return."""
    file = path()
    cached = _read(file)
    if not fetch:
        return cached
    try:
        fresh = cached is not None and time.time() - os.path.getmtime(file) < MAX_AGE
    except OSError:
        fresh = False
    if fresh and not refresh:
        return cached
    try:
        with github.get(URL) as r:
            text = r.read().decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not a catalogue")
        os.makedirs(os.path.dirname(file), exist_ok=True)
        store.write_text(file, text)
    except (*_HTTP_ERRORS, ValueError) as e:
        if cached is None:
            ui.warn(f"Couldn't fetch PortMaster's catalogue: {e}")
            return None
        ui.warn(f"Couldn't refresh PortMaster's catalogue, using the cached copy: {e}")
        return cached
    return data


def _is_aarch64(entry):
    arch = (entry.get("attr") or {}).get("arch")
    return not arch or "aarch64" in arch


def ports(catalog):
    """{zip name: entry} of the ports that run on aarch64."""
    return {zip_: e for zip_, e in (catalog.get("ports") or {}).items() if _is_aarch64(e)}


def _title(zip_, entry):
    return (entry.get("attr") or {}).get("title") or entry.get("name") or zip_


def search(catalog, text, needs_data=None):
    """Entries (each with its zip as "zip") whose title, zip name, genres and description hold every word of text,
    by title. needs_data True keeps ports with game data to add (rtr false), False the ready-to-run ones."""
    words = text.casefold().split()
    found = []
    for zip_, entry in ports(catalog).items():
        attr = entry.get("attr") or {}
        if needs_data is not None and (attr.get("rtr") is True) == needs_data:
            continue
        hay = " ".join([_title(zip_, entry), zip_, " ".join(attr.get("genres") or []), attr.get("desc") or ""]).casefold()
        if all(w in hay for w in words):
            found.append({**entry, "zip": zip_})
    return sorted(found, key=lambda e: _title(e["zip"], e).casefold())


def resolve(catalog, name):
    """The zip name for name (`celeste` or `celeste.zip`, any case), or None."""
    want = name.casefold()
    for zip_ in ports(catalog):
        if zip_.casefold() in (want, want + ".zip"):
            return zip_
    return None


def runtime_name(name):
    """The runtime's file name: PortMaster adds .squashfs to a port's runtime name that lacks it."""
    return name if name.endswith(".squashfs") else name + ".squashfs"


def runtimes(entry):
    """The aarch64 runtimes a port needs, by file name."""
    names = (entry.get("attr") or {}).get("runtime") or []
    if isinstance(names, str):
        names = [names]
    names = [runtime_name(n) for n in names if isinstance(n, str) and n]
    return [n for n in names if ".armhf." not in n and ".x86_64." not in n]


def runtime_source(catalog, name):
    """The utils entry of the runtime: the one by that file name, else the aarch64 build whose runtime_name it is."""
    name = runtime_name(name)
    utils = catalog.get("utils") or {}
    direct = utils.get(name)
    if isinstance(direct, dict) and direct.get("runtime_arch") in (None, "aarch64"):
        return direct
    return next((e for e in utils.values() if isinstance(e, dict) and e.get("runtime_name") == name
                 and e.get("runtime_arch") in (None, "aarch64")), None)
