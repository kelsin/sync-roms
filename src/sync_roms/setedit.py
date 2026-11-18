"""`sync-roms sets edit`: edit the game sets in storage by hand and save the changes there."""
import copy

from . import cardedit, edit, picker, previews, s3, store, themeart, ui
from .listedit import add_from_set, ask_category, file_counts, fold_discs, game_label, insert_game, recategorize, reconcile, series_keys, set_series, stocked, system_rows, view


# --- Set files ---------------------------------------------------------------------------------------

def repo_sets():
    """The sets in storage as {id: {"name", "description", "games"}}."""
    return {game_set.pop("id"): game_set for game_set in store.set_files()}


set_text = store.set_text  # the format of a set's file lives in store


# --- Editing the games of one set --------------------------------------------------------------------

def edit_one(game_set, systems, keys_of):
    """Edit one set: remove games, add games from a system or another set, change categories, rename."""
    names = {s["bucket"]: s["name"] for s in systems}
    while True:
        label = f"{themeart.set_emoji(game_set)} {game_set['name']}"  # a rename below changes it
        i = picker.filter_list(f"✏️  {label} (Esc = back)",
                               [f"Games in this set ({len(game_set['games'])}): switch some off",
                                "Add games from a system", "Add games from a set", "Change a game's category",
                                "Set a game's series",
                                "Rename / change the description"])
        if i is None:
            return
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
                        hotkeys=(cardedit.SERIES_KEY, cardedit.CLEAR_KEY), hint=edit.GAMES_HINT + " · r series · c all",
                        filters=f"{series_filter} (c shows all)" if series_filter else "")
                    if pressed == cardedit.CLEAR_KEY:
                        series_filter = None
                    elif pressed == cardedit.SERIES_KEY:
                        series_filter = cardedit.pick_series(game_set, series_filter) or series_filter
                    else:
                        break
            finally:  # Ctrl-C too: the toggles made are kept (rows hidden by the series stay as they were)
                game_set["games"] = reconcile(game_set["games"], shown)
        elif i == 1:
            options = stocked(systems)
            j = picker.filter_list("✏️  Add games from which system?", [s["name"] for s in options], extras=file_counts(options),
                                 preview=lambda k: previews.system(options[k]) if k < len(options) else None)
            if j is None:
                continue
            s = shown[options[j]["bucket"]]
            had = {g["bucket"] for g in s["games"]}
            interrupted = False
            try:
                edit.toggle_games(f"✏️  {s['name']} — ✅ in {label}, ⬜ in storage only",
                                  system_rows(s, keys_of(s["bucket"])))
            except KeyboardInterrupt:  # Ctrl-C: the toggles made are kept, with no category
                interrupted = True
            added = {g["bucket"] for g in s["games"]} - had
            try:
                category = ask_category(game_set["games"], f"{len(added)} new game(s)") if added and not interrupted else ""
            except KeyboardInterrupt:  # Ctrl-C at the question: no category
                category, interrupted = "", True
            game_set["games"] = reconcile(game_set["games"], shown, category)
            fold_discs(game_set["games"], keys_of(s["bucket"]))
            if interrupted:
                raise KeyboardInterrupt
        elif i == 2:
            add_from_set(game_set, [x for x in store.load_sets() if x["name"] != game_set["name"]], shown, keys_of, label)
        elif i == 3:
            games = [g for g in game_set["games"] if g.get("bucket")]
            j = picker.filter_list("✏️  Change which game's category?", [game_label(g, names) for g in games],
                                preview=lambda k: previews.game_thumb(games[k]["bucket"]) if k < len(games) else None,
                                preview_width=previews.GAME_WIDTH)
            if j is not None:
                recategorize(game_set["games"], games[j], ask_category(game_set["games"], games[j].get("title", "it")))
        elif i == 4:
            games = [g for g in game_set["games"] if g.get("bucket")]
            j = picker.filter_list("✏️  Set which game's series?", [game_label(g, names) for g in games],
                                preview=lambda k: previews.game_thumb(games[k]["bucket"]) if k < len(games) else None,
                                preview_width=previews.GAME_WIDTH)
            if j is not None:
                known = list(dict.fromkeys([*(n if isinstance(n, str) else n.get("name", "") for n in store.repo_json("series")),
                                            *(g["series"] for g in game_set["games"] if g.get("series"))]))
                if known:
                    print(ui.dim(f"  Series: {', '.join(known)}"))
                typed = ui.ask(f"🎮 Series for {games[j].get('title', 'it')} (empty for none): ").strip()
                set_series(game_set["games"], games[j], next((n for n in known if n.casefold() == typed.casefold()), typed))
        else:
            name = ui.ask(f"Name [{game_set['name']}] (empty keeps it): ").strip()
            desc = ui.ask("Description (empty keeps it): ").strip()
            game_set["name"] = name or game_set["name"]
            game_set["description"] = desc or game_set.get("description", "")


