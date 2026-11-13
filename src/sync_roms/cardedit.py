"""The card editor: every system a card's device can play (recommended ones marked) with its picks and space used,
and each system's games with set and scraped-metadata filters. Changes are saved to cards.json as they are made."""
import json
import queue
import threading

from . import budget, collections as colls, edit, inventory, m3u, metafilter, names, picker, previews, s3, scrape_plan, store, surprise, themeart, ui, usersettings, vita

FULL_KEY = "f"
SET_KEY = "s"
CLEAR_KEY = "c"
CLEAR_ALL_KEY = "D"
COLLECTIONS_KEY = "l"
SURPRISE_KEY = "S"
PAST_SURPRISE_KEY = "p"
META_KEY = "m"
VARIANT_KEY = "v"
LIST_HINT = "Enter games · f full · l collections · S surprise · D clear all"
GAMES_HINT = "Space toggle · Enter done · s set · m meta · p past · v variant"
META_HINT = "Enter list its values · Esc back"
VALUES_HINT = "Enter narrow to it · Esc back · / filter"
SETS_HINT = "Enter show its games · Space/Tab toggle its games here · / filter"
LIST_KEYS = [("Enter", "the system's games"), ("f", "full system: every file in its folder (again to undo)"),
             ("l", "collections on this card"), ("S", "Surprise menu: turn it on or off, or pick its systems"),
             ("D", "clear every pick, full system and set from the card")]
GAMES_KEYS = [("s", "sets on this system: narrow to one, or pick its games"),
              ("m", "narrow by scraped metadata (developer, genre, year...)"),
              ("p", "only the games that were surprises lately"), ("v", "the game's variants on other systems"),
              ("c", "clear the set, metadata and surprise filters")]
SIZING = "…"


def size_text(n):
    """A size in decimal units (1 GB = 10^9 bytes), as card sizes are sold: "512 GB", "1.5 GB"."""
    if n < 1000:
        return f"{n:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1000
        if round(n, 1) < 1000 or unit == "TB":
            return f"{n:.1f}".rstrip("0").rstrip(".") + f" {unit}"


def header(usage, capacity, fetch=None):
    """(status text, over budget) for a card's budget.Usage against its capacity in bytes (None: no size known).
    A partial usage is "not sized": there is no storage cache to size it from. fetch: bytes of ROMs not on the card
    yet (None: not known, as outside a sync)."""
    used = size_text(usage.bytes)
    if capacity is None:
        text, over = f"💾 {used} used", False
    else:
        over = usage.bytes > capacity
        text = f"💾 {used} / {size_text(capacity)}" + (f" · ⚠️  {size_text(usage.bytes - capacity)} over" if over else "")
    text += f" · {usage.count} file" + ("" if usage.count == 1 else "s")
    if fetch is not None:
        text += f" · ⬇️  {size_text(fetch)} to download"
    if usage.partial:
        text += f" · not sized ({inventory.UPDATE_HINT})"
    return text, over


WARN_AT, FULL_AT = 0.70, 0.90  # the header is green below WARN_AT of the card, yellow below FULL_AT, then red


def status_of(usage, capacity, fetch=None):
    """header() as a filter_list status: green until 70% of the card, yellow until 90%, red above (and when over budget)."""
    text, over = header(usage, capacity, fetch)
    if capacity is None:
        return text
    share = usage.bytes / capacity
    return (text, "red" if over or share >= FULL_AT else "yellow" if share >= WARN_AT else "green")


def system_labels(card, systems, recommended, usages):
    """(labels, extras) for the system list, in the given order: recommended systems get a ⭐; each picked system
    shows its count and size (… while not sized)."""
    games = card.get("games") or {}
    labels, extras = [], []
    for s in systems:
        rec = s["bucket"] in recommended
        labels.append(("⭐ " if rec else "   ") + s["name"])
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


ALL = "all"  # edit_card: a change that may touch every system
LOADING = "loading"
_metadata = {}  # system bucket -> metafilter.index, kept for the session so entering a system again doesn't fetch it again


