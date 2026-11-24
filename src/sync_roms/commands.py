"""Scriptable subcommands: games, sets, collections, themes, download, flash, unmount, mount, cards, saves, layouts, cache, config,
doctor, guide, check and completion; plus helpers the sync flow uses."""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import webbrowser

from . import collections as colls
from . import budget, cardedit, cardshare, collectionedit, external, guest, inventory, m3u, names, picker, runtime, s3, setedit, spruce_settings, store, surprise, themeart, ui, usersettings


UNKNOWN_SHOWN = 8  # device ids named in an "unknown device" error
COMMANDS = {"games", "sets", "collections", "themes", "download", "flash", "unmount", "umount", "mount", "cards", "saves", "layouts", "cache", "config", "doctor", "guide", "check", "completion"}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        name = self.prog.split()[1]
        if message == "the following arguments are required: action":  # a command typed without its subcommand
            ui.fail(f"'{name}' needs a subcommand: " + ", ".join(f"{name} {w}" for w in second_words()[name]), 2)
        ui.fail(f"{message}\n   Try 'sync-roms {name} --help'.", 2)


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
    ui.table(rows, ("Device", "Chip", "Systems", "Id"))
    return 0


def show_layouts(layouts, devices, layout_id=None, as_json=False):
    """Print the firmware layout table, or one layout's folders, note and devices."""
    runs = {name: [d for d in devices if name in d["firmwares"]] for name in layouts}
    if layout_id:
        if layout_id not in layouts:
            ui.fail(f"Unknown layout {layout_id!r}. Known: {', '.join(layouts)}\n   `sync-roms layouts` lists them all.", 2)
        layout, users = layouts[layout_id], runs[layout_id]
        if as_json:
            ui.emit_json({"id": layout_id, **layout, "devices": [d["id"] for d in users]})
            return 0
        print(ui.bold(f"💾 {layout['label']}") + ui.dim(f"  ({layout_id})"))
        for key, value in layout.items():
            if key.endswith("_dir"):
                print(f"  {key[:-4]}: {value}/")
        if layout.get("note"):
            print(ui.dim(f"  {layout['note']}"))
        for d in users:
            print(f"  {d['id']:<28} {d['name']}" + (ui.dim("  (default)") if d["firmwares"][0] == layout_id else ""))
        return 0
    if as_json:
        ui.emit_json([{"id": name, **layout, "devices": [d["id"] for d in runs[name]]} for name, layout in layouts.items()])
        return 0
    rows = [(layout["label"], layout["roms_dir"], layout["bios_dir"], str(len(runs[name])), name) for name, layout in layouts.items()]
    ui.table(rows, ("Firmware", "ROMs", "BIOS", "Devices", "Id"))
    return 0


def layouts_cmd(args):
    return show_layouts(store.repo_json("layouts"), store.repo_json("devices"), args.layout_id, args.json)


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
            entry.append({"title": names.title(key), "bucket": key})
            have.add(key)
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
    keys = resolve_keys(args.system, args.keys)
    tree = inventory.current()
    cached = tree.under(args.system + "/") if tree else {}
    for key in keys if cached else []:  # a cache without the system's folder says nothing about its files
        if key not in cached:
            ui.warn(f"{key} isn't in the storage cache: check the name, or run {inventory.UPDATE_HINT} if it was just added")
    return finish(args, raw, save, add_games(raw, args.system, keys))


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


def full_entry(entry):
    """A full system's entry replacing entry: a game list stays in it for `games full off`, as cardedit.toggle_full
    keeps it."""
    return {"full_system": True, **({"games": entry} if isinstance(entry, list) and entry else {})}


def games_full(args):
    need_system(args.system)
    raw, save = load_target(args.card)
    entry = raw.get(args.system)
    now = isinstance(entry, dict)
    if args.state == "on" and not now:
        raw[args.system] = full_entry(entry)
        return finish(args, raw, save, [("+", f"{args.system} (full system)")])
    if args.state == "off" and now:
        if entry.get("games"):
            raw[args.system] = entry["games"]
        else:
            del raw[args.system]
        return finish(args, raw, save, [("-", f"{args.system} (full system)")])
    return finish(args, raw, save, [])


