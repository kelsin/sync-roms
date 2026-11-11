"""The card editor: every system a card's device can play (recommended ones marked) with its picks and space used,
and each system's games with set and scraped-metadata filters. Changes are saved to cards.json as they are made."""
import curses
import json
import queue
import threading

from . import budget, edit, m3u, metafilter, picker, s3, scrape_plan, sizecache, store, ui

FULL_KEY = "f"
MAKE_SET_KEY = "m"
SET_KEY = "s"
CLEAR_KEY = "c"
CLEAR_ALL_KEY = "D"
META_KEY = "m"
LIST_HINT = "Enter games · f full · m make set · D clear all · Esc back · / filter"
GAMES_HINT = "Space toggle · Enter done · Esc back · / search · s set · m metadata · c clear"
META_HINT = "Enter list its values · Esc back"
VALUES_HINT = "Enter narrow to it · Esc back · / filter"
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


def header(usage, capacity, busy=True):
    """(status text, over budget) for a card's budget.Usage against its capacity in bytes (None: no size known).
    busy: whether size refreshes are still running; when not, a partial usage is "not sized" (a refresh failed)."""
    used = size_text(usage.bytes)
    if capacity is None:
        text, over = f"💾 {used} used", False
    else:
        over = usage.bytes > capacity
        text = f"💾 {used} / {size_text(capacity)} · " + (
            f"⚠️  {size_text(usage.bytes - capacity)} over" if over else f"{size_text(capacity - usage.bytes)} free")
    text += f" · {usage.count} file(s)"
    if usage.partial:
        text += f" · {SIZING} still sizing" if busy else " · not sized"
    return text, over


WARN_AT, FULL_AT = 0.70, 0.90  # the header is green below WARN_AT of the card, yellow below FULL_AT, then red


def status_of(usage, capacity, busy=True):
    """header() as a filter_list status: green until 70% of the card, yellow until 90%, red above (and when over budget)."""
    text, over = header(usage, capacity, busy)
    if capacity is None:
        return text
    share = usage.bytes / capacity
    return (text, "red" if over or share >= FULL_AT else "yellow" if share >= WARN_AT else "green")


def system_labels(card, systems, recommended, usages):
    """(labels, extras) for the system list, in the given order: recommended systems get a ⭐; each picked system
    shows its count and size (… while not sized)."""
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
        extras.append(row)
    return labels, extras


def set_filter(game_set, system):
    """Bucket keys of a set's games (and their extra files) on one system."""
    return {g["bucket"] for g in store.set_games(game_set) if g.get("system") == system["bucket"]}


def can_play(systems, setup):
    """The systems a (device or None for Full, layout) setup syncs, sorted by company then name."""
    return sorted((s for s in systems if store.system_applies(s, *setup)), key=store.system_sort_key)


_inflight = {}  # prefix -> the Sizing objects waiting on its running refresh, so a prefix is never refreshed twice at once
_inflight_lock = threading.Lock()


class Sizing:
    """Background size refreshes: each prefix is started once, and finished() tells the curses loop (polling on its
    own thread) that one is done; the worker threads never touch the screen. A prefix another Sizing is already
    refreshing joins that refresh instead of starting a second one."""

    def __init__(self):
        self.done = queue.Queue()
        self.started = set()
        self.pending = set()

    def start(self, prefix):
        if prefix in self.started:
            return
        self.started.add(prefix)
        self.pending.add(prefix)
        with _inflight_lock:
            waiting = _inflight.get(prefix)
            if waiting is not None:
                waiting.append(self)
                return
            _inflight[prefix] = [self]

        def finish(_sizes):
            with _inflight_lock:
                waiting = _inflight.pop(prefix)
            for sizing in waiting:
                sizing.pending.discard(prefix)
                sizing.done.put(prefix)

        sizecache.refresh_async(prefix, finish)

    def busy(self):
        """Whether a started refresh is still running."""
        return bool(self.pending)

    def finished(self):
        """Whether any refresh finished since the last call."""
        any_done = False
        while True:
            try:
                self.done.get_nowait()
            except queue.Empty:
                return any_done
            any_done = True


