"""Download planning, running and local ROM scanning."""
import contextlib
import os
import queue
import re
import sys
import tempfile
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import cardfs, external, inventory, m3u, runtime, s3, store, ui

STALE_HINT = " (not in storage any more: run sync-roms cache update)"  # a file the cache lists is gone from the storage folder


def rom_rel(key, disc_dir=None, discs=(), folders=None):
    """A ROM's path inside its system folder: the bucket key without its system.

    disc_dir: the folder the layout keeps multi-disc games' discs in (those keys are in discs) beside their playlist.
    folders: {key: its game's folder} (m3u.game_folders) for layouts that keep each disc game in a folder of its own.
    """
    rel = key.split("/", 1)[1]
    if disc_dir and key in discs and "/" not in rel:
        return disc_dir + "/" + rel
    if folders and key in folders and "/" not in rel:
        return folders[key] + "/" + rel
    return rel


def is_current(path, size, disc_dir=None):
    """Whether path is already storage's file; a playlist pointing into disc_dir is storage's with that prefix added."""
    if size is None:
        return False
    have = cardfs.size(path)
    if have is None:
        return False
    if have == size:
        return True
    if disc_dir and path.lower().endswith(".m3u"):
        try:
            return len(cardfs.read(path).replace(disc_dir.encode() + b"/", b"")) == size
        except OSError:
            return False
    return False


def bios_folders(system, layout_name, layout, bios_dir):
    """The card folders a system's BIOS files go in: the BIOS folder, or for layouts that sort BIOS by tag, its tag folders."""
    if not layout.get("bios_by_tag"):
        return [bios_dir]
    tag = store.folder_tag(system["folders"].get(layout_name))
    if not tag:
        return []
    return [os.path.join(bios_dir, t) for t in [tag, *system.get("nextui_bios_tags", [])]]


def with_sizes(jobs):
    """jobs with any size left unread (None, from a folder listing without sizes) read now, in parallel; a file that
    has gone is dropped. Bucket listings carry every size, so for them this changes nothing."""
    todo = [k for k, _, size in jobs if size is None]
    if not todo:
        return jobs
    have = inventory.stat(todo)
    return [(k, p, have[k] if size is None else size) for k, p, size in jobs if size is not None or k in have]


def plan_downloads(jobs, disc_dir=None):
    """jobs: list of (s3_key, local_path, expected_size). Drops files already present."""
    return [(k, p, s) for k, p, s in jobs if not is_current(p, s, disc_dir)]


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
    missing = getattr(error, "filename", None)
    if "No such file" in text and runtime.ROOT and missing and os.path.abspath(missing).startswith(os.path.join(runtime.ROOT, "")):
        return STALE_HINT
    if "No space left" in text:
        return " (the card is full)"
    if "timed out" in text.lower() or "Could not connect" in text:
        return " (network problem: re-run to retry)"
    return ""


def hard_exit():
    """Leave at once, without waiting for in-flight downloads (a second ^C)."""
    os._exit(130)


def download_playlist(job, disc_dir, coming, callback=None, wrote=None):
    """Write a playlist to its path once, its entries already pointing into disc_dir (m3u.prefixed_playlist; coming: the
    name keys of the paths this sync downloads)."""
    key, path, size = job
    with tempfile.TemporaryDirectory() as tmp:
        temp = os.path.join(tmp, "playlist.m3u")
        s3.download((key, temp, size), callback, wrote)
        with open(temp, "rb") as f:
            data = f.read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.replace_file(path, m3u.prefixed_playlist(data, os.path.dirname(path), disc_dir, lambda p: name_key(p) in coming))