def _spawn(fn):
    threading.Thread(target=fn, daemon=True).start()


class Metadata:
    """A system's scraped metadata.json as a metafilter.index, read once per session on a background thread (the
    worker never touches the screen). A failed read is not kept, so the next visit tries again."""

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
        values = [v for v, _ in found]
        j = picker.filter_list(f"🏷️  {label} on {system['name']}", values,
                               extras=[[(f"  {n} game(s)", "dim")] for _, n in found], hint=VALUES_HINT,
                               cursor=values.index(filters[field]) if filters.get(field) in values else 0)
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


def edit_card(name, setup=None, to_fetch=None):
    """The card's system list. setup: (device or None for Full, layout) to edit with instead of the saved one.
    to_fetch(system, keys): the keys not on the card yet, when editing from a sync; the status then shows how much
    a sync would download."""
    catalog = store.load_catalog()
    cards = store.load_cards()
    setup = setup or picker.saved_setup(cards.get(name), catalog["devices"], catalog["layouts"], name)
    if not setup:
        edit.note(ui.yellow(f"ℹ️  {name} has no device and firmware set; press {edit.SETUP_KEY} on it first."))
        return
    device = setup[0]
    systems = playable = can_play(catalog["systems"], setup)
    recommended = store.recommended_systems(device, catalog["systems"]) if device else set()
    # every playable system's usage, kept across passes: a change to one system recounts only it
    usages, version = budget.system_usages(card_entry(name, setup), playable), inventory.version()
    try:
        with ui.silent_thread():
            folders = inventory.folders()
    except (*s3.ERRORS, SystemExit):  # storage can't be reached (ui.fail raises SystemExit): go by the cache alone
        folders = None
    systems = [s for s in systems  # a missing or empty folder has nothing to pick, unless it already has picks
               if budget.picked(usages[s["bucket"]])
               or (folders is None or s["bucket"] in folders) and inventory.cached(f"{s['bucket']}/") != {}]
    pos = 0
    changed = None  # what the last pass changed: one system, ALL (any system may have) or None
    while True:
        card = card_entry(name, setup)
        if changed is ALL or inventory.version() != version:
            usages, version = budget.system_usages(card, playable), inventory.version()
        elif changed:
            usages[changed["bucket"]] = budget.system_usage(card, changed)
        changed = None
        capacity = budget.card_capacity(card)
        view = {}

        def work_out():
            card = card_entry(name, setup)
            view["total"] = budget.card_usage(card, systems, usages)
            view["fetch"] = budget.card_fetch_bytes(card, systems, to_fetch) if to_fetch else None
            return system_labels(card, systems, recommended, usages)

        labels, extras = work_out()

        def on_hotkey(key, idx):
            """f switches full system in place, so the screen isn't torn down and redrawn."""
            if key != FULL_KEY or idx is None:
                return False
            toggle_full(name, systems[idx]["bucket"])
            usages[systems[idx]["bucket"]] = budget.system_usage(card_entry(name, setup), systems[idx])
            extras[:] = work_out()[1]
            return True

        on = surprise.enabled(store.load_cards().get(name))
        i = picker.filter_list(f"💳 {name} — its systems (⭐ for the device) · 🎁 Surprise {'on' if on else 'off'}",
                               labels, extras=extras, cursor=pos,
                               hotkeys=(FULL_KEY, COLLECTIONS_KEY, SURPRISE_KEY, CLEAR_ALL_KEY), hint=LIST_HINT, key_help=LIST_KEYS,
                               status=lambda _state: status_of(view["total"], capacity, view["fetch"]),
                               on_hotkey=on_hotkey,
                               preview=lambda i: previews.system(systems[i]) if i < len(systems) else None)
        if i is None:
            return
        if isinstance(i, tuple):
            key, pos = i
            if key == FULL_KEY:
                toggle_full(name, systems[pos]["bucket"])
                changed = systems[pos]
            elif key == COLLECTIONS_KEY:
                pick_collections(name, {s["bucket"] for s in can_play(catalog["systems"], setup)},
                                 lambda: card_status(name, setup, systems, to_fetch))
                changed = ALL
            elif key == SURPRISE_KEY:
                surprise_menu(name, catalog["systems"])
                changed = ALL
            elif key == CLEAR_ALL_KEY:
                if ui.confirm(f"🧹 Clear every pick, full system and set from {name}?", default=False):
                    store.update_card(name, games={}, **({"excluded": {}} if store.card_excluded(name) else {}))
                    changed = ALL
            continue
        pos = i
        if edit_system(name, systems[i], setup, to_fetch, usages):
            changed = systems[i]


