"""Games-list helpers shared by the set and collection editors."""
from . import edit, inventory, picker, previews, s3, ui


def view(listing, systems):
    """A games list's games per known system, shaped like a card's games so the toggler can edit them."""
    return {s["bucket"]: {"bucket": s["bucket"], "name": s["name"], "full_system": False,
                          "games": [g for g in listing["games"] if g.get("system") == s["bucket"] and g.get("bucket")]}
            for s in systems}


def stocked(systems):
    """The systems with files in storage, to add games from: a missing or empty folder has nothing to add.
    All of them when storage can't be reached and nothing is cached."""
    try:
        with ui.silent_thread():
            folders = inventory.folders()
    except (*s3.ERRORS, SystemExit):  # storage can't be reached (ui.fail raises SystemExit): go by the cache alone
        folders = None
    return [s for s in systems
            if (folders is None or s["bucket"] in folders) and inventory.cached(f"{s['bucket']}/") != {}]


def insert_game(games, game):
    """Add game after the last game of its category, or at the end when its category is new (or it has none)."""
    cat = game.get("category")
    last = max((i for i, x in enumerate(games) if cat and x.get("category") == cat), default=len(games) - 1)
    games.insert(last + 1, game)


def reconcile(games, shown, category=""):
    """A games list's games after the toggler changed `shown` (a view): drop what was switched off, add what was switched on.

    Entries of systems that weren't shown, and untouched entries, are kept as they are."""
    now = {g["bucket"]: (s["bucket"], g) for s in shown.values() for g in s["games"]}
    out = [g for g in games if g.get("system") not in shown or not g.get("bucket") or g["bucket"] in now]
    have = {g.get("bucket") for g in out}
    for key, (system, g) in now.items():
        if key not in have:
            insert_game(out, {"title": g["title"], **({"category": category} if category else {}),
                              "system": system, "bucket": key})
    return out


def recategorize(games, game, category):
    """Give game a new category (empty removes it) and move it next to the games of that category."""
    if (game.get("category") or "") == category:
        return
    moved = {}
    for k, v in game.items():
        if k != "category":
            moved[k] = v
        if k == "title" and category:
            moved["category"] = category
    if category:
        moved.setdefault("category", category)
    games[:] = [x for x in games if x is not game]
    insert_game(games, moved)


def ask_category(games, what):
    cats = list(dict.fromkeys(g["category"] for g in games if g.get("category")))
    if cats:
        print(ui.dim(f"  Categories: {', '.join(cats)}"))
    typed = ui.ask(f"🏷️  Category for {what} (empty for none): ").strip()
    return next((c for c in cats if c.casefold() == typed.casefold()), typed)  # "cave" is the existing "Cave"


def game_label(game, names):
    """A game's row label; names: {system bucket: system name}."""
    return f"{game.get('category') + ' — ' if game.get('category') else ''}{names.get(game.get('system'), game.get('system'))}" \
           f" — {game.get('title') or game['bucket']}"


def add_from_set(listing, sets, shown, keys_of):
    """Pick one of sets and toggle its games, across every system, in listing (via shown, a view of it).

    New games get the category asked for, and the set's extra files (the discs of a multi-disc game)."""
    j = picker.filter_list("✏️  Add games from which set?", [f"{x['name']}  ({len(x['games'])} games)" for x in sets],
                           preview=lambda k: previews.collection(sets[k]["id"]))
    if j is None:
        return
    chosen = sets[j]
    rows = edit.set_rows(chosen, shown, lambda s: keys_of(s["bucket"]))
    if not rows:
        edit.note(ui.yellow(f"ℹ️  {chosen['name']} has no games on known systems."))
        return
    had = {g["bucket"] for s in shown.values() for g in s["games"]}
    edit.toggle_games(f"✏️  {chosen['name']} — ✅ in {listing['name']}, ⬜ not", rows)
    added = {g["bucket"] for s in shown.values() for g in s["games"]} - had
    category = ask_category(listing["games"], f"{len(added)} new game(s)") if added else ""
    listing["games"] = reconcile(listing["games"], shown, category)
    files = {g["bucket"]: g["files"] for g in chosen["games"] if g.get("bucket") and g.get("files")}
    for g in listing["games"]:
        if g.get("bucket") in added and g["bucket"] in files and "files" not in g:
            g["files"] = list(files[g["bucket"]])
