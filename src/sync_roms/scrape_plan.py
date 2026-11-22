"""Planning and applying scrape data on the card."""
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import cardfs, downloads, frontend, inventory, runtime, s3, shared, store, ui


# --- Scraped data (media, metadata) --------------------------------
# Lives in storage under scrapes/. Metadata is neutral JSON with only the fields that are safe
# to share; media keeps ES-DE's media type folder names.
SCRAPES = "scrapes"
MEDIA_TYPES = {"3dboxes", "backcovers", "covers", "custom", "fanart", "manuals", "marquees",
               "miximages", "physicalmedia", "screenshots", "titlescreens", "videos"}
# Onion's box art is made at upload time (PNG, at most 250x360) from the first of ONION_ART found locally
# and stored as scrapes/<system>/onion/<ROM name>.png, so a sync only downloads it.
ONION_TYPE = "onion"
ONION_ART = ("covers", "3dboxes", "screenshots")
ONION_MAX = (250, 360)
BUCKET_MEDIA = MEDIA_TYPES | {ONION_TYPE}
TEXT_FIELDS = ("name", "desc", "developer", "publisher", "genre", "players")


def metadata_key(system):
    return f"{SCRAPES}/{system}/metadata.json"


def load_metadata(system, fresh=False):
    """A system's metadata.json from storage ({} when there is none), read through the local mirror when a sync has one,
    or with fresh from storage itself. Raises ValueError if it isn't a JSON object."""
    key = metadata_key(system)
    if fresh:
        s3.check_root()  # an unmounted share, not a missing file
    try:
        text = shared.read(key) if fresh else s3.get_text(key)
    except s3.ERRORS as e:
        if not s3.missing(e):
            raise
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{key} isn't a JSON object")
    return data


