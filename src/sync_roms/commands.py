"""Scriptable subcommands: games, cards, config, doctor, check and completion; plus helpers the sync flow uses."""
import argparse
import datetime
import json
import os
import re
import sys

from . import collections as colls
from . import external, inventory, m3u, picker, runtime, s3, setedit, store, surprise, ui, usersettings


UNKNOWN_SHOWN = 8  # device ids named in an "unknown device" error
COMMANDS = {"games", "sets", "collections", "themes", "cards", "cache", "config", "doctor", "check", "completion"}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        ui.fail(f"{message}\n   Try 'sync-roms {self.prog.split()[-1]} --help'.", 2)


# --- Helpers the sync flow uses ----------------------------------------------------------------------

def unknown_device(device_id, ids):
    """Exit 2 for a device id that doesn't exist, naming a few real ones instead of all of them."""
    shown = ", ".join(ids[:UNKNOWN_SHOWN]) + (f", … ({len(ids) - UNKNOWN_SHOWN} more)" if len(ids) > UNKNOWN_SHOWN else "")
    ui.fail(f"Unknown device {device_id!r}. Known: {shown}\n   `sync-roms devices` lists them all.", 2)


def show_devices(devices, systems, device_id=None, as_json=False):
    """Print the device table, or one device's details."""
    if device_id:
        d = next((x for x in devices if x["id"] == device_id), None)
        if not d:
            unknown_device(device_id, [x["id"] for x in devices])
        names = {s["bucket"]: s["name"] for s in systems}
        if as_json:
            ui.emit_json({**d, "system_names": [names.get(i, i) for i in d["systems"]]})
            return 0
        print(ui.bold(f"📟 {d['name']}") + ui.dim(f"  ({d['id']}, {d['soc']})"))
        print(f"  firmwares: {', '.join(d['firmwares'])}  (first is the default)")
        if d.get("note"):
            print(ui.dim(f"  {d['note']}"))
        for i in d["systems"]:
            print(f"  {i:<14} {names.get(i, '')}")
        return 0
    if as_json:
        ui.emit_json([{"id": d["id"], "name": d["name"], "soc": d["soc"], "systems": len(d["systems"]),
                       "firmwares": d["firmwares"]} for d in devices])
        return 0
    rows = [(d["name"], d["soc"], str(len(d["systems"])), d["id"]) for d in devices]
    ui.table(rows, ("Device", "Chip", "Systems", "Id"), right=(2,))
    return 0


def setup_from_flags(manifest, current, device_id, layout):
    """(device dict or None for Full, layout name) from --device/--layout, filling a missing half from the saved setup
    or the device's default firmware."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    if device_id:
        if device_id == "full":
            device = None
        else:
            device = next((d for d in devices if d["id"] == device_id), None)
            if not device:
                unknown_device(device_id, ["full"] + [d["id"] for d in devices])
    elif current:
        device = current[0]
    else:
        ui.fail("--layout needs --device the first time (no saved setup for this card)", 2)
    offered = layouts if device is None else {n: layouts[n] for n in device["firmwares"]}
    if not layout:
        layout = current[1] if current and current[1] in offered else next(iter(offered))
    if layout not in offered:
        ui.fail(f"{'Full' if device is None else device['name']} doesn't run {layout!r}. Choose from: {', '.join(offered)}", 2)
    return device, layout


def load_target(card):
    """(raw games list, save function) for a card's games."""
    if card is None:
        ui.fail("Name the card with --card NAME (games lists belong to cards). Cards: "
                f"{', '.join(store.all_card_names()) or '(none yet)'}", 2)
    if card not in store.load_cards():
        ui.fail(f"No card named {card!r}. Cards: {', '.join(store.all_card_names()) or '(none yet)'}", 2)
    return store.card_games(card), lambda raw: store.save_lists({card: raw})


def system_ids():
    return [s["bucket"] for s in store.repo_json("systems")]


def need_system(system):
    if system not in system_ids():
        ui.fail(f"Unknown system {system!r}. Known: {', '.join(system_ids())}", 2)


def glob_match(key, pattern):
    """Whether the file part of a bucket key matches a pattern where only * and ? are wildcards ([ is literal)."""
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern.lower())
    return re.fullmatch(regex, key.split("/", 1)[1].lower(), re.S) is not None


def resolve_keys(system, patterns, listing=None):
    """Bucket keys for file names, SYSTEM/file keys or globs. Globs match against listing (bucket keys), which is
    storage's listing of the system when not given."""
    keys, in_storage = [], listing is None
    for pat in patterns:
        name = pat[len(system) + 1:] if pat.startswith(system + "/") else pat
        if not any(c in name for c in "*?"):
            keys.append(f"{system}/{name}")
            continue
        if listing is None:
            usersettings.ensure_bucket()
            inventory.prepare()
            listing = [k for k in inventory.files(system + "/") if not k.endswith("/")]
        if f"{system}/{name}" in listing:  # a real name that happens to contain * or ?
            keys.append(f"{system}/{name}")
            continue
        hits = [k for k in listing if glob_match(k, name)]
        if not hits:
            ui.warn(f"{pat!r} matches nothing in " + (f"{system}/" if in_storage else "the list"))
        keys += hits
    return list(dict.fromkeys(keys))


