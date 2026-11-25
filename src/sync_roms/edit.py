"""The --edit game list editor."""
import os
from collections import defaultdict

from . import languages, names, picker, previews, runtime, s3, store, surprise, tags, tagui, ui, vita


def note(text):
    """Say something: on an editor session's worker, on the session's next list's status line; else outside the list
    screen, waiting so the next redraw doesn't erase it."""
    if not picker.queue_note(text):
        _note_and_wait(text)


@ui.uses_terminal
def _note_and_wait(text):
    print(text)
    try:
        input(ui.dim("   Press Enter to continue "))
    except EOFError:
        pass


def snapshot(data):
    return {s["bucket"]: {g["bucket"] for g in s.get("games", []) if g.get("bucket")}
            for s in data["systems"]}


def notes_snapshot(data):
    return {g["bucket"]: g.get("note") for s in data["systems"] for g in s.get("games", []) if g.get("bucket")}


def set_note(s, key, text):
    """Set (or, with empty text, clear) the note of the game listed under key in system s. False if it isn't listed."""
    game = next((g for g in s["games"] if g.get("bucket") == key), None)
    if game is None:
        return False
    if text:
        game["note"] = text
    else:
        game.pop("note", None)
    return True


def note_text(games, key):
    """The note of the game listed under key in games ("" when it has none, or isn't listed)."""
    game = next((g for g in games if g.get("bucket") == key), None)
    return game.get("note", "") if game else ""


def save_note(games, key, text, covered=False):
    """Save the note typed after `w` for the game listed under key in games; the message the list shows. covered: the
    game is on only because a collection brings it, so it has no direct pick to hold a note."""
    if not set_note({"games": games}, key, text):
        if covered:
            return "Notes go only on games picked directly; this one comes from a collection"
        return "Switch the game on and press Enter first, then add its note"
    return "Note saved" if text else "Note cleared"


FULL_SYSTEM_NOTE = "Full system: every file in its folder is synced, so it can't be toggled"


def toggle_games(title, rows, hotkeys=(), hint=None, place=None, filters="", key_help=None, select_all=True, notes=True,
                 tag_filter=True):
    """_toggle_games over the rows tagui.FILTER keeps, reopened in the same place after `t` edited a game's tags or
    `s`/`c` changed the tag filter (the toggles made so far are applied first); the other keys are returned as it does.
    A caller that lists s or c in hotkeys handles them itself. tag_filter=False: every row is shown, with no s/c and no
    banner, for lists whose hidden rows would be acted on unseen (a suggestion review, a tag's own games)."""
    place = {} if place is None else place
    own = tuple(k for k in tagui.HOTKEYS if k not in hotkeys) if tag_filter else ()
    if own and key_help is None:  # the hint is what ? lists then: name s and c there
        hint = hint or (GAMES_HINT if notes else GAMES_HINT.replace(" · w note", ""))
        hint += " · s tag · c clear filters"
    helps = [h for h in tagui.KEYS_HELP if h[0] in own]
    while True:
        shown = [r for r in rows if tagui.FILTER.keep(r[1])] if tag_filter else rows
        line = tagui.FILTER.describe() if tag_filter else ""
        banner = tagui.banner() if line and line not in filters else ""
        if line and not shown and rows:
            banner += " · no games match the tag filter"
        pressed, i = _toggle_games(title, shown, (*hotkeys, *own), hint, place,
                                   " · ".join(x for x in (filters, banner) if x),
                                   None if key_help is None else [*key_help, *helps], select_all, notes)
        if pressed == tagui.TAG_KEY:
            if i is not None:
                tagui.edit_game_tags(shown[i][1], shown[i][2])
        elif pressed in own:
            tagui.handle_key(pressed, [r[1] for r in rows], place)
        else:
            return pressed


