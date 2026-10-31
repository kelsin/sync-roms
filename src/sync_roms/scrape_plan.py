"""Planning and applying scrape data on the card."""
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape, unescape

from . import downloads, runtime, s3, ui


# --- Scraped data (media, metadata, themes, collections, settings) --------------------------------
# Lives in the bucket under scrapes/. Metadata is neutral JSON with only the fields that are safe
# to share; media keeps ES-DE's media type folder names.
SCRAPES = "scrapes"
MEDIA_TYPES = {"3dboxes", "backcovers", "covers", "custom", "fanart", "manuals", "marquees",
               "miximages", "physicalmedia", "screenshots", "titlescreens", "videos"}
# Onion's box art is made at upload time (PNG, at most 250x360) from the first of ONION_ART found locally
# and stored as scrapes/<system>/onion/<ROM name>.png, so a sync only downloads it.
ONION_TYPE = "onion"
ONION_ART = ("covers", "3dboxes", "screenshots")
ONION_MAX = (250, 360)
# Slot's cart labels are made the same way (PNG fitting the cart's label size), by system, stored as
# scrapes/<system>/slot/<ROM name>.png.
SLOT_TYPE = "slot"
SLOT_ART = ("covers", "3dboxes", "screenshots")
SLOT_LABEL_MAX = {"gba": (1280, 661), "gb": (1024, 914), "gbc": (1024, 914)}
BUCKET_MEDIA = MEDIA_TYPES | {ONION_TYPE, SLOT_TYPE}
TEXT_FIELDS = ("name", "desc", "developer", "publisher", "genre", "players")
UNKNOWN_FIELDS = {"developer", "publisher", "genre", "players"}  # ES-DE writes "unknown" for these
SETTING_PREFIXES = ("Scrape", "Miximage", "Theme")  # Scrape covers Scrape* and Scraper*
SETTING_EXCLUDE = {"ScraperUsernameScreenScraper", "ScraperPasswordScreenScraper",
                   "ScraperUseAccountScreenScraper", "ThemeAspectRatio"}
SETTING_UI = {"DefaultSortOrder", "FavoritesFirst", "FavoritesStar", "FavoritesAddButton",
              "FavStarCustom", "FavFirstCustom", "FoldersOnTop", "GamelistFilters", "ShowHiddenFiles",
              "ShowHiddenGames", "SaveGamelistsMode", "AlternativeEmulatorPerGame", "StartupView",
              "QuickSystemSelect", "RandomEntryButton", "ListScrollOverlay", "MAMENameStripExtraInfo",
              "CollectionCustomGrouping", "SystemsSorting"}
SETTING_LINE = re.compile(r'<(bool|int|string)\s+name="([^"]+)"\s+value="([^"]*)"\s*/>')


