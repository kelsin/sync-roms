"""Art Book Next artwork for the Surprise collection on ES-DE and Knulli cards."""
import filecmp
import http.client
import os
import shutil
import tarfile
import tempfile
import urllib.request
import zlib

from . import __version__, frontend, runtime, s3, store, ui

ART = os.path.join(store.REPO_DATA, "themes", "art-book-next")  # the Surprise files, laid out as in the ES-DE theme
ART_PNG = "_inc/systems/artwork-outline/surprise.png"
LOGO_SVG = "_inc/systems/logos/surprise.svg"

# ES-DE on Android keeps downloaded themes off the card, so the card gets its own copy of the theme with the Surprise
# files added, under a folder name of its own (ES-DE prefers a downloaded theme of the same name). The copy comes from
# a GitHub archive of the theme kept in storage, which `sync-roms themes update` refreshes.
ESDE_THEME = "art-book-next-es-de"
ESDE_COPY = "art-book-next-sync-roms"
ESDE_REPO = "anthonycaccese/art-book-next-es-de"
ESDE_ARCHIVE = runtime.ESDE_THEMES_PREFIX + "art-book-next-es-de.tar.gz"
ESDE_COMMIT = runtime.ESDE_THEMES_PREFIX + "art-book-next-es-de.commit"  # the commit the archive was made from
ESDE_MARKER = ".sync-roms-commit"  # the same, in the card's copy
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


def _copy(src, dest):
    """Copy src to dest unless dest already has the same content. Returns whether it copied."""
    if os.path.exists(dest) and filecmp.cmp(src, dest, shallow=False):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    return True


def _art_files():
    """Paths (relative, /-separated) of the Surprise files in ART."""
    return sorted(os.path.relpath(os.path.join(root, f), ART).replace(os.sep, "/")
                  for root, _, files in os.walk(ART) for f in files)


# --- ES-DE ---------------------------------------------------------------------------------------------------------

def esde_wanted(base):
    """Whether the card's ES-DE uses Art Book Next (the downloaded theme or the card's copy of it)."""
    theme = frontend.get_string(_read(frontend.settings_path("esde", base)), "Theme")
    return theme in (ESDE_THEME, ESDE_COPY)


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


def install_esde(base):
    """Put Art Book Next with the Surprise art on the card and select it. Returns whether anything changed."""
    if not esde_wanted(base):
        return False
    dest = _esde_dir(base)
    commit = _stored_commit()
    changed = False
    if not commit:
        if not os.path.exists(os.path.join(dest, ESDE_MARKER)):
            ui.warn("Storage has no copy of Art Book Next for ES-DE, so the Surprise collection has no art; "
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
            ui.warn(f"Couldn't install Art Book Next for the Surprise collection: {e}")
            return False
        changed = True
    for rel in _art_files():
        changed |= _copy(os.path.join(ART, rel), s3.safe_join(dest, rel))
    _write_settings(frontend.settings_path("esde", base), "esde", {"Theme": ESDE_COPY})
    return changed


def describe_esde(base):
    if not esde_wanted(base):
        return
    commit = _stored_commit()
    if not commit and not os.path.exists(os.path.join(_esde_dir(base), ESDE_MARKER)):
        print(ui.dim("🎨 storage has no copy of Art Book Next for ES-DE (`sync-roms themes update` adds one)"))
        return
    if commit and commit != _card_commit(base):
        print(ui.dim(f"🎨 would copy Art Book Next ({commit[:7]}) into ES-DE/themes/{ESDE_COPY}"))
    print(ui.dim("🎨 would add the Surprise art to it and select it as the ES-DE theme"))


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


def install_knulli(base, name):
    """Put the Surprise art in Knulli's theme customizations for the collection called name. Returns whether files changed."""
    if not knulli_wanted(base):
        return False
    root = os.path.join(base, KNULLI_DIR)
    changed = _copy(os.path.join(ART, ART_PNG), os.path.join(root, "artwork", f"{name}.png"))
    changed |= _copy(os.path.join(ART, LOGO_SVG), os.path.join(root, "logos", f"{name}.svg"))
    _write_settings(frontend.settings_path("knulli", base), "knulli", knulli_settings(name),
                    only_if_unset={"UseCustomCollectionsSystemEx"})
    return changed


def describe_knulli(base, name):
    if knulli_wanted(base):
        print(ui.dim(f"🎨 would add the Surprise art to {KNULLI_DIR.replace(os.sep, '/')}/ and use it for {name}"))


def install(layout_name, base, name):
    """Add the Surprise collection's art for the frontend on the card. Returns whether files changed."""
    return install_esde(base) if layout_name == "esde" else install_knulli(base, name)


def describe(layout_name, base, name):
    describe_esde(base) if layout_name == "esde" else describe_knulli(base, name)
