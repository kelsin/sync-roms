"""The personal list of ports still waiting for the user's game data: ports-needed.json in the data folder,
{port folder: {"title", "zip", "inst", "folder" (where in storage to put the data), "cards": [card names]}}."""
import json
import os
import re

from . import inventory, s3, store, ui

GAMEDATA = "os/portmaster/gamedata/"
_NOT_SUBFOLDERS = {"port", "ports", "game", "games", "roms"}  # "the ports folder" names no folder inside the port's


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
    if m and m.group(1).casefold() not in {folder.casefold()} | _NOT_SUBFOLDERS:
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
