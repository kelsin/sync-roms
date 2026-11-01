"""The --edit game list editor."""
import os
import sys
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


FULL_SYSTEM_NOTE = "Full system: every file in its folder is synced, so it can't be toggled"


def toggle_games(title, rows, extras=None, covered=None):
    """Multi-select over rows of (system, bucket key, game title, label); adds/removes games in each system in place.

    extras: {bucket key: [more bucket keys]} added or removed together with that row's key.

    Rows of a full system are shown on and locked: its whole bucket folder is synced.
    covered: optional callable (system, bucket key) -> note or None; rows with a note are shown on and locked
    with that note (e.g. games a set reference or core already syncs).
    """
    notes = [FULL_SYSTEM_NOTE if s.get("full_system") else covered(s, key) if covered else None
             for s, key, _, _ in rows]
    locked = [bool(n) for n in notes]
    initial = [l or any(g.get("bucket") == key for g in s["games"]) for l, (s, key, _, _) in zip(locked, rows)]
    state = picker.filter_list(title, [label for *_, label in rows], multi=True, initial=initial, locked=locked,
                        locked_note=[n or "" for n in notes])
    for (s, key, name, _), on, was, lock in zip(rows, state, initial, locked):
        if lock:
            continue
        keys = [key] + list((extras or {}).get(key, []))
        if on and not was:
            for k in keys:
                if not any(g.get("bucket") == k for g in s["games"]):
                    s["games"].append({"title": name if k == key else os.path.splitext(k.split("/", 1)[-1])[0],
                                       "bucket": k})
        elif was and not on:
            s["games"] = [g for g in s["games"] if g.get("bucket") not in keys]


def system_rows(s, in_bucket):
    """Rows for toggle_games over every file of a system's bucket folder plus any listed game that isn't in it."""
    listed = {g["bucket"] for g in s["games"] if g.get("bucket")}
    return [(s, k, os.path.splitext(k.split("/", 1)[1])[0],
             k.split("/", 1)[1] + ("" if k in in_bucket else "  ⚠️ not in bucket"))
            for k in sorted(in_bucket | listed, key=str.lower)]


def edit_card_system(card, bucket, setup):
    """Toggle the games of one system in a card's extras (as --edit does) and save them. Returns whether anything changed.

    Games the core list or the card's own sets already sync are shown on and locked."""
    t = new_target(card, store.card_games(card))
    drop_inapplicable(t, setup)
    s = next(x for x in t["data"]["systems"] if x["bucket"] == bucket)
    full, keys = cover_notes({x["id"]: x for x in store.load_sets()}, t["sets_on"], store.personal_json("games.json"))
    if s.get("full_system") or bucket in full:
        note(ui.yellow(f"ℹ️  {s['name']} is a full system: every file in its bucket folder is downloaded, "
                       "so there is no game list to edit."))
        return False
    in_bucket = {k for k in s3.list_sizes(bucket + "/") if not k.endswith("/")}
    toggle_games(f"✏️  {s['name']} — ✅ in {card}'s extras, ⬜ in bucket only", system_rows(s, in_bucket),
                 covered=lambda _s, key: keys.get(key))
    if not any(target_changes(t)):
        return False
    store.save_lists(None, {card: store.dump_list(t["data"]["systems"], t["sets_on"])})
    return True


def set_rows(game_set, by_bucket, bucket_keys):
    """Rows for one set, sorted by system then title. Entries for unknown systems are skipped."""
    rows, seen = [], set()
    for g in game_set["games"]:
        s = by_bucket.get(g.get("system"))
        key = g.get("bucket")
        if not s or not key or key in seen:
            continue
        seen.add(key)
        title = g.get("title") or os.path.splitext(key.split("/", 1)[-1])[0]
        have = bucket_keys(s)
        warn = "" if s.get("full_system") or all(k in have for k in [key] + list(g.get("files", []))) \
            else "  ⚠️ not in bucket"
        rows.append((s, key, title, f"{s['name']} — {title}{warn}"))
    return sorted(rows, key=lambda r: (r[0]["name"].lower(), r[2].lower()))


