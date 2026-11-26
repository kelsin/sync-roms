"""The card editor: every system a card's device can play (recommended ones marked) with its picks and space used,
and each system's games with tag and scraped-metadata filters. Changes are saved to cards.json as they are made."""
import json
import queue
import threading

from . import budget, cardpicks, collections as colls, edit, guest, inventory, languages, listedit, metafilter, picker, previews, s3, scrape_plan, spruce_themes, store, surprise, tagui, tags, themeart, ui, usersettings

FULL_KEY = "f"
OFF_KEY = "x"
SET_KEY = tagui.SET_KEY
CLEAR_KEY = tagui.CLEAR_KEY
CLEAR_ALL_KEY = "D"
COLLECTIONS_KEY = "l"
SETTINGS_KEY = "S"
KEEP_KEY = "K"
GUEST_KEY = "F"
PAST_SURPRISE_KEY = "p"
META_KEY = "m"
VARIANT_KEY = "v"
ALL_KEY = "a"
LIST_HINT = "a all games · f full · s tag · c clear · l colls · S settings"
GAMES_HINT = "Space toggle · Enter done · m meta · p past · v variant"
META_HINT = "Enter list its values · Esc back"
VALUES_HINT = "Enter narrow to it · Esc back · / filter"
COLLECTIONS_HINT = "Enter show its games · Space/Tab toggle the collection · / filter"
ALL_GAMES_HINT = "Space toggle · Enter done · v variant"
LIST_KEYS = [("Enter", "the system's games"), ("f", "full system: every file in its folder (again to undo)"),
             ("x", "turn the system off on this card: nothing of it syncs, its picks stay (again to turn it back on)"),
             ("a", "every game across this card's systems"),
             ("s", "narrow every game to tags (the filter stays on in every list), then list them"),
             ("c", "clear the tag filter"), ("l", "collections on this card"),
             ("S", "settings menu: Surprise, theme, collections and RAOfflineProxy on or off, and the systems Surprise may use"),
             ("F", "guest card: a friend's card; syncs only copy ROMs, BIOS and scrapes (again to undo)"),
             ("D", "clear every pick and full system from the card")]
KEEP_HINT = " · K keep"
KEEP_KEYS = [("K", "pick every card file that matches a storage game")]
TAGS_HELP = ("s", "narrow by tags: games with every ✅ tag and no 🚫 one")
GAMES_KEYS = [TAGS_HELP, ("m", "narrow by scraped metadata (developer, genre, year...)"),
              ("p", "only the games that were surprises lately"), ("v", "the game's variants on other systems"),
              tagui.KEY_HELP, tagui.REPEAT_HELP, tagui.BULK_HELP, ("c", "clear the search, tag, metadata and surprise filters")]
COLLECTION_GAMES_HINT = "Space toggle · Enter done · v variant"
COLLECTION_GAMES_KEYS = [("v", "the game's variants on other systems"), tagui.KEY_HELP, tagui.REPEAT_HELP, tagui.BULK_HELP,
                         *tagui.KEYS_HELP]
ALL_GAMES_KEYS = COLLECTION_GAMES_KEYS
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


def shown_rows(sp, keep):
    """The rows of a SystemPicks a games list shows for keep(key): a shown playlist hides its discs."""
    kept = {r[1] for r in sp.rows if keep(r[1])}
    return [r for r in sp.rows if r[1] in kept and sp.playlist_of.get(r[1]) not in kept]


def _picks_stamp(name):
    """What of a card's saved picks its systems' rows depend on: each system's full flag and the keys it lists (a pick
    missing from storage, a Vita DLC or update, is a row of its own)."""
    out = []
    for bucket, entry in sorted(store.card_games(name).items()):
        full = isinstance(entry, dict) and bool(entry.get("full_system"))
        listed = entry if isinstance(entry, list) else []
        out.append((bucket, full, frozenset(g.get("bucket") for g in listed if isinstance(g, dict))))
    return tuple(out)


def match_counts(name, setup, systems, memo):
    """{system bucket: rows its games list shows} while a tag filter is on, else None; None for a system that is full
    or can't be listed. Counted as the list groups its rows (discs and records under their lead), so it equals the
    list's own count. memo: a dict the caller keeps; the counts are worked out again only when the filter, the tags,
    the card's picks (_picks_stamp) or the storage cache changed."""
    if not tagui.FILTER.describe():
        return None
    data = tags.load()  # kept in the memo and compared with `is`: an id could be reused by a replacement
    stamp = (inventory.version(), frozenset(tagui.FILTER.required), frozenset(tagui.FILTER.excluded), tagui.FILTER.untagged,
             _picks_stamp(name))
    if memo.get("stamp") != stamp or memo.get("tags") is not data:
        picks, out = cardpicks.CardPicks(name, setup), {}
        for s in systems:
            try:
                out[s["bucket"]] = None if picks.full(s["bucket"]) else len(shown_rows(picks.system(s), tagui.FILTER.keep))
            except s3.ERRORS:
                out[s["bucket"]] = None
        memo["stamp"], memo["tags"], memo["counts"] = stamp, data, out
    return memo["counts"]


