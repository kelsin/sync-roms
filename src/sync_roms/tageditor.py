"""`sync-roms tags edit`: edit the tags in storage. Every change is saved as it is made."""
from . import edit, names, picker, s3, store, tags, tagui, ui
from .listedit import add_from_system, add_from_tag, folder_lister, view


SORT_KEY = "o"
ADD_KEY, ADD_ALIAS, SETTINGS_KEY = "A", "+", "S"  # in a tag's games, as in the collection editor; + is a silent alias of A
CLEAR_KEY = "x"  # in a tag's settings: clear its description
QUIT_KEY = "Q"  # in a tag's games, its settings and its add lists: leave the editor, what was toggled saved
QUIT_HINT = "Q quit the editor"
ADD_HINT = f"{edit.GAMES_HINT} · {QUIT_HINT}"  # the hint of the tag's add lists
GAMES_HINT = f"{edit.GAMES_HINT} · A add games · S settings · {QUIT_HINT}"  # the tag's own games
GAMES_HELP = [(f"{ADD_KEY} / {ADD_ALIAS}", "add games"), (SETTINGS_KEY, "settings"), (QUIT_KEY, "quit the editor")]


class Quit(Exception):
    """Q: leave the tag editor at once (and, under `sync-roms edit`, go to its review); every change is already saved."""


def _label(tag):
    return f"{tag['emoji']} {tag['name']}"


def _games_of(tag_id):
    """The keys of the games with the tag."""
    return [k for k, rec in tags.load()["games"].items() if tag_id in rec["tags"]]


def _save(write, *args, **kwargs):
    """write(*args, **kwargs) to storage; False, with a note, when storage refused it."""
    try:
        write(*args, **kwargs)
    except (*s3.ERRORS, SystemExit, ValueError) as e:  # ui.fail exits, its error printed; ValueError: bad JSON, gone tag
        edit.note(ui.yellow(f"⚠️  Couldn't save the tags in storage: {e}"))
        return False
    return True


# --- One tag -----------------------------------------------------------------------------------------

def add_games(tag_id, systems, keys_of, add):
    """add(listing, shown) lets the user toggle games into a listing of the tag's games (shown is a view of it); the
    games it gained get the tag, and those it lost lose it (saved even after Ctrl-C). Returns what add returned."""
    keys = _games_of(tag_id)
    listing = {"games": [{"system": k.partition("/")[0], "bucket": k} for k in keys]}
    try:
        return add(listing, view(listing, systems))
    finally:
        now = {g["bucket"]: g for g in listing["games"] if g.get("bucket")}
        gained = [k for k in now if k not in keys]
        lost = [k for k in keys if k not in now]
        if (gained or lost) and _save(tags.retag_games, tag_id, add=gained, remove=lost,
                                      files={k: now[k]["files"] for k in gained if now[k].get("files")}) and gained:
            tagui._used({tag_id})  # first in the t pickers, as a tag just put on games there is


def rename(tag_id, tag):
    name = ui.ask(f"   Name ({tag['name']}; empty keeps it): ").strip()
    if not name:
        return
    if any(i != tag_id and tags.slug(t["name"]) == tags.slug(name) for i, t in tags.all_tags().items()):
        edit.note(ui.yellow(f"⚠️  There is already a tag named {name}; nothing was changed."))
    else:
        _save(tags.define_tag, tag_id, {"name": name})  # the id never changes


def change_emoji(tag_id, tag):
    emoji = ui.ask(f"   Emoji ({tag['emoji']}; empty keeps it): ").strip()
    if not emoji:
        return
    if any(i != tag_id and t["emoji"] == emoji for i, t in tags.all_tags().items()):
        problem = f"{emoji} is already another tag's emoji"
    else:
        _save(tags.define_tag, tag_id, {"emoji": emoji})
        return
    edit.note(ui.yellow(f"⚠️  {problem}; nothing was changed."))


def merge(tag_id, tag):
    """Merge the tag into another one picked from a list; returns whether it is gone."""
    defs = tags.all_tags()
    ids = sorted((i for i in defs if i != tag_id), key=lambda i: defs[i]["name"].casefold())
    if not ids:
        edit.note(ui.yellow("ℹ️  There is no other tag to merge into."))
        return False
    j = picker.filter_list(f"✏️  Merge {_label(tag)} into which tag?", [_label(defs[i]) for i in ids],
                           row_note=tagui.described(defs, ids))
    if j is None:
        return False
    into = defs[ids[j]]
    n = len(_games_of(tag_id))
    if not ui.confirm(f"🔀 Merge {_label(tag)} into {_label(into)}? Its {n} game(s) get {into['name']} and "
                      f"{tag['name']} is deleted.", default=False):
        return False
    if _save(tags.merge_tag, tag_id, ids[j]):
        tagui.FILTER.retarget(tag_id, ids[j])
        edit.note(f"🔀 Merged {n} game{'' if n == 1 else 's'} into {_label(into)}")
        return True
    return False


