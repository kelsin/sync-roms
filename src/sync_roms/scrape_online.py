"""Online scraping: which ROMs need metadata, which ScreenScraper game each one is, and the scrape run."""
import contextlib
import getpass
import hashlib
import http.client
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
import threading
import time
import zlib
from collections import Counter, deque, namedtuple
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from botocore.exceptions import ClientError

from . import inventory, runtime, s3, scrape_files, scrape_plan, scrape_state, screenscraper, store, ui, upload, usersettings

CHUNK = 8 << 20


def find_candidates(systems, roms, metadata, retry=False, fill=None):
    """{system folder: sorted ROM paths} with no entry in that system's metadata.json (and, unless retry, not marked
    unknown; a saved manual match overrides the unknown mark). Non-games waiting for review are never taken.

    fill: (wanted media types, {system folder: scrapes/<system>/ listing}); also takes the ROMs that have an entry
    but lack some wanted type in storage that ScreenScraper's last answer offered (unless retry, any type)."""
    out, state = {}, scrape_state.snapshot()
    for s in systems:
        system = s["bucket"]
        have = metadata.get(system, {})
        index = scrape_plan.scrape_index(fill[1].get(system, {})) if fill else {}

        def wanted(r):
            return r not in have or (fill and fill[0] - set(index.get(os.path.splitext(r)[0], ()))
                                     - (set() if retry else state.not_offered(system, r)))
        out[system] = sorted(r for r in roms.get(system, ())
                             if wanted(r) and not state.is_notgame(system, r)
                             and (retry or state.manual_match(system, r) is not None or not state.is_unknown(system, r)))
    return out


def hash_file(system, rom, size, mtime, stop=None):
    """{"md5","sha1","crc"} of a ROM read from the storage folder or mirror (one open file, one reused buffer), cached by
    size and mtime. Raises screenscraper.Stopped when the stop event is set between chunks."""
    cached = scrape_state.cached_hashes(system, rom, size, mtime)
    if cached:
        return cached
    md5, sha1, crc = hashlib.md5(), hashlib.sha1(), 0
    buf = bytearray(min(CHUNK, size))
    with open(s3.safe_join(s3.read_root(), f"{system}/{rom}"), "rb") as f:
        for start in range(0, size, CHUNK):
            if stop is not None and stop.is_set():
                raise screenscraper.Stopped()
            n = f.readinto(memoryview(buf)[:min(CHUNK, size - start)])
            chunk = memoryview(buf)[:n]
            md5.update(chunk)
            sha1.update(chunk)
            crc = zlib.crc32(chunk, crc)
    hashes = {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "crc": f"{crc:08X}"}
    scrape_state.save_hashes(system, rom, size, mtime, hashes)
    return hashes


_hashing = {}  # (system, ROM) -> Future of a hash being computed ahead of its lookup
_hashing_lock = threading.Lock()


_mtimes = {}  # (system, ROM) -> mtime of a candidate, taken when the candidates were stat'ed


def _mtime(name, rom):
    if (name, rom) in _mtimes:
        return _mtimes[name, rom]
    return int(os.path.getmtime(s3.safe_join(s3.read_root(), f"{name}/{rom}")))


def _stat_roms(candidates):
    """{system: {ROM: (size, mtime)}} of the candidate ROMs that are files in the read folder: one stat each, in
    parallel, instead of walking the system's folder. The mtimes are kept for _mtime."""
    jobs = [(name, rom) for name, roms in candidates.items() for rom in roms]

    def stat_one(job):
        try:
            st = os.stat(s3.safe_join(s3.read_root(), f"{job[0]}/{job[1]}"))
        except (OSError, ValueError):
            return None
        return (st.st_size, int(st.st_mtime)) if stat.S_ISREG(st.st_mode) else None
    with ThreadPoolExecutor(s3.STAT_WORKERS) as ex:
        stats = list(ex.map(stat_one, jobs))
    out = {name: {} for name in candidates}
    for (name, rom), st in zip(jobs, stats):
        if st:
            out[name][rom] = st
            _mtimes[name, rom] = st[1]
    return out


def _candidate_etags(candidates):
    """{system: {ROM: (size, etag)}} for the candidate ROMs. A storage folder has no ETags, so it is never listed: the
    candidates are stat'ed and get the fake "mtime-size" tag; a bucket is listed (and a mirror's files stat'ed for hashing)."""
    _mtimes.clear()
    if runtime.ROOT:
        return {name: {rom: (size, f"{mtime}-{size}") for rom, (size, mtime) in found.items()}
                for name, found in _stat_roms(candidates).items()}
    etags = _each(lambda name: inventory.etags(name + "/"), candidates)
    if s3.read_root():
        _stat_roms({name: [r for r in roms if r in etags[name]] for name, roms in candidates.items()})
    return etags


def prefetch_hash(pool, name, rom, size, stop):
    """Hash a ROM on the pool so its lookup, on a ScreenScraper thread, finds the hashes ready instead of reading the
    file itself. Only for ROMs read from a folder; a ROM already hashed or being hashed is left alone."""
    key = (name, rom)
    try:
        mtime = _mtime(name, rom)
    except (OSError, ValueError):
        return  # the lookup reports it
    if scrape_state.cached_hashes(name, rom, size, mtime):
        return
    with _hashing_lock:
        if key in _hashing or scrape_state.cached_hashes(name, rom, size, mtime):  # finished since the check above
            return
        _hashing[key] = fut = pool.submit(hash_file, name, rom, size, mtime, stop)
    fut.add_done_callback(lambda _: _forget_hashing(key))


def _forget_hashing(key):
    with _hashing_lock:
        _hashing.pop(key, None)


def _hashes(name, rom, size, stop):
    """hash_file's result, waiting for a prefetch of the same ROM instead of hashing it twice."""
    with _hashing_lock:
        fut = _hashing.get((name, rom))
    if fut is not None:
        return fut.result()
    return hash_file(name, rom, size, _mtime(name, rom), stop)