def run_downloads(todo, label, icon, base, failures=None, disc_dirs=None):
    """Download the jobs; returns the number that failed. failures, if given, collects (key, reason) for each.

    disc_dirs: {ROM folder: its layout's disc folder}; a playlist directly in one is written with its entries pointing there."""
    if not todo:
        print(ui.green(f"{icon} {label}: nothing to download ✨"))
        return 0
    print(ui.bold(f"\n{icon} {label}: downloading {len(todo)} file(s)"))
    failed = 0
    futs = []
    ex = ThreadPoolExecutor(runtime.WORKERS)
    moved = ui.ByteProgress([j[2] for j in todo])
    names = [j[0] for j in todo]
    bar = ui.ProgressBar(len(todo), moved.fraction, moved.total, io=moved, active=lambda: moved.active(names))

    coming = {name_key(j[1]) for j in todo} if disc_dirs else ()

    def fetch(i, j):
        moved.start(i)
        disc_dir = disc_dirs and j[1].lower().endswith(".m3u") and disc_dirs.get(os.path.normpath(os.path.dirname(j[1])))
        if disc_dir:
            download_playlist(j, disc_dir, coming, lambda n: moved.add(i, n), moved.wrote)
        else:
            s3.download(j, lambda n: moved.add(i, n), moved.wrote)

    try:
        finishing = queue.Queue()  # each future queues itself as it ends: a wait() per file would be O(files in flight)
        futs += [(j, ex.submit(fetch, i, j)) for i, j in enumerate(todo)]
        index = {f: i for i, (_, f) in enumerate(futs)}
        for _, f in futs:
            f.add_done_callback(finishing.put)
        for finished in range(1, len(todo) + 1):
            f = ui.wait_drawing(bar, finished - 1, finishing.get)
            j = todo[index[f]]
            prog = ui.dim(f"[{finished}/{len(todo)}]")
            moved.finish(index[f])
            try:
                f.result()
                src = j[0].split("/", 1)[0]
                rel = os.path.relpath(j[1], base)
                shown = j[0] if rel.split(os.sep, 1)[0] == src else f"{src} → {rel}"
                bar.say(f"  {prog} ✅ {shown}")
            except Exception as e:
                failed += 1
                reason = (getattr(e, 'stderr', None) or str(e)).strip() + failure_hint(e)
                if failures is not None:
                    failures.append((j[0], reason))
                line = f"  {prog} ❌ {ui.red(j[0])}: {reason}"
                if ui.QUIET:
                    ui.failure(line)
                else:
                    bar.say(line)
            bar.draw(finished)
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        running = [(i, j, f) for i, (j, f) in enumerate(futs) if not f.done()]
        bar.say(ui.yellow(f"🛑 Interrupted — finishing {len(running)} download(s) in flight (partly downloaded files restart on the next run). ^C again to abort now."))
        try:
            while running:
                for i, j, f in [r for r in running if r[2].done()]:
                    running.remove((i, j, f))
                    moved.finish(i)
                    if f.exception() is None:
                        bar.say(f"  ✅ {j[0]}")
                    elif ui.QUIET:
                        ui.failure(f"  ❌ {ui.red(j[0])}: {f.exception()}")
                    else:
                        bar.say(f"  ❌ {ui.red(j[0])}: {f.exception()}")
                bar.draw(sum(f.done() for _, f in futs))
                time.sleep(ui.POLL)
        except KeyboardInterrupt:
            bar.clear()
            for _, j, _ in running:  # hard_exit skips s3.download's own cleanup
                with contextlib.suppress(OSError):
                    os.remove(j[1] + ".part")
            print(ui.red("🛑 Aborted"))
            sys.stdout.flush()
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
ROCKNIX_PORTS_FILES = ("Install Collections.sh", "RAOfflineProxy Install.sh")  # sync-roms's scripts, run from ROCKNIX's Ports


def layout_files(layout_name, system):
    """Names at the top of the system's ROM folder that sync-roms put there for this layout: never offered for deletion."""
    return ROCKNIX_PORTS_FILES if layout_name == "rocknix" and system["bucket"] == "ports" else ()


PICO8_FILES = ("pico8_dyn", "pico8_64", "pico8.dat")  # the proprietary PICO-8 runtime that pico8.py extracts into ROCKNIX's pico8 ROM folder
OWN_ROOT_FILES = {"ports": ROCKNIX_PORTS_FILES, "pico8": PICO8_FILES}


def never_uploaded(bucket, rel):
    """Whether rel, a path in a local copy of the bucket's folder, is one of sync-roms's own files (never a ROM)."""
    return rel in OWN_ROOT_FILES.get(bucket, ())


IGNORED_ROOT_DIRS = {"images", "videos", "manuals",                # Batocera / Knulli scraped media
                     "imgs"}                                       # Onion scraped box art
IGNORED_FILES = {"thumbs.db", "desktop.ini"}                       # Windows
TEMP_DOWNLOAD = re.compile(r"\.(?:part|[0-9a-fA-F]{8})$")             # a download in progress or cut short (boto3 temp name)
# Dotfiles/folders that are OS litter; walk_roms(keep_dotfiles=True) drops only these and sync-roms's own temp names.
SYSTEM_DOT_NAMES = {".ds_store", ".localized", ".nomedia", ".appledouble", ".spotlight-v100", ".trashes",
                    ".fseventsd", ".temporaryitems", ".documentrevisions-v100", ".volumeicon.icns"}


RENAME_TEMP = ".rename"  # rename_on_card's temporary name ends with it, after a leading dot


def rename_temp(name):
    """Whether name is rename_on_card's temporary name, left behind when a rename was cut short."""
    return name.startswith(".") and name.endswith(RENAME_TEMP) and len(name) > len(RENAME_TEMP) + 1


def walk_roms(dest, keep_dotfiles=False, skip_db=False, rename_temps=False):
    """A walk over dest that yields only real ROM-folder content (no frontend/OS leftovers).

    keep_dotfiles: keep dotfiles that are real content, dropping only OS litter (.DS_Store, ._*, ...) and sync-roms's
    own temp names (.chd-*, .xiso-*, external.own_temp).
    skip_db: drop *.db files (Onion's ROM list caches, named like _cache2.db or cache6.db).
    rename_temps: keep rename_on_card's temporary names.
    """
    def hidden(name):
        if not name.startswith("."):
            return False
        return not keep_dotfiles or name.lower() in SYSTEM_DOT_NAMES or external.own_temp(name)

    for root, dirs, files in cardfs.walk(dest):
        at_root = os.path.normpath(root) == os.path.normpath(dest)
        dirs[:] = [d for d in dirs
                   if not hidden(d) and not (at_root and d.lower() in IGNORED_ROOT_DIRS)]
        files = [f for f in files
                 if (rename_temps and rename_temp(f)) or not hidden(f) and f.lower() not in IGNORED_FILES and not (skip_db and f.lower().endswith(".db")) and not TEMP_DOWNLOAD.search(f)
                 and not (at_root and f.lower() in IGNORED_ROOT_FILES)]
        yield root, files


