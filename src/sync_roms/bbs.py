"""The Lexaloffle PICO-8 BBS Featured listing: read a page, tell new carts from upgrades."""
import contextlib
import datetime
import http.client
import os
import re
import tempfile

from . import collections, drivers, github, ignore, inventory, runtime, s3, scrape_plan, scrape_state, store, surprise, ui, usersettings

LISTING = "https://www.lexaloffle.com/bbs/?cat=7&sub=2&orderby=featured"
_CARTS = "https://www.lexaloffle.com/bbs/cposts/"
_THUMB = re.compile(r"/pico8_(.+)\.png$")
_NAME = re.compile(r"^(.*?)(?:-(\d+))?\.p8\.png$")
_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.p8\.png")
_PNG = b"\x89PNG\r\n\x1a\n"
_HTTP_ERRORS = (OSError, http.client.HTTPException)
META = scrape_plan.metadata_key("pico8")
MEDIA = f"{scrape_plan.SCRAPES}/pico8/"
META_EVERY = 25  # carts put in storage between writes of META


def _fetch(url):
    """The body at url: the only request this module makes."""
    with github.get(url) as r:
        return r.read()


def page_url(n):
    return LISTING if n <= 1 else f"{LISTING}&page={n}"


def cart_url(file):
    return f"{_CARTS}{file[:2]}/{file}"


def identity(file):
    """(base, revision): molemole-1.p8.png -> ("molemole", 1); no suffix is revision 0."""
    m = _NAME.match(file)
    if not m:
        return file, 0
    return m.group(1), int(m.group(2) or 0)


def _value(text, i):
    """One JS value at text[i]: (value, next index). Empty slots are None."""
    c = text[i]
    if c in "'\"`":
        out = []
        i += 1
        while text[i] != c:
            if text[i] == "\\":
                i += 1
            out.append(text[i])
            i += 1
        return "".join(out), i + 1
    if c == "[":
        items = []
        i += 1
        while True:
            while text[i] in " \t\r\n":
                i += 1
            if text[i] == "]":
                return items, i + 1
            if text[i] == ",":
                items.append(None)
                i += 1
                continue
            item, i = _value(text, i)
            items.append(item)
            while text[i] in " \t\r\n":
                i += 1
            if text[i] == ",":
                i += 1
    j = i
    while text[j] not in ",]":
        j += 1
    return text[i:j].strip(), j


def parse_page(html):
    """The carts of one listing page, in page order.

    Each row of `pdat=[...]` is a JS array; the fields used are
    0 post id, 2 title, 3 thumbnail "/bbs/thumbs/pico8_<file stem>.png"
    (the cart is <stem>.p8.png), 7 author's user id, 8 author name
    (9..11 are the last comment's date, user id and name).
    """
    start = html.find("pdat=[")
    if start < 0:
        return []
    rows, _ = _value(html, start + len("pdat="))
    carts = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 9:
            continue
        m = _THUMB.search(row[3] or "")
        if not m:
            continue
        file = m.group(1) + ".p8.png"
        if not _FILE.fullmatch(file):
            ui.warn(f"Skipped a BBS cart whose file name isn't a plain name: {file!r}")
            continue
        carts.append({"post": row[0], "title": row[2], "author": row[8], "file": file})
    return carts


def classify(carts, keys, ignored):
    """(new, upgrades) among carts, given the `pico8/...` storage keys and ignored keys.

    An upgrade is (old key, cart): storage holds the same base at a lower revision.
    """
    skip = {identity(k.rsplit("/", 1)[-1])[0] for k in ignored}
    held = {}
    for key in keys:
        base, rev = identity(key.rsplit("/", 1)[-1])
        if base not in held or rev > held[base][0]:
            held[base] = (rev, key)
    new, upgrades, seen = [], [], set()
    for c in carts:
        base, rev = identity(c["file"])
        if base in skip or base in seen:
            continue
        seen.add(base)
        if base not in held:
            new.append(c)
        elif rev > held[base][0]:
            upgrades.append((held[base][1], c))
    return new, upgrades


def _names(game, key):
    return isinstance(game, dict) and (game.get("bucket") == key
                                       or (isinstance(game.get("files"), list) and key in game["files"]))


def _move(game, old, new, title):
    """Rewrite game (a dict) in place when it names old; True when it did."""
    if not _names(game, old):
        return False
    if game.get("bucket") == old:
        game["bucket"] = new
    if isinstance(game.get("files"), list):
        game["files"] = [new if k == old else k for k in game["files"]]
    game["title"] = title
    return True


