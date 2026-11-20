"""The card editor: every system a card's device can play (recommended ones marked) with its picks and space used,
and each system's games with set and scraped-metadata filters. Changes are saved to cards.json as they are made."""
import json
import queue
import threading

from . import budget, cardpicks, collections as colls, edit, inventory, listedit, metafilter, picker, previews, s3, scrape_plan, store, surprise, themeart, ui, usersettings

FULL_KEY = "f"
SET_KEY = "s"
CLEAR_KEY = "c"
CLEAR_ALL_KEY = "D"
COLLECTIONS_KEY = "l"
SURPRISE_KEY = "S"
KEEP_KEY = "k"
PAST_SURPRISE_KEY = "p"
META_KEY = "m"
VARIANT_KEY = "v"
SERIES_KEY = "r"
LIST_HINT = "Enter games · f full · s set · l collections · S surprise · D clear all"
GAMES_HINT = "Space toggle · Enter done · s set · m meta · p past · v variant"
META_HINT = "Enter list its values · Esc back"
VALUES_HINT = "Enter narrow to it · Esc back · / filter"
SETS_HINT = "Enter show its games · Space/Tab toggle its games here · / filter"
SET_GAMES_HINT = "Space toggle · Enter done · w note · v variant · r series"
LIST_KEYS = [("Enter", "the system's games"), ("f", "full system: every file in its folder (again to undo)"),
             ("s", "a set's games across this card's systems"), ("l", "collections on this card"),
             ("S", "Surprise menu: turn it on or off, or pick its systems"),
             ("D", "clear every pick, full system and set from the card")]
KEEP_HINT = " · k keep card files"
KEEP_KEYS = [("k", "pick every card file that matches a storage game")]
GAMES_KEYS = [("s", "sets on this system: narrow to one, or pick its games"),
              ("r", "narrow the set picked with s to one series of games"),
              ("m", "narrow by scraped metadata (developer, genre, year...)"),
              ("p", "only the games that were surprises lately"), ("v", "the game's variants on other systems"),
              ("c", "clear the search, set, series, metadata and surprise filters")]
SET_GAMES_KEYS = [("v", "the game's variants on other systems"), ("r", "narrow to one series of games"),
                  ("c", "clear the series filter")]
SIZING = "…"


def size_text(n):
    """A size in decimal units (1 GB = 10^9 bytes), as card sizes are sold: "512 GB", "1.5 GB"."""
    if n < 1000:
        return f"{n:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1000
        if round(n, 1) < 1000 or unit == "TB":
            return f"{n:.1f}".rstrip("0").rstrip(".") + f" {unit}"


def header(usage, capacity, fetch=None, count=True):
    """(status text, over budget) for a card's budget.Usage against its capacity in bytes (None: no size known).
    A partial usage is "not sized": there is no storage cache to size it from. fetch: bytes of ROMs not on the card
    yet (None: not known, as outside a sync). count: show the card's file count."""
    used = size_text(usage.bytes)
    if capacity is None:
        text, over = f"💾 {used} used", False
    else:
        over = usage.bytes > capacity
        text = f"💾 {used} / {size_text(capacity)} · " + (
            f"⚠️  {size_text(usage.bytes - capacity)} over" if over else f"{size_text(capacity - usage.bytes)} free")
    if count:
        text += f" · {usage.count} file" + ("" if usage.count == 1 else "s")
    if fetch is not None:
        text += f" · ⬇️  {size_text(fetch)} to download"
    if usage.partial:
        text += f" · not sized ({inventory.UPDATE_HINT})"
    return text, over


WARN_AT, FULL_AT = 0.70, 0.90  # the header is green below WARN_AT of the card, yellow below FULL_AT, then red


def status_of(usage, capacity, fetch=None, count=True):
    """header() as a filter_list status: green until 70% of the card, yellow until 90%, red above (and when over budget)."""
    text, over = header(usage, capacity, fetch, count)
    if capacity is None:
        return text
    share = usage.bytes / capacity
    return (text, "red" if over or share >= FULL_AT else "yellow" if share >= WARN_AT else "green")


