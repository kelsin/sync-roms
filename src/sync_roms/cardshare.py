"""Exporting and importing cards: the plain data a card shares with another person's machine."""
import copy

from . import picker, store, ui

KEPT = ("size", "device", "layout", "games", "excluded")
RENAME_KEY = "r"
PREFIX_KEY = "p"


def _plain(game):
    """A collection or surprise game as (system, {"title", "bucket", "files"?, "note"?}), or None when it isn't usable."""
    if not isinstance(game, dict):
        return None
    system, bucket = game.get("system"), game.get("bucket")
    if not (isinstance(system, str) and system and isinstance(bucket, str) and bucket):
        return None
    plain = {"title": game.get("title"), "bucket": bucket}
    for key in ("files", "note"):
        if game.get(key):
            plain[key] = game[key]
    return system, plain


def export_entry(entry, collections_by_id):
    """A card as shared: its KEPT fields, with its collections' games and every surprise (on or off) flattened into
    `games` under their system, skipping buckets already listed there. A collection game the card unticked
    (in `excluded`) isn't flattened and stays excluded; a surprise is always flattened and leaves `excluded`. A full system gets none; unknown ids and malformed games are skipped. The input is not changed."""
    out = {k: copy.deepcopy(entry[k]) for k in KEPT if k in entry}
    games = out.setdefault("games", {})
    if not isinstance(games, dict):
        return out
    unticked = entry.get("excluded") if isinstance(entry.get("excluded"), dict) else {}
    picks = []
    for cid in entry.get("collections") or ():
        picks += [(g, True) for g in (collections_by_id.get(cid) or {}).get("games", [])]
    picks += [(g, False) for g in entry.get("surprises") or []]
    for game, from_collection in picks:
        parsed = _plain(game)
        if not parsed:
            continue
        system, plain = parsed
        if from_collection and isinstance(unticked.get(system), list) and plain["bucket"] in unticked[system]:
            continue
        have = games.setdefault(system, [])
        if isinstance(have, list) and all(g.get("bucket") != plain["bucket"] for g in have if isinstance(g, dict)):
            have.append(plain)
            excluded = out.get("excluded")
            if isinstance(excluded, dict) and isinstance(excluded.get(system), list):
                excluded[system] = [b for b in excluded[system] if b != plain["bucket"]]
                if not excluded[system]:
                    del excluded[system]
                if not excluded:
                    del out["excluded"]
    if not games:
        out.pop("games", None)
    return out


def _system_games(entry):
    """(full, games) of a system's entry in a card's games: a list, or a full_system dict (its stashed list); None when
    it is neither."""
    if isinstance(entry, list):
        return False, [g for g in entry if isinstance(g, dict)]
    if isinstance(entry, dict) and entry.get("full_system"):
        stashed = entry.get("games")
        return True, [g for g in stashed if isinstance(g, dict)] if isinstance(stashed, list) else []
    return None


def _ids(value):
    return [i for i in value if isinstance(i, str)] if isinstance(value, list) else []


def copy_selections(src, dst, playable, dst_synced):
    """(new DST entry, counts, skipped) of copying SRC's picks into DST. Games of the `playable` systems are added by
    bucket (DST's entry wins); either side full makes the system full, its list under "games". Set and collection ids
    are unioned. SRC's exclusions for playable systems are added unless DST syncs the game (`dst_synced`, {system: bucket
    keys} before the copy, or its merged picks). A copied game is removed from DST's exclusions. counts: newly added "games" (not into a
    full system, whose list sync ignores), "full" (systems made full by SRC), "sets", "collections", "excluded";
    skipped: SRC's systems not in `playable`, or whose DST entry is malformed, sorted. Everything else of DST stays; neither input is changed."""
    out = copy.deepcopy(dst)
    counts = dict.fromkeys(("games", "full", "sets", "collections", "excluded"), 0)
    src_games = src.get("games") if isinstance(src.get("games"), dict) else {}
    src_excluded = src.get("excluded") if isinstance(src.get("excluded"), dict) else {}
    skipped = {s for s in (*src_games, *src_excluded) if s != store.SETS_KEY and s not in playable}
    excluded = dict(out["excluded"]) if isinstance(out.get("excluded"), dict) else {}
    games = out.get("games") if isinstance(out.get("games"), dict) else {}
    for system, entry in src_games.items():
        if system == store.SETS_KEY or system not in playable:
            continue
        theirs = _system_games(entry)
        mine = _system_games(games.get(system, []))
        if not theirs:
            continue
        if not mine:
            skipped.add(system)
            continue
        full = mine[0] or theirs[0]
        have = {g.get("bucket") for g in mine[1]}
        merged = list(mine[1])
        for game in theirs[1]:
            if game.get("bucket") not in have:
                have.add(game.get("bucket"))
                merged.append(copy.deepcopy(game))
                counts["games"] += not full
        buckets = {g.get("bucket") for g in theirs[1]}
        left = [b for b in _ids(excluded.get(system)) if b not in buckets]
        if left:
            excluded[system] = left
        elif system in excluded:
            del excluded[system]
        if full:
            counts["full"] += not mine[0]
            games[system] = {"full_system": True, **({"games": merged} if merged else {})}
        else:
            games[system] = merged
    sets = _ids(games.get(store.SETS_KEY))
    new_sets = list(dict.fromkeys(i for i in _ids(src_games.get(store.SETS_KEY)) if i not in sets))
    if new_sets:
        games[store.SETS_KEY] = sets + new_sets
        counts["sets"] = len(new_sets)
    if games or "games" in out:
        out["games"] = store.sorted_list(games)
    collections = _ids(out.get("collections"))
    new_colls = list(dict.fromkeys(i for i in _ids(src.get("collections")) if i not in collections))
    if new_colls:
        out["collections"] = collections + new_colls
        counts["collections"] = len(new_colls)
    for system, buckets in src_excluded.items():
        if system not in playable:
            continue
        picked = _system_games(games.get(system, []))
        skip = set(dst_synced.get(system, ())) | ({g.get("bucket") for g in picked[1]} if picked else set())
        mine = list(excluded.get(system, [])) if isinstance(excluded.get(system), list) else []
        for bucket in _ids(buckets):
            if bucket not in mine and bucket not in skip:
                mine.append(bucket)
                counts["excluded"] += 1
        if mine:
            excluded[system] = mine
    if excluded:
        out["excluded"] = excluded
    elif isinstance(out.get("excluded"), dict):
        del out["excluded"]
    return out, counts, sorted(skipped)