def start_system(sizing, bucket, layout):
    """Start the size refreshes the budget needs for one system: its ROM folder, and the scrapes its layout installs."""
    sizing.start(f"{bucket}/")
    if layout in scrape_plan.SCRAPE_LAYOUTS:
        sizing.start(f"{scrape_plan.SCRAPES}/{bucket}/")


LOADING = "loading"
_metadata = {}  # system bucket -> metafilter.index, kept for the session so entering a system again doesn't fetch it again


def _spawn(fn):
    threading.Thread(target=fn, daemon=True).start()


class Metadata:
    """A system's scraped metadata.json as a metafilter.index, read once per session on a background thread (like
    Sizing, the worker never touches the screen). A failed read is not kept, so the next visit tries again."""

    def __init__(self, bucket):
        self.bucket = bucket
        self.done = queue.Queue()
        self.result = _metadata.get(bucket, LOADING)
        if self.result is LOADING:
            _spawn(self._load)

    def _load(self):
        try:
            with ui.silent_thread():
                text = s3.get_text(f"{scrape_plan.SCRAPES}/{self.bucket}/metadata.json")
            result = metafilter.index(json.loads(text), self.bucket)
        except (Exception, SystemExit):  # missing, unreadable or not JSON: no metadata
            result = None
        self.done.put(result)

    def get(self):
        """The index, None when there is none, or LOADING. Never waits."""
        if self.result is LOADING:
            try:
                self.result = self.done.get_nowait()
            except queue.Empty:
                return LOADING
            if self.result is not None:
                _metadata[self.bucket] = self.result
        return self.result


def pick_meta(system, meta, filters, keys):
    """Set one metadata field of filters (in place) to a value picked from a list. keys(field): the bucket keys the game
    view would show without that field's filter; the values and their counts come from those."""
    pos = 0
    while True:
        if meta.get() is None:
            edit.note(ui.yellow(f"ℹ️  No scraped metadata for {system['name']} yet."))
            return
        extras = [[(f"  {filters[f]}", "cyan")] if f in filters else [] for f, _ in metafilter.FIELDS]
        i = picker.filter_list(f"🏷️  Filter {system['name']} by", [label for _, label in metafilter.FIELDS],
                               extras=extras, cursor=pos, hint=META_HINT, poll=lambda: None,
                               status=lambda _s: f"{SIZING} loading scraped metadata" if meta.get() is LOADING
                               else "Pick a field")
        if i is None:
            return
        pos = i
        idx = meta.get()
        if not isinstance(idx, dict):
            continue  # still loading (or found missing): ask again
        field, label = metafilter.FIELDS[i]
        found = metafilter.counts(idx, keys(field), field)
        if not found:
            edit.note(ui.yellow(f"ℹ️  No game in this list has a {label.lower()} in its scraped metadata."))
            continue
        j = picker.filter_list(f"🏷️  {label} on {system['name']}", [v for v, _ in found],
                               extras=[[(f"  {n} game(s)", "dim")] for _, n in found], hint=VALUES_HINT)
        if j is not None:
            filters[field] = found[j][0]
            return


def card_entry(name, setup, cards=None):
    """A card's saved entry, with the layout of the setup being edited (it may not be saved yet)."""
    entry = (store.load_cards() if cards is None else cards).get(name)
    return {**(entry if isinstance(entry, dict) else {}), "layout": setup[1]}