def match(client, system, rom, size, etag, game_id=None, stop=None):
    """(game id, how) for a ROM; how is "manual", "hash" or "name+size". Raises screenscraper.NotFound.

    One lookup sends the hashes, name and size together; it counts as "hash" only when the ROM ScreenScraper
    matched carries one of the hashes sent. A storage folder's file over HASH_MAX is sent without hashes unless they
    are cached, and hashed for one more lookup when that finds nothing. game_id: a match given for this run only
    (`scrape match`)."""
    if game_id:
        return game_id, "manual"
    name = system["bucket"]
    saved = scrape_state.manual_match(name, rom)
    if saved is not None:
        return saved, "manual"
    hashes = {}
    if s3.read_root():  # a folder's ETag is a fake "mtime-size" tag; hash the file instead
        hashes = _hashes(name, rom, size, stop) if size <= HASH_MAX else scrape_state.cached_hashes(name, rom, size, _mtime(name, rom)) or {}
    elif "-" not in (tag := etag.strip('"')):  # a multipart upload's ETag is not the file's MD5
        hashes = {"md5": tag}
    try:
        game = client.lookup(system["screenscraper"], os.path.basename(rom), size, **hashes)
    except screenscraper.NotFound:
        if hashes or not s3.read_root():
            raise
        hashes = _hashes(name, rom, size, stop)
        game = client.lookup(system["screenscraper"], os.path.basename(rom), size, **hashes)
    return screenscraper.to_int(game.get("id")), "hash" if screenscraper.rom_hash_matches(game, hashes) else "name+size"


def resolve_manual(client, system, query):
    """A game id: the query itself when it is an integer, else the user's pick from a ScreenScraper search."""
    query = query.strip()
    if query.isdigit():
        if int(query) > 0:
            return int(query)
        raise screenscraper.NotFound(f"no game {query}")
    results = client.search(system["screenscraper"], query)
    if not results:
        raise screenscraper.NotFound(f"no results for {query!r}")
    for i, (_, title) in enumerate(results, 1):
        print(f"  {i}. {title}")
    while True:
        answer = ui.ask("Pick a number (empty to cancel): ").strip()
        if not answer:
            raise screenscraper.NotFound("cancelled")
        if answer.isdigit() and 1 <= int(answer) <= len(results):
            return results[int(answer) - 1][0]


# --- The scrape run ---------------------------------------------------------------------------------
BATCH = 25  # ROMs scraped and uploaded together
LOOKAHEAD = 2  # batches in the pool at once: the next one is scraped while the last uploads
HASH_THREADS = 4  # ROMs hashed at once ahead of their lookups
HASH_MAX = 64 << 20  # bigger files in a storage folder are hashed only when their name and size find nothing (a bucket has no MD5 for them either)
METADATA_INTERVAL = 60  # seconds of scraped ROMs whose entries are written to metadata.json together
RETRIES = 3  # times a rate-limited or transient request is tried again
RETRY_WAIT = 10  # seconds before the first retry, doubled each time: 70 s in all, past a per-minute cap
UNREACHABLE_STOP = 3  # ROMs in a row that can't reach ScreenScraper after their retries stop the run
CREDENTIALS = ("screenscraper_user", "screenscraper_password")
# What one ROM's lookup and downloads can raise besides NotFound and QuotaExceeded: the client's own errors and
# those it doesn't wrap (a read cut short, a timeout, a malformed media URL, an unsafe ROM path).
ROM_ERRORS = (screenscraper.ApiError, OSError, ValueError, http.client.HTTPException)
IMAGE_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"))
SHOWN = 10
SCRAPER_TYPES = set(screenscraper.MEDIA_MAP.values()) | {scrape_plan.ONION_TYPE, scrape_plan.SLOT_TYPE}  # never custom/


class _RomClient:
    """One ROM's view of the client: rate-limited and transient requests are retried (the waits end when stop is set),
    and the game a lookup found is kept."""

    def __init__(self, client, stop=None):
        self.client, self.stop, self.found = client, stop, None

    def lookup(self, *args, **kwargs):
        self.found = _retry(self.stop, self.client.lookup, *args, **kwargs)
        return self.found

    def game(self, game_id):
        return _retry(self.stop, self.client.game, game_id)

    def search(self, system_id, name):
        return _retry(self.stop, self.client.search, system_id, name)

    def download(self, url, dest, **kwargs):
        return _retry(self.stop, self.client.download, url, dest, **kwargs)


def _retry(stop, call, /, *args, **kwargs):
    """call's result; a rate-limited or transient failure is tried again RETRIES times, after RETRY_WAIT seconds doubled
    each time. Raises screenscraper.Stopped when the stop event (None: there is none) is set while waiting."""
    for attempt in range(RETRIES + 1):
        try:
            return call(*args, **kwargs)
        except (screenscraper.RateLimited, screenscraper.Transient):
            if attempt == RETRIES:
                raise
            if (stop or threading.Event()).wait(RETRY_WAIT * 2 ** attempt):
                raise screenscraper.Stopped() from None


class _Unreachable:
    """The run's count of ROMs in a row (in the order they end) that couldn't reach ScreenScraper after their retries,
    shared by the lookup threads; error: the Transient error that stopped the run, once the count reached UNREACHABLE_STOP."""

    def __init__(self):
        self.lock, self.count, self.error = threading.Lock(), 0, None

    def reset(self):
        with self.lock:
            self.count, self.error = 0, None

    def add(self, e):
        """Count a ROM's outcome (e: its Transient error, None for any other outcome); whether the run must stop."""
        with self.lock:
            self.count = self.count + 1 if e is not None else 0
            if self.count >= UNREACHABLE_STOP and self.error is None:
                self.error = e
            return self.error is not None


_unreachable = _Unreachable()


def make_client():
    """A ScreenScraper client from the credentials in settings.json; fails, saying how to set them, when any is missing."""
    settings = usersettings.load_settings()
    missing = [k for k in CREDENTIALS if not settings.get(k)]
    if missing:
        ui.fail(f"ScreenScraper credentials missing: {', '.join(missing)}. Set them with `sync-roms scrape --set-credentials`, "
                f"or add {', '.join(CREDENTIALS)} to {os.path.join(store.data_dir(), 'settings.json')} "
                "(your ScreenScraper login)", 3)
    return screenscraper.Client(settings["screenscraper_user"], settings["screenscraper_password"],
                                {"devid": screenscraper.DEV_ID, "devpassword": screenscraper.DEV_PASSWORD})


PROMPTS = (("screenscraper_user", "ScreenScraper username", False), ("screenscraper_password", "ScreenScraper password", True))


def set_credentials():
    """Ask for the ScreenScraper login and save them in settings.json. A blank answer keeps the saved value;
    passwords are read without echo and no value is ever printed."""
    saved = usersettings.load_settings()
    answers = {}
    try:
        for key, label, secret in PROMPTS:
            note = " [Enter keeps the saved value]" if saved.get(key) else ""
            ask = getpass.getpass if secret else input
            answers[key] = ask(f"{label}{note}: ").strip()
    except EOFError:
        ui.fail("Credentials not saved", 2)
    except KeyboardInterrupt:
        print(ui.yellow("\n👋 Credentials not saved"))
        return 130
    answers = {k: v for k, v in answers.items() if v}
    if not answers:
        print(ui.yellow("Nothing changed"))
        return 0
    usersettings.save_settings({**usersettings.load_settings(), **answers})
    print(ui.green("✅ Saved ScreenScraper credentials to " + os.path.join(store.data_dir(), "settings.json")))
    try:
        quota = make_client().quota()
    except screenscraper.Refused as e:
        ui.failure(ui.red(f"❌ Credentials saved, but ScreenScraper refused the check: {e}"))
        return 1
    except (screenscraper.QuotaExceeded, screenscraper.ApiError) as e:
        ui.failure(ui.yellow(f"⚠️  Credentials saved, but the login couldn't be checked: {e}"))
        return 0
    if quota is None:
        ui.failure(ui.yellow(f"⚠️  {NO_ACCOUNT}"))
    else:
        print(ui.green(f"✅ ScreenScraper: {_quota_line(quota)}"))
    return 0


