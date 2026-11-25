"""The personal list of ports still waiting for the user's game data: ports-needed.json in the data folder,
{port folder: {"title", "zip", "inst", "folder" (where in storage to put the data), "cards": [card names]}}."""
import json
import os
import re

from . import inventory, s3, store, ui

GAMEDATA = "os/portmaster/gamedata/"
_DATA_FOLDERS = {"assets", "gamedata", "data", "content"}  # the words "the X folder" names a data folder by


def path():
    return os.path.join(store.data_dir(), "ports-needed.json")


def load():
    """The entries ({} when the file is missing or isn't a JSON object, warned about)."""
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        ui.warn(f"Couldn't read {path()}: {e}")
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def save(entries):
    os.makedirs(store.data_dir(), exist_ok=True)
    store.write_json(path(), entries, **store.PRETTY)


def subfolder(folder, inst):
    """The folder inside the port's folder that its instructions name (`ports/undertale/assets`, `"celeste/gamedata"`,
    `the assets folder`), or ""."""
    inst = inst or ""
    m = re.search(rf"(?<![\w-]){re.escape(folder)}/([\w-]+)", inst, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\bthe ([\w-]+) folder\b", inst, re.IGNORECASE)
    if m and m.group(1).casefold() in _DATA_FOLDERS:
        return m.group(1)
    return ""


def add(entries, folder, title, zip_name, inst, card):
    """Add or refresh the port's entry and add card to its cards."""
    sub = subfolder(folder, inst)
    old = entries.get(folder) or {}
    cards = sorted({c for c in old.get("cards") or [] if isinstance(c, str)} | {card})
    entries[folder] = {"title": title, "zip": zip_name, "inst": inst or "",
                       "folder": f"{GAMEDATA}{folder}/" + (f"{sub}/" if sub else ""), "cards": cards}


def remove_card(entries, folder, card):
    """Take card out of the port's entry; the entry goes when no cards are left."""
    entry = entries.get(folder)
    if entry is None:
        return
    entry["cards"] = [c for c in entry.get("cards") or [] if c != card]
    if not entry["cards"]:
        del entries[folder]


def prune(entries):
    """Drop the entries whose game data storage now has; their titles. Nothing is dropped when storage can't be read."""
    try:
        s3.check_root()
        have = [f for f in entries if inventory.files(f"{GAMEDATA}{f}/")]
    except s3.ERRORS as e:
        ui.warn(f"Couldn't check storage for the ports' game data: {e}")
        return []
    return [entries.pop(f).get("title") or f for f in have]


def block(entry, folder):
    """The port's title, its instructions and where to put its game data in storage."""
    lines = [entry.get("title") or folder]
    lines += ["    " + line for line in (entry.get("inst") or "").splitlines()]
    lines.append(f"    Put the files in {s3.location().rstrip('/')}/{entry.get('folder') or f'{GAMEDATA}{folder}/'}")
    return "\n".join(lines)


def _folder_of_port(port, metadata):
    """The port folder PORT names: a zip (with or without .zip) mapped through the metadata's portmaster folder, else
    its stem; any other word is the folder itself."""
    name = port[:-4] if port.lower().endswith(".zip") else port
    for zip_name, entry in metadata.items():
        if isinstance(entry, dict) and zip_name.casefold() in (name.casefold() + ".zip", port.casefold()):
            facts = entry.get("portmaster")
            folder = facts.get("folder") if isinstance(facts, dict) else None
            return folder if isinstance(folder, str) and folder else name
    return name


def done_command(card, ports, undo):
    """Record that the card already has the ports' game data (portmaster_data), or with undo that it doesn't."""
    from . import scrape_plan  # it imports portmaster, which imports this module
    if card not in store.load_cards():
        ui.fail(f"No card named {card!r}. Cards: {', '.join(store.all_card_names()) or '(none yet)'}", 2)
    try:
        metadata = scrape_plan.load_metadata("ports")
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't read the ports' titles from storage ({e}); naming the ports by their folders")
        metadata = {}
    folders = list(dict.fromkeys(_folder_of_port(p, metadata) for p in ports))
    have = [n for n in store.saved_card(card).get("portmaster_data") or [] if isinstance(n, str)]
    names = {f.casefold() for f in folders}
    if undo:
        have = [n for n in have if n.casefold() not in names]
    else:
        have = sorted(set(have) | {f for f in folders if f.casefold() not in {n.casefold() for n in have}})
    if have:
        store.update_card(card, portmaster_data=sorted(have))
    else:
        store.drop_card_field(card, "portmaster_data")
    if not undo:
        entries = load()
        for key in [k for k in entries if k.casefold() in names]:
            remove_card(entries, key, card)
        if entries or os.path.exists(path()):
            save(entries)
    print(f"{'Forgot' if undo else 'Marked'} the game data of {', '.join(folders)} {'on' if not undo else 'for'} {card}")
    return 0


def needed_command():
    """Print every port waiting for game data, with the cards that want it."""
    entries = load()
    gone = prune(entries)
    if gone:
        print(ui.green(f"Game data now in storage: {', '.join(gone)}"))
        save(entries)
    if not entries:
        print("No ports are waiting for game data")
        return 0
    for folder, entry in sorted(entries.items(), key=lambda kv: (kv[1].get("title") or kv[0]).casefold()):
        print(block(entry, folder))
        print(f"    Cards: {', '.join(c for c in entry.get('cards') or [] if isinstance(c, str))}")
    return 0