def system_labels(card, systems, recommended, usages, full_sizes):
    """(labels, extras) for the system list, in the given order: recommended systems get a ⭐; each picked system
    shows its count and size (… while not sized), then each system its size as a full system (full_sizes: {bucket:
    budget.full_usage}, a missing one not worked out yet; an empty folder shows none). A full system shows its files
    and full size instead of its picks, then 🗂️ (columns: blank where a row has none)."""
    games = card.get("games") or {}
    labels, extras = [], []
    for s in systems:
        rec = s["bucket"] in recommended
        labels.append(("⭐ " if rec else "   ") + s["name"])
        u, f = usages.get(s["bucket"]), full_sizes.get(s["bucket"])
        unknown = f is None or f.partial
        row = [("", "green"), ("", "dim"), ("", "dim")]
        entry = games.get(s["bucket"])
        if isinstance(entry, dict) and entry.get("full_system"):
            files = SIZING if unknown else f.count
            row = [(f"  {files} file" + ("" if files == 1 else "s"), "green"),
                   (f"  {SIZING if unknown else size_text(f.bytes)}", "dim"), ("  🗂️  full system", "cyan")]
        else:
            if u and budget.picked(u):
                row[:2] = [(f"  {u.count or SIZING} picked", "green"), (f"  {SIZING if u.partial else size_text(u.bytes)}", "dim")]
            if unknown or f.count:
                row[2] = (f"  🗂️  {SIZING if unknown else size_text(f.bytes)} full", "dim")
        extras.append(row if any(text for text, _ in row) else [])
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
                text = s3.get_text(scrape_plan.metadata_key(self.bucket))
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


class FullSizes:
    """Each system's budget.full_usage on a card, worked out on a background thread (the worker never touches the
    screen) and again when the storage cache changes. sizes: {bucket: Usage} of what has arrived."""

    def __init__(self, card, systems):
        self.card, self.systems = card, systems
        self.version, self.done, self.sizes = LOADING, None, {}

    def _load(self, done):
        try:
            with ui.silent_thread():
                for s in self.systems:
                    done.put((s["bucket"], budget.full_usage(self.card, s)))
        except (Exception, SystemExit):  # storage can't be read: the rest stay not worked out
            pass

    def update(self):
        """Take in what the worker has handed over, starting it first when the cache is new. Whether sizes changed;
        never waits."""
        changed, version = False, inventory.version()
        if version != self.version:
            self.version, self.done, self.sizes, changed = version, queue.Queue(), {}, True
            _spawn(lambda done=self.done: self._load(done))
        while True:
            try:
                bucket, usage = self.done.get_nowait()
            except queue.Empty:
                return changed
            self.sizes[bucket] = usage
            changed = True


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


@picker.one_app
def edit_card(name, setup=None, to_fetch=None, card_match=None):
    """The card's system list. setup: (device or None for Full, layout) to edit with instead of the saved one.
    to_fetch(system, keys): the keys not on the card yet, when editing from a sync; the status then shows how much
    a sync would download. card_match(system, keys): (the keys of the system's storage files that are on the card, how
    many other files its card folder holds), when editing from a sync; it enables k."""
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
    full = FullSizes({"layout": setup[1]}, systems)  # each system's size as a full system, kept for the session
    pos, set_pos = 0, None  # set_pos: the name of the set last opened
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
        full.update()

        def work_out():
            card = card_entry(name, setup)
            view["total"] = budget.card_usage(card, systems, usages)
            view["fetch"] = budget.card_fetch_bytes(card, systems, to_fetch) if to_fetch else None
            return system_labels(card, systems, recommended, usages, full.sizes)

        labels, extras = work_out()

        def poll():
            """Fill in the full sizes as the worker hands them over."""
            if full.update():
                extras[:] = system_labels(card_entry(name, setup), systems, recommended, usages, full.sizes)[1]

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
                               hotkeys=(FULL_KEY, SET_KEY, COLLECTIONS_KEY, SURPRISE_KEY, CLEAR_ALL_KEY,
                                        *((KEEP_KEY,) if card_match else ())),
                               hint=LIST_HINT + (KEEP_HINT if card_match else ""),
                               key_help=LIST_KEYS + (KEEP_KEYS if card_match else []),
                               status=lambda _state: status_of(view["total"], capacity, view["fetch"]),
                               on_hotkey=on_hotkey, poll=poll,
                               preview=lambda i: previews.system(systems[i]) if i < len(systems) else None)
        if i is None:
            return
        if isinstance(i, tuple):
            key, pos = i
            if key == FULL_KEY:
                toggle_full(name, systems[pos]["bucket"])
                changed = systems[pos]
            elif key == SET_KEY:
                chosen = pick_card_set(name, setup, systems, set_pos)
                if chosen:
                    set_pos = chosen["name"]
                    edit_set(name, chosen, setup, to_fetch, usages)
                    changed = ALL
            elif key == COLLECTIONS_KEY:
                pick_collections(name, {s["bucket"] for s in can_play(catalog["systems"], setup)},
                                 lambda: card_status(name, setup, systems, to_fetch))
                changed = ALL
            elif key == SURPRISE_KEY:
                surprise_menu(name, catalog["systems"])
                changed = ALL
            elif key == KEEP_KEY:
                keep_card_files(name, setup, systems, card_match)
                changed = ALL
            elif key == CLEAR_ALL_KEY:
                if ui.confirm(f"🧹 Clear every pick, full system and set from {name}?", default=False):
                    store.update_card(name, games={}, **({"excluded": {}} if store.card_excluded(name) else {}))
                    changed = ALL
            continue
        pos = i
        if edit_system(name, systems[i], setup, to_fetch, usages):
            changed = systems[i]


