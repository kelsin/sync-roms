"""Online scraping: which ROMs need metadata, and which ScreenScraper game each one is."""
import hashlib
import os
import zlib

from . import s3, scrape_state, screenscraper, ui

CHUNK = 8 << 20


def find_candidates(systems, roms, metadata, retry=False):
    """{system folder: sorted ROM paths} with no entry in that system's metadata.json (and, unless retry, not marked unknown)."""
    out = {}
    for s in systems:
        system = s["bucket"]
        have = metadata.get(system, {})
        out[system] = sorted(r for r in roms.get(system, ())
                             if r not in have and (retry or not scrape_state.is_unknown(system, r)))
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
    """(game id, how) for a ROM; how is "manual", "hash" or "name+size". Raises screenscraper.NotFound."""
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
    return screenscraper._int(game.get("id")), "hash" if hashes else "name+size"


def resolve_manual(client, system, query):
    """A game id: the query itself when it is an integer, else the user's pick from a ScreenScraper search."""
    query = query.strip()
    if query.isdigit():
        return int(query)
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
