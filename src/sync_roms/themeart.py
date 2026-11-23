"""Art Book Next artwork for custom collections (Surprise and the ones given art) and sets on ES-DE, Knulli, EmuDeck,
muOS, ROCKNIX and Spruce cards."""
import contextlib
import functools
import json
import unicodedata
import http.client
import os
import shutil
import tarfile
import tempfile
from xml.sax import saxutils
import zlib

from . import cardfs, downloads, frontend, github, rocknix_collections, runtime, s3, store, ui

THEME_DATA = os.path.join(store.REPO_DATA, "themes", "art-book-next")
SURPRISE_ART = "surprise"
DEFAULT_EMOJI = "💖"  # a collection with no art
SET_EMOJI = "📦"  # a set with no emoji of its own yet
# The Outline-style artwork a collection can use, by id: art/<id>.png; art.json has the labels the editor shows.
# Logos are drawn from the outlines of the theme's logo font (logo-font.json, from Changa One: see OFL.txt).

# ES-DE on Android keeps downloaded themes off the card, so the card gets its own copy of the theme with the Surprise
# files added, under a folder name of its own (ES-DE prefers a downloaded theme of the same name). The copy comes from
# a GitHub archive of the theme kept in storage, which `sync-roms themes update` refreshes.
ESDE_THEME = "art-book-next-es-de"
ESDE_COPY = "art-book-next-sync-roms"
ESDE_REPO = "anthonycaccese/art-book-next-es-de"
ESDE_ARCHIVE = runtime.ESDE_THEMES_PREFIX + "art-book-next-es-de.tar.gz"
ESDE_COMMIT = runtime.ESDE_THEMES_PREFIX + "art-book-next-es-de.commit"  # the commit the archive was made from
ESDE_MARKER = ".sync-roms-commit"  # the same, in the card's copy
ESDE_OWNED = ".sync-roms-collections"  # the collection folders sync-roms gave art in the card's copy
ARCHIVE_ERRORS = (tarfile.TarError, EOFError, zlib.error)  # what a damaged .tar.gz raises

# Knulli's Art Book Next is read-only, but takes artwork and logos from theme-customizations/ on the card for systems
# whose "System Artwork" and "System Logos" options are Custom; those options can be set for one system alone.
KNULLI_DIR = os.path.join("theme-customizations", "art-book-next")
# In Knulli's and ROCKNIX's customizations and muOS's collection catalogue: the collection names sync-roms gave art
CUSTOM_OWNED = ".sync-roms-art"
CUSTOM_FILES = (("artwork", ".png"), ("logos", ".svg"))  # a name's art in the customizations: (folder, extension)


def _write_settings(path, layout_name, values, only_if_unset=()):
    """Set the <string> entries in a frontend settings file; names in only_if_unset are left alone when present."""
    old = cardfs.text(path)
    new = old
    for name, value in values.items():
        if name in only_if_unset and frontend.get_string(new, name):
            continue
        new = frontend.set_string(new, layout_name, name, value)
    cardfs.write_text(path, new)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def art_choices():
    """{art id: label} of the artwork a collection can pick, in the order the editor lists it."""
    with open(os.path.join(THEME_DATA, "art.json"), encoding="utf-8") as f:
        return json.load(f)


@functools.cache
def _emoji():
    """emoji.json, read once per run: it is repo data, and the size recount looks it up once per collection game."""
    with open(os.path.join(THEME_DATA, "emoji.json"), encoding="utf-8") as f:
        return json.load(f)


def art_emoji(art_id, default=DEFAULT_EMOJI):
    """The emoji that stands for a piece of art in the editors: its own, or default when it has no art."""
    return _emoji().get(art_id, default) if art_id else default


def set_art(game_set):
    """The art id a set shows (its emoji and its preview): its "art", else its id."""
    return game_set.get("art") or game_set.get("id")