def keep_card_files(name, setup, systems, card_match):
    """Pick, in every system that isn't a full one, the files already on the card that match a storage game."""
    picks = cardpicks.CardPicks(name, setup)
    added = touched = unmatched = 0
    for system in systems:
        if picks.full(system["bucket"]):
            continue
        try:
            sp = picks.system(system)
        except s3.ERRORS as e:
            edit.note(ui.yellow(f"⚠️  Couldn't list {system['name']} in storage: {e}"))
            continue
        matched, other = card_match(system, list(sp.in_storage))
        n = sp.keep(sorted(matched), picks.cover())
        added, touched, unmatched = added + n, touched + bool(n), unmatched + other
    picks.save()
    edit.note(f"Picked {added} card file(s) in {touched} system(s); {unmatched} card file(s) match nothing in "
              "storage and still get deleted")


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
    """Switch a card's Surprise on or off (see surprise.set_enabled); returns the new state."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return surprise.enabled(entry)
    on = not surprise.enabled(entry)
    surprise.set_enabled(entry, on)
    if not on:
        entry.pop("surprises", None)  # off clears the current picks
    store.write_cards(cards)
    return surprise.enabled(entry)


def pick_collections(name, playable, card_status=None):
    """Toggle the collections a card includes (Space/Tab/Enter, in place), saving each
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
    labels, counts = [], []
    for c in found:
        p = sum(1 for g in colls.collection_games(c) if g.get("system") in playable)
        n = len(colls.collection_games(c)) - p
        labels.append(f"{themeart.art_emoji(c.get('art'))} {c['name']}")
        counts.append((f"  {p} playable" + (f", {n} not playable" if n else ""), "dim"))
    extras = [[] for _ in found]
    shown = {}

    def mark():
        extras[:] = [[("  ✅ on the card" if c["id"] in ids else "", "green"), count] for c, count in zip(found, counts)]
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
                               hotkeys=(" ", "\t", "enter"), on_hotkey=on_hotkey,
                               key_help=[("Space/Tab/Enter", "put the collection on the card or take it off")],
                               status=(lambda _state: shown["status"]) if card_status else None,
                               preview=lambda i: previews.collection(found[i].get("art")) if i < len(found) else None)
        if i is None:
            return
        toggle(i)
        pos = i


