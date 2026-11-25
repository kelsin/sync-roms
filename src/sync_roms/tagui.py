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
    elif not tag_id:
        problem = f"{name} has no letters or digits to make an id from"
    elif tag_id in existing:
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


STATES = ("⬜", "✅", "🚫")  # off, required, excluded
CLEAR_KEY = "c"


class TagFilter:
    """What a games list is narrowed to by tags: the games with every required tag and none of the excluded (a file
    of a record counts as its game)."""

    def __init__(self):
        self.required, self.excluded = set(), set()
        self._worked = None  # (tags data, required, excluded, keys with every required tag or None, keys to leave out)

    def clear(self):
        self.required.clear()
        self.excluded.clear()

    def keep(self, key):
        """Whether the filter shows the game."""
        if not self.required and not self.excluded:
            return True
        data, required, excluded = tags.load(), frozenset(self.required), frozenset(self.excluded)
        w = self._worked
        if w is None or w[0] is not data or w[1:3] != (required, excluded):  # worked out again after a tag change
            allowed = tags.games_with(required, excluded) if required else None
            left_out = set().union(*(tags.games_with({i}, ()) for i in excluded))
            w = self._worked = (data, required, excluded, allowed, left_out)
        return (w[3] is None or key in w[3]) and key not in w[4]

    def describe(self):
        """The filter line's part: "✅ 🚀 Shmups · 🚫 🐝 Cave", required tags first, or "" with no filter."""
        defs = tags.all_tags()
        parts = []
        for mark, ids in (("✅", self.required), ("🚫", self.excluded)):
            for i in sorted((i for i in ids if i in defs), key=lambda i: defs[i]["name"].casefold()):
                parts.append(f"{mark} {defs[i]['emoji']} {defs[i]['name']}")
        return " · ".join(parts)

    def pick(self, row_keys):
        """A list of the tags with games among row_keys: Enter cycles a tag off → required → excluded → off, c clears,
        Esc returns. Notes when no tag has a game there."""
        row_keys = set(row_keys)
        defs = tags.all_tags()
        counts = {i: len(row_keys & tags.games_with({i}, ())) for i in defs}
        ids = sorted((i for i, n in counts.items() if n), key=lambda i: defs[i]["name"].casefold())
        if not ids:
            note(ui.yellow("ℹ️  No tag has games among these."))
            return
        cursor = 0
        while True:
            labels = [f"{STATES[(i in self.required) + 2 * (i in self.excluded)]} {defs[i]['emoji']} {defs[i]['name']}"
                      f" ({counts[i]})" for i in ids]
            result = picker.filter_list("🏷️  Narrow to games with ✅ tags and without 🚫 ones", labels, cursor=cursor,
                                        hotkeys=(CLEAR_KEY,), hint="Enter ⬜ → ✅ → 🚫 → ⬜ · c clear · Esc done",
                                        key_help=[("Enter", "cycle the tag: ⬜ off, ✅ needed, 🚫 left out"),
                                                  (CLEAR_KEY, "clear every tag")])
            if result is None:
                return
            if isinstance(result, tuple):
                self.clear()
                cursor = result[1] or 0
                continue
            i, cursor = ids[result], result
            if i in self.required:
                self.required.discard(i)
                self.excluded.add(i)
            elif i in self.excluded:
                self.excluded.discard(i)
            else:
                self.required.add(i)