def dump_json(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def parse_gamelist(text):
    """{ROM path: safe fields} from an ES-DE gamelist.xml. Raises ET.ParseError if it is malformed.

    Only the <gameList> block is read: ES-DE can write an <alternativeEmulator> element before it,
    which leaves two top-level elements. Only the scraped fields are kept (no favorites, play
    counts, emulator choices or media tags), and values ES-DE writes for "nothing" are dropped.
    """
    m = re.search(r"<gameList\b.*</gameList>", text, re.S)
    games = {}
    if not m:
        return games
    for g in ET.fromstring(m.group(0)).findall("game"):
        path = (g.findtext("path") or "").strip()
        if not path.startswith("./"):
            continue
        fields = {}
        for f in TEXT_FIELDS:
            v = (g.findtext(f) or "").strip()
            if v and not (f in UNKNOWN_FIELDS and v.lower() == "unknown"):
                fields[f] = v
        try:
            rating = round(float(g.findtext("rating") or 0), 2)
        except ValueError:
            rating = 0
        if rating > 0:
            fields["rating"] = rating
        d = (g.findtext("releasedate") or "").strip()
        if re.match(r"\d{8}T", d) and not d.startswith("1970"):
            fields["releasedate"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        games[path[2:]] = fields
    return games


def merge_metadata(remote, local):
    """Local values replace the bucket's; entries (and fields) only in the bucket are kept."""
    merged = {k: dict(v) for k, v in remote.items()}
    for rom, fields in local.items():
        merged[rom] = {**merged.get(rom, {}), **fields}
    return merged


def merge_lines(remote, local):
    """Union of the lines of two text files: remote lines first, then new local ones."""
    seen, out = set(), []
    for line in (remote + "\n" + local).splitlines():
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return "\n".join(out) + "\n" if out else ""


def share_setting(name):
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        return False
    if re.search(r"password|username|passkey", name, re.I) or name in SETTING_EXCLUDE:
        return False
    return name.startswith(SETTING_PREFIXES) or name in SETTING_UI


def safe_settings(text):
    """{name: typed value} for the ES-DE settings that are safe to share, from es_settings.xml."""
    out = {}
    for kind, name, value in SETTING_LINE.findall(text):
        if not share_setting(name):
            continue
        value = unescape(value, {"&quot;": '"', "&apos;": "'"})
        try:
            out[name] = (value == "true") if kind == "bool" else int(value) if kind == "int" else value
        except ValueError:
            pass
    return out


def walk_files(root, skip_top=()):
    """(relative path with /, full path) of every non-hidden file under root."""
    for dp, dns, fns in os.walk(root):
        at_root = os.path.normpath(dp) == os.path.normpath(root)
        dns[:] = sorted(d for d in dns if not d.startswith(".") and not (at_root and d in skip_top))
        for f in sorted(fns):
            if not f.startswith("."):
                full = os.path.join(dp, f)
                yield os.path.relpath(full, root).replace(os.sep, "/"), full


# --- Installing scraped data ------------------------------------------------------------------------
# A sync places the bucket's scrapes/ data for the chosen systems on the card, converted for the layout:
# esde keeps ES-DE's media folders and gamelists, knulli gets images/videos/manuals and a gamelist.xml
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
GAMELIST_FILES = {"esde": "gamelist.xml", "knulli": "gamelist.xml", "onion": "miyoogamelist.xml"}
# muOS catalogue art, MUOS/info/catalogue/<system's muos_catalogue>/<folder>/<ROM name>.<ext>, and the media types that fill it
MUOS_MEDIA = (("box", ("covers", "3dboxes")), ("preview", ("screenshots", "titlescreens")))
SCRAPE_LAYOUTS = set(GAMELIST_FILES) | {"muos", "slot"}


def gamelist_fields(meta):
    """gamelist.xml tags (as text) for one ROM's stored metadata."""
    out = {f: meta[f] for f in TEXT_FIELDS if f in meta}
    if "rating" in meta:
        out["rating"] = format(meta["rating"], "g")
    if "releasedate" in meta:
        out["releasedate"] = meta["releasedate"].replace("-", "") + "T000000"
    return out


def scrape_index(listing):
    """{ROM path without extension: {media type: (key, size)}} from a listing of scrapes/<system>/."""
    index = defaultdict(dict)
    for key, size in sorted(listing.items()):
        parts = key.split("/")
        if len(parts) > 3 and parts[2] in BUCKET_MEDIA:
            index[os.path.splitext("/".join(parts[3:]))[0]].setdefault(parts[2], (key, size))
    return index


def plan_scrapes(layout_name, rom_rels, listing, meta, media_root, rom_dir, present):
    """Media downloads, gamelist entries and text files for one system's ROMs.

    rom_rels: ROM paths in the system folder; media_root: the system's media folder (esde's downloaded_media
    folder, muOS's catalogue folder or Slot's Labels folder); rom_dir: the system's ROM folder on the card;
    present(rom): is that ROM (going to be) on the card.
    Returns (jobs [(key, local path, size)], entries {ROM path: {gamelist tag: text}}, texts [(local path, text)]).
    """
    index = scrape_index(listing)
    jobs, entries, texts = [], {}, []

    def add(key, root, rel, size):
        try:
            jobs.append((key, s3.safe_join(root, rel), size))
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
        if layout_name == "slot":
            if SLOT_TYPE in found:
                key, size = found[SLOT_TYPE]
                add(key, media_root, base + ".png", size)
            continue
        if layout_name == "esde":
            for mtype, (key, size) in found.items():
                if mtype in MEDIA_TYPES:  # not the Onion-only art
                    add(key, media_root, f"{mtype}/{key.split('/', 3)[3]}", size)
        elif layout_name == "knulli":
            for tag, folder, suffix, types in KNULLI_MEDIA:
                mtype = next((t for t in types if t in found), None)
                if mtype:
                    key, size = found[mtype]
                    name = f"{base}-{suffix}{os.path.splitext(key)[1]}"
                    add(key, rom_dir, f"{folder}/{name}", size)
                    tags[tag] = f"./{folder}/{name}"
        elif layout_name == "onion":
            if "/" in rom:  # Onion's Imgs folder is flat and its gamelist ignores subfolders
                continue
            tags = {"name": tags["name"]} if "name" in tags else {}
            if ONION_TYPE in found:
                key, size = found[ONION_TYPE]
                add(key, rom_dir, f"Imgs/{base}.png", size)
                tags["image"] = f"./Imgs/{base}.png"
        if tags:
            entries[rom] = tags
    return jobs, entries, texts


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
    w, h = (int(re.search(rf"{k}: (\d+)", out).group(1)) for k in ("pixelWidth", "pixelHeight"))
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
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(prefix + ET.tostring(root, encoding="unicode") + "\n")
    return True


def setting_line(name, value):
    if isinstance(value, bool):
        return f'<bool name="{name}" value="{str(value).lower()}" />'
    if isinstance(value, int):
        return f'<int name="{name}" value="{value}" />'
    return f'<string name="{name}" value="{escape(str(value), {chr(34): "&quot;"})}" />'


def update_settings(text, settings):
    """es_settings.xml text with the given typed settings set: lines replaced in place, missing ones added."""
    lines = text.splitlines() or ['<?xml version="1.0"?>']
    todo = {k: v for k, v in settings.items() if share_setting(k)}
    for i, line in enumerate(lines):
        m = SETTING_LINE.search(line)
        if m and m.group(2) in todo:
            lines[i] = setting_line(m.group(2), todo.pop(m.group(2)))
    lines += [setting_line(k, v) for k, v in todo.items()]
    return "\n".join(lines) + "\n"


def plan_esde_extras(es_dir, listing, texts):
    """Themes, collections and settings from scrapes/esde/ that the card is missing or has older.

    listing: {key: size} under scrapes/esde/; texts: {key: text} of its collections and settings.json.
    Returns (download jobs, [(path, text)] to write).
    """
    prefix = f"{SCRAPES}/esde/"
    jobs = []
    for key, size in sorted(listing.items()):
        if key.startswith(prefix + "themes/") and not key.endswith("/"):
            try:
                jobs.append((key, s3.safe_join(es_dir, "themes/" + key[len(prefix + "themes/"):]), size))
            except ValueError as e:
                print(ui.yellow(f"  ⚠️  skipping {e}"))
    writes = []
    for key, text in sorted(texts.items()):
        if key.startswith(prefix + "collections/") and key.endswith(".cfg"):
            try:
                path = s3.safe_join(es_dir, "collections/" + key[len(prefix + "collections/"):])
            except ValueError as e:
                print(ui.yellow(f"  ⚠️  skipping {e}"))
                continue
        elif key == prefix + "settings.json":
            path = os.path.join(es_dir, "settings", "es_settings.xml")
        else:
            continue
        old = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = f.read()
        if key.endswith(".cfg"):
            new = merge_lines(old, text)
            changed = new.splitlines() != old.splitlines()
        else:
            try:
                new = update_settings(old, json.loads(text))
            except ValueError:
                continue
            changed = new != old
        if changed:
            writes.append((path, new))
    return downloads.plan_downloads(jobs), writes


def load_scrape_data(systems, esde):
    """The bucket's scrape data for the chosen systems: {bucket folder: (listing, metadata)}, plus the
    shared scrapes/esde/ listing and texts when the layout is esde."""
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = list(ex.map(lambda s: s3.list_sizes(f"{SCRAPES}/{s['bucket']}/"), systems))
    extra = s3.list_sizes(f"{SCRAPES}/esde/") if esde else {}
    meta_keys = [f"{SCRAPES}/{s['bucket']}/metadata.json" for s, l in zip(systems, listings)
                 if f"{SCRAPES}/{s['bucket']}/metadata.json" in l]
    texts = s3.fetch_texts(meta_keys + [k for k in extra if k.endswith(".cfg") or k.endswith("/settings.json")])
    data = {}
    for s, listing in zip(systems, listings):
        key = f"{SCRAPES}/{s['bucket']}/metadata.json"
        try:
            meta = json.loads(texts[key]) if key in texts else {}
        except ValueError:
            meta = {}
        data[s["bucket"]] = (listing, meta)
    return data, extra, {k: v for k, v in texts.items() if k.startswith(f"{SCRAPES}/esde/")}


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def media_root_of(layout_name, system, base, es_dir):
    """The folder a system's scraped media goes in, for layouts that keep it apart from the ROMs."""
    if layout_name == "muos":
        return os.path.join(base, "MUOS", "info", "catalogue", system["muos_catalogue"])
    if layout_name == "slot":
        return os.path.join(base, "Labels", system["folders"]["slot"])
    return os.path.join(es_dir, "downloaded_media", system["bucket"])


def build_scrape_plan(layout_name, systems, data, extra, extra_texts, rom_rels, dest_of, es_dir, present, base):
    """Everything a sync installs from scrapes/: media jobs, gamelist entries per file, text files, ES-DE extras."""
    plan = {"jobs": [], "gamelists": defaultdict(dict), "extras": [], "writes": []}
    for s in systems:
        listing, meta = data[s["bucket"]]
        rom_dir = dest_of(s)
        media_root = media_root_of(layout_name, s, base, es_dir)
        jobs, entries, texts = plan_scrapes(layout_name, rom_rels.get(s["bucket"], ()), listing, meta, media_root,
                                            rom_dir,
                                            # Slot takes ROMs flat, whatever folder they are in in the bucket
                                            lambda rom, d=rom_dir: present(os.path.join(
                                                d, os.path.basename(rom) if layout_name == "slot" else rom)))
        plan["jobs"] += downloads.plan_downloads(jobs)
        for path, text in texts:  # only the ones that would change
            if not os.path.exists(path) or read_text(path) != text:
                plan["writes"].append((path, text))
        if entries:
            gl = (os.path.join(es_dir, "gamelists", s["bucket"]) if layout_name == "esde" else rom_dir)
            plan["gamelists"][os.path.join(gl, GAMELIST_FILES[layout_name])].update(entries)
    if layout_name == "esde":
        plan["extras"], plan["writes"] = plan_esde_extras(es_dir, extra, extra_texts)
    return plan


def describe_scrape_plan(plan):
    jobs = plan["jobs"] + plan["extras"]
    print(f"🖼️  Scraped data: {ui.bold(str(len(jobs)))} file(s) to download "
          f"({ui.human_size(sum(j[2] or 0 for j in jobs))}), {len(plan['gamelists'])} gamelist file(s) to update"
          + (f", {len(plan['writes'])} text/collection/settings file(s)" if plan["writes"] else ""))


def apply_scrape_plan(plan, base):
    """Download the media, then write the gamelists, collections and settings. Returns failures."""
    failed = downloads.run_downloads(plan["jobs"] + plan["extras"], "Scraped data", "🖼️", base)
    for path, entries in plan["gamelists"].items():
        try:
            update_gamelist(path, entries)
        except (ET.ParseError, OSError, UnicodeDecodeError) as e:
            failed += 1
            print(ui.red(f"  ❌ {path}: {e}"))
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return failed


def card_stems(rom_dir, flat):
    """ROM names without extension in a system's ROM folder (base names only if flat)."""
    stems = set()
    for root, files in downloads.walk_roms(rom_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), rom_dir).replace(os.sep, "/")
            stems.add(os.path.splitext(os.path.basename(rel) if flat else rel)[0])
    return stems


def media_name(layout_name, name):
    """How a firmware compares art names with ROM names: muOS ignores case, Slot also ignores bracketed tags."""
    if layout_name == "slot":
        name = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", name)
    return name.strip().lower()


def stale_firmware_media(layout_name, systems, roms_dir, base):
    """Art files in muOS's catalogue (box, preview and text) or Slot's Labels folders whose ROM isn't on the card.

    Systems that share a catalogue folder are judged together. A folder whose ROM folders hold no ROMs is left alone.
    """
    groups = defaultdict(list)
    for s in systems:
        if s["folders"].get(layout_name):
            groups[media_root_of(layout_name, s, base, "")].append(os.path.join(roms_dir, s["folders"][layout_name]))
    stale = []
    for root, rom_dirs in sorted(groups.items()):
        stems = {media_name(layout_name, stem) for d in set(rom_dirs) if os.path.isdir(d) for stem in card_stems(d, True)}
        if not stems:
            continue
        for sub in ("box", "preview", "text") if layout_name == "muos" else (".",):
            folder = os.path.normpath(os.path.join(root, sub))
            for rel, full in walk_files(folder) if os.path.isdir(folder) else []:
                if media_name(layout_name, os.path.splitext(os.path.basename(rel))[0]) not in stems:
                    stale.append(full)
    return stale


def stale_media(layout_name, systems, roms_dir, es_dir, base=None):
    """Media files on the card whose ROM isn't in the system's ROM folder, for every system in the
    layout (not just the ones being synced). Systems with no ROM folder are left alone."""
    stale, seen = [], set()
    if layout_name in ("muos", "slot"):
        return stale_firmware_media(layout_name, systems, roms_dir, base)
    for s in systems:
        folder = s["folders"].get(layout_name)
        rom_dir = os.path.join(roms_dir, folder) if folder else None
        if not rom_dir or rom_dir in seen or not os.path.isdir(rom_dir):
            continue
        seen.add(rom_dir)
        stems = card_stems(rom_dir, layout_name != "esde")
        if layout_name == "esde":
            for mtype in sorted(MEDIA_TYPES):
                base = os.path.join(es_dir, "downloaded_media", folder, mtype)
                stale += [full for rel, full in walk_files(base) if os.path.splitext(rel)[0] not in stems] \
                    if os.path.isdir(base) else []
        elif layout_name == "knulli":
            for sub in ("images", "videos", "manuals"):
                base = os.path.join(rom_dir, sub)
                for rel, full in walk_files(base) if os.path.isdir(base) else []:
                    name = os.path.splitext(os.path.basename(rel))[0]
                    if name not in stems and not any(name.endswith("-" + x) and name[:-len(x) - 1] in stems
                                                     for x in KNULLI_SUFFIXES):
                        stale.append(full)
        elif layout_name == "onion":
            base = os.path.join(rom_dir, "Imgs")
            stale += [full for rel, full in walk_files(base) if os.path.splitext(os.path.basename(rel))[0] not in stems] \
                if os.path.isdir(base) else []
    return stale