def games_sets(args):
    raw, save = load_target(args.card)
    known = {x["id"]: x for x in store.load_sets()}
    if args.verb == "list":
        on = store.list_sets(raw)
        ui.table([(f"{'✅' if set_id in on else '⬜'} {set_id}", f"{themeart.set_emoji(x)} {x['name']}") for set_id, x in known.items()])
        return 0
    if not args.set_id:
        ui.fail(f"sets {args.verb} needs a set id. Known: {', '.join(known)}", 2)
    on = list(store.list_sets(raw))
    if args.set_id not in known and not (args.verb == "remove" and args.set_id in on):  # a card may name a gone set
        ui.fail(f"Unknown set {args.set_id!r} (run `{inventory.UPDATE_HINT}` if another machine added it). "
                f"Known: {', '.join(known)}", 2)
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
CARD_FIELDS = ("collections", "frontend_collections", "drivers", "boot_logos", "surprise", "surprises", "pico8")
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
            if isinstance(card, dict) and surprise.enabled(card) != surprise.default_on(card):
                print(f"@surprise {'true' if surprise.enabled(card) else 'false'}")
            continue
        if field == "pico8":
            if isinstance(card, dict) and isinstance(card.get("pico8"), str) and card["pico8"]:
                print(f"@pico8 {card['pico8']}")
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
            entry = {"system": system, "bucket": key, "title": names.title(key)}
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
            if field == "pico8":
                if text.strip():
                    fields["pico8"] = text.strip()
                else:
                    ui.warn(f"skipping {line!r}: expected @pico8 FILE")
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
                raw[system] = full_entry(raw.get(system))
                changes.append(("+", f"{system} (full system)"))
        else:
            by_system.setdefault(system, []).append(line)
    for system, keys in by_system.items():
        changes += add_games(raw, system, keys)
    for field, values in fields.items():
        if field == "pico8":
            changes.append(("+", f"pico8: {values}"))
            continue
        changes.append(("+", f"{field}: {', '.join(CARD_HOOKS.get(field, (None, str))[1](v) for v in values)}"))

    def save_all(raw):
        if save(raw) is False:
            return False
        values = dict(fields)
        if surprise_keys:
            values["surprises"] = surprise_entries(surprise_keys)
        if values and store.update_card(args.card, **values) is False:
            return False
        if surprise_state is not None:
            cards = store.load_cards()
            entry = cards.setdefault(args.card, {})
            if isinstance(entry, dict):
                surprise.set_enabled(entry, surprise_state)
                return store.write_cards(cards)
        return None

    return finish(args, raw, save_all, changes)


# --- Cards ------------------------------------------------------------------------------------------

def cards_list(args):
    cards = store.load_cards()
    manifest = store.load_catalog()
    rows = []
    hidden = 0
    for name in sorted(cards):
        if guest.is_guest(cards[name]) and not args.all:
            hidden += 1
            continue
        setup = picker.saved_setup(cards[name], manifest["devices"], manifest["layouts"])
        games = store.card_games(name, cards)
        extras = sum(len(v) if isinstance(v, list) else 1 for v in games.values())
        usage = full = picked = None
        if setup:
            # what a sync of the picks puts on the card (ROMs, the layout's scrapes, BIOS), from the size cache
            entry, systems = cardedit.card_entry(name, setup, cards), cardedit.can_play(manifest["systems"], setup)
            usages = budget.system_usages(entry, systems)
            usage = budget.card_usage(entry, systems, usages)
            off = store.systems_off(entry)
            full = {b for b in usages if isinstance(games.get(b), dict) and games[b].get("full_system") and b not in off}
            picked = sum(u.count for b, u in usages.items() if b not in full)  # direct, set and collection games
        rows.append({"name": name, "device": (setup[0]["id"] if setup[0] else "full") if setup else None,
                     "layout": setup[1] if setup else None, "size": cards[name].get("size") if isinstance(cards[name], dict) else None,
                     "used": usage.bytes if usage else None, "sized": not usage.partial if usage else None,
                     "full_systems": len(full) if setup else None, "games": picked, "extras": extras,
                     "guest": guest.is_guest(cards[name]),
                     "surprise": surprise.enabled(cards[name]), "theme": store.card_flag(cards[name], "theme"),
                     "collections": store.card_flag(cards[name], "custom_collections"),
                     "raofflineproxy": store.card_flag(cards[name], "raofflineproxy")})
    if args.json:
        ui.emit_json(rows)
        return 0

    # numbers are right-aligned within their column so sizes and counts line up
    width = lambda values: max((len(v) for v in values), default=0)
    unsized = any(r["sized"] is False for r in rows)
    amount = lambda r: "*" if r["sized"] is False else cardedit.size_text(r["used"])  # a partial size means nothing
    used_w = width([amount(r) for r in rows if r["used"] is not None])
    size_w = width([r["size"] for r in rows if r["size"]])
    full_w = width([str(r["full_systems"]) for r in rows if r["games"] is not None])
    games_w = width([str(r["games"] if r["games"] is not None else r["extras"]) for r in rows])
    plural = lambda n, w, word: f"{n:>{w}} {word}" + ("" if n == 1 else "s")

    def used(r):
        if r["used"] is None:
            return " " * (used_w + 3) + (r["size"] or "").rjust(size_w) if r["size"] else ""
        if r["sized"] is False:
            return "*".rjust(used_w) + (f" / {r['size']:>{size_w}}" if r["size"] else "")
        # no size set: a ❔ in the size slot (two columns wide) keeps the rest of the row aligned
        return amount(r).rjust(used_w) + (f" / {r['size']:>{size_w}}" if r["size"] else " / " + "❔".rjust(size_w - 1))

    def picks(r):
        if r["games"] is None:
            return ("", f"{r['extras']:>{games_w}} game entries")
        return (plural(r["full_systems"], full_w, "full system"), plural(r["games"], games_w, "game"))

    # one fixed two-column slot per status emoji (blank when it doesn't apply), so several line up; add new ones here
    badges = lambda r: "".join(emoji if on else "  " for emoji, on in [("🎁", r["surprise"]), ("🎨", r["theme"]),
                                                                         ("💖", r["collections"]), ("🏆", r["raofflineproxy"]),
                                                                         ("👤", r["guest"])])
    ui.table([(r["name"], r["device"] or "(no device set)", r["layout"] or "", used(r), *picks(r), badges(r))
              for r in rows])
    if hidden:
        print(ui.dim(f"{hidden} guest card{'' if hidden == 1 else 's'} hidden (--all shows them)"))
    if unsized:
        print()
        print(ui.dim("* Not sized: there is no storage cache yet, so full-system folders can't be counted.\n"
                     f"  Build it with: {inventory.UPDATE_HINT}"))
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
        size = budget.parse_size(args.size)
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


