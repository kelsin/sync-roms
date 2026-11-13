"""Reviewing ROMs ScreenScraper calls non-games or doesn't know: ignore each one, search for it under another name, or
leave it for later. A scrape offers this for non-games at the end of its run; `sync-roms scrape review` opens it any time
for both."""
import argparse
import os
import re
import sys

from . import ignore, inventory, s3, scrape_online, scrape_state, screenscraper, ui

PROMPT = "[i]gnore · [s]earch · [k]eep for later · [b]ack · [q]uit · [I]gnore all the rest  (k): "
NOTHING = "No non-game or unknown ROMs to review ✨"
_TAGS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")


def search_name(rom):
    """A ROM's file name without its extension or its (...) and [...] tags: what to search ScreenScraper for."""
    stem = rom.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return " ".join(_TAGS.sub("", stem).split())


def _out():
    """Where the review's lines go: under --quiet the questions are on stderr, so what they are about is too."""
    return sys.stderr if ui.QUIET else sys.stdout


def _show(key, size, info, pos):
    """info: what ScreenScraper said of a non-game, or None for a ROM it doesn't know. pos: (its number, how many)."""
    out = _out()
    print(ui.bold(f"\n{'❔' if info is None else '🚫'} {key}") + ui.dim(f"  {ui.human_size(size)}" if size is not None else "")
          + ui.dim(f"  · {pos[0]} of {pos[1]}"), file=out)
    if info is None:
        print("   ScreenScraper: doesn't know this ROM", file=out)
        return
    said = " · ".join(p for p in (info.get("name"), info.get("genre"), info.get("year")) if p)
    print(f"   ScreenScraper: {said or '(no details)'}", file=out)
    if info.get("desc"):
        print(ui.dim(f"   {info['desc']}"), file=out)


def _clear(key):
    """Take a ROM off the review lists (non-games and unknown)."""
    name, rom = key.split("/", 1)
    scrape_state.clear_notgame(name, rom)
    scrape_state.clear_unknown(name, rom)
    scrape_state.flush_unknown()


def _search(system, rom, client):
    """Whether the ROM was matched to a game and scraped (its saved match is the game picked)."""
    name = system["bucket"]
    suggestion = search_name(rom)
    query = ui.ask(f"   Search name [{suggestion}]: ").strip() or suggestion
    try:
        game_id = scrape_online.resolve_manual(scrape_online._RomClient(client), system, query)
    except (screenscraper.NotFound, screenscraper.ApiError, screenscraper.QuotaExceeded) as e:
        print(ui.yellow(f"   {e}"), file=_out())
        return False
    code = scrape_online.match_command(argparse.Namespace(system=name, rom=rom, game=str(game_id), skip_media=None,
                                                          dry_run=False, confirmed=True, client=client))
    if code == 0 and scrape_state.manual_match(name, rom) == game_id:
        return True
    print(ui.yellow(f"   {name}/{rom} was not scraped as game {game_id}"), file=_out())
    return False


def review(systems, keys, sizes, client=None):
    """Go through the pending non-games and unknown ROMs in keys ("system/rom"), one at a time; those kept for later
    come after the rest. systems: {storage folder: system}."""
    kept = scrape_state.kept()
    keys = sorted(keys, key=lambda k: (k in kept, *k.split("/", 1)))
    queued, searched, i = [], set(), 0
    try:
        while i < len(keys):
            key = keys[i]
            if key in searched:
                i += 1
                continue
            name, rom = key.split("/", 1)
            _show(key, sizes.get(key), scrape_state.notgames().get(key), (i + 1, len(keys)))
            while True:
                answer = ui.ask(PROMPT).strip()
                if answer in ("", "k"):
                    scrape_state.keep(name, rom)
                    i += 1
                    break
                if answer == "i":
                    queued.append(key)
                    i += 1
                    break
                if answer == "q":
                    return 0
                if answer == "b":
                    if not queued:
                        print(ui.yellow("   No ignore to take back"), file=_out())
                        continue
                    back = keys.index(queued.pop())
                    for k in keys[back + 1:i]:
                        if k in searched:
                            print(ui.yellow(f"   {k} was scraped from a search; that stays (`scrape match` changes it)"), file=_out())
                    i = back
                    break
                if answer == "I":
                    rest = [k for k in keys[i:] if k not in searched]
                    if ui.confirm(f"   Ignore this and the {len(rest) - 1} remaining ROM(s)?", default=False):
                        queued += rest
                        return 0
                    continue
                if answer == "s":
                    if client is None:
                        client = scrape_online.make_client()
                    if _search(systems[name], rom, client):
                        _clear(key)
                        searched.add(key)
                        i += 1
                        break
                    continue
                print(ui.yellow(f"   Unknown answer {answer!r}"), file=_out())
        return 0
    finally:
        if queued:
            entries = {}
            for key in queued:
                name, rom = key.split("/", 1)
                entries.setdefault(name, []).append(rom)
            ignore.add(entries)
            for key in queued:
                _clear(key)
            print(ui.green(f"🙈 Ignored {len(queued)} ROM(s)"))


def _systems(name):
    return {s["bucket"]: s for s in scrape_online._pick_systems(name)}


def _scraped(keys):
    """The keys of unknown ROMs that have a metadata entry by now (from `upload scrapes`, say)."""
    out = set()
    for system in sorted({k.split("/", 1)[0] for k in keys}):
        try:
            have = scrape_online.load_metadata(system)
        except ValueError:  # an unreadable metadata.json: keep its ROMs to review
            continue
        out |= {k for k in keys if k.split("/", 1)[0] == system and k.split("/", 1)[1] in have}
    return out


def review_command(args):
    """`scrape review [SYSTEM]`: review every pending non-game and unknown ROM (of one system, when given)."""
    if not sys.stdin.isatty():
        ui.fail("scrape review needs a terminal", 2)

    def mine(k):
        return not args.system or k.split("/", 1)[0] == args.system
    notgames = {k for k in scrape_state.notgames() if mine(k)}
    unknown = {k for k in scrape_state.unknown() if mine(k)} - notgames
    for key in _scraped(unknown):
        _clear(key)
        unknown.discard(key)
    keys = sorted(notgames | unknown)
    if not keys:
        print(ui.green(NOTHING))
        return 0
    if s3.read_root() or inventory.current() is not None:
        sizes = inventory.stat(keys)  # ignored or deleted ROMs are left out
    else:  # a bucket with no storage cache: one listing per system
        sizes = {}
        for system in sorted({k.split("/", 1)[0] for k in keys}):
            sizes.update(inventory.files(system + "/"))
        sizes = {k: n for k, n in sizes.items() if k in keys}
    if not sizes and inventory.current() is None and s3.read_root() and not os.path.isdir(s3.read_root()):
        ui.fail(f"{s3.read_root()} isn't there (is the share mounted?); nothing reviewed", 3)  # keep every mark
    for key in keys:
        if key not in sizes:
            _clear(key)
    keys = [k for k in keys if k in sizes]
    if not keys:
        print(ui.green(NOTHING))
        return 0
    return review(_systems(args.system), keys, sizes)
