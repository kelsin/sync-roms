"""Scriptable subcommands: games, cards, config, doctor, check and completion; plus helpers the sync flow uses."""
import argparse
import json
import os
import re
import shutil
import sys

from . import external, picker, runtime, s3, store, ui, usersettings


UNKNOWN_SHOWN = 8  # device ids named in an "unknown device" error
COMMANDS = {"games", "cards", "config", "doctor", "check", "completion"}


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
            print(json.dumps({**d, "system_names": [names.get(i, i) for i in d["systems"]]}, indent=2))
            return 0
        print(ui.bold(f"📟 {d['name']}") + ui.dim(f"  ({d['id']}, {d['soc']})"))
        print(f"  firmwares: {', '.join(d['firmwares'])}  (first is the default)")
        if d.get("note"):
            print(ui.dim(f"  {d['note']}"))
        for i in d["systems"]:
            print(f"  {i:<14} {names.get(i, '')}")
        return 0
    if as_json:
        print(json.dumps([{"id": d["id"], "name": d["name"], "soc": d["soc"], "systems": len(d["systems"]),
                           "firmwares": d["firmwares"]} for d in devices], indent=2))
        return 0
    rows = [(d["name"], d["soc"], str(len(d["systems"])), d["id"]) for d in devices]
    head = ("Device", "Chip", "Systems", "Id")
    widths = [max(len(r[i]) for r in rows + [head]) for i in range(4)]
    print(ui.bold(f"{head[0]:<{widths[0]}}  {head[1]:<{widths[1]}}  {head[2]:>{widths[2]}}  {head[3]}"))
    for name, soc, count, ident in rows:
        print(f"{name:<{widths[0]}}  {soc:<{widths[1]}}  {count:>{widths[2]}}  {ident}")
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


def systems_from_flag(flag, systems, available):
    """Indexes into systems for --systems: 'all' (every system that has games) or a comma list of system ids."""
    if flag == "all":
        return [i for i, s in enumerate(systems) if available(s)]
    ids = [x.strip() for x in flag.split(",") if x.strip()]
    by_id = {s["bucket"]: i for i, s in enumerate(systems)}
    unknown = [x for x in ids if x not in by_id]
    if unknown:
        ui.fail(f"Unknown or unsupported system(s) for this card: {', '.join(unknown)}. Available: {', '.join(by_id)}", 2)
    return [by_id[x] for x in ids if available(systems[by_id[x]])]


# --- Raw games lists ----------------------------------------------------------------------------------

def load_target(card):
    """(raw games list, save function) for the core list, or for a card's extras."""
    store.seed_personal_files()
    if card is None:
        return store.personal_json("games.json"), lambda raw: store.save_lists(raw, {})
    if card not in store.load_cards():
        ui.fail(f"No card named {card!r}. Cards: {', '.join(store.all_card_names()) or '(none yet)'}", 2)
    return store.card_games(card), lambda raw: store.save_lists(None, {card: raw})


def system_ids():
    return [s["bucket"] for s in store.repo_json("systems")]


def need_system(system):
    if system not in system_ids():
        ui.fail(f"Unknown system {system!r}. Known: {', '.join(system_ids())}", 2)


def glob_match(key, pattern):
    """Whether the file part of a bucket key matches a pattern where only * and ? are wildcards ([ is literal)."""
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern.lower())
    return re.fullmatch(regex, key.split("/", 1)[1].lower(), re.S) is not None


def resolve_keys(system, patterns):
    """Bucket keys for file names, SYSTEM/file keys or globs. Globs match against the bucket's listing."""
    keys, listing = [], None
    for pat in patterns:
        name = pat[len(system) + 1:] if pat.startswith(system + "/") else pat
        if not any(c in name for c in "*?"):
            keys.append(f"{system}/{name}")
            continue
        if listing is None:
            usersettings.ensure_bucket()
            listing = [k for k in s3.list_sizes(system + "/") if not k.endswith("/")]
        if f"{system}/{name}" in listing:  # a real name that happens to contain * or ?
            keys.append(f"{system}/{name}")
            continue
        hits = [k for k in listing if glob_match(k, name)]
        if not hits:
            ui.warn(f"{pat!r} matches nothing in {system}/")
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
        print(json.dumps({"full_systems": full, "sets": sets,
                          "games": [{"system": s, "bucket": k, "title": t} for s, k, t in entries]}, indent=2))
        return 0
    for system in full:
        print(f"{system}\t*\t(full system)")
    for set_id in sets:
        print(f"sets\t{set_id}\t(whole set)")
    for system, key, title in entries:
        print(f"{system}\t{key}\t{title}")
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
    save(raw)
    print(ui.green(f"💾 Saved {len(changes)} change(s)") + ui.dim(f" ({'card ' + args.card if args.card else 'core list'})"))
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
    keys = set()
    for k in args.keys:
        name = k[len(args.system) + 1:] if k.startswith(args.system + "/") else k
        key = f"{args.system}/{name}"
        if key not in listed and any(c in name for c in "*?"):
            hits = [x for x in listed if glob_match(x, name)]
            if not hits:
                ui.warn(f"{k!r} matches nothing in the list")
            keys.update(hits)
        else:
            keys.add(key)
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
        for set_id, x in known.items():
            print(f"{'✅' if set_id in on else '⬜'} {set_id}\t{x['name']}")
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