def card_status(name, setup, systems, to_fetch=None):
    """status_of for the card as saved now, over the systems the card editor lists."""
    card = card_entry(name, setup)
    total = budget.card_usage(card, systems)
    fetch = budget.card_fetch_bytes(card, systems, to_fetch) if to_fetch else None
    return status_of(total, budget.card_capacity(card), fetch)


def surprise_menu(name, systems):
    """S in the system list: turn the card's Surprise on or off, or pick the systems Surprise may use on every card."""
    on = surprise.enabled(store.load_cards().get(name))
    i = picker.filter_list("🎁 Surprise", [f"Turn Surprise {'off' if on else 'on'} for {name}",
                                          "Systems Surprise may use (every card)"])
    if i == 0:
        toggle_surprise(name)
    elif i == 1:
        pick_surprise_systems(systems)


def pick_surprise_systems(systems):
    """Check the systems Surprise may pick from; the unchecked ones are saved as surprise_excluded_systems."""
    excluded = surprise.excluded_systems()
    states = picker.filter_list("🎁 Systems Surprise may use (every card)", [s["name"] for s in systems], multi=True,
                                initial=[s["bucket"] not in excluded for s in systems])
    if states is None:
        return
    ids = {s["bucket"] for s in systems}
    kept = excluded - ids  # ids not in the catalog stay as they are
    off = sorted(kept | {s["bucket"] for s, on in zip(systems, states) if not on})
    usersettings.save_setting("surprise_excluded_systems", off or None)


def toggle_surprise(name):
    """Switch a card's Surprise on or off (on is the absence of the field); returns the new state."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return True
    if entry.get("surprise") is False:
        entry.pop("surprise")
    else:
        entry["surprise"] = False
        entry.pop("surprises", None)  # off clears the current picks
    store.write_cards(cards)
    return surprise.enabled(entry)


def pick_collections(name, playable, card_status=None):
    """Toggle the collections a card includes (Space/Tab in place, Enter toggles and reopens on that row), saving each
    toggle at once. Each is shown with how many of its games are on systems in playable (system buckets the card syncs).
    card_status(): the card's size status, worked out again after each toggle."""
    found = colls.load_collections()
    if not found:
        edit.note(ui.yellow("ℹ️  No collections yet: make one in sync-roms collections edit "
                            "(or 💖 Collections in sync-roms edit)."))
        return
    entry = store.load_cards().get(name)
    saved = entry.get("collections") if isinstance(entry, dict) else None
    ids = [i for i in saved if isinstance(i, str)] if isinstance(saved, list) else []
    labels = []
    for c in found:
        p = sum(1 for g in colls.collection_games(c) if g.get("system") in playable)
        n = len(colls.collection_games(c)) - p
        labels.append(f"{themeart.art_emoji(c.get('art'))} {c['name']}  ({p} playable" + (f", {n} not playable)" if n else ")"))
    extras = [[] for _ in found]
    shown = {}

    def mark():
        extras[:] = [[("  ✅ on the card", "green")] if c["id"] in ids else [] for c in found]
        shown["status"] = card_status() if card_status else None

    def toggle(idx):
        cid = found[idx]["id"]
        ids.remove(cid) if cid in ids else ids.append(cid)
        store.update_card(name, collections=list(ids))
        mark()

    def on_hotkey(_key, idx):
        if idx is None:
            return False
        toggle(idx)
        return True

    mark()
    pos = 0
    while True:
        i = picker.filter_list(f"💖 Collections on {name} (Space/Enter toggles)", labels, extras=extras, cursor=pos,
                               hotkeys=(" ", "\t"), on_hotkey=on_hotkey,
                               key_help=[("Space/Tab/Enter", "put the collection on the card or take it off")],
                               status=(lambda _state: shown["status"]) if card_status else None,
                               preview=lambda i: previews.collection(found[i].get("art")) if i < len(found) else None)
        if i is None:
            return
        toggle(i)
        pos = i


