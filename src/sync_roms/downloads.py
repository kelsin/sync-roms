"""Download planning, running and local ROM scanning."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import external, inventory, runtime, s3, ui


def rom_rel(key, flat, disc_dir=None, discs=()):
    """A ROM's path inside its system folder: the bucket key without its system, or just the file name if flat.

    disc_dir: the folder the layout keeps multi-disc games' discs in (those keys are in discs) beside their playlist.
    """
    rel = key.split("/", 1)[1]
    if disc_dir and key in discs and "/" not in rel:
        return disc_dir + "/" + rel
    return os.path.basename(rel) if flat else rel


def archive_extracted(path, listings=None):
    """Whether an archive's ROM is already beside it: a file with the archive's name and another extension.

    listings: a dict a caller keeps across calls, so each folder is listed once.
    """
    stem, ext = os.path.splitext(os.path.basename(path))
    folder = os.path.dirname(path)
    if ext.lower() not in external.ARCHIVE_EXTS:
        return False
    stems = listings.get(folder) if listings is not None else None
    if stems is None:
        stems = ({os.path.splitext(f)[0] for f in os.listdir(folder) if not f.lower().endswith(external.ARCHIVE_EXTS)}
                 if os.path.isdir(folder) else set())
        if listings is not None:
            listings[folder] = stems
    return stem in stems


def is_current(path, size, disc_dir=None):
    """Whether path is already storage's file; a playlist pointing into disc_dir is storage's with that prefix added."""
    if size is None or not os.path.exists(path):
        return False
    if os.path.getsize(path) == size:
        return True
    if disc_dir and path.lower().endswith(".m3u"):
        with open(path, "rb") as f:
            return len(f.read().replace(disc_dir.encode() + b"/", b"")) == size
    return False


def with_sizes(jobs):
    """jobs with any size left unread (None, from a folder listing without sizes) read now, in parallel; a file that
    has gone is dropped. Bucket listings carry every size, so for them this changes nothing."""
    todo = [k for k, _, size in jobs if size is None]
    if not todo:
        return jobs
    have = inventory.stat(todo)
    return [(k, p, have[k] if size is None else size) for k, p, size in jobs if size is not None or k in have]


def plan_downloads(jobs, unzip=False, disc_dir=None):
    """jobs: list of (s3_key, local_path, expected_size). Drops files already present, and with unzip the
    archives whose ROM was already extracted."""
    listings = {}
    return [(k, p, s) for k, p, s in jobs
            if not is_current(p, s, disc_dir) and not (unzip and archive_extracted(p, listings))]


def hide_discs(dest, disc_dir, discs, dry_run=False):
    """Move multi-disc games' discs already loose in dest into dest/disc_dir; returns their new paths."""
    moved = []
    for key in sorted(discs):
        name = os.path.basename(key)
        old, new = os.path.join(dest, name), os.path.join(dest, disc_dir, name)
        if os.path.isfile(old) and not os.path.exists(new):
            if not dry_run:
                os.makedirs(os.path.dirname(new), exist_ok=True)
                os.replace(old, new)
            moved.append(new)
    return moved


def failure_hint(error):
    """A short pointer for the common S3 failures; empty when there's nothing useful to add."""
    text = str(error)
    if "403" in text or "AccessDenied" in text or "Forbidden" in text:
        return " (access denied: check the profile can read this storage)"
    if "404" in text or "NoSuchKey" in text or "Not Found" in text:
        return " (not in storage any more)"
    if "No space left" in text:
        return " (the card is full)"
    if "timed out" in text.lower() or "Could not connect" in text:
        return " (network problem: re-run to retry)"
    return ""


def hard_exit():
    """Leave at once, without waiting for in-flight downloads (a second ^C)."""
    os._exit(130)