def game_entries(raw):
    """[(system, key, title)] for the listed games of a raw list."""
    out = []
    for system, entry in raw.items():
        if isinstance(entry, list):
            out += [(system, g["bucket"], g.get("title", "")) for g in entry if isinstance(g, dict) and g.get("bucket")]
    return out


def games_list(args):
    raw, _ = load_target(args.card)
    full = sorted(k for k, v in raw.items() if isinstance(v, dict) and v.get("full_system"))
    sets = store.list_sets(raw)
    entries = game_entries(raw)
    if args.json:
        ui.emit_json({"full_systems": full, "sets": sets,
                      "games": [{"system": s, "bucket": k, "title": t} for s, k, t in entries]})
        return 0
    ui.table([(s, "*", "(full system)") for s in full] + [("sets", i, "(whole set)") for i in sets]
             + [(s, k, t) for s, k, t in entries])
    return 0


def finish(args, raw, save, changes):
    """Print the changes and save them unless --dry-run."""
    if not changes:
        print(ui.yellow("Nothing to change."))
        return 0
    for sign, text in changes:
        print((ui.green if sign == "+" else ui.red)(f"  {sign} {text}"))
    if args.dry_run:
        print(ui.yellow("🧪 Dry run — nothing saved"))
        return 0
    if save(raw) is False:
        return 3
    print(ui.green(f"💾 Saved {len(changes)} change(s)") + ui.dim(f" (card {args.card})"))
    return 0


def add_games(raw, system, keys):
    entry = raw.get(system)
    if isinstance(entry, dict):
        ui.warn(f"{system} is a full system, so its games can't be listed one by one (games full {system} off first)")
        return []
    entry = raw.setdefault(system, [])
    have = {g.get("bucket") for g in entry if isinstance(g, dict)}
    changes = []
    for key in keys:
        if key not in have:
            entry.append({"title": os.path.splitext(key.split("/", 1)[1])[0], "bucket": key})
            changes.append(("+", key))
    if not entry:
        del raw[system]
    return changes


def remove_games(raw, system, keys):
    entry = raw.get(system)
    if not isinstance(entry, list):
        return []
    gone = [g["bucket"] for g in entry if isinstance(g, dict) and g.get("bucket") in keys]
    raw[system] = [g for g in entry if not (isinstance(g, dict) and g.get("bucket") in keys)]
    if not raw[system]:
        del raw[system]
    return [("-", k) for k in gone]


def games_add(args):
    need_system(args.system)
    raw, save = load_target(args.card)
    return finish(args, raw, save, add_games(raw, args.system, resolve_keys(args.system, args.keys)))


def games_remove(args):
    need_system(args.system)
    raw, save = load_target(args.card)
    listed = [g["bucket"] for g in raw.get(args.system, []) if isinstance(raw.get(args.system), list) and isinstance(g, dict)
              and isinstance(g.get("bucket"), str)]
    keys = set(resolve_keys(args.system, args.keys, listed))
    changes = remove_games(raw, args.system, keys)
    for k in sorted(keys - {c[1] for c in changes}):
        ui.warn(f"{k} isn't in the list")
    return finish(args, raw, save, changes)


def games_full(args):
    need_system(args.system)
    raw, save = load_target(args.card)
    now = isinstance(raw.get(args.system), dict)
    if args.state == "on" and not now:
        raw[args.system] = {"full_system": True}
        return finish(args, raw, save, [("+", f"{args.system} (full system)")])
    if args.state == "off" and now:
        del raw[args.system]
        return finish(args, raw, save, [("-", f"{args.system} (full system)")])
    return finish(args, raw, save, [])


def games_sets(args):
    raw, save = load_target(args.card)
    known = {x["id"]: x for x in store.load_sets()}
    if args.verb == "list":
        on = store.list_sets(raw)
        ui.table([(f"{'✅' if set_id in on else '⬜'} {set_id}", x["name"]) for set_id, x in known.items()])
        return 0
    if not args.set_id:
        ui.fail(f"sets {args.verb} needs a set id. Known: {', '.join(known)}", 2)
    if args.set_id not in known:
        ui.fail(f"Unknown set {args.set_id!r}. Known: {', '.join(known)}", 2)
    on = list(store.list_sets(raw))
    if args.verb == "add" and args.set_id not in on:
        raw[store.SETS_KEY] = on + [args.set_id]
        return finish(args, raw, save, [("+", f"set {args.set_id}")])
    if args.verb == "remove" and args.set_id in on:
        on.remove(args.set_id)
        if on:
            raw[store.SETS_KEY] = on
        else:
            raw.pop(store.SETS_KEY, None)
        return finish(args, raw, save, [("-", f"set {args.set_id}")])
    return finish(args, raw, save, [])


def parse_collection(value):
    """A collection id from an import line; None (with a warning) when no such collection exists."""
    if value not in {c["id"] for c in colls.load_collections()}:
        ui.warn(f"unknown collection {value!r}, skipped")
        return None
    return value


# Card-entry list fields that `games export`/`import` carry as `@field value` lines, one per value. CARD_HOOKS gives a
# field its own parse(value) -> item or None (None skips the line; the hook warns) and format(item) -> text; a field
# without one uses the text as it is.
CARD_FIELDS = ("collections", "frontend_collections", "surprise", "surprises")
CARD_HOOKS = {"collections": (parse_collection, str), "surprises": (None, lambda s: s["bucket"])}