def dump_json(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def merge_metadata(remote, local):
    """Local values replace storage's; entries (and fields) only in storage are kept."""
    merged = {k: dict(v) for k, v in remote.items()}
    for rom, fields in local.items():
        merged[rom] = {**merged.get(rom, {}), **fields}
    return merged


def walk_files(root, skip_top=()):
    """(relative path with /, full path) of every non-hidden file under root."""
    for dp, dns, fns in cardfs.walk(root):
        at_root = os.path.normpath(dp) == os.path.normpath(root)
        dns[:] = sorted(d for d in dns if not d.startswith(".") and not (at_root and d in skip_top))
        for f in sorted(fns):
            if not f.startswith("."):
                full = os.path.join(dp, f)
                yield os.path.relpath(full, root).replace(os.sep, "/"), full


# --- Installing scraped data ------------------------------------------------------------------------
# A sync places storage's scrapes/ data for the chosen systems on the card, converted for the layout:
# esde keeps ES-DE's media folders and gamelists, knulli and rocknix get images/videos/manuals and a gamelist.xml
# with explicit media tags, onion gets the box art made for it at upload time in Imgs/ and a miyoogamelist.xml.
# Knulli: (gamelist tag, folder, file suffix, ES-DE media types to take it from; first one found wins)
KNULLI_MEDIA = (
    ("image", "images", "image", ("miximages", "screenshots")),
    ("thumbnail", "images", "thumb", ("covers",)),
    ("marquee", "images", "marquee", ("marquees",)),
    ("fanart", "images", "fanart", ("fanart",)),
    ("boxback", "images", "boxback", ("backcovers",)),
    ("titleshot", "images", "titleshot", ("titlescreens",)),
    ("video", "videos", "video", ("videos",)),
    ("manual", "manuals", "manual", ("manuals",)),
)
KNULLI_SUFFIXES = {"image", "thumb", "marquee", "fanart", "boxback", "titleshot", "bezel", "boxart",
                   "cartridge", "mix", "wheel", "map", "video", "manual", "magazine", "music"}
GAMELIST_FILES = {"esde": "gamelist.xml", "emudeck": "gamelist.xml", "knulli": "gamelist.xml", "rocknix": "gamelist.xml", "onion": "miyoogamelist.xml",
                  "allium": "gamelist.xml", "spruce": "miyoogamelist.xml", "nextui": None}  # None: no gamelist, the art is found by name in .media/
ONION_ONLY_LISTS = ("recentlist-hidden.json", "favorite.json")  # in the root of Onion's roms folder
ONION_LAYOUTS = ("onion", "allium", "spruce")  # all keep box art in a flat Imgs/ folder
# muOS catalogue art, MUOS/info/catalogue/<system's muos_catalogue>/<folder>/<ROM name>.<ext>, and the media types that fill it
MUOS_MEDIA = (("box", ("covers", "3dboxes")), ("preview", ("screenshots", "titlescreens")))
# EmuDeck's media goes on the card; its gamelists go in ES-DE's data folder on the computer running the sync
SCRAPE_LAYOUTS = set(GAMELIST_FILES) | {"muos"}
EMUDECK_MEDIA = os.path.join("Emulation", "tools", "downloaded_media")
CART_LAYOUTS = (*frontend.ESDE_LAYOUTS, "knulli", "rocknix", "nextui") + ONION_LAYOUTS  # a PICO-8 cart with no scraped picture is its own: these show it as its image


def gamelist_fields(meta):
    """gamelist.xml tags (as text) for one ROM's stored metadata."""
    out = {f: meta[f] for f in TEXT_FIELDS if f in meta}
    if "rating" in meta:
        out["rating"] = format(meta["rating"], "g")
    if "releasedate" in meta:
        out["releasedate"] = meta["releasedate"].replace("-", "") + "T000000"
    return out


def _index_entry(key):
    """(ROM stem, media type) of a scrapes/<system>/<type>/<ROM path>.<ext> key, or None for any other key."""
    parts = key.split("/")
    if len(parts) > 3 and parts[2] in BUCKET_MEDIA:
        return os.path.splitext("/".join(parts[3:]))[0], parts[2]
    return None


def scrape_index(listing):
    """{ROM path without extension: {media type: (key, size)}} from a listing of scrapes/<system>/."""
    index = defaultdict(dict)
    for key, size in sorted(listing.items()):
        index_add(index, key, size)
    return index


def index_add(index, key, size):
    """Add one listing entry to a scrape_index (the first key of a stem and type stays)."""
    entry = _index_entry(key)
    if entry:
        index[entry[0]].setdefault(entry[1], (key, size))


def index_drop(index, key):
    """Remove one listing entry from a scrape_index."""
    entry = _index_entry(key)
    if entry and index.get(entry[0], {}).get(entry[1], (None,))[0] == key:
        del index[entry[0]][entry[1]]


def nextui_art(rom):
    """Where NextUI looks for a ROM's art (rom: its path in the system folder), without the extension: .media/ in the
    entry's own folder, named by the entry (nextui.c's thumbnail path). A folder holding a .cue or .m3u of its own name
    is the entry (NextUI launches it), so that game's art sits beside the folder."""
    folder, stem = os.path.split(os.path.splitext(rom)[0])
    if folder and os.path.basename(folder) == stem and rom.lower().endswith((".cue", ".m3u")):
        folder = os.path.dirname(folder)
    return os.path.join(folder, ".media", stem)


def plan_scrapes(layout_name, rom_rels, listing, meta, media_root, rom_dir, present, join=s3.safe_join, index=None):
    """Media downloads, gamelist entries and text files for one system's ROMs.

    rom_rels: ROM paths in the system folder; media_root: the system's media folder (esde's downloaded_media
    folder or muOS's catalogue folder); rom_dir: the system's ROM folder on the card;
    present(rom): is that ROM (going to be) on the card;
    join(root, rel): a job's local path (scrape_cost, which only adds up sizes, skips the path checks);
    index: scrape_index(listing) when already built (listing is then not read).
    Returns (jobs [(key, local path, size)], entries {ROM path: {gamelist tag: text}}, texts [(local path, text)]).
    """
    index = scrape_index(listing) if index is None else index
    jobs, entries, texts = [], {}, []

    def add(key, root, rel, size):
        try:
            jobs.append((key, join(root, rel), size))
        except ValueError as e:
            print(ui.yellow(f"  ⚠️  skipping {e}"))
    for rom in sorted(rom_rels):
        if not present(rom):
            continue
        stem = os.path.splitext(rom)[0]
        found = index.get(stem, {})
        tags = gamelist_fields(meta.get(rom, {}))
        base = os.path.basename(stem)
        if layout_name == "muos":  # the catalogue is flat, even when the ROM is in a subfolder
            for folder, types in MUOS_MEDIA:
                mtype = next((t for t in types if t in found), None)
                if mtype:
                    key, size = found[mtype]
                    add(key, media_root, f"{folder}/{base}{os.path.splitext(key)[1]}", size)
            if meta.get(rom, {}).get("desc"):
                texts.append((os.path.join(media_root, "text", base + ".txt"), meta[rom]["desc"] + "\n"))
            continue
        if layout_name in frontend.ESDE_LAYOUTS:
            for mtype, (key, size) in found.items():
                if mtype in MEDIA_TYPES:  # not the Onion-only art
                    add(key, media_root, f"{mtype}/{key.split('/', 3)[3]}", size)
        elif layout_name in ("knulli", "rocknix"):
            for tag, folder, suffix, types in KNULLI_MEDIA:
                mtype = next((t for t in types if t in found), None)
                if mtype:
                    key, size = found[mtype]
                    name = f"{base}-{suffix}{os.path.splitext(key)[1]}"
                    add(key, rom_dir, f"{folder}/{name}", size)
                    tags[tag] = f"./{folder}/{name}"
        elif layout_name in ONION_LAYOUTS:
            if "/" in rom:  # Imgs is flat and the gamelist only lists the folder's own files
                continue
            # Onion's and Spruce's miyoogamelist.xml take name and image only; Allium's gamelist.xml also reads the rest
            keep = ("name",) if layout_name != "allium" else ("name", "developer", "publisher", "genre", "rating", "releasedate")
            tags = {k: v for k, v in tags.items() if k in keep}
            if layout_name == "allium":  # Allium fails to parse the whole list if a <game> has no <name>
                tags.setdefault("name", base)
            if ONION_TYPE in found:
                key, size = found[ONION_TYPE]
                add(key, rom_dir, f"Imgs/{base}.png", size)
                tags["image"] = f"./Imgs/{base}.png"
        elif layout_name == "nextui":  # no gamelist: the art is found by name in .media/ beside the game
            tags = {}
            if ONION_TYPE in found:
                key, size = found[ONION_TYPE]
                add(key, rom_dir, nextui_art(rom) + ".png", size)
        if tags:
            entries[rom] = tags
    return jobs, entries, texts


def scrape_cost(layout_name, system, rom_rel, listing, index=None):
    """Bytes of scraped files a sync would install for one ROM (rom_rel: its path in the system folder) under a
    layout, from a listing of scrapes/<system>/ with sizes (or its scrape_index); 0 for a layout without scrapes or a
    ROM with none."""
    if layout_name not in SCRAPE_LAYOUTS:
        return 0
    jobs, _, _ = plan_scrapes(layout_name, [rom_rel], listing, {}, "/media", "/roms", lambda rom: True,
                              join=lambda root, rel: None, index=index)
    return sum(size or 0 for _, _, size in jobs)


NO_SHRINK = "Onion box art needs Pillow or macOS sips to resize images"


def can_shrink():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return bool(shutil.which("sips"))


def shrink_png(src, dst, box=ONION_MAX):
    """Write src as a PNG that fits in box (never enlarged), with Pillow or macOS sips."""
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image:
        with Image.open(src) as im:
            im.thumbnail(box)
            im.save(dst, "PNG", optimize=True)
        return
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                         check=True, capture_output=True, text=True).stdout
    dims = [re.search(rf"{k}: (\d+)", out) for k in ("pixelWidth", "pixelHeight")]  # sips exits 0 for a file it can't read
    if not all(dims):
        raise ValueError(f"not a readable image: {src}")
    w, h = (int(m.group(1)) for m in dims)
    scale = min(1, box[0] / w, box[1] / h)
    subprocess.run(["sips", "-s", "format", "png", "-z", str(max(1, round(h * scale))), str(max(1, round(w * scale))),
                    src, "--out", dst], check=True, capture_output=True)


