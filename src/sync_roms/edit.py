"""The --edit game list editor."""
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import picker, runtime, s3, store, ui


def note(text):
    """Say something outside the curses screen and wait, so the next redraw doesn't erase it."""
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


def toggle_games(title, rows, extras=None, covered=None, excluded=None):
    """Multi-select over rows of (system, bucket key, game title, label); adds/removes games in each system in place.

    extras: {bucket key: [more bucket keys]} added or removed together with that row's key.

    Rows of a full system are shown on and locked: its whole storage folder is synced.
    covered: optional callable (system, bucket key) -> note or None; rows with a note are shown on and locked
    with that note (e.g. games a set reference already syncs).
    excluded: {system bucket: [keys]}, updated in place. When given, covered rows can be switched off (they start on
    unless listed) and the off ones are recorded there; only full systems stay locked.
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

    state = picker.filter_list(title, [label for *_, label in rows], multi=True, initial=initial, locked=locked,
                               locked_note=[n or "" for n in notes], hint=GAMES_HINT, note_text=note_text, on_note=on_note)
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
                    s["games"].append({"title": name if k == key else store.key_title(k), "bucket": k})
        elif was and not on:
            systems[s["bucket"]] = s
            removed[s["bucket"]].update(keys)
    for bucket, keys in removed.items():
        if keys and bucket in systems:
            systems[bucket]["games"] = [g for g in systems[bucket]["games"] if g.get("bucket") not in keys]


def system_rows(s, in_bucket):
    """Rows for toggle_games over every file of a system's storage folder plus any listed game that isn't in it."""
    listed = {g["bucket"] for g in s["games"] if g.get("bucket")}
    return [(s, k, store.key_title(k),
             k.split("/", 1)[1] + ("" if k in in_bucket else "  ⚠️ not in storage"))
            for k in sorted(in_bucket | listed, key=str.lower)]


def edit_card_system(card, bucket, setup):
    """Toggle the games of one system in a card's extras (as --edit does) and save them. Returns whether anything changed.

    Games the card's own sets already sync are shown on and locked."""
    cards = store.load_cards()
    t = new_target(card, store.card_games(card, cards))
    drop_inapplicable(t, setup)
    s = next(x for x in t["data"]["systems"] if x["bucket"] == bucket)
    keys = cover_notes({x["id"]: x for x in store.load_sets()}, t["sets_on"])
    if s.get("full_system"):
        note(ui.yellow(f"ℹ️  {s['name']} is a full system: every file in its storage folder is downloaded, "
                       "so there is no game list to edit."))
        return False
    in_bucket = store.folder_keys(bucket)
    before = store.card_excluded(card, cards)
    excluded = {b: list(k) for b, k in before.items()}
    toggle_games(f"✏️  {s['name']} — ✅ synced to {card}, ⬜ not (set games can be switched off here)",
                 system_rows(s, in_bucket), covered=lambda _s, key: keys.get(key), excluded=excluded)
    excluded = {b: k for b, k in excluded.items() if k}
    changed = excluded != before
    if changed:
        store.update_card(card, excluded=excluded)
    if not any(target_changes(t)):
        return changed
    store.save_lists({card: store.dump_list(t["data"]["systems"], t["sets_on"])})
    return True


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
        title = g.get("title") or store.key_title(key)
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


def toggle_set_ref(sets_on, set_id):
    """The set ids with set_id switched on or off."""
    return [i for i in sets_on if i != set_id] if set_id in sets_on else sets_on + [set_id]


def toggle_full_system(s):
    s["full_system"] = not s["full_system"]


FULL_KEY = "f"
SETUP_KEY = "v"
DELETE_KEY = "d"
RENAME_KEY = "r"
FULL_HINT = "Enter open · f {what} · Esc back · / filter"
MENU_HINT = "Enter open · Esc save · v device · r rename · d delete"
GAMES_HINT = "Space toggle · Enter done · Esc back · / filter · w note · a all · o view"


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