def valid_card_name(name, existing):
    """Why name can't be a new card's folder name, or None if it can."""
    if not name.strip():
        return "A card needs a name."
    if "/" in name or os.sep in name:
        return "A card name is a folder name, so it can't contain a slash."
    if name in existing:
        return f"There is already a card named {name}."
    return None


def cover_notes(sets_by_id, own_set_ids, core=None):
    """Why games are synced without being in the list being edited.

    Returns ({system bucket: note} for whole systems, {bucket key: note} for single games). The notes come from
    the list's own set references and, when editing a card, from the core list (a raw games list).
    """
    full, keys = {}, {}
    if core is not None:
        for bucket, entry in core.items():
            if isinstance(entry, dict) and entry.get("full_system"):
                full[bucket] = "From core: full system"
            elif isinstance(entry, list):
                for g in entry:
                    if isinstance(g, dict) and g.get("bucket"):
                        keys.setdefault(g["bucket"], "From core")
        for sid in store.list_sets(core):
            for g in store.set_games(sets_by_id[sid]) if sid in sets_by_id else []:
                keys.setdefault(g["bucket"], f"From core: {sets_by_id[sid]['name']}")
    for sid in own_set_ids:
        for g in store.set_games(sets_by_id[sid]) if sid in sets_by_id else []:
            keys.setdefault(g["bucket"], f"Full set: {sets_by_id[sid]['name']}")
    return full, keys


def toggle_set_ref(sets_on, set_id):
    """The set ids with set_id switched on or off."""
    return [i for i in sets_on if i != set_id] if set_id in sets_on else sets_on + [set_id]


def toggle_full_system(s):
    s["full_system"] = not s["full_system"]


FULL_KEY = "\x06"  # ^F
SETUP_KEY = "\x04"  # ^D
DELETE_KEY = "\x18"  # ^X
RENAME_KEY = "\x12"  # ^R
FULL_HINT = "type to filter · ↑/↓ move · Enter open · ^F toggle {what} · Esc back"


def new_target(label, raw, setup=None):
    """The editing state of one games list: its systems, set references and what they were when opened."""
    data = {"systems": store.apply_games(store.repo_json("systems"), raw)}
    sets_on = store.list_sets(raw)
    return {"label": label, "data": data, "sets_on": sets_on, "setup": setup, "was": snapshot(data),
            "was_full": {s["bucket"]: s["full_system"] for s in data["systems"]}, "was_sets": list(sets_on)}


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
    on, was = set(t["sets_on"]), set(t["was_sets"])
    if on - was:
        added[store.SETS_KEY] = sorted(on - was)
    if was - on:
        removed[store.SETS_KEY] = sorted(was - on)
    return added, removed


