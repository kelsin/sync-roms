"""Exporting and importing cards: the plain data a card shares with another person's machine."""
import copy

from . import picker, ui

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
    `games` under their system, skipping buckets already listed there, and taken out of `excluded` (which never
    applied to them). A full system gets none; unknown ids and malformed games are skipped. The input is not changed."""
    out = {k: copy.deepcopy(entry[k]) for k in KEPT if k in entry}
    games = out.setdefault("games", {})
    if not isinstance(games, dict):
        return out
    picks = []
    for cid in entry.get("collections") or ():
        picks += (collections_by_id.get(cid) or {}).get("games", [])
    picks += entry.get("surprises") or []
    for game in picks:
        parsed = _plain(game)
        if not parsed:
            continue
        system, plain = parsed
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