def cards_clean(args):
    from . import convert
    return convert.clean_command(args)


def cards_convert(args):
    from . import convert
    return convert.convert_command(args)


def cards_install(args):
    from . import install
    return install.run(args)


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


def cards_copy(args):
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so no card can be saved. Fix or move it first.", 3)
    cards = store.load_cards()
    for name in (args.src, args.dst):
        if name not in cards:
            ui.fail(f"No card named {name!r}", 2)
    if args.src == args.dst:
        ui.fail("Pick two different cards", 2)
    catalog = store.load_catalog()
    setup = picker.saved_setup(cards[args.dst], catalog["devices"], catalog["layouts"], args.dst)
    if setup is None:
        ui.fail(f"Card {args.dst!r} has no usable device and layout", 2)
    playable = {s["bucket"] for s in catalog["systems"] if store.system_applies(s, *setup)}
    dst_synced = {s["bucket"]: set(store.listed(s)) for s in store.load_manifest([args.dst], keep_off=True)["systems"]}
    cards = store.load_cards()
    entry, counts, skipped = cardshare.copy_selections(cards[args.src], cards[args.dst], playable, dst_synced)
    shown = f"{counts['games']} games, {counts['full']} full systems, {counts['sets']} sets, {counts['collections']} collections, {counts['excluded']} exclusions"
    if args.dry_run:
        print(ui.yellow(f"🧪 Would copy from {args.src} to {args.dst}: {shown}"))
    else:
        cards[args.dst] = entry
        if not store.write_cards(cards):
            return 3
        print(ui.green(f"📋 Copied from {args.src} to {args.dst}: {shown}"))
    if skipped:
        print(ui.dim(f"  skipped ({args.dst} can't play them): {', '.join(skipped)}"))
    return 0


def cards_export(args):
    cards = store.load_cards()
    if not cards:
        ui.fail("No cards yet", 2)
    chosen = cardshare.pick_export(sorted(cards))
    if not chosen:
        print(ui.yellow("↩️  Nothing exported"))
        return 0
    if args.dry_run:
        print(ui.yellow(f"🧪 Would export {len(chosen)} card(s) to {args.file}"))
        return 0
    if os.path.exists(args.file) and not args.yes and not ui.confirm(f"Overwrite {args.file}?", default=False):
        print(ui.yellow("↩️  Kept"))
        return 0
    by_id = {c["id"]: c for c in colls.load_collections()}
    try:
        with open(args.file, "w") as f:
            f.write(json.dumps({name: cardshare.export_entry(cards[name], by_id) for name in chosen}, indent=2) + "\n")
    except OSError as e:
        ui.fail(f"Couldn't write {args.file}: {e}", 3)
    print(ui.green(f"💾 Exported {len(chosen)} card(s) to {args.file}"))
    return 0


def cards_import(args):
    try:
        with open(args.file) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        ui.fail(f"Can't read {args.file}: {e}", 2)
    if not isinstance(data, dict):
        ui.fail(f"{args.file} isn't a cards file ({{name: card}})", 2)
    source = {name: entry for name, entry in data.items() if isinstance(entry, dict)}
    if not source:
        ui.fail(f"No cards in {args.file}", 2)
    if not store.cards_readable():
        ui.fail(f"{os.path.join(store.data_dir(), 'cards.json')} isn't valid JSON, so no card can be saved. Fix or move it first.", 3)
    cards = store.load_cards()
    manifest = store.load_catalog()
    chosen = cardshare.pick_import(source, set(cards), {d["id"] for d in manifest["devices"]}, set(manifest["layouts"]))
    if not chosen:
        print(ui.yellow("↩️  Nothing imported"))
        return 0
    shown = ", ".join(new if new == old else f"{old} → {new}" for new, old in chosen.items())
    if args.dry_run:
        print(ui.yellow(f"🧪 Would import: {shown}"))
        return 0
    for new, old in chosen.items():
        cards[new] = cardshare.import_entry(source[old])
    if not store.write_cards(cards):
        return 3
    print(ui.green(f"💾 Imported: {shown}"))
    return 0


# --- config, check, doctor ---------------------------------------------------------------------------