def games_export(args):
    raw, _ = load_target(args.card)
    for system, entry in raw.items():
        if isinstance(entry, dict) and entry.get("full_system"):
            print(f"{system}/*")
    for _, key, _ in game_entries(raw):
        print(key)
    return 0


def games_import(args):
    raw, save = load_target(args.card)
    try:
        lines = [l.strip() for l in (sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")) if l.strip() and not l.startswith("#")]
    except OSError as e:
        ui.fail(f"Can't read {args.file}: {e}", 2)
    changes, by_system = [], {}
    for line in lines:
        system, _, name = line.partition("/")
        if system not in system_ids() or not name:
            ui.warn(f"skipping {line!r}: expected SYSTEM/file or SYSTEM/*")
        elif name == "*":
            if not isinstance(raw.get(system), dict):
                raw[system] = {"full_system": True}
                changes.append(("+", f"{system} (full system)"))
        else:
            by_system.setdefault(system, []).append(line)
    for system, keys in by_system.items():
        changes += add_games(raw, system, keys)
    return finish(args, raw, save, changes)


# --- Cards ------------------------------------------------------------------------------------------

def cards_list(args):
    cards = store.load_cards()
    manifest = store.load_manifest()
    rows = []
    for name in sorted(cards):
        setup = picker.saved_setup(cards[name], manifest["devices"], manifest["layouts"])
        extras = sum(len(v) if isinstance(v, list) else 1 for v in store.card_games(name).values())
        rows.append({"name": name, "device": (setup[0]["id"] if setup[0] else "full") if setup else None,
                     "layout": setup[1] if setup else None, "extras": extras})
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print(f"{r['name']}\t{r['device'] or '(no device set)'}\t{r['layout'] or ''}\t{r['extras']} extra entries")
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
    manifest = store.load_manifest()
    current = picker.saved_setup(cards.get(args.name), manifest["devices"], manifest["layouts"])
    if create and not (args.device and args.layout):
        ui.fail("cards new needs --device and --layout", 2)
    device, layout = setup_from_flags(manifest, current, args.device, args.layout)
    if args.dry_run:
        print(ui.yellow(f"🧪 Would save {args.name}: {device['id'] if device else 'full'} · {layout}"))
        return 0
    if not store.update_card(args.name, device=device["id"] if device else "full", layout=layout):
        return 3
    print(ui.green(f"💾 {args.name}: {device['id'] if device else 'full'} · {layout}"))
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
        print(ui.yellow(f"🧪 Would delete card {args.name} and its extra games"))
        return 0
    if not args.yes and not ui.confirm(f"Delete card {args.name} and its extra games? (cards.json.bak keeps the old file)", default=False):
        print(ui.yellow("↩️  Kept"))
        return 0
    store.delete_card(args.name)
    print(ui.green(f"🗑️  Deleted card {args.name}"))
    return 0


# --- config, check, doctor ---------------------------------------------------------------------------

def effective_settings():
    """[(name, value, source)] for the settings sync-roms reads."""
    saved = usersettings.load_settings()
    out = []
    for name, env, default in (("bucket", "ROMS_BUCKET", None), ("endpoint", "ROMS_ENDPOINT", None),
                               ("profile", "ROMS_PROFILE", "roms-readonly"), ("write_profile", "ROMS_WRITE_PROFILE", "roms"),
                               ("mirror", None, None)):
        if env and os.environ.get(env):
            out.append((name, os.environ[env], f"env {env}"))
        elif saved.get(name):
            out.append((name, saved[name], "settings.json"))
        else:
            out.append((name, default, "default" if default else "unset"))
    return out


def config_cmd(args):
    if args.action == "path":
        print(store.data_dir())
        return 0
    print(ui.bold("⚙️  sync-roms settings") + ui.dim(f"  {store.data_dir()}"))
    for name, value, source in effective_settings():
        print(f"  {name:<14} {value if value is not None else ui.dim('(not set)'):<28} {ui.dim(source)}")
    return 0


def check_data():
    """Problems found in the user's data files, as strings."""
    problems = []
    systems = {s["bucket"] for s in store.repo_json("systems")}
    devices = {d["id"] for d in store.repo_json("devices")}
    layouts = set(store.repo_json("layouts"))
    sets = {x["id"] for x in store.load_sets()}

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
            elif not (isinstance(entry, dict) and "full_system" in entry):
                problems.append(f"{where}: {key}: must be a list of games or {{\"full_system\": true}}")

    core = load("games.json")
    if core is not None:
        check_list("games.json", core)
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
    return problems


def check_cmd(args):
    problems = check_data()
    for p in problems:
        print(ui.red(f"❌ {p}"))
    if not problems:
        print(ui.green("✅ games.json, cards.json, device-systems.json and the sets look fine"))
    return 1 if problems else 0


def doctor_cmd(args):
    bad = 0

    def line(ok, text, hint=""):
        nonlocal bad
        bad += ok is False
        print(f"{'✅' if ok else '⚠️ ' if ok is None else '❌'} {text}" + (ui.dim(f"  → {hint}") if hint and not ok else ""))

    settings = dict((n, v) for n, v, _ in effective_settings())
    line(bool(settings["bucket"]), f"bucket: {settings['bucket'] or 'not set'}", "run any sync-roms command to be asked, or set ROMS_BUCKET")
    runtime.PROFILE, runtime.WRITE_PROFILE = settings["profile"], settings["write_profile"]
    runtime.BUCKET, runtime.ENDPOINT = settings["bucket"], settings["endpoint"]
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
    for tool in ("7z", "chdman", "extract-xiso"):
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


def completion_cmd(args):
    if args.shell == "list":
        print("\n".join(completion_lists(args.what or "")))
        return 0
    from .cli import SUBCOMMANDS
    subs = " ".join(SUBCOMMANDS)
    flags = "--dry-run --yes --ask --device --layout --systems --card --no-clean --json --version --help"
    if args.shell in ("bash", "zsh"):
        script = f'''_sync_roms() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}" prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  case "$prev" in
    --card) COMPREPLY=($(compgen -W "$(sync-roms completion list cards)" -- "$cur")); return;;
    --device) COMPREPLY=($(compgen -W "$(sync-roms completion list devices)" -- "$cur")); return;;
    --layout) COMPREPLY=($(compgen -W "$(sync-roms completion list layouts)" -- "$cur")); return;;
    --systems) COMPREPLY=($(compgen -W "all $(sync-roms completion list systems)" -- "$cur")); return;;
  esac
  if [ "$COMP_CWORD" -eq 1 ]; then COMPREPLY=($(compgen -W "{subs} {flags}" -- "$cur") $(compgen -d -- "$cur"))
  elif [[ "$cur" == -* ]]; then COMPREPLY=($(compgen -W "{flags}" -- "$cur"))
  else COMPREPLY=($(compgen -f -- "$cur")); fi
}}
complete -o filenames -F _sync_roms sync-roms
'''
        print(("autoload -U +X bashcompinit && bashcompinit\n" if args.shell == "zsh" else "") + script, end="")
    else:
        print(f'''complete -c sync-roms -f -n __fish_use_subcommand -a "{subs}"
complete -c sync-roms -l card -x -a "(sync-roms completion list cards)"
complete -c sync-roms -l device -x -a "(sync-roms completion list devices)"
complete -c sync-roms -l layout -x -a "(sync-roms completion list layouts)"
complete -c sync-roms -l systems -x -a "all (sync-roms completion list systems)"
complete -c sync-roms -s n -l dry-run -d "change nothing"
complete -c sync-roms -s y -l yes -d "answer prompts with their default"
complete -c sync-roms -l json -d "machine-readable output"
complete -c sync-roms -l no-clean -d "skip the end-of-run card tidy"
complete -c sync-roms -l version''')
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

    cards = sub.add_parser("cards", add_help=False, allow_abbrev=False)
    csub = cards.add_subparsers(dest="action", required=True)
    p = csub.add_parser("list", allow_abbrev=False); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cards_list)
    for name, create in (("new", True), ("set", False)):
        p = csub.add_parser(name, allow_abbrev=False); common(p, card=False); p.add_argument("name")
        p.add_argument("--device"); p.add_argument("--layout"); p.set_defaults(fn=lambda a, c=create: cards_save_setup(a, c))
    p = csub.add_parser("rename", allow_abbrev=False); common(p, card=False); p.add_argument("old"); p.add_argument("new"); p.set_defaults(fn=cards_rename)
    p = csub.add_parser("delete", allow_abbrev=False); common(p, card=False); p.add_argument("name"); p.set_defaults(fn=cards_delete)

    p = sub.add_parser("config", allow_abbrev=False); common(p, card=False); p.add_argument("action", choices=["show", "path"], nargs="?", default="show"); p.set_defaults(fn=config_cmd)
    p = sub.add_parser("doctor", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=doctor_cmd)
    p = sub.add_parser("check", allow_abbrev=False); common(p, card=False); p.set_defaults(fn=check_cmd)
    p = sub.add_parser("completion", allow_abbrev=False); common(p, card=False); p.add_argument("shell", choices=["bash", "zsh", "fish", "list"])
    p.add_argument("what", nargs="?"); p.set_defaults(fn=completion_cmd)
    return ap


def run(argv):
    args = build_parser().parse_args(argv)
    ui.ASSUME_YES = getattr(args, "yes", False)
    return args.fn(args) or 0