def games_export(args):
    raw, _ = load_target(args.card)
    for system, entry in raw.items():
        if isinstance(entry, dict) and entry.get("full_system"):
            print(f"{system}/*")
    for _, key, _ in game_entries(raw):
        print(key)
    card = store.load_cards()[args.card]
    for field in CARD_FIELDS:
        if field == "surprise":
            if isinstance(card, dict) and not surprise.enabled(card):
                print("@surprise false")
            continue
        values = card.get(field) if isinstance(card, dict) else None
        for value in values if isinstance(values, list) else []:
            if field == "surprises" and not (isinstance(value, dict) and isinstance(value.get("bucket"), str)):
                continue
            print(f"@{field} {CARD_HOOKS.get(field, (None, str))[1](value)}")
    return 0


def surprise_entries(keys_by_system):
    """Saved-surprise dicts for {system: [keys]}; a multi-disc game's other keys come from the system's listing."""
    out = []
    for system, keys in keys_by_system.items():
        groups = {}
        try:
            groups = m3u.file_groups(inventory.files(f"{system}/", sizes=False))
        except (*s3.ERRORS, SystemExit):
            ui.warn(f"can't list {system}/, importing its surprises without their other discs")
        for key in keys:
            entry = {"system": system, "bucket": key, "title": store.key_title(key)}
            files = [k for k in groups.get(key, []) if k != key]
            out.append({**entry, "files": files} if files else entry)
    return out