def pick_set(system, sets, games, titles, catalog, current=None, synced=lambda: set()):
    """The set to filter a system's games to, or None: sets with games in catalog (the system's bucket keys) are
    offered, starting on the one named current, each with how many of its games are synced out of those in storage
    (synced() gives the synced bucket keys). Space/Tab adds that set's games on this system to games (in place) as
    direct picks, or removes them when all are already picked; other systems are untouched."""
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
        def count(keys):
            have, total = len(keys & catalog & done), len(keys & catalog)
            return "➖" if total == 0 else "✅" if have == total else f"{have}/{total}"

        extras[:] = [[(f"  {count(keys)}", "cyan")] for _, keys in shown]

    def on_hotkey(_key, idx):
        """Toggles in place, so the screen isn't torn down and redrawn."""
        if idx is None:
            return False
        have = {g.get("bucket") for g in games}
        mine = shown[idx][1] & catalog
        if mine <= have:
            games[:] = [g for g in games if g.get("bucket") not in mine]
        else:
            for key in sorted(mine - have):
                games.append({"title": titles[key], "bucket": key})
        mark()
        return True

    mark()
    cursor = next((n for n, (x, _) in enumerate(shown) if x["name"] == current), 0)
    i = picker.filter_list(f"📦 Sets with games on {system['name']}", labels, extras=extras, cursor=cursor,
                           hotkeys=(" ", "\t"), hint=SETS_HINT, on_hotkey=on_hotkey,
                           preview=lambda i: previews.collection(shown[i][0]["id"]) if i < len(shown) else None)
    if i is None:
        return None
    return shown[i][0]