def pick_card_set(name, setup, systems, current=None):
    """The set to open as a card's set view, or None: single-select, the sets with a game in storage on systems (the
    card editor's list), starting on the one named current, each with how many of those games the card syncs."""
    picks = cardpicks.CardPicks(name, setup)
    views = [(x, set_view_keys(x, systems)) for x in store.load_sets()]
    in_storage = {}  # {system bucket: its keys, or True for a full system} of the systems with set games
    try:
        for s in {s["bucket"]: s for _, view in views for s, _, _ in view}.values():
            if picks.full(s["bucket"]):
                in_storage[s["bucket"]] = True
                continue
            in_storage[s["bucket"]] = store.folder_keys(s["bucket"])
    except s3.ERRORS as e:
        edit.note(ui.yellow(f"⚠️  Couldn't list storage: {e}"))
        return None
    shown = []
    for x, view in views:
        keys = [k for s, k, _ in view if in_storage[s["bucket"]] is True or k in in_storage[s["bucket"]]]
        if keys:
            shown.append((x, keys))
    if not shown:
        edit.note("ℹ️  No set has games in storage for this card's systems.")
        return None
    labels = [f"{themeart.set_emoji(x)} {x['name']}  ({len(keys)} games)" for x, keys in shown]
    extras = []
    for _, keys in shown:
        have = sum(1 for k in keys if picks.on_card(k))
        extras.append([(f"  {'✅' if have == len(keys) else f'{have}/{len(keys)}'}", "cyan")])
    cursor = next((n for n, (x, _) in enumerate(shown) if x["name"] == current), 0)
    i = picker.filter_list(f"📦 Sets on {name}'s systems", labels, extras=extras, cursor=cursor,
                           preview=lambda i: previews.collection(themeart.set_art(shown[i][0])) if i < len(shown) else None)
    return None if i is None else shown[i][0]


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
    mains = [{g["bucket"] for g in x["games"] if g.get("system") == system["bucket"] and g.get("bucket")}
             for x, _ in shown]  # each game once, without its extra files (the other discs of a multi-disc game)
    labels = [f"{themeart.set_emoji(x)} {x['name']}  ({len(m & catalog)} on {system['name']}"
              + (f", {len(m - catalog)} not in storage)" if m - catalog else ")") for (x, _), m in zip(shown, mains)]
    extras = [[]] * len(shown)

    def mark():
        done = synced()
        def count(keys):
            have, total = len(keys & catalog & done), len(keys & catalog)
            return "➖" if total == 0 else "✅" if have == total else f"{have}/{total}"

        extras[:] = [[(f"  {count(m)}", "cyan")] for m in mains]

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
                           preview=lambda i: previews.collection(themeart.set_art(shown[i][0])) if i < len(shown) else None)
    if i is None:
        return None
    return shown[i][0]


class GameFilters:
    """What a system's games list is narrowed to (a set's games and one of its series, past surprises, scraped metadata)
    and the hotkeys that change it, for the card and collection editors. system is a systems.json entry or its view in a games list."""
    KEYS = (SET_KEY, SERIES_KEY, META_KEY, PAST_SURPRISE_KEY, CLEAR_KEY)

    def __init__(self, system):
        self.system = system
        self.meta = Metadata(system["bucket"])
        self.set = None  # (set name, bucket keys, set emoji) the list is narrowed to
        self.set_games = None  # the set self.set narrows to, its games on this system only
        self.series = None  # the series of set_games the list is narrowed to as well
        self.meta_filt = {}  # {metadata field: value} the list is narrowed to as well
        self.past = None  # bucket keys of the past surprises the list is narrowed to

    def keep(self, key, skip=None):
        """Whether the filters (all but the skip field's metadata one) show a row."""
        wanted = {f: v for f, v in self.meta_filt.items() if f != skip}
        return ((self.set is None or key in self.set[1])
                and (self.series is None or key in listedit.series_keys(self.set_games, self.series))
                and (self.past is None or key in self.past)
                and (not wanted or metafilter.matches(self.meta.get().get(key, {}), wanted)))

    def describe(self):
        """The filters line of the list: what it is narrowed to, or empty."""
        parts = ([f"{self.set[2]} {self.set[0]} only"] if self.set else []) \
            + ([f"🎮 {self.series}"] if self.series else []) \
            + (["🎁 past surprises only"] if self.past is not None else []) \
            + ([metafilter.describe(self.meta_filt)] if self.meta_filt else [])
        return f"{' · '.join(parts)} (c clear filters)" if parts else ""

    def handle(self, pressed, keys, place, choose_set):
        """Apply a filter hotkey; returns whether pressed was one. keys: every row's bucket key; place: the list's
        picker.carry_place (c clears its / filter too); choose_set(current set name): pick_set's chosen set, or None."""
        if pressed == CLEAR_KEY:
            self.set = self.set_games = self.series = self.past = None
            self.meta_filt.clear()
            place.get("session", {}).pop("query", None)  # the / filter too
        elif pressed == PAST_SURPRISE_KEY:
            self.past = surprise.past_keys(self.system["bucket"]) or None
            if self.past is None:
                edit.note(ui.yellow(f"ℹ️  No past surprises on {self.system['name']}."))
        elif pressed == SERIES_KEY:
            if self.set_games is None:
                edit.note(ui.yellow(f"ℹ️  Narrow {self.system['name']} to a set with s first, then pick one of its series."))
            else:
                self.series = pick_series(self.set_games, self.series) or self.series
        elif pressed == META_KEY:
            pick_meta(self.system, self.meta, self.meta_filt, lambda field: [k for k in keys if self.keep(k, field)])
        elif pressed == SET_KEY:
            chosen = choose_set(self.set and self.set[0])
            if chosen:
                if chosen["name"] != (self.set and self.set[0]):
                    self.series = None
                self.set = (chosen["name"], set_filter(chosen, self.system), themeart.set_emoji(chosen))
                self.set_games = {"name": chosen["name"],
                                  "games": [g for g in chosen["games"] if g.get("system") == self.system["bucket"]]}
        else:
            return False
        return True