def toggle_full(name, bucket):
    """Switch a system's full_system on or off in a card and save it. The game list it replaces stays in the entry
    ("games", which sync ignores) and is put back when full_system is switched off again, even in a later session."""
    games = dict(store.card_games(name))
    entry = games.get(bucket)
    if isinstance(entry, dict) and entry.get("full_system"):
        if entry.get("games"):
            games[bucket] = entry["games"]
        else:
            games.pop(bucket)
    else:
        games[bucket] = {"full_system": True, **({"games": entry} if isinstance(entry, list) and entry else {})}
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
    start_card = card_entry(name, setup)
    start_usages = budget.system_usages(start_card, systems)
    systems = [s for s in systems  # a folder cached as empty has nothing to pick, unless it already has picks
               if sizecache.cached(f"{s['bucket']}/") != {} or budget.picked(start_usages[s["bucket"]])]
    for s in systems:  # the systems with picks are sized now, so the total doesn't wait for each to be opened
        if budget.picked(start_usages[s["bucket"]]):
            start_system(sizing, s["bucket"], setup[1])
    pos = 0
    while True:
        card = card_entry(name, setup)
        capacity = budget.card_capacity(card)
        view = {}

        def work_out():
            card = card_entry(name, setup)
            usages = budget.system_usages(card, systems)
            view["total"] = budget.card_usage(card, systems, usages)
            return system_labels(card, systems, recommended, usages)

        labels, extras = work_out()

        def poll():
            if sizing.finished():
                extras[:] = work_out()[1]

        def on_hotkey(key, idx):
            """f switches full system in place, so the screen isn't torn down and redrawn."""
            if key != FULL_KEY or idx is None:
                return False
            toggle_full(name, systems[idx]["bucket"])
            extras[:] = work_out()[1]
            return True

        i = picker.filter_list(f"💳 {name} — its systems (⭐ for the device)", labels, extras=extras,
                               cursor=pos, hotkeys=(FULL_KEY, MAKE_SET_KEY, CLEAR_ALL_KEY), hint=LIST_HINT,
                               status=lambda _state: status_of(view["total"], capacity, sizing.busy()), poll=poll,
                               on_hotkey=on_hotkey)
        if i is None:
            return
        if isinstance(i, tuple):
            key, pos = i
            if key == FULL_KEY:
                toggle_full(name, systems[pos]["bucket"])
            elif key == CLEAR_ALL_KEY:
                if ui.confirm(f"🧹 Clear every pick, full system and set from {name}?", default=False):
                    store.update_card(name, games={}, **({"excluded": {}} if store.card_excluded(name) else {}))
            else:
                sets = store.load_sets()
                edit.make_set_from_extras(edit.new_target(name, store.card_games(name)), sets,
                                          {x["id"]: x for x in sets})
            continue
        pos = i
        edit_system(name, systems[i], setup, sizing)


def pick_set(system, sets, sets_on, catalog, current=None, synced=lambda: set()):
    """The set to filter a system's games to, or None: sets with games in catalog (the system's bucket keys) are
    offered, starting on the one named current, each with how many of its games are synced out of those in storage
    (synced() gives the synced bucket keys). f switches a set's reference on the card (in sets_on, in place)."""
    shown = [(x, set_filter(x, system)) for x in sets]
    shown = [(x, keys) for x, keys in shown if keys & catalog]
    if not shown:
        edit.note(ui.yellow(f"ℹ️  No set has games in storage for {system['name']}."))
        return None
    labels = [f"{x['name']}  ({len(keys & catalog)} on {system['name']}"
              + (f", {len(keys - catalog)} not in storage)" if keys - catalog else ")") for x, keys in shown]
    extras = [[]] * len(shown)

    def mark():
        done = synced()
        extras[:] = [[(f"  {len(keys & catalog & done)}/{len(keys & catalog)}", "cyan")]
                     + ([("  📦 full set", "green")] if x["id"] in sets_on else []) for x, keys in shown]

    def on_hotkey(_key, idx):
        """f switches the reference in place, so the screen isn't torn down and redrawn."""
        if idx is None:
            return False
        sets_on[:] = edit.toggle_set_ref(sets_on, shown[idx][0]["id"])
        mark()
        return True

    mark()
    cursor = next((n for n, (x, _) in enumerate(shown) if x["name"] == current), 0)
    i = picker.filter_list(f"📦 Sets with games on {system['name']}", labels, extras=extras, cursor=cursor,
                           hotkeys=(FULL_KEY,), hint=SETS_HINT, on_hotkey=on_hotkey)
    if i is None:
        return None
    return shown[i][0]


