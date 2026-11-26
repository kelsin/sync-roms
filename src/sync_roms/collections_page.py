"""The data of the collections page (`sync-roms collections page`): collections, their games, tags and pictures."""
import base64
import io
import json
import os

from . import collections, inventory, names, s3, scrape_plan, store, tags, themeart, ui

QUALITY = 80
BAND_WIDTH = 150
BAND_CROP = (50, 600, 343, 1050)  # the band's plain colour around the drawing in y 600..1050


def webp_uri(path, width=None, crop=None):
    """A `data:` URI of the picture as WebP, cropped to crop when given, then shrunk to width (never enlarged) when given; None when path is missing."""
    from PIL import Image
    if not os.path.exists(path):
        return None
    with Image.open(path) as image:
        image.load()
        if crop:
            image = image.crop(crop)
        if width and image.width > width:
            image = image.resize((width, max(1, round(image.height * width / image.width))), Image.LANCZOS)
        out = io.BytesIO()
        image.save(out, "WEBP", quality=QUALITY)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def _art(art_id):
    """The collection's pictures by kind; a kind with no file is left out."""
    band = themeart.art_png(art_id)
    box = themeart.art_png(art_id, "art-box/Imgs_med")
    found = {"band": webp_uri(band, BAND_WIDTH, BAND_CROP) if band else None,
             "box": webp_uri(box) if box else None,
             "totk": webp_uri(os.path.join(themeart.ZELDA_ART, "Imgs_med", f"{art_id}.png"))}
    return {kind: uri for kind, uri in found.items() if uri}


def _tag_definitions():
    try:
        return tags.all_tags()
    except (SystemExit, *s3.ERRORS):
        ui.warn("Storage isn't reachable, so the page has no tags.")
        return {}


def _system_sizes(system):
    """(ROM sizes {key: bytes}, art bytes per ROM {key without extension: bytes}) of one system, from one listing of
    its folder and one of scrapes/<system>/ (inventory's, so the cache when there is one). Art is the scraped media
    only: not the Onion or Spruce pictures made from it, not metadata or state files."""
    roms = {k: v for k, v in inventory.files(f"{system}/").items() if isinstance(v, int)}
    art = {}
    for key, size in scrape_plan.scrape_listing(system).items():
        entry = scrape_plan.media_entry(key)
        if entry and entry[1] in scrape_plan.MEDIA_TYPES and isinstance(size, int):
            stem = f"{system}/{entry[0]}"
            art[stem] = art.get(stem, 0) + size
    return roms, art


def _sizes(systems):
    """{system: _system_sizes}; {} (every size unknown) when storage isn't reachable."""
    try:
        return {s: _system_sizes(s) for s in sorted(systems)}
    except (SystemExit, *s3.ERRORS):
        ui.warn("Storage isn't reachable, so the page has no sizes.")
        return {}


def _game_size(paths, listed):
    """{"rom", "art"} bytes of a game's files (listed: _system_sizes of its system), or None when storage has none of them."""
    if listed is None:
        return None
    roms, art = listed
    found = [p for p in paths if p in roms]
    if not found:
        return None
    return {"rom": sum(roms[p] for p in found), "art": sum(art.get(os.path.splitext(p)[0], 0) for p in found)}


def page_data():
    """{"tags", "systems", "collections"} for the page, collections in load_collections() order."""
    defined = _tag_definitions()
    system_names = {s["bucket"]: s["name"] for s in store.repo_json("systems")}
    loaded = collections.load_collections()
    sizes = _sizes({g["bucket"].partition("/")[0] for c in loaded for g in c["games"]})
    used, out = set(), []
    for collection in loaded:
        games = []
        for game in collection["games"]:
            bucket = game["bucket"]
            system = bucket.partition("/")[0]
            used.add(system)
            title = game.get("title")
            paths = [bucket, *game.get("files", ())]
            entry = {"title": title if isinstance(title, str) and title else names.title(bucket),
                     "system": system, "paths": paths,
                     "tags": [t for t in tags.tags_of(bucket) if t in defined] if defined else []}
            size = _game_size(paths, sizes.get(system))
            if size:
                entry["size"] = size
            games.append(entry)
        games.sort(key=lambda g: store.sort_key(g["title"]))
        art_id = collection.get("art") or collection["id"]
        out.append({"id": collection["id"], "name": collection["name"], "description": collection["description"],
                    "art": _art(art_id), "size": {k: sum(g.get("size", {}).get(k, 0) for g in games) for k in ("rom", "art")},
                    "games": games})
    return {"tags": {i: {"name": t["name"], "emoji": t["emoji"]} for i, t in defined.items()},
            "systems": {s: system_names.get(s, s) for s in sorted(used)},
            "collections": out}


TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "collections-page.html")


def DEFAULT_PATH():
    """The page `collections page` writes without --out (the folder `collections share` serves)."""
    return os.path.join(store.data_dir(), "share", "collections", "index.html")


def render():
    """The page: the template with page_data() in its data block."""
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    block = json.dumps(page_data()).replace("<", "\\u003c")
    return html.replace('id="page-data">{}<', f'id="page-data">{block}<', 1)


def write_page(path):
    """Write the page to path (folders made, atomically)."""
    html = render()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    store.write_text(path, html)


def update_page(path):
    """Write the page unless path already holds exactly it. True when written (missing or out of date)."""
    html = render()
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == html:
                return False
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    store.write_text(path, html)
    return True