def effective_settings():
    """[(name, value, source)] for the settings sync-roms reads."""
    out = [(name, value, source) for name, (value, source) in usersettings.resolve_settings().items()]
    mirror = usersettings.load_settings().get("mirror")
    out.append(("mirror", mirror, "settings.json" if mirror else "unset"))
    eject = usersettings.load_settings().get("eject")
    out.append(("eject", eject is not False, "default" if eject is None else "settings.json"))
    return out


CONFIG_KINDS = {"bucket": str, "root": str, "endpoint": str, "profile": str, "write_profile": str, "mirror": str,
                "eject": bool, "storage_cache_declined": bool, "surprise_ttl_days": int, "surprise_excluded_systems": list,
                "screenscraper_user": str, "screenscraper_password": str, "ra_mode": str, "ra_username": str,
                "ra_password": str, "ra_api_key": str, "ra_offline_proxy": bool,
                "ra_proxy_stats": bool, "syncthing": bool}  # the settings `config set` and `config unset` take
HIDDEN = {"screenscraper_password", "ra_password", "ra_api_key"}  # set, never printed


def config_value(name, text):
    """The JSON value `config set NAME TEXT` saves; exits 2 when TEXT doesn't fit the setting."""
    kind = CONFIG_KINDS[name]
    if kind is bool:
        if text not in ("true", "false"):
            ui.fail(f"{name} is true or false, not {text!r}", 2)
        return text == "true"
    if kind is int:
        try:
            return _positive_int(text)
        except argparse.ArgumentTypeError as e:
            ui.fail(f"{name}: {e}", 2)
    if kind is list:
        ids = [i.strip() for i in text.split(",") if i.strip()]
        unknown = [i for i in ids if i not in system_ids()]
        if unknown or not ids:
            ui.fail(f"{name} takes comma-separated system ids; unknown: {', '.join(unknown) or '(none given)'}\n"
                    "   `sync-roms completion list systems` lists them.", 2)
        return ids
    if name == "ra_mode" and text not in spruce_settings.MODES:
        ui.fail(f"{name} is one of {', '.join(spruce_settings.MODES)}, not {text!r}", 2)
    if not text:
        ui.fail(f"{name} can't be empty: `sync-roms config unset {name}` removes it", 2)
    if name in ("root", "mirror"):  # saved absolute, as the first-run prompt and `mirror use` do, so it doesn't move with the cwd
        text = os.path.expanduser(text)
        if not os.path.isabs(text):
            ui.fail(f"{text} is not an absolute path: give the whole folder path, e.g. /Volumes/roms", 2)
    return text


IMPORTERS = {"spruce": spruce_settings.import_settings}  # card layout -> importer(card folder): saves the card's settings in settings.json


def import_settings(card):
    """`config import [CARD]`: CARD is a card name saved in cards.json (its folder /Volumes/<name>) or a folder, whose basename is
    the card name, else the current folder. The importer comes from the card's saved layout."""
    if card and not os.path.isdir(os.path.expanduser(card)) and os.sep not in card:
        base, name = os.path.join("/Volumes", card), card
    else:
        base = os.path.abspath(os.path.expanduser(card or os.getcwd()))
        name = os.path.basename(base)
    saved = store.saved_card(name)
    if not saved:
        ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
    layout = saved.get("layout")
    if not layout:
        ui.fail(f"{name!r} has no layout. Set it with `sync-roms cards set {name} --layout NAME`, or sync the card once", 2)
    if layout not in IMPORTERS:
        ui.fail(f"importing settings from {layout} cards isn't supported yet (supported: {', '.join(IMPORTERS)})", 2)
    if not os.path.isdir(base):
        ui.fail(f"No folder {base}: give the card's mounted folder, e.g. `sync-roms config import /Volumes/{name}`", 2)
    return IMPORTERS[layout](base)


def config_cmd(args):
    name, value = getattr(args, "name", None), getattr(args, "value", None)
    if args.action == "import":
        if value is not None:
            ui.fail("`config import` takes only a card name or folder", 2)
        return import_settings(name)
    if args.action == "apply":
        if value is not None:
            ui.fail("`config apply` takes only a card name or folder", 2)
        from . import settings_apply
        return settings_apply.run(name, args.dry_run)
    if args.action in ("set", "unset"):
        if name not in CONFIG_KINDS:
            ui.fail((f"Unknown setting {name!r}" if name else f"`config {args.action}` needs a setting's name")
                    + f". Known: {', '.join(CONFIG_KINDS)}", 2)
        if args.action == "unset":
            if value is not None:
                ui.fail("`config unset` takes only the setting's name", 2)
            if name not in usersettings.load_settings():
                print(ui.dim(f"{name} wasn't set in settings.json"))
                return 0
            usersettings.save_setting(name, None)
            print(ui.green(f"💾 Removed {name} from settings.json"))
            return 0
        if value is None:
            ui.fail(f"`config set {name}` needs a value", 2)
        saved = config_value(name, value)
        usersettings.save_setting(name, saved)
        shown = ",".join(saved) if isinstance(saved, list) else saved if isinstance(saved, str) else json.dumps(saved)
        print(ui.green(f"💾 Saved {name} = {'(not shown)' if name in HIDDEN else shown} in settings.json"))
        return 0
    if name is not None:
        ui.fail(f"`config {args.action}` takes no arguments ({name!r})", 2)
    if args.action == "path":
        print(store.data_dir())
        return 0
    print(ui.bold("⚙️  sync-roms settings") + ui.dim(f"  {store.data_dir()}"))
    for name, value, source in effective_settings():
        print(f"  {name:<14} {(json.dumps(value) if isinstance(value, bool) else str(value)) if value is not None else ui.dim('(not set)'):<28} {ui.dim(source)}")
    return 0


