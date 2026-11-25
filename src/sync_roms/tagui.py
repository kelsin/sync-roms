"""Tags on the game lists: the emoji column every list shows and `t`, which edits one game's tags."""
from . import picker, s3, tags, ui

TAG_KEY = "t"
NEW_KEY = "n"
KEY_HELP = (TAG_KEY, "the game's tags: check them, n adds a new tag")


def note(text):
    from . import edit  # edit imports this module
    edit.note(text)


def column(keys):
    """One extras part per row: the emoji of the game's tags, none shown for a game with no tags."""
    return [(tags.emoji_of(key), "") for key in keys]


def _count():
    """{tag id: number of games that have it}."""
    out = {}
    for rec in tags.load()["games"].values():
        for i in rec["tags"]:
            out[i] = out.get(i, 0) + 1
    return out


def _new_tag():
    """Ask for a name and an emoji and define the tag; its id, or None when cancelled or refused (a note says why)."""
    name = ui.ask("🏷️  Name for the new tag (empty to cancel): ").strip()
    emoji = ui.ask("   Emoji for it: ").strip() if name else ""
    tag_id = tags.slug(name)
    existing = tags.all_tags()
    if not name:
        problem = "a tag needs a name"
    elif not emoji:
        problem = "a tag needs an emoji"
    elif not tag_id or tag_id in existing:
        problem = f"there is already a tag named {name}"
    elif any(t["emoji"] == emoji for t in existing.values()):
        problem = f"{emoji} is already another tag's emoji"
    else:
        tags.define_tag(tag_id, {"name": name, "emoji": emoji})
        return tag_id
    note(ui.yellow(f"⚠️  {problem}; no tag was added."))
    return None


def edit_game_tags(key, title):
    """A list of every tag with the game's checked: Enter saves, n adds a new tag. Returns whether its tags changed."""
    try:
        start = set(tags.tags_of(key))
        picked = set(start)
        while True:
            defs = tags.all_tags()
            ids = sorted(defs, key=lambda i: defs[i]["name"].casefold())
            counts = _count()
            labels = [f"{defs[i]['emoji']} {defs[i]['name']} ({counts.get(i, 0)} games)" for i in ids]
            session = {"sel": [i in picked for i in ids]}
            result = picker.filter_list(f"🏷️  Tags of {title} (n adds a new tag)", labels, multi=True,
                                        initial=[i in start for i in ids], hotkeys=(NEW_KEY,), session=session,
                                        hint="Space toggle · Enter done · n new tag",
                                        key_help=[(NEW_KEY, "add a new tag, checked for this game")])
            if result is None:
                return False
            if isinstance(result, tuple):
                picked = {i for i, on in zip(ids, session["sel"]) if on}
                made = _new_tag()
                if made:
                    picked.add(made)
                continue
            chosen = {i for i, on in zip(ids, result) if on}
            if chosen == start:
                return False
            tags.set_game_tags(key, sorted(chosen))
            return True
    except (*s3.ERRORS, SystemExit) as e:
        note(ui.yellow(f"⚠️  Couldn't save the tags in storage: {e}"))
        return False