NO_ACCOUNT = "ScreenScraper sent no account details for your login; check it with `sync-roms scrape --set-credentials`"


def _quota_line(quota):
    return f"{quota.used_today}/{quota.max_today} requests used today, {quota.max_threads} thread(s)"


def _each(fn, names):
    """{name: fn(name)} for each name, run on several threads (each call waits on storage); the first error is raised."""
    names = list(names)
    if len(names) < 2:
        return {n: fn(n) for n in names}
    with ThreadPoolExecutor(min(len(names), runtime.WORKERS)) as ex:
        return dict(zip(names, ex.map(fn, names)))


def metadata_key(system):
    return f"{scrape_plan.SCRAPES}/{system}/metadata.json"


def load_metadata(system):
    """A system's metadata.json from storage ({} when there is none). Raises ValueError if it isn't a JSON object."""
    try:
        text = s3.get_text(metadata_key(system))
    except FileNotFoundError:
        return {}
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return {}
        raise
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{metadata_key(system)} isn't a JSON object")
    return data


def planned_match(system, rom, size, etag):
    """How match() will look a ROM up first, without asking ScreenScraper."""
    if scrape_state.manual_match(system, rom) is not None:
        return "manual"
    if s3.read_root():
        return "hash" if size <= HASH_MAX or _cached(system, rom, size) else "name+size"
    return "hash" if "-" not in etag.strip('"') else "name+size"


def _cached(system, rom, size):
    return scrape_state.cached_hashes(system, rom, size, _mtimes.get((system, rom))) is not None


def report(systems_candidates, matches):
    """Lines per system: ROMs to scrape, how many matched by hash, by name+size and manually, and the unmatched ones.

    matches: {system: {ROM: "hash" | "name+size" | "manual", or None when ScreenScraper doesn't know it}}; a ROM
    missing from it wasn't scraped (failed or not reached).
    """
    lines = []
    for system, roms in sorted(systems_candidates.items()):
        if not roms:
            continue
        got = matches.get(system, {})
        counts = Counter(got[r] for r in roms if got.get(r))
        unmatched = [r for r in roms if r in got and got[r] is None]
        parts = [f"{counts['hash']} by hash", f"{counts['name+size']} by name+size", f"{counts['manual']} manual"]
        if unmatched:
            parts.append(f"{len(unmatched)} unmatched")
        rest = sum(1 for r in roms if r not in got)
        if rest:
            parts.append(f"{rest} not scraped")
        lines.append(f"  {system}: {len(roms)} to scrape — " + ", ".join(parts))
        lines += [f"     unmatched: {r}" for r in unmatched[:SHOWN]]
        if len(unmatched) > SHOWN:
            lines.append(f"     … and {len(unmatched) - SHOWN} more")
    return "\n".join(lines)


def _media_ext(path, mtype):
    """The file extension for a downloaded media file, or None when it isn't one (an error page, "NOMEDIA", empty):
    manuals must be PDFs, videos MP4-family files (an ftyp box), everything else a PNG, JPEG or GIF."""
    with open(path, "rb") as f:
        head = f.read(12)
    if mtype == "manuals":
        return ".pdf" if head.startswith(b"%PDF") else None
    if mtype == "videos":
        return ".mp4" if head[4:8] == b"ftyp" else None
    return next((ext for magic, ext in IMAGE_MAGIC if head.startswith(magic)), None)


def scrape_rom(client, system, item, tmp, skip, stop, game_id=None):
    """("done", (how, metadata, {media type: local file})), ("notgame", (how, what ScreenScraper says about it)),
    ("unknown", (how, "missing")), ("failed", reason), ("unreachable", the Transient error left after the retries),
    ("stop", the QuotaExceeded or Refused that stops the run) or ("skipped", None) when the run stopped (quota, refused,
    unreachable or Ctrl-C) before this ROM finished. Every outcome but "skipped" counts toward the ROMs in a row that
    couldn't reach ScreenScraper; UNREACHABLE_STOP of them set the stop event. game_id: see match()."""
    status, payload = _scrape_rom(client, system, item, tmp, skip, stop, game_id)
    if status != "skipped" and _unreachable.add(payload if status == "unreachable" else None):
        stop.set()
    return status, payload


