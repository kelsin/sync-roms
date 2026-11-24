"""Games-list helpers shared by the set and collection editors."""
from . import edit, inventory, m3u, picker, previews, s3, store, themeart, ui


# --- Multi-disc games --------------------------------------------------------------------------------

def playlist_groups(in_storage):
    """{.m3u key: its game's keys, playlist first} for the multi-disc games whose playlist is in storage."""
    return {group[0]: group for group in m3u.file_groups(in_storage).values()
            if group[0].lower().endswith(".m3u") and group[0] in in_storage}


def system_rows(entry, in_storage):
    """edit.system_rows without the discs of multi-disc games that have a playlist: the playlist is the game's row."""
    discs = {k for group in playlist_groups(in_storage).values() for k in group[1:]}
    return [row for row in edit.system_rows(entry, in_storage) if row[1] not in discs]


def fold_discs(games, in_storage):
    """Give each game whose bucket is a playlist in storage, and that has no files yet, its discs as files."""
    groups = playlist_groups(in_storage)
    for g in games:
        if g.get("bucket") in groups and "files" not in g:
            g["files"] = groups[g["bucket"]][1:]


def view(listing, systems):
    """A games list's games per known system, shaped like a card's games so the toggler can edit them."""
    return {s["bucket"]: {"bucket": s["bucket"], "name": s["name"], "full_system": False,
                          "games": [g for g in listing["games"] if g.get("system") == s["bucket"] and g.get("bucket")]}
            for s in systems}


def stocked(systems):
    """The systems with files in storage, to add games from, by company then name like the card editor: a missing or
    empty folder has nothing to add. All of them when storage can't be reached and nothing is cached."""
    try:
        with ui.silent_thread():
            folders = inventory.folders()
    except (*s3.ERRORS, SystemExit):  # storage can't be reached (ui.fail raises SystemExit): go by the cache alone
        folders = None
    return sorted((s for s in systems if (folders is None or s["bucket"] in folders)
                   and inventory.cached(f"{s['bucket']}/") != {}), key=store.system_sort_key)


def folder_lister():
    """keys_of(bucket): store.folder_keys of a system's folder, listed once per bucket."""
    listed = {}

    def keys_of(bucket):
        if bucket not in listed:
            listed[bucket] = store.folder_keys(bucket)
        return listed[bucket]
    return keys_of


def file_counts(systems):
    """Per system, its file count in storage as filter_list extras; none without a storage cache (counting would list
    every folder)."""
    out = []
    for s in systems:
        n = sum(not k.endswith("/") for k in inventory.cached(f"{s['bucket']}/") or {})
        out.append([(f"  {n} file" + ("" if n == 1 else "s"), "dim")] if n else [])
    return out


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
                              "system": system, "bucket": key,  # then the entry's other fields: a note, files
                              **{k: v for k, v in g.items() if k not in ("title", "category", "system", "bucket")}})
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


def set_series(games, game, series):
    """Give game a series (empty removes it), keeping it after the title and category; returns game."""
    moved = {}
    for k, v in game.items():
        if k != "series":
            moved[k] = v
        if series and k == ("category" if "category" in game else "title"):
            moved["series"] = series
    game.clear()
    game.update(moved)
    return game


def series_of(game_set, min_games=2):
    """[(series, game count)] of a set's games in file order of first appearance, leaving out series with fewer than
    min_games games."""
    counts = {}
    for g in game_set["games"]:
        if g.get("series"):
            counts[g["series"]] = counts.get(g["series"], 0) + 1
    return [(name, n) for name, n in counts.items() if n >= min_games]


def series_keys(game_set, series):
    """The bucket keys (with each game's files) of the set's games in series."""
    return {k for g in game_set["games"] if g.get("series") == series for k in [g["bucket"], *g.get("files", [])]}


def pick_name(title, names, current, noun, what):
    """Pick a name from a list: "" for none (first row), a known name, or a new one typed (last row); None when
    cancelled (an empty new name too). The cursor starts on current."""
    i = picker.filter_list(title, ["(none)", *names, "new…"], hint="Enter pick · Esc cancel",
                           cursor=next((n + 1 for n, x in enumerate(names) if x.casefold() == (current or "").casefold()), 0))
    if i is None:
        return None
    if i == 0:
        return ""
    if i <= len(names):
        return names[i - 1]
    typed = ui.ask(f"🏷️  New {noun} for {what}: ", cancellable=True)
    typed = (typed or "").strip()
    if not typed:
        return None
    return next((n for n in names if n.casefold() == typed.casefold()), typed)  # "cave" is the existing "Cave"


