"""The --edit game list editor."""
import os
import sys
from collections import defaultdict

from . import names, picker, previews, runtime, s3, store, ui, vita


def note(text):
    """Say something outside the list screen and wait, so the next redraw doesn't erase it."""
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


FULL_SYSTEM_NOTE = "Full system: every file in its folder is synced, so it can't be toggled"


def toggle_games(title, rows, extras=None, covered=None, excluded=None, hotkeys=(), hint=None, place=None, filters=""):
    """Multi-select over rows of (system, bucket key, game title, label); adds/removes games in each system in place.

    extras: {bucket key: [more bucket keys]} added or removed together with that row's key.

    Rows of a full system are shown on and locked: its whole storage folder is synced.
    covered: optional callable (system, bucket key) -> note or None; rows with a note are shown on and locked
    with that note (e.g. games a set reference already syncs).
    excluded: {system bucket: [keys]}, updated in place. When given, covered rows can be switched off (they start on
    unless listed) and the off ones are recorded there; only full systems stay locked.
    hotkeys/hint: extra keys the list offers (and the hint line to show). The toggles made so far are applied, and the
    key pressed is returned (None on Enter). place: a dict the caller keeps across calls, so a list of the same rows
    opens where the last one was left (picker.carry_place). filters: the caller's filters, for the filter line.
    Ctrl-C applies the toggles made so far, then raises KeyboardInterrupt.
    """
    notes = [FULL_SYSTEM_NOTE if s.get("full_system") else covered(s, key) if covered else None
             for s, key, _, _ in rows]
    optional = [bool(n) and excluded is not None and not s.get("full_system") for n, (s, *_) in zip(notes, rows)]
    locked = [bool(n) and not o for n, o in zip(notes, optional)]
    have = {}  # system bucket -> keys of its listed games, kept current as games are added and removed

    def listed(s):
        if s["bucket"] not in have:
            have[s["bucket"]] = {g["bucket"] for g in s["games"] if g.get("bucket")}
        return have[s["bucket"]]

    initial = [(key not in excluded.get(s["bucket"], ())) if o else l or key in listed(s)
               for o, l, (s, key, _, _) in zip(optional, locked, rows)]
    def note_text(i):
        game = next((g for g in rows[i][0]["games"] if g.get("bucket") == rows[i][1]), None)
        return game.get("note", "") if game else ""

    def on_note(i, text):
        s, key = rows[i][:2]
        if not set_note(s, key, text):
            return "Switch the game on and press Enter first, then add its note"
        return "Note saved" if text else "Note cleared"

    variants, parents = store.variant_index(store.load_sets())
    system_names = {s["bucket"]: s["name"] for s in store.repo_json("systems")}
    session = {"sel": list(initial)}
    if place is not None:
        picker.carry_place(place, [key for _, key, _, _ in rows], session)
    interrupted = False
    try:
        state = picker.filter_list(title, [label for *_, label in rows], multi=True, initial=initial, locked=locked,
                                   locked_note=[n or "" for n in notes], hint=hint or GAMES_HINT, note_text=note_text,
                                   on_note=on_note, hotkeys=hotkeys, session=session, filters=filters,
                                   row_note=lambda i: variant_line(rows[i][1], variants, parents, system_names),
                                   preview=lambda i: previews.game(rows[i][1]) if i < len(rows) else None)
    except KeyboardInterrupt:  # Ctrl-C: the toggles made so far are applied, then the caller gets the Ctrl-C
        interrupted, state = True, session["sel"]
    pressed = state[0] if isinstance(state, tuple) else None
    if pressed:
        state = session["sel"]
    removed = defaultdict(set)  # system bucket -> keys to drop from its games
    systems = {}
    for (s, key, name, _), on, was, lock, opt in zip(rows, state, initial, locked, optional):
        if lock:
            continue
        if opt:
            if on != was:
                keys = set(excluded.get(s["bucket"], ())) ^ {key}
                excluded[s["bucket"]] = sorted(keys)
            continue
        keys = [key] + list((extras or {}).get(key, []))
        if on and not was:
            for k in keys:
                removed[s["bucket"]].discard(k)
                if k not in listed(s):
                    listed(s).add(k)
                    s["games"].append({"title": name if k == key else names.title(k), "bucket": k})
        elif was and not on:
            systems[s["bucket"]] = s
            removed[s["bucket"]].update(keys)
    for bucket, keys in removed.items():
        if keys and bucket in systems:
            systems[bucket]["games"] = [g for g in systems[bucket]["games"] if g.get("bucket") not in keys]
    if interrupted:
        raise KeyboardInterrupt
    return pressed


def system_rows(s, in_bucket):
    """Rows for toggle_games over every file of a system's storage folder (Vita DLC and updates only if listed)
    plus any listed game that isn't in it."""
    listed = {g["bucket"] for g in s["games"] if g.get("bucket")}
    return [(s, k, names.title(k),
             k.split("/", 1)[1] + ("" if k in in_bucket else "  ⚠️ not in storage"))
            for k in sorted(in_bucket | listed, key=str.lower) if not vita.is_extra(k) or k in listed]