def games_import(args):
    raw, save = load_target(args.card)
    try:
        lines = [l.strip() for l in (sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")) if l.strip() and not l.startswith("#")]
    except OSError as e:
        ui.fail(f"Can't read {args.file}: {e}", 2)
    changes, by_system, known, fields = [], {}, set(system_ids()), {}
    surprise_state, surprise_keys = None, {}
    for line in lines:
        if line.startswith("@"):
            field, _, text = line[1:].partition(" ")
            if field not in CARD_FIELDS:
                ui.warn(f"skipping {line!r}: unknown card field")
                continue
            if field == "surprise":
                if text.strip() in ("true", "false"):
                    surprise_state = text.strip() == "true"
                    changes.append(("+", f"@surprise {text.strip()}"))
                else:
                    ui.warn(f"skipping {line!r}: expected @surprise true or false")
                continue
            if field == "surprises":
                system, _, name = text.strip().partition("/")
                if system not in known or not name:
                    ui.warn(f"skipping {line!r}: expected @surprises SYSTEM/file")
                elif sum(map(len, surprise_keys.values())) >= surprise.SLOTS:
                    ui.warn(f"skipping {line!r}: a card holds at most {surprise.SLOTS} surprises")
                else:
                    surprise_keys.setdefault(system, []).append(text.strip())
                    changes.append(("+", f"@surprises {text.strip()}"))
                continue
            if not text.strip():
                ui.warn(f"skipping {line!r}: expected @{field} VALUE")
                continue
            value = CARD_HOOKS.get(field, (lambda text: text, str))[0](text.strip())
            if value is not None:
                fields.setdefault(field, []).append(value)
            continue
        system, _, name = line.partition("/")
        if system not in known or not name:
            ui.warn(f"skipping {line!r}: expected SYSTEM/file or SYSTEM/*")
        elif name == "*":
            if not isinstance(raw.get(system), dict):
                raw[system] = {"full_system": True}
                changes.append(("+", f"{system} (full system)"))
        else:
            by_system.setdefault(system, []).append(line)
    for system, keys in by_system.items():
        changes += add_games(raw, system, keys)
    for field, values in fields.items():
        changes.append(("+", f"{field}: {', '.join(CARD_HOOKS.get(field, (None, str))[1](v) for v in values)}"))

    def save_all(raw):
        if save(raw) is False:
            return False
        values = dict(fields)
        if surprise_state is False:
            values["surprise"] = False
        if surprise_keys:
            values["surprises"] = surprise_entries(surprise_keys)
        if surprise_state:
            cards = store.load_cards()
            if isinstance(cards.get(args.card), dict) and cards[args.card].pop("surprise", None) is not None:
                store.write_cards(cards)
        return store.update_card(args.card, **values) if values else None

    return finish(args, raw, save_all, changes)


# --- Cards ------------------------------------------------------------------------------------------

def parse_size(text):
    """A card size as written to cards.json ("512 GB", "1 TB") from "512", "512gb", "1 TB"; None when it isn't one."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GB|TB|G|T)?\s*", text, re.I)
    if not m or float(m.group(1)) <= 0:
        return None
    number = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
    return f"{number} {'TB' if (m.group(2) or 'GB').upper().startswith('T') else 'GB'}"


def cards_list(args):
    cards = store.load_cards()
    manifest = store.load_catalog()
    rows = []
    for name in sorted(cards):
        setup = picker.saved_setup(cards[name], manifest["devices"], manifest["layouts"])
        extras = sum(len(v) if isinstance(v, list) else 1 for v in store.card_games(name, cards).values())
        rows.append({"name": name, "device": (setup[0]["id"] if setup[0] else "full") if setup else None,
                     "layout": setup[1] if setup else None, "size": cards[name].get("size") if isinstance(cards[name], dict) else None,
                     "extras": extras})
    if args.json:
        ui.emit_json(rows)
        return 0
    ui.table([(r["name"], r["device"] or "(no device set)", r["layout"] or "", r["size"] or "", f"{r['extras']} game entries") for r in rows])
    return 0


def cards_save_setup(args, create):
    cards = store.load_cards()
    if create and args.name in cards:
        ui.fail(f"There is already a card named {args.name!r}", 2)
    if not create and args.name not in cards:
        ui.fail(f"No card named {args.name!r}. Cards: {', '.join(sorted(cards)) or '(none yet)'}", 2)
    if "/" in args.name or not args.name.strip():
        ui.fail("A card name is a folder name: no slashes, not empty", 2)
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so the card can't be saved. Fix or move it first.", 3)
    manifest = store.load_catalog()
    current = picker.saved_setup(cards.get(args.name), manifest["devices"], manifest["layouts"])
    if create and not (args.device and args.layout):
        ui.fail("cards new needs --device and --layout", 2)
    device, layout = setup_from_flags(manifest, current, args.device, args.layout)
    values = {"device": device["id"] if device else "full", "layout": layout}
    if args.size:
        size = parse_size(args.size)
        if not size:
            ui.fail(f"{args.size!r} isn't a card size. Use e.g. 256, 512GB or 1TB", 2)
        values["size"] = size
    shown = f"{values['device']} · {layout}" + (f" · {values['size']}" if "size" in values else "")
    if args.dry_run:
        print(ui.yellow(f"🧪 Would save {args.name}: {shown}"))
        return 0
    if not store.update_card(args.name, **values):
        return 3
    print(ui.green(f"💾 {args.name}: {shown}"))
    return 0


def cards_rename(args):
    cards = store.load_cards()
    if args.old not in cards:
        ui.fail(f"No card named {args.old!r}", 2)
    if args.new in cards or "/" in args.new or not args.new.strip():
        ui.fail(f"{args.new!r} is taken or not a valid folder name", 2)
    if args.dry_run:
        print(ui.yellow(f"🧪 Would rename {args.old} to {args.new}"))
        return 0
    cards[args.new] = cards.pop(args.old)
    if not store.write_cards(cards):
        return 3
    print(ui.green(f"💾 Renamed {args.old} → {args.new}") + ui.dim("  (also rename the card's folder, or the next sync starts a new card)"))
    return 0


def cards_delete(args):
    if args.name not in store.load_cards():
        ui.fail(f"No card named {args.name!r}", 2)
    if args.dry_run:
        print(ui.yellow(f"🧪 Would delete card {args.name} and its games"))
        return 0
    if not args.yes and not ui.confirm(f"Delete card {args.name} and its games? (cards.json.bak keeps the old file)", default=False):
        print(ui.yellow("↩️  Kept"))
        return 0
    if not store.delete_card(args.name):
        return 3
    print(ui.green(f"🗑️  Deleted card {args.name}"))
    return 0


# --- config, check, doctor ---------------------------------------------------------------------------

def effective_settings():
    """[(name, value, source)] for the settings sync-roms reads."""
    out = [(name, value, source) for name, (value, source) in usersettings.resolve_settings().items()]
    mirror = usersettings.load_settings().get("mirror")
    out.append(("mirror", mirror, "settings.json" if mirror else "unset"))
    return out


def config_cmd(args):
    if args.action == "path":
        print(store.data_dir())
        return 0
    print(ui.bold("⚙️  sync-roms settings") + ui.dim(f"  {store.data_dir()}"))
    for name, value, source in effective_settings():
        print(f"  {name:<14} {value if value is not None else ui.dim('(not set)'):<28} {ui.dim(source)}")
    return 0


def cache_cmd(args):
    usersettings.ensure_bucket()
    return inventory.update_command(args.full) if args.action == "update" else inventory.status_command()


def check_game_file(problems, path, where, systems):
    """Check one set or collection file; returns its [(system, key)] pairs, or None when the file is unusable.

    where: the name problems are reported under. systems: the set of known system ids."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        problems.append(f"{where}: not valid JSON ({e})")
        return None
    games = data.get("games") if isinstance(data, dict) else None
    if not isinstance(games, list):
        problems.append(f"{where}: must be an object with a 'games' list")
        return None
    if not isinstance(data.get("name"), str) or not data["name"]:
        problems.append(f"{where}: missing 'name'")
    listed = []
    for g in games:
        if not isinstance(g, dict) or not isinstance(g.get("bucket"), str) or not g["bucket"]:
            problems.append(f"{where}: entry without a bucket key: {g!r}")
            continue
        system = g.get("system")
        if system not in systems:
            problems.append(f"{where}: {g['bucket']}: unknown system {system!r}")
            continue
        if not g.get("title"):
            problems.append(f"{where}: {g['bucket']}: missing 'title'")
        if not isinstance(g.get("category", ""), str):
            problems.append(f"{where}: {g['bucket']}: 'category' must be a string")
        files = g.get("files", [])
        if not isinstance(files, list) or not all(isinstance(k, str) for k in files):
            problems.append(f"{where}: {g['bucket']}: 'files' must be a list of bucket keys")
            files = []
        for k in [g["bucket"]] + files:
            if not k.startswith(system + "/"):
                problems.append(f"{where}: {k!r} isn't under {system}/")
            else:
                listed.append((system, k))
    return listed


def check_folder(problems, folder, prefix, systems):
    """Check every .json file in folder with check_game_file; returns {prefix + file name: [(system, key)]}."""
    keys = {}
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith(".json"):
            listed = check_game_file(problems, os.path.join(folder, name), f"{prefix}{name}", systems)
            if listed is not None:
                keys[f"{prefix}{name}"] = listed
    return keys


def check_sets(problems, systems):
    """Check every repo set file and return the keys each one lists as {set id: [(system, key)]}.

    systems: the set of known system ids."""
    return check_folder(problems, store.REPO_DATA + "/sets", "", systems)


def check_collections(problems, systems):
    """Check every file in the user's collections folder; returns {"collections/<file>": [(system, key)]}."""
    return check_folder(problems, colls.collections_dir(), "collections/", systems)


def valid_ratio(value):
    """True for a W:H aspect ratio string of two positive whole numbers."""
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", value) is not None


def check_data(list_keys=None, repo_systems=None):
    """Problems found in the user's data files, as strings.

    list_keys: optional callable(system id) -> set of bucket keys in that system's folder; when given, every
    key the lists and sets name must be among them.
    repo_systems: the repo's systems.json already loaded."""
    problems = []
    if repo_systems is None:
        repo_systems = store.repo_json("systems")
    for s in repo_systems:
        sid = s.get("screenscraper")
        if sid is not None and (not isinstance(sid, int) or isinstance(sid, bool)):
            problems.append(f"systems.json: {s['bucket']}: screenscraper must be an integer")
    for s in repo_systems:
        ratio = s.get("ratio")
        if ratio is not None and not valid_ratio(ratio):
            problems.append(f"systems.json: {s['bucket']}: ratio must look like W:H with whole numbers, not {ratio!r}")
    wanted = {}  # where -> [(system, key)] for the bucket check
    systems = {s["bucket"] for s in repo_systems}
    over = store.repo_json("ratio-systems")
    for ratio, ids in list(over.get("ratios", {}).items()) + [("dual_screen", over.get("dual_screen", []))]:
        if ratio != "dual_screen" and not valid_ratio(ratio):
            problems.append(f"ratio-systems.json: ratio {ratio!r} must look like W:H with whole numbers")
        problems.extend(f"ratio-systems.json: {ratio}: unknown system {i!r}" for i in ids if i not in systems)
    for d in store.repo_json("devices"):
        for key in ("screen", "screen2"):
            if key in d and not valid_ratio(d[key]):
                problems.append(f"devices.json: {d['id']}: {key} must look like W:H with whole numbers, not {d[key]!r}")
    devices = {d["id"] for d in store.repo_json("devices")}
    layouts = set(store.repo_json("layouts"))
    sets = {x["id"] for x in store.load_sets()}
    wanted.update(check_sets(problems, systems))
    wanted.update(check_collections(problems, systems))
    collection_ids = {c["id"] for c in colls.load_collections()}

    def load(name):
        path = os.path.join(store.data_dir(), name)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except ValueError as e:
            problems.append(f"{name}: not valid JSON ({e})")

    def check_list(where, raw):
        if not isinstance(raw, dict):
            problems.append(f"{where}: must be an object")
            return
        for key, entry in raw.items():
            if key == store.SETS_KEY:
                if not isinstance(entry, list) or not all(isinstance(i, str) for i in entry):
                    problems.append(f"{where}: 'sets' must be a list of set ids")
                else:
                    problems.extend(f"{where}: unknown set {i!r}" for i in entry if i not in sets)
            elif key not in systems:
                problems.append(f"{where}: unknown system {key!r}")
            elif isinstance(entry, list):
                for g in entry:
                    if not isinstance(g, dict) or not g.get("bucket"):
                        problems.append(f"{where}: {key}: entry without a bucket key: {g!r}")
                    elif not isinstance(g["bucket"], str):
                        problems.append(f"{where}: {key}: bucket key must be a string: {g['bucket']!r}")
                    elif not g["bucket"].startswith(key + "/"):
                        problems.append(f"{where}: {key}: {g['bucket']!r} isn't under {key}/")
                    else:
                        wanted.setdefault(where, []).append((key, g["bucket"]))
            elif not (isinstance(entry, dict) and "full_system" in entry):
                problems.append(f"{where}: {key}: must be a list of games or {{\"full_system\": true}}")

    cards = load("cards.json")
    if cards is not None and not isinstance(cards, dict):
        problems.append("cards.json: must be an object")
        cards = {}
    for name, entry in (cards or {}).items():
        if not isinstance(entry, dict):
            problems.append(f"cards.json: {name}: must be an object")
            continue
        if entry.get("device") not in devices | {"full", None}:
            problems.append(f"cards.json: {name}: unknown device {entry.get('device')!r}")
        if entry.get("layout") not in layouts | {None}:
            problems.append(f"cards.json: {name}: unknown layout {entry.get('layout')!r}")
        if "games" in entry:
            check_list(f"cards.json: {name}", entry["games"])
        picked = entry.get("collections", [])
        if not isinstance(picked, list) or not all(isinstance(i, str) for i in picked):
            problems.append(f"cards.json: {name}: 'collections' must be a list of collection ids")
        else:
            problems.extend(f"cards.json: {name}: unknown collection {i!r}" for i in picked if i not in collection_ids)
        names = entry.get("frontend_collections", [])
        if not isinstance(names, list) or not all(isinstance(i, str) for i in names):
            problems.append(f"cards.json: {name}: 'frontend_collections' must be a list of names")
        if "surprise" in entry and not isinstance(entry["surprise"], bool):
            problems.append(f"cards.json: {name}: 'surprise' must be true or false")
        picks = entry.get("surprises", [])
        if not isinstance(picks, list):
            problems.append(f"cards.json: {name}: 'surprises' must be a list")
        else:
            for g in picks:
                if not isinstance(g, dict) or not all(isinstance(g.get(k), str) and g.get(k)
                                                      for k in ("system", "bucket", "title")):
                    problems.append(f"cards.json: {name}: surprises: each must have system, bucket and title")
                elif g["system"] not in systems:
                    problems.append(f"cards.json: {name}: surprises: unknown system {g['system']!r}")
                else:
                    files = g.get("files", [])
                    if not isinstance(files, list) or not all(isinstance(k, str) for k in files):
                        problems.append(f"cards.json: {name}: surprises: {g['bucket']}: 'files' must be a list of bucket keys")
                        files = []
                    for k in [g["bucket"]] + files:
                        if not k.startswith(g["system"] + "/"):
                            problems.append(f"cards.json: {name}: surprises: {k!r} isn't under {g['system']}/")
                        else:
                            wanted.setdefault(f"cards.json: {name}: surprises", []).append((g["system"], k))
    history = load("surprises.json")
    if history is not None and not isinstance(history, list):
        problems.append("surprises.json: must be a list")
        history = []
    for e in history or []:
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ("system", "bucket", "title", "card", "date")):
            problems.append("surprises.json: entry needs system, bucket, title, card and date")
            continue
        if e["system"] not in systems:
            problems.append(f"surprises.json: unknown system {e['system']!r}")
        elif not e["bucket"].startswith(e["system"] + "/"):
            problems.append(f"surprises.json: {e['bucket']!r} isn't under {e['system']}/")
        try:
            datetime.date.fromisoformat(e["date"])
        except ValueError:
            problems.append(f"surprises.json: {e['date']!r} isn't an ISO date")
    overlay = load("device-systems.json")
    if overlay is not None and not isinstance(overlay, dict):
        problems.append("device-systems.json: must be an object")
        overlay = {}
    for dev, change in (overlay or {}).items():
        if dev not in devices:
            problems.append(f"device-systems.json: unknown device {dev!r}")
        elif not isinstance(change, dict):
            problems.append(f"device-systems.json: {dev}: must be an object with add/remove")
        else:
            for key in ("add", "remove"):
                ids = change.get(key, [])
                if not isinstance(ids, list):
                    problems.append(f"device-systems.json: {dev}.{key}: must be a list of system ids")
                    continue
                for sid in ids:
                    if not isinstance(sid, str) or sid not in systems:
                        problems.append(f"device-systems.json: {dev}.{key}: unknown system {sid!r}")
    if list_keys:
        have = {}
        for where, pairs in wanted.items():
            for system, key in pairs:
                if system not in have:
                    have[system] = list_keys(system)
                if key not in have[system]:
                    problems.append(f"{where}: {key!r} isn't in storage")
    return problems


def bucket_lister():
    """A callable(system id) -> bucket keys, using the read-only profile (refuses the write profile)."""
    if not runtime.ROOT and runtime.PROFILE == runtime.WRITE_PROFILE:
        ui.fail(f"--bucket-keys only reads storage; use the read-only profile, not {runtime.WRITE_PROFILE!r} "
                "(--profile / ROMS_PROFILE)", 2)
    inventory.prepare()
    return lambda system: {k for k in inventory.files(system + "/") if not k.endswith("/")}


def check_notices(repo_systems):
    """Things worth knowing about the data that don't make `check` fail, as strings. repo_systems: systems.json loaded."""
    missing = [s["bucket"] for s in repo_systems if s.get("screenscraper") is None]
    return [f"systems.json: {len(missing)} system(s) have no ScreenScraper system id, so `scrape` skips them: "
            + ", ".join(missing)] if missing else []


def check_cmd(args):
    repo_systems = store.repo_json("systems")
    problems = check_data(bucket_lister() if args.bucket_keys else None, repo_systems)
    for p in problems:
        print(ui.red(f"❌ {p}"))
    for n in check_notices(repo_systems):
        print(ui.yellow(f"⚠️  {n}"))
    if not problems:
        print(ui.green("✅ cards.json, surprises.json, device-systems.json, the sets and your collections look fine"))
    return 1 if problems else 0


def doctor_cmd(args):
    bad = 0

    def line(ok, text, hint=""):
        nonlocal bad
        bad += ok is False
        print(f"{'✅' if ok else '⚠️ ' if ok is None else '❌'} {text}" + (ui.dim(f"  → {hint}") if hint and not ok else ""))

    settings = dict((n, v) for n, v, _ in effective_settings())
    if runtime.ROOT:
        line(os.path.isdir(runtime.ROOT), f"storage folder: {runtime.ROOT}", "is the network share mounted?")
        if os.path.isdir(runtime.ROOT):
            try:
                os.listdir(runtime.ROOT)
                line(True, f"can list {runtime.ROOT}")
            except OSError as e:
                line(False, f"can't list {runtime.ROOT}: {e}", "check the share's permissions")
    else:
        line(bool(settings["bucket"]), f"bucket: {settings['bucket'] or 'not set'}", "run any sync-roms command to be asked, or set ROMS_BUCKET")
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound
            session = boto3.Session(profile_name=runtime.PROFILE)
            line(session.get_credentials() is not None, f"AWS profile {runtime.PROFILE}", f"aws configure --profile {runtime.PROFILE}")
            if settings["bucket"] and session.get_credentials() is not None:
                try:
                    s3.s3_client().list_objects_v2(Bucket=runtime.BUCKET, MaxKeys=1)
                    line(True, f"can list s3://{runtime.BUCKET}")
                except (ClientError, BotoCoreError) as e:
                    line(False, f"can't list s3://{runtime.BUCKET}: {e}", f"aws sso login --profile {runtime.PROFILE}, or check the bucket name")
        except ProfileNotFound:
            line(False, f"AWS profile {runtime.PROFILE} not found", f"aws configure --profile {runtime.PROFILE}")
        try:
            boto3.Session(profile_name=runtime.WRITE_PROFILE)
            line(True, f"write profile {runtime.WRITE_PROFILE} exists")
        except ProfileNotFound:
            line(None, f"write profile {runtime.WRITE_PROFILE} not found", "only needed for upload and clean")
    for tool in ("7z", "chdman", "extract-xiso", "iso2zar"):
        found = external.find_tool(tool)
        line(True if found else None, f"{tool}: {found or 'not installed'}",
             "sync-roms tools install" if tool in external.TOOL_FORMULAE else external.MANUAL_TOOLS[tool])
    problems = check_data()
    line(not problems, f"data files in {store.data_dir()}" + ("" if not problems else f": {len(problems)} problem(s)"), "sync-roms check")
    return 1 if bad else 0


# --- Shell completion ----------------------------------------------------------------------------------

def completion_lists(what):
    if what == "cards":
        return store.all_card_names()
    if what == "systems":
        return system_ids()
    if what == "devices":
        return ["full"] + [d["id"] for d in store.repo_json("devices")]
    if what == "layouts":
        return list(store.repo_json("layouts"))
    return []


def all_flags():
    """Every option string the CLI accepts (flag parser, subcommand parsers and global flags), sorted."""
    from . import cli
    found = set(cli.GLOBAL_VALUE_FLAGS) | {"--quiet", "--verbose"}

    def walk(parser):
        for action in parser._actions:
            found.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    walk(child)
    walk(cli.build_parser())
    walk(build_parser())
    return sorted(found - {"--device-id"})  # --device-id is set by `devices ID`, not typed


def collections_edit(args):
    from . import collectionedit  # imported late: it reaches this module through edit
    return collectionedit.edit_collections()


def themes_update(args):
    from . import themeart
    usersettings.ensure_bucket()
    return themeart.update_storage(args.dry_run)


def second_words():
    """{command: the words that can follow it} for the commands that have subcommands."""
    from . import cli
    words = {}
    for key in cli.LEGACY:
        if len(key) > 1:
            words.setdefault(key[0], []).append(key[1])
    words["games"] = sorted(set(words.get("games", [])) | {"list", "add", "remove", "full", "sets", "export", "import"})
    words["sets"] = ["edit"]
    words["collections"] = ["edit"]
    words["themes"] = ["update"]
    words["cards"] = ["edit", "list", "new", "set", "rename", "delete"]
    words["config"] = ["show", "path"]
    words["cache"] = ["update"]
    words["completion"] = ["bash", "zsh", "fish"]
    return words


def completion_cmd(args):
    if args.shell == "list":
        print("\n".join(completion_lists(args.what or "")))
        return 0
    from .cli import SUBCOMMANDS
    subs = " ".join(SUBCOMMANDS)
    flag_list = all_flags()
    flags = " ".join(flag_list)
    second = second_words()
    if args.shell in ("bash", "zsh"):
        cases = "\n".join(f"      {name}) COMPREPLY=($(compgen -W \"{' '.join(w)}\" -- \"$cur\")); return;;" for name, w in second.items())
        script = f'''_sync_roms() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}" prev="${{COMP_WORDS[COMP_CWORD-1]}}" cmd="${{COMP_WORDS[1]}}"
  case "$prev" in
    --card) COMPREPLY=($(compgen -W "$(sync-roms completion list cards)" -- "$cur")); return;;
    --device) COMPREPLY=($(compgen -W "$(sync-roms completion list devices)" -- "$cur")); return;;
    --layout) COMPREPLY=($(compgen -W "$(sync-roms completion list layouts)" -- "$cur")); return;;
    --system) COMPREPLY=($(compgen -W "$(sync-roms completion list systems)" -- "$cur")); return;;
    --profile|--write-profile|--bucket|--root|--endpoint) return;;
  esac
  if [[ "$cur" == -* ]]; then COMPREPLY=($(compgen -W "{flags}" -- "$cur")); return; fi
  if [ "$COMP_CWORD" -eq 1 ]; then COMPREPLY=($(compgen -W "{subs}" -- "$cur") $(compgen -d -- "$cur")); return; fi
  if [ "$COMP_CWORD" -eq 2 ]; then
    case "$cmd" in
{cases}
    esac
  fi
  if [ "$COMP_CWORD" -eq 3 ] && [ "$cmd" = games ]; then
    case "${{COMP_WORDS[2]}}" in add|remove|full) COMPREPLY=($(compgen -W "$(sync-roms completion list systems)" -- "$cur")); return;; esac
  fi
  COMPREPLY=($(compgen -f -- "$cur"))
}}
complete -o filenames -F _sync_roms sync-roms
'''
        print(("autoload -U +X bashcompinit && bashcompinit\n" if args.shell == "zsh" else "") + script, end="")
    else:
        lines = [f'complete -c sync-roms -f -n __fish_use_subcommand -a "{subs}"']
        for name, w in second.items():
            lines.append(f'complete -c sync-roms -f -n "__fish_seen_subcommand_from {name}; and not __fish_seen_subcommand_from {" ".join(w)}" -a "{" ".join(w)}"')
        values = {"card": "cards", "device": "devices", "layout": "layouts", "system": "systems"}
        for flag in (f for f in flag_list if f.startswith("--")):
            name = flag[2:]
            if name in values:
                lines.append(f'complete -c sync-roms -l {name} -x -a "(sync-roms completion list {values[name]})"')
            else:
                lines.append(f"complete -c sync-roms -l {name}")
        print("\n".join(lines))
    return 0


# --- Dispatch ---------------------------------------------------------------------------------------

def build_parser():
    ap = Parser(prog="sync-roms", add_help=False, allow_abbrev=False)
    sub = ap.add_subparsers(dest="command")

    def common(p, card=True):
        p.add_argument("-n", "--dry-run", action="store_true")
        p.add_argument("-y", "--yes", action="store_true")
        if card:
            p.add_argument("--card")

    games = sub.add_parser("games", add_help=False, allow_abbrev=False)
    gsub = games.add_subparsers(dest="action", required=True)
    p = gsub.add_parser("list", allow_abbrev=False); common(p); p.add_argument("--json", action="store_true"); p.set_defaults(fn=games_list)
    p = gsub.add_parser("add", allow_abbrev=False); common(p); p.add_argument("system"); p.add_argument("keys", nargs="+"); p.set_defaults(fn=games_add)
    p = gsub.add_parser("remove", allow_abbrev=False); common(p); p.add_argument("system"); p.add_argument("keys", nargs="+"); p.set_defaults(fn=games_remove)
    p = gsub.add_parser("full", allow_abbrev=False); common(p); p.add_argument("system"); p.add_argument("state", choices=["on", "off"]); p.set_defaults(fn=games_full)
    p = gsub.add_parser("sets", allow_abbrev=False); common(p); p.add_argument("verb", choices=["list", "add", "remove"])
    p.add_argument("set_id", nargs="?"); p.set_defaults(fn=games_sets)
    p = gsub.add_parser("export", allow_abbrev=False); common(p); p.set_defaults(fn=games_export)
    p = gsub.add_parser("import", allow_abbrev=False); common(p); p.add_argument("file"); p.set_defaults(fn=games_import)

    sets = sub.add_parser("sets", add_help=False, allow_abbrev=False)
    ssub = sets.add_subparsers(dest="action", required=True)
    p = ssub.add_parser("edit", allow_abbrev=False); p.set_defaults(fn=lambda a: setedit.edit_sets())

    collections = sub.add_parser("collections", add_help=False, allow_abbrev=False)
    colsub = collections.add_subparsers(dest="action", required=True)
    p = colsub.add_parser("edit", allow_abbrev=False)
    p.set_defaults(fn=collections_edit)

    themes = sub.add_parser("themes", add_help=False, allow_abbrev=False)
    tsub = themes.add_subparsers(dest="action", required=True)
    p = tsub.add_parser("update", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=themes_update)

    cards = sub.add_parser("cards", add_help=False, allow_abbrev=False)
    csub = cards.add_subparsers(dest="action", required=True)
    p = csub.add_parser("list", allow_abbrev=False); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cards_list)
    for name, create in (("new", True), ("set", False)):
        p = csub.add_parser(name, allow_abbrev=False); common(p, card=False); p.add_argument("name")
        p.add_argument("--device"); p.add_argument("--layout"); p.add_argument("--size", help="the card's size, e.g. 256, 512GB, 1TB"); p.set_defaults(fn=lambda a, c=create: cards_save_setup(a, c))
    p = csub.add_parser("rename", allow_abbrev=False); common(p, card=False); p.add_argument("old"); p.add_argument("new"); p.set_defaults(fn=cards_rename)
    p = csub.add_parser("delete", allow_abbrev=False); common(p, card=False); p.add_argument("name"); p.set_defaults(fn=cards_delete)

    p = sub.add_parser("config", allow_abbrev=False); common(p, card=False); p.add_argument("action", choices=["show", "path"], nargs="?", default="show"); p.set_defaults(fn=config_cmd)
    p = sub.add_parser("cache", allow_abbrev=False); common(p, card=False); p.add_argument("action", choices=["update"], nargs="?"); p.add_argument("--full", action="store_true"); p.set_defaults(fn=cache_cmd)
    p = sub.add_parser("doctor", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=doctor_cmd)
    p = sub.add_parser("check", allow_abbrev=False); common(p, card=False); p.add_argument("--bucket-keys", action="store_true"); p.set_defaults(fn=check_cmd)
    p = sub.add_parser("completion", allow_abbrev=False); common(p, card=False); p.add_argument("shell", choices=["bash", "zsh", "fish", "list"])
    p.add_argument("what", nargs="?"); p.set_defaults(fn=completion_cmd)
    return ap


def run(argv):
    args = build_parser().parse_args(argv)
    ui.ASSUME_YES = getattr(args, "yes", False)
    return args.fn(args) or 0