def set_emoji(game_set):
    """A set's emoji: its art's in emoji.json (set_art), or SET_EMOJI when it has none. Display only, never stored."""
    return art_emoji(set_art(game_set), SET_EMOJI)


def collection_emoji(collection):
    """A collection's art emoji, or DEFAULT_EMOJI. Display only, never stored."""
    return art_emoji(collection.get("art"))


def art_png(art_id, folder="art"):
    """The artwork file for art_id (in art/, or art-box/<size> for Spruce's box pictures), or None when there is
    none."""
    if art_id != SURPRISE_ART and art_id not in art_choices():
        return None
    return os.path.join(THEME_DATA, folder, f"{art_id}.png")


def logo_svg(text):
    """An SVG logo (200x40, white, like the theme's own) spelling text in capitals with the theme's logo font, or None
    when the font can't draw it (the frontend then shows the name as text)."""
    with open(os.path.join(THEME_DATA, "logo-font.json"), encoding="utf-8") as f:
        font = json.load(f)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).upper()
    if not text.strip() or any(c not in font["glyphs"] for c in text):
        return None
    glyphs = [font["glyphs"][c] for c in text]
    width = sum(g["advance"] for g in glyphs) or 1
    scale = min(18.7 / font["cap_height"], 190 / width)  # capitals as tall as the theme's logos, never wider than 190
    # the capitals are centred on the middle line (the theme's own logos run from 11.15 to 29.85)
    paths, x = [], 0
    for g in glyphs:
        if g["path"]:
            paths.append(f'<path transform="translate({x} 0)" d="{g["path"]}"/>')
        x += g["advance"]
    left = (200 - width * scale) / 2
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg viewBox="0 0 200 40" xmlns="http://www.w3.org/2000/svg">\n'
            f'  <g fill="#fff" transform="translate({left:.2f} {20 + scale * font["cap_height"] / 2:.2f}) '
            f'scale({scale:.5f} {-scale:.5f})">{"".join(paths)}</g>\n</svg>\n')


def _reserved(layout_name):
    """Lowercase theme names a collection can't take art for: the systems' own, and the theme's built-in collections
    (giving them art would replace the system's)."""
    names = {s["folders"].get(layout_name) or "" for s in store.repo_json("systems")} - {""}
    return {n.lower() for n in names} | {"custom-collections", "now-playing", "completed", "all", "favorites",
                                         "lastplayed", "recent", "2players", "4players", "neverplayed",
                                         "retroachievements", "arcade", "vertical", "lightgun", "wheel", "trackball",
                                         "spinner"}


def usable(layout_name, arts):
    """The {collection name: art png} of arts ({name: art id}) that can be installed, warning about the rest."""
    out, taken = {}, set()
    for name, art_id in sorted(arts.items()):
        png = art_png(art_id, "art-box/Imgs" if layout_name == "spruce" else "art")
        if not png:
            ui.warn(f"{name}: there is no theme art called {art_id!r}; skipped")
        elif layout_name != "spruce" and (name.lower() in _reserved(layout_name) or name.lower().startswith("auto-")):
            ui.warn(f"{name}: a collection named like a system or a built-in collection can't have its own theme art")
        elif name.lower() in taken:  # cards ignore case, and ES-DE themes a collection by its name in lower case
            ui.warn(f"{name}: another collection with this name in other capitals already has theme art; skipped")
        else:
            out[name] = png
            taken.add(name.lower())
    return out


# --- ES-DE ---------------------------------------------------------------------------------------------------------

def esde_wanted(layout_name, base):
    """Whether the card's ES-DE uses Art Book Next (the downloaded theme or the card's copy of it) or hasn't picked a
    theme yet, so a new card has the theme before ES-DE is first set up."""
    theme = frontend.get_string(cardfs.text(frontend.settings_path(layout_name, base)), "Theme")
    return not theme or theme in (ESDE_THEME, ESDE_COPY)


def _esde_dir(layout_name, base):
    return os.path.join(frontend.esde_dir(layout_name, base), "themes", ESDE_COPY)


