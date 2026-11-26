"""`sync-roms collections edit`: edit your own collections and save them to ~/.sync-roms/collections/."""
import copy

from . import collections as colls
from . import cardedit, edit, names, picker, store, themeart, ui
from . import listedit
from .listedit import diff_lists, edit_menu, folder_lister, reconcile, view


ADD_KEY, ADD_ALIAS, SETTINGS_KEY = "A", "+", "S"  # + is a silent alias of A
GAMES_HINT = "Space toggle · Enter done · a all · m meta · p past"
GAMES_KEYS = [k for k in cardedit.GAMES_KEYS if k[0] != cardedit.VARIANT_KEY]  # what ? lists in a system's games list


# --- Editing the games of one collection -------------------------------------------------------------

def art_label(art_id):
    return themeart.art_choices().get(art_id, "none") if art_id else "none"


def pick_art(collection):
    """Let the user pick the collection's theme art (or none)."""
    choices = themeart.art_choices()
    ids = [None, *choices]
    current = ids.index(collection.get("art")) if collection.get("art") in ids else 0
    j = picker.filter_list(f"{themeart.art_emoji(collection.get('art'))} {collection['name']}: art in the Art Book Next theme (ES-DE, Knulli, ROCKNIX)",
                           [f"{themeart.art_emoji(None)} None (the theme's default)",
                            *(f"{themeart.art_emoji(i)} {label}" for i, label in choices.items())], cursor=current,
                           preview=lambda j: themeart.art_png(ids[j]) if ids[j] else None)
    if j is None:
        return
    if ids[j]:
        collection["art"] = ids[j]
    else:
        collection.pop("art", None)


CLEAR_KEY = "x"


def settings_menu(collection, others=()):
    """The collection's name, description and theme art; Esc returns. The art row shows the current picture. others:
    the ids of the other collections, which a new name can't collide with; x clears the description."""
    cursor = 0
    while True:
        rows = [f"Name: {collection['name']}", f"Description: {collection.get('description') or 'none'}",
                f"{themeart.art_emoji(collection.get('art'))} Theme art: {art_label(collection.get('art'))}"]
        i = picker.filter_list(f"{header(collection)}: settings (Esc = back)", rows, cursor=cursor,
                               preview=lambda j: themeart.art_png(collection.get("art")), hotkeys=(CLEAR_KEY,),
                               hint="Enter edit · x clear description · Esc back",
                               key_help=[("Enter", "edit the row"), (CLEAR_KEY, "clear the description"), ("Esc", "back")])
        if i is None:
            return
        if isinstance(i, tuple):
            cursor = i[1]
            if i[1] == 1:
                collection["description"] = ""
            continue
        cursor = i
        if i == 0:
            name = ui.ask(f"   Name ({collection['name']}; empty keeps it): ").strip()
            problem = colls.collection_problem(name, others) if name else None
            if problem:
                print(ui.yellow(f"  {problem}"))
            elif name:
                collection["name"] = name
        elif i == 1:
            desc = ui.ask("   One-line description (empty keeps it): ").strip()
            if desc:
                collection["description"] = desc
        else:
            pick_art(collection)


def toggle_filtered(s, title, rows):
    """edit.toggle_games over a system's rows (s is its entry in a view), narrowed by the card editor's game filters."""
    filters = cardedit.GameFilters(s)
    place = {}  # where the list was left, kept while a key lists the same games
    while True:
        shown = [r for r in rows if filters.keep(r[1])]
        pressed = edit.toggle_games(title, shown, hotkeys=cardedit.GameFilters.KEYS,
                                    hint=GAMES_HINT, key_help=GAMES_KEYS, place=place,
                                    filters=filters.describe(len(shown), len(rows)))
        if not filters.handle(pressed, [r[1] for r in rows], place):
            return


def header(collection):
    """The games list's title: emoji, name, description and theme art."""
    desc = f" — {collection['description']}" if collection.get("description") else ""
    return f"{themeart.collection_emoji(collection)} {collection['name']}{desc}  ·  art: {art_label(collection.get('art'))}"


def header_label(collection):
    return f"{themeart.collection_emoji(collection)} {collection['name']}"


def ordered(games, systems):
    """games sorted by title (as the list shows it), then system; games with no bucket key keep their place at the end."""
    sysname = {s["bucket"]: s["name"].lower() for s in systems}
    return sorted(games, key=lambda g: (not g.get("bucket"), store.sort_key(g.get("title") or names_title(g)),
                                        sysname.get(g.get("system"), "")))


def names_title(game):
    return names.title(game["bucket"]) if game.get("bucket") else ""