def has_local_files(dest, skip_db=False, ignore=()):
    """True if dest has any ROM file (frontend files and dotfiles are ignored, and so are the ignore names at its top)."""
    return any(f for root, files in walk_roms(dest, skip_db=skip_db) for f in files
               if not (f in ignore and os.path.normpath(root) == os.path.normpath(dest)))


def name_key(path):
    """A card path as a case-insensitive card compares names: case and Unicode form left out."""
    return unicodedata.normalize("NFC", os.path.normpath(path)).casefold()


def find_extras(dest, wanted_keys, skip_db=False, disc_dir=None, discs=(), keep=(), renames=None, folders=None):
    """Local files under dest that aren't in the system's ROM list (frontend files and dotfiles are ignored;
    a .psvita file is kept while its .zip is listed).

    disc_dir: the layout's folder for multi-disc games' discs (discs: their keys); its files are checked too.
    folders: {key: its game's folder} (m3u.game_folders), for layouts that keep each disc game in a folder of its own.
    keep: paths inside dest that are expected too (BIOS files that go in the ROM folder).
    renames: if given, gets (path, storage's spelling) for each file that is an expected one spelled differently (case,
    Unicode form). Such a file is never an extra, unless the expected spelling is on the card too (a case-sensitive card).
    """
    rels = [rom_rel(k, disc_dir, discs, folders) for k in wanted_keys]
    expected = {os.path.normpath(r) for r in rels} | {os.path.normpath(r) for r in keep}
    spellings = defaultdict(list)  # {name_key: the expected paths with it}
    for rel in expected:
        spellings[name_key(rel)].append(rel)
    walks = list(walk_roms(dest, skip_db=skip_db, rename_temps=True))
    if disc_dir:  # walk_roms skips dot folders, but the discs live in one
        walks += walk_roms(os.path.join(dest, disc_dir), rename_temps=True)
    found = [(os.path.join(root, f), os.path.normpath(os.path.relpath(os.path.join(root, f), dest)))
             for root, files in walks for f in files]
    on_card = defaultdict(list)  # {name_key: the card's paths with it}
    for _, rel in found:
        on_card[name_key(rel)].append(rel)
    extras = []
    for path, rel in found:
        if rename_temp(os.path.basename(rel)):
            extras.append(path)  # a rename cut short: its file is downloaded again
            continue
        if rel in expected:
            continue
        key = name_key(rel)
        if key in spellings:
            if any(r in expected for r in on_card[key]):
                extras.append(path)  # a second file beside the expected one
            elif renames is not None and len(spellings[key]) == 1 and len(on_card[key]) == 1:
                renames.append((path, os.path.join(dest, spellings[key][0])))
            continue  # more than one way to match it: kept as it is, never deleted
        if rel.lower().endswith(".psvita") and name_key(os.path.splitext(rel)[0] + ".zip") in spellings:
            continue  # a Vita game's title id file lives and dies with its zip
        extras.append(path)
    return extras


def rename_on_card(path, new):
    """Rename path to new through a temporary name in new's folder: a case-only rename straight to new does nothing on a
    case-insensitive card."""
    folder = os.path.dirname(new)
    os.makedirs(folder, exist_ok=True)
    temp = os.path.join(folder, f".{os.path.basename(new)}{RENAME_TEMP}")
    os.replace(path, temp)
    os.replace(temp, new)


def after_renames(todo, renames, disc_dir=None):
    """todo once renames ((path, new path) pairs) are done: a job for a renamed file writes to its new spelling, and is
    dropped when the renamed file is already storage's (a case-sensitive card, where the download plan missed it)."""
    renamed = {name_key(new): (path, new) for path, new in renames}
    out = []
    for key, path, size in todo:
        old, new = renamed.get(name_key(path), (None, path))
        if old is None or not is_current(old, size, disc_dir):
            out.append((key, new, size))
    return out


def plan_moves(todo, extra_sizes):
    """(extra path, job) pairs: a job's file that an unwanted card file can become instead of being downloaded, matched by
    base name (case and Unicode form left out) and size, never by content. extra_sizes: {extra path: size}. A name and size
    that more than one extra or more than one job has moves nothing."""
    extras, jobs = defaultdict(list), defaultdict(list)
    for path, size in extra_sizes.items():
        extras[name_key(os.path.basename(path)), size].append(path)
    for job in todo:
        if job[2] is not None:
            jobs[name_key(os.path.basename(job[1])), job[2]].append(job)
    return [(extras[match][0], found[0]) for match, found in jobs.items()
            if len(found) == 1 and len(extras.get(match, ())) == 1]
