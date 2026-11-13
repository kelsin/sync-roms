"""Repo and personal data files: games lists, sets, cards, device overlay."""
import json
import os
import re
import shutil
import sys
import tempfile

from . import inventory, s3, ui


REPO_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


_repo_text = {}  # path -> ((mtime_ns, size), file text)


def repo_json(name):
    """A repo data file, parsed fresh on every call (callers mutate the result) from text cached until the file changes
    (json.loads of the text is faster than deep-copying a cached parse)."""
    path = os.path.join(REPO_DATA, name + ".json")
    cached = _repo_text.get(path)
    try:
        st = os.stat(path)
    except FileNotFoundError:  # an upgrade removed the install under a running sync: serve what was read
        if not cached:
            raise
        return json.loads(cached[1])
    sig = (st.st_mtime_ns, st.st_size)
    if not cached or cached[0] != sig:
        with open(path) as f:
            cached = _repo_text[path] = (sig, f.read())
    return json.loads(cached[1])


def preload_repo_data():
    """Read every repo data file now, so a long sync still has them if an upgrade removes the install mid-run."""
    for name in os.listdir(REPO_DATA):
        if name.endswith(".json"):
            repo_json(name[:-5])


def key_title(key):
    """A bucket key's file name without the system folder or extension."""
    return os.path.splitext(key.split("/", 1)[-1])[0]


def folder_keys(bucket):
    """Bucket keys of the files in a system's storage folder."""
    return {k for k in inventory.files(bucket + "/") if not k.endswith("/")}


# The process umask can only be read by setting it, so it is read once here, while a single thread is running: a
# background writer (the size cache) doing that at the same time as another would leave the umask at 0.
_UMASK = os.umask(0)
os.umask(_UMASK)


def _keep_backup(path):
    backup(path)


def write_json(path, data, *, backup=False, mode=None, trailing_newline=False, **dump_kw):
    """Write data to path as JSON in one atomic step (temp file in the same folder, then a rename).

    backup: keep the file's contents from before this run as <name>.bak first. mode: permission bits for the file
    (default: those of the existing file, else 0o666 minus the umask). dump_kw goes to json.dump. Raises OSError on failure."""
    folder = os.path.dirname(path) or "."
    if backup:
        _keep_backup(path)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o777
        except OSError:
            mode = 0o666 & ~_UMASK
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, **dump_kw)
            if trailing_newline:
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if mode != 0o600 and sys.platform != "win32":  # mkstemp already made the file 600
            os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def device_defaults(systems=None):
    """{device id: {"systems": [...], "note": str}} resolved from device-systems.json.

    systems: the already-loaded systems list, when the caller has one.
    Tiers form one ordered chain: the first lists its "systems", each later one "add"s to everything before it. A device
    names its tier (and may override the tier's note). Systems come out in systems.json order.
    """
    data = repo_json("device-systems")
    order = {s["bucket"]: i for i, s in enumerate(systems if systems is not None else repo_json("systems"))}
    tiers, have = {}, set()
    for t in data["tiers"]:
        have = have | set(t.get("systems", t.get("add", [])))
        tiers[t["id"]] = {"systems": sorted(have, key=order.__getitem__), "note": t["note"]}
    return {dev: {"systems": tiers[e["tier"]]["systems"], "note": e.get("note", tiers[e["tier"]]["note"])}
            for dev, e in data["devices"].items()}


def system_sort_key(system):
    """Sort key for system lists in the editors: company, then system name, case-insensitive."""
    return (system.get("company", "").lower(), system["name"].lower())


def recommended_systems(device, systems):
    """Ids of the systems to highlight for a device: those whose native ratio is the device's screen, the
    ratio-systems.json overrides for that screen, and the dual-screen list when it has a second screen, limited to what the
    device can play (its overlaid "systems", else the repo defaults). Ratios match by exact string.

    systems: the already-loaded systems list."""
    over = repo_json("ratio-systems")
    screen = device.get("screen")
    picked = set()
    if screen:
        picked |= {s["bucket"] for s in systems if s.get("ratio") == screen}
        picked |= set(over.get("ratios", {}).get(screen, []))
    if device.get("screen2"):
        picked |= set(over.get("dual_screen", []))
    can_play = device.get("systems")
    if can_play is None:
        can_play = device_defaults(systems).get(device.get("id"), {}).get("systems", [])
    return picked & set(can_play) & {s["bucket"] for s in systems}


