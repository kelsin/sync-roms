"""PICO-8 Splore carts cached on a spruceOS card: read what the card holds and tell new carts from upgrades."""
import glob
import os
import shutil
import tempfile

from . import bbs, cardfs, drivers, ignore, inventory, names, s3, scrape_online, store, ui, usersettings

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


def _same(path, other):
    """Whether two files hold the same bytes."""
    try:
        if os.path.getsize(path) != os.path.getsize(other):
            return False
        with open(path, "rb") as a, open(other, "rb") as b:
            return a.read() == b.read()
    except OSError:
        return False


def _renames(base, pico8_dir, held):
    """[(old name, cart file)] of the top-level `.p8.png` copies in pico8_dir that hold a cached cart's bytes under
    another name, when held (the `pico8/` keys) has that cart and pico8_dir doesn't have its file yet."""
    carts = [c for c in cached(base) if f"pico8/{c['file']}" in held]
    out, taken = [], set()
    for name, (is_dir, _) in sorted(cardfs.listing(pico8_dir).items()):
        if is_dir or not name.endswith(".p8.png"):
            continue
        for c in carts:
            if name != c["file"] and c["file"] not in taken and not cardfs.exists(os.path.join(pico8_dir, c["file"])) \
                    and _same(os.path.join(pico8_dir, name), c["path"]):
                out.append((name, c["file"]))
                taken.add(c["file"])
                break
    return out


def _rename(card, base, pico8_dir, dry_run=False, planned=()):
    """Rename the card's Splore-import copies of carts storage has to the cart's own file name, then add the cached
    carts storage has and pico8_dir holds to the card's games (a cart the games don't name would be an extra). Exit
    code. dry_run: only list them, counting the planned keys (carts the run would add) as held."""
    try:
        held = set(inventory.files("pico8/", sizes=False)) | set(planned)
    except s3.ERRORS as e:
        ui.warn(f"Couldn't list pico8/ in {s3.location()} ({e}); not renaming Splore imports")
        return 1
    code, renamed = 0, set()
    for old, file in _renames(base, pico8_dir, held):
        if dry_run:
            print(f"  would rename {old} → {file}")
            renamed.add(file)
            continue
        try:
            os.rename(os.path.join(pico8_dir, old), os.path.join(pico8_dir, file))
        except OSError as e:
            ui.warn(f"Couldn't rename {old} to {file} ({e})")
            code = 1
            continue
        print(f"  📦 Renamed {old} → {file}")
    if not dry_run:
        cardfs.clear()
    games = store.card_games(card).get("pico8")
    if isinstance(games, dict):  # a full system: every cart syncs already
        return code
    named = {g.get("bucket") for g in games if isinstance(g, dict)} if isinstance(games, list) else set()
    keys = [key for c in cached(base) if (key := f"pico8/{c['file']}") in held and key not in named
            and key not in ignore.keys() and (c["file"] in renamed or cardfs.exists(os.path.join(pico8_dir, c["file"])))]
    for key in keys:
        print(f"  {'would add' if dry_run else '➕ Added'} {key[len('pico8/'):]} to the card's games")
    if keys and not dry_run:
        _add_to_card(card, keys)
    return code


def _fetch(cart, tmp):
    path = os.path.join(tmp, cart["file"])
    shutil.copyfile(cart["path"], path)
    return path


def _has_login():
    settings = usersettings.load_settings()
    return all(settings.get(k) for k in scrape_online.CREDENTIALS)


def _scrape(added, system):
    """Scrape the carts just added: run_scrape's exit code (130: stopped with Ctrl-C), 0 without a login, 1 when it
    failed (warned)."""
    if not _has_login():
        print(ui.dim("  no ScreenScraper login saved: `sync-roms scrape pico8` scrapes them"))
        return 0
    try:
        sizes = inventory.files("pico8/")
        todo = [(key[len("pico8/"):], sizes.get(key), inventory.tag(key)) for key in added]
        return scrape_online.run_scrape(scrape_online.make_client(), {"pico8": system}, {"pico8": todo}, set(),
                                        ask=False, review=False)
    except SystemExit:  # ui.fail already said why
        ui.warn("The Splore carts' scrape stopped; `sync-roms scrape pico8` tries again")
        return 1
    except Exception as e:
        ui.warn(f"Couldn't scrape the Splore carts ({e}); `sync-roms scrape pico8` tries again")
        return 1


def _add_to_card(card, added):
    games = store.card_games(card)
    entries = games.get("pico8")
    if isinstance(entries, dict):  # a full system: every cart syncs already
        return
    entries = list(entries) if isinstance(entries, list) else []
    named = {g.get("bucket") for g in entries if isinstance(g, dict)}
    new = [{"title": names.title(key), "bucket": key} for key in added if key not in named]
    if new:
        store.update_card(card, games={**games, "pico8": entries + new})


def run(card, base, pico8_dir, system, dry_run):
    """Add the carts in a spruce card's Splore cache to storage's pico8/ (new carts and newer revisions), scrape the
    new ones and add them to the card's games, then rename the card's Splore-import copies (base: the card's root;
    pico8_dir: its PICO-8 ROM folder; system: the pico8 entry of systems). Exit code, 0 or 1."""
    try:
        new, upgrades = plan(base)
    except s3.ERRORS as e:
        ui.warn(f"Couldn't read pico8/ in {s3.location()} ({e}); skipping the Splore carts")
        return 1
    todo = [(None, c) for c in new] + upgrades
    if not todo:
        return _rename(card, base, pico8_dir, dry_run)
    print(ui.bold("🕹️  Splore carts on the card"))
    for old, c in todo:
        print(f"  new: {c['file']}" if old is None else f"  upgrade: {old} → {c['file']}")
    print(f"  {len(new)} new, {len(upgrades)} upgrade(s)")
    if dry_run:
        print(ui.dim(f"  would scrape {len(new)} cart(s)" if _has_login() else
                     "  no ScreenScraper login saved: would not scrape them (`sync-roms scrape pico8` does)"))
        return _rename(card, base, pico8_dir, True, {f"pico8/{c['file']}" for _, c in todo})
    if not drivers.can_write():
        ui.warn(f"No write access to {s3.location()}: the Splore carts stay on the card only")
        return _rename(card, base, pico8_dir)
    if not ui.has_terminal() and not ui.ASSUME_YES:
        print(ui.dim("  run sync with --yes, or on a terminal, to add them"))
        return _rename(card, base, pico8_dir)
    scrape = " and scrape the new ones" if new and _has_login() else ""
    if not ui.confirm(f"Add these to {s3.location()}{scrape}?", default=True):
        return _rename(card, base, pico8_dir)
    with tempfile.TemporaryDirectory() as tmp:
        added, _, code = bbs.add_carts(todo, _fetch, tmp)
    if added:
        names.reset()  # the titles add_carts just wrote
        scraped = _scrape(added, system)
        _add_to_card(card, added)  # first: the carts are in storage, and a later run wouldn't add them as new
        if scraped == 130:
            raise KeyboardInterrupt
        code = (scraped and 1) or code
    return _rename(card, base, pico8_dir) or code