def update_gamelist(path, entries):
    """Set the given tags on each ROM's <game> in a gamelist file, creating the file and entries as needed.

    Everything else in the file is kept (favorites, play counts, an <alternativeEmulator> block...).
    Returns True if the file was written.
    """
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    m = re.search(r"<gameList\b[^>]*/>", text) or re.search(r"<gameList\b.*</gameList>", text, re.S)
    prefix = text[:m.start()] if m else '<?xml version="1.0"?>\n'
    root = ET.fromstring(m.group(0)) if m else ET.Element("gameList")
    games = {(g.findtext("path") or "").strip(): g for g in root.findall("game")}
    changed = not m
    for rom, tags in entries.items():
        game = games.get("./" + rom)
        if game is None:
            game = ET.SubElement(root, "game")
            ET.SubElement(game, "path").text = "./" + rom
            games["./" + rom] = game
            changed = True
        for tag, value in tags.items():
            el = game.find(tag)
            if el is None:
                el = ET.SubElement(game, tag)
            if el.text != value:
                el.text = value
                changed = True
    if not changed:
        return False
    ET.indent(root, space="\t")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.replace_file(path, prefix + ET.tostring(root, encoding="unicode") + "\n", newline="")
    return True


def load_scrape_data(systems):
    """The storage's scrape data for the chosen systems: {storage folder: (listing, metadata)}."""
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = list(ex.map(lambda s: inventory.files(f"{SCRAPES}/{s['bucket']}/", sizes=False), systems))
    meta_keys = [metadata_key(s["bucket"]) for s, l in zip(systems, listings) if metadata_key(s["bucket"]) in l]
    texts = s3.fetch_texts(meta_keys)
    data = {}
    for s, listing in zip(systems, listings):
        key = metadata_key(s["bucket"])
        try:
            meta = json.loads(texts[key]) if key in texts else {}
        except ValueError:
            meta = {}
        data[s["bucket"]] = (listing, meta)
    return data


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def esde_name(system, layout_name="esde"):
    """ES-DE's name for a system, which its media and gamelist folders use: the first part of its ROM folder in the
    layout (so systems that share a ROM folder share them), or its bucket when the layout has no folder for it."""
    return (system["folders"].get(layout_name) or system["bucket"]).split("/")[0]


