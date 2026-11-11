"""The card editor: every system a card's device can play (recommended ones marked) with its picks and space used,
and each system's games with a set filter. Changes are saved to cards.json as they are made."""
import queue

from . import budget, edit, picker, scrape_plan, sizecache, store, ui

FULL_KEY = "f"
MAKE_SET_KEY = "m"
SET_KEY = "s"
CLEAR_KEY = "c"
LIST_HINT = "Enter games · f full system · m make a set · Esc back · / filter"
GAMES_HINT = "Space toggle · Enter done · Esc back · / search · s set filter · c clear · a all"
SETS_HINT = "Enter show its games · f sync the full set · Esc back · / filter"
SIZING = "…"


def size_text(n):
    """A size in decimal units (1 GB = 10^9 bytes), as card sizes are sold: "512 GB", "1.5 GB"."""
    if n < 1000:
        return f"{n:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1000
        if round(n, 1) < 1000 or unit == "TB":
            return f"{n:.1f}".rstrip("0").rstrip(".") + f" {unit}"


def header(usage, capacity):
    """(status text, over budget) for a card's budget.Usage against its capacity in bytes (None: no size known)."""
    used = size_text(usage.bytes)
    if capacity is None:
        text, over = f"💾 {used} used", False
    else:
        over = usage.bytes > capacity
        text = f"💾 {used} / {size_text(capacity)} · " + (
            f"⚠️  {size_text(usage.bytes - capacity)} over" if over else f"{size_text(capacity - usage.bytes)} free")
    text += f" · {usage.count} game(s)"
    if usage.partial:
        text += f" · {SIZING} still sizing"
    return text, over


def status_of(usage, capacity):
    """header() as a filter_list status: red when over budget."""
    text, over = header(usage, capacity)
    return (text, "red") if over else text


def system_labels(card, systems, recommended, usages):
    """(labels, extras) for the system list, in the given (systems.json) order: recommended systems get a ⭐ and a
    cyan "recommended"; each picked system shows its count and size (… while not sized)."""
    width = max((len(s["name"]) for s in systems), default=0)
    games = card.get("games") or {}
    labels, extras = [], []
    for s in systems:
        rec = s["bucket"] in recommended
        labels.append(("⭐ " if rec else "   ") + s["name"].ljust(width))
        u = usages.get(s["bucket"])
        row = []
        entry = games.get(s["bucket"])
        if isinstance(entry, dict) and entry.get("full_system"):
            row.append(("  🗂️  full system", "cyan"))
        if u and budget.picked(u):
            row.append((f"  {u.count or SIZING} picked", "green"))
            row.append((f"  {SIZING if u.partial else size_text(u.bytes)}", "dim"))
        if rec:
            row.append(("  recommended", "cyan"))
        extras.append(row)
    return labels, extras


def set_filter(game_set, system):
    """Bucket keys of a set's games (and their extra files) on one system."""
    return {g["bucket"] for g in store.set_games(game_set) if g.get("system") == system["bucket"]}


def can_play(systems, setup):
    """The systems a (device or None for Full, layout) setup syncs, in systems.json order."""
    return [s for s in systems if store.system_applies(s, *setup)]


class Sizing:
    """Background size refreshes: each prefix is started once, and finished() tells the curses loop (polling on its
    own thread) that one is done; the worker threads never touch the screen."""

    def __init__(self):
        self.done = queue.Queue()
        self.started = set()

    def start(self, prefix):
        if prefix not in self.started:
            self.started.add(prefix)
            sizecache.refresh_async(prefix, lambda _sizes: self.done.put(prefix))

    def finished(self):
        """Whether any refresh finished since the last call."""
        any_done = False
        while True:
            try:
                self.done.get_nowait()
            except queue.Empty:
                return any_done
            any_done = True


def card_entry(name, setup, cards=None):
    """A card's saved entry, with the layout of the setup being edited (it may not be saved yet)."""
    entry = (store.load_cards() if cards is None else cards).get(name)
    return {**(entry if isinstance(entry, dict) else {}), "layout": setup[1]}


def toggle_full(name, bucket, stash):
    """Switch a system's full_system on or off in a card and save it. The game list it replaced is kept in stash and
    put back when it is switched off again in this session."""
    games = dict(store.card_games(name))
    entry = games.get(bucket)
    if isinstance(entry, dict) and entry.get("full_system"):
        if stash.get(bucket):
            games[bucket] = stash.pop(bucket)
        else:
            games.pop(bucket)
    else:
        if isinstance(entry, list) and entry:
            stash[bucket] = entry
        games[bucket] = {"full_system": True}
    store.update_card(name, games=store.sorted_list(games))


