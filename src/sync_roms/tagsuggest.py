"""`sync-roms tags suggest`: tags for games from the genre ScreenScraper gave them, reviewed before they are saved.

The repo's genre-tags.json maps a genre to tag ids: a ROM's `genre` in its system's scraped metadata.json is looked up
in full, else by its part before " / " ("Sports / Darts" is "Sports"). Suggestions cover every version of a game: the
tagged games, and the pool, which is every full English game in storage (surprise.is_candidate) that isn't a tagged
game or one of its files. A suggestion the user turned down is in tags.json's `declined` and isn't made again."""
from . import edit, inventory, names, s3, scrape_plan, store, surprise, tags, ui

_metadata = {}  # {system bucket: its parsed metadata.json}, read once per run


def reset():
    """Forget the metadata read, so the next use reads storage again."""
    _metadata.clear()


def _meta(bucket):
    if bucket not in _metadata:
        try:
            _metadata[bucket] = scrape_plan.load_metadata(bucket)
        except ValueError as e:
            ui.warn(f"Couldn't read {bucket}'s scraped metadata ({e}); it gets no suggestions")
            _metadata[bucket] = {}
    return _metadata[bucket]


def _entry(key):
    entry = _meta(key.partition("/")[0]).get(key.partition("/")[2])
    return entry if isinstance(entry, dict) else {}


def _title(key):
    """The game's scraped name, else names.title."""
    name = _entry(key).get("name")
    return name if isinstance(name, str) and name else names.title(key)


def _records(bucket):
    return sorted(k for k in tags.load()["games"] if k.partition("/")[0] == bucket)


def pool(system):
    """{key: title} of every game of the system that has no record and isn't a file of a tagged game (see the module
    docstring)."""
    bucket = system["bucket"]
    covered = set()
    for key, rec in tags.load()["games"].items():
        covered.add(key)
        covered.update(rec.get("files", ()))
    out = {}
    for unit in surprise.units(system, inventory.files(f"{bucket}/", sizes=False), set(system["bios"]["files"])):
        if not covered.intersection(unit):
            out[unit[0]] = _title(unit[0])
    return out


def untagged(system):
    """How many games of the system's pool have no tags."""
    return sum(1 for k in pool(system) if tags.record(k) is None)


def _genre_tags(mapping, genre):
    genre = genre.strip() if isinstance(genre, str) else ""
    return mapping.get(genre) or mapping.get(genre.split(" / ")[0].strip()) or []


def suggestions(systems):
    """{key: [tag ids]} of the genre's tags each game of the pool and each tagged game lacks; tags turned down for it
    and ids that aren't tags are left out."""
    mapping = store.repo_json("genre-tags")
    data = tags.load()
    out = {}
    for s in systems:
        for key in [*pool(s), *_records(s["bucket"])]:
            have = set(tags.tags_of(key)) | set(data["declined"].get(key, ()))
            ids = [i for i in _genre_tags(mapping, _entry(key).get("genre")) if i in data["tags"] and i not in have]
            if ids:
                out[key] = list(dict.fromkeys(ids))
    return out


def suggest_command(args):
    """The suggestions for the systems named (all of them by default) as a list to toggle, grouped by tag, all
    checked; Enter (after a yes) adds the checked ones and turns down the others, one write each."""
    systems = store.repo_json("systems")
    by_bucket = {s["bucket"]: s for s in systems}
    for name in args.systems:
        if name not in by_bucket:
            ui.fail(f"Unknown system {name!r}. Known: {', '.join(by_bucket)}", 2)
    chosen = [by_bucket[n] for n in dict.fromkeys(args.systems)] or systems
    folders = inventory.folders()
    found = suggestions([s for s in chosen if s["bucket"] in folders])
    if not found:
        print("🏷️  No new tag suggestions.")
        return 0
    defs = tags.all_tags()
    rows = []
    for key, ids in found.items():
        s = by_bucket[key.partition("/")[0]]
        title = _title(key)
        for i in ids:
            rows.append(((defs[i]["name"].casefold(), s["name"].casefold(), store.sort_key(title), key),
                         ({"bucket": str(len(rows)), "games": [{"bucket": key}]}, key, title,
                          f"{defs[i]['emoji']} {defs[i]['name']} — {s['name']} — {title}"), i))
    rows.sort(key=lambda r: r[0])  # each row has its own listing (named by its number, as the toggler keys them)
    edit.toggle_games("🏷️  Suggested tags — ✅ add it, ⬜ don't suggest it again", [r[1] for r in rows],
                      notes=False, tag_filter=False)
    accepted, declined = {}, {}
    for _, (entry, key, _, _), i in rows:
        (accepted if entry["games"] else declined).setdefault(key, []).append(i)
    n_add, n_decline = sum(map(len, accepted.values())), sum(map(len, declined.values()))
    if not ui.confirm(f"🏷️  Add {n_add} tag(s) and turn down {n_decline}?", default=True):
        print("Nothing was saved.")
        return 0
    try:
        if accepted:
            tags.add_tags(accepted)
        if declined:
            tags.decline(declined)
    except (*s3.ERRORS, ValueError) as e:  # ValueError: tags.json in storage isn't valid JSON
        ui.fail(f"Couldn't save the tags in storage: {e}", 1)
    print(f"🏷️  Added {n_add} tag(s) to {len(accepted)} game(s); turned down {n_decline}.")
    return 0