def _shown(layout_name, base):
    """The theme copy's path from ES-DE's data folder's parent, for messages."""
    return os.path.relpath(_esde_dir(layout_name, base), os.path.dirname(os.path.normpath(frontend.esde_dir(layout_name, base))))


def _card_commit(layout_name, base):
    return _read(os.path.join(_esde_dir(layout_name, base), ESDE_MARKER)).strip()


def _stored_commit():
    """The commit of the theme archive in storage, or None when storage has none."""
    try:
        return s3.get_text(ESDE_COMMIT).strip() or None
    except s3.ERRORS:
        return None


def _sync_written(dest):
    """Paths (relative, with "/") under dest that sync-roms wrote itself and an update keeps: the collection list and,
    for each collection folder in it (and Surprise), the files `_esde_files` gives it."""
    keep = {ESDE_MARKER, ESDE_OWNED}
    for folder in set(_read(os.path.join(dest, ESDE_OWNED)).splitlines()) | {SURPRISE_ART}:
        keep |= _esde_paths(folder)
    return keep


def _esde_paths(folder):
    """The paths in the theme (relative, with "/") of the files that give a collection folder its art."""
    return {f"_inc/systems/artwork-outline/{folder}.png", f"_inc/systems/logos/{folder}.svg",
            f"_inc/systems/_metadata-global/{folder}.xml", f"{folder}/theme.xml"}


def _extract(archive_path, dest, commit):
    """Bring dest to the archive's files, writing only the ones that are missing or differ (each through a temp name and
    a rename), deleting the ones the archive lacks except sync-roms's own, and writing the commit marker last, so a
    stopped sync leaves the old marker and the next one finishes. A collection folder on sync-roms's list that the
    archive has metadata for is the theme's own from then on: it leaves the list."""
    shutil.rmtree(dest + "-disabled", ignore_errors=True)  # from the days the copy was staged there
    wanted = set()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            rel = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not member.isfile() or not rel:
                continue
            path = s3.safe_join(dest, rel)
            wanted.add(downloads.name_key(path))
            cardfs.write_bytes(path, archive.extractfile(member).read())
    owned = _read(os.path.join(dest, ESDE_OWNED)).splitlines()
    ours = [n for n in owned
            if downloads.name_key(os.path.join(dest, "_inc", "systems", "_metadata-global", f"{n}.xml")) not in wanted]
    if ours != owned:
        cardfs.write_bytes(os.path.join(dest, ESDE_OWNED), "".join(f"{n}\n" for n in ours).encode())
    kept = {downloads.name_key(os.path.join(dest, *k.split("/"))) for k in _sync_written(dest)}
    for folder, _, names in os.walk(dest, topdown=False):
        for name in names:
            path = os.path.join(folder, name)
            if downloads.name_key(path) not in wanted | kept:  # cards ignore case
                os.remove(path)
        if folder != dest and not os.listdir(folder):
            os.rmdir(folder)
    store.replace_file(os.path.join(dest, ESDE_MARKER), commit + "\n")


def _metadata(name):
    """The theme's metadata for a custom collection (as the theme has for its own custom-collections)."""
    return ("<theme>\n    <variables>\n"
            f"        <systemName>{saxutils.escape(name)}</systemName>\n"
            "        <systemDescription>A custom collection.</systemDescription>\n"
            "        <systemManufacturer>Various</systemManufacturer>\n"
            "        <systemReleaseYear>Various</systemReleaseYear>\n"
            "        <systemReleaseDate>Various</systemReleaseDate>\n"
            "        <systemReleaseDateFormated>Various</systemReleaseDateFormated>\n"
            "        <systemHardwareType>Collection</systemHardwareType>\n"
            "        <systemCoverSize>1-1</systemCoverSize>\n"
            "        <systemCoverSizeType>square</systemCoverSizeType>\n"
            "        <systemCartSize>1-1</systemCartSize>\n"
            "    </variables>\n</theme>\n").encode()