def edit_system(name, system, setup, sizing=None):
    """A card's games of one system: the whole storage folder, searchable, filterable to a set's games and by scraped
    metadata. Saves to cards.json when left; returns whether anything changed."""
    sizing = sizing or Sizing()
    bucket = system["bucket"]
    start_system(sizing, bucket, setup[1])
    cards = store.load_cards()
    raw = store.card_games(name, cards)
    entry = raw.get(bucket)
    if isinstance(entry, dict) and entry.get("full_system"):
        edit.note(ui.yellow(f"ℹ️  {system['name']} is a full system: every file in its storage folder is downloaded, "
                            "so there is no game list to edit."))
        return False
    meta = Metadata(bucket)
    s = {**system, "games": [dict(g) for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []}
    sets_on = list(store.list_sets(raw))
    before_excluded = store.card_excluded(name, cards)
    excluded = set(before_excluded.get(bucket, ()))
    other_excluded = {b: list(k) for b, k in before_excluded.items() if b != bucket}
    sets = store.load_sets()
    sets_by_id = {x["id"]: x for x in sets}
    # names only: on a folder a sized listing stats every file, which the background refresh already does
    try:
        in_storage = {k for k in s3.list_sizes(f"{bucket}/", sizes=False) if not k.endswith("/")}
    except s3.ERRORS as e:
        edit.note(ui.yellow(f"⚠️  Couldn't list {system['name']} in storage: {e}"))
        return False
    rows = edit.system_rows(s, in_storage)
    titles = {k: title for _, k, title, _ in rows}
    groups = m3u.file_groups(in_storage)  # a multi-disc game's files are switched on and off together
    others = [x for x in can_play(store.repo_json("systems"), setup) if x["bucket"] != bucket]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = {}

    def work_out():
        card = card_entry(name, setup, cards)  # with the set references and exclusions as edited so far
        card = {**card, "games": {**(card.get("games") or {}), store.SETS_KEY: list(sets_on)},
                "excluded": {b: k for b, k in other_excluded.items() if k}}
        usages = budget.system_usages(card, others)
        parts = list(usages.values())  # without BIOS: it is added once, with this system's, in status
        work["others"] = budget.Usage(sum(p.bytes for p in parts), sum(p.count for p in parts),
                                      any(p.partial for p in parts))
        picked = [x for x in others if budget.picked(usages[x["bucket"]])]
        work["bios"] = (budget.bios_usage(picked), budget.bios_usage(picked + [system]))
        work["costs"], work["partial"] = budget.game_costs(card, system, [r[1] for r in rows])

    work_out()

    def cover():
        return edit.cover_notes(sets_by_id, sets_on)

    def states(notes):
        """{bucket key: synced} for every row, from the card as edited so far: picked directly or by a referenced set,
        and not excluded (as sync does)."""
        direct = {g.get("bucket") for g in s["games"]}
        return {k: (k in notes or k in direct) and k not in excluded for _, k, _, _ in rows}

    start = states(cover())
    filt = None  # (set name, bucket keys) the list is narrowed to
    meta_filt = {}  # {metadata field: value} the list is narrowed to as well

    def keep(key, skip=None):
        """Whether the filters (all but the skip field's metadata one) show a row."""
        wanted = {f: v for f, v in meta_filt.items() if f != skip}
        return ((filt is None or key in filt[1])
                and (not wanted or metafilter.matches(meta.get().get(key, {}), wanted)))

    def row_extras(key, notes, state):
        out = []
        if key in groups:
            out.append((f"  🔗 {len(groups[key])} files", "dim"))
        if key in notes:
            out.append((f"  📦 {notes[key].split(': ', 1)[-1]}", "cyan" if state else "dim"))
        if key in work["costs"]:
            out.append((f"  {size_text(work['costs'][key])}", "dim"))
        elif key in in_storage:
            out.append((f"  {SIZING}", "dim"))
        return out

    def changes(keys, base, state):
        """{bucket key: synced} for what one pass switched, each switched file's whole multi-disc game with it (the
        files the pass didn't show too)."""
        out = {}
        for key, want in zip(keys, state):
            if want != base[key]:
                for k in groups.get(key, [key]):
                    out.setdefault(k, want)
        return out

    def apply(keys, notes, base, state):
        """Fold one pass's on/off states into the card being edited. On: not excluded, and picked directly unless a
        referenced set covers it. Off: not picked directly, and excluded only while a referenced set covers it."""
        for key, want in changes(keys, base, state).items():
            if want == base[key]:
                continue
            if want:
                excluded.discard(key)
                if key not in notes and all(g.get("bucket") != key for g in s["games"]):
                    s["games"].append({"title": titles[key], "bucket": key})
            else:
                s["games"] = [g for g in s["games"] if g.get("bucket") != key]
                if key in notes:
                    excluded.add(key)
                else:
                    excluded.discard(key)

    def save():
        games = {k: v for k, v in raw.items() if k not in (bucket, store.SETS_KEY)}
        if s["games"]:
            games[bucket] = s["games"]
        if sets_on:
            games[store.SETS_KEY] = sets_on
        new_excluded = {b: k for b, k in other_excluded.items() if k}
        if excluded:
            new_excluded[bucket] = sorted(excluded)
        changed = store.sorted_list(games) != store.sorted_list(raw) or new_excluded != before_excluded
        if changed:
            store.update_card(name, games=store.sorted_list(games),
                              **({"excluded": new_excluded} if new_excluded or before_excluded else {}))
        return changed

    pending = None  # (rows shown, notes, states before) of the pass on screen, applied if Ctrl-C ends it
    try:
        while True:
            notes = cover()
            base = states(notes)
            shown = [r for r in rows if keep(r[1])]
            keys = [r[1] for r in shown]
            index = {k: i for i, k in enumerate(keys)}
            links = [[index[m] for m in groups.get(k, ()) if m in index] for k in keys]
            session = {"sel": [base[k] for k in keys]}
            extras = [row_extras(k, notes, st) for k, st in zip(keys, session["sel"])]

            def status(state):
                now = dict(base)
                now.update(changes(keys, base, state))
                picked = [k for k, st in now.items() if st]
                mine = sum(work["costs"].get(k, 0) for k in picked)
                bios = work["bios"][1 if picked else 0]
                partial = (work["others"].partial or bios.partial
                           or bool(picked) and work["partial"])
                total = budget.Usage(work["others"].bytes + mine + bios.bytes, work["others"].count + len(picked),
                                     partial)
                return status_of(total, capacity, sizing.busy())

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

            parts = ([f"📦 {filt[0]} only"] if filt else []) + ([metafilter.describe(meta_filt)] if meta_filt else [])
            where = f" · {' · '.join(parts)} (c shows all)" if parts else ""
            pending = (keys, notes, base, session)
            result = picker.filter_list(f"✏️  {system['name']} on {name} — ✅ synced, ⬜ not, 📦 from a set{where}",
                                        [r[3] for r in shown], multi=True, initial=[start[k] for k in keys],
                                        extras=extras, hint=GAMES_HINT, hotkeys=(SET_KEY, META_KEY, CLEAR_KEY),
                                        status=status,
                                        poll=poll, session=session, note_text=note_text, on_note=on_note,
                                        links=links)
            pending = None
            apply(keys, notes, base, session["sel"] if isinstance(result, tuple) else result)
            if not isinstance(result, tuple):
                break
            if result[0] == CLEAR_KEY:
                filt = None
                meta_filt.clear()
            elif result[0] == META_KEY:
                pick_meta(system, meta, meta_filt, lambda field: [r[1] for r in rows if keep(r[1], field)])
            else:
                refs = list(sets_on)
                chosen = pick_set(system, sets, sets_on, {r[1] for r in rows}, filt and filt[0],
                                  lambda: {k for k, v in states(cover()).items() if v})
                if sets_on != refs:  # kept as is: rows switched by the reference change aren't pending, so u keeps them
                    covered = cover()  # an exclusion means nothing once no set covers the game, on any system
                    excluded.intersection_update(covered)
                    other_excluded.update((b, [k for k in keys if k in covered]) for b, keys in other_excluded.items())
                    start = states(cover())
                    work_out()  # the other systems' share and BIOS change with the set references
                if chosen:
                    filt = (chosen["name"], set_filter(chosen, system))
    except (KeyboardInterrupt, curses.error):  # Ctrl-C, or a terminal too small to draw the list: keep the toggles
        if pending:
            keys, notes, base, session = pending
            apply(keys, notes, base, session["sel"])
        save()
        raise
    return save()
