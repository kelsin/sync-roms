"""Games-list helpers shared by the tag and collection editors."""
from . import edit, inventory, m3u, picker, previews, s3, store, tags, tagui, ui


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


def reconcile(games, shown):
    """A games list's games after the toggler changed `shown` (a view): drop what was switched off, add what was switched on.

    Entries of systems that weren't shown, and untouched entries, are kept as they are."""
    now = {g["bucket"]: (s["bucket"], g) for s in shown.values() for g in s["games"]}
    out = [g for g in games if g.get("system") not in shown or not g.get("bucket") or g["bucket"] in now]
    have = {g.get("bucket") for g in out}
    for key, (system, g) in now.items():
        if key not in have:
            out.append({"title": g["title"], "system": system, "bucket": key,  # then the entry's other fields: a note, files
                        **{k: v for k, v in g.items() if k not in ("title", "system", "bucket")}})
    return out


ALL_SYSTEMS = "🌐 All systems"


def add_from_system(listing, systems, shown, keys_of, label, toggle=None, tag_filter=True, query="", hotkeys=(),
                    hint=None):
    """Pick one of systems with files in storage and toggle its games in listing (via shown, a view of it).
    label is listing's name as shown, with its emoji. Returns the hotkey that closed the games list, or None.

    toggle(s, title, rows) shows the system's rows (s is its entry in shown) instead of a plain edit.toggle_games.
    tag_filter=False: the games list ignores the sticky tag filter. query: no system is asked for: the all-systems list
    opens with that / filter. hotkeys/hint: the games list's own extra keys and hint, as edit.toggle_games takes them.
    New games get the discs of a multi-disc game whose playlist is in storage. Ctrl-C keeps the toggles made, then is
    raised again."""
    options = stocked(systems)
    j = 0 if query else picker.filter_list(
        "✏️  Add games from which system?", [ALL_SYSTEMS] + [s["name"] for s in options], extras=[[]] + file_counts(options),
        preview=lambda k: previews.system(options[k - 1]) if 0 < k <= len(options) else None)
    if j is None:
        return None
    everywhere = j == 0
    if everywhere:
        picked = options
        rows = all_rows(shown, options, keys_of)
        if not rows:
            edit.note(ui.yellow("ℹ️  No games in storage."))
            return None
        title = f"✏️  All systems — ✅ in {label}, ⬜ in storage only"
    else:
        s = shown[options[j - 1]["bucket"]]
        picked = [options[j - 1]]
        rows = system_rows(s, keys_of(s["bucket"]))
        title = f"✏️  {s['name']} — ✅ in {label}, ⬜ in storage only"
    place = {"keys": [r[1] for r in rows], "session": {"query": query}} if query else None
    interrupted, pressed = False, None
    try:
        if everywhere:
            pressed = toggle_all(title, rows, place, tag_filter, hotkeys, hint)
        elif toggle:
            toggle(s, title, rows)
        else:
            pressed = edit.toggle_games(title, rows, hotkeys=hotkeys, hint=hint, place=place, tag_filter=tag_filter)
    except KeyboardInterrupt:  # Ctrl-C in the list or a picker it opens: the toggles made are kept
        interrupted = True
    listing["games"] = reconcile(listing["games"], shown)
    for p in picked:
        fold_discs(listing["games"], keys_of(p["bucket"]))
    if interrupted:
        raise KeyboardInterrupt
    return pressed


def add_from_tag(listing, shown, keys_of, label, hotkeys=(), hint=None):
    """Pick one tag, set the tag filter to it while its games are listed (so nothing else hides them; the filter you
    had is put back when the list closes, Ctrl-C included), and toggle its games, across every system, in
    listing (via shown, a view of it). label is listing's name as shown, with its emoji. New games get their
    record's extra files (the discs of a multi-disc game). hotkeys/hint: the games list's own, as edit.toggle_games
    takes them; returns the hotkey that closed it, or None. Ctrl-C keeps the toggles made, then is raised again."""
    defs, records = tags.all_tags(), tags.load()["games"]
    if not defs:
        edit.note(ui.yellow("ℹ️  No tags yet."))
        return None
    ids = sorted(defs, key=lambda i: defs[i]["name"].casefold())
    games_of = {i: [k for k, rec in records.items() if i in rec["tags"]] for i in ids}
    j = picker.filter_list("✏️  Add games with which tag?",
                           [f"{defs[i]['emoji']} {defs[i]['name']}  ({len(games_of[i])} games)" for i in ids],
                           row_note=tagui.described(defs, ids))
    if j is None:
        return None
    tag = defs[ids[j]]
    games = [{"system": k.partition("/")[0], "bucket": k, **({"files": records[k]["files"]} if "files" in records[k] else {})}
             for k in games_of[ids[j]]]
    rows = edit.list_rows({"games": games}, shown, lambda s: keys_of(s["bucket"]))
    if not rows:
        edit.note(ui.yellow(f"ℹ️  {tag['emoji']} {tag['name']} has no games on known systems."))
        return None
    had = {g["bucket"] for s in shown.values() for g in s["games"]}
    interrupted, pressed = False, None
    saved = tagui.FILTER.state()
    tagui.FILTER.clear()
    tagui.FILTER.required.add(ids[j])
    try:
        pressed = edit.toggle_games(f"✏️  {tag['emoji']} {tag['name']} — ✅ in {label}, ⬜ not", rows, hotkeys=hotkeys,
                                    hint=hint)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        tagui.FILTER.restore(saved)
    added = {g["bucket"] for s in shown.values() for g in s["games"]} - had
    listing["games"] = reconcile(listing["games"], shown)
    files = {g["bucket"]: g["files"] for g in games if g.get("files")}
    for g in listing["games"]:
        if g.get("bucket") in added and g["bucket"] in files and "files" not in g:
            g["files"] = list(files[g["bucket"]])
    if interrupted:
        raise KeyboardInterrupt
    return pressed