def personal_json(name):
    path = os.path.join(data_dir(), name)
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError as e:
        ui.fail(f"{path} isn't valid JSON ({e}). Fix it, or move it aside to start fresh.")


def load_overlay():
    """The user's device-systems.json overlay ({} when there is none)."""
    path = os.path.join(data_dir(), "device-systems.json")
    return personal_json("device-systems.json") if os.path.exists(path) else {}


_backed_up = set()


def backup(path):
    """Keep the file's contents from before this run next to it as <name>.bak (local only) before it is first rewritten.
    Later writes in the same run leave the .bak alone, so it stays a recovery copy."""
    if path not in _backed_up and os.path.exists(path):
        _backed_up.add(path)
        shutil.copyfile(path, path + ".bak")


def apply_games(systems, games):
    """Attach each system's games from a games list. An entry of {"full_system": true} instead of a list
    marks a system whose every bucket file is synced."""
    for s in systems:
        entry = games.get(s["bucket"], [])
        s["games"] = [g for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []
        s["full_system"] = isinstance(entry, dict) and bool(entry.get("full_system"))
    return systems


def apply_device_overlay(devices, systems, overlay):
    """Set each device's systems/note from the repo defaults, adjusted by the user's add/remove overlay.

    overlay: {device id: {"add": [system ids], "remove": [system ids]}}. Unknown ids warn and are skipped.
    """
    defaults = device_defaults(systems)
    known = {s["bucket"] for s in systems}
    for d in devices:
        base = defaults.get(d["id"], {"systems": [], "note": ""})
        d["systems"], d["note"] = list(base["systems"]), base["note"]
    by_id = {d["id"]: d for d in devices}
    for dev_id, change in overlay.items():
        if dev_id not in by_id:
            print(f"warning: device-systems.json: unknown device {dev_id!r}, skipped", file=sys.stderr)
            continue
        if not isinstance(change, dict):
            continue
        for key in ("add", "remove"):
            for sid in change.get(key, []):
                if sid not in known:
                    print(f"warning: device-systems.json: {dev_id}: unknown system {sid!r}, skipped", file=sys.stderr)
        remove = set(change.get("remove", []))
        d = by_id[dev_id]
        d["systems"] = [x for x in d["systems"] if x not in remove]
        d["systems"] += [x for x in dict.fromkeys(change.get("add", [])) if x in known and x not in d["systems"]]


SETS_KEY = "sets"  # reserved key in a games list: ids of whole game sets to sync
_warned = set()  # warnings already printed this run, so a menu redraw doesn't repeat them


def card_games(card, cards=None):
    """The games list saved for a card in cards.json ({} when it has none). cards: cards.json already loaded."""
    entry = (load_cards() if cards is None else cards).get(card)
    games = entry.get("games") if isinstance(entry, dict) else None
    return games if isinstance(games, dict) else {}


def card_excluded(card, cards=None):
    """Games a card opted out of, {system bucket: [bucket keys]}: dropped from what its sets sync there.
    cards: cards.json already loaded."""
    entry = (load_cards() if cards is None else cards).get(card)
    excluded = entry.get("excluded") if isinstance(entry, dict) else None
    return excluded if isinstance(excluded, dict) else {}


def _game_keys(game):
    """A locked game's (system, [bucket key, then its files]), or None when it isn't a usable game entry."""
    if not isinstance(game, dict):
        return None
    system, bucket, files = game.get("system"), game.get("bucket"), game.get("files")
    if not (isinstance(system, str) and system and isinstance(bucket, str) and bucket):
        return None
    return system, [bucket] + [k for k in (files if isinstance(files, list) else ()) if isinstance(k, str) and k]


def card_locked_games(entry, collections_by_id):
    """The games a card's collections add, then its current surprises (when Surprise is on),
    {system bucket: [{"title", "bucket", "from"}]}: one entry per key of a game (its bucket key, then its files),
    the first occurrence winning within a system. Ids that don't load and malformed games are skipped."""
    from . import surprise  # surprise imports store
    ids = entry.get("collections") if isinstance(entry, dict) else None
    locked = {}

    def add(game, label):
        parsed = _game_keys(game)
        if parsed:
            seen = locked.setdefault(parsed[0], [])
            for key in parsed[1]:
                if all(g["bucket"] != key for g in seen):
                    seen.append({"title": game.get("title"), "bucket": key, "from": label})

    for cid in ids if isinstance(ids, list) else ():
        coll = collections_by_id.get(cid)
        for game in (coll or {}).get("games", []):
            add(game, f"💖 {coll['name']}")
    if isinstance(entry, dict) and surprise.enabled(entry):
        picks = entry.get("surprises")
        for game in picks if isinstance(picks, list) else ():
            add(game, surprise.LABEL)
    return {system: games for system, games in locked.items() if games}


def merge_locked(systems, locked):
    """Append locked games ({system bucket: [game]}) to the systems that list them, skipping keys already listed.
    Unknown systems are skipped; a full system's flag is left alone."""
    for s in systems:
        have = {g.get("bucket") for g in s["games"]}
        for g in locked.get(s["bucket"], ()):
            if g["bucket"] not in have:
                s["games"].append(dict(g))
                have.add(g["bucket"])


def all_card_names(cards=None):
    return sorted(load_cards() if cards is None else cards)


def list_sets(games):
    """The set ids a games list references; anything that isn't a list of strings is ignored."""
    ids = games.get(SETS_KEY, [])
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        if SETS_KEY not in _warned:
            _warned.add(SETS_KEY)
            print(f"warning: games: {SETS_KEY!r} must be a list of set ids, ignored (saving that list drops it)",
                  file=sys.stderr)
        return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []
    return ids


def set_games(game_set):
    """A set's games as {"title", "bucket", "system"} entries, with each game's extra files as entries of their own."""
    out, seen = [], set()
    for g in game_set["games"]:
        for key in [g.get("bucket")] + list(g.get("files", [])):
            if key and key not in seen:
                seen.add(key)
                title = g.get("title") if key == g.get("bucket") and g.get("title") else key_title(key)
                out.append({"title": title, "bucket": key, "system": g.get("system")})
    return out


def merge_lists(systems, lists, sets):
    """Set each system's games/full_system to the union of the games lists and the sets they reference.

    A list is {system bucket: [games] | {"full_system": true}, "sets": [set ids]}. Games go in the order
    lists come, direct games before set games, deduplicated by bucket key.
    """
    by_id = {x["id"]: x for x in sets}
    for s in systems:
        s["games"], s["full_system"] = [], False
    by_bucket = {s["bucket"]: s for s in systems}

    seen = {s["bucket"]: set() for s in systems}

    def add(s, g):
        if g.get("bucket") and g["bucket"] not in seen[s["bucket"]]:
            seen[s["bucket"]].add(g["bucket"])
            s["games"].append({k: v for k, v in g.items() if k != "system"})

    for raw in lists:
        for s in systems:
            entry = raw.get(s["bucket"])
            if isinstance(entry, dict):
                s["full_system"] = s["full_system"] or bool(entry.get("full_system"))
            elif isinstance(entry, list):
                for g in entry:
                    if isinstance(g, dict):
                        add(s, g)
    for raw in lists:
        for set_id in list_sets(raw):
            if set_id not in by_id:
                print(f"warning: games: unknown set {set_id!r}, skipped", file=sys.stderr)
                continue
            for g in set_games(by_id[set_id]):
                if g["system"] in by_bucket:
                    add(by_bucket[g["system"]], g)
    return systems


def prune_unknown_sets(sets, cards=None):
    """Drop set ids that no longer exist from every card's games, rewriting only what changes.
    cards: cards.json already loaded. Returns whether anything was rewritten."""
    cards_in = load_cards() if cards is None else cards
    known = {x["id"] for x in sets}

    def pruned(raw):
        ids = raw.get(SETS_KEY) if isinstance(raw, dict) else None
        if not isinstance(ids, list) or all(i in known for i in ids if isinstance(i, str)):
            return None
        gone = [i for i in ids if isinstance(i, str) and i not in known]
        out = {k: v for k, v in raw.items() if k != SETS_KEY}
        keep = [i for i in ids if not isinstance(i, str) or i in known]
        if keep:
            out[SETS_KEY] = keep
        return out, gone

    changed = {n: p for n in all_card_names(cards_in) if (p := pruned(card_games(n, cards_in)))}
    for n, p in changed.items():
        ui.warn(f"card {n}: removed sets that no longer exist: {', '.join(p[1])}")
    if changed:
        save_lists({n: p[0] for n, p in changed.items()})
    return bool(changed)


def load_catalog():
    """Layouts, systems and devices from the repo with the device-system overlay applied. Read-only: no seeding,
    no games, sets or cards, nothing pruned or rewritten."""
    catalog = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    apply_device_overlay(catalog["devices"], catalog["systems"], load_overlay())
    return catalog


def load_manifest(card_names=()):
    """Systems, devices and layouts from the repo, joined with the games of the named cards (their picks, set
    references and full systems, plus the games of their collections and, with Surprise on, their current
    surprises) and the device-system overlay. No cards means no games."""
    sets = load_sets()
    cards = load_cards()
    if prune_unknown_sets(sets, cards):
        cards = load_cards()
    manifest = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    lists = [card_games(n, cards) for n in card_names]
    merge_lists(manifest["systems"], lists, sets)
    if len(card_names) == 1:
        excluded = card_excluded(card_names[0], cards)
        for s in manifest["systems"]:
            skip = excluded.get(s["bucket"], ())
            s["games"] = [g for g in s["games"] if g.get("bucket") not in skip]
    from . import collections
    by_id = {c["id"]: c for c in collections.load_collections()}
    for n in card_names:
        merge_locked(manifest["systems"], card_locked_games(cards.get(n) or {}, by_id))
    apply_device_overlay(manifest["devices"], manifest["systems"], load_overlay())
    return manifest


def listed(s):
    """Bucket keys of the games a system lists, without the ignored ones."""
    from . import ignore  # imported here: ignore uses this module
    return [g["bucket"] for g in s.get("games", []) if g.get("bucket") and not ignore.is_ignored(g["bucket"])]


def synced_keys(s):
    """Bucket keys a sync brings for a system: its listed games, plus each Vita game's DLC and newest update."""
    from . import vita  # imported here: vita imports chd, which imports this module
    keys = listed(s)
    if s["bucket"] != vita.BUCKET or not keys:
        return keys
    extra = vita.extras(keys, inventory.files(vita.BUCKET + "/", sizes=False))
    return keys + [k for found in extra.values() for k in found if k not in keys]


def available_keys(s, have):
    """Bucket keys to download: every file in the folder for full systems, else the game list
    plus a Vita game's DLC and newest update.

    have: {key: size} listing of the system's storage folder.
    """
    if s.get("full_system"):
        return sorted(k for k in have if not k.endswith("/"))
    return synced_keys(s)


def list_system(s):
    """{key: size} of what a sync needs from a system's bucket folder. Reading from a folder (e.g. a network share),
    a system with a game list only stats the keys a sync needs (synced_keys) instead of walking the whole folder."""
    if not s.get("full_system") and s3.read_root():
        return inventory.stat(synced_keys(s))
    return inventory.files(s["bucket"] + "/")


def data_dir():
    """Per-user data folder for sync-roms."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "sync-roms")
    xdg = os.environ.get("XDG_DATA_HOME")
    return os.path.join(xdg, "sync-roms") if xdg else os.path.expanduser("~/.sync-roms")


def load_cards():
    """Saved {root folder name: {"device": device id or "full", "layout": layout name, "size": readable card size like "512 GB", "android_media": "always" or "never", "systems": [system ids last picked]}}."""
    try:
        with open(os.path.join(data_dir(), "cards.json")) as f:
            cards = json.load(f)
    except OSError:
        return {}
    except ValueError as e:
        if "cards" not in _warned:
            _warned.add("cards")
            ui.warn(f"cards.json isn't valid JSON ({e}); ignoring it and leaving it untouched")
        return {}
    return cards if isinstance(cards, dict) else {}


def cards_readable():
    """False when cards.json exists but can't be parsed, so it must not be overwritten."""
    path = os.path.join(data_dir(), "cards.json")
    if not os.path.exists(path):
        return True
    try:
        with open(path) as f:
            return isinstance(json.load(f), dict)
    except (OSError, ValueError):
        return False


def update_card(name, **values):
    """Merge values into a card's saved entry, keeping its other keys."""
    cards = load_cards()
    entry = cards.get(name)
    cards[name] = {**(entry if isinstance(entry, dict) else {}), **values}
    return write_cards(cards)


def write_cards(cards):
    """Write cards.json (keeping the one from before this run as cards.json.bak), unless the existing file can't be parsed."""
    path = os.path.join(data_dir(), "cards.json")
    if not cards_readable():
        ui.warn(f"Not saving: {path} isn't valid JSON and would be overwritten. Fix or move it first.")
        return False
    try:
        os.makedirs(data_dir(), exist_ok=True)
        write_json(path, cards, backup=True, indent=2, sort_keys=True)
    except OSError as e:
        print(ui.yellow(f"  ⚠️  Couldn't remember this setting: {e}"))
        return False
    return True


def delete_card(name):
    cards = load_cards()
    if name in cards:
        del cards[name]
        return write_cards(cards)
    return False


def save_card(name, device, layout):
    update_card(name, device=device["id"] if device else "full", layout=layout)


PRETTY = {"indent": 2, "ensure_ascii": False, "trailing_newline": True}  # write_json format of every hand-readable file


def set_data(game_set):
    """A set as it is written to its file: name, description (when there is one), games."""
    data = {"name": game_set["name"]}
    if game_set.get("description"):
        data["description"] = game_set["description"]
    data["games"] = game_set["games"]
    return data


def set_text(game_set):
    """A set as the text of its file, in the format the set files use."""
    return json.dumps(set_data(game_set), indent=2, ensure_ascii=False) + "\n"


def read_set_file(path, set_id):
    with open(path) as f:
        data = json.load(f)
    return {"id": set_id, "name": data.get("name", set_id),
            "description": data.get("description", ""), "games": data.get("games", [])}


def repo_set_files():
    """The repo's own sets (data/sets/*.json) as read_set_file dicts, in file-name order."""
    folder = os.path.join(REPO_DATA, "sets")
    if not os.path.isdir(folder):
        return []
    return [read_set_file(os.path.join(folder, name), name[:-5]) for name in sorted(os.listdir(folder))
            if name.endswith(".json")]


def load_sets():
    """Game sets from the repo's data/sets/*.json, sorted by name.

    Each file is {"name", "description" (optional), "games": [{"title", "system", "bucket", "files" (optional)}]}.
    "category" (optional) groups games in the set editor.
    "files" are extra bucket keys (e.g. the discs of a multi-disc game) toggled together with "bucket".
    """
    return sorted(repo_set_files(), key=lambda x: x["name"].lower())


def set_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sort_games(games):
    return sorted(games, key=lambda g: (str(g.get("bucket", "")).lower(), str(g.get("bucket", ""))))


def sorted_list(raw):
    """A games list with systems sorted ("sets" last), each system's games by bucket key and set ids alphabetical."""
    out = {}
    for key in sorted(raw, key=lambda k: (k == SETS_KEY, k)):
        entry = raw[key]
        if key == SETS_KEY and isinstance(entry, list):
            entry = sorted(entry, key=str)
        elif isinstance(entry, list) and all(isinstance(g, dict) for g in entry):
            entry = sort_games(entry)
        out[key] = entry
    return out


def dump_list(systems, sets_on):
    """A games list as saved in a card's cards.json entry."""
    out = {s["bucket"]: {"full_system": True} if s["full_system"] else s["games"]
           for s in systems if s["full_system"] or s["games"]}
    if sets_on:
        out[SETS_KEY] = list(sets_on)
    return out


def save_lists(cards):
    """Write each card's games list into its cards.json entry."""
    if not cards:
        return True
    saved = load_cards()
    for name, games in cards.items():
        entry = saved.get(name)
        saved[name] = {**(entry if isinstance(entry, dict) else {}), "games": sorted_list(games)}
    return write_cards(saved)


def save_overlay(changes):
    """Write device-systems.json: {device id: (added system ids, removed system ids)} replaces those devices' entries
    (an entry with nothing in it is dropped). The previous file is kept as .bak."""
    path = os.path.join(data_dir(), "device-systems.json")
    overlay = load_overlay()
    for dev_id, (add, remove) in changes.items():
        entry = {k: v for k, v in (("add", add), ("remove", remove)) if v}
        if entry:
            overlay[dev_id] = entry
        else:
            overlay.pop(dev_id, None)
    write_json(path, overlay, backup=True, **PRETTY)


def guess_system(systems, folder):
    """Index of the system whose bucket id (first) or frontend folder name is the folder's name, else None."""
    name = os.path.basename(os.path.normpath(folder)).lower()
    for i, s in enumerate(systems):
        if s["bucket"].lower() == name:
            return i
    for i, s in enumerate(systems):
        if name in (f.lower() for f in s["folders"].values() if f):
            return i
    return None


def system_applies(system, device, layout_name):
    """Whether a system is synced for a device (None for Full) and layout: the device runs it and the layout has a folder for it."""
    return bool(system["folders"].get(layout_name)) and (device is None or system["bucket"] in device["systems"])
