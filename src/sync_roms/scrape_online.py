"""Online scraping: which ROMs need metadata, which ScreenScraper game each one is, and the scrape run."""
import getpass
import hashlib
import http.client
import json
import os
import tempfile
import threading
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from . import s3, scrape_files, scrape_plan, scrape_state, screenscraper, store, ui, upload, usersettings

CHUNK = 8 << 20


def find_candidates(systems, roms, metadata, retry=False):
    """{system folder: sorted ROM paths} with no entry in that system's metadata.json (and, unless retry, not marked
    unknown; a saved manual match overrides the unknown mark)."""
    out = {}
    for s in systems:
        system = s["bucket"]
        have = metadata.get(system, {})
        out[system] = sorted(r for r in roms.get(system, ())
                             if r not in have and (retry or scrape_state.manual_match(system, r) is not None
                                                      or not scrape_state.is_unknown(system, r)))
    return out


def hash_file(system, rom, size, mtime):
    """{"md5","sha1","crc"} of a ROM read from the storage folder or mirror, cached by size and mtime."""
    cached = scrape_state.cached_hashes(system, rom, size, mtime)
    if cached:
        return cached
    md5, sha1, crc = hashlib.md5(), hashlib.sha1(), 0
    key = f"{system}/{rom}"
    for start in range(0, size, CHUNK):
        chunk = s3.read_range(key, start, min(start + CHUNK, size))
        md5.update(chunk)
        sha1.update(chunk)
        crc = zlib.crc32(chunk, crc)
    hashes = {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "crc": f"{crc:08X}"}
    scrape_state.save_hashes(system, rom, size, mtime, hashes)
    return hashes


def match(client, system, rom, size, etag):
    """(game id, how) for a ROM; how is "manual", "hash" or "name+size". Raises screenscraper.NotFound.

    One lookup sends the hashes, name and size together; it counts as "hash" only when the ROM ScreenScraper
    matched carries one of the hashes sent."""
    name = system["bucket"]
    saved = scrape_state.manual_match(name, rom)
    if saved is not None:
        return saved, "manual"
    hashes = {}
    if s3.read_root():  # a folder's ETag is a fake "mtime-size" tag; hash the file instead
        mtime = int(os.path.getmtime(s3.safe_join(s3.read_root(), f"{name}/{rom}")))
        hashes = hash_file(name, rom, size, mtime)
    elif "-" not in (tag := etag.strip('"')):  # a multipart upload's ETag is not the file's MD5
        hashes = {"md5": tag}
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
BATCH = 25  # ROMs scraped, uploaded and written to metadata.json together
RETRIES = 3  # times a rate-limited request is tried again
RETRY_WAIT = 2  # seconds before the first retry, doubled each time
CREDENTIALS = ("screenscraper_user", "screenscraper_password", "screenscraper_devid", "screenscraper_devpassword")
# What one ROM's lookup and downloads can raise besides NotFound and QuotaExceeded: the client's own errors and
# those it doesn't wrap (a read cut short, a timeout, a malformed media URL, an unsafe ROM path).
ROM_ERRORS = (screenscraper.ApiError, OSError, ValueError, http.client.HTTPException)
IMAGE_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"))
SHOWN = 10


class _RomClient:
    """One ROM's view of the client: rate-limited requests are retried, and the game a lookup found is kept."""

    def __init__(self, client):
        self.client, self.found = client, None

    def lookup(self, *args, **kwargs):
        self.found = _retry(self.client.lookup, *args, **kwargs)
        return self.found

    def game(self, game_id):
        return _retry(self.client.game, game_id)

    def search(self, system_id, name):
        return _retry(self.client.search, system_id, name)

    def download(self, url, dest):
        return _retry(self.client.download, url, dest)


def _retry(call, *args, **kwargs):
    for attempt in range(RETRIES + 1):
        try:
            return call(*args, **kwargs)
        except screenscraper.RateLimited:
            if attempt == RETRIES:
                raise
            time.sleep(RETRY_WAIT * 2 ** attempt)


def make_client():
    """A ScreenScraper client from the credentials in settings.json; fails, saying how to set them, when any is missing."""
    settings = usersettings.load_settings()
    missing = [k for k in CREDENTIALS if not settings.get(k)]
    if missing:
        ui.fail(f"ScreenScraper credentials missing: {', '.join(missing)}. Set them with `sync-roms scrape --set-credentials`, "
                f"or add {', '.join(CREDENTIALS)} to {os.path.join(store.data_dir(), 'settings.json')} "
                "(your ScreenScraper login, and the developer id and password ScreenScraper gives on request)", 3)
    return screenscraper.Client(settings["screenscraper_user"], settings["screenscraper_password"],
                                {"devid": settings["screenscraper_devid"], "devpassword": settings["screenscraper_devpassword"]})