def _esde_files(arts):
    """{path in the theme: bytes} giving each collection in arts ({name: art png}) its art. ES-DE themes a custom
    collection by its name in lower case."""
    files = {}
    for name, png in arts.items():
        folder = name.lower()
        with open(png, "rb") as f:
            files[f"_inc/systems/artwork-outline/{folder}.png"] = f.read()
        logo = logo_svg(name)
        if logo:
            files[f"_inc/systems/logos/{folder}.svg"] = logo.encode()
        files[f"_inc/systems/_metadata-global/{folder}.xml"] = _metadata(name)
        files[f"{folder}/theme.xml"] = b"<theme><include>./../theme.xml</include></theme>\n"
    return files


def _theme_has(dest, folder):
    """Whether the theme copy at dest themes folder itself (it has metadata for it that sync-roms didn't write)."""
    owned = set(_read(os.path.join(dest, ESDE_OWNED)).splitlines()) | {SURPRISE_ART}
    return folder not in owned and os.path.exists(os.path.join(dest, "_inc", "systems", "_metadata-global", f"{folder}.xml"))


def _esde_stale(dest, keep):
    """The collection folders on the list in the theme copy at dest that aren't in keep: their art is removed. A line
    that isn't a name sync-roms writes is left out."""
    return [n for n in _read(os.path.join(dest, ESDE_OWNED)).splitlines()
            if n not in keep and n and frontend.safe_name(n) == n]


def _esde_remove(dest, keep):
    """Remove from the theme copy at dest the files sync-roms wrote for the collection folders on its list that aren't
    in keep, and take them off the list. Returns whether anything changed."""
    owned = _read(os.path.join(dest, ESDE_OWNED)).splitlines()
    stale = [n for n in owned if n not in keep]
    for folder in _esde_stale(dest, keep):
        for rel in _esde_paths(folder):
            with contextlib.suppress(FileNotFoundError):
                os.remove(s3.safe_join(dest, rel))
        try:
            os.rmdir(os.path.join(dest, folder))  # only when that emptied it
        except OSError:
            pass
    return bool(stale) and cardfs.write_bytes(os.path.join(dest, ESDE_OWNED), "".join(f"{n}\n" for n in owned if n in keep).encode())


def install_esde(layout_name, base, arts):
    """Put Art Book Next with the collections' art in the card's ES-DE and select it, and remove the art sync-roms gave
    collections no longer in arts. Returns whether anything changed."""
    if not esde_wanted(layout_name, base):
        return False
    dest = _esde_dir(layout_name, base)
    if not arts:  # nothing to add, so the theme is neither copied nor selected
        return _esde_remove(dest, ())
    commit = _stored_commit()
    changed = False
    if not commit:
        if not os.path.exists(os.path.join(dest, ESDE_MARKER)):
            ui.warn("Storage has no copy of Art Book Next for ES-DE, so collections have no art; "
                    "run `sync-roms themes update` to add one")
            return False
    elif commit != _card_commit(layout_name, base):
        print(f"🎨 Copying Art Book Next for ES-DE ({commit[:7]}) into {_shown(layout_name, base)}...")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "theme.tar.gz")
                s3.download((ESDE_ARCHIVE, path, None))
                _extract(path, dest, commit)
        except (*s3.ERRORS, *ARCHIVE_ERRORS, ValueError) as e:
            ui.warn(f"Couldn't install Art Book Next for the collections' art: {e}")
            return False
        changed = True
    for name in [n for n in arts if _theme_has(dest, n.lower())]:
        ui.warn(f"{name}: Art Book Next already has art of its own for that name; skipped")
        del arts[name]
    changed |= _esde_remove(dest, {n.lower() for n in arts})
    owned = set(_read(os.path.join(dest, ESDE_OWNED)).splitlines()) | {n.lower() for n in arts}
    changed |= cardfs.write_bytes(os.path.join(dest, ESDE_OWNED), "".join(f"{n}\n" for n in sorted(owned)).encode())
    for rel, data in _esde_files(arts).items():
        changed |= cardfs.write_bytes(s3.safe_join(dest, rel), data)
    _write_settings(frontend.settings_path(layout_name, base), layout_name, {"Theme": ESDE_COPY})
    return changed