def edit_manifest():
    """Add/remove games in the core list or a card's extras (browsing by system or by set), then save them."""
    print(ui.bold("✏️  Edit mode") + ui.dim(f"  read={runtime.PROFILE}"))
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so nothing could be saved. "
                "Fix or move it first.", 3)
    manifest = store.load_manifest()  # also seeds games.json
    core_raw = store.personal_json("games.json")
    repo_systems = store.repo_json("systems")
    print(ui.dim(f"📡 Listing s3://{runtime.BUCKET}/ ..."))
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = ex.map(lambda s: {k for k in s3.list_sizes(s["bucket"] + "/") if not k.endswith("/")}, repo_systems)
        bucket_keys = {s["bucket"]: keys for s, keys in zip(repo_systems, listings)}
    names = {s["bucket"] for s in repo_systems}
    sets = store.load_sets()
    sets_by_id = {x["id"]: x for x in sets}

    for game_set in sets:
        for g in game_set["games"]:
            if g.get("system") not in names:
                print(ui.yellow(f"⚠️  Set {game_set['name']}: unknown system {g.get('system')!r}, skipped"), file=sys.stderr)

    targets = {}  # None (the core list) or a card name -> editing state
    new_cards = set()  # cards made in this session

    def core_now():
        """The core list as it stands in this session."""
        core = targets.get(None)
        return store.dump_list(core["data"]["systems"], core["sets_on"]) if core else core_raw

    def edit_target(t, is_card):
        name = next((k for k, v in targets.items() if v is t), None)
        setup = (t["setup"] or picker.saved_setup(store.load_cards().get(name), manifest["devices"], manifest["layouts"])
                 if is_card else None)
        systems_all = [s for s in t["data"]["systems"] if not setup or store.system_applies(s, *setup)]
        by_bucket = {s["bucket"]: s for s in systems_all}
        systems = sorted((s for s in systems_all if bucket_keys[s["bucket"]] or s["games"] or s.get("full_system")),
                         key=lambda s: s["name"].lower())
        where = "games.json" if not is_card else f"{t['label']}'s extras"
        pos = {"system": 0, "set": 0}

        def cover():
            return cover_notes(sets_by_id, t["sets_on"], core_now() if is_card else None)

        def edit_system():
            now = snapshot(t["data"])
            full, keys = cover()
            width = max((len(s["name"]) for s in systems), default=0)
            labels, extras = [], []
            for s in systems:
                b = s["bucket"]
                changed = now[b] ^ t["was"][b]
                total = len(bucket_keys[b])
                whole = s.get("full_system") or b in full
                covered = {k for k in keys if k.split("/", 1)[0] == b}
                have = total if whole else len((now[b] | covered) & bucket_keys[b])
                missing = 0 if whole else len(now[b] - bucket_keys[b])
                labels.append(s["name"].ljust(width))
                row = [(f"  {have}", "green"), (f" / {total}", "dim")]
                if whole:
                    row.append(("  🗂️  full system", "cyan"))
                if missing:
                    row.append((f"  {missing} not in bucket", "red"))
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
                if s["bucket"] in full:
                    note(ui.yellow(f"ℹ️  {s['name']} is a full system in core, so it can't be changed here."))
                else:
                    toggle_full_system(s)
                return True
            pos["system"] = i
            s = systems[i]
            if s.get("full_system") or s["bucket"] in full:
                note(ui.yellow(f"ℹ️  {s['name']} is a full system: every file in its bucket folder is "
                               "downloaded, so there is no game list to edit."))
                return True
            toggle_games(f"✏️  {s['name']} — ✅ in {where}, ⬜ in bucket only",
                         system_rows(s, bucket_keys[s["bucket"]]),
                         covered=lambda _s, key: keys.get(key))
            return True

        def edit_set():
            if not sets:
                note(ui.yellow("ℹ️  No game sets found."))
                return False
            full, keys = cover()
            labels, extras = [], []
            for game_set in sets:
                entries = [(g.get("system"), g.get("bucket")) for g in game_set["games"] if g.get("system") in by_bucket]
                on = sum(1 for sid, key in entries if by_bucket[sid].get("full_system")
                         or any(g.get("bucket") == key for g in by_bucket[sid]["games"])
                         or sid in full or key in keys)
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
                ref = "  📦 full set (^F on the set list to stop syncing all of it)" if sets[i]["id"] in t["sets_on"] else ""
                toggle_games(f"✏️  {sets[i]['name']} — ✅ in {where}, ⬜ not{ref}", rows, files,
                             covered=lambda s, key: full.get(s["bucket"]) or keys.get(key))
            else:
                note(ui.yellow(f"ℹ️  {sets[i]['name']} has no games to toggle."))
            return True

        while True:
            i = picker.filter_list(f"✏️  Edit {t['label']} (Esc = back)", ["By system", "By set"])
            if i is None:
                break
            while (edit_system, edit_set)[i]():
                pass

    def open_target(key, label, is_card):
        if key not in targets:
            raw = core_raw if key is None else store.card_games(key)
            targets[key] = new_target(label, raw)
            setup = picker.saved_setup(store.load_cards().get(key), manifest["devices"], manifest["layouts"]) if is_card else None
            if setup:
                drop_inapplicable(targets[key], setup)
        edit_target(targets[key], is_card)

    def add_card():
        existing = set(store.load_cards()) | set(targets)
        while True:
            name = input("➕ New card: its folder name, e.g. RGSP (a path works too; empty to cancel): ").strip()
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
        saved = t["setup"] if t and t["setup"] else picker.saved_setup(store.load_cards().get(name), manifest["devices"], manifest["layouts"])
        try:
            setup = picker.choose_setup(manifest, saved)
        except SystemExit:
            return
        if name not in targets:
            targets[name] = new_target(f"💳 {name}", store.card_games(name))
        targets[name]["setup"] = setup
        drop_inapplicable(targets[name], setup)

    def delete_card(name):
        if not ui.confirm(f"🗑️  Delete card {name} and its extra games now? (cards.json.bak keeps the old file)", default=False):
            return
        if name in store.load_cards():
            store.delete_card(name)
        targets.pop(name, None)
        new_cards.discard(name)

    def rename_card(name):
        if name not in store.load_cards():
            note(ui.yellow("ℹ️  Save this new card first, then rename it."))
            return
        new = input(f"✏️  New folder name for {name} (empty to cancel): ").strip()
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

    def setup_extra(name):
        """The card's device and firmware as a row suffix; a pending change in cyan."""
        t = targets.get(name)
        pending = bool(t and t["setup"])
        setup = t["setup"] if pending else picker.saved_setup(store.load_cards().get(name), manifest["devices"], manifest["layouts"])
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
        defaults = store.repo_json("device-systems")
        names = {s["bucket"]: s["name"] for s in manifest["systems"]}
        devices = manifest["devices"]
        extras = [[("  edited", "cyan")] if d["id"] in overlay_pending else [] for d in devices]
        i = picker.filter_list("🧩 Which device's recommended systems?", [d["name"] for d in devices], extras=extras,
                               hint="type to filter · ↑/↓ move · Enter open · Esc back")
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
        overlay_file = os.path.join(store.data_dir(), "device-systems.json")
        saved_all = store.personal_json("device-systems.json") if os.path.exists(overlay_file) else {}
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
                cards = sorted(set(store.load_cards()) | {k for k in targets if k is not None})
                n = len(cards)
                options = (["🏠 Core (every card)"] + [f"💳 {name}" for name in cards]
                           + ["➕ New card", "🧩 Device systems", "✅ Done (review & save)", "🚪 Quit without saving"])
                extras = ([pending_extra(None)] + [setup_extra(name) + pending_extra(name) for name in cards]
                          + [[], [("  " + str(len(overlay_pending)) + " edited", "cyan")] if overlay_pending else [], [], []])
                i = picker.filter_list("✏️  What do you want to edit?  (Esc = review & save)", options, extras=extras,
                                       hotkeys=(SETUP_KEY, DELETE_KEY, RENAME_KEY),
                                       hint="type to filter · Enter open · on a card: ^D device/firmware · ^R rename · ^X delete · Esc review & save")
                if i is None or i == n + 3:
                    return True
                if isinstance(i, tuple):
                    if 0 < i[1] <= n:
                        {SETUP_KEY: change_setup, DELETE_KEY: delete_card, RENAME_KEY: rename_card}[i[0]](cards[i[1] - 1])
                    continue
                if i == 0:
                    open_target(None, "🏠 Core", False)
                elif i <= n:
                    open_target(cards[i - 1], f"💳 {cards[i - 1]}", True)
                elif i == n + 1:
                    add_card()
                elif i == n + 2:
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
        print(ui.dim("  (Removing only drops a game from the list; the file stays in the bucket.)"))

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
    saved = store.save_lists(store.dump_list(targets[None]["data"]["systems"], targets[None]["sets_on"]) if None in changed else None,
               {k: store.dump_list(t["data"]["systems"], t["sets_on"]) for k, t in changed.items() if k is not None})
    if overlay_pending:
        store.save_overlay(overlay_pending)
    if not saved:
        print(ui.red("❌ Some changes were not saved (see above)."))
        return 3
    print(ui.green("🎉 Saved") + ui.dim(f"  ({store.data_dir()}; previous versions kept as .bak)"))
    return 0