def delete(tag_id, tag):
    """Delete the tag after asking; returns whether it is gone."""
    n = len(_games_of(tag_id))
    if not ui.confirm(f"🗑️  Delete {_label(tag)}? {n} game(s) lose it.", default=False):
        return False
    if _save(tags.delete_tag, tag_id):
        tagui.FILTER.retarget(tag_id, None)
        edit.note(f"🗑️  Deleted {_label(tag)}")
        return True
    return False


def header(tag):
    """The tag's games list's title: emoji, name and description."""
    return f"{_label(tag)}{' — ' + tag['description'] if tag.get('description') else ''}"


def settings_menu(tag_id, systems, keys_of):
    """The tag's name, emoji and description, adding the games of another tag, merging and deleting; Esc returns, x
    clears the description, Q raises Quit. Returns whether the tag is gone (merged or deleted)."""
    cursor = 0
    while True:
        tag = tags.all_tags().get(tag_id)
        if tag is None:
            return True
        rows = [f"Name: {tag['name']}", f"Emoji: {tag['emoji']}", f"Description: {tag.get('description') or 'none'}",
                "Add games with another tag", "Merge into another tag", "Delete this tag"]
        i = picker.filter_list(f"{header(tag)}: settings (Esc = back)", rows, cursor=cursor, hotkeys=(CLEAR_KEY, QUIT_KEY),
                               hint=f"Enter edit · x clear description · {QUIT_HINT} · Esc back",
                               key_help=[("Enter", "edit the row"), (CLEAR_KEY, "clear the description"),
                                         (QUIT_KEY, "quit the editor"), ("Esc", "back")])
        if i is None:
            return False
        if isinstance(i, tuple):
            if i[0] == QUIT_KEY:
                raise Quit
            cursor = i[1] or 0
            if i[1] == 2 and tag.get("description"):
                _save(tags.define_tag, tag_id, {"description": None})
            elif i[1] != 2:
                edit.note("ℹ️  x clears the description: press it on the Description row")
            continue
        cursor = i
        if i == 0:
            rename(tag_id, tag)
        elif i == 1:
            change_emoji(tag_id, tag)
        elif i == 2:
            text = ui.ask("   One-line description (empty keeps it): ").strip()
            if text:
                _save(tags.define_tag, tag_id, {"description": text})
        elif i == 3:
            if add_games(tag_id, systems, keys_of, lambda listing, shown: add_from_tag(
                    listing, shown, keys_of, _label(tag), hotkeys=(QUIT_KEY,), hint=ADD_HINT)) == QUIT_KEY:
                raise Quit
        elif i == 4:
            if merge(tag_id, tag):
                return True
        elif delete(tag_id, tag):
            return True