def _move_all(games, old, new, title):
    return sum([_move(g, old, new, title) for g in games if isinstance(g, dict)]) > 0


def _move_key(keys, old, new):
    """Put new where old is in keys (a list of bucket keys), in place and listed once; True when old was there."""
    if old not in keys:
        return False
    keys[:] = dict.fromkeys(new if k == old else k for k in keys)
    return True


def retarget(old, new, title):
    """Move every personal reference to the cart key old onto new, retitled: cards' games (a full system's kept list
    too), exclusions and surprises, the surprise history and collections, each file saved only when it changed.
    Returns the ids of the sets that still name old (as a game, one of its files or a variant), for the caller to
    warn about."""
    cards = store.load_cards()
    changed = False
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        games = card.get("games")
        for entries in games.values() if isinstance(games, dict) else ():
            if isinstance(entries, dict):  # a full system: the list it replaced
                entries = entries.get("games")
            if isinstance(entries, list):
                changed |= _move_all(entries, old, new, title)
        excluded = card.get("excluded")
        for keys in excluded.values() if isinstance(excluded, dict) else ():
            if isinstance(keys, list):
                changed |= _move_key(keys, old, new)
        if isinstance(card.get("surprises"), list):
            changed |= _move_all(card["surprises"], old, new, title)
    if changed:
        store.write_cards(cards)
    history = surprise.load_history()
    if _move_all(history, old, new, title):
        surprise.save_history(history, datetime.date.today())
    for collection in collections.load_collections():
        if _move_all(collection["games"], old, new, title):
            collections.save_collection(collection)
    return [s["id"] for s in store.load_sets()
            if any(_names(g, old) or any(_names(v, old) for v in g.get("variants") or ()) for g in s["games"])]


# --- sync-roms download pico8 ---------------------------------------------------------------------------------------

def _read_listing(keys, ignored, count):
    """((new, upgrades), carts, failed) from the listing's pages, read in turn until a page has no rows, an HTTP error
    (a warning, failed is True; the pages read are kept) or, with count, enough carts."""
    carts, n, failed = [], 1, False
    while True:
        try:
            rows = parse_page(_fetch(page_url(n)).decode("utf-8", "replace"))
        except _HTTP_ERRORS as e:
            ui.warn(f"Couldn't read page {n} of the PICO-8 BBS Featured listing ({e}); using the {n - 1} page(s) read")
            failed = True
            break
        if not rows:
            break
        carts += rows
        new, upgrades = classify(carts, keys, ignored)
        if count is not None and len(new) + len(upgrades) >= count:
            break
        n += 1
    return classify(carts, keys, ignored), carts, failed


def _media_moves(old_file, new_file):
    """(old key, new key) of the scrapes/pico8/ media named after old_file's stem."""
    old_stem, new_stem = os.path.splitext(old_file)[0], os.path.splitext(new_file)[0]
    moves = []
    for key in inventory.files(MEDIA, sizes=False):
        folder, _, name = key[len(MEDIA):].rpartition("/")
        stem, ext = os.path.splitext(name)
        if folder and stem == old_stem:
            moves.append((key, f"{MEDIA}{folder}/{new_stem}{ext}"))
    return moves


def _move_state(old_file, new_file):
    """Give the new revision the old one's manual ScreenScraper match and forget the rest of the old one's scrape
    state (non-game, unknown, not-offered media, hashes): that was about another file."""
    scrape_state.move_match("pico8", old_file, new_file)
    scrape_state.clear_notgame("pico8", old_file)
    scrape_state.clear_unknown("pico8", old_file)
    scrape_state.mark_nomedia("pico8", old_file, ())
    scrape_state.forget_hashes("pico8", old_file)
    scrape_state.flush()


def _download(cart, tmp):
    """The cart's .p8.png saved in tmp; None (a warning) when what came isn't a PNG."""
    data = _fetch(cart_url(cart["file"]))
    if not data.startswith(_PNG):
        ui.warn(f"{cart['file']} from the BBS isn't a PNG; skipped")
        return None
    path = os.path.join(tmp, cart["file"])
    with open(path, "wb") as f:
        f.write(data)
    return path