def edit_card(name, setup=None):
    """The card's system list. setup: (device or None for Full, layout) to edit with instead of the saved one."""
    catalog = store.load_catalog()
    cards = store.load_cards()
    setup = setup or picker.saved_setup(cards.get(name), catalog["devices"], catalog["layouts"], name)
    if not setup:
        edit.note(ui.yellow(f"ℹ️  {name} has no device and firmware set; press {edit.SETUP_KEY} on it first."))
        return
    device = setup[0]
    systems = can_play(catalog["systems"], setup)
    recommended = store.recommended_systems(device, catalog["systems"]) if device else set()
    sizing = Sizing()
    sizing.start("BIOS/")
    stash, pos = {}, 0
    while True:
        card = card_entry(name, setup)
        capacity = budget.card_capacity(card)
        view = {}

        def work_out():
            usages = budget.system_usages(card, systems)
            view["total"] = budget.card_usage(card, systems, usages)
            return system_labels(card, systems, recommended, usages)

        labels, extras = work_out()

        def poll():
            if sizing.finished():
                extras[:] = work_out()[1]

        i = picker.filter_list(f"💳 {name} — its systems (⭐ recommended for the device)", labels, extras=extras,
                               cursor=pos, hotkeys=(FULL_KEY, MAKE_SET_KEY), hint=LIST_HINT,
                               status=lambda _state: status_of(view["total"], capacity), poll=poll)
        if i is None:
            return
        if isinstance(i, tuple):
            key, pos = i
            if key == FULL_KEY:
                toggle_full(name, systems[pos]["bucket"], stash)
            else:
                sets = store.load_sets()
                edit.make_set_from_extras(edit.new_target(name, store.card_games(name)), sets,
                                          {x["id"]: x for x in sets})
            continue
        pos = i
        edit_system(name, systems[i], setup, sizing)


def pick_set(system, sets, sets_on, catalog):
    """The set to filter a system's games to, or None: sets with games in catalog (the system's bucket keys) are
    offered. f switches a set's reference on the card (in sets_on, in place)."""
    shown = [(x, set_filter(x, system)) for x in sets]
    shown = [(x, keys) for x, keys in shown if keys & catalog]
    if not shown:
        edit.note(ui.yellow(f"ℹ️  No set has games in storage for {system['name']}."))
        return None
    pos = 0
    while True:
        labels = [f"{x['name']}  ({len(keys & catalog)} on {system['name']}"
                  + (f", {len(keys - catalog)} not in storage)" if keys - catalog else ")") for x, keys in shown]
        extras = [[("  📦 full set", "green")] if x["id"] in sets_on else [] for x, _ in shown]
        i = picker.filter_list(f"📦 Sets with games on {system['name']}", labels, extras=extras, cursor=pos,
                               hotkeys=(FULL_KEY,), hint=SETS_HINT)
        if i is None:
            return None
        if isinstance(i, tuple):
            pos = i[1]
            sets_on[:] = edit.toggle_set_ref(sets_on, shown[pos][0]["id"])
            continue
        return shown[i][0]


