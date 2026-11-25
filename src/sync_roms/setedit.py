"""`sync-roms sets edit`: edit the game sets in storage by hand and save the changes there."""
import copy

from . import cardedit, edit, inventory, languages, picker, previews, runtime, s3, store, tagui, themeart, ui
from .listedit import add_from_set, add_from_system, ask_category, diff_lists, edit_menu, folder_lister, game_label, insert_game, pick_name, recategorize, reconcile, series_keys, series_of, set_series, view


# --- Set files ---------------------------------------------------------------------------------------

def repo_sets():
    """The sets in storage as {id: {"name", "description", "games"}}."""
    return {game_set.pop("id"): game_set for game_set in store.set_files()}


set_text = store.set_text  # the format of a set's file lives in store


# --- Editing the games of one set --------------------------------------------------------------------

SERIES_KEY = "r"
GAMES_HINT = "Space toggle · Enter done · w note · a all · o view · r series"
GAMES_KEYS = [tagui.KEY_HELP, (SERIES_KEY, "narrow to one series of games"), ("c", "clear the series filter")]  # what ? lists


def pick_series(game_set, current=None):
    """The series of the set's games picked from a list (with its game count), or None; notes when the set has none."""
    found = series_of(game_set)
    if not found:
        edit.note(ui.yellow(f"ℹ️  {game_set['name']} has no series."))
        return None
    labels = [f"{n}  ({c} games)" for n, c in found]
    i = picker.filter_list(f"🎮 Series in {game_set['name']}", labels,
                           cursor=next((j for j, (n, _) in enumerate(found) if n == current), 0))
    return None if i is None else found[i][0]


def pick_game(title, games, names):
    """Pick one of games from a list (its flag beside each); the index, or None on Esc."""
    return picker.filter_list(title, [game_label(g, names) for g in games],
                              extras=[[languages.column(g["bucket"])] for g in games],
                              **previews.game_pane([g["bucket"] for g in games]))


def edit_one(game_set, systems, keys_of):
    """Edit one set: remove games, add games from a system or another set, change categories, rename."""
    names = {s["bucket"]: s["name"] for s in systems}
    pos = 0
    while True:
        label = f"{themeart.set_emoji(game_set)} {game_set['name']}"  # a rename below changes it
        i = picker.filter_list(f"✏️  {label} (Esc = back)",
                               [f"Games in this set ({len(game_set['games'])}): switch some off",
                                "Add games from a system", "Add games from a set", "Change a game's category",
                                "Set a game's series",
                                "Rename / change the description"], cursor=pos)
        if i is None:
            return
        pos = i
        shown = view(game_set, systems)
        if i == 0:
            rows = edit.set_rows(game_set, shown, lambda s: keys_of(s["bucket"]))
            if not rows:
                edit.note(ui.yellow("ℹ️  This set has no games yet."))
                continue
            series_filter = None  # the series the list is narrowed to
            try:
                while True:
                    narrowed = [r for r in rows if r[1] in series_keys(game_set, series_filter)] if series_filter else rows
                    pressed = edit.toggle_games(
                        f"✏️  {label} — ✅ in the set, ⬜ remove it", narrowed,
                        hotkeys=(SERIES_KEY, cardedit.CLEAR_KEY), hint=GAMES_HINT,
                        key_help=GAMES_KEYS, filters=f"{series_filter} (c clear filters)" if series_filter else "")
                    if pressed == cardedit.CLEAR_KEY:
                        series_filter = None
                    elif pressed == SERIES_KEY:
                        series_filter = pick_series(game_set, series_filter) or series_filter
                    else:
                        break
            finally:  # Ctrl-C too: the toggles made are kept (rows hidden by the series stay as they were)
                game_set["games"] = reconcile(game_set["games"], shown)
        elif i == 1:
            add_from_system(game_set, systems, shown, keys_of, label)
        elif i == 2:
            add_from_set(game_set, [x for x in store.load_sets() if x["name"] != game_set["name"]], shown, keys_of, label)
        elif i == 3:
            games = [g for g in game_set["games"] if g.get("bucket")]
            j = pick_game("✏️  Change which game's category?", games, names)
            if j is not None:
                cats = list(dict.fromkeys(g["category"] for g in game_set["games"] if g.get("category")))
                picked = pick_name(f"🏷️  Category for {games[j].get('title', 'it')}", cats, games[j].get("category", ""),
                                   "category", games[j].get("title", "it"))
                if picked is not None:
                    recategorize(game_set["games"], games[j], picked)
        elif i == 4:
            games = [g for g in game_set["games"] if g.get("bucket")]
            j = pick_game("✏️  Set which game's series?", games, names)
            if j is not None:
                known = list(dict.fromkeys([*(n if isinstance(n, str) else n.get("name", "") for n in store.repo_json("series")),
                                            *(g["series"] for g in game_set["games"] if g.get("series"))]))
                picked = pick_name(f"🎮 Series for {games[j].get('title', 'it')}", known, games[j].get("series", ""),
                                   "series", games[j].get("title", "it"))
                if picked is not None:
                    set_series(game_set["games"], games[j], picked)
        else:
            name = ui.ask(f"Name [{game_set['name']}] (empty keeps it): ").strip()
            desc = ui.ask("Description (empty keeps it): ").strip()
            game_set["name"] = name or game_set["name"]
            game_set["description"] = desc or game_set.get("description", "")