def _work_out(picks, shown, others, card_usages, to_fetch):
    """What a games list's status adds its rows to, from the card as edited so far: the systems it doesn't show
    (others: their usage without BIOS, and those with something picked) and each shown SystemPicks' game costs.
    card_usages: as for edit_system."""
    card = picks.card()  # with the picks, set references and exclusions as edited so far
    usages = budget.system_usages(card, others) if card_usages is None else {x["bucket"]: card_usages[x["bucket"]] for x in others}
    parts = list(usages.values())  # without BIOS: it is added once, with the shown systems', in _status
    costs = {sp.bucket: budget.game_costs(card, sp.system, [r[1] for r in sp.rows]) for sp in shown}
    return {"others": budget.Usage(sum(p.bytes for p in parts), sum(p.count for p in parts), any(p.partial for p in parts)),
            "picked": [x for x in others if budget.picked(usages[x["bucket"]])],
            "costs": {b: c for b, (c, _) in costs.items()}, "partial": {b: p for b, (_, p) in costs.items()},
            "fetch": budget.card_fetch_bytes(card, others, to_fetch) if to_fetch else None}


def _status(work, now, capacity, to_fetch):
    """A games list's status_of: _work_out's rest of the card plus the shown systems as they are now, now being
    [(SystemPicks, {bucket key: synced})], with the BIOS of every system with something picked counted once."""
    picked = [(sp, [k for k, st in states.items() if st]) for sp, states in now]
    bios = budget.bios_usage(work["picked"] + [sp.system for sp, keys in picked if keys])
    mine = sum(work["costs"][sp.bucket].get(k, 0) for sp, keys in picked for k in keys)
    partial = work["others"].partial or bios.partial or any(keys and work["partial"][sp.bucket] for sp, keys in picked)
    total = budget.Usage(work["others"].bytes + mine + bios.bytes,
                         work["others"].count + sum(len(keys) for _, keys in picked), partial)
    fetch = None if to_fetch is None else work["fetch"] + sum(budget.fetch_bytes(sp.system, keys, to_fetch)
                                                              for sp, keys in picked)
    return status_of(total, capacity, fetch, count=False)  # the whole card's file count says little here


def _row_extras(sp, work, key, notes, state):
    """A game row's columns: files, set note, lock, size (blank where it has none)."""
    out = [("", "dim"), ("", "dim"), ("", "cyan"), ("", "dim")]
    costs = work["costs"][sp.bucket]
    if key in sp.groups:
        out[0] = (f"  🔗 {len(sp.groups[key])} files", "dim")
    elif key in sp.bundled:
        out[0] = (f"  🔗 {len(sp.bundled[key]) + 1} files", "dim")
    if key in notes:  # the note ends in the set's emoji and name (edit.cover_notes)
        out[1] = (f"  {notes[key].split(': ', 1)[-1]}", "cyan" if state else "dim")
    if key in sp.locked_from:
        out[2] = (f"  {sp.locked_from[key]}", "cyan")
    if key in costs:
        out[3] = (f"  {size_text(costs[key])}", "dim")
    elif key in sp.in_storage:
        out[3] = (f"  {SIZING}", "dim")
    return out