# --- What changed ------------------------------------------------------------------------------------

def game_line(game):
    return f"{game.get('title') or game['bucket']} ({game['bucket']})"


def diff_sets(before, after):
    """[(kind, set id, [lines])] for every set that was created, removed or changed; kind is new, removed or changed."""
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
            found.append(("changed", sid, lines or ["edited"]))
    return found


def print_changes(found):
    print(ui.bold("\n📝 Changes"))
    for kind, sid, lines in found:
        print(ui.bold(f"  {sid}") + ui.dim(f"  ({kind})"))
        for line in lines:
            print((ui.green if line.startswith("+") else ui.red if line.startswith("-") else str)(f"    {line}"))


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
        sid = store.set_slug(name)
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
    before = repo_sets()
    working = copy.deepcopy(before)
    state = {"review": False, "fallback": store.sets_from_fallback()}
    while True:
        try:
            code = edit_working(systems, before, working, state)
        except KeyboardInterrupt:  # Ctrl-C: review the changes as Done does, then stop as before
            if state["review"] or not diff_sets(before, working):  # Ctrl-C at that review itself, or nothing to review
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
    listed = {}

    def keys_of(bucket):
        if bucket not in listed:
            print(ui.dim(f"📡 Listing {s3.location()}/{bucket}/ ..."))
            listed[bucket] = store.folder_keys(bucket)
        return listed[bucket]

    while True:
        ids = sorted(working, key=lambda x: working[x]["name"].lower())
        n = len(ids)
        found = diff_sets(before, working)
        edited = {sid for _, sid, _ in found}
        labels = ([f"{themeart.set_emoji(working[x])} {working[x]['name']}  ({len(working[x]['games'])} games)" for x in ids]
                  + ["➕ New set", "✅ Done (review & save)", "🚪 Quit without saving"])
        extras = [[("  " + ("new" if x not in before else "edited"), "cyan")] if x in edited else [] for x in ids] + [[], [], []]
        i = n + 1 if state["review"] else picker.filter_list("✏️  Which set?  (Esc = review & save)", labels, extras=extras,
                                                    hotkeys=(edit.DELETE_KEY,), hint="/ filter · Enter open · d delete · Esc review",
                                                    preview=lambda k: previews.collection(ids[k]) if k < n else None)
        if isinstance(i, tuple):
            if i[1] < n:
                sid = ids[i[1]]
                where = local_references(sid)
                note = f" Your {', '.join(where)} still reference(s) it." if where else ""
                if ui.confirm(f"🗑️  Delete set {themeart.set_emoji(working[sid])} {working[sid]['name']}?{note}", default=False):
                    del working[sid]
            continue
        if i is not None and i < n:
            edit_one(working[ids[i]], systems, keys_of)
            continue
        if i == n:
            sid = new_set(working)
            if sid:
                edit_one(working[sid], systems, keys_of)
            continue
        if i == n + 2:
            if not edited or ui.confirm("Discard your pending changes and quit?", default=False):
                edit.note(ui.yellow("👋 Quit without saving."))
                return 0
            continue
        if not found:
            edit.note(ui.yellow("👋 No changes, nothing saved."))
            return 0
        empty = [sid for kind, sid, _ in found if kind != "removed" and not working[sid]["games"]]
        if empty:
            edit.note(ui.yellow(f"ℹ️  {', '.join(empty)} has no games. Add some or delete it first."))
            state["review"] = False
            continue
        print_changes(found)
        answer = ui.choose("💾 Save these changes to storage?", "sed", "s", "s save · e keep editing · d discard")
        if answer == "e":
            state["review"] = False
            continue
        if answer == "d":
            edit.note(ui.yellow("👋 Not saved."))
            return None if state["review"] else 0
        try:
            save_sets(before, working, found, state["fallback"])
        except Stale as e:
            edit.note(ui.red(f"❌ {e}; nothing was saved. Quit and reopen the editor to start from storage's sets."))
            state["review"] = False
            continue
        except s3.ERRORS as e:  # e.g. an unmounted storage folder: back to the menu with what is left still pending
            edit.note(ui.red(f"❌ Couldn't save the sets to storage: {e}"))
            state["review"] = False
            continue
        saved = ui.green(f"💾 Saved {len(found)} set(s) to storage.")
        if not picker.queue_note(saved, keep=True):  # on the menu, and on the normal screen after the editor
            print(saved)
        return None if state["review"] else 0
