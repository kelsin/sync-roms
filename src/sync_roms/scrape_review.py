"""Reviewing ROMs ScreenScraper calls non-games: ignore each one, search for it under another name, or leave it for
later. A scrape offers this at the end of its run; `sync-roms scrape review` opens it any time."""
import argparse
import re
import sys

from . import ignore, inventory, s3, scrape_online, scrape_state, screenscraper, ui

PROMPT = "[i]gnore · [s]earch · [k]eep for later · [I]gnore all the rest  (k): "
_TAGS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")


def search_name(rom):
    """A ROM's file name without its extension or its (...) and [...] tags: what to search ScreenScraper for."""
    stem = rom.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return " ".join(_TAGS.sub("", stem).split())


def _show(key, size, info):
    print(ui.bold(f"\n🚫 {key}") + ui.dim(f"  {ui.human_size(size)}" if size is not None else ""))
    said = " · ".join(p for p in (info.get("name"), info.get("genre"), info.get("year")) if p)
    print(f"   ScreenScraper: {said or '(no details)'}")
    if info.get("desc"):
        print(ui.dim(f"   {info['desc']}"))


def _search(system, rom, client):
    """Whether the ROM was matched to a game and scraped (its saved match is the game picked)."""
    name = system["bucket"]
    suggestion = search_name(rom)
    query = ui.ask(f"   Search name [{suggestion}]: ").strip() or suggestion
    try:
        game_id = scrape_online.resolve_manual(scrape_online._RomClient(client), system, query)
    except (screenscraper.NotFound, screenscraper.ApiError, screenscraper.QuotaExceeded) as e:
        print(ui.yellow(f"   {e}"))
        return False
    code = scrape_online.match_command(argparse.Namespace(system=name, rom=rom, game=str(game_id), skip_media=None,
                                                          dry_run=False, confirmed=True))
    return code == 0 and scrape_state.manual_match(name, rom) == game_id


def review(systems, keys, sizes, client=None):
    """Go through the pending non-games in keys ("system/rom"), one at a time. systems: {storage folder: system}."""
    keys = sorted(keys, key=lambda k: tuple(k.split("/", 1)))
    queued = []
    try:
        for i, key in enumerate(keys):
            name, rom = key.split("/", 1)
            _show(key, sizes.get(key), scrape_state.notgames().get(key, {}))
            while True:
                answer = ui.ask(PROMPT).strip()
                if answer in ("", "k"):
                    break
                if answer == "i":
                    queued.append(key)
                    break
                if answer == "I":
                    rest = keys[i:]
                    if ui.confirm(f"   Ignore this and the {len(rest) - 1} remaining ROM(s)?", default=False):
                        queued += rest
                        return 0
                    continue
                if answer == "s":
                    if client is None:
                        client = scrape_online.make_client()
                    if _search(systems[name], rom, client):
                        scrape_state.clear_notgame(name, rom)
                        break
                    continue
        return 0
    finally:
        if queued:
            entries = {}
            for key in queued:
                name, rom = key.split("/", 1)
                entries.setdefault(name, []).append(rom)
            ignore.add(entries)
            for key in queued:
                scrape_state.clear_notgame(*key.split("/", 1))
            print(ui.green(f"🙈 Ignored {len(queued)} ROM(s)"))


def _systems(name):
    return {s["bucket"]: s for s in scrape_online._pick_systems(name)}


def review_command(args):
    """`scrape review [SYSTEM]`: review every pending non-game (of one system, when given)."""
    if not sys.stdin.isatty():
        ui.fail("scrape review needs a terminal", 2)
    keys = sorted(k for k in scrape_state.notgames() if not args.system or k.split("/", 1)[0] == args.system)
    if not keys:
        print(ui.green("No non-game results to review ✨"))
        return 0
    if s3.read_root() or inventory.current() is not None:
        sizes = inventory.stat(keys)  # ignored or deleted ROMs are left out
    else:  # a bucket with no storage cache: one listing per system
        sizes = {}
        for system in sorted({k.split("/", 1)[0] for k in keys}):
            sizes.update(inventory.files(system + "/"))
        sizes = {k: n for k, n in sizes.items() if k in keys}
    for key in keys:
        if key not in sizes:
            scrape_state.clear_notgame(*key.split("/", 1))
    keys = [k for k in keys if k in sizes]
    if not keys:
        print(ui.green("No non-game results to review ✨"))
        return 0
    return review(_systems(args.system), keys, sizes)