PROMPTS = (("screenscraper_user", "ScreenScraper username", False), ("screenscraper_password", "ScreenScraper password", True),
           ("screenscraper_devid", "ScreenScraper developer id", False), ("screenscraper_devpassword", "ScreenScraper developer password", True))


def set_credentials():
    """Ask for the four ScreenScraper credentials and save them in settings.json. A blank answer keeps the saved value;
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
    for key, value in answers.items():
        usersettings.save_setting(key, value)
    print(ui.green("✅ Saved ScreenScraper credentials to " + os.path.join(store.data_dir(), "settings.json")))
    return 0


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


def planned_match(system, rom, etag):
    """How match() will look a ROM up first, without asking ScreenScraper."""
    if scrape_state.manual_match(system, rom) is not None:
        return "manual"
    return "hash" if s3.read_root() or "-" not in etag.strip('"') else "name+size"


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


def scrape_rom(client, system, item, tmp, skip, stop):
    """("done", (how, metadata, {media type: local file})), ("unknown", None), ("failed", reason), ("quota", None)
    or ("skipped", None) when the run stopped (quota or Ctrl-C) before this ROM finished."""
    rom, size, etag = item
    if stop.is_set():
        return "skipped", None
    rc = _RomClient(client)
    try:
        game_id, how = match(rc, system, rom, size, etag)
        raw = rc.found if rc.found is not None else rc.game(game_id)
        if screenscraper.is_notgame(raw):
            raise screenscraper.NotFound("not a game")
        meta, media = screenscraper.parse_game(raw, ())
        if not meta:
            raise screenscraper.ApiError("ScreenScraper returned no data for it")
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
                rc.download(url, dest)
            except screenscraper.NotFound:  # ScreenScraper has no such file: not a failure
                continue
            ext = _media_ext(dest, mtype)
            if ext:
                files[mtype] = dest + ext
                os.replace(dest, files[mtype])
    except screenscraper.QuotaExceeded:
        stop.set()
        return "quota", None
    except screenscraper.NotFound:
        return "unknown", None
    except ROM_ERRORS as e:
        return "failed", _reason(e)
    return "done", (how, meta, files)


def _reason(e):
    """Printable text for a ROM's failure: our own ApiError messages (which never hold a URL), else only the error's type,
    since other errors' text can quote a media URL and the credentials in its query."""
    return str(e) if type(e) in (screenscraper.ApiError, screenscraper.RateLimited) and str(e) else type(e).__name__


def _uploaded(jobs, have):
    """Whether every upload job is in storage: same size for files, present for shrunk images."""
    return all(j[0] in have and (len(j) > 3 or have[j[0]] == j[2]) for j in jobs)


def _storage_fail(what, e):
    ui.fail(f"{what} failed ({type(e).__name__}). ROMs recorded in earlier batches are complete; "
            "run `sync-roms scrape` again to continue.", 3)


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


