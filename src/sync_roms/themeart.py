"""Art Book Next artwork for custom collections (Surprise and the ones given art) on ES-DE and Knulli cards."""
import json
import unicodedata
import http.client
import os
import shutil
import tarfile
import tempfile
import urllib.request
from xml.sax import saxutils
import zlib

from . import __version__, frontend, runtime, s3, store, ui

THEME_DATA = os.path.join(store.REPO_DATA, "themes", "art-book-next")
SURPRISE_ART = "surprise"
DEFAULT_EMOJI = "💖"  # a collection with no art
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


def _write_settings(path, layout_name, values, only_if_unset=()):
    """Set the <string> entries in a frontend settings file; names in only_if_unset are left alone when present."""
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    new = old
    for name, value in values.items():
        if name in only_if_unset and frontend.get_string(new, name):
            continue
        new = frontend.set_string(new, layout_name, name, value)
    if new != old:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)


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


def art_emoji(art_id):
    """The emoji that stands for a collection's art in the editors: its own, or DEFAULT_EMOJI when it has no art."""
    with open(os.path.join(THEME_DATA, "emoji.json"), encoding="utf-8") as f:
        return json.load(f).get(art_id, DEFAULT_EMOJI) if art_id else DEFAULT_EMOJI


def art_png(art_id):
    """The artwork file for art_id, or None when there is none."""
    if art_id != SURPRISE_ART and art_id not in art_choices():
        return None
    return os.path.join(THEME_DATA, "art", f"{art_id}.png")


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


def _put(path, data):
    """Write data (bytes) to path unless it already holds them. Returns whether it wrote."""
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


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
        png = art_png(art_id)
        if not png:
            ui.warn(f"{name}: there is no theme art called {art_id!r}; skipped")
        elif name.lower() in _reserved(layout_name) or name.lower().startswith("auto-"):
            ui.warn(f"{name}: a collection named like a system or a built-in collection can't have its own theme art")
        elif name.lower() in taken:  # cards ignore case, and ES-DE themes a collection by its name in lower case
            ui.warn(f"{name}: another collection with this name in other capitals already has theme art; skipped")
        else:
            out[name] = png
            taken.add(name.lower())
    return out


# --- ES-DE ---------------------------------------------------------------------------------------------------------

def esde_wanted(base):
    """Whether the card's ES-DE uses Art Book Next (the downloaded theme or the card's copy of it) or hasn't picked a
    theme yet, so a new card has the theme before ES-DE is first set up."""
    theme = frontend.get_string(_read(frontend.settings_path("esde", base)), "Theme")
    return not theme or theme in (ESDE_THEME, ESDE_COPY)


def _esde_dir(base):
    return os.path.join(base, "ES-DE", "themes", ESDE_COPY)


def _card_commit(base):
    return _read(os.path.join(_esde_dir(base), ESDE_MARKER)).strip()


def _stored_commit():
    """The commit of the theme archive in storage, or None when storage has none."""
    try:
        return s3.get_text(ESDE_COMMIT).strip() or None
    except s3.ERRORS:
        return None


