"""Download planning, running and local ROM scanning."""
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from . import external, runtime, s3, ui


def rom_rel(key, flat):
    """A ROM's path inside its system folder: the bucket key without its system, or just the file name if flat."""
    rel = key.split("/", 1)[1]
    return os.path.basename(rel) if flat else rel


def archive_extracted(path):
    """Whether an archive's ROM is already beside it: a file with the archive's name and another extension."""
    stem, ext = os.path.splitext(os.path.basename(path))
    folder = os.path.dirname(path)
    if ext.lower() not in external.ARCHIVE_EXTS or not os.path.isdir(folder):
        return False
    return any(os.path.splitext(f)[0] == stem and not f.lower().endswith(external.ARCHIVE_EXTS) for f in os.listdir(folder))


def plan_downloads(jobs, unzip=False):
    """jobs: list of (s3_key, local_path, expected_size). Drops files already present, and with unzip the
    archives whose ROM was already extracted."""
    return [(k, p, s) for k, p, s in jobs
            if not (s is not None and os.path.exists(p) and os.path.getsize(p) == s)
            and not (unzip and archive_extracted(p))]


def run_downloads(todo, label, icon, base):
    if not todo:
        print(ui.green(f"{icon} {label}: nothing to download ✨"))
        return 0
    print(ui.bold(f"\n{icon} {label}: downloading {len(todo)} file(s)"))
    failed = 0
    ex = ThreadPoolExecutor(runtime.WORKERS)
    moved = ui.ByteProgress([j[2] for j in todo])
    bar = ui.ProgressBar(len(todo), moved.fraction, sum(moved.size))
    try:
        futs = [(j, ex.submit(s3.download, j, lambda n, i=i: moved.add(i, n))) for i, j in enumerate(todo)]
        for i, (j, f) in enumerate(futs, 1):
            prog = ui.dim(f"[{i}/{len(todo)}]")
            try:
                while True:
                    try:
                        f.result(timeout=0.25)
                        break
                    except FutureTimeout:
                        bar.draw(i - 1)
                moved.finish(i - 1)
                src = j[0].split("/", 1)[0]
                rel = os.path.relpath(j[1], base)
                shown = j[0] if rel.split(os.sep, 1)[0] == src else f"{src} → {rel}"
                bar.say(f"  {prog} ✅ {shown}")
            except Exception as e:
                failed += 1
                moved.finish(i - 1)
                bar.say(f"  {prog} ❌ {ui.red(j[0])}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
            bar.draw(i)
    except KeyboardInterrupt:
        bar.say(ui.yellow("🛑 Interrupted — dropping queued downloads, finishing the ones in flight..."))
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        bar.clear()
    return failed


# Files/folders that frontends put in a system's ROM folder. They aren't ROMs, so they never
# count as "files present" and are never offered for deletion (dotfiles are ignored too).
IGNORED_ROOT_FILES = {
    "systeminfo.txt", "systems.txt", "noload.txt", "flatten.txt",  # ES-DE
    "_info.txt", "gamelist.xml",                                   # Batocera / Knulli
    "miyoogamelist.xml",                                           # Onion
}
IGNORED_ROOT_DIRS = {"images", "videos", "manuals",                # Batocera / Knulli scraped media
                     "imgs"}                                       # Onion scraped box art
IGNORED_FILES = {"thumbs.db", "desktop.ini"}                       # Windows
# Dotfiles/folders that are OS litter; walk_roms(keep_dotfiles=True) drops only these (and "._*" AppleDouble files).
SYSTEM_DOT_NAMES = {".ds_store", ".localized", ".nomedia", ".appledouble", ".spotlight-v100", ".trashes",
                    ".fseventsd", ".temporaryitems", ".documentrevisions-v100", ".volumeicon.icns"}


def walk_roms(dest, keep_dotfiles=False):
    """os.walk over dest that yields only real ROM-folder content (no frontend/OS leftovers).

    keep_dotfiles: keep dotfiles that are real content, dropping only OS litter (.DS_Store, ._*, ...).
    """
    def hidden(name):
        if not name.startswith("."):
            return False
        return not keep_dotfiles or name.lower() in SYSTEM_DOT_NAMES or name.startswith("._")

    for root, dirs, files in os.walk(dest):
        at_root = os.path.normpath(root) == os.path.normpath(dest)
        dirs[:] = [d for d in dirs
                   if not hidden(d) and not (at_root and d.lower() in IGNORED_ROOT_DIRS)]
        files = [f for f in files
                 if not hidden(f) and f.lower() not in IGNORED_FILES
                 and not (at_root and f.lower() in IGNORED_ROOT_FILES)]
        yield root, files


def has_local_files(dest):
    """True if dest has any ROM file (frontend files and dotfiles are ignored)."""
    return any(files for _, files in walk_roms(dest))


def find_extras(dest, wanted_keys, unzip=False):
    """Local files under dest that aren't in the system's ROM list (frontend files and dotfiles are ignored).

    unzip: the layout extracts archives flat, so a listed archive's extracted ROM isn't an extra.
    """
    rels = [rom_rel(k, unzip) for k in wanted_keys]
    expected = {os.path.normpath(r) for r in rels}
    stems = {os.path.splitext(r)[0] for r in rels if r.lower().endswith(external.ARCHIVE_EXTS)} if unzip else set()
    extras = []
    for root, files in walk_roms(dest):
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.normpath(os.path.relpath(path, dest))
            if rel not in expected and os.path.splitext(rel)[0] not in stems:
                extras.append(path)
    return extras