def add_from_filter(listing, systems, shown, keys_of, label):
    """Add every game in storage the tag filter shows (a game once, by its lead key) that listing doesn't have yet,
    after a count confirm; asks for a filter first when none is set. New games get their record's extra files and a
    multi-disc game's discs."""
    if not tagui.FILTER.active():
        tagui.FILTER.pick(set(tags.load()["games"]))
        if not tagui.FILTER.active():
            return
    options = stocked(systems)
    had = {g["bucket"] for s in shown.values() for g in s["games"]}
    rows = [r for r in all_rows(shown, options, keys_of)
            if r[1] not in had and tags.owner(r[1]) == r[1] and tagui.FILTER.keep(r[1])]
    line = tagui.FILTER.describe()
    if not rows:
        edit.note(ui.yellow(f"ℹ️  No games in storage match {line} that {label} doesn't have."))
        return
    if not ui.confirm(f"✏️  Add {tagui.games(len(rows))} matching {line} to {label}?", default=False):
        return
    records = tags.load()["games"]
    for s, key, name, _ in rows:
        s["games"].append({"title": name, "bucket": key})
    listing["games"] = reconcile(listing["games"], shown)
    added = {r[1] for r in rows}
    for g in listing["games"]:
        if g.get("bucket") in added and "files" not in g and records.get(g["bucket"], {}).get("files"):
            g["files"] = list(records[g["bucket"]]["files"])
    for bucket in {s["bucket"] for s, *_ in rows}:
        fold_discs(listing["games"], keys_of(bucket))
    edit.note(f"✏️  Added {tagui.games(len(rows))} to {label}")


# --- What changed ------------------------------------------------------------------------------------

def game_line(game):
    return f"{game.get('title') or game['bucket']} ({game['bucket']})"


def diff_lists(before, after):
    """[(kind, id, [lines])] for every games list (a collection) that was created, removed or changed; kind is new,
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
            for k in new:
                if k not in old:
                    continue
                other = sorted(f for f in set(old[k]) | set(new[k]) if old[k].get(f) != new[k].get(f))
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


# --- The collections menu -------------------------------------------------------------------

def edit_menu(noun, before, working, state, emoji, art, delete_note, new_item, open_item, save, question, empty_ok=True):
    """The menu of the games lists in working ({id: list}, before as loaded) for the collection editor (noun);
    Done and Esc review the changes and ask question (save, keep editing or discard). state["review"] starts at that
    review and stays true until the user goes back to editing; when that review ends the editor, returns None.
    Returns the exit code.

    emoji(item) and art(item) of a list with its "id"; delete_note(id): what else deleting it does, as a sentence
    starting with a space (or ""); new_item(working) asks for a new list, adds it and returns its id (None when
    cancelled); open_item(item) edits one; save(found) saves the reviewed changes (diff_lists) and returns whether it
    did (False, its error noted, goes back to the menu). Without empty_ok, a list with no games can't be saved."""
    pos = 0
    while True:
        ids = sorted(working, key=lambda x: store.sort_key(working[x]["name"]))
        n = len(ids)
        found = diff_lists(before, working)
        edited = {x for _, x, _ in found}
        labels = ([f"{emoji({**working[x], 'id': x})} {working[x]['name']}  ({len(working[x]['games'])} games)" for x in ids]
                  + [f"➕ New {noun}", "✅ Done (review & save)", "🚪 Quit without saving"])
        extras = [[("  " + ("new" if x not in before else "edited"), "cyan")] if x in edited else [] for x in ids] + [[], [], []]
        i = n + 1 if state["review"] else picker.filter_list(f"✏️  Which {noun}?  (Esc = review & save)", labels, extras=extras,
                                                    hotkeys=(edit.DELETE_KEY, tagui.CLEAR_KEY), cursor=pos, filters=tagui.banner(),
                                                    hint=tagui.menu_hint("/ filter · Enter open · d delete · Esc review"),
                                                    preview=lambda k: previews.collection(art({**working[ids[k]], "id": ids[k]})) if k < n else None)
        if isinstance(i, tuple):
            pos = i[1] or 0
            if i[0] == tagui.CLEAR_KEY:
                tagui.handle_key(tagui.CLEAR_KEY, ())
            elif i[1] < n:
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
    return sorted(rows, key=lambda r: (store.sort_key(r[2]), names[r[0]["bucket"]]))


def toggle_all(title, rows, place=None, tag_filter=True, hotkeys=(), hint=None):
    """edit.toggle_games over rows from all_rows (s and c, the sticky tag filter, are its own). `a` toggles every shown
    game only while a tag filter is set: the unfiltered list is every file in storage. Returns the hotkey pressed."""
    return edit.toggle_games(title, rows, hotkeys=hotkeys, hint=hint, place=place, select_all=edit.WHEN_FILTERED,
                             tag_filter=tag_filter)
