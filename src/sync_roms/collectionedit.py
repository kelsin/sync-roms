"""`sync-roms collections edit`: edit your own collections and save them to ~/.sync-roms/collections/."""
import copy

from . import collections as colls
from . import cardedit, edit, picker, store, themeart, ui
from .listedit import add_from_system, add_from_tag, diff_lists, edit_menu, folder_lister, reconcile, view


GAMES_HINT = "Space toggle · Enter done · a all · s tag · m meta · c clear · p past"
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


def toggle_filtered(s, title, rows):
    """edit.toggle_games over a system's rows (s is its entry in a view), narrowed by the card editor's game filters."""
    filters = cardedit.GameFilters(s)
    place = {}  # where the list was left, kept while a key lists the same games
    while True:
        pressed = edit.toggle_games(title, [r for r in rows if filters.keep(r[1])], hotkeys=cardedit.GameFilters.KEYS,
                                    hint=GAMES_HINT, key_help=GAMES_KEYS, place=place,
                                    filters=filters.describe())
        if not filters.handle(pressed, [r[1] for r in rows], place):
            return


def edit_one(collection, systems, keys_of):
    """Edit one collection: remove games, add games from a system or a tag, rename."""
    pos = 0
    while True:
        label = f"{themeart.collection_emoji(collection)} {collection['name']}"  # the art may change below
        i = picker.filter_list(f"{label} (Esc = back)",
                               [f"Games in this collection ({len(collection['games'])}): switch some off",
                                "Add games from a system", "Add games from a tag", "Rename / change the description",
                                f"{themeart.art_emoji(collection.get('art'))} Theme art: {art_label(collection.get('art'))}"], cursor=pos)
        if i is None:
            return
        pos = i
        shown = view(collection, systems)
        if i == 0:
            rows = edit.set_rows(collection, shown, lambda s: keys_of(s["bucket"]))
            if not rows:
                edit.note(ui.yellow("ℹ️  This collection has no games yet."))
                continue
            try:
                edit.toggle_games(f"✏️  {label} — ✅ in the collection, ⬜ remove it", rows)
            finally:  # Ctrl-C too: the toggles made are kept
                collection["games"] = reconcile(collection["games"], shown)
        elif i == 1:
            add_from_system(collection, systems, shown, keys_of, label, categories=False, toggle=toggle_filtered)
        elif i == 2:
            add_from_tag(collection, shown, keys_of, label)
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
    cid = store.slug(name)
    working[cid] = {"name": name, "description": ui.ask("   One-line description (optional): ").strip(), "games": []}
    return cid


@picker.one_app
def edit_collections():
    """Edit your collections, then save the changes locally. Returns the exit code."""
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    before = {c.pop("id"): c for c in colls.load_collections()}
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
                     delete_note, new_collection, lambda collection: edit_one(collection, systems, keys_of),
                     lambda found: save(working, found), "💾 Save these changes?")