def system_labels(card, systems, recommended, usages, full_sizes, matches=None):
    """(labels, extras) for the system list, in the given order: recommended systems get a ⭐; each picked system
    shows its count and size (… while not sized), then each system its size as a full system (full_sizes: {bucket:
    budget.full_usage}, a missing one not worked out yet; an empty folder shows none). A full system shows its files
    and full size instead of its picks, then 🗂️. The first column starts with the state: 🟢 full system, 🟡 some games picked, ⚪ none.
    matches: {bucket: games the tag filter shows} (match_counts), a last column "N match" while a filter is on."""
    games = card.get("games") or {}
    off = store.systems_off(card)
    labels, extras = [], []
    for s in systems:
        rec = s["bucket"] in recommended
        labels.append(("⭐ " if rec else "   ") + s["name"])
        u, f = usages.get(s["bucket"]), full_sizes.get(s["bucket"])
        unknown = f is None or f.partial
        row = [("  ⚪", "dim"), ("", "dim"), ("", "dim")]
        entry = games.get(s["bucket"])
        if s["bucket"] in off:
            row[0] = ("  🚫 off", "red")
            if unknown or f.count:
                row[2] = (f"  🗂️  {SIZING if unknown else size_text(f.bytes)} full", "dim")
        elif isinstance(entry, dict) and entry.get("full_system"):
            files = SIZING if unknown else f.count
            row = [(f"  🟢 {files} file" + ("" if files == 1 else "s"), "green"),
                   (f"  {SIZING if unknown else size_text(f.bytes)}", "dim"), ("  🗂️  full system", "cyan")]
        else:
            if u and budget.picked(u):
                row[:2] = [(f"  🟡 {u.count or SIZING} picked", "green"), (f"  {SIZING if u.partial else size_text(u.bytes)}", "dim")]
            if unknown or f.count:
                row[2] = (f"  🗂️  {SIZING if unknown else size_text(f.bytes)} full", "dim")
        if matches is not None:
            n = matches.get(s["bucket"])
            row.append(("", "dim") if n is None else (f"  {n} match", "cyan" if n else "dim"))
        extras.append(row)
    return labels, extras


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
            edit.note(ui.yellow(f"ℹ️  No scraped metadata for {store.short_name(system)} yet."))
            return
        extras = [[(f"  {filters[f]}", "cyan")] if f in filters else [] for f, _ in metafilter.FIELDS]
        i = picker.filter_list(f"🏷️  Filter {store.short_name(system)} by", [label for _, label in metafilter.FIELDS],
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
        j = picker.filter_list(f"🏷️  {label} on {store.short_name(system)}", values,
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
    return {**store.saved_card(name, cards), "layout": setup[1]}


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


def toggle_off(name, bucket):
    """Turn a system off on a card, or back on, and save it. The card's picks stay."""
    cards = store.load_cards()
    entry = dict(store.saved_card(name, cards))
    off = store.systems_off(entry) ^ {bucket}
    if off:
        entry["systems_off"] = sorted(off)
    else:
        entry.pop("systems_off", None)
    cards[name] = entry
    store.write_cards(cards)


def toggle_guest(name):
    """Make a card a guest card, or an ordinary one again, and save it. Returns the new state."""
    cards = store.load_cards()
    entry = dict(store.saved_card(name, cards))
    on = not guest.is_guest(entry)
    if on:
        entry["guest"] = True
    else:
        entry.pop("guest", None)
    cards[name] = entry
    store.write_cards(cards)
    return on


@picker.one_app
def edit_card(name, setup=None, to_fetch=None, card_match=None, on_guest=None):
    """The card's system list. setup: (device or None for Full, layout) to edit with instead of the saved one.
    to_fetch(system, keys): the keys not on the card yet, when editing from a sync; the status then shows how much
    a sync would download. card_match(system, keys): the keys of the system's storage files that are on the card, when
    editing from a sync; it enables K. on_guest(): called when F turns the guest flag on, when editing from a sync
    (it reseeds the card's picks)."""
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
    stocked = {s["bucket"] for s in listedit.stocked(systems)}
    systems = [s for s in systems  # a missing or empty folder has nothing to pick, unless it already has picks
               if budget.picked(usages[s["bucket"]]) or s["bucket"] in stocked]
    full = FullSizes({"layout": setup[1]}, systems)  # each system's size as a full system, kept for the session
    pos = 0
    match_memo = {}  # match_counts' memo: kept across passes
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
        matches = match_counts(name, setup, systems, match_memo)  # while a tag filter is on, each system's games it shows
        full.update()

        def work_out():
            card = card_entry(name, setup)
            view["total"] = budget.card_usage(card, systems, usages)
            view["fetch"] = budget.card_fetch_bytes(card, systems, to_fetch) if to_fetch else None
            return system_labels(card, systems, recommended, usages, full.sizes, matches)

        labels, extras = work_out()

        def poll():
            """Fill in the full sizes as the worker hands them over."""
            if full.update():
                extras[:] = system_labels(card_entry(name, setup), systems, recommended, usages, full.sizes, matches)[1]

        def on_hotkey(key, idx):
            """f and x switch full system and off in place, so the screen isn't torn down and redrawn."""
            nonlocal matches
            if key not in (FULL_KEY, OFF_KEY) or idx is None:
                return False
            if key == FULL_KEY and systems[idx]["bucket"] in store.systems_off(card_entry(name, setup)):
                return "This system is off on the card: turn it on with x first"
            (toggle_full if key == FULL_KEY else toggle_off)(name, systems[idx]["bucket"])
            usages[systems[idx]["bucket"]] = budget.system_usage(card_entry(name, setup), systems[idx])
            matches = match_counts(name, setup, systems, match_memo)  # a full system has no count
            extras[:] = work_out()[1]
            return True

        saved = store.load_cards().get(name)
        on = surprise.enabled(saved)
        one_theme = isinstance(saved, dict) and saved.get("layout") == "spruce" and saved.get("one_theme") is True
        i = picker.filter_list(f"💳 {name} — its systems (⭐ for the device) · 🎁 Surprise {'on' if on else 'off'}"
                               + (f" · 🎨 {spruce_themes.current(name) or 'one theme: none picked'}" if one_theme else "")
                               + (" · 👤 guest" if guest.is_guest(saved) else ""),
                               labels, extras=extras, cursor=pos, filters=tagui.banner(),
                               hotkeys=(FULL_KEY, OFF_KEY, ALL_KEY, SET_KEY, CLEAR_KEY, COLLECTIONS_KEY, SETTINGS_KEY, GUEST_KEY,
                                        CLEAR_ALL_KEY, *((KEEP_KEY,) if card_match else ())),
                               hint=LIST_HINT + (KEEP_HINT if card_match else ""),
                               key_help=LIST_KEYS + (KEEP_KEYS if card_match else []),
                               status=lambda _state: status_of(view["total"], capacity, view["fetch"]),
                               on_hotkey=on_hotkey, poll=poll,
                               preview=lambda i: previews.system(systems[i]) if i < len(systems) else None)
        if i is None:
            return
        if isinstance(i, tuple):
            key, pos = i  # never f or x: on_hotkey takes them
            if key == ALL_KEY:
                edit_all(name, setup, systems, to_fetch, usages)
                changed = ALL
            elif key == SET_KEY:
                edit_all(name, setup, systems, to_fetch, usages, pick_tags=True)
                changed = ALL
            elif key == CLEAR_KEY:
                tagui.handle_key(CLEAR_KEY, ())
            elif key == COLLECTIONS_KEY:
                chosen = pick_collections(name, {s["bucket"] for s in can_play(catalog["systems"], setup)},
                                          lambda: card_status(name, setup, systems, to_fetch), setup)
                if chosen:
                    edit_set(name, chosen, setup, to_fetch, usages)
                changed = ALL
            elif key == SETTINGS_KEY:
                settings_menu(name, catalog["systems"], playable)
                changed = ALL
            elif key == KEEP_KEY:
                keep_card_files(name, setup, systems, card_match)
                changed = ALL
            elif key == GUEST_KEY:
                if guest.is_guest(store.saved_card(name)) or ui.confirm(
                        f"Make {name} a guest card? Its picks are replaced by the ROMs found on the card, "
                        f"{'now' if on_guest else 'at its next sync'}, and its collections and surprises dropped.",
                        default=False):
                    if toggle_guest(name) and on_guest:
                        on_guest()
                changed = ALL
            elif key == CLEAR_ALL_KEY:
                if ui.confirm(f"🧹 Clear every pick and full system from {name}?", default=False):
                    store.update_card(name, games={}, **({"excluded": {}} if store.card_excluded(name) else {}))
                    changed = ALL
            continue
        pos = i
        if edit_system(name, systems[i], setup, to_fetch, usages):
            changed = systems[i]


def keep_card_files(name, setup, systems, card_match):
    """Pick, in every system that isn't a full one, the files already on the card that match a storage game."""
    picks = cardpicks.CardPicks(name, setup)
    added = touched = 0
    for system in systems:
        if picks.full(system["bucket"]):
            continue
        try:
            sp = picks.system(system)
        except s3.ERRORS as e:
            edit.note(ui.yellow(f"⚠️  Couldn't list {store.short_name(system)} in storage: {e}"))
            continue
        matched = card_match(system, list(sp.in_storage))
        n = sp.keep(sorted(matched))
        added, touched = added + n, touched + bool(n)
    picks.save()
    edit.note(f"Picked {added} card file(s) in {touched} system(s).")


def card_status(name, setup, systems, to_fetch=None):
    """status_of for the card as saved now, over the systems the card editor lists."""
    card = card_entry(name, setup)
    total = budget.card_usage(card, systems)
    fetch = budget.card_fetch_bytes(card, systems, to_fetch) if to_fetch else None
    return status_of(total, budget.card_capacity(card), fetch)


def settings_menu(name, systems, playable):
    """S in the system list: turn the card's Surprise, theme, custom collections or RAOfflineProxy on or off, pick the systems
    Surprise may use on every card or on this card (playable: the systems the card can play) and, on a spruce card, its one-theme mode and current theme."""
    state = lambda on: "on" if on else "off"
    pos = 0
    while True:
        entry = store.load_cards().get(name)
        spruce = isinstance(entry, dict) and entry.get("layout") == "spruce"
        current = entry.get("spruce_theme") if spruce else None
        current = current if isinstance(current, str) and current else None
        i = picker.filter_list("⚙️  Settings", [
            f"🎁 Surprise: {state(surprise.enabled(entry))}",
            f"🎨 Theme (Art Book Next, ES-DE theme, collection art): {state(store.card_flag(entry, 'theme'))}",
            f"💖 Collections (written to the frontend, Surprise's too): {state(store.card_flag(entry, 'custom_collections'))}",
            f"🏆 RAOfflineProxy (RetroAchievements offline proxy app): {state(store.card_flag(entry, 'raofflineproxy'))}",
            "Systems Surprise may use (every card)",
            "Systems Surprise may use (this card)",
            "Tags Surprise picks from (every card)",
            "Tags Surprise picks from (this card)",
            *([f"🎨 One theme only: {state(entry.get('one_theme') is True)}",
               f"🎨 Spruce theme: {current or 'none'}"] if spruce else [])], cursor=pos)
        if i is None:
            return
        pos = i
        if i == 0:
            toggle_surprise(name)
        elif i in (1, 2, 3):
            toggle_flag(name, ("theme", "custom_collections", "raofflineproxy")[i - 1])
        elif i == 4:
            pick_surprise_systems(systems)
        elif i == 5:
            pick_card_surprise_systems(name, playable)
        elif i == 6:
            pick_surprise_tags()
        elif i == 7:
            pick_card_surprise_tags(name)
        elif i == 8 and spruce:
            toggle_one_theme(name)
        elif i == 9 and spruce:
            pick_spruce_theme(name, current)


def toggle_one_theme(name):
    """Switch a spruce card's one-theme mode (one_theme: true, removed for off)."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return
    if entry.pop("one_theme", None) is True:
        store.write_cards(cards)
    else:
        store.update_card(name, one_theme=True)


def pick_spruce_theme(name, current):
    """Pick the card's current spruce theme, saved as spruce_theme (removed for none, kept on Esc)."""
    theme = spruce_themes.pick_one(f"🎨 Spruce theme ({name})", current)
    if theme is False:
        return
    if theme:
        store.update_card(name, spruce_theme=theme)
        return
    cards = store.load_cards()
    if isinstance(cards.get(name), dict) and cards[name].pop("spruce_theme", None) is not None:
        store.write_cards(cards)


def toggle_flag(name, field):
    """Switch a card's `theme`, `custom_collections` or `raofflineproxy` on or off (see store.set_card_flag); returns the new state."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return store.card_flag(entry, field)
    store.set_card_flag(entry, field, not store.card_flag(entry, field))
    store.write_cards(cards)
    return store.card_flag(entry, field)


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


def pick_card_surprise_systems(name, playable):
    """Check the systems Surprise may pick from on this card; the unchecked ones are saved as the card's
    surprise_excluded_systems (removed when none). Systems excluded on every card show unchecked."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return
    excluded = surprise.card_excluded_systems(entry)
    everywhere = surprise.excluded_systems()
    states = picker.filter_list(f"🎁 Systems Surprise may use ({name})",
                                [s["name"] + (" (off on every card)" if s["bucket"] in everywhere else "") for s in playable],
                                multi=True, initial=[s["bucket"] not in excluded | everywhere for s in playable])
    if states is None:
        return
    shown = {s["bucket"] for s in playable}
    off = sorted((excluded - shown) | (excluded & everywhere)
                 | {s["bucket"] for s, on in zip(playable, states) if not on and s["bucket"] not in everywhere})
    if off:
        entry["surprise_excluded_systems"] = off
    else:
        entry.pop("surprise_excluded_systems", None)
    store.write_cards(cards)


def _pick_tags(title, current):
    """Check the tags out of all of them; (the tag ids checked plus those of current that no tag has any more), or None
    when cancelled."""
    defs = tags.all_tags()
    ids = sorted(defs, key=lambda i: defs[i]["name"].casefold())
    states = picker.filter_list(title, [f"{defs[i]['emoji']} {defs[i]['name']}" for i in ids], multi=True,
                                initial=[i in current for i in ids])
    if states is None:
        return None
    return sorted((current - set(ids)) | {i for i, on in zip(ids, states) if on})


def pick_surprise_tags():
    """Check the tags Surprise picks from on every card; saved as surprise_tags (removed when none are checked)."""
    chosen = _pick_tags("🎁 Tags Surprise picks from (every card)",
                        set(usersettings.load_settings().get("surprise_tags") or ()))
    if chosen is not None:
        usersettings.save_setting("surprise_tags", chosen or None)


def pick_card_surprise_tags(name):
    """Check the tags Surprise picks from on this card (instead of the ones for every card); saved as the card's
    surprise_tags (removed when none are checked)."""
    cards = store.load_cards()
    entry = cards.get(name)
    if not isinstance(entry, dict):
        return
    ids = entry.get("surprise_tags")
    chosen = _pick_tags(f"🎁 Tags Surprise picks from ({name})", set(ids) if isinstance(ids, list) else set())
    if chosen is None:
        return
    if chosen:
        entry["surprise_tags"] = chosen
    else:
        entry.pop("surprise_tags", None)
    store.write_cards(cards)


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


def pick_collections(name, playable, card_status=None, setup=None):
    """Toggle the collections a card includes (Space/Tab, in place), saving each toggle at once; returns the
    collection Enter was pressed on (to open its games), or None. Each is shown with how many of its games are on
    systems in playable (system buckets the card syncs) and, with setup (device, layout), how many are on the card.
    card_status(): the card's size status, worked out again after each toggle."""
    found = colls.load_collections()
    if not found:
        edit.note(ui.yellow("ℹ️  No collections yet: make one in sync-roms collections edit "
                            "(or 💖 Collections in sync-roms edit)."))
        return
    entry = store.saved_card(name)
    saved = entry.get("collections")
    ids = [i for i in saved if isinstance(i, str)] if isinstance(saved, list) else []
    labels, not_playable, playable_games = [], [], []
    for c in found:
        playable_games.append([g for g in colls.collection_games(c) if g.get("system") in playable])
        not_playable.append(len(colls.collection_games(c)) - len(playable_games[-1]))
        labels.append(f"{themeart.art_emoji(c.get('art'))} {c['name']}")
    extras = [[] for _ in found]
    shown = {}

    def mark():
        picks = cardpicks.CardPicks(name, setup) if setup else None  # fresh: a toggle changes what is locked

        def have_text(games):
            have = sum(1 for g in games if picks.on_card(g["bucket"]))
            return "  ✅" if have == len(games) > 0 else f"  {have}/{len(games)}"
        def count_text(games, n):
            text = f"  {len(games)} playable" + (f", {n} not playable" if n else "")
            if tagui.FILTER.describe():  # the tag filter applies when the collection's games open
                text += f", {sum(1 for g in games if tagui.FILTER.keep(g['bucket']))} match"
            return (text, "dim")
        extras[:] = [[("  ✅ on the card" if c["id"] in ids else "", "green"),
                      *([(have_text(games), "cyan")] if picks else []), count_text(games, n)]
                     for c, games, n in zip(found, playable_games, not_playable)]
        shown["status"] = card_status() if card_status else None

    def on_hotkey(key, idx):
        if idx is None or key == CLEAR_KEY:
            return False
        cid = found[idx]["id"]
        ids.remove(cid) if cid in ids else ids.append(cid)
        store.update_card(name, collections=list(ids))
        mark()
        return True

    pos = 0
    while True:
        mark()
        i = picker.filter_list(f"💖 Collections on {name} (Space toggles · Enter opens)", labels, extras=extras,
                           hotkeys=(" ", "\t", CLEAR_KEY), on_hotkey=on_hotkey, hint=tagui.menu_hint(COLLECTIONS_HINT),
                           filters=tagui.banner(), cursor=pos,
                           key_help=[("Space/Tab", "put the collection on the card or take it off"),
                                     ("Enter", "show its games to pick them one by one"), tagui.KEYS_HELP[1]],
                           status=(lambda _state: shown["status"]) if card_status else None,
                           preview=lambda i: previews.card_collection(found[i].get("art"), entry) if i < len(found) else None)
        if isinstance(i, tuple) and i[0] == CLEAR_KEY:
            tagui.handle_key(CLEAR_KEY, ())
            pos = i[1] or 0
            continue
        return found[i] if isinstance(i, int) and i < len(found) else None


class GameFilters:
    """What a system's games list is narrowed to (tags, past surprises, scraped metadata) and the hotkeys that change
    it, for the card and collection editors. system is a systems.json entry or its view in a games list."""
    KEYS = (SET_KEY, META_KEY, PAST_SURPRISE_KEY, CLEAR_KEY)

    def __init__(self, system):
        self.system = system
        self.meta = Metadata(system["bucket"])
        self.tags = tagui.FILTER  # the tags every list is narrowed to
        self.meta_filt = {}  # {metadata field: value} the list is narrowed to as well
        self.past = None  # bucket keys of the past surprises the list is narrowed to

    def keep(self, key, skip=None):
        """Whether the filters (all but the skip field's metadata one) show a row."""
        wanted = {f: v for f, v in self.meta_filt.items() if f != skip}
        return (self.tags.keep(key)
                and (self.past is None or key in self.past)
                and (not wanted or metafilter.matches(self.meta.get().get(key, {}), wanted)))

    def describe(self, shown=None, total=None):
        """The filters line of the list: what it is narrowed to (with "N of M shown" when shown is fewer than total),
        or empty."""
        parts = ([self.tags.describe()] if self.tags.describe() else []) \
            + (["🎁 past surprises only"] if self.past is not None else []) \
            + ([metafilter.describe(self.meta_filt)] if self.meta_filt else [])
        return f"{' · '.join(parts)}{tagui.counts(shown, total)} (c clear filters)" if parts else ""

    def handle(self, pressed, keys, place):
        """Apply a filter hotkey; returns whether pressed was one. keys: every row's bucket key; place: the list's
        picker.carry_place (c clears its / filter too)."""
        if pressed == CLEAR_KEY:
            tagui.handle_key(pressed, keys, place)  # the tags and the / filter
            self.past = None
            self.meta_filt.clear()
        elif pressed == PAST_SURPRISE_KEY:
            self.past = surprise.past_keys(self.system["bucket"]) or None
            if self.past is None:
                edit.note(ui.yellow(f"ℹ️  No past surprises on {store.short_name(self.system)}."))
        elif pressed == META_KEY:
            pick_meta(self.system, self.meta, self.meta_filt, lambda field: [k for k in keys if self.keep(k, field)])
        elif pressed == SET_KEY:
            tagui.handle_key(pressed, keys, place)
        else:
            return False
        return True


def _work_out(picks, shown, others, card_usages, to_fetch, variant=None):
    """What a games list's status adds its rows to, from the card as edited so far: the systems it doesn't show
    (others: their usage without BIOS, and those with something picked) and each shown SystemPicks' game costs.
    card_usages: as for edit_system. variant: the system bucket v just changed; when it is one of the others, its
    usage in card_usages is counted again."""
    card = picks.card()  # with the picks and exclusions as edited so far
    if card_usages is not None:
        for x in others:
            if x["bucket"] == variant:
                card_usages[variant] = budget.system_usage(card, x)
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


def _row_extras(sp, work, key):
    """A game row's columns: files, lock, language flag, size (blank where it has none)."""
    out = [("", "dim"), ("", "cyan"), languages.column(key), ("", "dim")]
    costs = work["costs"][sp.bucket]
    if key in sp.groups:
        out[0] = (f"  🔗 {len(sp.groups[key])} files", "dim")
    elif key in sp.bundled:
        out[0] = (f"  🔗 {len(sp.bundled[key]) + 1} files", "dim")
    if key in sp.locked_from:
        out[1] = (f"  {surprise.LABEL if key in sp.surprise else sp.locked_from[key]}", "cyan")
    if key in costs:
        out[3] = (f"  {size_text(costs[key])}", "dim")
    elif key in sp.in_storage:
        out[3] = (f"  {SIZING}", "dim")
    return out


def _variant_mark(picks, key, on_card=None):
    """The row column marking a game one of whose variants is on the card (blank otherwise). on_card: picks.on_card,
    or a quicker answer from states already worked out."""
    on_card = on_card or picks.on_card
    on = any(on_card(v["bucket"]) for v in picks.variants.get(key, ()))
    return ("  🔀 variant", "cyan") if on else ("", "dim")


def _locked_note(sp, key):
    """Why a surprise game row can't be switched off ("" for any other row)."""
    return f"From {surprise.LABEL}; take it off the card to remove this game" if key in sp.surprise else ""


def _toggle_variant(picks, key, title):
    """v on a game row: toggle its variant on the card, picked from a list when it has several. The variant's system
    bucket, or None when none was."""
    found = picks.variants.get(key, [])
    if len(found) > 1:
        all_found, frozen, at = found, None, None  # at: the highlighted variant's place in all_found
        while True:  # t edits the highlighted variant's tags, then the list opens again on its row
            found = frozen or [v for v in all_found if tagui.FILTER.keep(v["bucket"])]
            frozen = None
            places = [all_found.index(v) for v in found]  # on the same variant after s or c, else the nearest shown
            cursor = min(range(len(found)), key=lambda j: (abs(places[j] - at), places[j])) if found and at is not None else 0
            i = picker.filter_list(f"Variants of {title}",
                                   [f"{'✅' if picks.on_card(v['bucket']) else '⬜'} {v['note']}" for v in found],
                                   extras=[[languages.column(v["bucket"]), tag]
                                           for v, tag in zip(found, tagui.column([v["bucket"] for v in found]))],
                                   hotkeys=(*tagui.TAG_KEYS, *tagui.HOTKEYS), cursor=cursor,
                                   key_help=[tagui.KEY_HELP, tagui.REPEAT_HELP, *tagui.KEYS_HELP],
                                   tag_info=tagui.summary([v["bucket"] for v in found]),
                                   filters=tagui.banner(len(found), len(all_found)) + (" · no variants match the tag filter" if all_found and not found else ""))
            if not isinstance(i, tuple):
                break
            pressed, i = i
            at = places[i] if i is not None else at
            if pressed in tagui.TAG_KEYS:
                tagui.tag_key(pressed, *((found[i]["bucket"], found[i]["note"]) if i is not None else (None, None)))
                frozen = found
            else:
                tagui.handle_key(pressed, [v["bucket"] for v in all_found])
        found = [] if i is None else [found[i]]
    if not found:
        return None
    picks.toggle_variant(found[0])
    return found[0]["bucket"].partition("/")[0]


def _games_pass(title, shown, picks, sps, files_of, start, work, capacity, to_fetch, place, **list_kw):
    """One pass of a card's games list over shown, rows of (system, bucket key, title, label), from the card as edited
    so far; the toggles are then folded into picks (on Ctrl-C too, which is raised again). sps: {system bucket:
    SystemPicks} of the rows' systems but the full ones, whose rows are on and locked; files_of: {bucket key: the files
    switched with it}; start: {bucket key: synced} when the editor opened; work: _work_out's; place:
    picker.carry_place's, kept across passes; list_kw: filter_list's arguments each list sets itself (hint, hotkeys,
    key_help, filters, select_all). Returns filter_list's result."""
    bases = {b: sp.states() for b, sp in sps.items()}
    keys = [r[1] for r in shown]
    sp_of = [sps.get(r[0]["bucket"]) for r in shown]  # None on a full system
    base = {k: sp is None or bases[sp.bucket][k] for k, sp in zip(keys, sp_of)}
    index = {k: i for i, k in enumerate(keys)}
    links = [[index[m] for m in sp.groups.get(k, ()) if m in index] if sp else [] for k, sp in zip(keys, sp_of)]
    session = {"sel": [base[k] for k in keys]}
    picker.carry_place(place, keys, session)  # where the last pass was, when it listed the same games
    hidden, seen = {}, set()  # {system bucket: (keys, states when the editor opened)} of what earlier passes switched
    outside = [0, 0]  # in rows this pass doesn't show, each multi-disc game once: (switched on, switched off)
    for k, was in start.items():
        b = k.partition("/")[0]
        group = sps[b].groups.get(k, [k]) if b in sps and k in bases[b] else ()
        if group and bases[b][k] != was and not any(m in index or m in seen for m in group):
            seen.update(group)
            outside[was] += 1
            ks, ws = hidden.setdefault(b, ([], []))
            for f in (k, *files_of.get(k, ())):
                if f in bases[b]:
                    ks.append(f)
                    ws.append(was)
    reverted = []

    def on_card(key):
        """picks.on_card, from this pass's states where the key's system has them."""
        b = key.partition("/")[0]
        return bases[b].get(key, False) if b in bases else picks.on_card(key)
    tag_marks = tagui.column(keys)
    extras = [(_row_extras(sp, work, k) + [_variant_mark(picks, k, on_card)]
               if sp else [("", "dim")] * 2 + [languages.column(k)]) + [tag]
              for k, sp, tag in zip(keys, sp_of, tag_marks)]

    def switched(state):
        """{system bucket: (keys, states)} of the rows this pass switched, each with its files."""
        out = {}
        for k, sp, want in zip(keys, sp_of, state):
            if sp and want != base[k]:
                ks, ws = out.setdefault(sp.bucket, ([], []))
                for f in (k, *files_of.get(k, ())):
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
            sps[b].apply(ks, bases[b], ws)

    try:
        result = picker.filter_list(
            title, [r[3] for r in shown], multi=True, initial=[start[k] for k in keys], extras=extras, status=status,
            row_note=lambda i: edit.variant_line(keys[i], picks.variants, picks.parents, picks.system_names,
                                                 picks.on_card),
            session=session, note_text=lambda i: edit.note_text(sp_of[i].games, keys[i]),
            on_note=lambda i, text: edit.save_note(
                sp_of[i].games, keys[i], text,
                covered=keys[i] in sp_of[i].collected and keys[i] not in sp_of[i].excluded),
            **previews.game_pane(keys), links=links, tag_info=tagui.summary(keys),
            locked=[sp is None or k in sp.surprise for k, sp in zip(keys, sp_of)],
            locked_note=[edit.FULL_SYSTEM_NOTE if sp is None else _locked_note(sp, k) for k, sp in zip(keys, sp_of)],
            outside=tuple(outside), on_revert=lambda: reverted.append(True), **list_kw)
    except KeyboardInterrupt:  # Ctrl-C: keep the toggles
        apply(session["sel"])
        raise
    apply(session["sel"] if isinstance(result, tuple) else result)
    for b, (ks, ws) in hidden.items() if reverted else ():  # u at Esc's question: what the pass hid goes back too
        sps[b].apply(ks, sps[b].states(), ws)
    return result


def edit_system(name, system, setup, to_fetch=None, card_usages=None):
    """A card's games of one system: the whole storage folder, searchable, filterable by tags and by scraped
    metadata. Saves to cards.json when left; returns whether anything changed. to_fetch: as for edit_card.
    card_usages: budget.system_usages of the card as saved, over every system it can play (edit_card keeps them), so
    the other systems aren't counted again; v brings the usage of its variant's system up to date in it."""
    bucket = system["bucket"]
    cards = store.load_cards()
    picks = cardpicks.CardPicks(name, setup, cards)
    if picks.full(bucket):
        edit.note(ui.yellow(f"ℹ️  {store.short_name(system)} is a full system: every file in its storage folder is downloaded, "
                            "so there is no game list to edit."))
        return False
    filters = GameFilters(system)
    try:
        sp = picks.system(system)
    except s3.ERRORS as e:
        edit.note(ui.yellow(f"⚠️  Couldn't list {store.short_name(system)} in storage: {e}"))
        return False
    others = [x for x in can_play(store.repo_json("systems"), setup) if x["bucket"] != bucket]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = _work_out(picks, [sp], others, card_usages, to_fetch)
    start = sp.states()

    place = {}  # picker.carry_place's: the last pass's row, filter text, view and scroll
    off_note = " · 🚫 off on this card" if bucket in store.systems_off(store.saved_card(name, cards)) else ""
    try:
        while True:
            shown = shown_rows(sp, filters.keep)
            total = len(shown_rows(sp, lambda _key: True))
            result = _games_pass(
                f"✏️  {store.short_name(system)} on {name} — ✅ synced, ⬜ not{off_note}", shown, picks, {bucket: sp}, {},
                start, work, capacity, to_fetch, place, hint=tagui.games_hint(GAMES_HINT), hotkeys=(*GameFilters.KEYS, VARIANT_KEY, *tagui.TAG_KEYS, tagui.BULK_KEY),
                key_help=GAMES_KEYS, filters=filters.describe(len(shown), total))
            if not isinstance(result, tuple):
                break
            if result[0] in tagui.TAG_KEYS:
                tagui.tag_key(result[0], *(shown[result[1]][1:3] if result[1] is not None else (None, None)))
            elif result[0] == tagui.BULK_KEY:
                tagui.bulk_tag([r[1] for r in picker.on_screen(place, shown)])
            elif result[0] == VARIANT_KEY:
                variant = result[1] is not None and _toggle_variant(picks, *shown[result[1]][1:3])
                if variant:
                    work = _work_out(picks, [sp], others, card_usages, to_fetch, variant)
            else:
                filters.handle(result[0], [r[1] for r in sp.rows], place)
    except KeyboardInterrupt:  # Ctrl-C: the pass on screen kept its toggles
        picks.save()
        raise
    return picks.save()


def edit_all(name, setup, systems, to_fetch=None, card_usages=None, pick_tags=False):
    """Every file of the systems' storage folders (from the storage cache) in one list, by title then system, toggled
    as in edit_set (a full system's on and locked) and narrowed by the tag filter. pick_tags: the tags are picked before
    the list opens, which then doesn't open when none is. Returns whether anything changed."""
    picks = cardpicks.CardPicks(name, setup)  # handed to edit_set, so each folder is listed once
    games = []
    for s in systems:
        try:
            in_storage = store.folder_keys(s["bucket"]) if picks.full(s["bucket"]) else picks.system(s).in_storage
        except s3.ERRORS as e:
            edit.note(ui.yellow(f"⚠️  Couldn't list {s['name']} in storage: {e}"))
            return False
        games += [{"system": s["bucket"], "bucket": key, "title": title, "label": label}
                  for _, key, title, label in listedit.system_rows({**s, "games": []}, in_storage)]
    return edit_set(name, {"name": "All games", "games": games}, setup, to_fetch, card_usages, all_games=True, picks=picks,
                    pick_tags=pick_tags)


def edit_set(name, game_set, setup, to_fetch=None, card_usages=None, all_games=False, picks=None, pick_tags=False):
    """A card's games of one collection over every system it can play, in one list (system, then title), toggled as in
    edit_system; games not in storage are left out, a full system's are on and locked. Saves to cards.json when left;
    returns whether anything changed. to_fetch, card_usages: as for edit_system. all_games: edit_all's list (its games
    carry their row label): by title then system, s narrows it by tags (pick_tags: picked before it opens; with none
    picked it doesn't). picks: the CardPicks to edit, when the caller already made one."""
    cards = store.load_cards()
    picks = picks or cardpicks.CardPicks(name, setup, cards)
    playable = {s["bucket"]: s for s in can_play(store.repo_json("systems"), setup)}
    found, seen = [], set()  # [(system, bucket key, files)] of the playable games, in file order, each key once
    for g in game_set["games"]:
        s, key = playable.get(g.get("system")), g.get("bucket")
        if s and key and key not in seen:
            seen.add(key)
            found.append((s, key, list(g.get("files", []))))
    sps = {}  # {system bucket: SystemPicks} of the systems with listed games, but full ones
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
    rows = edit.list_rows({"games": [g for g in game_set["games"] if g.get("bucket") in files_of]},
                          playable, lambda _s: present)
    if all_games:
        label_of = {g["bucket"]: g["label"] for g in game_set["games"]}
        rows = sorted(((s, key, title, f"{s['name']} — {label_of[key]}") for s, key, title, _ in rows),
                      key=lambda r: (store.sort_key(r[2]), r[0]["name"].lower()))
    listed = [r for r in rows if r[0]["bucket"] not in sps  # a shown playlist hides its discs
              or sps[r[0]["bucket"]].playlist_of.get(r[1]) not in files_of]
    if pick_tags:
        tagui.FILTER.pick({r[1] for r in listed})
        if not tagui.FILTER.active():
            return False
    others = [x for x in playable.values() if x["bucket"] not in sps]
    capacity = budget.card_capacity(card_entry(name, setup, cards))
    work = _work_out(picks, list(sps.values()), others, card_usages, to_fetch)

    opened = {b: sp.states() for b, sp in sps.items()}
    start = {key: s["bucket"] not in sps or opened[s["bucket"]][key] for s, key, _, _ in rows}
    place = {}  # picker.carry_place's: the last pass's row, filter text, view and scroll
    frozen = None  # the rows of the pass `t` was pressed in: shown again as they were, so the cursor stays put
    try:
        while True:
            shown = frozen or [r for r in listed if tagui.FILTER.keep(r[1])]
            frozen = None
            filters = tagui.banner(len(shown), len(listed))
            if not shown and listed:
                filters += " · no games match the tag filter"
            if all_games:
                emoji, hint, hotkeys, key_help = "🌐", tagui.games_hint(ALL_GAMES_HINT, select_all=tagui.FILTER.active()), (VARIANT_KEY, *tagui.TAG_KEYS, tagui.BULK_KEY, *tagui.HOTKEYS), ALL_GAMES_KEYS
                origin = ""
            else:
                emoji, hint, hotkeys, key_help = (themeart.collection_emoji(game_set), tagui.games_hint(COLLECTION_GAMES_HINT),
                                                  (VARIANT_KEY, *tagui.TAG_KEYS, tagui.BULK_KEY, *tagui.HOTKEYS), COLLECTION_GAMES_KEYS)
                origin = ", 💖 from a collection"
            result = _games_pass(
                f"{emoji} {game_set['name']} on {name} — ✅ synced, ⬜ not{origin}", shown, picks, sps, files_of,
                start, work, capacity, to_fetch, place, hint=hint, hotkeys=hotkeys, key_help=key_help, filters=filters,
                select_all=not all_games or tagui.FILTER.active())
            if not isinstance(result, tuple):
                break
            if result[0] in tagui.TAG_KEYS:
                tagui.tag_key(result[0], *(shown[result[1]][1:3] if result[1] is not None else (None, None)))
                frozen = shown
            elif result[0] == tagui.BULK_KEY:
                tagui.bulk_tag([r[1] for r in picker.on_screen(place, shown)])
                frozen = shown
            elif tagui.handle_key(result[0], {r[1] for r in listed}, place):
                pass
            elif result[1] is not None:
                variant = _toggle_variant(picks, *shown[result[1]][1:3])
                if variant:
                    work = _work_out(picks, list(sps.values()), others, card_usages, to_fetch, variant)
    except KeyboardInterrupt:  # Ctrl-C: the pass on screen kept its toggles
        picks.save()
        raise
    return picks.save()