def edit_one(tag_id, systems, keys_of):
    """One tag: its games first, as the collection editor lists a collection's (a game switched off loses the tag when
    the list is left keeping the changes, by Enter, A, S, Q or Ctrl-C, or by Esc, which asks first whether to keep or
    revert them; it stays listed while the tag is open, so it can be switched back on), with A (or +) to add games,
    the list's / search carried into All systems, and S for its settings. Q raises Quit once the toggles are saved."""
    system_names = {s["bucket"]: s["name"] for s in systems}
    kept = set()  # every game listed while the tag is open
    files = {}  # game key -> its record's extra files, put back on a game switched back on
    place = {}
    while True:
        tag = tags.all_tags().get(tag_id)
        if tag is None:
            return
        records = tags.load()["games"]
        keys = [k for k, rec in records.items() if tag_id in rec["tags"]]
        files.update({k: records[k]["files"] for k in keys if records[k].get("files")})
        kept.update(keys)
        query = ""
        if not kept:  # nothing to list: the same actions as a menu
            i = picker.filter_list(f"{header(tag)} (Esc = back)", ["Add games", "Settings"],
                                   hotkeys=(ADD_KEY, ADD_ALIAS, SETTINGS_KEY, QUIT_KEY),
                                   hint=f"Enter open · A add games · S settings · {QUIT_HINT} · Esc back",
                                   key_help=[("Enter", "open the row"), *GAMES_HELP, ("Esc", "back")])
            pressed = None if i is None else i[0] if isinstance(i, tuple) else ADD_KEY if i == 0 else SETTINGS_KEY
        else:
            entry = {"bucket": "", "games": [{"bucket": k} for k in keys]}
            rows = sorted(((entry, k, names.title(k), f"{system_names.get(k.partition('/')[0], k.partition('/')[0])} — {names.title(k)}")
                           for k in kept), key=lambda r: (store.sort_key(r[2]), r[1]))
            if place.get("added"):  # back from adding: on the first game added
                at = next(i for i, r in enumerate(rows) if r[1] in place["added"])
                place = {"keys": [r[1] for r in rows], "session": {"row": at}}
            def follow(key, had):  # t or . put this tag on the row or took it off: its check follows
                has = tag_id in tags.tags_of(tags.owner(key))
                if has != (tag_id in had):  # another tag changed: the row keeps the check you gave it
                    entry["games"] = [g for g in entry["games"] if g["bucket"] != key] + ([{"bucket": key}] if has else [])
            try:
                pressed = edit.toggle_games(header(tag), rows, hotkeys=(ADD_KEY, ADD_ALIAS, SETTINGS_KEY, QUIT_KEY),
                                            hint=GAMES_HINT, key_help=GAMES_HELP, place=place, notes=False,
                                            tag_filter=False, retagged=follow)
            finally:  # Ctrl-C too: the toggles made are saved
                now = {g["bucket"] for g in entry["games"]}
                gone, back = set(keys) - now, sorted(now - set(keys))
                if gone or back:
                    _save(tags.retag_games, tag_id, add=back, remove=gone, files={k: files[k] for k in back if k in files})
            query = place.get("session", {}).get("query", "").strip()  # spaces alone are no search
        if pressed == QUIT_KEY:
            raise Quit
        if pressed is None:
            return
        if pressed in (ADD_KEY, ADD_ALIAS):
            before = set(_games_of(tag_id))
            if add_games(tag_id, systems, keys_of, lambda listing, shown: add_from_system(
                    listing, systems, shown, keys_of, _label(tag), tag_filter=False, query=query, hotkeys=(QUIT_KEY,),
                    hint=ADD_HINT)) == QUIT_KEY:
                raise Quit
            place["added"] = set(_games_of(tag_id)) - before
        elif settings_menu(tag_id, systems, keys_of):
            return


# --- The list ----------------------------------------------------------------------------------------

@picker.one_app
def edit_tags(quit_raises=False):
    """The list of tags; Enter opens one's games, n adds a new one. Returns the exit code. Q (in a tag) leaves it: with
    quit_raises, by raising Quit for the caller (`sync-roms edit` goes to its review)."""
    try:
        return _tag_list()
    except Quit:
        if quit_raises:
            raise
        return 0


def _tag_list():
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    keys_of = folder_lister()
    pos, by_count = 0, False
    while True:
        defs = tags.all_tags()
        counts = tagui._count()
        ids = sorted(defs, key=(lambda i: (-counts.get(i, 0), defs[i]["name"].casefold())) if by_count
                     else lambda i: defs[i]["name"].casefold())
        n = len(ids)
        i = picker.filter_list("🏷️  Which tag?  (Esc = back)",
                               [f"{_label(defs[x])}  ({counts.get(x, 0)} games)" for x in ids] + ["➕ New tag"],
                               hotkeys=(tagui.NEW_KEY, tagui.CLEAR_KEY, SORT_KEY), cursor=pos, filters=tagui.banner(),
                               hint=tagui.menu_hint("/ filter · Enter open · n new tag · o sort · Esc back"),
                               extras=[[("no games", "dim")] if not counts.get(x) else [("", "")] for x in ids] + [[("", "")]],
                               key_help=[("Enter", "open the tag's games"), (tagui.NEW_KEY, "add a new tag"),
                                         (SORT_KEY, f"sort by {'name' if by_count else 'game count'} instead"),
                                         (tagui.CLEAR_KEY, "clear the tag filter")],
                               row_note=tagui.described(defs, ids))
        if i is None:
            return 0
        if isinstance(i, tuple):
            if i[0] == tagui.CLEAR_KEY:
                tagui.handle_key(tagui.CLEAR_KEY, ())
                pos = i[1] or 0
                continue
            if i[0] == SORT_KEY:
                by_count, pos = not by_count, i[1] or 0
                continue
            i = n
        pos = i
        if i < n:
            edit_one(ids[i], systems, keys_of)
        else:
            made = _save_new()
            if made:
                edit_one(made, systems, keys_of)


def _save_new():
    """tagui's new-tag questions, with a storage failure noted instead of raised."""
    try:
        return tagui._new_tag()
    except (*s3.ERRORS, SystemExit, ValueError) as e:  # ValueError: tags.json in storage isn't valid JSON
        edit.note(ui.yellow(f"⚠️  Couldn't save the tags in storage: {e}"))
        return None