def download_pico8(args):
    """Add the BBS Featured carts storage doesn't have to pico8/, and newer revisions of those it has. Exit code."""
    usersettings.ensure_bucket()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):
        ui.warn(f"The storage folder {runtime.ROOT} isn't there (is it mounted?)")
        return 1
    if not args.dry_run and not drivers.can_write():
        ui.fail(f"No write access to {s3.location()}: `download pico8` adds files to storage")
    keys = set(inventory.files("pico8/", sizes=False))
    (new, upgrades), carts, failed = _read_listing(keys, ignore.keys(), args.count)
    order = {c["file"]: i for i, c in enumerate(carts)}
    todo = sorted([(None, c) for c in new] + upgrades, key=lambda job: order[job[1]["file"]])[:args.count]
    if not todo:
        if not failed:
            print(ui.green(f"✅ storage has every Featured PICO-8 cart ({len(carts)} listed)"))
        return 1 if failed else 0
    print(ui.bold(f"🕹️  PICO-8 BBS Featured: {len(carts)} carts listed"))
    for old, c in todo:
        print(f"  new: {c['file']}" if old is None else f"  upgrade: {old} → {c['file']}")
    print(f"  {sum(old is None for old, _ in todo)} new, {sum(old is not None for old, _ in todo)} upgrade(s)")
    if args.dry_run:
        print(ui.dim("🧪 Dry run: nothing downloaded or written"))
        return 1 if failed else 0
    if not args.yes and not ui.confirm(f"Add these to {s3.location()}?", default=False):
        return 1 if failed else 0
    try:
        meta = scrape_plan.load_metadata("pico8", fresh=True)
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't read {META} ({e})")
        return 1
    added = upgraded = 0
    code = 1 if failed else 0
    pending = []  # (old key or None, cart, key) of the carts put in storage since META was last written

    def finish():
        """Write META with the pending carts, then move the upgrades off their old revisions. False, with the pending
        carts taken back out (so the next run adds them again with their titles), when META couldn't be written."""
        nonlocal added, upgraded, code
        if not pending:
            return True
        done = pending[:]
        pending.clear()
        try:
            s3.put_text(META, scrape_plan.dump_json(meta))
        except s3.ERRORS as e:
            keys = [key for _, _, key in done]
            ui.warn(f"Couldn't write {META} ({e}); removing {', '.join(keys)} again and stopping")
            with contextlib.suppress(*s3.ERRORS):
                s3.delete_keys(keys)
            code = 1
            return False
        for old, c, key in done:
            if old is None:
                added += 1
                continue
            old_file = old[len("pico8/"):]
            moves = _media_moves(old_file, c["file"])
            if moves and s3.move_keys(moves):
                code = 1
            _move_state(old_file, c["file"])
            try:
                still = retarget(old, key, c["title"])
            except OSError as e:  # the references still name the old revision, so it stays
                ui.warn(f"Couldn't move cards and collections from {old} to {key} ({e}); keeping {old}")
                code = 1
                upgraded += 1
                continue
            for set_id in still:
                ui.warn(f"Set {set_id} still names {old}: change it to {key}")
            try:  # last, so a failure here leaves only a duplicate file: the new cart is complete
                errors = s3.delete_keys([old])
            except s3.ERRORS as e:
                errors = [e]
            if errors:
                ui.warn(f"Couldn't delete {old} from storage ({errors[0]}); delete it by hand")
                code = 1
            upgraded += 1
        return True
    with tempfile.TemporaryDirectory() as tmp:
        try:  # a stop (or Ctrl-C) still writes META for the carts already put in storage
            for old, c in todo:
                file, key = c["file"], f"pico8/{c['file']}"
                try:
                    path = _download(c, tmp)
                except _HTTP_ERRORS as e:
                    ui.warn(f"Couldn't download {file} from the BBS ({e}); stopping")
                    code = 1
                    break
                if path is None:
                    continue
                try:
                    s3.put_file(key, path)
                except s3.ERRORS as e:
                    ui.warn(f"Couldn't write {file} to {s3.location()} ({e}); stopping")
                    code = 1
                    break
                entry = {"name": c["title"], "developer": c["author"]}
                if old is not None:
                    entry = {**meta.pop(old[len("pico8/"):], {}), **entry}
                meta = scrape_plan.merge_metadata(meta, {file: entry})
                pending.append((old, c, key))
                if len(pending) >= META_EVERY and not finish():
                    break
        finally:
            finish()
    print(ui.green(f"✅ Added {added} and upgraded {upgraded} PICO-8 cart(s) in {s3.location()}"))
    return code