def _toggle_games(title, rows, hotkeys, hint, place, filters, key_help, select_all, notes):
    """Multi-select over rows of (system, bucket key, game title, label); adds/removes games in each system in place.
    Returns (key pressed or None, its row's index).

    Rows of a full system are shown on and locked: its whole storage folder is synced.
    hotkeys/hint/key_help: extra keys the list offers (the hint line to show, and the (keys, what they do) pairs ?
    lists). The toggles made so far are applied, and the key pressed is returned (None on Enter). place: a dict the caller keeps across calls, so a list of the same rows
    opens where the last one was left (picker.carry_place). filters: the caller's filters, for the filter line.
    select_all: False turns the list's `a` (toggle all shown) off. notes: False turns `w` off, for lists whose rows
    keep no notes.
    Ctrl-C applies the toggles made so far, then raises KeyboardInterrupt.
    """
    hint = hint or (GAMES_HINT if notes else GAMES_HINT.replace(" · w note", ""))
    hint += "" if " t tags" in hint else " · t tags"
    key_help = key_help if key_help is None or any(k == tagui.TAG_KEY for k, _ in key_help) else [*key_help, tagui.KEY_HELP]
    locked = [bool(s.get("full_system")) for s, *_ in rows]
    have = {}  # system bucket -> keys of its listed games, kept current as games are added and removed

    def listed(s):
        if s["bucket"] not in have:
            have[s["bucket"]] = {g["bucket"] for g in s["games"] if g.get("bucket")}
        return have[s["bucket"]]

    initial = [lock or key in listed(s) for lock, (s, key, _, _) in zip(locked, rows)]
    variants, parents = tags.variant_index()
    system_names = {s["bucket"]: s["name"] for s in store.repo_json("systems")}
    session = {"sel": list(initial)}
    picker.carry_place(place, [key for _, key, _, _ in rows], session)
    extras = [[languages.column(key), tag] for (_, key, _, _), tag in zip(rows, tagui.column([r[1] for r in rows]))]
    interrupted = False
    try:
        state = picker.filter_list(title, [label for *_, label in rows], multi=True, initial=initial, locked=locked,
                                   locked_note=[FULL_SYSTEM_NOTE if lock else "" for lock in locked], hint=hint, key_help=key_help,
                                   note_text=(lambda i: note_text(rows[i][0]["games"], rows[i][1])) if notes else None,
                                   on_note=(lambda i, text: save_note(rows[i][0]["games"], rows[i][1], text)) if notes else None,
                                   hotkeys=(*hotkeys, tagui.TAG_KEY), session=session, filters=filters,
                                   row_note=lambda i: variant_line(rows[i][1], variants, parents, system_names),
                                   select_all=select_all, extras=extras,
                                   **previews.game_pane([key for _, key, _, _ in rows]))
    except KeyboardInterrupt:  # Ctrl-C: the toggles made so far are applied, then the caller gets the Ctrl-C
        interrupted, state = True, session["sel"]
    pressed, at = state if isinstance(state, tuple) else (None, None)
    if pressed:
        state = session["sel"]
    removed = defaultdict(set)  # system bucket -> keys to drop from its games
    systems = {}
    for (s, key, name, _), on, was, lock in zip(rows, state, initial, locked):
        if lock:
            continue
        if on and not was:
            if key not in listed(s):
                listed(s).add(key)
                s["games"].append({"title": name, "bucket": key})
        elif was and not on:
            systems[s["bucket"]] = s
            removed[s["bucket"]].add(key)
    for bucket, keys in removed.items():
        systems[bucket]["games"] = [g for g in systems[bucket]["games"] if g.get("bucket") not in keys]
    if interrupted:
        raise KeyboardInterrupt
    return pressed, at


def system_rows(s, in_bucket):
    """Rows for toggle_games over every file of a system's storage folder (Vita DLC and updates only if listed)
    plus any listed game that isn't in it, sorted by title (an arcade set's or PICO-8 cart's scraped name)."""
    listed = {g["bucket"] for g in s["games"] if g.get("bucket")}

    def label(k, title):
        path = k.split("/", 1)[1]
        return (path if title == store.key_title(k) else f"{title} — {path}") \
            + ("" if k in in_bucket else "  ⚠️ not in storage")

    titled = [(k, names.title(k)) for k in in_bucket | listed if not vita.is_extra(k) or k in listed]
    return [(s, k, title, label(k, title)) for k, title in sorted(titled, key=lambda r: (store.sort_key(r[1]), r[0]))]