def edit_card_system(card, bucket, setup):
    """The card editor's game view for one system of a card (saved as it is left). Returns whether anything changed."""
    from . import cardedit
    system = next(x for x in store.repo_json("systems") if x["bucket"] == bucket)
    return cardedit.edit_system(card, system, setup)


def set_rows(game_set, by_bucket, bucket_keys):
    """Rows for one set, grouped by category (in file order) then sorted by system and title.

    Entries for unknown systems are skipped."""
    rows, seen = [], set()
    order = {}
    for g in game_set["games"]:
        s = by_bucket.get(g.get("system"))
        key = g.get("bucket")
        if not s or not key or key in seen:
            continue
        seen.add(key)
        title = g.get("title") or names.title(key)
        have = bucket_keys(s)
        warn = "" if s.get("full_system") or all(k in have for k in [key] + list(g.get("files", []))) \
            else "  ⚠️ not in storage"
        cat = g.get("category") or ""
        order.setdefault(cat, len(order))
        rows.append((cat, (s, key, title, f"{cat + ' — ' if cat else ''}{s['name']} — {title}{warn}")))
    return [r for _, r in sorted(rows, key=lambda c: (order[c[0]], c[1][0]["name"].lower(), c[1][2].lower()))]


def valid_card_name(name, existing):
    """Why name can't be a new card's folder name, or None if it can."""
    if not name.strip():
        return "A card needs a name."
    if "/" in name or os.sep in name:
        return "A card name is a folder name, so it can't contain a slash."
    if name in existing:
        return f"There is already a card named {name}."
    return None


def cover_notes(sets_by_id, own_set_ids):
    """Why games are synced without being in the list being edited.

    Returns {bucket key: note}, from the list's own set references.
    """
    keys = {}
    for sid in own_set_ids:
        for g in store.set_games(sets_by_id[sid]) if sid in sets_by_id else []:
            keys.setdefault(g["bucket"], f"Full set: {sets_by_id[sid]['name']}")
    return keys