def ask_category(games, what):
    """The category typed for what, "" for none."""
    cats = list(dict.fromkeys(g["category"] for g in games if g.get("category")))
    if cats:
        print(ui.dim(f"  Categories: {', '.join(cats)}"))
    typed = ui.ask(f"🏷️  Category for {what} (empty for none): ").strip()
    return next((c for c in cats if c.casefold() == typed.casefold()), typed)  # "cave" is the existing "Cave"


def game_label(game, names):
    """A game's row label; names: {system bucket: system name}."""
    return f"{game.get('category') + ' — ' if game.get('category') else ''}{names.get(game.get('system'), game.get('system'))}" \
           f" — {game.get('title') or game['bucket']}"


ALL_SYSTEMS = "🌐 All systems"


def add_from_system(listing, systems, shown, keys_of, label, categories=True, toggle=None):
    """Pick one of systems with files in storage and toggle its games in listing (via shown, a view of it).
    label is listing's name as shown, with its emoji.

    toggle(s, title, rows) shows the system's rows (s is its entry in shown) instead of a plain edit.toggle_games.
    New games get the category asked for when categories is true (none after Ctrl-C, which keeps the toggles made and
    is then raised again), and the discs of a multi-disc game whose playlist is in storage."""
    options = stocked(systems)
    j = picker.filter_list("✏️  Add games from which system?", [ALL_SYSTEMS] + [s["name"] for s in options],
                           extras=[[]] + file_counts(options),
                           preview=lambda k: previews.system(options[k - 1]) if 0 < k <= len(options) else None)
    if j is None:
        return
    everywhere = j == 0
    if everywhere:
        picked = options
        rows = all_rows(shown, options, keys_of)
        if not rows:
            edit.note(ui.yellow("ℹ️  No games in storage."))
            return
        title = f"✏️  All systems — ✅ in {label}, ⬜ in storage only"
    else:
        s = shown[options[j - 1]["bucket"]]
        picked = [options[j - 1]]
        rows = system_rows(s, keys_of(s["bucket"]))
        title = f"✏️  {s['name']} — ✅ in {label}, ⬜ in storage only"
    had = {g["bucket"] for p in picked for g in shown[p["bucket"]]["games"]}
    interrupted = False
    try:
        if everywhere:
            toggle_all(title, rows, store.load_sets())
        elif toggle:
            toggle(s, title, rows)
        else:
            edit.toggle_games(title, rows)
    except KeyboardInterrupt:  # Ctrl-C in the list or a picker it opens: the toggles made are kept, with no category
        interrupted = True
    added = {g["bucket"] for p in picked for g in shown[p["bucket"]]["games"]} - had
    try:
        category = ask_category(listing["games"], f"{len(added)} new game(s)") if categories and added and not interrupted else ""
    except KeyboardInterrupt:  # Ctrl-C at the question: no category
        category, interrupted = "", True
    listing["games"] = reconcile(listing["games"], shown, category)
    for p in picked:
        fold_discs(listing["games"], keys_of(p["bucket"]))
    if interrupted:
        raise KeyboardInterrupt


def add_from_set(listing, sets, shown, keys_of, label, categories=True):
    """Pick one of sets and toggle its games, across every system, in listing (via shown, a view of it).
    label is listing's name as shown, with its emoji.

    New games get the category asked for when categories is true (none after Ctrl-C, which keeps the toggles made and
    is then raised again), and the set's extra files (the discs of a multi-disc game)."""
    j = picker.filter_list("✏️  Add games from which set?", [f"{themeart.set_emoji(x)} {x['name']}  ({len(x['games'])} games)" for x in sets],
                           preview=lambda k: previews.collection(themeart.set_art(sets[k])))
    if j is None:
        return
    chosen = sets[j]
    rows = edit.set_rows(chosen, shown, lambda s: keys_of(s["bucket"]))
    if not rows:
        edit.note(ui.yellow(f"ℹ️  {themeart.set_emoji(chosen)} {chosen['name']} has no games on known systems."))
        return
    had = {g["bucket"] for s in shown.values() for g in s["games"]}
    interrupted = False
    try:
        edit.toggle_games(f"✏️  {themeart.set_emoji(chosen)} {chosen['name']} — ✅ in {label}, ⬜ not", rows)
    except KeyboardInterrupt:
        interrupted = True
    added = {g["bucket"] for s in shown.values() for g in s["games"]} - had
    try:
        category = ask_category(listing["games"], f"{len(added)} new game(s)") if categories and added and not interrupted else ""
    except KeyboardInterrupt:  # Ctrl-C at the question: no category
        category, interrupted = "", True
    listing["games"] = reconcile(listing["games"], shown, category)
    files = {g["bucket"]: g["files"] for g in chosen["games"] if g.get("bucket") and g.get("files")}
    for g in listing["games"]:
        if g.get("bucket") in added and g["bucket"] in files and "files" not in g:
            g["files"] = list(files[g["bucket"]])
    if interrupted:
        raise KeyboardInterrupt