def import_entry(entry):
    """The part of a shared card kept on import (KEPT fields), with Surprise off."""
    return {**{k: entry[k] for k in KEPT if k in entry}, "surprise": False}


def final_name(name, prefix, renames):
    """The name an imported card gets: its rename when it has one, else the prefix plus its own name."""
    return renames[name] if name in renames else prefix + name


def name_problem(name, taken):
    """Why `name` can't be a card name: "taken" or "invalid" (empty or has a `/`), else None."""
    if name in taken:
        return "taken"
    if not name.strip() or "/" in name:
        return "invalid"
    return None


def pick_export(names):
    """The cards to export, chosen in a list of names (none on to start); None on Esc."""
    state = picker.filter_list("📤 Cards to export", names, multi=True, initial=[False] * len(names), esc_asks=False,
                               hint="Space toggle · Enter export")
    return None if state is None else [name for name, on in zip(names, state) if on]


@picker.one_app
def pick_import(cards, existing, devices, layouts):
    """{final name: source name} of the cards chosen from `cards` (an export or a cards.json), or None on Esc. Rows show
    the final name; `r` renames the highlighted card and `p` sets a prefix for all. A final name that is taken (by
    `existing` or another chosen row) or invalid is marked, and Enter with one chosen keeps the list open. A card whose
    device or layout isn't in `devices`/`layouts` is locked."""
    sources = sorted(cards)
    notes = []
    for name in sources:
        device, layout = cards[name].get("device"), cards[name].get("layout")
        known_device = device is None or isinstance(device, str) and device in devices | {"full"}
        known_layout = layout is None or isinstance(layout, str) and layout in layouts
        notes.append(f"unknown device {device!r}" if not known_device
                     else f"unknown layout {layout!r}" if not known_layout else "")
    locked = [bool(n) for n in notes]
    prefix, renames = "", {}
    session = {"sel": [False] * len(sources)}

    def problems(state):
        finals = [final_name(name, prefix, renames) for name in sources]
        out = []
        for i, final in enumerate(finals):
            others = {f for j, f in enumerate(finals) if j != i and state[j] and not locked[j]}
            out.append(name_problem(final, existing | others))
        return finals, out

    while True:
        finals, found = problems(session["sel"])
        extras = [[(name if final != name else "", "dim"), (problem or "", "red")]
                  for name, final, problem in zip(sources, finals, found)]
        state = picker.filter_list(
            "📥 Cards to import", finals, multi=True, initial=[False] * len(sources), esc_asks=False, extras=extras,
            locked=locked, locked_note=notes, hotkeys=(RENAME_KEY, PREFIX_KEY), session=session,
            hint="Space toggle · Enter import · r rename · p prefix all",
            key_help=[("Space/Tab", "choose the card"), ("Enter", "import the chosen cards"),
                      (RENAME_KEY, "rename the card"), (PREFIX_KEY, "set a prefix for every card's name")])
        if state is None:
            return None
        if isinstance(state, tuple):
            key, i = state
            if key == RENAME_KEY and i is not None:
                answer = ui.ask(f"✏️  Name for {sources[i]} [{finals[i]}] (empty removes the rename): ").strip()
                if answer:
                    renames[sources[i]] = answer
                else:
                    renames.pop(sources[i], None)
            elif key == PREFIX_KEY:
                prefix = ui.ask(f"🏷️  Prefix for every card's name [{prefix}] (empty clears it): ")
            continue
        finals, found = problems(state)
        bad = [f"{final} ({problem})" for final, problem, on in zip(finals, found, state) if on and problem]
        if bad:
            text = f"Rename these first: {', '.join(bad)}"
            if not picker.queue_note(text):
                print(ui.yellow(f"⚠️  {text}"))
            continue
        return {final: name for name, final, on, lock in zip(sources, finals, state, locked) if on and not lock}