def cache_cmd(args):
    if args.full and args.action != "update":
        ui.fail("--full only applies to `cache update`", 2)
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
    return check_game_data(problems, data, where, systems)


def check_game_data(problems, data, where, systems):
    """check_game_file's checks of a file's parsed JSON."""
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
        if not isinstance(g.get("series", ""), str):
            problems.append(f"{where}: {g['bucket']}: 'series' must be a string")
        listed += check_keys(problems, where, system, g)
    return listed


def check_keys(problems, where, system, game):
    """[(system, key)] of a game's bucket key and 'files' that are under system/; the rest go to problems."""
    files = game.get("files", [])
    if not isinstance(files, list) or not all(isinstance(k, str) for k in files):
        problems.append(f"{where}: {game['bucket']}: 'files' must be a list of bucket keys")
        files = []
    listed = []
    for k in [game["bucket"]] + files:
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
    """Check every set in storage and return the keys each one lists as {"sets/<id>.json": [(system, key)]}.

    systems: the set of known system ids."""
    sets = store.set_files()
    problems.extend(f"{key}: isn't a set (a JSON object with a games list)" for key in store.skipped_sets())
    art = themeart.art_choices()
    keys = {}
    for game_set in sets:
        where = f"{store.SETS}{game_set['id']}.json"
        keys[where] = check_game_data(problems, game_set, where, systems)
        if game_set.get("art") and game_set["art"] not in art:
            problems.append(f"{where}: unknown art {game_set['art']!r}")
    return keys


def check_set_notices():
    """Sets with no art of their own, or showing the same art as another set, as notices."""
    art, by_art = themeart.art_choices(), {}
    for game_set in store.set_files():
        by_art.setdefault(game_set.get("art") or game_set["id"], []).append(game_set["id"])
    bare = sorted(i for a, ids in by_art.items() if a not in art for i in ids)
    out = [f"sets: {len(bare)} set(s) have no art in art.json, so they show {themeart.SET_EMOJI} and get no picture: "
           + ", ".join(bare)] if bare else []
    return out + [f"sets: {', '.join(sorted(ids))} share the art {a!r}"
                  for a, ids in sorted(by_art.items()) if a in art and len(ids) > 1]


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
    drivers = store.repo_json("drivers")
    driver_ids = set()
    for dr in drivers["drivers"]:
        if not re.fullmatch(r"[a-z0-9-]+", dr["id"]):
            problems.append(f"drivers.json: driver id {dr['id']!r} must be lowercase letters, digits and dashes")
        if dr["id"] in driver_ids:
            problems.append(f"drivers.json: duplicate driver id {dr['id']!r}")
        driver_ids.add(dr["id"])
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", dr["repo"]):
            problems.append(f"drivers.json: {dr['id']}: repo must look like owner/name, not {dr['repo']!r}")
        try:
            re.compile(dr["asset"])
        except re.error as e:
            problems.append(f"drivers.json: {dr['id']}: asset is not a valid regex ({e})")
    used = set()
    for gid, g in drivers["gpus"].items():
        for i in g["drivers"]:
            used.add(i)
            if i not in driver_ids:
                problems.append(f"drivers.json: {gid}: unknown driver {i!r}")
    problems.extend(f"drivers.json: driver {i!r} is not used by any gpu" for i in sorted(driver_ids - used))
    problems.extend(
        f"devices.json: {d['id']}: unknown gpu {d['gpu']!r}"
        for d in store.repo_json("devices")
        if "gpu" in d and d["gpu"] not in drivers["gpus"]
    )
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
                    problems.extend(f"{where}: unknown set {i!r} (run `{inventory.UPDATE_HINT}` if another machine "
                                    "added it)" for i in entry if i not in sets)
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
        for field in ("frontend_collections", "drivers", "boot_logos"):
            names = entry.get(field, [])
            if not isinstance(names, list) or not all(isinstance(i, str) for i in names):
                problems.append(f"cards.json: {name}: '{field}' must be a list of names")
        for field in ("pico8", "spruce_os"):
            if field in entry and not (isinstance(entry[field], str) and entry[field]):
                problems.append(f"cards.json: {name}: '{field}' must be a file name")
        if "spruce_emu" in entry and not (isinstance(entry["spruce_emu"], dict) and all(
                isinstance(v, list) and all(isinstance(i, str) for i in v) for v in entry["spruce_emu"].values())):
            problems.append(f"cards.json: {name}: 'spruce_emu' must map folders to lists of file names")
        if "muos_storage" in entry and entry["muos_storage"] not in ("sd1", "sd2"):
            problems.append(f"cards.json: {name}: 'muos_storage' must be sd1 or sd2")
        if "surprise" in entry and not isinstance(entry["surprise"], bool):
            problems.append(f"cards.json: {name}: 'surprise' must be true or false")
        for flag in ("theme", "custom_collections"):
            if flag in entry and not isinstance(entry[flag], bool):
                problems.append(f"cards.json: {name}: '{flag}' must be true or false")
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
                    where = f"cards.json: {name}: surprises"
                    wanted.setdefault(where, []).extend(check_keys(problems, where, g["system"], g))
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
        ui.failure(ui.red(f"❌ {p}"))
    for n in check_notices(repo_systems) + check_set_notices():
        print(ui.yellow(f"⚠️  {n}"))
    if not problems:
        print(ui.green("✅ cards.json, surprises.json, device-systems.json, the sets and your collections look fine"))
    return 1 if problems else 0


