"""Repo and personal data files: games lists, sets, cards, device overlay."""
import json
import os
import shutil
import sys

from . import ui


REPO_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERSONAL_FILES = ("games.json",)  # per-user, in data_dir(); never read from the bucket


def repo_json(name):
    with open(os.path.join(REPO_DATA, name + ".json")) as f:
        return json.load(f)


def personal_json(name):
    path = os.path.join(data_dir(), name)
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError as e:
        ui.fail(f"{path} isn't valid JSON ({e}). Fix it, or move it aside to start fresh.")


def backup(path):
    """Keep the file's previous contents next to it as <name>.bak (local only) before it is rewritten."""
    if os.path.exists(path):
        shutil.copyfile(path, path + ".bak")


def seed_personal_files():
    """Give the user their own copy of each personal file, starting from the repo's version."""
    os.makedirs(data_dir(), exist_ok=True)
    for name in PERSONAL_FILES:
        dest = os.path.join(data_dir(), name)
        if not os.path.exists(dest):
            shutil.copyfile(os.path.join(REPO_DATA, name), dest)


def apply_games(systems, games):
    """Attach each system's games from games.json. An entry of {"full_system": true} instead of a list
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
    defaults = repo_json("device-systems")
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


def card_games(card):
    """The extra games list saved for a card in cards.json ({} when it has none)."""
    entry = load_cards().get(card)
    games = entry.get("games") if isinstance(entry, dict) else None
    return games if isinstance(games, dict) else {}


def all_card_names():
    return sorted(load_cards())


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
                title = g.get("title") if key == g.get("bucket") and g.get("title") \
                    else os.path.splitext(key.split("/", 1)[-1])[0]
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

    def add(s, g):
        if g.get("bucket") and not any(x.get("bucket") == g["bucket"] for x in s["games"]):
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


def load_manifest(card_names=()):
    """Systems, devices and layouts from the repo, joined with the personal games (plus the extras of the
    named cards) and device-system overlay."""
    seed_personal_files()
    manifest = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    lists = [personal_json("games.json")] + [card_games(n) for n in card_names]
    merge_lists(manifest["systems"], lists, load_sets())
    overlay_path = os.path.join(data_dir(), "device-systems.json")
    overlay = personal_json("device-systems.json") if os.path.exists(overlay_path) else {}
    apply_device_overlay(manifest["devices"], manifest["systems"], overlay)
    return manifest


def listed(s):
    """Bucket keys of the games games.json lists for a system."""
    return [g["bucket"] for g in s.get("games", []) if g.get("bucket")]


def available_keys(s, have):
    """Bucket keys to download: every file in the folder for full systems, else the game list.

    have: {key: size} listing of the system's bucket folder.
    """
    if s.get("full_system"):
        return sorted(k for k in have if not k.endswith("/"))
    return listed(s)


def data_dir():
    """Per-user data folder for this script."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "sync-roms")
    xdg = os.environ.get("XDG_DATA_HOME")
    return os.path.join(xdg, "sync-roms") if xdg else os.path.expanduser("~/.sync-roms")


def load_cards():
    """Saved {root folder name: {"device": device id or "full", "layout": layout name, "android_media": "always" or "never", "systems": [system ids last picked]}}."""
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
    """Write cards.json (keeping the old one as cards.json.bak), unless the existing file can't be parsed."""
    path = os.path.join(data_dir(), "cards.json")
    if not cards_readable():
        ui.warn(f"Not saving: {path} isn't valid JSON and would be overwritten. Fix or move it first.")
        return False
    try:
        os.makedirs(data_dir(), exist_ok=True)
        backup(path)
        with open(path + ".tmp", "w") as f:
            json.dump(cards, f, indent=2, sort_keys=True)
        os.replace(path + ".tmp", path)
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


def load_sets():
    """Game sets from the repo's data/sets/*.json, sorted by name.

    Each file is {"name", "description" (optional), "games": [{"title", "system", "bucket", "files" (optional)}]}.
    "files" are extra bucket keys (e.g. the discs of a multi-disc game) toggled together with "bucket".
    """
    folder = os.path.join(REPO_DATA, "sets")
    sets = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith(".json"):
            with open(os.path.join(folder, name)) as f:
                data = json.load(f)
            sets.append({"id": name[:-5], "name": data.get("name", name[:-5]),
                         "description": data.get("description", ""), "games": data.get("games", [])})
    return sorted(sets, key=lambda x: x["name"].lower())


def dump_list(systems, sets_on):
    """A games list as saved to games.json or a card's cards.json entry."""
    out = {s["bucket"]: {"full_system": True} if s["full_system"] else s["games"]
           for s in systems if s["full_system"] or s["games"]}
    if sets_on:
        out[SETS_KEY] = list(sets_on)
    return out


def save_lists(core, cards):
    """Write the core list (when given) to games.json and each card's list into its cards.json entry."""
    if core is not None:
        path = os.path.join(data_dir(), "games.json")
        backup(path)
        with open(path + ".tmp", "w") as f:
            json.dump(core, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(path + ".tmp", path)
    ok = True
    for name, games in cards.items():
        ok = update_card(name, games=games) and ok
    return ok


def save_overlay(changes):
    """Write device-systems.json: {device id: (added system ids, removed system ids)} replaces those devices' entries
    (an entry with nothing in it is dropped). The previous file is kept as .bak."""
    path = os.path.join(data_dir(), "device-systems.json")
    overlay = personal_json("device-systems.json") if os.path.exists(path) else {}
    for dev_id, (add, remove) in changes.items():
        entry = {k: v for k, v in (("add", add), ("remove", remove)) if v}
        if entry:
            overlay[dev_id] = entry
        else:
            overlay.pop(dev_id, None)
    backup(path)
    with open(path + ".tmp", "w") as f:
        json.dump(overlay, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)


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