# --- What changed ------------------------------------------------------------------------------------

def game_line(game):
    return f"{game.get('title') or game['bucket']} ({game['bucket']})"


def diff_lists(before, after):
    """[(kind, id, [lines])] for every games list (set or collection) that was created, removed or changed; kind is new,
    removed or changed."""
    found = []
    for sid in sorted(set(before) | set(after)):
        a, b = before.get(sid), after.get(sid)
        if a is None:
            found.append(("new", sid, [f"+ {game_line(g)}" for g in b["games"] if g.get("bucket")]))
        elif b is None:
            found.append(("removed", sid, [f"{len(a['games'])} game(s)"]))
        elif a != b:
            lines = [f"name: {a['name']} → {b['name']}"] if a["name"] != b["name"] else []
            if a.get("description", "") != b.get("description", ""):
                lines.append("description changed")
            old = {g["bucket"]: g for g in a["games"] if g.get("bucket")}
            new = {g["bucket"]: g for g in b["games"] if g.get("bucket")}
            lines += [f"+ {game_line(new[k])}" for k in new if k not in old]
            lines += [f"- {game_line(old[k])}" for k in old if k not in new]
            lines += [f"~ {game_line(new[k])}: category {old[k].get('category') or 'none'} → {new[k].get('category') or 'none'}"
                      for k in new if k in old and (old[k].get("category") or "") != (new[k].get("category") or "")]
            for k in new:
                if k not in old:
                    continue
                if (old[k].get("series") or "") != (new[k].get("series") or ""):
                    lines.append(f"~ {game_line(new[k])}: series {old[k].get('series') or 'none'} → {new[k].get('series') or 'none'}")
                other = sorted(f for f in set(old[k]) | set(new[k])
                               if f not in ("category", "series") and old[k].get(f) != new[k].get(f))
                if other:
                    lines.append(f"~ {game_line(new[k])}: {', '.join(other)} changed")
            if not lines and [g["bucket"] for g in a["games"] if g.get("bucket")] != [g["bucket"] for g in b["games"] if g.get("bucket")]:
                lines.append("order changed")
            found.append(("changed", sid, lines or ["edited"]))
    return found


def print_changes(found):
    print(ui.bold("\n📝 Changes"))
    for kind, sid, lines in found:
        print(ui.bold(f"  {sid}") + ui.dim(f"  ({kind})"))
        for line in lines:
            print((ui.green if line.startswith("+") else ui.red if line.startswith("-") else str)(f"    {line}"))


# --- The sets and collections menu -------------------------------------------------------------------