def guide_cmd(args):
    """Open the device setup guide in the default browser: a copy in the cache folder with your cards filled in."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "setup-guide.html")
    with open(src, encoding="utf-8") as f:
        html = f.read()
    cards = [{"name": n, "device": c.get("device"), "layout": c.get("layout")}
             for n, c in store.load_cards().items() if isinstance(c, dict) and not c.get("guest")]
    block = json.dumps(cards).replace("<", "\\u003c")
    path = os.path.join(store.cache_dir(), "setup-guide.html")
    os.makedirs(store.cache_dir(), exist_ok=True)
    store.write_text(path, html.replace('id="cards-data">[]<', f'id="cards-data">{block}<', 1))
    print(path)
    if not webbrowser.open(pathlib.Path(path).as_uri()):
        ui.fail("Couldn't open a browser: open the file above yourself", 1)
    return 0


def doctor_cmd(args):
    bad = 0

    def line(ok, text, hint=""):
        nonlocal bad
        bad += ok is False
        print(f"{'✅' if ok else '⚠️ ' if ok is None else '❌'} {text}" + (ui.dim(f"  → {hint}") if hint and not ok else ""))

    problem = usersettings.settings_problem()
    if problem:
        line(False, problem)
    settings = {"bucket": runtime.BUCKET} if problem else dict((n, v) for n, v, _ in effective_settings())
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
            line(None, f"write profile {runtime.WRITE_PROFILE} not found", "only needed for upload, clean, saving sets and saving scrape state")
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
    return collectionedit.edit_collections()


def themes_update(args):
    from . import spruce_themes, themeart
    usersettings.ensure_bucket()
    return max(themeart.update_storage(args.dry_run), spruce_themes.update_storage(args.dry_run))


def style_args(args):
    """The style names given (None for all of them); an unknown one exits 2 naming the styles."""
    from . import custom_themes
    unknown = [n for n in args.names if n not in custom_themes.STYLES]
    if unknown:
        ui.fail(f"Unknown theme style {', '.join(unknown)}; the custom theme styles are: {', '.join(custom_themes.styles())}", 2)
    return list(dict.fromkeys(args.names)) or None


def palette_args(args):
    """The palettes to build: every one with --all-palettes; else the --palette names (duplicates dropped, first order
    kept; an unknown one exits 2 naming the palettes); else, with a terminal and without --yes, the picker, starting
    from the saved selection, which a confirmed choice replaces (Esc exits 0, nothing on exits 2); else the saved
    selection, and none saved exits 2 naming the palettes. Flags never change the saved selection."""
    from .custom_themes import palette_picker, palettes
    known = ", ".join(palettes.names())
    if args.all_palettes:
        return list(palettes.PALETTES.values())
    chosen = list(dict.fromkeys(args.palette or []))
    if chosen:
        unknown = [n for n in chosen if n not in palettes.PALETTES]
        if unknown:
            ui.fail(f"Unknown palette {', '.join(unknown)}; the palettes are: {known}", 2)
    elif ui.has_terminal() and not ui.ASSUME_YES:
        chosen = palette_picker.pick("🎨 Palettes to build the custom themes in", palette_picker.saved())
        if chosen is None:
            print("Cancelled: nothing built")
            sys.exit(0)
        if not chosen:
            ui.fail("No palette chosen: nothing built", 2)
        palette_picker.save(chosen)
    else:
        chosen = palette_picker.saved()
        if not chosen:
            ui.fail("No palettes saved: choose them with --palette NAME (repeatable) or --all-palettes, or in the "
                    f"picker (run it in a terminal without --yes); the palettes are: {known}", 2)
    return [palettes.get(n) for n in chosen]


def themes_build(args):
    from . import custom_themes
    usersettings.ensure_bucket()
    styles = style_args(args)
    chosen = palette_args(args) if custom_themes.needs_palettes(styles) else []
    try:
        built = custom_themes.build(styles, chosen, args.out)
    except custom_themes.BaseMissing as e:
        ui.fail(f"{e}: run `sync-roms themes update` first (or `sync-roms cache update` if another machine put it there)", 1)
    except s3.ERRORS as e:
        ui.fail(f"Couldn't read the base theme from {s3.location()}: {e}", 1)
    for name, folder in built.items():
        print(f"🎨 {name}: {folder}")
    return 0


def themes_publish(args):
    from . import custom_themes
    usersettings.ensure_bucket()
    styles = style_args(args)
    chosen = palette_args(args) if custom_themes.needs_palettes(styles) else []
    try:
        return custom_themes.publish(styles, chosen, args.dry_run)
    except custom_themes.BaseMissing as e:
        ui.fail(f"{e}: run `sync-roms themes update` first (or `sync-roms cache update` if another machine put it there)", 1)
    except custom_themes.DownloadFailed as e:
        ui.fail(f"{e}", 1)
    except json.JSONDecodeError as e:
        ui.fail(f"{runtime.CUSTOM_THEMES_STATE} or {runtime.SPRUCE_THEMES_STATE} in {s3.location()} isn't valid JSON ({e}). Fix or move it first.", 3)
    except s3.ERRORS as e:
        ui.fail(f"Couldn't publish to {s3.location()}: {e}", 1)


def themes_palettes(args):
    """Write the palette overview image and open it in the default viewer."""
    from .custom_themes import palette_sheet
    try:
        path = palette_sheet.write_sheet(os.path.join(store.cache_dir(), "themes", "palettes.png"))
    except OSError as e:
        ui.fail(f"Couldn't write the palette overview: {e}", 1)
    print(path)
    if not webbrowser.open(pathlib.Path(path).as_uri()):
        ui.fail("Couldn't open a viewer: open the file above yourself", 1)
    return 0


def themes_pick(args):
    from . import spruce_themes
    usersettings.ensure_bucket()
    ui.require_terminal("pick themes", "a terminal")
    chosen = spruce_themes.pick("🎨 Spruce themes synced by default", spruce_themes.default_list())
    if chosen is None:
        return 0
    settings = usersettings.load_settings()
    settings["spruce_themes"] = sorted(chosen, key=lambda n: (n.lower(), n))
    usersettings.save_settings(settings)
    print(f"✅ {len(chosen)} Spruce theme(s) on by default")
    return 0


def download_pico8(args):
    from . import bbs
    return bbs.download_pico8(args)


def saves_stash(args):
    from . import saves
    return saves.stash_command(args)


def saves_apply(args):
    from . import saves
    return saves.apply_command(args)


def saves_manage(args):
    from . import saves_manage
    return saves_manage.manage_command(args)


def unmount_cmd(args):
    from . import unmount
    return unmount.run(args)


def mount_cmd(args):
    from . import mount
    return mount.run(args)


def flash_cmd(args):
    from . import flash
    return flash.run(args)


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
    words["themes"] = ["update", "pick", "build", "publish", "palettes"]
    words["download"] = ["pico8"]
    words["cards"] = ["edit", "list", "new", "set", "rename", "convert", "install", "clean", "delete", "copy", "export", "import"]
    words["saves"] = ["stash", "apply", "manage"]
    words["config"] = ["show", "path", "set", "unset", "import", "apply"]
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
    settings = " ".join(CONFIG_KINDS)
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
  if [ "$COMP_CWORD" -eq 3 ] && [ "$cmd" = config ]; then
    case "${{COMP_WORDS[2]}}" in set|unset) COMPREPLY=($(compgen -W "{settings}" -- "$cur")); return;; esac
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
        lines.append(f'complete -c sync-roms -f -n "__fish_seen_subcommand_from config; and __fish_seen_subcommand_from set unset" -a "{settings}"')
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

def _positive_int(text):
    try:
        n = int(text)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number")
    return n


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
    for action, fn in (("build", themes_build), ("publish", themes_publish)):
        p = tsub.add_parser(action, allow_abbrev=False); common(p, card=False); p.add_argument("names", nargs="*")
        group = p.add_mutually_exclusive_group()
        group.add_argument("--palette", action="append", metavar="NAME"); group.add_argument("--all-palettes", action="store_true")
        if action == "build":
            p.add_argument("--out", metavar="DIR")
        p.set_defaults(fn=fn)
    p = tsub.add_parser("palettes", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=themes_palettes)
    p = tsub.add_parser("pick", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=themes_pick)

    download = sub.add_parser("download", add_help=False, allow_abbrev=False)
    dsub = download.add_subparsers(dest="action", required=True)
    p = dsub.add_parser("pico8", allow_abbrev=False); common(p, card=False)
    p.add_argument("--count", type=_positive_int, metavar="N"); p.set_defaults(fn=download_pico8)

    p = sub.add_parser("flash", add_help=False, allow_abbrev=False); common(p, card=False); p.set_defaults(fn=flash_cmd)
    p = sub.add_parser("unmount", aliases=["umount"], add_help=False, allow_abbrev=False); common(p, card=False); p.set_defaults(fn=unmount_cmd)
    p = sub.add_parser("mount", add_help=False, allow_abbrev=False); common(p, card=False); p.set_defaults(fn=mount_cmd)

    cards = sub.add_parser("cards", add_help=False, allow_abbrev=False)
    csub = cards.add_subparsers(dest="action", required=True)
    p = csub.add_parser("list", allow_abbrev=False); p.add_argument("--json", action="store_true"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cards_list)
    for name, create in (("new", True), ("set", False)):
        p = csub.add_parser(name, allow_abbrev=False); common(p, card=False); p.add_argument("name")
        p.add_argument("--device"); p.add_argument("--layout"); p.add_argument("--size", help="the card's size, e.g. 256, 512GB, 1TB"); p.set_defaults(fn=lambda a, c=create: cards_save_setup(a, c))
    p = csub.add_parser("rename", allow_abbrev=False); common(p, card=False); p.add_argument("old"); p.add_argument("new"); p.set_defaults(fn=cards_rename)
    p = csub.add_parser("convert", allow_abbrev=False); common(p, card=False); p.add_argument("card", nargs="?")
    p.add_argument("--layout", required=True); p.set_defaults(fn=cards_convert)
    p = csub.add_parser("install", allow_abbrev=False); common(p, card=False); p.add_argument("card", nargs="?"); p.set_defaults(fn=cards_install)
    p = csub.add_parser("clean", allow_abbrev=False); common(p, card=False); p.add_argument("card", nargs="?"); p.set_defaults(fn=cards_clean)
    p = csub.add_parser("delete", allow_abbrev=False); common(p, card=False); p.add_argument("name"); p.set_defaults(fn=cards_delete)
    p = csub.add_parser("copy", allow_abbrev=False); common(p, card=False); p.add_argument("src"); p.add_argument("dst"); p.set_defaults(fn=cards_copy)
    p = csub.add_parser("export", allow_abbrev=False); common(p, card=False); p.add_argument("file"); p.set_defaults(fn=cards_export)
    p = csub.add_parser("import", allow_abbrev=False); common(p, card=False); p.add_argument("file"); p.set_defaults(fn=cards_import)

    saves = sub.add_parser("saves", add_help=False, allow_abbrev=False)
    svsub = saves.add_subparsers(dest="action", required=True)
    for name, fn in (("stash", saves_stash), ("apply", saves_apply)):
        p = svsub.add_parser(name, allow_abbrev=False); common(p, card=False); p.add_argument("card", nargs="?")
        p.add_argument("--retroarch", metavar="DIR"); p.set_defaults(fn=fn)
    p = svsub.add_parser("manage", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=saves_manage)

    p = sub.add_parser("layouts", allow_abbrev=False); common(p, card=False); p.add_argument("layout_id", nargs="?"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=layouts_cmd)
    p = sub.add_parser("config", allow_abbrev=False); common(p, card=False); p.add_argument("action", choices=["show", "path", "set", "unset", "import", "apply"], nargs="?", default="show")
    p.add_argument("name", nargs="?"); p.add_argument("value", nargs="?"); p.set_defaults(fn=config_cmd)
    p = sub.add_parser("cache", allow_abbrev=False); common(p, card=False); p.add_argument("action", choices=["update"], nargs="?"); p.add_argument("--full", action="store_true"); p.set_defaults(fn=cache_cmd)
    p = sub.add_parser("doctor", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=doctor_cmd)
    p = sub.add_parser("guide", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=guide_cmd)
    p = sub.add_parser("check", allow_abbrev=False); common(p, card=False); p.add_argument("--bucket-keys", action="store_true"); p.set_defaults(fn=check_cmd)
    p = sub.add_parser("completion", allow_abbrev=False); common(p, card=False); p.add_argument("shell", choices=["bash", "zsh", "fish", "list"])
    p.add_argument("what", nargs="?"); p.set_defaults(fn=completion_cmd)
    return ap


def run(argv):
    if argv[0] == "cards" and (len(argv) == 1 or argv[1].startswith("-")):  # bare `cards` is `cards list`
        argv = ["cards", "list", *argv[1:]]
    ap = build_parser()
    ap.prog = f"sync-roms {argv[0]}"  # its errors (unrecognized arguments) point at the command's help
    args = ap.parse_args(argv)
    if getattr(args, "dry_run", False) and not (args.fn is config_cmd and args.action == "apply") and (args.fn in (games_list, games_export, layouts_cmd, config_cmd, cache_cmd, doctor_cmd, guide_cmd, check_cmd, completion_cmd, themes_pick, themes_build, themes_palettes)
                                            or (args.fn is games_sets and args.verb == "list")):
        name = " ".join(w for w in (args.command, getattr(args, "action", None), getattr(args, "verb", None)) if w)
        if args.fn is config_cmd and args.action in ("set", "unset"):
            ui.fail(f"--dry-run can't preview `{name}`: run it without --dry-run to change settings.json", 2)
        ui.fail(f"--dry-run has no effect on `{name}`", 2)
    ui.ASSUME_YES = getattr(args, "yes", False)
    return args.fn(args) or 0