def _variant_mark(picks, key):
    """The row column marking a game one of whose variants is on the card (blank otherwise)."""
    on = any(picks.on_card(v["bucket"]) for v in picks.variants.get(key, ()))
    return ("  🔀 variant", "cyan") if on else ("", "dim")


def _locked_note(sp, key):
    """Why a collection or surprise game row can't be switched off ("" for any other row)."""
    return f"From {sp.locked_from[key]}; take it off the card to remove this game" if key in sp.locked_from else ""


def _note_text(sp, key):
    """The note of a game picked on its system ("" when it has none)."""
    game = next((g for g in sp.games if g.get("bucket") == key), None)
    return game.get("note", "") if game else ""


def _on_note(sp, key, text):
    """Save a game's note (`w`); the message the list shows."""
    if not edit.set_note({"games": sp.games}, key, text):
        return "Switch the game on and press Enter first, then add its note"
    return "Note saved" if text else "Note cleared"


def _toggle_variant(picks, key, title):
    """v on a game row: toggle its variant on the card, picked from a list when it has several. Whether one was."""
    found = picks.variants.get(key, [])
    if len(found) > 1:
        i = picker.filter_list(f"Variants of {title}",
                               [f"{'✅' if picks.on_card(v['bucket']) else '⬜'} {v['note']}" for v in found])
        found = [] if i is None else [found[i]]
    if found:
        picks.toggle_variant(found[0])
    return bool(found)


def edit_system(name, system, setup, to_fetch=None, card_usages=None):
    """A card's games of one system: the whole storage folder, searchable, filterable to a set's games and by scraped
    metadata. Saves to cards.json when left; returns whether anything changed. to_fetch: as for edit_card.
    card_usages: budget.system_usages of the card as saved, over every system it can play (edit_card keeps them), so
    the other systems aren't counted again."""
    bucket = system["bucket"]
    cards = store.load_cards()
    picks = cardpicks.CardPicks(name, setup, cards)
    if picks.full(bucket):
        edit.note(ui.yellow(f"ℹ️  {system['name']} is a full system: every file in its storage folder is downloaded, "
                            "so there is no game list to edit."))
        return False
    filters = GameFilters(system)
    try:
        sp = picks.system(system)
    except s3.ERRORS as e:
        edit.note(ui.yellow(f"⚠️  Couldn't list {system['name']} in storage: {e}"))
        return False
    others = [x for x in can_play(store.repo_json("systems"), setup) if x["bucket"] != bucket]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = _work_out(picks, [sp], others, card_usages, to_fetch)
    start = sp.states(picks.cover())

    pending = None  # (rows shown, notes, states before) of the pass on screen, applied if Ctrl-C ends it
    place = {}  # picker.carry_place's: the last pass's row, filter text, view and scroll
    try:
        while True:
            notes = picks.cover()
            base = sp.states(notes)
            kept = {r[1] for r in sp.rows if filters.keep(r[1])}
            shown = [r for r in sp.rows if r[1] in kept and sp.playlist_of.get(r[1]) not in kept]  # a shown playlist hides its discs
            keys = [r[1] for r in shown]
            index = {k: i for i, k in enumerate(keys)}
            links = [[index[m] for m in sp.groups.get(k, ()) if m in index] for k in keys]
            session = {"sel": [base[k] for k in keys]}
            picker.carry_place(place, keys, session)  # where the last pass was, when it listed the same games
            extras = [_row_extras(sp, work, k, notes, st) + [_variant_mark(picks, k)]
                      for k, st in zip(keys, session["sel"])]

            def status(state):
                now = dict(base)
                now.update(sp.changes(keys, base, state))
                return _status(work, [(sp, now)], capacity, to_fetch)

            pending = (keys, notes, base, session)
            result = picker.filter_list(f"✏️  {system['name']} on {name} — ✅ synced, ⬜ not, 📦 from a set",
                                        [r[3] for r in shown], multi=True, initial=[start[k] for k in keys],
                                        extras=extras, hint=GAMES_HINT, hotkeys=(*GameFilters.KEYS, VARIANT_KEY),
                                        key_help=GAMES_KEYS, filters=filters.describe(),
                                        status=status, row_note=lambda i: edit.variant_line(
                                            keys[i], picks.variants, picks.parents, picks.system_names, picks.on_card),
                                        session=session, note_text=lambda i: _note_text(sp, keys[i]),
                                        on_note=lambda i, text: _on_note(sp, keys[i], text),
                                        preview=lambda i: previews.game_thumb(keys[i]) if i < len(keys) else None,
                                        preview_width=previews.GAME_WIDTH,
                                        links=links, locked=[k in sp.locked_from for k in keys],
                                        locked_note=[_locked_note(sp, k) for k in keys])
            pending = None
            sp.apply(keys, notes, base, session["sel"] if isinstance(result, tuple) else result)
            if not isinstance(result, tuple):
                break
            if result[0] == VARIANT_KEY:
                if result[1] is not None and _toggle_variant(picks, keys[result[1]], sp.titles[keys[result[1]]]):
                    work = _work_out(picks, [sp], others, card_usages, to_fetch)
            else:
                filters.handle(result[0], [r[1] for r in sp.rows], place, lambda current: pick_set(
                    system, list(picks.sets_by_id.values()), sp.games, sp.titles, {r[1] for r in sp.rows}, current,
                    lambda: {k for k, v in sp.states(picks.cover()).items() if v}))
    except KeyboardInterrupt:  # Ctrl-C: keep the toggles
        if pending:
            keys, notes, base, session = pending
            sp.apply(keys, notes, base, session["sel"])
        picks.save()
        raise
    return picks.save()


