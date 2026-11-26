"""Repo and personal data files: games lists, cards, device overlay."""
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


def folder_keys(bucket, say=True):
    """Bucket keys of the files in a system's storage folder (names only: without a cache, a size is a stat per file).
    say: print that the folder is being listed when there is no storage cache to read it from."""
    if say and inventory.current() is None:
        print(ui.dim(f"📡 Listing {s3.location()}/{bucket}/ ..."))
    return {k for k in inventory.files(bucket + "/", sizes=False) if not k.endswith("/")}


# The process umask can only be read by setting it, so it is read once here, while a single thread is running: a
# background writer (the size cache) doing that at the same time as another would leave the umask at 0.
_UMASK = os.umask(0)
os.umask(_UMASK)


def _keep_backup(path):
    backup(path)


def _write_atomic(path, data, *, text, encoding, newline, mode, fsync):
    """Write data to a temp file beside path, then rename it over path; the temp file never outlives a failure."""
    folder = os.path.dirname(path) or "."
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o777
        except OSError:
            mode = 0o666 & ~_UMASK
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w" if text else "wb", **({"encoding": encoding, "newline": newline} if text else {})) as f:
            f.write(data)
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        if mode != 0o600 and sys.platform != "win32":  # mkstemp already made the file 600
            os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def write_text(path, text, *, backup=False, mode=None):
    """Write text (UTF-8) to path in one atomic step (temp file in the same folder, then a rename), synced to disk.

    backup: keep the file's contents from before this run as <name>.bak first. mode: permission bits for the file
    (default: those of the existing file, else 0o666 minus the umask). Raises OSError on failure."""
    if backup:
        _keep_backup(path)
    _write_atomic(path, text, text=True, encoding="utf-8", newline=None, mode=mode, fsync=True)


def replace_file(path, data, *, encoding="utf-8", newline=None):
    """Write data (str, or bytes) to path in one atomic step (temp file in the same folder, then a rename), so a
    stopped run never leaves a half-written file. Not synced to disk: for files on a card that is ejected afterwards.
    encoding and newline are those of open() and apply to str only. Raises OSError on failure."""
    _write_atomic(path, data, text=isinstance(data, str), encoding=encoding, newline=newline, mode=None, fsync=False)


def write_json(path, data, *, backup=False, mode=None, trailing_newline=False, **dump_kw):
    """Write data to path as JSON with write_text. dump_kw goes to json.dumps."""
    write_text(path, json.dumps(data, **dump_kw) + ("\n" if trailing_newline else ""), backup=backup, mode=mode)


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


def short_name(system):
    """The short name editors and the collections page show for a system (its full name when it has none)."""
    return system.get("short") or system["name"]


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


LEGACY_SETS = "sets"  # a games list's old whole-set references: synced no more, dropped when the list is saved
_warned = set()  # warnings already printed this run, so a menu redraw doesn't repeat them


def saved_card(card, cards=None):
    """A card's entry in cards.json (in cards, when already loaded; not a copy), or {} when it has none or a malformed one."""
    entry = (load_cards() if cards is None else cards).get(card)
    return entry if isinstance(entry, dict) else {}


def card_games(card, cards=None):
    """The games list saved for a card in cards.json ({} when it has none). cards: cards.json already loaded."""
    games = saved_card(card, cards).get("games")
    return games if isinstance(games, dict) else {}


def card_excluded(card, cards=None):
    """Games a card opted out of, {system bucket: [bucket keys]}: dropped from what its collections sync there.
    cards: cards.json already loaded."""
    excluded = saved_card(card, cards).get("excluded")
    return excluded if isinstance(excluded, dict) else {}


def systems_off(entry):
    """The set of system ids nothing syncs for on a card, from its cards.json entry's `systems_off`."""
    ids = entry.get("systems_off") if isinstance(entry, dict) else None
    return {i for i in ids if isinstance(i, str)} if isinstance(ids, list) else set()


def _game_keys(game):
    """A locked game's (system, [bucket key, then its files]), or None when it isn't a usable game entry."""
    if not isinstance(game, dict):
        return None
    system, bucket, files = game.get("system"), game.get("bucket"), game.get("files")
    if not (isinstance(system, str) and system and isinstance(bucket, str) and bucket):
        return None
    return system, [bucket] + [k for k in (files if isinstance(files, list) else ()) if isinstance(k, str) and k]


def card_locked_games(entry, collections_by_id, excluded=None):
    """The games a card's collections add, then its current surprises (when Surprise is on),
    {system bucket: [{"title", "bucket", "from"}]}: one entry per key of a game (its bucket key, then its files),
    the first occurrence winning within a system. Ids that don't load and malformed games are skipped.
    excluded: {system bucket: [keys]} whose keys a collection's games leave out (surprises are never left out)."""
    from . import surprise  # surprise imports store
    ids = entry.get("collections") if isinstance(entry, dict) else None
    locked = {}

    def add(game, label, skip=()):
        parsed = _game_keys(game)
        if parsed:
            seen = locked.setdefault(parsed[0], [])
            for key in parsed[1]:
                if key not in skip and all(g["bucket"] != key for g in seen):
                    seen.append({"title": game.get("title"), "bucket": key, "from": label})

    from . import themeart  # here: themeart imports store
    for cid in ids if isinstance(ids, list) else ():
        coll = collections_by_id.get(cid)
        for game in (coll or {}).get("games", []):
            parsed = _game_keys(game)
            skip = (excluded or {}).get(parsed[0]) if parsed else None
            add(game, f"{themeart.collection_emoji(coll)} {coll['name']}", skip if isinstance(skip, list) else ())
    from . import guest  # here: guest imports store
    if isinstance(entry, dict) and surprise.enabled(entry) and not guest.is_guest(entry):
        picks = entry.get("surprises")
        for game in picks if isinstance(picks, list) else ():
            add(game, surprise.LABEL)
    return {system: games for system, games in locked.items() if games}


