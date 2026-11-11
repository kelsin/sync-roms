"""The user's collections: one file per collection in ~/.sync-roms/collections/ (never in the repo or storage)."""
import json
import os
import re

from . import frontend, store, ui

SURPRISE = "surprise"


def collections_dir():
    return os.path.join(store.data_dir(), "collections")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_collections():
    """Every readable collection as {"id", "name", "description", "games"}, sorted by name (case-insensitive)."""
    folder = collections_dir()
    found = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data["name"], str) or not isinstance(data["games"], list):
                raise ValueError("needs a text 'name' and a 'games' list")
            found.append({"id": name[:-5], "name": data["name"], "description": data.get("description", ""),
                          "games": data["games"]})
        except (OSError, ValueError, AttributeError, KeyError, TypeError) as e:
            ui.warn(f"collections/{name}: couldn't be read ({e}), skipped")
    return sorted(found, key=lambda c: c["name"].lower())


def save_collection(collection):
    """Write collection (a dict with id, name, optional description, games) to its file."""
    data = {"name": collection["name"]}
    if collection.get("description"):
        data["description"] = collection["description"]
    data["games"] = collection["games"]
    os.makedirs(collections_dir(), exist_ok=True)
    store.write_json(os.path.join(collections_dir(), collection["id"] + ".json"), data, **store.PRETTY)


def delete_collection(collection_id):
    os.remove(os.path.join(collections_dir(), collection_id + ".json"))


def collection_problem(name, existing_ids):
    """Why name can't be a new collection's name, or None."""
    sid = slug(name)
    if not sid:
        return "A collection needs a name with letters or digits."
    if frontend.safe_name(name).lower() == SURPRISE:
        return "Surprise is used by the Surprise option."
    if sid in existing_ids:
        return f"There is already a collection with the id {sid}."
    return None


def collection_games(collection):
    """The collection's games that have a bucket key."""
    return [g for g in collection.get("games", []) if g.get("bucket")]


def remove_from_cards(collection_id):
    """Drop collection_id from every card's 'collections'; returns the names of the cards that changed, sorted."""
    cards = store.load_cards()
    changed = []
    for name, card in cards.items():
        ids = card.get("collections")
        if isinstance(ids, list) and collection_id in ids:
            card["collections"] = [i for i in ids if i != collection_id]
            changed.append(name)
    if changed:
        store.write_cards(cards)
    return sorted(changed)