def media_root_of(layout_name, system, base, es_dir):
    """The folder a system's scraped media goes in, for layouts that keep it apart from the ROMs."""
    if layout_name == "muos":
        return os.path.join(base, "MUOS", "info", "catalogue", system["muos_catalogue"])
    if layout_name == "emudeck":
        return os.path.join(base, EMUDECK_MEDIA, esde_name(system, "emudeck"))
    return os.path.join(es_dir, "downloaded_media", esde_name(system))


def build_scrape_plan(layout_name, systems, data, rom_rels, dest_of, es_dir, present, base, recheck=None):
    """Everything a sync installs from scrapes/: media jobs, gamelist entries per file, text files.

    es_dir: ES-DE's data folder, where esde and emudeck gamelists go (for emudeck, the one on this computer).
    recheck: the local paths of an earlier plan's media jobs; the media it found current are left out unchecked."""
    plan = {"jobs": [], "gamelists": defaultdict(dict), "writes": []}
    for s in systems:
        listing, meta = data[s["bucket"]]
        rom_dir = dest_of(s)
        media_root = media_root_of(layout_name, s, base, es_dir)
        carts = s["bucket"] == "pico8" and layout_name in CART_LAYOUTS
        jobs, entries, texts = plan_scrapes(layout_name, rom_rels.get(s["bucket"], ()), listing, meta,
                                            media_root, rom_dir, lambda rom, d=rom_dir: present(os.path.join(d, rom)))
        if carts:  # a cart without a scraped picture is its own picture
            index = scrape_index(listing)
            for rom in sorted(rom_rels.get(s["bucket"], ())):
                if not rom.endswith(".p8.png") or not present(os.path.join(rom_dir, rom)):
                    continue
                found = index.get(os.path.splitext(rom)[0], {})
                if layout_name in ("knulli", "rocknix"):  # the cart is already in the ROM folder
                    if "image" not in entries.get(rom, {}):
                        entries.setdefault(rom, {})["image"] = f"./{rom}"
                    continue
                if layout_name == "nextui":
                    if ONION_TYPE in found:
                        continue
                    root, rel = rom_dir, nextui_art(rom) + ".png"
                elif layout_name in ONION_LAYOUTS:
                    if "/" in rom or ONION_TYPE in found:  # Imgs is flat
                        continue
                    root, rel = rom_dir, f"Imgs/{rom}"
                    entries.setdefault(rom, {})["image"] = f"./Imgs/{rom}"
                else:
                    if "miximages" in found:
                        continue
                    root, rel = media_root, f"miximages/{rom}"
                try:
                    jobs.append((f"{s['bucket']}/{rom}", s3.safe_join(root, rel), None))
                except ValueError as e:
                    print(ui.yellow(f"  ⚠️  skipping {e}"))
        jobs = downloads.with_sizes(jobs)  # sizes only for media that could be installed
        listing.update((k, size) for k, _, size in jobs)  # kept, so a rebuild of the plan reads none of them again
        plan["jobs"] += downloads.plan_downloads(jobs if recheck is None else [j for j in jobs if j[1] in recheck])
        for path, text in texts:  # only the ones that would change
            if not os.path.exists(path) or read_text(path) != text:
                plan["writes"].append((path, text))
        if entries and GAMELIST_FILES[layout_name]:
            gl = (os.path.join(es_dir, "gamelists", esde_name(s, layout_name)) if layout_name in frontend.ESDE_LAYOUTS
                  else rom_dir)
            plan["gamelists"][os.path.join(gl, GAMELIST_FILES[layout_name])].update(entries)
    return plan