def run_batch(client, system, batch, skip, threads, shrink, outcomes, listing, replace=False):
    """Scrape, upload and record one batch of a system's ROMs. Returns (failures, quota hit).

    listing: {key: size} of scrapes/<system>/, kept up to date with what this batch uploads. Media types a ROM already
    has there are neither downloaded nor overwritten, unless replace: then the ROMs' metadata entries are replaced
    (not merged) and their old media files are overwritten or deleted.
    """
    name = system["bucket"]
    stop = threading.Event()
    failed = 0
    index = scrape_plan.scrape_index(listing)
    kept = {rom: set() if replace else set(index.get(os.path.splitext(rom)[0], ())) for rom, _, _ in batch}
    with tempfile.TemporaryDirectory() as tmp:
        ex = ThreadPoolExecutor(threads)
        try:
            futures = [ex.submit(scrape_rom, client, system, item, tmp, skip | kept[item[0]], stop) for item in batch]
            results = [f.result() for f in futures]
        except KeyboardInterrupt:
            stop.set()
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        ex.shutdown()
        quota_hit = any(status == "quota" for status, _ in results)
        jobs = {}  # ROM -> its upload jobs
        done = {}
        for (rom, _, _), (status, payload) in zip(batch, results):
            if status == "unknown":
                scrape_state.mark_unknown(name, rom)
                outcomes[rom] = None
                print(ui.dim(f"     ❔ {name}/{rom}: not on ScreenScraper"))
            elif status == "failed":
                failed += 1
                print(ui.yellow(f"  ⚠️  {name}/{rom}: {payload}; skipped"))
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
            upload_failed = upload.run_uploads(todo) if todo else 0
            have = s3.list_sizes(f"{scrape_plan.SCRAPES}/{name}/") if upload_failed else {}
        except s3.ERRORS as e:
            _storage_fail(f"Uploading {name} media", e)
        if upload_failed:
            for rom in [r for r in done if not _uploaded(jobs[r], have)]:
                failed += 1
                del done[rom]
                print(ui.yellow(f"  ⚠️  {name}/{rom}: its media didn't all upload; skipped"))
        for rom in done:
            listing.update((j[0], j[2]) for j in jobs[rom])
    if replace and done:
        stale = [k for rom in done for k in _media_keys(listing, name, os.path.splitext(rom)[0])
                 if k not in {j[0] for j in jobs[rom]}]
        try:
            errors = s3.delete_keys(stale) if stale else []
        except s3.ERRORS as e:
            _storage_fail(f"Deleting old {name} media", e)
        for k in stale:
            listing.pop(k, None)
        for e in errors:
            print(ui.yellow(f"  ⚠️  {e.get('Key')}: couldn't delete the old file"))
    if done:
        try:
            merged = scrape_plan.merge_metadata(load_metadata(name), {} if replace else
                                                {rom: meta for rom, (_, meta) in done.items()})
            if replace:
                merged.update((rom, dict(meta)) for rom, (_, meta) in done.items())
            s3.put_text(metadata_key(name), scrape_plan.dump_json(merged))
        except ValueError as e:
            print(ui.yellow(f"  ⚠️  {e}; {len(done)} ROM(s) not recorded"))
            return failed + len(done), quota_hit
        except s3.ERRORS as e:
            _storage_fail(f"Writing {metadata_key(name)}", e)
        for rom, (how, _) in done.items():
            outcomes[rom] = how
            if scrape_state.is_unknown(name, rom):  # found after all (a retry, or a manual match)
                scrape_state.clear_unknown(name, rom)
        print(ui.green(f"  ✅ {name}: {len(done)} ROM(s) scraped"))
    return failed, quota_hit


