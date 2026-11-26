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
    """A list of every tag with the game's checked: Enter saves, n adds a new tag. Returns whether its tags changed.
    A file of a record (another disc) edits that record's tags."""
    try:
        key = tags.owner(key)
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
            tags.change_game_tags(key, add=chosen - start, remove=start - chosen)
            return True
    except (*s3.ERRORS, SystemExit, ValueError) as e:  # ValueError: tags.json in storage isn't valid JSON
        note(ui.yellow(f"⚠️  Couldn't save the tags in storage: {e}"))
        return False


def bulk_tag(keys):
    """Tags every game of keys (a file of a record counts as its record, once): a checklist of the tags, checked where
    all the games have it; checking adds a tag to every game, unchecking one they all have removes it. Asks "Tag N
    games?" before it writes. Returns whether tags were written."""
    try:
        owners = list(dict.fromkeys(tags.owner(k) for k in keys))
        if not owners:
            note(ui.yellow("ℹ️  No games shown to tag."))
            return False
        start = {i for i in tags.all_tags() if all(i in tags.tags_of(o) for o in owners)}
        picked = set(start)
        while True:
            defs = tags.all_tags()
            ids = sorted(defs, key=lambda i: defs[i]["name"].casefold())
            labels = [f"{defs[i]['emoji']} {defs[i]['name']}" for i in ids]
            session = {"sel": [i in picked for i in ids]}
            result = picker.filter_list(f"🏷️  Tag {len(owners)} games (n adds a new tag)", labels, multi=True,
                                        initial=[i in start for i in ids], hotkeys=(NEW_KEY,), session=session,
                                        hint="Space toggle · Enter done · n new tag",
                                        key_help=[(NEW_KEY, "add a new tag, checked for these games")])
            if result is None:
                return False
            if isinstance(result, tuple):
                picked = {i for i, on in zip(ids, session["sel"]) if on}
                made = _new_tag()
                if made:
                    picked.add(made)
                continue
            chosen = {i for i, on in zip(ids, result) if on}
            break
        add, remove = chosen - start, start - chosen
        if not add and not remove:
            note(ui.yellow("ℹ️  No tag changed."))
            return False
        if not ui.confirm(f"🏷️  Tag {len(owners)} games?", default=False):
            return False
        tags.change_games_tags({o: (add, remove) for o in owners})
        note(f"🏷️  Tagged {len(owners)} games")
        return True
    except (*s3.ERRORS, SystemExit, ValueError) as e:
        note(ui.yellow(f"⚠️  Couldn't save the tags in storage: {e}"))
        return False


NO_TAGS = "🈳 No tags at all"
STATES = ("⬜", "✅", "🚫")  # off, required, excluded
CLEAR_KEY = "c"