def card_flag(entry, field):
    """A card's on/off setting (`theme`, `custom_collections`, `raofflineproxy`): its bool in cards.json, on when absent."""
    on = entry.get(field) if isinstance(entry, dict) else None
    return on if isinstance(on, bool) else True


def set_card_flag(entry, field, on):
    """Save a card's on/off setting: on is the default, so it is the field's absence; off is stored as False."""
    entry.pop(field, None)
    if not on:
        entry[field] = False


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


def merge_lists(systems, lists):
    """Set each system's games/full_system to the union of the games lists.

    A list is {system bucket: [games] | {"full_system": true}}. Games go in the order lists come, deduplicated by
    bucket key.
    """
    for s in systems:
        s["games"], s["full_system"] = [], False

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
    return systems


def load_catalog():
    """Layouts, systems and devices from the repo with the device-system overlay applied. Read-only: no seeding,
    no games or cards, nothing pruned or rewritten."""
    catalog = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    apply_device_overlay(catalog["devices"], catalog["systems"], load_overlay())
    return catalog


def load_manifest(card_names=(), keep_off=False):
    """Systems, devices and layouts from the repo, joined with the games of the named cards (their picks and full
    systems, plus the games of their collections and, with Surprise on, their current surprises) and the
    device-system overlay. No cards means no games. A one-card manifest empties the card's systems_off, unless
    keep_off."""
    cards = load_cards()
    manifest = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    lists = [card_games(n, cards) for n in card_names]
    merge_lists(manifest["systems"], lists)
    if len(card_names) == 1:
        excluded = card_excluded(card_names[0], cards)
        for s in manifest["systems"]:
            skip = excluded.get(s["bucket"], ())
            s["games"] = [g for g in s["games"] if g.get("bucket") not in skip]
    from . import collections
    by_id = {c["id"]: c for c in collections.load_collections()}
    one = card_names[0] if len(card_names) == 1 else None
    for n in card_names:
        merge_locked(manifest["systems"], card_locked_games(cards.get(n) or {}, by_id,
                                                            card_excluded(n, cards) if n == one else None))
    if one and not keep_off:
        off = systems_off(cards.get(one))
        for s in manifest["systems"]:
            if s["bucket"] in off:
                s["games"], s["full_system"] = [], False
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


def cache_dir():
    """Per-user folder for caches that can be rebuilt from storage."""
    return os.path.join(data_dir(), "cache")


def load_cards():
    """Saved {root folder name: {"device": device id or "full", "layout": layout name, "size": readable card size like "512 GB", "systems": [system ids last picked]}}."""
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
    """Merge values into a card's saved entry, keeping its other keys. A layout that differs from the saved one drops
    the card's pico8: the zip was put where the old layout's installer looks, so the next sync puts it on the card again."""
    cards = load_cards()
    entry = cards.get(name)
    entry = dict(entry) if isinstance(entry, dict) else {}
    if entry.get("layout") and values.get("layout", entry["layout"]) != entry["layout"]:
        entry.pop("pico8", None)
    cards[name] = {**entry, **values}
    return write_cards(cards)


def drop_card_field(name, field):
    """Take field out of a card's saved entry (absent, not empty)."""
    cards = load_cards()
    if isinstance(cards.get(name), dict) and field in cards[name]:
        cards[name] = {k: v for k, v in cards[name].items() if k != field}
        return write_cards(cards)
    return True


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


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sort_key(name):
    """name as it sorts: case, a leading "The", "A" or "An" (or a trailing ", The") and then its tags ("(USA)",
    "[!]") left out, so "Lost Vikings 2 (USA)" follows "The Lost Vikings (USA)"."""
    full = re.sub(r"^(the|an?)\s+(?=\S)", "", name.casefold())
    base = re.sub(r"\s*[(\[].*", "", full)
    return re.sub(r",\s*(the|an?)$", "", base), full


def sort_games(games):
    return sorted(games, key=lambda g: (str(g.get("bucket", "")).lower(), str(g.get("bucket", ""))))


def sorted_list(raw):
    """A games list with systems sorted, each system's games by bucket key, without old set references."""
    out = {}
    for key in sorted(k for k in raw if k != LEGACY_SETS):
        entry = raw[key]
        if isinstance(entry, list) and all(isinstance(g, dict) for g in entry):
            entry = sort_games(entry)
        out[key] = entry
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


def folder_tag(folder):
    """The uppercase tag in a folder's trailing "(...)" ("Game Boy Advance (GBA)" -> "GBA"), else None."""
    m = re.search(r"\(([A-Z0-9]+)\)$", folder or "")
    return m.group(1) if m else None


def system_applies(system, device, layout_name):
    """Whether a system is synced for a device (None for Full) and layout: the device runs it and the layout has a folder for it."""
    from . import portmaster
    if not system["folders"].get(layout_name):
        return False
    if system["bucket"] == portmaster.PORTS:  # only PortMaster devices, whatever their tier lists
        return portmaster.enabled(device, layout_name)
    return device is None or system["bucket"] in device["systems"]