def describe_scrape_plan(plan):
    jobs = plan["jobs"]
    print(f"🖼️  Scraped data: {ui.bold(str(len(jobs)))} file(s) to download "
          f"({ui.human_size(sum(j[2] or 0 for j in jobs))}), {len(plan['gamelists'])} gamelist file(s) to update"
          + (f", {len(plan['writes'])} text file(s)" if plan["writes"] else ""))


def apply_scrape_plan(plan, base, failures=None):
    """Download the media, then write the gamelists and text files. Returns (failures, whether anything was written
    to the card at base); failures, if given, collects (key, reason) for each failed download."""
    failed = downloads.run_downloads(plan["jobs"], "Scraped data", "🖼️", base, failures) if plan["jobs"] else 0
    wrote = failed < len(plan["jobs"])
    for path, entries in plan["gamelists"].items():
        try:
            # EmuDeck's gamelists are on this computer, not the card
            if update_gamelist(path, entries) and os.path.realpath(path).startswith(os.path.realpath(base) + os.sep):
                wrote = True
        except (ET.ParseError, OSError, UnicodeDecodeError) as e:
            failed += 1
            ui.failure(ui.red(f"  ❌ {path}: {e}"))
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.replace_file(path, text, newline="")
        wrote = True
    return failed, wrote


def card_stems(rom_dir, flat, skip_db=False):
    """ROM names without extension in a system's ROM folder (base names only if flat)."""
    stems = set()
    for root, files in downloads.walk_roms(rom_dir, skip_db=skip_db):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), rom_dir).replace(os.sep, "/")
            stems.add(os.path.splitext(os.path.basename(rel) if flat else rel)[0])
    return stems


def media_name(layout_name, name):
    """How a firmware compares art names with ROM names: muOS ignores case."""
    return name.strip().lower()


def stale_firmware_media(layout_name, systems, roms_dir, base):
    """Art files in muOS's catalogue (box, preview and text) whose ROM isn't on the card.

    Systems that share a catalogue folder are judged together. A folder whose ROM folders hold no ROMs is left alone.
    """
    groups = defaultdict(list)
    for s in systems:
        if s["folders"].get(layout_name):
            groups[media_root_of(layout_name, s, base, "")].append(os.path.join(roms_dir, s["folders"][layout_name]))
    stale = []
    for root, rom_dirs in sorted(groups.items()):
        stems = {media_name(layout_name, stem) for d in set(rom_dirs) if os.path.isdir(d) for stem in card_stems(d, True, layout_name in ONION_LAYOUTS)}
        if not stems:
            continue
        for sub in ("box", "preview", "text"):
            folder = os.path.normpath(os.path.join(root, sub))
            for rel, full in walk_files(folder) if os.path.isdir(folder) else []:
                if media_name(layout_name, os.path.splitext(os.path.basename(rel))[0]) not in stems:
                    stale.append(full)
    return stale