# --- Saving -----------------------------------------------------------------------------------------

class Stale(Exception):
    """The sets the editor loaded may be older than storage's: nothing was saved."""


def save_sets(before, after, found, from_fallback=False):
    """Write the new and changed sets in found to storage and delete the removed ones, one at a time; before follows
    each one saved, so after a storage error (s3.ERRORS propagate) only what is left is still a change.

    Raises Stale, writing nothing, when the sets were read from the local copies (from_fallback) or a set in found no
    longer holds in storage what before has (another machine saved it meanwhile)."""
    if from_fallback:
        raise Stale("The sets were read from the local copies (storage couldn't be checked)")
    changed = [sid for _, sid, _ in found if store.set_changed(sid, before.get(sid))]
    added = [sid for sid in changed if sid not in before]
    if added:
        raise Stale(f"{', '.join(added)} already in storage (another machine added it; run `{inventory.UPDATE_HINT}` so "
                    "the editor lists it)")
    if changed:
        raise Stale(f"{', '.join(changed)} changed in storage since you opened the editor (another machine?)")
    for kind, sid, _ in found:
        if kind == "removed":
            store.delete_set(sid)
            del before[sid]
        else:
            store.write_set(sid, after[sid])
            before[sid] = copy.deepcopy(after[sid])


# --- The editor --------------------------------------------------------------------------------------

def local_references(set_id):
    """Where your own cards still use a set id."""
    found = [f"card {card}" for card in store.all_card_names() if set_id in store.list_sets(store.card_games(card))]
    return found


def new_set(working):
    """Ask for a new set's name and description and add it to working; returns its id, or None when cancelled."""
    while True:
        name = ui.ask("📦 Name for the new set (empty to cancel): ").strip()
        if not name:
            return None
        sid = store.slug(name)
        if not sid:
            print(ui.yellow("  A set needs a name with letters or digits."))
        elif sid in working:
            print(ui.yellow(f"  There is already a set with the id {sid}."))
        else:
            break
    working[sid] = {"name": name, "description": ui.ask("   One-line description (optional): ").strip(), "games": []}
    return sid


@picker.one_app
def edit_sets():
    """Edit the sets in storage, then save the changes there. Returns the exit code."""
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    store.reset_sets()  # storage's sets as they are now, not as an earlier part of this run read them
    before = repo_sets()
    working = copy.deepcopy(before)
    state = {"review": False, "fallback": store.sets_from_fallback()}
    while True:
        try:
            code = edit_working(systems, before, working, state)
        except KeyboardInterrupt:  # Ctrl-C: review the changes as Done does, then stop as before
            if state["review"] or not diff_lists(before, working):  # Ctrl-C at that review itself, or nothing to review
                raise
            print(ui.yellow("\n🛑 Interrupted — review your changes before leaving."))
            state["review"] = True
            continue
        if code is None:  # the review after a Ctrl-C ended the editor
            raise KeyboardInterrupt
        return code


def edit_working(systems, before, working, state):
    """The sets menu over working; Done reviews it and saves it to storage. state["review"] starts at that review and stays
    true until the user goes back to editing; when that review ends the editor, returns None. Returns the exit code."""
    keys_of = folder_lister()

    def delete_note(sid):
        where = local_references(sid)
        return f" Your {', '.join(where)} still reference(s) it." if where else ""

    def save(found):
        try:
            save_sets(before, working, found, state["fallback"])
        except Stale as e:
            edit.note(ui.red(f"❌ {e}; nothing was saved. Quit and reopen the sets editor: it starts from storage's sets."))
            return False
        except SystemExit:  # ui.fail, e.g. no write profile: its error is printed; the edits stay pending
            need = "" if runtime.ROOT else f" (saving needs the write profile {runtime.WRITE_PROFILE!r})"
            edit.note(ui.red(f"❌ Couldn't save the sets to storage{need}: see the error above. Nothing more was saved."))
            return False
        except s3.ERRORS as e:  # e.g. an unmounted storage folder: back to the menu with what is left still pending
            edit.note(ui.red(f"❌ Couldn't save the sets to storage: {e}"))
            return False
        saved = ui.green(f"💾 Saved {len(found)} set(s) to storage.")
        if not picker.queue_note(saved, keep=True):  # on the menu, and on the normal screen after the editor
            print(saved)
        return True

    return edit_menu("set", before, working, state, themeart.set_emoji, themeart.set_art, delete_note, new_set,
                     lambda game_set: edit_one(game_set, systems, keys_of), save, "💾 Save these changes to storage?",
                     empty_ok=False)