class TagFilter:
    """What a games list is narrowed to by tags: the games with every required tag and none of the excluded (a file
    of a record counts as its game)."""

    def __init__(self):
        self.required, self.excluded = set(), set()
        self.untagged = False  # only games with no tags at all (never together with required tags)
        self._worked = None  # (tags data, required, excluded, keys with every required tag or None, keys to leave out)

    def clear(self):
        self.required.clear()
        self.excluded.clear()
        self.untagged = False

    def active(self):
        return bool(self.required or self.excluded or self.untagged)

    def keep(self, key):
        """Whether the filter shows the game."""
        if self.untagged and tags.tags_of(tags.owner(key)):
            return False
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
        parts = [f"✅ {NO_TAGS}"] if self.untagged else []
        for mark, ids in (("✅", self.required), ("🚫", self.excluded)):
            for i in sorted((i for i in ids if i in defs), key=lambda i: defs[i]["name"].casefold()):
                parts.append(f"{mark} {defs[i]['emoji']} {defs[i]['name']}")
        return " · ".join(parts)

    def pick(self, row_keys):
        """A list of the tags with games among row_keys that the filter still shows (plus the tags already required or
        excluded, and "No tags at all"): Enter cycles a tag off → required → excluded → off, c clears, Esc returns.
        Notes when nothing is there to pick."""
        row_keys = set(row_keys)
        defs = tags.all_tags()
        cursor, entries = 0, None  # the rows are chosen once, so the cursor keeps its row while the counts change
        while True:
            untagged, self.untagged = self.untagged, False  # the tags to pick from are those the other filters leave
            narrowed = {k for k in row_keys if self.keep(k)}
            self.untagged = untagged
            counts = {i: len(narrowed & tags.games_with({i}, ())) for i in defs}
            none = sum(1 for k in narrowed if not tags.tags_of(tags.owner(k)))
            if entries is None:
                ids = sorted((i for i, n in counts.items() if n or i in self.required or i in self.excluded),
                             key=lambda i: defs[i]["name"].casefold())
                entries = ids + ([None] if ids and (none or self.untagged) else [])
            if not entries:
                note(ui.yellow("ℹ️  No tag has games among these."))
                return
            labels = [f"{'✅' if self.untagged else '⬜'} {NO_TAGS} ({none})" if i is None else
                      f"{STATES[(i in self.required) + 2 * (i in self.excluded)]} {defs[i]['emoji']} {defs[i]['name']}"
                      f" ({counts[i]})" for i in entries]
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
            i, cursor = entries[result], result
            if i is None:
                self.untagged = not self.untagged
                if self.untagged:
                    self.required.clear()
            elif i in self.required:
                self.required.discard(i)
                self.excluded.add(i)
            elif i in self.excluded:
                self.excluded.discard(i)
            else:
                self.required.add(i)
                self.untagged = False


FILTER = TagFilter()  # the one tag filter every game list shares; only c clears it
SET_KEY = "s"
HOTKEYS = (SET_KEY, CLEAR_KEY)
KEYS_HELP = [(SET_KEY, "narrow by tags (stays on in every list)"),
             (CLEAR_KEY, "clear the / search and the filters")]
BULK_KEY = "T"
BULK_HELP = (BULK_KEY, "tag every shown game: check the tags to add (✅ already on all of them), uncheck to remove")
TAGS_HINT = "s filter by tag · t edit tags · T tag all shown · c clear filters"
PAUSED = "🏷️ tag filter paused here"


def counts(shown, total):
    """" · N of M shown" when a list shows fewer rows than it has, else ""."""
    if shown is None or total is None or shown >= total:
        return ""
    return f" · {shown} of {total} shown"


def banner(shown=None, total=None):
    """The filters line's tag part for a list: what FILTER shows (with "N of M shown" when shown is fewer than
    total), or "" with no filter."""
    line = FILTER.describe()
    return f"{line}{counts(shown, total)} (c clear filters)" if line else ""


def paused():
    """The filters line's part for a list that ignores FILTER, or "" with no filter set."""
    return PAUSED if FILTER.describe() else ""


def games_hint(base, filtering=True, notes=True, select_all=True):
    """The hint of a games list: base (its own keys, starting "Space toggle · Enter done") with s, t and c named the
    same way everywhere, then / and w and a where the list has them. filtering False: a list that ignores the tag
    filter names only t."""
    drop = {"Space", "Enter", "s", "t", "c", "/", "w", "a"}
    rest = [p for p in base.split(" · ") if p.split(" ", 1)[0] not in drop]
    tag = TAGS_HINT if filtering else TAGS_HINT.split(" · ")[1]
    keys = ["/ filter"] + (["w note"] if notes else []) + (["a all shown"] if select_all else [])
    return " · ".join(["Space toggle", "Enter done", tag, *keys, *rest])


def menu_hint(hint):
    """A menu's hint, naming c while a tag filter is on."""
    return f"{hint} · c clear filters" if FILTER.describe() else hint


def handle_key(pressed, row_keys, place=None):
    """Apply s (pick tags among row_keys) or c (clear FILTER and the list's / filter in place); returns whether
    pressed was one of them."""
    if pressed == SET_KEY:
        FILTER.pick(row_keys)
    elif pressed == CLEAR_KEY:
        FILTER.clear()
        ((place or {}).get("session") or {}).pop("query", None)
    else:
        return False
    return True