def edit_system(name, system, setup, sizing=None):
    """A card's games of one system: the whole storage folder, searchable, filterable to a set's games. Saves to
    cards.json when left; returns whether anything changed."""
    sizing = sizing or Sizing()
    bucket = system["bucket"]
    sizing.start(f"{bucket}/")
    if setup[1] in scrape_plan.SCRAPE_LAYOUTS:
        sizing.start(f"{scrape_plan.SCRAPES}/{bucket}/")
    cards = store.load_cards()
    raw = store.card_games(name, cards)
    entry = raw.get(bucket)
    if isinstance(entry, dict) and entry.get("full_system"):
        edit.note(ui.yellow(f"ℹ️  {system['name']} is a full system: every file in its storage folder is downloaded, "
                            "so there is no game list to edit."))
        return False
    s = {**system, "games": [dict(g) for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []}
    sets_on = list(store.list_sets(raw))
    before_excluded = store.card_excluded(name, cards)
    excluded = set(before_excluded.get(bucket, ()))
    sets = store.load_sets()
    sets_by_id = {x["id"]: x for x in sets}
    in_storage = store.folder_keys(bucket)
    rows = edit.system_rows(s, in_storage)
    others = [x for x in can_play(store.repo_json("systems"), setup) if x["bucket"] != bucket]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = {}

    def work_out():
        card = card_entry(name, setup, cards)
        usages = budget.system_usages(card, others)
        work["others"] = budget.card_usage(card, others, usages)
        picked = [x for x in others if budget.picked(usages[x["bucket"]])]
        work["bios"] = (budget.bios_usage(picked), budget.bios_usage(picked + [system]))
        work["costs"], work["scrapes_missing"] = budget.game_costs(card, system, [r[1] for r in rows])

    work_out()

    def cover():
        return edit.cover_notes(sets_by_id, sets_on)

    def states(notes):
        """{bucket key: synced} for every row, from the card as edited so far."""
        direct = {g.get("bucket") for g in s["games"]}
        return {k: k not in excluded if k in notes else k in direct for _, k, _, _ in rows}

    start = states(cover())
    filt = None  # (set name, bucket keys) the list is narrowed to

    def row_extras(key, notes, state):
        out = []
        if key in notes:
            out.append((f"  📦 {notes[key].split(': ', 1)[-1]}", "cyan" if state else "dim"))
        if key in work["costs"]:
            out.append((f"  {size_text(work['costs'][key])}", "dim"))
        elif key in in_storage:
            out.append((f"  {SIZING}", "dim"))
        return out

    while True:
        notes = cover()
        base = states(notes)
        shown = [r for r in rows if filt is None or r[1] in filt[1]]
        keys = [r[1] for r in shown]
        session = {"sel": [base[k] for k in keys]}
        extras = [row_extras(k, notes, st) for k, st in zip(keys, session["sel"])]

        def status(state):
            now = dict(base)
            now.update(zip(keys, state))
            picked = [k for k, st in now.items() if st]
            mine = sum(work["costs"].get(k, 0) for k in picked)
            bios = work["bios"][1 if picked else 0]
            partial = (work["others"].partial or bios.partial
                       or bool(picked) and (work["scrapes_missing"] or any(k not in work["costs"] for k in picked)))
            total = budget.Usage(work["others"].bytes + mine + bios.bytes, work["others"].count + len(picked), partial)
            return status_of(total, capacity)

        def poll():
            if sizing.finished():
                work_out()
                extras[:] = [row_extras(k, notes, st) for k, st in zip(keys, session["sel"])]

        def note_text(i):
            game = next((g for g in s["games"] if g.get("bucket") == keys[i]), None)
            return game.get("note", "") if game else ""

        def on_note(i, text):
            if not edit.set_note(s, keys[i], text):
                return "Switch the game on and press Enter first, then add its note"
            return "Note saved" if text else "Note cleared"

        where = f" · 📦 {filt[0]} only (c shows all)" if filt else ""
        result = picker.filter_list(f"✏️  {system['name']} on {name} — ✅ synced, ⬜ not, 📦 from a set{where}",
                                    [r[3] for r in shown], multi=True, initial=[start[k] for k in keys],
                                    extras=extras, hint=GAMES_HINT, hotkeys=(SET_KEY, CLEAR_KEY), status=status,
                                    poll=poll, session=session, note_text=note_text, on_note=on_note)
        state = session["sel"] if isinstance(result, tuple) else result
        for (_, key, title, _), want in zip(shown, state):
            if want == base[key]:
                continue
            if key in notes:
                excluded.symmetric_difference_update({key})
            elif want:
                s["games"].append({"title": title, "bucket": key})
            else:
                s["games"] = [g for g in s["games"] if g.get("bucket") != key]
        if not isinstance(result, tuple):
            break
        if result[0] == CLEAR_KEY:
            filt = None
        else:
            chosen = pick_set(system, sets, sets_on, {r[1] for r in rows})
            if chosen:
                filt = (chosen["name"], set_filter(chosen, system))
    games = {k: v for k, v in raw.items() if k not in (bucket, store.SETS_KEY)}
    if s["games"]:
        games[bucket] = s["games"]
    if sets_on:
        games[store.SETS_KEY] = sets_on
    new_excluded = {b: list(k) for b, k in before_excluded.items() if b != bucket}
    if excluded:
        new_excluded[bucket] = sorted(excluded)
    changed = store.sorted_list(games) != store.sorted_list(raw) or new_excluded != before_excluded
    if changed:
        store.update_card(name, games=store.sorted_list(games),
                          **({"excluded": new_excluded} if new_excluded or before_excluded else {}))
    return changed
