"""PICO-8 Splore carts cached on a spruceOS card: read what the card holds and tell new carts from upgrades."""
import glob
import os

from . import bbs, ignore, inventory

CACHE = ("Emu", "PICO8", ".lexaloffle", "pico-8")


def favourites(base):
    """{cart base: (title or None, author or None)} from the card's `favourites.txt`."""
    out = {}
    try:
        with open(os.path.join(base, *CACHE, "favourites.txt"), encoding="utf-8", errors="replace") as f:
            lines = f.read().replace("\r", "").split("\n")
    except OSError:
        return out
    for line in lines:
        fields = [x.strip() for x in line.split("|")]
        if len(fields) < 2 or not fields[1]:
            continue
        name = fields[1].rsplit("/", 1)[-1]
        for ext in (".p8.png", ".p8"):
            if name.endswith(ext):
                name = name[:-len(ext)]
        cart = bbs.identity(name + ".p8.png")[0]
        title = next((x for x in reversed(fields[6:]) if x), None)  # the last field: the title
        author = fields[4] if len(fields) > 4 and fields[4] else None
        out[cart] = (title, author)
    return out


def _is_png(path):
    try:
        with open(path, "rb") as f:
            return f.read(len(bbs._PNG)) == bbs._PNG
    except OSError:
        return False


def cached(base):
    """The carts in the card's Splore cache, the highest revision of each, sorted by file."""
    root = os.path.join(base, *CACHE, "bbs")
    paths = glob.glob(os.path.join(glob.escape(root), "carts", "*.p8.png"))
    paths += glob.glob(os.path.join(glob.escape(root), "*", "*.p8.png"))
    best = {}
    for path in paths:
        file = os.path.basename(path)
        if file.startswith("temp-") or not bbs._FILE.fullmatch(file) or not _is_png(path):
            continue
        name, rev = bbs.identity(file)
        if name not in best or rev > best[name][0]:
            best[name] = (rev, file, path)
    names = favourites(base)
    carts = []
    for name, (_, file, path) in best.items():
        title, author = names.get(name, (None, None))
        carts.append({"file": file, "path": path, "title": title, "author": author})
    return sorted(carts, key=lambda c: c["file"])


def plan(base):
    """(new, upgrades) of the card's cached carts against storage's `pico8/`."""
    return bbs.classify(cached(base), set(inventory.files("pico8/", sizes=False)), ignore.keys())