def make_set_from_extras(t, sets, sets_by_id):
    """Save the games in a card target's extras as a personal set and add it to the open set lists.

    Returns the new set's id, or None when cancelled or there is nothing to save."""
    systems = [s for s in t["data"]["systems"] if s["games"]]
    if not systems:
        note(ui.yellow("ℹ️  This card has no extra games to make a set from."))
        return None
    while True:
        name = ui.ask(f"📦 Name for the new set of {sum(len(s['games']) for s in systems)} game(s) "
                      "(empty to cancel): ").strip()
        if not name:
            return None
        problem = store.personal_set_problem(name)
        if not problem:
            break
        print(ui.yellow(f"  {problem}"))
    set_id = store.save_personal_set(name, systems)
    new = store.read_set_file(os.path.join(store.personal_sets_dir(), set_id + ".json"), set_id)
    sets.append(new)
    sets.sort(key=lambda x: x["name"].lower())
    sets_by_id[set_id] = new
    print(ui.green(f"📦 Saved set {name}") + ui.dim(f"  ({store.personal_sets_dir()}); find it under By set"))
    return set_id


def edit_manifest():
    """Add/remove games in a card's list (browsing by system or by set), then save them."""
    print(ui.bold("✏️  Edit mode") + ui.dim(f"  {s3.access()}"))
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so nothing could be saved. "
                "Fix or move it first.", 3)
    manifest = store.load_manifest()
    repo_systems = manifest["systems"]
    print(ui.dim(f"📡 Listing {s3.location()}/ ..."))
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = ex.map(lambda s: store.folder_keys(s["bucket"]), repo_systems)
        bucket_keys = {s["bucket"]: keys for s, keys in zip(repo_systems, listings)}
    names = {s["bucket"] for s in repo_systems}
    sets = store.load_sets()
    sets_by_id = {x["id"]: x for x in sets}

    for game_set in sets:
        for g in game_set["games"]:
            if g.get("system") not in names:
                print(ui.yellow(f"⚠️  Set {game_set['name']}: unknown system {g.get('system')!r}, skipped"), file=sys.stderr)

    targets = {}  # card name -> editing state
    new_cards = set()  # cards made in this session

    def saved_setup(name, cards=None):
        """The device and firmware saved for a card (cards: cards.json already loaded)."""
        return picker.saved_setup((store.load_cards() if cards is None else cards).get(name),
                                  manifest["devices"], manifest["layouts"])

    def edit_target(t, is_card, setup=None):
        name = next((k for k, v in targets.items() if v is t), None)
        setup = (t["setup"] or setup or saved_setup(name)) if is_card else None
        systems_all = [s for s in t["data"]["systems"] if not setup or store.system_applies(s, *setup)]
        by_bucket = {s["bucket"]: s for s in systems_all}
        systems = sorted((s for s in systems_all if bucket_keys[s["bucket"]] or s["games"] or s.get("full_system")),
                         key=lambda s: s["name"].lower())
        where = f"{t['label']}'s extras"
        pos = {"system": 0, "set": 0}

        def cover():
            return cover_notes(sets_by_id, t["sets_on"])

        def edit_system():
            now = snapshot(t["data"])
            keys = cover()
            width = max((len(s["name"]) for s in systems), default=0)
            labels, extras = [], []
            covered_by = defaultdict(set)
            for k in keys:
                covered_by[k.split("/", 1)[0]].add(k)
            for s in systems:
                b = s["bucket"]
                changed = now[b] ^ t["was"][b]
                total = len(bucket_keys[b])
                whole = s.get("full_system")
                covered = covered_by[b]
                have = total if whole else len((now[b] | covered) & bucket_keys[b])
                missing = 0 if whole else len(now[b] - bucket_keys[b])
                labels.append(s["name"].ljust(width))
                row = [(f"  {have}", "green"), (f" / {total}", "dim")]
                if whole:
                    row.append(("  🗂️  full system", "cyan"))
                if missing:
                    row.append((f"  {missing} not in storage", "red"))
                if changed:
                    row.append((f"  {len(changed)} change(s)", "cyan"))
                extras.append(row)
            i = picker.filter_list("✏️  Pick a system to edit (Esc = back)", labels, extras=extras,
                            hint=FULL_HINT.format(what="full system"), cursor=pos["system"], hotkeys=(FULL_KEY,))
            if i is None:
                return False
            if isinstance(i, tuple):
                pos["system"] = i[1]
                s = systems[i[1]]
                toggle_full_system(s)
                return True
            pos["system"] = i
            s = systems[i]
            if s.get("full_system"):
                note(ui.yellow(f"ℹ️  {s['name']} is a full system: every file in its storage folder is "
                               "downloaded, so there is no game list to edit."))
                return True
            toggle_games(f"✏️  {s['name']} — ✅ in {where}, ⬜ in storage only",
                         system_rows(s, bucket_keys[s["bucket"]]),
                         covered=lambda _s, key: keys.get(key))
            return True

        def edit_set():
            if not sets:
                note(ui.yellow("ℹ️  No game sets found."))
                return False
            keys = cover()
            now = snapshot(t["data"])
            labels, extras = [], []
            for game_set in sets:
                entries = [(g.get("system"), g.get("bucket")) for g in game_set["games"] if g.get("system") in by_bucket]
                on = sum(1 for sid, key in entries if by_bucket[sid].get("full_system")
                         or key in now[sid] or key in keys)
                desc = f" — {game_set['description']}" if game_set["description"] else ""
                labels.append(f"{game_set['name']}  ({on}/{len(entries)} on){desc}")
                extras.append([("  📦 full set", "green")] if game_set["id"] in t["sets_on"] else [])
            i = picker.filter_list("✏️  Pick a set to edit (Esc = back)", labels, extras=extras,
                            hint=FULL_HINT.format(what="full set"), cursor=pos["set"], hotkeys=(FULL_KEY,))
            if i is None:
                return False
            if isinstance(i, tuple):
                pos["set"] = i[1]
                t["sets_on"] = toggle_set_ref(t["sets_on"], sets[i[1]]["id"])
                return True
            pos["set"] = i
            rows = set_rows(sets[i], by_bucket, lambda s: bucket_keys[s["bucket"]])
            if rows:
                files = {g["bucket"]: g["files"] for g in sets[i]["games"] if g.get("bucket") and g.get("files")}
                ref = "  📦 full set (f on the set list to stop syncing all of it)" if sets[i]["id"] in t["sets_on"] else ""
                toggle_games(f"✏️  {sets[i]['name']} — ✅ in {where}, ⬜ not{ref}", rows, files,
                             covered=lambda s, key: keys.get(key))
            else:
                note(ui.yellow(f"ℹ️  {sets[i]['name']} has no games to toggle."))
            return True

        while True:
            i = picker.filter_list(f"✏️  Edit {t['label']} (Esc = back)",
                                   ["By system", "By set"] + (["📦 Make a set from these extras"] if is_card else []))
            if i is None:
                break
            if i == 2:
                make_set_from_extras(t, sets, sets_by_id)
                continue
            while (edit_system, edit_set)[i]():
                pass

    def open_target(key, label, is_card):
        setup = None
        if key not in targets:
            cards = store.load_cards()
            raw = store.card_games(key, cards)
            targets[key] = new_target(label, raw)
            setup = saved_setup(key, cards) if is_card else None
            if setup:
                drop_inapplicable(targets[key], setup)
        edit_target(targets[key], is_card, setup)

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
        targets[name] = new_target(name, {}, setup)
        new_cards.add(name)
        edit_target(targets[name], True)
        if not any(target_changes(targets[name])) and not ui.confirm(
                f"Keep new card {name} with no extra games? (it saves just the device and firmware)"):
            del targets[name]
            new_cards.discard(name)

    def change_setup(name):
        """Pick a different device and firmware for a card; saved with the other changes."""
        t = targets.get(name)
        saved = t["setup"] if t and t["setup"] else saved_setup(name)
        try:
            setup = picker.choose_setup(manifest, saved)
        except SystemExit:
            return
        if name not in targets:
            targets[name] = new_target(f"💳 {name}", store.card_games(name))
        targets[name]["setup"] = setup
        drop_inapplicable(targets[name], setup)

    def delete_card(name):
        if not ui.confirm(f"🗑️  Delete card {name} and its extra games now? (cards.json.bak keeps the copy from before this run)", default=False):
            return
        if name in store.load_cards():
            store.delete_card(name)
        targets.pop(name, None)
        new_cards.discard(name)

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
        t = targets.get(key)
        return sum(len(v) for part in target_changes(t) for v in part.values()) if t else 0

    def pending_extra(key):
        n = pending_count(key)
        return [(f"  {n} change(s)", "cyan")] if n else []

    overlay_pending = {}  # device id -> (system ids added, system ids removed) relative to the repo defaults

    def edit_device_systems():
        """Pick a device, then toggle which systems it recommends; saved as the add/remove overlay."""
        defaults = store.device_defaults(manifest["systems"])
        names = {s["bucket"]: s["name"] for s in manifest["systems"]}
        devices = manifest["devices"]
        extras = [[("  edited", "cyan")] if d["id"] in overlay_pending else [] for d in devices]
        i = picker.filter_list("🧩 Which device's recommended systems?", [d["name"] for d in devices], extras=extras,
                               hint="/ filter · Enter open · Esc back")
        if i is None:
            return False
        d = devices[i]
        base = defaults.get(d["id"], {}).get("systems", [])
        ids = sorted(names, key=lambda x: names[x].lower())
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

    def menu():
        """The top menu. Returns True to review and save, False to quit without saving."""
        try:
            while True:
                saved = store.load_cards()
                cards = sorted(set(saved) | {k for k in targets if k is not None})
                n = len(cards)
                options = ([f"💳 {name}" for name in cards]
                           + ["➕ New card", "🧩 Device systems", "✅ Done (review & save)", "🚪 Quit without saving"])
                extras = ([setup_extra(name, saved) + pending_extra(name) for name in cards]
                          + [[], [("  " + str(len(overlay_pending)) + " edited", "cyan")] if overlay_pending else [], [], []])
                i = picker.filter_list("✏️  What do you want to edit?  (Esc = review & save)", options, extras=extras,
                                       hotkeys=(SETUP_KEY, DELETE_KEY, RENAME_KEY),
                                       hint=MENU_HINT)
                if i is None or i == n + 2:
                    return True
                if isinstance(i, tuple):
                    if i[1] < n:
                        {SETUP_KEY: change_setup, DELETE_KEY: delete_card, RENAME_KEY: rename_card}[i[0]](cards[i[1]])
                    continue
                if i < n:
                    open_target(cards[i], f"💳 {cards[i]}", True)
                elif i == n:
                    add_card()
                elif i == n + 1:
                    while edit_device_systems():
                        pass
                else:
                    if not changed_targets() and not overlay_pending or ui.confirm("Discard your pending changes and quit?", default=False):
                        return False
        except KeyboardInterrupt:
            print(ui.yellow("\n🛑 Interrupted — your pending changes are kept; review them below."))
            return True

    def changed_targets():
        return {k: t for k, t in targets.items() if t["setup"] or any(target_changes(t))}

    def print_changes(changed, cap):
        print(ui.bold("\n📝 Changes"))
        for key, t in changed.items():
            added, removed = target_changes(t)
            print(ui.bold(f"  {t['label']}") + (ui.dim("  (new card)") if key in new_cards else ui.dim("  (device/firmware)") if t["setup"] else ""))
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
            print(ui.yellow("👋 Quit without saving."))
            return 0
        changed = changed_targets()
        if not changed and not overlay_pending:
            print(ui.yellow("👋 No changes, nothing saved."))
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
    saved = store.save_lists({k: store.dump_list(t["data"]["systems"], t["sets_on"]) for k, t in changed.items()})
    if overlay_pending:
        store.save_overlay(overlay_pending)
    if not saved:
        print(ui.red("❌ Some changes were not saved (see above)."))
        return 3
    print(ui.green("🎉 Saved") + ui.dim(f"  ({store.data_dir()}; versions from before this run kept as .bak)"))
    return 0