def stale_media(layout_name, systems, roms_dir, es_dir, base=None):
    """Media files on the card whose ROM isn't in the system's ROM folder, for every system in the
    layout (not just the ones being synced). Systems with no ROM folder are left alone. es_dir: ES-DE's data folder
    (for emudeck, the one on this computer, or None when it doesn't serve the card: its gamelists are left alone)."""
    stale, seen = [], set()
    if layout_name == "muos":
        return stale_firmware_media(layout_name, systems, roms_dir, base)
    named = {esde_name(x, layout_name) for x in systems}
    for s in systems:
        folder = s["folders"].get(layout_name)
        rom_dir = os.path.join(roms_dir, folder) if folder else None
        if not rom_dir or rom_dir in seen or not cardfs.is_dir(rom_dir):
            continue
        seen.add(rom_dir)
        stems = card_stems(rom_dir, layout_name not in frontend.ESDE_LAYOUTS, layout_name in ONION_LAYOUTS)
        if layout_name in frontend.ESDE_LAYOUTS:
            for mtype in sorted(MEDIA_TYPES):
                media = os.path.join(media_root_of(layout_name, s, base, es_dir), mtype)
                stale += [full for rel, full in walk_files(media) if os.path.splitext(rel)[0] not in stems] \
                    if cardfs.is_dir(media) else []
            old = s["bucket"]  # an older sync named the folders after the bucket: all of it is stale once the ES-DE one exists
            if old != esde_name(s, layout_name) and old not in named and cardfs.is_dir(media_root_of(layout_name, s, base, es_dir)):
                stale += [full for _, full in walk_files(media_root_of(layout_name, {"folders": {}, "bucket": old}, base, es_dir))]
                if es_dir:
                    stale += [path for path in [os.path.join(es_dir, "gamelists", old, GAMELIST_FILES[layout_name])]
                              if cardfs.size(path) is not None]
        elif layout_name in ("knulli", "rocknix"):
            for sub in ("images", "videos", "manuals"):
                base = os.path.join(rom_dir, sub)
                for rel, full in walk_files(base) if cardfs.is_dir(base) else []:
                    name = os.path.splitext(os.path.basename(rel))[0]
                    if name not in stems and not any(name.endswith("-" + x) and name[:-len(x) - 1] in stems
                                                     for x in KNULLI_SUFFIXES):
                        stale.append(full)
        elif layout_name == "nextui":  # only the PNGs in each folder's .media/ (a hidden folder walk_files skips) that no ROM names
            walked = list(downloads.walk_roms(rom_dir))
            arts = {nextui_art(os.path.relpath(os.path.join(root, f), rom_dir)) for root, files in walked for f in files}
            for root, _ in walked:
                media = os.path.join(root, ".media")
                stale += [os.path.join(media, f) for f in sorted(cardfs.listing(media))
                          if f.lower().endswith(".png") and os.path.relpath(os.path.join(media, os.path.splitext(f)[0]), rom_dir) not in arts] \
                    if cardfs.is_dir(media) else []
        elif layout_name in ONION_LAYOUTS:
            base = os.path.join(rom_dir, "Imgs")
            stale += [full for rel, full in walk_files(base) if os.path.splitext(os.path.basename(rel))[0] not in stems] \
                if cardfs.is_dir(base) else []
            # the other Onion-family firmware's gamelist, once this layout's own has replaced it
            other = GAMELIST_FILES["onion" if layout_name == "allium" else "allium"]
            if cardfs.exists(os.path.join(rom_dir, GAMELIST_FILES[layout_name])) \
                    and cardfs.exists(os.path.join(rom_dir, other)):
                stale.append(os.path.join(rom_dir, other))
            if not stems:  # an empty system: its gamelists and ROM list caches go too, so the firmware doesn't show it
                stale += [os.path.join(rom_dir, f) for f in sorted(cardfs.listing(rom_dir))
                          if f in GAMELIST_FILES.values() or f.lower().endswith(".db")]
    if layout_name == "allium":  # Onion OS's lists of recent and favourite games, which Allium doesn't use
        stale += [path for f in ONION_ONLY_LISTS if cardfs.size(path := os.path.join(roms_dir, f)) is not None]
    return list(dict.fromkeys(stale))


def prune_empty_systems(layout_name, systems, roms_dir):
    """Remove the Onion-family ROM folders (and their Imgs) that hold no ROMs and nothing else. Returns the folders removed."""
    removed = []
    if layout_name not in ONION_LAYOUTS:
        return removed
    for rom_dir in sorted({os.path.join(roms_dir, s["folders"][layout_name]) for s in systems if s["folders"].get(layout_name)}):
        if not cardfs.is_dir(rom_dir) or card_stems(rom_dir, False, True):
            continue
        imgs = os.path.join(rom_dir, "Imgs")
        for dp, _, _ in sorted(cardfs.walk(imgs), reverse=True):  # deepest first
            try:
                os.rmdir(dp)
            except OSError:
                pass
        try:
            os.rmdir(rom_dir)
            removed.append(rom_dir)
        except OSError:  # something else lives there
            pass
    return removed