def _scrape_rom(client, system, item, tmp, skip, stop, game_id):
    rom, size, etag = item
    if stop.is_set():
        return "skipped", None
    rc = _RomClient(client, stop)
    how = None
    try:
        game_id, how = match(rc, system, rom, size, etag, game_id, stop)
        raw = rc.found if rc.found is not None else rc.game(game_id)
        if screenscraper.is_notgame(raw):
            return "notgame", (how, screenscraper.notgame_info(raw))
        meta, media = screenscraper.parse_game(raw, ())
        if not meta:
            raise screenscraper.ApiError("ScreenScraper returned no data for it")
        scrape_state.mark_nomedia(system["bucket"], rom, set(screenscraper.MEDIA_MAP.values()) - set(media))
        stem = os.path.splitext(rom)[0]
        rom_tmp = tempfile.mkdtemp(dir=tmp)  # ROMs with the same stem (Game.zip, Game.7z) never share a file
        files = {}
        for mtype, url in sorted(media.items()):
            if mtype in skip:
                continue
            if stop.is_set():
                return "skipped", None
            dest = s3.safe_join(rom_tmp, f"{mtype}/{stem}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                rc.download(url, dest, stop=stop, **({"limit": screenscraper.VIDEO_MAX} if mtype == "videos" else {}))
            except screenscraper.NotFound:  # ScreenScraper has no such file: not a failure
                continue
            except screenscraper.MediaRefused as e:  # too large or off screenscraper.fr: skip just this file
                print(ui.yellow(f"  ⚠️  {system['bucket']}/{rom}: {mtype} skipped ({e})"))
                continue
            ext = _media_ext(dest, mtype)
            if ext:
                files[mtype] = dest + ext
                os.replace(dest, files[mtype])
    except (screenscraper.QuotaExceeded, screenscraper.Refused) as e:
        stop.set()
        return "stop", e
    except screenscraper.NotFound:
        return "unknown", (how, "missing")
    except screenscraper.Stopped:
        return "skipped", None
    except screenscraper.Transient as e:
        return "unreachable", e
    except ROM_ERRORS as e:
        return "failed", _reason(e)
    except BaseException:  # stop the other workers at once, not when the run's thread notices
        stop.set()
        raise
    return "done", (how, meta, files)


def _reason(e):
    """Printable text for a ROM's failure: our own ApiError messages (which never hold a URL), else only the error's type,
    since other errors' text can quote a media URL and the credentials in its query."""
    return str(e) if type(e) in (screenscraper.ApiError, screenscraper.RateLimited, screenscraper.Transient) and str(e) else type(e).__name__


def _uploaded(jobs, have):
    """Whether every upload job is in storage: same size for files, present for shrunk images."""
    return all(j[0] in have and (len(j) > 3 or have[j[0]] == j[2]) for j in jobs)


RERUN = "sync-roms scrape"


def _storage_fail(what, e, rerun):
    ui.fail(f"{what} failed ({type(e).__name__}). ROMs recorded in earlier batches are complete; "
            f"run `{rerun}` again to continue.", 3)


def _stop_message(e, rerun, counts=(0, 0)):
    """What the user is told when e stopped the run: why, and how to continue. counts: (ROMs scraped this run, ROMs left),
    said on Ctrl-C."""
    if isinstance(e, KeyboardInterrupt):
        return (f"🛑 Interrupted. {counts[0]} ROM(s) scraped this run are saved and {counts[1]} are left; run `{rerun}` again "
                "to continue where it stopped.")
    if isinstance(e, screenscraper.Refused):
        return f"⛔ {e}. Everything scraped so far is saved; run `{rerun}` again to continue where it stopped."
    if isinstance(e, screenscraper.Transient):
        return (f"🔌 ScreenScraper couldn't be reached for {UNREACHABLE_STOP} ROMs in a row; the last error: {e}. Everything "
                f"scraped so far is saved; run `{rerun}` again later to continue where it stopped.")
    if isinstance(e, screenscraper.TooManyUnrecognized):
        why = "ScreenScraper takes no more unrecognized ROMs from you today (HTTP 431)"
    else:
        why = "ScreenScraper's daily quota is used up"
    return f"⏳ {why}. Everything scraped so far is saved; run `{rerun}` again tomorrow to continue where it stopped."


def _batches(items):
    """items in batches of at most BATCH with no two ROMs of the same stem (they share media files) in one batch."""
    batches, open_ = [], []  # open_: [(batch, its stems)] that aren't full yet
    for item in items:
        stem = os.path.splitext(item[0])[0]
        for batch, stems in open_:
            if stem not in stems:
                break
        else:
            batch, stems = [], set()
            batches.append(batch)
            open_.append((batch, stems))
        batch.append(item)
        stems.add(stem)
        if len(batch) == BATCH:
            open_ = [o for o in open_ if o[0] is not batch]
    return batches


def _media_keys(listing, system, stem):
    """{key: media type} of every media file (Onion and Slot images included) a ROM stem has in a scrapes/<system>/
    listing."""
    out = {}
    for key in listing:
        parts = key.split("/", 3)
        if len(parts) == 4 and parts[1] == system and parts[2] in scrape_plan.BUCKET_MEDIA \
                and os.path.splitext(parts[3])[0] == stem:
            out[key] = parts[2]
    return out


Started = namedtuple("Started", "futures kept tmp stop")  # a batch handed to the pool: its futures, the media types storage already has per ROM, its temp folder, the run's stop event


def start_batch(ex, client, system, batch, skip, stop, index, replace=False, forced=None, hasher=None):
    """Hand a batch's ROMs to the pool and return at once; run_batch takes what they scraped. Media types a ROM already
    has in index (scrape_plan.scrape_index of scrapes/<system>/) are not downloaded, unless replace. forced: {ROM: game id} matches
    given for this run only. hasher: a pool that hashes the batch's ROMs meanwhile (ROMs read from a folder)."""
    forced = forced or {}
    if hasher is not None and s3.read_root():
        for rom, size, _ in batch:
            if size <= HASH_MAX and rom not in forced and scrape_state.manual_match(system["bucket"], rom) is None:
                prefetch_hash(hasher, system["bucket"], rom, size, stop)
    kept = {rom: set() if replace else set(index.get(os.path.splitext(rom)[0], ())) for rom, _, _ in batch}
    tmp = tempfile.mkdtemp()
    futures = [ex.submit(scrape_rom, client, system, item, tmp, skip | kept[item[0]], stop, forced.get(item[0]))
               for item in batch]
    return Started(futures, kept, tmp, stop)


def _say_rom(pos, name, rom, status, payload, forced_id):
    """Print the line of a ROM whose work ended: the game it matched, how, and its media count; nothing for a ROM
    skipped or stopping the run (the closing message covers them)."""
    head = f"  {ui.dim(pos)} "
    if status in ("unknown", "notgame") and forced_id is not None:
        ui.failure(ui.red(f"{head}❌ {name}/{rom}: " + (f"ScreenScraper game {forced_id} is not a playable game entry"
                                                       if status == "notgame" else f"ScreenScraper has no game {forced_id}")))
    elif status == "notgame":
        found = f" → {payload[1]['name']}" if payload[1]["name"] else ""
        print(ui.dim(f"{head}🚫 {name}/{rom}{found}: ScreenScraper lists it as a non-game"))
    elif status == "unknown":
        print(ui.dim(f"{head}❔ {name}/{rom}: not on ScreenScraper"))
    elif status in ("failed", "unreachable"):
        ui.failure(ui.yellow(f"{head}⚠️  {name}/{rom}: {payload if status == 'failed' else _reason(payload)}; skipped"))
    elif status == "done":
        how, meta, files = payload
        found = f" → {meta['name']}" if meta.get("name") else ""
        print(f"{head}✅ {name}/{rom}{found}" + ui.dim(f"  {how}, {len(files)} media"))


def run_batch(system, batch, started, shrink, outcomes, listing, index, pending, replace=False, forced=None, rerun=RERUN,
              position=(0, None), interrupted=False):
    """Wait for a started batch's ROMs, printing a line for each as it ends, upload their media and queue their entries in
    pending ({ROM: (how, metadata, upload jobs)}, written to metadata.json by record). Returns (failures, the error that
    stops the run or None): a KeyboardInterrupt on Ctrl-C, a ROM's QuotaExceeded or Refused, or the Transient error of the
    last of UNREACHABLE_STOP ROMs in a row that couldn't reach ScreenScraper.

    listing: {key: size} of scrapes/<system>/, and index: its scrape_index, both kept up to date with what this batch
    uploads. replace: the ROMs'
    metadata entries are replaced (not merged) and their old scraper media (never custom/ or skipped types) is
    overwritten. forced: see start_batch; rerun: the command that continues the run. position: (the system's ROMs
    before this batch, its ROM count), for each ROM's line.

    Ctrl-C stops the run: the ROMs still working stop at their next check, and those that finished are uploaded and
    queued; during the upload it keeps the ROMs whose media all made it. interrupted: an earlier Ctrl-C is being
    handled, so this one aborts (raised).
    """
    name = system["bucket"]
    forced = forced or {}
    failed, cut = 0, False  # cut: Ctrl-C ended the upload early, so what it didn't copy is left, not failed
    kept = started.kept
    results = [("skipped", None)] * len(batch)
    order = {f: i for i, f in enumerate(started.futures)}
    left, shown = set(started.futures), position[0]

    def take():  # results in batch order, each ROM's line printed as it ends
        nonlocal shown
        while left:
            for f in sorted(wait(left, return_when=FIRST_COMPLETED)[0], key=order.get):
                left.discard(f)
                i = order[f]
                results[i] = status, payload = f.result()
                if status not in ("skipped", "stop"):
                    shown += 1
                    _say_rom(f"[{shown}/{position[1] or len(batch)}]", name, batch[i][0], status, payload, forced.get(batch[i][0]))
    try:
        try:
            take()
        except KeyboardInterrupt:
            if interrupted:
                raise
            interrupted = True
            started.stop.set()
            print(ui.yellow("  🛑 Interrupted — finishing the ROMs in progress and saving what is done. ^C again to abort now."))
            take()
        halt = KeyboardInterrupt() if interrupted else next((p for s, p in results if s == "stop"), _unreachable.error)
        jobs = {}  # ROM -> its upload jobs
        done = {}
        for (rom, _, _), (status, payload) in zip(batch, results):
            if status in ("unknown", "notgame") and rom in forced:
                failed += 1
                outcomes[rom] = None
            elif status == "notgame":
                scrape_state.mark_notgame(name, rom, payload[1])
                outcomes[rom] = None
            elif status == "unknown":
                if payload[0] == "manual":  # the saved match's game is gone: don't retry it on every run
                    print(ui.yellow(f"  ⚠️  {name}/{rom}: ScreenScraper has no game {scrape_state.manual_match(name, rom)}; "
                                    "forgot that saved match"))
                    scrape_state.forget_match(name, rom)
                scrape_state.mark_unknown(name, rom)
                outcomes[rom] = None
            elif status in ("failed", "unreachable"):
                failed += 1
            elif status == "done":
                how, meta, files = payload
                stem = os.path.splitext(rom)[0]
                rom_jobs = [(f"{scrape_plan.SCRAPES}/{name}/{mtype}/{stem}{os.path.splitext(path)[1]}", path, os.path.getsize(path))
                            for mtype, path in sorted(files.items())]
                if shrink:  # a type already in storage counts as found, so art is never made from a lesser image
                    found = {**{t: None for t in kept[rom]}, **files}
                    rom_jobs += [(key, src, os.path.getsize(src), box)
                                 for key, src, box in scrape_files.derived_art(name, stem, found)
                                 if src and (replace or key not in listing)]
                jobs[rom], done[rom] = rom_jobs, (how, meta)
        todo = [j for js in jobs.values() for j in js]
        try:
            try:
                upload_failed = upload.run_uploads(todo, quiet=True) if todo else 0
            except KeyboardInterrupt:  # run_uploads let the files in flight finish
                if interrupted:
                    raise
                started.stop.set()
                halt, cut, upload_failed = KeyboardInterrupt(), True, 1
            have = inventory.files(f"{scrape_plan.SCRAPES}/{name}/") if upload_failed else {}
        except s3.ERRORS as e:
            _storage_fail(f"Uploading {name} media", e, rerun)
        if upload_failed:
            for rom in [r for r in done if not _uploaded(jobs[r], have)]:
                del done[rom]
                if not cut:
                    failed += 1
                    ui.failure(ui.yellow(f"  ⚠️  {name}/{rom}: its media didn't all upload; skipped"))
    finally:
        shutil.rmtree(started.tmp, ignore_errors=True)
    for rom, (how, meta) in done.items():
        for j in jobs[rom]:
            listing[j[0]] = j[2]
            scrape_plan.index_add(index, j[0], j[2])
        pending[rom] = (how, meta, jobs[rom])
    return failed, halt


def _bad_entries(name, data):
    """Why a loaded metadata.json can't be used (an entry that isn't an object), or None."""
    if all(isinstance(v, dict) for v in data.values()):
        return None
    return f"{metadata_key(name)} has an entry that isn't an object"


def _read_metadata(name, rerun):
    """(a system's metadata.json from storage, None), or (None, why it can't be used)."""
    try:
        remote = load_metadata(name)
    except ValueError as e:
        return None, e
    except s3.ERRORS as e:
        _storage_fail(f"Reading {metadata_key(name)}", e, rerun)
    why = _bad_entries(name, remote)
    return (None, why) if why else (remote, None)


def record(system, pending, outcomes, listing, index, skip, replace=False, rerun=RERUN, fill=False):
    """Write pending's entries (see run_batch) to the system's metadata.json, one read and one write for all of them,
    and empty pending. With replace the entries replace the old ones and the old scraper media they leave behind is
    deleted. fill: ROMs that already have an entry keep its fields; ScreenScraper's only add the missing ones.
    Returns (failures, whether the system's remaining ROMs must be skipped)."""
    name = system["bucket"]
    scrape_state.flush_unknown()
    if not pending:
        return 0, False
    done = dict(pending)
    pending.clear()
    remote, why = _read_metadata(name, rerun)
    if why:
        print(ui.yellow(f"  ⚠️  {why}; {len(done)} ROM(s) not recorded, skipping the rest of {name}"))
        return len(done), True
    for rom, (_, meta, _) in done.items():  # remote is ours: changed in place
        old = remote.get(rom, {})
        remote[rom] = dict(meta) if replace else {**old, **({**meta, **old} if fill else meta)}
    try:
        s3.put_text(metadata_key(name), scrape_plan.dump_json(remote))
    except s3.ERRORS as e:
        _storage_fail(f"Writing {metadata_key(name)}", e, rerun)
    for rom, (how, _, jobs) in done.items():
        if replace:  # the new entry is written: the old game's other scraper media goes (a failed delete only orphans it)
            uploaded = {j[0] for j in jobs}
            stale = [k for k, t in _media_keys(listing, name, os.path.splitext(rom)[0]).items()
                     if t in SCRAPER_TYPES - skip and k not in uploaded]
            try:
                errors = s3.delete_keys(stale) if stale else []
            except s3.ERRORS as e:
                _storage_fail(f"Deleting old {name} media", e, rerun)
            for k in stale:
                listing.pop(k, None)
                scrape_plan.index_drop(index, k)
            for e in errors:
                print(ui.yellow(f"  ⚠️  {e.get('Key')}: couldn't delete the old file"))
        outcomes[rom] = how
        scrape_state.clear_unknown(name, rom)  # found after all, if it was a retry or a manual match
    scrape_state.flush_unknown()
    print(ui.green(f"  ✅ {name}: {len(done)} ROM(s) scraped"))
    return 0, False


def _progress(client, done, total, elapsed):
    """A batch header's tail: the time elapsed and left (once some ROMs are done) and today's requests, when the client
    has seen them."""
    parts = [f"{ui.eta(elapsed)} elapsed, {ui.eta(elapsed / done * (total - done))} left"] if done else []
    quota = client.last_quota
    if quota is not None and quota.max_today:
        parts.append(f"{quota.used_today}/{quota.max_today} requests used today")
    return "  " + " · ".join(parts) if parts else ""


def _stems(batch):
    return {os.path.splitext(rom)[0] for rom, _, _ in batch}


def scrape_system(client, system, items, threads, skip, shrink, outcomes, listing, index, replace=False, forced=None,
                  rerun=RERUN, fill=False, metadata=None):
    """Scrape one system's ROMs on one pool of threads, in batches: the next batch is scraped while the last one uploads,
    so no thread waits for a batch's slowest ROM. Entries are written to metadata.json every METADATA_INTERVAL seconds, when
    the system is done and when the run stops. Returns (failures, the error that stopped the run or None: a KeyboardInterrupt
    on Ctrl-C, once what finished is saved; a second Ctrl-C is raised). Arguments: see run_batch;
    index: scrape_plan.scrape_index(listing); metadata: the system's metadata.json if the caller already loaded it."""
    name = system["bucket"]
    # a metadata.json that can't be used fails before any quota is spent
    why = _read_metadata(name, rerun)[1] if metadata is None else _bad_entries(name, metadata)
    if why:
        print(ui.yellow(f"  ⚠️  {why}; skipping {name}"))
        return len(items), None
    batches, flight = deque(_batches(items)), deque()
    pending, stop, failed, halted, started = {}, threading.Event(), 0, None, 0
    last_write = since = time.monotonic()
    ex, hasher = ThreadPoolExecutor(threads), ThreadPoolExecutor(HASH_THREADS)
    try:
        while batches or flight:
            while (batches and len(flight) < LOOKAHEAD and not stop.is_set()  # same-stem ROMs share media: wait for the earlier batch to upload
                   and not any(_stems(batches[0]) & _stems(b) for b, _ in flight)):
                batch = batches.popleft()
                flight.append((batch, start_batch(ex, client, system, batch, skip, stop, index, replace, forced, hasher)))
            if not flight:
                break
            batch, begun = flight.popleft()
            print(ui.bold(f"\n🔎 {name}: ROMs {started + 1}-{started + len(batch)} of {len(items)}")
                  + ui.dim(_progress(client, started, len(items), time.monotonic() - since)))
            n, hit = run_batch(system, batch, begun, shrink, outcomes, listing, index, pending, replace=replace, forced=forced,
                               rerun=rerun, position=(started, len(items)), interrupted=isinstance(halted, KeyboardInterrupt))
            started += len(batch)
            failed += n
            halted = halted or hit
            if time.monotonic() - last_write >= METADATA_INTERVAL:
                scrape_state.flush_unknown()  # marks from a run that finds nothing must not wait for the final flush
                scrape_state.flush_hashes()
                scrape_state.flush_nomedia()
                last_write = time.monotonic()
                if pending:
                    n, halt = record(system, pending, outcomes, listing, index, skip, replace, rerun, fill)
                    failed += n
                    if halt:
                        return failed, halted
        n, _ = record(system, pending, outcomes, listing, index, skip, replace, rerun, fill)
        return failed + n, halted
    except BaseException:  # Ctrl-C, a storage failure: queued ROMs never start, running ones stop at their next stop check
        stop.set()
        ex.shutdown(wait=True, cancel_futures=True)
        hasher.shutdown(wait=True, cancel_futures=True)
        with contextlib.suppress(SystemExit):  # what was uploaded still gets its entries
            record(system, pending, outcomes, listing, index, skip, replace, rerun, fill)
        raise
    finally:
        stop.set()
        ex.shutdown(wait=True, cancel_futures=True)
        hasher.shutdown(wait=True, cancel_futures=True)
        scrape_state.flush_hashes()
        scrape_state.flush_unknown()
        scrape_state.flush_nomedia()
        for _, begun in flight:
            shutil.rmtree(begun.tmp, ignore_errors=True)


def run_scrape(client, systems, todo, skip, ask=True, replace=False, forced=None, rerun=RERUN, outcomes=None, fill=False,
               listings=None, metadata=None):
    """Confirm (unless not ask), then scrape todo ({system: [(ROM, size, etag)]}) in batches. Returns the exit code.
    replace, forced, rerun, fill: see run_batch and record. outcomes: filled with {system: {ROM: how, or None when unknown}}.
    listings: {system: {key: size} of scrapes/<system>/} and metadata: {system: its metadata.json} the caller already has."""
    count = sum(len(v) for v in todo.values())
    listings, metadata = dict(listings or {}), metadata or {}
    before = set(scrape_state.notgames())
    _unreachable.reset()
    try:
        listings.update(_each(lambda name: inventory.files(f"{scrape_plan.SCRAPES}/{name}/"), [n for n in todo if n not in listings]))
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    indexes = {name: scrape_plan.scrape_index(listings[name]) for name in todo}
    kept = 0 if replace else sum(len(indexes[name].get(os.path.splitext(r)[0], ()))
                                 for name, items in todo.items() for r, _, _ in items)
    note = f"; the {kept} media file(s) already there are kept" if kept else ""
    try:
        quota = _retry(None, client.quota)
    except screenscraper.QuotaExceeded as e:
        ui.failure(ui.yellow(_stop_message(e, rerun)))
        return 1
    except screenscraper.ApiError as e:
        ui.fail(f"{e}", 3)
    if quota is None:
        print(ui.yellow(f"  ⚠️  {NO_ACCOUNT}; scraping on one thread"))
        quota = screenscraper.Quota(1, 0, 0)
    elif quota.max_today:
        print(ui.dim(f"ScreenScraper: {_quota_line(quota)}"))
        need, left = count * (1 + len(set(screenscraper.MEDIA_MAP.values()) - skip)), max(0, quota.max_today - quota.used_today)
        print(ui.dim(f"  up to {need} request(s) for {count} ROM(s), {left} left today"))
        if need > left:
            print(ui.yellow(f"  ⚠️  This may use up today's quota: the run then stops, keeping what it finished, and `{rerun}` "
                            "continues tomorrow"))
    if ask and not ui.confirm(f"🖼️  Scrape {count} ROM(s) from ScreenScraper and write their media and metadata to "
                              f"{s3.location()}/{scrape_plan.SCRAPES}/{note} ?", default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    shrink = scrape_plan.can_shrink()
    if not shrink:
        print(ui.yellow(f"  ⚠️  {scrape_plan.NO_SHRINK}; not making them"))
    outcomes = {} if outcomes is None else outcomes
    failed, halted = 0, None
    for name, items in sorted(todo.items()):
        outcomes[name] = {}
        n, halted = scrape_system(client, systems[name], items, max(1, quota.max_threads), skip, shrink, outcomes[name],
                                  listings[name], indexes[name], replace, forced, rerun, fill, metadata.get(name))
        failed += n
        if halted:
            break
    print(ui.bold("\n📋 Results"))
    print(report({name: [r for r, _, _ in items] for name, items in todo.items()}, outcomes))
    interrupted = isinstance(halted, KeyboardInterrupt)
    if not interrupted:  # nothing is asked after Ctrl-C
        _offer_review(client, systems, todo, sorted(set(scrape_state.notgames()) - before))
    if halted:
        counts = (sum(1 for got in outcomes.values() for how in got.values() if how), count - sum(map(len, outcomes.values())))
        ui.failure(ui.yellow("\n" + _stop_message(halted, rerun, counts)))
        return 130 if interrupted else 1
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s); run `{rerun}` to try again"))
    return 1 if failed else 0


def _offer_review(client, systems, todo, new):
    """After a run that turned up non-games: review them now (on a terminal, if the user wants), else say how to later."""
    if not new:
        return
    print(ui.yellow(f"\n🚫 {len(new)} ROM(s) came back as non-games"))
    if sys.stdin.isatty() and ui.confirm("Review them now?", default=True):
        from . import scrape_review
        sizes = {f"{name}/{r}": size for name, items in todo.items() for r, size, _ in items}
        scrape_review.review(systems, new, sizes, client)
    else:
        print(ui.dim("   Review them later with: sync-roms scrape review"))


def _check_skip(skip):
    skip = set(skip or ())
    types = set(screenscraper.MEDIA_MAP.values())
    bad = skip - types
    if bad:
        ui.fail(f"Unknown media type(s): {', '.join(sorted(bad))}; choose from {', '.join(sorted(types))}", 2)
    return skip


def _pick_systems(name):
    systems = store.load_manifest(store.all_card_names())["systems"]
    if name:
        systems = [s for s in systems if s["bucket"] == name]
        if not systems:
            ui.fail(f"No system {name!r}; give its storage folder name (e.g. gba)", 2)
    return systems


def scrape_command(args):
    try:
        return _scrape_command(args)
    finally:
        _mtimes.clear()


def _scrape_command(args):
    """Scrape the available ROMs that have no metadata yet from ScreenScraper into scrapes/<system>/.

    args: system (storage folder name, or None for all), retry (also try ROMs marked unknown), skip_media (media type
    folder names not to download), dry_run, and optionally all (every ROM in the storage, not just the listed games) and
    fill_media (also the ROMs with metadata that lack some media type in storage; their metadata is kept).
    """
    skip = _check_skip(args.skip_media)
    print(ui.bold("🖼️  Scrape from ScreenScraper") + ui.dim(f"  {s3.access(True)}"))
    systems = _pick_systems(args.system)
    try:
        print("📏 Listing the ROMs available in storage...")
        roms = scrape_files.bucket_roms(systems, all_files=getattr(args, "all", False))
        listed = [s for s in systems if roms.get(s["bucket"])]
        def loaded(name):
            try:
                return load_metadata(name)
            except ValueError:
                return None
        metadata = {}
        for name, data in _each(loaded, [s["bucket"] for s in listed]).items():
            if data is None:
                print(ui.yellow(f"  ⚠️  {metadata_key(name)} isn't valid JSON; skipping {name}"))
                roms[name] = set()
            else:
                metadata[name] = data
        fill = None
        if getattr(args, "fill_media", False):
            have = _each(lambda name: inventory.files(f"{scrape_plan.SCRAPES}/{name}/", sizes=False), [s["bucket"] for s in listed])
            fill = (set(screenscraper.MEDIA_MAP.values()) - skip, have)
        candidates = find_candidates(listed, roms, metadata, retry=args.retry, fill=fill)
        for s in listed:
            if candidates.get(s["bucket"]) and "screenscraper" not in s:
                print(ui.yellow(f"  ⚠️  {s['bucket']} has no ScreenScraper system id; skipping its {len(candidates[s['bucket']])} ROM(s)"))
                del candidates[s["bucket"]]
        candidates = {k: v for k, v in candidates.items() if v}
        etags = _candidate_etags(candidates)
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    todo = {name: [(r, *etags[name][r]) for r in roms_ if r in etags[name]] for name, roms_ in candidates.items()}
    planned = {name: {r: planned_match(name, r, size, etag) for r, size, etag in items} for name, items in todo.items()}
    if not any(todo.values()):
        print(ui.green("Nothing to scrape ✨") + ("" if getattr(args, "all", False) else ui.dim("  (--all also takes the ROMs no card lists)")))
        return 0
    print(ui.bold("\n🔎 ROMs to scrape (and how each will be looked up first)"))
    print(report({name: [r for r, _, _ in items] for name, items in todo.items()}, planned))
    if s3.read_root():
        read = sum(size for name, items in todo.items() for r, size, _ in items
                   if planned[name][r] == "hash" and not _cached(name, r, size))
        print(f"  📖 {ui.human_size(read)} to read for hashing" + ui.dim(f"  (files over {ui.human_size(HASH_MAX)} only when name+size finds nothing)"))
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing looked up or written"))
        wanted = sorted(set(screenscraper.MEDIA_MAP.values()) - skip)
        for name, items in sorted(todo.items()):
            print(f"  {metadata_key(name)} {ui.dim(f'+{len(items)} entr' + ('y' if len(items) == 1 else 'ies'))}")
            print(f"  {scrape_plan.SCRAPES}/{name}/<{'|'.join(wanted)}>/ {ui.dim('what ScreenScraper has for:')}")
            for r, _, _ in items[:SHOWN]:
                print(ui.dim(f"     {r}"))
            if len(items) > SHOWN:
                print(ui.dim(f"     … and {len(items) - SHOWN} more"))
        return 0
    client = make_client()
    return run_scrape(client, {s["bucket"]: s for s in systems}, todo, skip, fill=fill is not None,
                      listings=fill[1] if fill else None, metadata=metadata)


def match_command(args):
    """`scrape match SYSTEM ROM GAME`: save which ScreenScraper game a ROM is (GAME is a game id, or a name to search
    and pick from), then scrape that ROM.

    args: system (storage folder name), rom (ROM path in it, e.g. "Game (USA).zip"), game, and optionally skip_media
    and dry_run (resolve the game, save and write nothing).
    """
    skip = _check_skip(getattr(args, "skip_media", None))
    system = _pick_systems(args.system)[0]
    name = system["bucket"]
    if "screenscraper" not in system:
        ui.fail(f"{name} has no ScreenScraper system id, so it can't be scraped", 2)
    try:
        listing = inventory.etags(name + "/")
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    if args.rom not in listing:
        ui.fail(f"No {name}/{args.rom} in {s3.location()}", 2)
    client = make_client()
    rerun = "sync-roms scrape match " + shlex.join([name, args.rom, args.game])
    try:
        game_id = resolve_manual(_RomClient(client), system, args.game)
    except screenscraper.NotFound as e:
        if str(e) == "cancelled":
            print(ui.yellow("👋 Cancelled."))
            return 0
        ui.fail(f"ScreenScraper has no game for {args.game!r}", 1)
    except screenscraper.QuotaExceeded as e:
        print(ui.yellow(_stop_message(e, rerun)))
        return 1
    except screenscraper.ApiError as e:
        ui.fail(f"{e}", 3)
    rerun = "sync-roms scrape match " + shlex.join([name, args.rom, str(game_id)])
    if getattr(args, "dry_run", False):
        print(ui.yellow(f"🧪 Dry run — would match {name}/{args.rom} to ScreenScraper game {game_id} and scrape it"))
        return 0
    stem = os.path.splitext(args.rom)[0]
    try:
        data = load_metadata(name)
        replace = args.rom in data
        media = inventory.files(f"{scrape_plan.SCRAPES}/{name}/")
    except ValueError:
        ui.fail(f"{metadata_key(name)} isn't valid JSON", 3)
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    where = f"{s3.location()}/{scrape_plan.SCRAPES}/"
    shared = sorted(r for r in listing if r != args.rom and os.path.splitext(r)[0] == stem)
    if shared:
        print(ui.yellow(f"⚠️  {name}/{args.rom} shares its media files with {', '.join(shared)}"))
    if replace:
        old = sorted(k for k, t in _media_keys(media, name, stem).items() if t in SCRAPER_TYPES - skip)
        for k in old[:SHOWN]:
            print(ui.dim(f"     {k}"))
        if len(old) > SHOWN:
            print(ui.dim(f"     … and {len(old) - SHOWN} more"))
        left = "custom/" + (f" and the skipped types ({', '.join(sorted(skip))})" if skip else "")
        question = (f"🔁 Replace the metadata entry and media of {name}/{args.rom} in {where} with ScreenScraper game "
                    f"{game_id}? {len(old)} file(s) listed above are overwritten or deleted; {left} left as they are.")
    else:
        kept = len(scrape_plan.scrape_index(media).get(stem, ()))
        note = f"; the {kept} media file(s) already there are kept" if kept else ""
        question = (f"🖼️  Scrape {name}/{args.rom} as ScreenScraper game {game_id} and write its media and metadata to "
                    f"{where}{note} ?")
    if not getattr(args, "confirmed", False) and not ui.confirm(question, default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    print(f"🔗 {name}/{args.rom} → ScreenScraper game {game_id}")
    size, etag = listing[args.rom]
    outcomes = {}
    code = run_scrape(client, {name: system}, {name: [(args.rom, size, etag)]}, skip, ask=False, replace=replace,
                      forced={args.rom: game_id}, rerun=rerun, outcomes=outcomes, listings={name: media}, metadata={name: data})
    how = outcomes.get(name, {}).get(args.rom, "")
    if how == "manual":  # saved only once the ROM is scraped as that game
        scrape_state.save_match(name, args.rom, game_id)
        scrape_state.clear_notgame(name, args.rom)
        return code
    return code or 1


MISSING = {  # why a ROM has no metadata: (mark, how the system's line counts it)
    "notgame": ("🚫", "non-game"), "unknown": ("❔", "not on ScreenScraper"),
    "manual": ("🔗", "matched, not scraped yet"), "new": ("⏳", "not looked up yet"),
}


def missing_command(args):
    """`scrape missing [SYSTEM]`: list every ROM with no metadata entry and why: ScreenScraper calls it a non-game or
    doesn't know it, it has a saved match that wasn't scraped, or it hasn't been looked up. Nothing is looked up or written.

    args: system (storage folder name, or None for all) and optionally all (every ROM in the storage, not just the
    listed games)."""
    systems = _pick_systems(args.system)
    print(ui.bold("🔎 ROMs with no metadata") + ui.dim(f"  {s3.location()}"))
    try:
        roms = scrape_files.bucket_roms(systems, all_files=getattr(args, "all", False))
        listed = [s for s in systems if roms.get(s["bucket"])]

        def loaded(name):
            try:
                return load_metadata(name)
            except ValueError:
                return None
        metadata = _each(loaded, [s["bucket"] for s in listed])
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    state, total = scrape_state.snapshot(), 0
    for s in sorted(listed, key=lambda s: s["bucket"]):
        name = s["bucket"]
        if metadata[name] is None:
            print(ui.yellow(f"  ⚠️  {metadata_key(name)} isn't valid JSON; skipping {name}"))
            continue
        why = {}
        for r in sorted(roms[name] - set(metadata[name])):
            why[r] = ("notgame" if state.is_notgame(name, r) else "manual" if state.manual_match(name, r) is not None
                      else "unknown" if state.is_unknown(name, r) else "new")
        if not why:
            continue
        total += len(why)
        counts = Counter(why.values())
        parts = [f"{counts[k]} {MISSING[k][1]}" for k in MISSING if counts[k]]
        if "screenscraper" not in s:
            parts = ["no ScreenScraper system id, so it can't be scraped"]
        print(f"  {name} ({len(why)}): " + ", ".join(parts))
        for r, k in why.items():
            print(f"     {MISSING[k][0]} {r}")
    if not total:
        print(ui.green("Every ROM has metadata ✨"))
        return 0
    print(ui.dim("\n   Review the non-games and unknown ROMs: sync-roms scrape review [SYSTEM]"))
    print(ui.dim("   Say which game one is: sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME"))
    print(ui.dim("   Look up the rest: sync-roms scrape"))
    return 0