def run_scrape(client, systems, todo, skip, ask=True, replace=False):
    """Confirm (unless not ask), then scrape todo ({system: [(ROM, size, etag)]}) in batches. Returns the exit code.
    replace: the ROMs' metadata entries and media are replaced (see run_batch)."""
    count = sum(len(v) for v in todo.values())
    try:
        listings = {name: s3.list_sizes(f"{scrape_plan.SCRAPES}/{name}/") for name in todo}
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    kept = 0 if replace else sum(len(scrape_plan.scrape_index(listings[name]).get(os.path.splitext(r)[0], ()))
                                 for name, items in todo.items() for r, _, _ in items)
    note = f"; the {kept} media file(s) already there are kept" if kept else ""
    if ask and not ui.confirm(f"🖼️  Scrape {count} ROM(s) from ScreenScraper and write their media and metadata to "
                              f"{s3.location()}/{scrape_plan.SCRAPES}/{note} ?", default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    try:
        quota = _retry(client.quota)
    except screenscraper.QuotaExceeded:
        print(ui.yellow("⏳ ScreenScraper's daily quota is used up; run this again tomorrow."))
        return 1
    except screenscraper.ApiError as e:
        ui.fail(f"{e}", 3)
    if quota.max_today:
        print(ui.dim(f"ScreenScraper: {quota.used_today}/{quota.max_today} requests used today, {quota.max_threads} thread(s)"))
    shrink = scrape_plan.can_shrink()
    if not shrink:
        print(ui.yellow("  ⚠️  Onion box art and Slot labels need Pillow or macOS sips to resize images; not making them"))
    outcomes, failed, quota_hit = {}, 0, False
    for name, items in sorted(todo.items()):
        outcomes[name] = {}
        for i in range(0, len(items), BATCH):
            print(ui.bold(f"\n🔎 {name}: ROMs {i + 1}-{min(i + BATCH, len(items))} of {len(items)}"))
            n, quota_hit = run_batch(client, systems[name], items[i:i + BATCH], skip, max(1, quota.max_threads),
                                     shrink, outcomes[name], listings[name], replace)
            failed += n
            if quota_hit:
                break
        if quota_hit:
            break
    print(ui.bold("\n📋 Results"))
    print(report({name: [r for r, _, _ in items] for name, items in todo.items()}, outcomes))
    if quota_hit:
        print(ui.yellow("\n⏳ ScreenScraper's daily quota is used up. Everything scraped so far is saved; "
                        "run `sync-roms scrape` again tomorrow to continue where it stopped."))
        return 1
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def _check_skip(skip):
    skip = set(skip or ())
    bad = skip - scrape_plan.MEDIA_TYPES
    if bad:
        ui.fail(f"Unknown media type(s): {', '.join(sorted(bad))}; choose from {', '.join(sorted(scrape_plan.MEDIA_TYPES))}", 2)
    return skip


def _pick_systems(name):
    systems = store.load_manifest()["systems"]
    if name:
        systems = [s for s in systems if s["bucket"] == name]
        if not systems:
            ui.fail(f"No system {name!r}; give its bucket folder name (e.g. gba)", 2)
    return systems


def scrape_command(args):
    """Scrape the available ROMs that have no metadata yet from ScreenScraper into scrapes/<system>/.

    args: system (bucket folder name, or None for all), retry (also try ROMs marked unknown), skip_media (media type
    folder names not to download), dry_run.
    """
    skip = _check_skip(args.skip_media)
    print(ui.bold("🖼️  Scrape from ScreenScraper") + ui.dim(f"  {s3.access(True)}"))
    systems = _pick_systems(args.system)
    try:
        print("📏 Listing the ROMs available in the bucket...")
        roms = scrape_files.bucket_roms(systems)
        listed = [s for s in systems if roms.get(s["bucket"])]
        metadata = {}
        for s in listed:
            try:
                metadata[s["bucket"]] = load_metadata(s["bucket"])
            except ValueError:
                print(ui.yellow(f"  ⚠️  {metadata_key(s['bucket'])} isn't valid JSON; skipping {s['bucket']}"))
                roms[s["bucket"]] = set()
        candidates = find_candidates(listed, roms, metadata, retry=args.retry)
        for s in listed:
            if candidates.get(s["bucket"]) and "screenscraper" not in s:
                print(ui.yellow(f"  ⚠️  {s['bucket']} has no ScreenScraper system id; skipping its {len(candidates[s['bucket']])} ROM(s)"))
                del candidates[s["bucket"]]
        candidates = {k: v for k, v in candidates.items() if v}
        etags = {name: s3.list_with_etags(name + "/") for name in candidates}
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    todo = {name: [(r, *etags[name][r]) for r in roms_ if r in etags[name]] for name, roms_ in candidates.items()}
    planned = {name: {r: planned_match(name, r, etag) for r, _, etag in items} for name, items in todo.items()}
    if not any(todo.values()):
        print(ui.green("Nothing to scrape ✨"))
        return 0
    print(ui.bold("\n🔎 ROMs with no metadata (and how each will be looked up first)"))
    print(report({name: [r for r, _, _ in items] for name, items in todo.items()}, planned))
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
    return run_scrape(client, {s["bucket"]: s for s in systems}, todo, skip)


def match_command(args):
    """`scrape match SYSTEM ROM GAME`: save which ScreenScraper game a ROM is (GAME is a game id, or a name to search
    and pick from), then scrape that ROM.

    args: system (bucket folder name), rom (ROM path in it, e.g. "Game (USA).zip"), game, and optionally skip_media
    and dry_run (resolve the game, save and write nothing).
    """
    skip = _check_skip(getattr(args, "skip_media", None))
    system = _pick_systems(args.system)[0]
    name = system["bucket"]
    if "screenscraper" not in system:
        ui.fail(f"{name} has no ScreenScraper system id, so it can't be scraped", 2)
    try:
        listing = s3.list_with_etags(name + "/")
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    if args.rom not in listing:
        ui.fail(f"No {name}/{args.rom} in {s3.location()}", 2)
    client = make_client()
    try:
        game_id = resolve_manual(_RomClient(client), system, args.game)
    except screenscraper.NotFound as e:
        if str(e) == "cancelled":
            print(ui.yellow("👋 Cancelled."))
            return 0
        ui.fail(f"ScreenScraper has no game for {args.game!r}", 1)
    except (screenscraper.ApiError, screenscraper.QuotaExceeded) as e:
        ui.fail(f"{e}", 3)
    if getattr(args, "dry_run", False):
        print(ui.yellow(f"🧪 Dry run — would match {name}/{args.rom} to ScreenScraper game {game_id} and scrape it"))
        return 0
    try:
        replace = args.rom in load_metadata(name)
    except ValueError:
        ui.fail(f"{metadata_key(name)} isn't valid JSON", 3)
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    question = (f"🔁 Replace the metadata and media of {name}/{args.rom} with ScreenScraper game {game_id}? "
                "Its old media files are overwritten or deleted." if replace else
                f"🖼️  Scrape {name}/{args.rom} as ScreenScraper game {game_id} and write its media and metadata to "
                f"{s3.location()}/{scrape_plan.SCRAPES}/ ?")
    if not ui.confirm(question, default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    scrape_state.save_match(name, args.rom, game_id)
    print(f"🔗 {name}/{args.rom} → ScreenScraper game {game_id}")
    size, etag = listing[args.rom]
    return run_scrape(client, {name: system}, {name: [(args.rom, size, etag)]}, skip, ask=False, replace=replace)