def run_downloads(todo, label, icon, base, failures=None):
    """Download the jobs; returns the number that failed. failures, if given, collects (key, reason) for each."""
    if not todo:
        print(ui.green(f"{icon} {label}: nothing to download ✨"))
        return 0
    print(ui.bold(f"\n{icon} {label}: downloading {len(todo)} file(s)"))
    failed = 0
    futs = []
    ex = ThreadPoolExecutor(runtime.WORKERS)
    moved = ui.ByteProgress([j[2] for j in todo])
    bar = ui.ProgressBar(len(todo), moved.fraction, moved.total, io=moved)
    try:
        futs += [(j, ex.submit(s3.download, j, lambda n, i=i: moved.add(i, n), moved.wrote)) for i, j in enumerate(todo)]
        for i, (j, f) in enumerate(futs, 1):
            prog = ui.dim(f"[{i}/{len(todo)}]")
            try:
                ui.wait_drawing(bar, i - 1, f.result)
                moved.finish(i - 1)
                src = j[0].split("/", 1)[0]
                rel = os.path.relpath(j[1], base)
                shown = j[0] if rel.split(os.sep, 1)[0] == src else f"{src} → {rel}"
                bar.say(f"  {prog} ✅ {shown}")
            except Exception as e:
                failed += 1
                moved.finish(i - 1)
                reason = (getattr(e, 'stderr', None) or str(e)).strip() + failure_hint(e)
                if failures is not None:
                    failures.append((j[0], reason))
                bar.say(f"  {prog} ❌ {ui.red(j[0])}: {reason}")
            bar.draw(i)
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        running = [f for _, f in futs if f.running()]
        bar.say(ui.yellow(f"🛑 Interrupted — finishing {len(running)} download(s) in flight (partly downloaded files restart on the next run). ^C again to abort now."))
        try:
            while any(f.running() for f in running):
                bar.draw(sum(f.done() for _, f in futs))
                time.sleep(ui.POLL)
        except KeyboardInterrupt:
            bar.clear()
            print(ui.red("🛑 Aborted"))
            hard_exit()
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
TEMP_DOWNLOAD = re.compile(r"\.(?:part|[0-9a-fA-F]{8})$")             # a download in progress or cut short (boto3 temp name)
# Dotfiles/folders that are OS litter; walk_roms(keep_dotfiles=True) drops only these (and "._*" AppleDouble files).
SYSTEM_DOT_NAMES = {".ds_store", ".localized", ".nomedia", ".appledouble", ".spotlight-v100", ".trashes",
                    ".fseventsd", ".temporaryitems", ".documentrevisions-v100", ".volumeicon.icns"}


def walk_roms(dest, keep_dotfiles=False, skip_db=False):
    """os.walk over dest that yields only real ROM-folder content (no frontend/OS leftovers).

    keep_dotfiles: keep dotfiles that are real content, dropping only OS litter (.DS_Store, ._*, ...).
    skip_db: drop *.db files (Onion's ROM list caches, named like _cache2.db or cache6.db).
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
                 if not hidden(f) and f.lower() not in IGNORED_FILES and not (skip_db and f.lower().endswith(".db")) and not TEMP_DOWNLOAD.search(f)
                 and not (at_root and f.lower() in IGNORED_ROOT_FILES)]
        yield root, files


def has_local_files(dest, skip_db=False, ignore=()):
    """True if dest has any ROM file (frontend files and dotfiles are ignored, and so are the ignore names at its top)."""
    return any(f for root, files in walk_roms(dest, skip_db=skip_db) for f in files
               if not (f in ignore and os.path.normpath(root) == os.path.normpath(dest)))


def find_extras(dest, wanted_keys, unzip=False, skip_db=False, disc_dir=None, discs=(), keep=()):
    """Local files under dest that aren't in the system's ROM list (frontend files and dotfiles are ignored;
    a .psvita file is kept while its .zip is listed).

    unzip: the layout extracts archives flat, so a listed archive's extracted ROM isn't an extra.
    disc_dir: the layout's folder for multi-disc games' discs (discs: their keys); its files are checked too.
    keep: paths inside dest that are expected too (BIOS files that go in the ROM folder).
    """
    rels = [rom_rel(k, unzip, disc_dir, discs) for k in wanted_keys]
    expected = {os.path.normpath(r) for r in rels} | {os.path.normpath(r) for r in keep}
    stems = {os.path.splitext(r)[0] for r in rels if r.lower().endswith(external.ARCHIVE_EXTS)} if unzip else set()
    extras = []
    walks = list(walk_roms(dest, skip_db=skip_db))
    if disc_dir:  # walk_roms skips dot folders, but the discs live in one
        walks += walk_roms(os.path.join(dest, disc_dir))
    for root, files in walks:
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.normpath(os.path.relpath(path, dest))
            if rel not in expected and os.path.splitext(rel)[0] not in stems:
                if rel.lower().endswith(".psvita") and os.path.splitext(rel)[0] + ".zip" in expected:
                    continue  # a Vita game's title id file lives and dies with its zip
                extras.append(path)
    return extras
