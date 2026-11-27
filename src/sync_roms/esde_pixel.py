"""The Pixel ES-DE theme on `esde` and `emudeck` cards: built from repo code into `cache/themes/esde/` and copied into
ES-DE's `themes/` folder. Sync never selects it: the user picks it in ES-DE."""
import hashlib
import os

from . import cardfs, downloads, frontend, store, ui
from .custom_themes.esde import build

THEME = build.THEME
MARKER = ".sync-roms-build"  # the build's key, in the cached build and (written last) in the card's copy
OWNED = ".sync-roms-collections"  # the collection names sync-roms gave art in the card's copy
ART_FOLDERS = ("consoles", "controllers")  # the variants' `systems/` folders, where a collection's art goes
LABEL = "the Pixel ES-DE theme"  # what a skipped step names
_ROOT = os.path.dirname(os.path.abspath(__file__))
# What the build reads: its code, the Pixel sprites and palettes, the font and the system list.
SOURCES = (os.path.join(_ROOT, "custom_themes", "esde"), os.path.join(_ROOT, "custom_themes", "pixel"),
           os.path.join(_ROOT, "custom_themes", "palettes.py"), os.path.join(store.REPO_DATA, "themes", "fusion-pixel"),
           os.path.join(store.REPO_DATA, "systems.json"))


def _source_files():
    for source in SOURCES:
        if os.path.isfile(source):
            yield source
            continue
        for folder, dirs, names in os.walk(source):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in names:
                if not name.endswith(".pyc"):
                    yield os.path.join(folder, name)


def key():
    """SHA-256 over the build's source files (their paths and bytes, in sorted path order)."""
    h = hashlib.sha256()
    for path in sorted(_source_files()):
        h.update(os.path.relpath(path, _ROOT).replace(os.sep, "/").encode() + b"\0")
        with open(path, "rb") as f:
            h.update(f.read())
        h.update(b"\0")
    return h.hexdigest()


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def cache_root():
    return os.path.join(store.cache_dir(), "themes", "esde")


def _count(path):
    """The number of files under path, its marker left out."""
    return sum(len(names) for _, _, names in os.walk(path)) - os.path.exists(os.path.join(path, MARKER))


def cached():
    """The built theme folder in the cache. Its marker holds the key and the build's file count: it is rebuilt when the
    sources changed, a build stopped before its marker, or files have gone from it since."""
    digest = key()
    path = os.path.join(cache_root(), THEME)
    if _read(os.path.join(path, MARKER)).split() != [digest, str(_count(path))]:
        build.build(cache_root())
        store.write_text(os.path.join(path, MARKER), f"{digest}\n{_count(path)}\n")
    return path


def dest(layout_name, base):
    return os.path.join(frontend.esde_dir(layout_name, base), "themes", THEME)


def shown(layout_name, base):
    """The copy's path from ES-DE's data folder's parent, for messages."""
    es_dir = frontend.esde_dir(layout_name, base)
    return os.path.relpath(dest(layout_name, base), os.path.dirname(os.path.normpath(es_dir))).replace(os.sep, "/")


def _kept(target):
    """name_keys of the files in target that sync-roms writes there itself: the collection list and its names' art and
    theme folders (`<name>/theme.xml`)."""
    names = [name for name in _read(os.path.join(target, OWNED)).splitlines() if name]
    rels = [MARKER, OWNED] + [f"systems/{folder}/{name}.png" for name in names for folder in ART_FOLDERS] \
        + [f"{name}/theme.xml" for name in names]
    return {downloads.name_key(os.path.join(target, *rel.split("/"))) for rel in rels}


def install(layout_name, base):
    """Bring the card's copy to the cached build: write the files that are missing or differ, remove the ones the build
    lacks except sync-roms's collection list and art, and write the marker last, so a stopped sync is finished by the
    next. Returns whether anything changed (False only when the card's marker
    already names this build)."""
    source = cached()
    digest = _read(os.path.join(source, MARKER)).split()[0]
    target = dest(layout_name, base)
    if _read(os.path.join(target, MARKER)).strip() == digest:
        return False
    wanted = set()
    for folder, _, names in os.walk(source):
        for name in names:
            rel = os.path.relpath(os.path.join(folder, name), source)
            if rel == MARKER:
                continue
            path = os.path.join(target, rel)
            wanted.add(downloads.name_key(path))
            with open(os.path.join(folder, name), "rb") as f:
                cardfs.write_bytes(path, f.read())
    keep = wanted | _kept(target)
    for folder, _, names in os.walk(target, topdown=False):
        for name in names:
            path = os.path.join(folder, name)
            if downloads.name_key(path) not in keep:  # cards ignore case
                os.remove(path)
        if folder != target and not os.listdir(folder):
            os.rmdir(folder)
    store.replace_file(os.path.join(target, MARKER), (digest + "\n").encode())
    cardfs.clear()  # the card changed: later steps list it afresh
    return True


def describe(layout_name, base):
    card = _read(os.path.join(dest(layout_name, base), MARKER)).strip()
    if card == key():
        return
    verb = "would update Pixel for ES-DE in" if card else "would install Pixel for ES-DE into"
    print(ui.dim(f"🎨 {verb} {shown(layout_name, base)}"))


def wanted(layout_name, entry):
    """Whether sync puts Pixel on this card: `esde` and `emudeck` cards with the `theme` flag on."""
    return layout_name in frontend.ESDE_LAYOUTS and store.card_flag(entry, "theme")


def step(layout_name, base, entry, dry_run, problem=None, skipped=None):
    """Sync's Pixel step: on `esde`/`emudeck` with the card's `theme` flag on, install or update Pixel (dry run: say so).
    problem is `frontend.emudeck_problem`'s answer for emudeck; skipped(LABEL) says it. Returns whether it changed
    anything."""
    if not wanted(layout_name, entry):
        return False
    if problem:
        if skipped:
            skipped(LABEL)
        return False
    if dry_run:
        describe(layout_name, base)
        return False
    fresh = not os.path.exists(os.path.join(dest(layout_name, base), MARKER))
    if not install(layout_name, base):
        return False
    print(ui.green(f"🎨 {'Installed' if fresh else 'Updated'} Pixel for ES-DE"))
    return True