def set_view_keys(game_set, systems):
    """[(system, bucket key, files)] of a set's games on the systems, in file order, each key once."""
    by_bucket = {s["bucket"]: s for s in systems}
    out, seen = [], set()
    for g in game_set["games"]:
        s, key = by_bucket.get(g.get("system")), g.get("bucket")
        if s and key and key not in seen:
            seen.add(key)
            out.append((s, key, list(g.get("files", []))))
    return out


def pick_series(game_set, current=None):
    """The series of the set's games picked from a list (with its game count), or None; notes when the set has none."""
    found = listedit.series_of(game_set)
    if not found:
        edit.note(ui.yellow(f"ℹ️  {game_set['name']} has no series."))
        return None
    labels = [f"{n}  ({c} games)" for n, c in found]
    i = picker.filter_list(f"🎮 Series in {game_set['name']}", labels,
                           cursor=next((j for j, (n, _) in enumerate(found) if n == current), 0))
    return None if i is None else found[i][0]


def edit_set(name, game_set, setup, to_fetch=None, card_usages=None):
    """A card's games of one set over every system it can play, in one list (category, then system and title), toggled
    as in edit_system; games not in storage are left out, a full system's are on and locked. Saves to cards.json when
    left; returns whether anything changed. to_fetch, card_usages: as for edit_system."""
    cards = store.load_cards()
    picks = cardpicks.CardPicks(name, setup, cards)
    playable = can_play(store.repo_json("systems"), setup)
    found = set_view_keys(game_set, playable)
    sps = {}  # {system bucket: SystemPicks} of the systems with set games, but full ones
    for s in {s["bucket"]: s for s, _, _ in found if not picks.full(s["bucket"])}.values():
        try:
            sps[s["bucket"]] = picks.system(s)
        except s3.ERRORS as e:
            edit.note(ui.yellow(f"⚠️  Couldn't list {s['name']} in storage: {e}"))
            return False
    kept = [(s, key, files) for s, key, files in found  # a row of its system (not an unlisted Vita DLC), in storage
            if s["bucket"] not in sps or key in sps[s["bucket"]].titles and key in sps[s["bucket"]].in_storage]
    files_of = {key: files for _, key, files in kept}
    present = {k for key, files in files_of.items() for k in (key, *files)}  # the rest are left out: no warning
    rows = edit.set_rows({"games": [g for g in game_set["games"] if g.get("bucket") in files_of]},
                         {s["bucket"]: s for s in playable}, lambda _s: present)
    listed = [r for r in rows if r[0]["bucket"] not in sps  # a shown playlist hides its discs
              or sps[r[0]["bucket"]].playlist_of.get(r[1]) not in files_of]
    series_filter = None  # the series the list is narrowed to
    others = [x for x in playable if x["bucket"] not in sps]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = _work_out(picks, list(sps.values()), others, card_usages, to_fetch)

    def row_states(bases):
        """{bucket key: synced} for every row, from each system's SystemPicks.states."""
        return {key: s["bucket"] not in sps or bases[s["bucket"]][key] for s, key, _, _ in rows}
    start = row_states({b: sp.states(picks.cover()) for b, sp in sps.items()})
    pending = None  # (apply, session) of the pass on screen, applied if Ctrl-C ends it
    place = {}  # picker.carry_place's: the last pass's row, filter text, view and scroll
    try:
        while True:
            notes = picks.cover()
            bases = {b: sp.states(notes) for b, sp in sps.items()}
            base = row_states(bases)
            wanted = listedit.series_keys(game_set, series_filter) if series_filter else None
            shown = [r for r in listed if wanted is None or r[1] in wanted]
            keys = [r[1] for r in shown]
            sp_of = [sps.get(r[0]["bucket"]) for r in shown]  # None on a full system
            index = {k: i for i, k in enumerate(keys)}
            links = [[index[m] for m in sp.groups.get(k, ()) if m in index] if sp else [] for k, sp in zip(keys, sp_of)]
            session = {"sel": [base[k] for k in keys]}
            picker.carry_place(place, keys, session)
            extras = [_row_extras(sp, work, k, notes, st) + [_variant_mark(picks, k)] if sp else []
                      for k, sp, st in zip(keys, sp_of, session["sel"])]

            def switched(state):
                """{system bucket: (keys, states)} of the rows this pass switched, each with its files."""
                out = {}
                for k, sp, want in zip(keys, sp_of, state):
                    if sp and want != base[k]:
                        ks, ws = out.setdefault(sp.bucket, ([], []))
                        for f in (k, *files_of[k]):
                            if f in bases[sp.bucket]:
                                ks.append(f)
                                ws.append(want)
                return out

            def status(state):
                moved = switched(state)
                now = []
                for b, sp in sps.items():
                    states = dict(bases[b])
                    if b in moved:
                        states.update(sp.changes(moved[b][0], bases[b], moved[b][1]))
                    now.append((sp, states))
                return _status(work, now, capacity, to_fetch)

            def apply(state):
                for b, (ks, ws) in switched(state).items():
                    sps[b].apply(ks, notes, bases[b], ws)

            pending = (apply, session)
            result = picker.filter_list(
                f"{themeart.set_emoji(game_set)} {game_set['name']} on {name} — ✅ synced, ⬜ not, 📦 from a set",
                [r[3] for r in shown], multi=True, initial=[start[k] for k in keys], extras=extras,
                hint=SET_GAMES_HINT, hotkeys=(VARIANT_KEY, SERIES_KEY, CLEAR_KEY), key_help=SET_GAMES_KEYS, status=status,
                filters=f"{series_filter} (c clear filters)" if series_filter else "",
                row_note=lambda i: edit.variant_line(keys[i], picks.variants, picks.parents, picks.system_names,
                                                     picks.on_card),
                session=session, note_text=lambda i: _note_text(sp_of[i], keys[i]),
                on_note=lambda i, text: _on_note(sp_of[i], keys[i], text),
                preview=lambda i: previews.game_thumb(keys[i]) if i < len(keys) else None,
                preview_width=previews.GAME_WIDTH, links=links, select_all=False,
                locked=[sp is None or k in sp.locked_from for k, sp in zip(keys, sp_of)],
                locked_note=[edit.FULL_SYSTEM_NOTE if sp is None else _locked_note(sp, k) for k, sp in zip(keys, sp_of)])
            pending = None
            apply(session["sel"] if isinstance(result, tuple) else result)
            if not isinstance(result, tuple):
                break
            if result[0] == CLEAR_KEY:
                series_filter = None
            elif result[0] == SERIES_KEY:
                series_filter = pick_series(game_set, series_filter) or series_filter
            elif result[1] is not None and _toggle_variant(picks, keys[result[1]], shown[result[1]][2]):
                work = _work_out(picks, list(sps.values()), others, card_usages, to_fetch)
    except KeyboardInterrupt:  # Ctrl-C: keep the toggles
        if pending:
            apply, session = pending
            apply(session["sel"])
        picks.save()
        raise
    return picks.save()