def describe_esde(layout_name, base, arts):
    if not esde_wanted(layout_name, base):
        return
    stale = _esde_stale(_esde_dir(layout_name, base), {n.lower() for n in arts})
    if stale:
        print(ui.dim(f"🎨 would remove the art for {', '.join(stale)} from {_shown(layout_name, base).replace(os.sep, '/')}"))
    if not arts:
        return
    commit = _stored_commit()
    if not commit and not os.path.exists(os.path.join(_esde_dir(layout_name, base), ESDE_MARKER)):
        print(ui.dim("🎨 storage has no copy of Art Book Next for ES-DE (`sync-roms themes update` adds one)"))
        return
    if commit and commit != _card_commit(layout_name, base):
        print(ui.dim(f"🎨 would copy Art Book Next ({commit[:7]}) into {_shown(layout_name, base).replace(os.sep, '/')}"))
    print(ui.dim(f"🎨 would add art for {', '.join(arts)} to it and select it as the ES-DE theme"))


def update_storage(dry_run=False):
    """Replace storage's Art Book Next archive with one of the theme's latest commit. Returns an exit code."""
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):
        ui.warn(f"The storage folder {runtime.ROOT} isn't there (is it mounted?)")
        return 1
    try:
        with github.get(f"https://api.github.com/repos/{ESDE_REPO}/commits/HEAD", "application/vnd.github.sha") as r:
            latest = r.read().decode().strip()
    except (OSError, http.client.HTTPException) as e:
        ui.warn(f"Couldn't ask GitHub for the latest Art Book Next commit: {e}")
        return 1
    stored = _stored_commit()
    if stored == latest:
        print(ui.green(f"✅ Art Book Next for ES-DE in storage is already the latest ({latest[:7]})"))
        return 0
    print(f"🎨 Art Book Next for ES-DE: {stored[:7] if stored else 'none in storage'} → {latest[:7]}")
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would upload {ESDE_ARCHIVE} and {ESDE_COMMIT}"))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "theme.tar.gz")
        try:
            with github.get(f"https://codeload.github.com/{ESDE_REPO}/tar.gz/{latest}") as r, open(path, "wb") as f:
                shutil.copyfileobj(r, f)
            with tarfile.open(path, mode="r:gz") as archive:  # a whole, readable archive before it replaces the old one
                count = sum(1 for m in archive if m.isfile())
        except (OSError, http.client.HTTPException, *ARCHIVE_ERRORS) as e:
            ui.warn(f"Couldn't download Art Book Next: {e}")
            return 1
        try:
            s3.put_file(ESDE_ARCHIVE, path)
            s3.put_text(ESDE_COMMIT, latest + "\n")
        except s3.ERRORS as e:
            ui.warn(f"Couldn't upload Art Book Next to {s3.location()}: {e}")
            return 1
    print(ui.green(f"✅ Uploaded Art Book Next {latest[:7]} ({count} files) to {s3.location()}"))
    return 0


# --- Knulli --------------------------------------------------------------------------------------------------------

def knulli_wanted(base):
    """Whether the card's Knulli uses Art Book Next (or hasn't picked a theme yet)."""
    theme = frontend.get_string(cardfs.text(frontend.settings_path("knulli", base)), "ThemeSet")
    return not theme or "art-book-next" in theme


def knulli_settings(name):
    """The es_settings.cfg entries that show the collection name with its custom art and keep it on its own."""
    return {f"subset.{name}.system-view-artwork": "custom", f"subset.{name}.system-logos": "custom",
            "UseCustomCollectionsSystemEx": "false"}


