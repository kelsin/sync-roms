"""The data of the collections page (`sync-roms collections page`): collections, their games, tags and pictures."""
import base64
import io
import json
import os
import shutil

from . import collections, inventory, languages, metafilter, names, s3, scrape_plan, store, tags, themeart, ui

QUALITY = 80
BAND_WIDTH = 150
BAND_CROP = (50, 600, 343, 1050)  # the band's plain colour around the drawing in y 600..1050


def webp_bytes(path, width=None, crop=None):
    """The picture as WebP bytes, cropped to crop when given, then shrunk to width (never enlarged) when given; None when path is missing."""
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
    return out.getvalue()


def webp_uri(path, width=None, crop=None):
    """A `data:` URI of the picture as WebP (see webp_bytes); None when path is missing."""
    data = webp_bytes(path, width, crop)
    return None if data is None else "data:image/webp;base64," + base64.b64encode(data).decode("ascii")


def _art(art_id, art_dir=None):
    """The collection's pictures by kind; a kind with no file is left out. Each is a `data:` URI, or with art_dir a
    file `<art_id>-<kind>.webp` written there and named `art/<art_id>-<kind>.webp`."""
    band = themeart.art_png(art_id)
    box = themeart.art_png(art_id, "art-box/Imgs_med")
    found = {"band": (band, BAND_WIDTH, BAND_CROP) if band else None,
             "box": (box, None, None) if box else None,
             "totk": (os.path.join(themeart.ZELDA_ART, "Imgs_med", f"{art_id}.png"), None, None)}
    out = {}
    for kind, spec in found.items():
        data = webp_bytes(*spec) if spec else None
        if data is None:
            continue
        if art_dir is None:
            out[kind] = "data:image/webp;base64," + base64.b64encode(data).decode("ascii")
        else:
            name = f"{art_id}-{kind}.webp"
            os.makedirs(art_dir, exist_ok=True)
            with open(os.path.join(art_dir, name), "wb") as f:
                f.write(data)
            out[kind] = f"art/{name}"
    return out


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


def _metadata(systems):
    """{system: scraped metadata.json}; {} when storage isn't reachable."""
    try:
        return {system: scrape_plan.load_metadata(system) for system in sorted(systems)}
    except (SystemExit, ValueError, *s3.ERRORS):
        return {}  # the tags and sizes already warned about unreachable storage


def _years(metadata):
    """{system: {ROM path in the system folder: release year}} from the metadata (games with no year are left out)."""
    return {system: {rom: next(iter(v["year"])) for rom, entry in meta.items()
                     if (v := metafilter.values(entry)).get("year")}
            for system, meta in metadata.items()}


def _game_size(paths, listed):
    """{"rom", "art"} bytes of a game's files (listed: _system_sizes of its system), or None when storage has none of them."""
    if listed is None:
        return None
    roms, art = listed
    found = [p for p in paths if p in roms]
    if not found:
        return None
    return {"rom": sum(roms[p] for p in found), "art": sum(art.get(os.path.splitext(p)[0], 0) for p in found)}


def page_data(public=False, art_dir=None):
    """{"tags", "systems", "collections"} for the page, collections in load_collections() order. public leaves the
    games' storage paths out; art_dir writes the pictures there as files (see _art) instead of embedding them."""
    defined = _tag_definitions()
    system_names = {s["bucket"]: store.short_name(s) for s in store.repo_json("systems")}
    loaded = collections.load_collections()
    sizes = _sizes({g["bucket"].partition("/")[0] for c in loaded for g in c["games"]})
    metadata = _metadata({g["bucket"].partition("/")[0] for c in loaded for g in c["games"]})
    years = _years(metadata)
    used, out = set(), []
    for collection in loaded:
        games = []
        for game in collection["games"]:
            bucket = game["bucket"]
            system = bucket.partition("/")[0]
            used.add(system)
            title = game.get("title")
            paths = [bucket, *game.get("files", ())]
            entry = {"title": names.scraped_name(metadata, bucket) or (title if isinstance(title, str) and title else names.title(bucket)),
                     "system": system,
                     "tags": [t for t in tags.tags_of(bucket) if t in defined] if defined else []}
            if not public:
                entry["paths"] = paths
            if languages.translated(bucket):
                entry["flag"] = languages.flag(bucket)
            size = _game_size(paths, sizes.get(system))
            if size:
                entry["size"] = size
            year = years.get(system, {}).get(bucket.partition("/")[2])
            if year:
                entry["year"] = year
            games.append(entry)
        games.sort(key=lambda g: store.sort_key(g["title"]))
        art_id = collection.get("art") or collection["id"]
        out.append({"id": collection["id"], "name": collection["name"], "description": collection["description"],
                    "art": _art(art_id, art_dir), "size": {k: sum(g.get("size", {}).get(k, 0) for g in games) for k in ("rom", "art")},
                    "games": games})
    return {"tags": {i: {"name": t["name"], "emoji": t["emoji"]} for i, t in defined.items()},
            "systems": {s: system_names.get(s, s) for s in sorted(used)},
            "collections": out}


TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "collections-page")
TEMPLATE_FILES = ("page.html", "page.css", "page.js")


def DEFAULT_PATH():
    """The page `collections page` writes without --out (the folder `collections share` serves)."""
    return os.path.join(store.data_dir(), "share", "collections", "index.html")


def template_files():
    """{"page.html", "page.css", "page.js": text}: the page's template files."""
    files = {}
    for name in TEMPLATE_FILES:
        with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
            files[name] = f.read()
    return files


def fill(html, data):
    """html with data (JSON, `<` escaped) in its empty page-data block."""
    block = json.dumps(data).replace("<", "\\u003c")
    return html.replace('id="page-data">{}<', f'id="page-data">{block}<', 1)


def render(data=None):
    """The self-contained page: the template with its style and script inlined and data (default page_data()) in its data block."""
    files = template_files()
    html = files["page.html"]
    html = html.replace('<link rel="stylesheet" href="page.css">', f"<style>\n{files['page.css']}</style>", 1)
    html = html.replace('<script src="page.js"></script>', f"<script>\n{files['page.js']}</script>", 1)
    return fill(html, page_data() if data is None else data)


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


def write_public(out_dir, home="/"):
    """Build the public page in out_dir, emptied first: index.html (the template's page with its data, no game paths
    and a link to home), page.css, page.js and art/*.webp."""
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    files = template_files()
    data = page_data(public=True, art_dir=os.path.join(out_dir, "art"))
    data["home"] = home
    store.write_text(os.path.join(out_dir, "index.html"), fill(files["page.html"], data))
    for name in ("page.css", "page.js"):
        store.write_text(os.path.join(out_dir, name), files[name])