def edit_card_system(card, bucket, setup):
    """The card editor's game view for one system of a card (saved as it is left). Returns whether anything changed."""
    from . import cardedit
    system = next(x for x in store.repo_json("systems") if x["bucket"] == bucket)
    return cardedit.edit_system(card, system, setup)


def list_rows(listing, by_bucket, bucket_keys):
    """Rows for one games list (a collection, a tag's games), sorted by system and title.

    Entries for unknown systems are skipped."""
    rows, seen = [], set()
    for g in listing["games"]:
        s = by_bucket.get(g.get("system"))
        key = g.get("bucket")
        if not s or not key or key in seen:
            continue
        seen.add(key)
        title = g.get("title") or names.title(key)
        have = bucket_keys(s)
        warn = "" if s.get("full_system") or all(k in have for k in [key] + list(g.get("files", []))) \
            else "  ⚠️ not in storage"
        rows.append((s, key, title, f"{s['name']} — {title}{warn}"))
    return sorted(rows, key=lambda r: (r[0]["name"].lower(), store.sort_key(r[2])))


def valid_card_name(name, existing):
    """Why name can't be a new card's folder name, or None if it can."""
    if not name.strip():
        return "A card needs a name."
    if "/" in name or os.sep in name:
        return "A card name is a folder name, so it can't contain a slash."
    if name in existing:
        return f"There is already a card named {name}."
    return None


def variant_line(key, variants, parents, system_names, on=None):
    """The note under a game row about its variants, or a variant row's canonical game; "" for neither.

    on is None for a read-only view, else a callable(variant bucket) -> bool saying whether it is on the card.
    """
    found = variants.get(key)
    if found:
        if on is None:
            notes = "; ".join(v["note"] for v in found)
            return f"↳ Variants: {notes}" if len(found) > 1 else f"↳ Variant: {notes}"
        if len(found) > 1:
            return f"↳ {len(found)} variants (v picks): " + "; ".join(v["note"] for v in found)
        tail = " · ✅ on the card (v removes it)" if on(found[0]["bucket"]) else " (v adds it)"
        return f"↳ Variant: {found[0]['note']}{tail}"
    parent = parents.get(key)
    if parent:
        return f"Variant of {system_names.get(parent['system'], parent['system'])} — {parent['title']}"
    return ""


SETUP_KEY = "v"
DELETE_KEY = "d"
RENAME_KEY = "r"
MENU_HINT = "Enter open · Esc back · v device · r rename · d delete"
GAMES_HINT = "Space toggle · Enter done · / filter · w note · a all · o view · t tags"


def new_target(label, raw, setup=None):
    """The editing state of one games list: its systems and what they were when opened."""
    data = {"systems": store.apply_games(store.repo_json("systems"), raw)}
    return {"label": label, "data": data, "raw": dict(raw), "setup": setup, "was": snapshot(data),
            "was_full": {s["bucket"]: s["full_system"] for s in data["systems"]}, "was_notes": notes_snapshot(data)}


def drop_inapplicable(t, setup):
    """Empty the games and full-system flag of every system the card's device/firmware doesn't sync, and take its
    entry out of the saved games list (t["raw"]); every other entry there stays as it was saved."""
    for s in t["data"]["systems"]:
        if not store.system_applies(s, *setup):
            s["games"], s["full_system"] = [], False
            t["raw"].pop(s["bucket"], None)