def restore(collection, originals, before, systems):
    """Put back the original entry (note, discs) of each game switched back on since `before`, then sort the games."""
    collection["games"] = ordered([originals.get(g["bucket"], g) if g.get("bucket") and g["bucket"] not in before else g
                                   for g in collection["games"]], systems)


def edit_one(collection, systems, keys_of, others=()):
    """Edit one collection: its games first (a game switched off stays listed, so it can be switched back on), with
    A to add games and S for its settings (others: the other collections' ids)."""
    kept = {}  # game key -> (system bucket, title, label) of every row listed, so removed games stay on the list
    originals = {}  # game key -> its entry in the collection, for a game switched back on after it was removed
    place = {}
    while True:
        shown = view(collection, systems)
        by_bucket = {s["bucket"]: s for s in shown.values()}
        for r in edit.list_rows(collection, shown, lambda s: keys_of(s["bucket"])):
            kept[r[1]] = (r[0]["bucket"], r[2], r[3])
        originals.update({g["bucket"]: g for g in collection["games"] if g.get("bucket")})
        rows = sorted(((by_bucket[b], key, title, label) for key, (b, title, label) in kept.items()),
                      key=lambda r: (store.sort_key(r[2]), r[0]["name"].lower()))
        before = {g.get("bucket") for g in collection["games"]}
        if not rows:  # nothing to list: the same actions as a menu
            i = picker.filter_list(f"{header(collection)} (Esc = back)", ["Add games", "Settings"])
            pressed = None if i is None else ADD_KEY if i == 0 else SETTINGS_KEY
            if pressed is None:
                return
        else:
            try:
                pressed = listedit.toggle_all(header(collection), rows, place, hotkeys=(ADD_KEY, ADD_ALIAS, SETTINGS_KEY),
                                              hint="A add games · S settings",
                                              key_help=[(f"{ADD_KEY} / {ADD_ALIAS}", "add games"), (SETTINGS_KEY, "settings")])
            finally:  # Ctrl-C too: the toggles made are kept
                collection["games"] = reconcile(collection["games"], shown)
                restore(collection, originals, before, systems)
            if pressed is None:
                return
        if pressed in (ADD_KEY, ADD_ALIAS):  # Ctrl-C in there keeps its toggles and is raised again
            before = {g.get("bucket") for g in collection["games"]}
            try:
                listedit.add_from_system(collection, systems, view(collection, systems), keys_of, header_label(collection),
                                         toggle=toggle_filtered)
            finally:
                restore(collection, originals, before, systems)
        elif pressed == SETTINGS_KEY:
            settings_menu(collection, others)


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
    cid = store.slug(name)
    working[cid] = {"name": name, "description": ui.ask("   One-line description (optional): ").strip(), "games": []}
    return cid


@picker.one_app
def edit_collections():
    """Edit your collections, then save the changes locally. Returns the exit code."""
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    before = {c.pop("id"): c for c in colls.load_collections()}
    for c in before.values():  # games are always kept by name, so a file in another order isn't a change
        c["games"] = ordered(c["games"], systems)
    working = copy.deepcopy(before)
    try:
        return edit_working(systems, before, working)
    except KeyboardInterrupt:  # Ctrl-C: offer to save the changes, then stop as before
        found = diff_lists(before, working)
        try:
            keep = bool(found) and ui.confirm("\n💾 Save your collection changes?", default=True)
        except KeyboardInterrupt:  # a second Ctrl-C discards
            keep = False
        if keep:
            save(working, found)
        elif found:
            print(ui.yellow("\n👋 Not saved."))
        raise


def save(working, found):
    """Write the new and changed collections in found (diff_lists) and remove the deleted ones (and their place on
    cards); returns True."""
    for kind, cid, _ in found:
        if kind == "removed":
            colls.delete_collection(cid)
            colls.remove_from_cards(cid)
        else:
            colls.save_collection({"id": cid, **working[cid]})
    edit.note(ui.green(f"💖 Saved to {colls.collections_dir()}"))
    return True


def edit_working(systems, before, working):
    """The collections menu over working; Done and Esc review it and save it locally. Returns the exit code."""
    keys_of = folder_lister()

    def delete_note(cid):
        names = cards_using(cid)
        return f" Cards {', '.join(names)} use it and lose it too." if names else ""

    return edit_menu("collection", before, working, {"review": False}, themeart.collection_emoji, lambda c: c.get("art"),
                     delete_note, new_collection, lambda collection: edit_one(collection, systems, keys_of, [x for x in working if working[x] is not collection]),
                     lambda found: save(working, found), "💾 Save these changes?")
