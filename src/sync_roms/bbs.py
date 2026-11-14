"""The Lexaloffle PICO-8 BBS Featured listing: read a page, tell new carts from upgrades."""
import re

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