def edit_system(name, system, setup, to_fetch=None, card_usages=None):
    """A card's games of one system: the whole storage folder, searchable, filterable to a set's games and by scraped
    metadata. Saves to cards.json when left; returns whether anything changed. to_fetch: as for edit_card.
    card_usages: budget.system_usages of the card as saved, over every system it can play (edit_card keeps them), so
    the other systems aren't counted again."""
    bucket = system["bucket"]
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
    variants, parents = store.variant_index(sets)
    system_names = {x["bucket"]: x["name"] for x in store.repo_json("systems")}
    other_picks = {}  # {system bucket: [games]}: the card's direct picks on other systems, once a variant changes them
    if inventory.current() is None:
        print(ui.dim(f"📡 Listing {s3.location()}/{bucket}/ ..."))
    # names only: without a storage cache, a folder's sized listing stats every file
    try:
        in_storage = {k for k in inventory.files(f"{bucket}/", sizes=False) if not k.endswith("/")}
    except s3.ERRORS as e:
        edit.note(ui.yellow(f"⚠️  Couldn't list {system['name']} in storage: {e}"))
        return False
    rows = edit.system_rows(s, in_storage)
    titles = {k: title for _, k, title, _ in rows}
    groups = m3u.file_groups(in_storage)  # a multi-disc game's files are switched on and off together
    bundled = vita.extras(in_storage, in_storage)  # a Vita game's DLC and update sync with it
    others = [x for x in can_play(store.repo_json("systems"), setup) if x["bucket"] != bucket]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    locked_from = {g["bucket"]: g["from"] for g in store.card_locked_games(
        card_entry(name, setup, cards), {c["id"]: c for c in colls.load_collections()}).get(bucket, [])}
    work = {}

    def work_out():
        card = card_entry(name, setup, cards)  # with the set references and exclusions as edited so far
        games = {**(card.get("games") or {}), **other_picks, store.SETS_KEY: list(sets_on)}
        card = {**card, "games": {k: v for k, v in games.items() if v or k == store.SETS_KEY},
                "excluded": {b: k for b, k in other_excluded.items() if k}}
        usages = budget.system_usages(card, others) if card_usages is None else {x["bucket"]: card_usages[x["bucket"]] for x in others}
        parts = list(usages.values())  # without BIOS: it is added once, with this system's, in status
        work["others"] = budget.Usage(sum(p.bytes for p in parts), sum(p.count for p in parts),
                                      any(p.partial for p in parts))
        picked = [x for x in others if budget.picked(usages[x["bucket"]])]
        work["bios"] = (budget.bios_usage(picked), budget.bios_usage(picked + [system]))
        work["costs"], work["partial"] = budget.game_costs(card, system, [r[1] for r in rows])
        work["fetch"] = budget.card_fetch_bytes(card, others, to_fetch) if to_fetch else None

    work_out()

    def cover():
        return edit.cover_notes(sets_by_id, sets_on)

    def states(notes):
        """{bucket key: synced} for every row, from the card as edited so far: picked directly or by a referenced set,
        and not excluded (as sync does)."""
        direct = {g.get("bucket") for g in s["games"]}
        return {k: k in locked_from or (k in notes or k in direct) and k not in excluded for _, k, _, _ in rows}

    start = states(cover())

    def full(sb):
        entry = raw.get(sb)
        return sb != bucket and isinstance(entry, dict) and bool(entry.get("full_system"))

    def picks_of(sb, writing=False):
        """The card's direct picks on a system as edited so far; writing makes another system's a working copy in
        other_picks, saved with this one."""
        if sb == bucket:
            return s["games"]
        entry = raw.get(sb)
        mine = [dict(g) for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []
        return other_picks.setdefault(sb, mine) if writing else other_picks.get(sb, mine)

    def on_card(vb):
        """Whether a variant's bucket key is synced by the card as edited so far."""
        sb = vb.partition("/")[0]
        if sb == bucket:
            return states(cover()).get(vb, False)
        return full(sb) or ((any(g.get("bucket") == vb for g in picks_of(sb)) or vb in cover())
                            and vb not in other_excluded.get(sb, ()))

    def toggle_variant(v):
        """Add or remove a variant (and its files) as a direct pick; one the card syncs whole or through a set or
        collection stays as it is."""
        vb = v["bucket"]
        sb = vb.partition("/")[0]
        own = [vb, *v.get("files", ())]
        if on_card(vb):
            if full(sb) or all(g.get("bucket") != vb for g in picks_of(sb)):
                return
            picks = picks_of(sb, writing=True)
            picks[:] = [g for g in picks if g.get("bucket") not in own]
        else:
            picks = picks_of(sb, writing=True)
            picks.extend({"title": names.title(k), "bucket": k} for k in own
                         if all(g.get("bucket") != k for g in picks))
            if sb == bucket:
                excluded.difference_update(own)
            elif sb in other_excluded:
                other_excluded[sb] = [k for k in other_excluded[sb] if k not in own]
        work_out()
    filt = None  # (set name, bucket keys) the list is narrowed to
    meta_filt = {}  # {metadata field: value} the list is narrowed to as well
    past = None  # bucket keys of the past surprises the list is narrowed to

    def keep(key, skip=None):
        """Whether the filters (all but the skip field's metadata one) show a row."""
        wanted = {f: v for f, v in meta_filt.items() if f != skip}
        return ((filt is None or key in filt[1])
                and (past is None or key in past)
                and (not wanted or metafilter.matches(meta.get().get(key, {}), wanted)))

    def row_extras(key, notes, state):
        out = []
        if key in groups:
            out.append((f"  🔗 {len(groups[key])} files", "dim"))
        elif key in bundled:
            out.append((f"  🔗 {len(bundled[key]) + 1} files", "dim"))
        if key in notes:
            out.append((f"  📦 {notes[key].split(': ', 1)[-1]}", "cyan" if state else "dim"))
        if key in locked_from:
            out.append((f"  {locked_from[key]}", "cyan"))
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
            if want == base[key] or key in locked_from:
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
        for sb, picks in other_picks.items():
            if picks:
                games[sb] = picks
            else:
                games.pop(sb, None)
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
    place = {}  # picker.carry_place's: the last pass's row, filter text, view and scroll
    try:
        while True:
            notes = cover()
            base = states(notes)
            shown = [r for r in rows if keep(r[1])]
            keys = [r[1] for r in shown]
            index = {k: i for i, k in enumerate(keys)}
            links = [[index[m] for m in groups.get(k, ()) if m in index] for k in keys]
            session = {"sel": [base[k] for k in keys]}
            picker.carry_place(place, keys, session)  # where the last pass was, when it listed the same games
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
                fetch = None if to_fetch is None else work["fetch"] + budget.fetch_bytes(system, picked, to_fetch)
                return status_of(total, capacity, fetch)

            def note_text(i):
                game = next((g for g in s["games"] if g.get("bucket") == keys[i]), None)
                return game.get("note", "") if game else ""

            def on_note(i, text):
                if not edit.set_note(s, keys[i], text):
                    return "Switch the game on and press Enter first, then add its note"
                return "Note saved" if text else "Note cleared"

            parts = ([f"📦 {filt[0]} only"] if filt else []) + (["🎁 past surprises only"] if past is not None else []) + ([metafilter.describe(meta_filt)] if meta_filt else [])
            pending = (keys, notes, base, session)
            result = picker.filter_list(f"✏️  {system['name']} on {name} — ✅ synced, ⬜ not, 📦 from a set",
                                        [r[3] for r in shown], multi=True, initial=[start[k] for k in keys],
                                        extras=extras, hint=GAMES_HINT, hotkeys=(SET_KEY, META_KEY, PAST_SURPRISE_KEY, CLEAR_KEY, VARIANT_KEY),
                                        key_help=GAMES_KEYS, filters=f"{' · '.join(parts)} (c shows all)" if parts else "",
                                        status=status, row_note=lambda i: edit.variant_line(
                                            keys[i], variants, parents, system_names, on_card),
                                        session=session, note_text=note_text, on_note=on_note,
                                        preview=lambda i: previews.game(keys[i]) if i < len(keys) else None,
                                        links=links, locked=[k in locked_from for k in keys],
                                        locked_note=[f"From {locked_from[k]}; take it off the card to remove this game"
                                                     if k in locked_from else "" for k in keys])
            pending = None
            apply(keys, notes, base, session["sel"] if isinstance(result, tuple) else result)
            if not isinstance(result, tuple):
                break
            if result[0] == CLEAR_KEY:
                filt = None
                past = None
                meta_filt.clear()
            elif result[0] == PAST_SURPRISE_KEY:
                past = surprise.past_keys(bucket)
                if not past:
                    past = None
                    edit.note(ui.yellow(f"ℹ️  No past surprises on {system['name']}."))
            elif result[0] == VARIANT_KEY:
                found = variants.get(keys[result[1]], []) if result[1] is not None else []
                if len(found) > 1:
                    i = picker.filter_list(f"Variants of {titles[keys[result[1]]]}",
                                           [f"{'✅' if on_card(v['bucket']) else '⬜'} {v['note']}" for v in found])
                    found = [] if i is None else [found[i]]
                if found:
                    toggle_variant(found[0])
            elif result[0] == META_KEY:
                pick_meta(system, meta, meta_filt, lambda field: [r[1] for r in rows if keep(r[1], field)])
            else:
                chosen = pick_set(system, sets, s["games"], titles, {r[1] for r in rows}, filt and filt[0],
                                  lambda: {k for k, v in states(cover()).items() if v})
                if chosen:
                    filt = (chosen["name"], set_filter(chosen, system))
    except KeyboardInterrupt:  # Ctrl-C: keep the toggles
        if pending:
            keys, notes, base, session = pending
            apply(keys, notes, base, session["sel"])
        save()
        raise
    return save()
