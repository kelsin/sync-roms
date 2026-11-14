"""The Lexaloffle PICO-8 BBS Featured listing: read a page, tell new carts from upgrades."""
import datetime
import re

from . import collections, store, surprise

LISTING = "https://www.lexaloffle.com/bbs/?cat=7&sub=2&orderby=featured"
_CARTS = "https://www.lexaloffle.com/bbs/cposts/"
_THUMB = re.compile(r"/pico8_(.+)\.png$")
_NAME = re.compile(r"^(.*?)(?:-(\d+))?\.p8\.png$")


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
        if m:
            carts.append({"post": row[0], "title": row[2], "author": row[8],
                          "file": m.group(1) + ".p8.png"})
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


def retarget(old, new, title):
    """Move every personal reference to the cart key old onto new, retitled: cards' games and surprises, the
    surprise history and collections, each file saved only when it changed. Returns the ids of the repo sets that
    still name old, for the caller to warn about."""
    cards = store.load_cards()
    changed = False
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        games = card.get("games")
        for entries in games.values() if isinstance(games, dict) else ():
            if isinstance(entries, list):
                changed |= _move_all(entries, old, new, title)
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
            if any(_names(g, old) for g in s["games"])]