def target_changes(t):
    """(added, removed) as {label: [text]} for a target; (new card's setup counts as a change on its own)."""
    now = snapshot(t["data"])
    added = {e: sorted(now[e] - t["was"][e]) for e in now if now[e] - t["was"][e]}
    removed = {e: sorted(t["was"][e] - now[e]) for e in now if t["was"][e] - now[e]}
    for s in t["data"]["systems"]:
        if s["full_system"] != t["was_full"][s["bucket"]]:
            (added if s["full_system"] else removed)[s["bucket"]] = ["(full system)"]
    notes = notes_snapshot(t["data"])
    for s in t["data"]["systems"]:
        for g in s["games"]:
            key = g.get("bucket")
            if key in t["was_notes"] and notes[key] != t["was_notes"][key]:
                added.setdefault(s["bucket"], []).append(f"{key} (note)")
    return added, removed


@picker.one_app
def edit_manifest():
    """The editor's top menu: Cards (each opens the card editor, which saves games as they change), Tags (each edit saved to storage),
    Collections (saved as you leave the collection editor), Device systems; device/firmware and device-system changes are reviewed and saved at the end."""
    print(ui.bold("✏️  Edit mode") + ui.dim(f"  {s3.access()}"))
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so nothing could be saved. "
                "Fix or move it first.", 3)
    manifest = store.load_manifest()

    targets = {}  # card name -> {"label", "setup"}: a device/firmware change saved with the review (games save at once)

    def saved_setup(name, cards=None):
        """The device and firmware saved for a card (cards: cards.json already loaded)."""
        return picker.saved_setup((store.load_cards() if cards is None else cards).get(name),
                                  manifest["devices"], manifest["layouts"])

    def open_card(name):
        from . import cardedit
        cardedit.edit_card(name, targets[name]["setup"] if name in targets else None)

    def fresh_target(name):
        """A card's pending device/firmware change as a target: its saved games, minus those the new setup doesn't sync."""
        t = targets[name]
        fresh = new_target(t["label"], store.card_games(name), t["setup"])
        drop_inapplicable(fresh, t["setup"])
        return fresh

    def add_card():
        existing = set(store.load_cards()) | set(targets)
        while True:
            name = ui.ask("➕ New card: its folder name, e.g. RGSP (a path works too; empty to cancel): ").strip()
            if not name:
                return
            if "/" in name:
                name = os.path.basename(os.path.normpath(name))
            problem = valid_card_name(name, existing)
            if not problem:
                break
            print(ui.yellow(f"  {problem}"))
        print(ui.dim("  Next: pick the device, then its firmware (Esc steps back or cancels)."))
        try:
            setup = picker.choose_setup(manifest)
        except SystemExit:
            return
        store.save_card(name, *setup)
        open_card(name)
        card = store.saved_card(name)
        if not (store.card_games(name) or card.get("collections") or card.get("guest") is True) and ui.confirm(
                f"Keep new card {name} with no games? (it keeps just the device and firmware)",
                cancellable=True) is False:
            store.delete_card(name)

    def change_setup(name):
        """Pick a different device and firmware for a card; saved with the other changes."""
        t = targets.get(name)
        saved = t["setup"] if t and t["setup"] else saved_setup(name)
        try:
            setup = picker.choose_setup(manifest, saved)
        except SystemExit:
            return
        targets[name] = {"label": f"💳 {name}", "setup": setup}

    def delete_card(name):
        if not ui.confirm(f"🗑️  Delete card {name} and its games now? (cards.json.bak keeps the copy from before this run)", default=False):
            return
        if name in store.load_cards():
            store.delete_card(name)
        targets.pop(name, None)

    def rename_card(name):
        if name not in store.load_cards():
            note(ui.yellow("ℹ️  Save this new card first, then rename it."))
            return
        new = ui.ask(f"✏️  New folder name for {name} (empty to cancel): ").strip()
        if not new:
            return
        problem = valid_card_name(new, set(store.load_cards()) | set(targets))
        if problem:
            note(ui.yellow(f"  {problem}"))
            return
        cards = store.load_cards()
        cards[new] = cards.pop(name)
        if store.write_cards(cards) and name in targets:
            t = targets.pop(name)
            t["label"] = f"💳 {new}"
            targets[new] = t

    def setup_extra(name, cards):
        """The card's device and firmware as a row suffix (cards: cards.json already loaded); a pending change in cyan."""
        t = targets.get(name)
        pending = bool(t and t["setup"])
        setup = t["setup"] if pending else saved_setup(name, cards)
        gift = f"  🎁 {'on' if surprise.enabled(cards.get(name)) else 'off'}"
        if not setup:
            return [("  ⚠️  no device set", "red"), (gift, "dim")]
        return [(f"  {setup[0]['name'] if setup[0] else 'Full'} · {manifest['layouts'][setup[1]]['label']}",
                 "cyan" if pending else "dim"), (gift, "dim")]

    def pending_count(key):
        return sum(len(v) for part in target_changes(fresh_target(key)) for v in part.values()) if key in targets else 0

    def pending_extra(key):
        n = pending_count(key)
        return [(f"  {n} change(s)", "cyan")] if n else []

    device_pos = [0]  # the device list's row, kept while it is reopened after each device
    overlay_pending = {}  # device id -> (system ids added, system ids removed) relative to the repo defaults

    def edit_device_systems():
        """Pick a device, then toggle which systems it recommends; saved as the add/remove overlay."""
        defaults = store.device_defaults(manifest["systems"])
        by_sort = sorted(manifest["systems"], key=store.system_sort_key)
        names = {s["bucket"]: s["name"] for s in by_sort}
        devices = manifest["devices"]
        extras = [[("  edited", "cyan")] if d["id"] in overlay_pending else [] for d in devices]
        i = picker.filter_list("🧩 Which device's recommended systems?", [d["name"] for d in devices], extras=extras,
                               hint="/ filter · Enter open · Esc back", cursor=device_pos[0])
        if i is None:
            return False
        device_pos[0] = i
        d = devices[i]
        base = defaults.get(d["id"], {}).get("systems", [])
        ids = list(names)
        labels = [f"{names[x]}" + ("" if x in base else "  (not in the default)") for x in ids]
        state = picker.filter_list(f"🧩 {d['name']} — ✅ synced for this device", labels, multi=True,
                                   initial=[x in d["systems"] for x in ids])
        now = {x for x, on in zip(ids, state) if on}
        add, remove = sorted(now - set(base)), sorted(set(base) - now)
        saved_all = store.load_overlay()
        saved_overlay = saved_all.get(d["id"]) if isinstance(saved_all, dict) else None
        saved_overlay = saved_overlay if isinstance(saved_overlay, dict) else {}
        if (add, remove) == (sorted(saved_overlay.get("add", [])), sorted(saved_overlay.get("remove", []))):
            overlay_pending.pop(d["id"], None)  # nothing changed from what is saved
        elif add or remove or saved_overlay:
            overlay_pending[d["id"]] = (add, remove)  # ([], []) drops the saved entry
        d["systems"] = [x for x in base if x in now] + [x for x in ids if x in now and x not in base]
        return True

    def edit_cards():
        """The card list: open a card, add one, or change/rename/delete the highlighted one. Esc goes back."""
        pos = 0
        while True:
            saved = store.load_cards()
            cards = sorted(set(saved) | {k for k in targets if k is not None})
            n = len(cards)
            options = [f"💳 {name}" for name in cards] + ["➕ New card"]
            extras = [setup_extra(name, saved) + pending_extra(name) for name in cards] + [[]]
            i = picker.filter_list("💳 Which card?  (Esc = back)", options, extras=extras,
                                   hotkeys=(SETUP_KEY, DELETE_KEY, RENAME_KEY), hint=MENU_HINT, cursor=pos)
            if i is None:
                return
            pos = i[1] if isinstance(i, tuple) else i
            if isinstance(i, tuple):
                if i[1] < n:
                    {SETUP_KEY: change_setup, DELETE_KEY: delete_card, RENAME_KEY: rename_card}[i[0]](cards[i[1]])
            elif i < n:
                open_card(cards[i])
            else:
                add_card()

    def edit_tags():
        """The tags in storage, saved as they are changed; a failure (SystemExit) returns here instead of ending the editor."""
        from . import tageditor
        try:
            tageditor.edit_tags()
        except SystemExit:
            pass  # the reason is a note, on the menu

    def edit_collections():
        from . import collectionedit
        collectionedit.edit_collections()

    def menu():
        """The top menu. Returns True to review and save, False to quit without saving."""
        try:
            while True:
                options = ["💳 Cards", "🏷️ Tags", "💖 Collections", "🧩 Device systems", "✅ Done (review & save)", "🚪 Quit (card games are already saved)"]
                extras = [[("  " + str(len(targets)) + " pending", "cyan")] if targets else [],
                          [], [], [("  " + str(len(overlay_pending)) + " edited", "cyan")] if overlay_pending else [], [], []]
                i = picker.filter_list("✏️  What do you want to edit?  (Esc = review & save)", options, extras=extras,
                                       hint="Enter open · Esc review & save")
                if i is None or i == 4:
                    return True
                if i == 0:
                    edit_cards()
                elif i == 1:
                    edit_tags()
                elif i == 2:
                    edit_collections()
                elif i == 3:
                    while edit_device_systems():
                        pass
                else:
                    if not changed_targets() and not overlay_pending or ui.confirm("Discard your pending changes and quit?", default=False):
                        return False
        except KeyboardInterrupt:
            print(ui.yellow("\n🛑 Interrupted — card games are saved; collection changes, if any, were offered for saving or review; pending device and device-system changes are kept: review them below."))
            return True

    def changed_targets():
        return {k: fresh_target(k) for k in targets}

    def print_changes(changed, cap):
        print(ui.bold("\n📝 Changes"))
        for key, t in changed.items():
            added, removed = target_changes(t)
            print(ui.bold(f"  {t['label']}") + ui.dim("  (device/firmware)"))
            for label, group, sign, col in (("added", added, "➕", ui.green), ("removed", removed, "➖", ui.red)):
                for esde, ks in group.items():
                    print(col(f"  {sign} {esde}: {len(ks)} {label}"))
                    ui.print_head(ks, cap, lambda k: k.split("/", 1)[1] if "/" in k else k)
        for dev_id, (add, remove) in overlay_pending.items():
            dev = next(d for d in manifest["devices"] if d["id"] == dev_id)
            print(ui.bold(f"  🧩 {dev['name']} (device-systems.json)"))
            for sid in add:
                print(ui.green(f"  ➕ {sid}"))
            for sid in remove:
                print(ui.red(f"  ➖ {sid}"))
        print(ui.dim("  (Removing only drops a game from the list; the file stays in storage.)"))

    while True:
        if not menu():
            print(ui.yellow("👋 Quit without saving the device changes (card games are already saved)."))
            return 0
        changed = changed_targets()
        if not changed and not overlay_pending:
            print(ui.yellow("👋 Nothing else to save (card games are saved as you edit them)."))
            return 0
        print_changes(changed, runtime.MAX_MISSING_SHOWN)
        answer = ui.choose("💾 Save these changes?", "sedl", "s", "s save · e keep editing · d discard · l list every change",
                             esc="e")
        while answer == "l":
            print_changes(changed, 10 ** 6)
            answer = ui.choose("💾 Save these changes?", "sed", "s", "s save · e keep editing · d discard", esc="e")
        if answer == "e":
            continue
        if answer == "d":
            print(ui.yellow("👋 Not saved."))
            return 0
        break
    for key, t in changed.items():
        if t["setup"]:
            store.save_card(key, *t["setup"])
    saved = store.save_lists({k: t["raw"] for k, t in changed.items() if any(target_changes(t))})
    if overlay_pending:
        store.save_overlay(overlay_pending)
    if not saved:
        print(ui.red("❌ Some changes were not saved (see above)."))
        return 3
    print(ui.green("🎉 Saved") + ui.dim(f"  ({store.data_dir()}; versions from before this run kept as .bak)"))
    return 0