def variant_line(key, variants, parents, system_names, on=None):
    """The note under a set game row about its variants, or a variant row's canonical game; "" for neither.

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


def toggle_set_ref(sets_on, set_id):
    """The set ids with set_id switched on or off."""
    return [i for i in sets_on if i != set_id] if set_id in sets_on else sets_on + [set_id]


SETUP_KEY = "v"
DELETE_KEY = "d"
RENAME_KEY = "r"
MENU_HINT = "Enter open · Esc back · v device · r rename · d delete"
GAMES_HINT = "Space toggle · Enter done · / filter · w note · a all · o view"


def new_target(label, raw, setup=None):
    """The editing state of one games list: its systems, set references and what they were when opened."""
    data = {"systems": store.apply_games(store.repo_json("systems"), raw)}
    sets_on = store.list_sets(raw)
    return {"label": label, "data": data, "sets_on": sets_on, "setup": setup, "was": snapshot(data),
            "was_full": {s["bucket"]: s["full_system"] for s in data["systems"]}, "was_sets": list(sets_on),
            "was_notes": notes_snapshot(data)}


def drop_inapplicable(t, setup):
    """Empty the games and full-system flag of every system the card's device/firmware doesn't sync."""
    for s in t["data"]["systems"]:
        if not store.system_applies(s, *setup):
            s["games"], s["full_system"] = [], False


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
    on, was = set(t["sets_on"]), set(t["was_sets"])
    if on - was:
        added[store.SETS_KEY] = sorted(on - was)
    if was - on:
        removed[store.SETS_KEY] = sorted(was - on)
    return added, removed


def edit_manifest():
    """The editor's top menu: Cards (each opens the card editor, which saves games as they change), Sets (opens a PR),
    Collections (saved as you leave the collection editor), Device systems; device/firmware and device-system changes are reviewed and saved at the end."""
    print(ui.bold("✏️  Edit mode") + ui.dim(f"  {s3.access()}"))
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so nothing could be saved. "
                "Fix or move it first.", 3)
    manifest = store.load_manifest()
    names = {s["bucket"] for s in manifest["systems"]}
    for game_set in store.load_sets():
        for g in game_set["games"]:
            if g.get("system") not in names:
                print(ui.yellow(f"⚠️  Set {game_set['name']}: unknown system {g.get('system')!r}, skipped"), file=sys.stderr)

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
        if not store.card_games(name) and not ui.confirm(
                f"Keep new card {name} with no games? (it keeps just the device and firmware)"):
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
        if not setup:
            return [("  ⚠️  no device set", "red")]
        return [(f"  {setup[0]['name'] if setup[0] else 'Full'} · {manifest['layouts'][setup[1]]['label']}",
                 "cyan" if pending else "dim")]

    def pending_count(key):
        return sum(len(v) for part in target_changes(fresh_target(key)) for v in part.values()) if key in targets else 0

    def pending_extra(key):
        n = pending_count(key)
        return [(f"  {n} change(s)", "cyan")] if n else []

    overlay_pending = {}  # device id -> (system ids added, system ids removed) relative to the repo defaults

    def edit_device_systems():
        """Pick a device, then toggle which systems it recommends; saved as the add/remove overlay."""
        defaults = store.device_defaults(manifest["systems"])
        by_sort = sorted(manifest["systems"], key=store.system_sort_key)
        names = {s["bucket"]: s["name"] for s in by_sort}
        devices = manifest["devices"]
        extras = [[("  edited", "cyan")] if d["id"] in overlay_pending else [] for d in devices]
        i = picker.filter_list("🧩 Which device's recommended systems?", [d["name"] for d in devices], extras=extras,
                               hint="/ filter · Enter open · Esc back")
        if i is None:
            return False
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
        while True:
            saved = store.load_cards()
            cards = sorted(set(saved) | {k for k in targets if k is not None})
            n = len(cards)
            options = [f"💳 {name}" for name in cards] + ["➕ New card"]
            extras = [setup_extra(name, saved) + pending_extra(name) for name in cards] + [[]]
            i = picker.filter_list("💳 Which card?  (Esc = back)", options, extras=extras,
                                   hotkeys=(SETUP_KEY, DELETE_KEY, RENAME_KEY), hint=MENU_HINT)
            if i is None:
                return
            if isinstance(i, tuple):
                if i[1] < n:
                    {SETUP_KEY: change_setup, DELETE_KEY: delete_card, RENAME_KEY: rename_card}[i[0]](cards[i[1]])
            elif i < n:
                open_card(cards[i])
            else:
                add_card()

    def edit_sets():
        """The repo's sets; opens a PR and needs git and gh, so a missing tool returns here instead of ending the editor."""
        from . import setedit
        try:
            setedit.edit_sets()
        except SystemExit:
            pass  # the reason is already printed
        note("")  # keep what it printed (a PR link, why it stopped) on screen until the menu redraws

    def edit_collections():
        from . import collectionedit
        collectionedit.edit_collections()
        note("")  # keep what it printed on screen until the menu redraws

    def menu():
        """The top menu. Returns True to review and save, False to quit without saving."""
        try:
            while True:
                options = ["💳 Cards", "📦 Sets", "💖 Collections", "🧩 Device systems", "✅ Done (review & save)", "🚪 Quit without saving"]
                extras = [[("  " + str(len(targets)) + " pending", "cyan")] if targets else [],
                          [], [], [("  " + str(len(overlay_pending)) + " edited", "cyan")] if overlay_pending else [], [], []]
                i = picker.filter_list("✏️  What do you want to edit?  (Esc = review & save)", options, extras=extras,
                                       hint="Enter open · Esc review & save")
                if i is None or i == 4:
                    return True
                if i == 0:
                    edit_cards()
                elif i == 1:
                    edit_sets()
                elif i == 2:
                    edit_collections()
                elif i == 3:
                    while edit_device_systems():
                        pass
                else:
                    if not changed_targets() and not overlay_pending or ui.confirm("Discard your pending changes and quit?", default=False):
                        return False
        except KeyboardInterrupt:
            print(ui.yellow("\n🛑 Interrupted — card games are saved; collection and set changes, if any, were offered for saving or review; pending device and device-system changes are kept: review them below."))
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
                    for k in ks[:cap]:
                        print(ui.dim(f"       {k.split('/', 1)[1] if '/' in k else k}"))
                    if len(ks) > cap:
                        print(ui.dim(f"       … and {len(ks) - cap} more"))
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
            print(ui.yellow("👋 Quit without saving the device changes (card games were saved as you edited them)."))
            return 0
        changed = changed_targets()
        if not changed and not overlay_pending:
            print(ui.yellow("👋 Nothing else to save (card games are saved as you edit them)."))
            return 0
        print_changes(changed, runtime.MAX_MISSING_SHOWN)
        answer = ui.choose("💾 Save these changes?", "sedl", "s", "s save · e keep editing · d discard · l list every change")
        while answer == "l":
            print_changes(changed, 10 ** 6)
            answer = ui.choose("💾 Save these changes?", "sed", "s", "s save · e keep editing · d discard")
        if answer == "e":
            continue
        if answer == "d":
            print(ui.yellow("👋 Not saved."))
            return 0
        break
    for key, t in changed.items():
        if t["setup"]:
            store.save_card(key, *t["setup"])
    saved = store.save_lists({k: store.dump_list(t["data"]["systems"], t["sets_on"])
                              for k, t in changed.items() if any(target_changes(t))})
    if overlay_pending:
        store.save_overlay(overlay_pending)
    if not saved:
        print(ui.red("❌ Some changes were not saved (see above)."))
        return 3
    print(ui.green("🎉 Saved") + ui.dim(f"  ({store.data_dir()}; versions from before this run kept as .bak)"))
    return 0