def _custom_stale(root, arts):
    """The names on the list in the customizations folder root (the collections sync-roms gave art there) that aren't in
    arts: their art is removed."""
    return [n for n in _read(os.path.join(root, CUSTOM_OWNED)).splitlines()
            if n and frontend.safe_name(n) == n and n not in arts]


def _custom_remove(root, arts, files=CUSTOM_FILES):
    """Remove from the customizations folder root the art sync-roms put there (the names on its list, each name's files
    being <folder>/<name><extension> for files) for collections no longer in arts, and list the ones in arts instead.
    Returns the names it removed."""
    stale = _custom_stale(root, arts)
    for name in stale:
        for folder, ext in files:
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(root, folder, name + ext))
    if arts:
        cardfs.write_bytes(os.path.join(root, CUSTOM_OWNED), "".join(f"{n}\n" for n in sorted(arts)).encode())
    else:
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(root, CUSTOM_OWNED))
    return stale


def _custom_describe(base, rel_dir, arts, what="art"):
    """Print what installing arts in the customizations folder rel_dir of the card at base would do."""
    shown = rel_dir.replace(os.sep, "/")
    stale = _custom_stale(os.path.join(base, rel_dir), arts)
    if stale:
        print(ui.dim(f"🎨 would remove the {what} for {', '.join(stale)} from {shown}/"))
    if arts:
        print(ui.dim(f"🎨 would add art for {', '.join(arts)} to {shown}/"))


def install_knulli(base, arts):
    """Put the collections' art ({name: art png}) in Knulli's theme customizations, and remove the art and settings
    sync-roms gave collections no longer in arts. Returns whether files changed."""
    if not knulli_wanted(base):
        return False
    root = os.path.join(base, KNULLI_DIR)
    path = frontend.settings_path("knulli", base)
    stale = _custom_remove(root, arts)  # before the art is written: a card that ignores case has one file for Favs and favs
    text = cardfs.text(path)
    for name in stale:
        for option in ("system-view-artwork", "system-logos"):
            text = frontend.remove_string(text, f"subset.{name}.{option}")
    cardfs.write_text(path, text)
    changed, settings = bool(stale), {}
    for name, png in arts.items():
        with open(png, "rb") as f:
            changed |= cardfs.write_bytes(os.path.join(root, "artwork", f"{name}.png"), f.read())
        logo = logo_svg(name)
        if logo:
            changed |= cardfs.write_bytes(os.path.join(root, "logos", f"{name}.svg"), logo.encode())
        settings.update(knulli_settings(name))
        if not logo:  # the theme shows the name as text
            del settings[f"subset.{name}.system-logos"]
    _write_settings(path, "knulli", settings, only_if_unset={"UseCustomCollectionsSystemEx"})
    return changed


def describe_knulli(base, arts):
    if knulli_wanted(base):
        _custom_describe(base, KNULLI_DIR, arts, "art and settings")


# --- ROCKNIX -------------------------------------------------------------------------------------------------------

def install_rocknix(base, arts):
    """Put the collections' art ({name: art png}) in Art Book Next's ROCKNIX customizations on the card, and remove the
    art sync-roms gave collections no longer in arts. Its settings are on internal storage: the collections' install
    script turns the art on and off. Returns whether files changed."""
    root = os.path.join(base, rocknix_collections.ART_DIR)
    changed = bool(_custom_remove(root, arts))
    for name, png in arts.items():
        with open(png, "rb") as f:
            changed |= cardfs.write_bytes(os.path.join(root, "artwork", f"{name}.png"), f.read())
        logo = logo_svg(name)
        if logo:
            changed |= cardfs.write_bytes(os.path.join(root, "logos", f"{name}.svg"), logo.encode())
    return changed


# --- muOS ----------------------------------------------------------------------------------------------------------