def edit_menu(noun, before, working, state, emoji, art, delete_note, new_item, open_item, save, question, empty_ok=True):
    """The menu of the games lists in working ({id: list}, before as loaded) for the set or collection editor (noun);
    Done and Esc review the changes and ask question (save, keep editing or discard). state["review"] starts at that
    review and stays true until the user goes back to editing; when that review ends the editor, returns None.
    Returns the exit code.

    emoji(item) and art(item) of a list with its "id"; delete_note(id): what else deleting it does, as a sentence
    starting with a space (or ""); new_item(working) asks for a new list, adds it and returns its id (None when
    cancelled); open_item(item) edits one; save(found) saves the reviewed changes (diff_lists) and returns whether it
    did (False, its error noted, goes back to the menu). Without empty_ok, a list with no games can't be saved."""
    pos = 0
    while True:
        ids = sorted(working, key=lambda x: working[x]["name"].lower())
        n = len(ids)
        found = diff_lists(before, working)
        edited = {x for _, x, _ in found}
        labels = ([f"{emoji({**working[x], 'id': x})} {working[x]['name']}  ({len(working[x]['games'])} games)" for x in ids]
                  + [f"➕ New {noun}", "✅ Done (review & save)", "🚪 Quit without saving"])
        extras = [[("  " + ("new" if x not in before else "edited"), "cyan")] if x in edited else [] for x in ids] + [[], [], []]
        i = n + 1 if state["review"] else picker.filter_list(f"✏️  Which {noun}?  (Esc = review & save)", labels, extras=extras,
                                                    hotkeys=(edit.DELETE_KEY,), hint="/ filter · Enter open · d delete · Esc review", cursor=pos,
                                                    preview=lambda k: previews.collection(art({**working[ids[k]], "id": ids[k]})) if k < n else None)
        if isinstance(i, tuple):
            pos = i[1]
            if i[1] < n:
                x = ids[i[1]]
                if ui.confirm(f"🗑️  Delete {noun} {emoji({**working[x], 'id': x})} {working[x]['name']}?{delete_note(x)}", default=False):
                    del working[x]
            continue
        if i is not None and i < n:
            pos = i
            open_item(working[ids[i]])
            continue
        if i == n:
            pos = i
            x = new_item(working)
            if x:
                open_item(working[x])
            continue
        if i == n + 2:
            if not edited or ui.confirm("Discard your pending changes and quit?", default=False):
                edit.note(ui.yellow("👋 Quit without saving."))
                return 0
            continue
        if not found:
            edit.note(ui.yellow("👋 No changes, nothing saved."))
            return 0
        empty = [] if empty_ok else [x for kind, x, _ in found if kind != "removed" and not working[x]["games"]]
        if empty:
            edit.note(ui.yellow(f"ℹ️  {', '.join(empty)} has no games. Add some or delete it first."))
            state["review"] = False
            continue
        print_changes(found)
        answer = ui.choose(question, "sed", "s", "s save · e keep editing · d discard", esc="e")
        if answer == "e":
            state["review"] = False
            continue
        if answer == "d":
            edit.note(ui.yellow("👋 Not saved."))
            return None if state["review"] else 0
        if not save(found):
            state["review"] = False
            continue
        return None if state["review"] else 0


# --- All systems at once -----------------------------------------------------------------------------

def all_rows(shown, systems, keys_of):
    """Rows for edit.toggle_games over every system's files, by title then system. Each row's entry is the system's
    view in shown, so toggles write into it; labels start with the system's name."""
    rows = []
    for system in systems:
        s = shown[system["bucket"]]
        rows += [(s, key, title, f"{system['name']} — {label}")
                 for _, key, title, label in system_rows(s, keys_of(system["bucket"]))]
    names = {s["bucket"]: s["name"].lower() for s in systems}
    return sorted(rows, key=lambda r: (r[2].lower(), names[r[0]["bucket"]]))


def pick_row_set(sets, row_keys, current=None):
    """A set with a game among row_keys, picked from a list; None when none is picked or no set has one."""
    shown = [(x, n) for x in sets for n in [sum(g["bucket"] in row_keys for g in store.set_games(x))] if n]
    if not shown:
        edit.note(ui.yellow("ℹ️  No set has games among these."))
        return None
    i = picker.filter_list("Narrow to a set", [f"{themeart.set_emoji(x)} {x['name']}  ({n} games)" for x, n in shown],
                           cursor=next((j for j, (x, _) in enumerate(shown) if x["name"] == current), 0))
    return None if i is None else shown[i][0]


def toggle_all(title, rows, sets, place=None):
    """edit.toggle_games over rows from all_rows, with s narrowing to a set and c clearing that and the / filter."""
    from . import cardedit  # cardedit imports this module
    chosen = None
    place = {} if place is None else place
    key_help = [(cardedit.SET_KEY, "narrow to a set"), (cardedit.CLEAR_KEY, "clear filters")]
    while True:
        keep = {g["bucket"] for g in store.set_games(chosen)} if chosen else None
        pressed = edit.toggle_games(
            title, [r for r in rows if keep is None or r[1] in keep],
            hotkeys=(cardedit.SET_KEY, cardedit.CLEAR_KEY),
            hint="Space toggle · Enter done · s set · c clear filters", key_help=key_help, place=place, select_all=False,
            filters=f"{themeart.set_emoji(chosen)} {chosen['name']} only (c clear filters)" if chosen else "")
        if pressed == cardedit.CLEAR_KEY:
            chosen = None
            place.get("session", {}).pop("query", None)
        elif pressed == cardedit.SET_KEY:
            chosen = pick_row_set(sets, {r[1] for r in rows}, chosen and chosen["name"]) or chosen
        else:
            return
