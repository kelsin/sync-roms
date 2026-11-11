"""`sync-roms collections edit`: edit your own collections and save them to ~/.sync-roms/collections/."""
import copy

from . import collections as colls
from . import edit, m3u, picker, s3, store, surprise, themeart, ui
from .listedit import ask_category, game_label, reconcile, recategorize, view


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


PAST_SURPRISE_KEY = "p"
CLEAR_KEY = "c"
GAMES_HINT = "Space toggle · Enter done · / filter · w note · a all · p past · c clear"


# --- Editing the games of one collection -------------------------------------------------------------

def art_label(art_id):
    return themeart.art_choices().get(art_id, "none") if art_id else "none"


def pick_art(collection):
    """Let the user pick the collection's theme art (or none)."""
    choices = themeart.art_choices()
    ids = [None, *choices]
    current = ids.index(collection.get("art")) if collection.get("art") in ids else 0
    j = picker.filter_list(f"🎨 {collection['name']}: art in the Art Book Next theme (ES-DE, Knulli)",
                           ["None (the theme's default)", *choices.values()], cursor=current)
    if j is None:
        return
    if ids[j]:
        collection["art"] = ids[j]
    else:
        collection.pop("art", None)


def edit_one(collection, systems, keys_of):
    """Edit one collection: remove games, add games from a system, change categories, rename."""
    names = {s["bucket"]: s["name"] for s in systems}
    while True:
        i = picker.filter_list(f"✏️  {collection['name']} (Esc = back)",
                               [f"Games in this collection ({len(collection['games'])}): switch some off",
                                "Add games from a system", "Change a game's category", "Rename / change the description",
                                f"Theme art: {art_label(collection.get('art'))}"])
        if i is None:
            return
        shown = view(collection, systems)
        if i == 0:
            rows = edit.set_rows(collection, shown, lambda s: keys_of(s["bucket"]))
            if not rows:
                edit.note(ui.yellow("ℹ️  This collection has no games yet."))
                continue
            edit.toggle_games(f"✏️  {collection['name']} — ✅ in the collection, ⬜ remove it", rows)
            collection["games"] = reconcile(collection["games"], shown)
        elif i == 1:
            j = picker.filter_list("✏️  Add games from which system?", [s["name"] for s in systems])
            if j is None:
                continue
            s = shown[systems[j]["bucket"]]
            had = {g["bucket"] for g in s["games"]}
            all_rows, past = system_rows(s, keys_of(s["bucket"])), None
            while True:
                where = " · 🎁 past surprises only (c shows all)" if past is not None else ""
                pressed = edit.toggle_games(
                    f"✏️  {s['name']} — ✅ in {collection['name']}, ⬜ in storage only{where}",
                    [r for r in all_rows if past is None or r[1] in past],
                    hotkeys=(PAST_SURPRISE_KEY, CLEAR_KEY), hint=GAMES_HINT)
                if pressed == PAST_SURPRISE_KEY:
                    past = surprise.past_keys(s["bucket"]) or None
                    if past is None:
                        edit.note(ui.yellow(f"ℹ️  No past surprises on {s['name']}."))
                elif pressed == CLEAR_KEY:
                    past = None
                else:
                    break
            added = {g["bucket"] for g in s["games"]} - had
            category = ask_category(collection["games"], f"{len(added)} new game(s)") if added else ""
            collection["games"] = reconcile(collection["games"], shown, category)
            fold_discs(collection["games"], keys_of(s["bucket"]))
        elif i == 2:
            games = [g for g in collection["games"] if g.get("bucket")]
            j = picker.filter_list("✏️  Change which game's category?", [game_label(g, names) for g in games])
            if j is not None:
                recategorize(collection["games"], games[j], ask_category(collection["games"], games[j].get("title", "it")))
        elif i == 4:
            pick_art(collection)
        else:
            name = ui.ask(f"Name [{collection['name']}] (empty keeps it): ").strip()
            problem = colls.collection_problem(name, ()) if name else None
            if problem:
                edit.note(ui.yellow(f"  {problem}"))
                name = ""
            desc = ui.ask("Description (empty keeps it): ").strip()
            collection["name"] = name or collection["name"]  # the id never changes: cards reference it
            collection["description"] = desc or collection.get("description", "")


# --- The editor --------------------------------------------------------------------------------------

def cards_using(collection_id):
    """The names of the cards whose collections hold collection_id, sorted."""
    return sorted(name for name, card in store.load_cards().items()
                  if isinstance(card, dict) and isinstance(card.get("collections"), list)
                  and collection_id in card["collections"])


def new_collection(working):
    """Ask for a new collection's name and description and add it to working; returns its id, or None when cancelled."""
    while True:
        name = ui.ask("💖 Name for the new collection (empty to cancel): ").strip()
        if not name:
            return None
        problem = colls.collection_problem(name, working)
        if not problem:
            break
        print(ui.yellow(f"  {problem}"))
    cid = colls.slug(name)
    working[cid] = {"name": name, "description": ui.ask("   One-line description (optional): ").strip(), "games": []}
    return cid


def edit_collections():
    """Edit your collections, then save the changes locally. Returns the exit code."""
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    before = {c.pop("id"): c for c in colls.load_collections()}
    working = copy.deepcopy(before)
    listed = {}

    def keys_of(bucket):
        if bucket not in listed:
            print(ui.dim(f"📡 Listing {s3.location()}/{bucket}/ ..."))
            listed[bucket] = store.folder_keys(bucket)
        return listed[bucket]

    while True:
        ids = sorted(working, key=lambda x: working[x]["name"].lower())
        n = len(ids)
        changed = [cid for cid in ids if working[cid] != before.get(cid)]
        deleted = [cid for cid in before if cid not in working]
        labels = ([f"{working[x]['name']}  ({len(working[x]['games'])} games)" for x in ids]
                  + ["➕ New collection", "✅ Done (save)", "🚪 Quit without saving"])
        extras = [[("  " + ("new" if x not in before else "edited"), "cyan")] if x in changed else [] for x in ids] + [[], [], []]
        i = picker.filter_list("✏️  Which collection?  (Esc = save)", labels, extras=extras,
                               hotkeys=(edit.DELETE_KEY,), hint="/ filter · Enter open · d delete · Esc save")
        if isinstance(i, tuple):
            if i[1] < n:
                cid = ids[i[1]]
                names = cards_using(cid)
                if ui.confirm(f"🗑️  Delete collection {working[cid]['name']}?"
                              + (f" Cards {', '.join(names)} use it and lose it too." if names else ""), default=False):
                    del working[cid]
            continue
        if i is not None and i < n:
            edit_one(working[ids[i]], systems, keys_of)
            continue
        if i == n:
            cid = new_collection(working)
            if cid:
                edit_one(working[cid], systems, keys_of)
            continue
        if i == n + 2:
            if not (changed or deleted) or ui.confirm("Discard your pending changes and quit?", default=False):
                print(ui.yellow("👋 Quit without saving."))
                return 0
            continue
        if not (changed or deleted):
            print(ui.yellow("👋 No changes, nothing saved."))
            return 0
        empty = [working[cid]["name"] for cid in ids if not working[cid]["games"]]
        if empty:
            edit.note(ui.yellow(f"ℹ️  {', '.join(empty)} has no games. Add some or delete it first."))
            continue
        for cid in changed:
            colls.save_collection({"id": cid, **working[cid]})
        for cid in deleted:
            colls.delete_collection(cid)
            colls.remove_from_cards(cid)
        print(ui.green(f"💖 Saved to {colls.collections_dir()}"))
        return 0