MUOS_DIR = os.path.join("MUOS", "info", "catalogue", "Collection")
MUOS_FILES = (("box", ".png"), ("grid", ".png"))  # muOS shows <collection folder>.png of both


def install_muos(base, arts):
    """Put the collections' art ({name: art png}) in muOS's catalogue as box and grid pictures, and remove what
    sync-roms put there for collections no longer in arts. Returns whether files changed."""
    root = os.path.join(base, MUOS_DIR)
    changed = bool(_custom_remove(root, arts, MUOS_FILES))  # before the art is written, as in install_knulli
    for name, png in arts.items():
        with open(png, "rb") as f:
            data = f.read()
        for folder, ext in MUOS_FILES:
            changed |= cardfs.write_bytes(os.path.join(root, folder, name + ext), data)
    return changed


# --- Spruce --------------------------------------------------------------------------------------------------------

SPRUCE_SIZES = ("Imgs", "Imgs_med", "Imgs_small")  # PyUI shows <size>/<collection name>.png, PNG only
SPRUCE_DIR = os.path.join("Collections", SPRUCE_SIZES[0])


def _spruce_stale(base, arts, owned):
    """The pictures, in every size, of the collections sync-roms owns (owned) that have no art in arts any more."""
    paths = (os.path.join(base, "Collections", size, f"{name}.png")
             for name in dict.fromkeys(owned) if name not in arts for size in SPRUCE_SIZES)
    return [p for p in paths if os.path.exists(p)]


def install_spruce(base, arts, owned):
    """Put the collections' art ({name: art png of the Imgs size}) in Collections/Imgs/, Imgs_med/ and Imgs_small/
    and remove the pictures of each collection in owned that has none now. Other files there are left alone.
    Returns whether files changed."""
    changed = False
    for name, png in arts.items():
        for size in SPRUCE_SIZES:
            with open(os.path.join(os.path.dirname(os.path.dirname(png)), size, os.path.basename(png)), "rb") as f:
                changed |= cardfs.write_bytes(os.path.join(base, "Collections", size, f"{name}.png"), f.read())
    for path in _spruce_stale(base, arts, owned):
        os.remove(path)
        changed = True
    return changed


def describe_spruce(base, arts, owned):
    where = SPRUCE_DIR.replace(os.sep, "/")
    if arts:
        print(ui.dim(f"🎨 would add the art for {', '.join(arts)} to {where}/ (and Imgs_med/, Imgs_small/)"))
    stale = list(dict.fromkeys(os.path.basename(p)[:-4] for p in _spruce_stale(base, arts, owned)))
    if stale:
        print(ui.dim(f"🎨 would remove the art for {', '.join(stale)} from {where}/ (and Imgs_med/, Imgs_small/)"))


def install(layout_name, base, arts, owned=()):
    """Give the custom collections in arts ({name: art id}) their art in the frontend's theme. Returns whether files
    changed. NextUI has no theme to put it in. owned (Spruce only): the collections sync-roms writes, whose art is
    removed when they have none."""
    if layout_name == "nextui":
        return False
    arts = usable(layout_name, arts)
    if layout_name == "spruce":
        return install_spruce(base, arts, owned)
    if layout_name == "muos":
        return install_muos(base, arts)
    if layout_name == "rocknix":
        return install_rocknix(base, arts)
    return install_esde(layout_name, base, arts) if layout_name in frontend.ESDE_LAYOUTS else install_knulli(base, arts)


def describe(layout_name, base, arts, owned=()):
    if layout_name == "nextui":
        return
    arts = usable(layout_name, arts)
    if layout_name == "spruce":
        return describe_spruce(base, arts, owned)
    if layout_name == "muos":
        return _custom_describe(base, MUOS_DIR, arts)
    if layout_name == "rocknix":
        return _custom_describe(base, rocknix_collections.ART_DIR, arts)
    describe_esde(layout_name, base, arts) if layout_name in frontend.ESDE_LAYOUTS else describe_knulli(base, arts)