def _extract(archive_path, dest, commit):
    """Replace dest with the archive's files and the commit marker. They are written to a folder ES-DE ignores (its name
    ends in "disabled") that only replaces dest once complete, so a failed copy never leaves a half theme behind."""
    part = dest + "-disabled"
    shutil.rmtree(part, ignore_errors=True)
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            rel = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not member.isfile() or not rel:
                continue
            path = s3.safe_join(part, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                shutil.copyfileobj(archive.extractfile(member), f)
    with open(os.path.join(part, ESDE_MARKER), "w") as f:
        f.write(commit + "\n")
    shutil.rmtree(dest, ignore_errors=True)
    os.rename(part, dest)


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


def install_esde(base, arts):
    """Put Art Book Next with the collections' art on the card and select it. Returns whether anything changed."""
    if not esde_wanted(base) or not arts:
        return False
    dest = _esde_dir(base)
    commit = _stored_commit()
    changed = False
    if not commit:
        if not os.path.exists(os.path.join(dest, ESDE_MARKER)):
            ui.warn("Storage has no copy of Art Book Next for ES-DE, so collections have no art; "
                    "run `sync-roms themes update` to add one")
            return False
    elif commit != _card_commit(base):
        print(f"🎨 Copying Art Book Next for ES-DE ({commit[:7]}) into {os.path.relpath(dest, base)}...")
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
    owned = set(_read(os.path.join(dest, ESDE_OWNED)).splitlines()) | {n.lower() for n in arts}
    changed |= _put(os.path.join(dest, ESDE_OWNED), "".join(f"{n}\n" for n in sorted(owned)).encode())
    for rel, data in _esde_files(arts).items():
        changed |= _put(s3.safe_join(dest, rel), data)
    _write_settings(frontend.settings_path("esde", base), "esde", {"Theme": ESDE_COPY})
    return changed


def describe_esde(base, arts):
    if not esde_wanted(base) or not arts:
        return
    commit = _stored_commit()
    if not commit and not os.path.exists(os.path.join(_esde_dir(base), ESDE_MARKER)):
        print(ui.dim("🎨 storage has no copy of Art Book Next for ES-DE (`sync-roms themes update` adds one)"))
        return
    if commit and commit != _card_commit(base):
        print(ui.dim(f"🎨 would copy Art Book Next ({commit[:7]}) into ES-DE/themes/{ESDE_COPY}"))
    print(ui.dim(f"🎨 would add art for {', '.join(arts)} to it and select it as the ES-DE theme"))


def _github(url, accept=None):
    headers = {"User-Agent": f"sync-roms/{__version__}", **({"Accept": accept} if accept else {})}
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)


def update_storage(dry_run=False):
    """Replace storage's Art Book Next archive with one of the theme's latest commit. Returns an exit code."""
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):
        ui.warn(f"The storage folder {runtime.ROOT} isn't there (is it mounted?)")
        return 1
    try:
        with _github(f"https://api.github.com/repos/{ESDE_REPO}/commits/HEAD", "application/vnd.github.sha") as r:
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
            with _github(f"https://codeload.github.com/{ESDE_REPO}/tar.gz/{latest}") as r, open(path, "wb") as f:
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
    theme = frontend.get_string(_read(frontend.settings_path("knulli", base)), "ThemeSet")
    return not theme or "art-book-next" in theme


def knulli_settings(name):
    """The es_settings.cfg entries that show the collection name with its custom art and keep it on its own."""
    return {f"subset.{name}.system-view-artwork": "custom", f"subset.{name}.system-logos": "custom",
            "UseCustomCollectionsSystemEx": "false"}


def install_knulli(base, arts):
    """Put the collections' art ({name: art png}) in Knulli's theme customizations. Returns whether files changed."""
    if not knulli_wanted(base) or not arts:
        return False
    root = os.path.join(base, KNULLI_DIR)
    changed, settings = False, {}
    for name, png in arts.items():
        with open(png, "rb") as f:
            changed |= _put(os.path.join(root, "artwork", f"{name}.png"), f.read())
        logo = logo_svg(name)
        if logo:
            changed |= _put(os.path.join(root, "logos", f"{name}.svg"), logo.encode())
        settings.update(knulli_settings(name))
        if not logo:  # the theme shows the name as text
            del settings[f"subset.{name}.system-logos"]
    _write_settings(frontend.settings_path("knulli", base), "knulli", settings,
                    only_if_unset={"UseCustomCollectionsSystemEx"})
    return changed


def describe_knulli(base, arts):
    if knulli_wanted(base) and arts:
        print(ui.dim(f"🎨 would add art for {', '.join(arts)} to {KNULLI_DIR.replace(os.sep, '/')}/"))


def install(layout_name, base, arts):
    """Give the custom collections in arts ({name: art id}) their art in the frontend's theme. Returns whether files
    changed."""
    arts = usable(layout_name, arts)
    return install_esde(base, arts) if layout_name == "esde" else install_knulli(base, arts)


def describe(layout_name, base, arts):
    arts = usable(layout_name, arts)
    describe_esde(base, arts) if layout_name == "esde" else describe_knulli(base, arts)
