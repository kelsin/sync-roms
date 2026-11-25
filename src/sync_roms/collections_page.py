"""The data of the collections page (`sync-roms collections page`): collections, their games, tags and pictures."""
import base64
import io
import json
import os

from . import collections, names, s3, store, tags, themeart, ui

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


def page_data():
    """{"tags", "systems", "collections"} for the page, collections in load_collections() order."""
    defined = _tag_definitions()
    system_names = {s["bucket"]: s["name"] for s in store.repo_json("systems")}
    used, out = set(), []
    for collection in collections.load_collections():
        games = []
        for game in collection["games"]:
            bucket = game["bucket"]
            system = bucket.partition("/")[0]
            used.add(system)
            title = game.get("title")
            games.append({"title": title if isinstance(title, str) and title else names.title(bucket),
                          "system": system,
                          "paths": [bucket, *game.get("files", ())],
                          "tags": [t for t in tags.tags_of(bucket) if t in defined] if defined else []})
        art_id = collection.get("art") or collection["id"]
        out.append({"id": collection["id"], "name": collection["name"], "description": collection["description"],
                    "art": _art(art_id), "games": games})
    return {"tags": {i: {"name": t["name"], "emoji": t["emoji"]} for i, t in defined.items()},
            "systems": {s: system_names.get(s, s) for s in sorted(used)},
            "collections": out}


TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "collections-page.html")


def DEFAULT_PATH():
    """The page `collections page` writes without --out (the folder `collections share` serves)."""
    return os.path.join(store.data_dir(), "share", "collections", "index.html")


def write_page(path):
    """Write the page, the template with page_data() in its data block, to path (folders made, atomically)."""
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    block = json.dumps(page_data()).replace("<", "\\u003c")
    html = html.replace('id="page-data">{}<', f'id="page-data">{block}<', 1)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    store.write_text(path, html)
