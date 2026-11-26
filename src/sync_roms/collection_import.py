"""`sync-roms collections import`: add collections exported from the share page to your own."""
import json
import os

from . import collections, store, ui


def read(path):
    """The collection in an exported file as {"name", "description"?, "art"?, "games"}, its games cleaned as
    `load_collections` cleans them. Raises ValueError for a file that can't be read or isn't a collection."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ValueError(f"couldn't be read ({e})") from e
    except ValueError as e:
        raise ValueError(f"isn't JSON ({e})") from e
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not isinstance(data.get("games"), list):
        raise ValueError("isn't a collection (needs a text 'name' and a 'games' list)")
    games, dropped = collections._clean_games(data["games"])
    if dropped:
        ui.warn(f"{path}: some games aren't valid (each needs a system and a bucket), skipped")
    out = {"name": data["name"]}
    for key in ("description", "art"):
        if isinstance(data.get(key), str) and data[key]:
            out[key] = data[key]
    out["games"] = games
    return out


def differences(mine, theirs):
    """(the file's games yours lacks, your games the file lacks), matched by bucket, each in its list's order."""
    have, got = {g["bucket"] for g in mine["games"]}, {g["bucket"] for g in theirs["games"]}
    return [g for g in theirs["games"] if g["bucket"] not in have], [g for g in mine["games"] if g["bucket"] not in got]


def merged(mine, theirs):
    """mine with the file's games it lacks appended; its name, description, art and notes kept."""
    games = list(mine["games"])
    have = {g["bucket"] for g in games}
    for g in differences(mine, theirs)[0]:
        if g["bucket"] not in have:
            have.add(g["bucket"])
            games.append(g)
    return {**mine, "games": games}


def _show(heading, games, short):
    if games:
        games = sorted(games, key=lambda g: (short.get(g["system"], g["system"]),
                                             store.sort_key(g.get("title") or os.path.basename(g["bucket"]))))
        print(f"{heading} ({len(games)}):")
        for g in games:
            print(f"  {short.get(g['system'], g['system'])}: {g.get('title') or os.path.basename(g['bucket'])}")


def _new_name(taken):
    """Ask for a name collection_problem accepts; None when the answer is empty."""
    while True:
        name = ui.ask("New name: ").strip()
        if not name:
            return None
        problem = collections.collection_problem(name, taken)
        if not problem:
            return name
        ui.warn(problem)


def run(paths, dry_run):
    """Import each file; returns the exit code (2 when no file could be read)."""
    existing = {c["id"]: c for c in collections.load_collections()}
    short = {s["bucket"]: store.short_name(s) for s in store.repo_json("systems")}

    def save(collection, done, would):
        if not dry_run:
            store.backup(os.path.join(collections.collections_dir(), collection["id"] + ".json"))
            collections.save_collection(collection)
        existing[collection["id"]] = collection
        print(ui.yellow(f"🧪 Would {would}") if dry_run else ui.green(done))

    read_any = False
    for path in paths:
        try:
            theirs = read(path)
        except ValueError as e:
            ui.warn(f"{path} {e}, skipped")
            continue
        read_any = True
        name, cid = theirs["name"], store.slug(theirs["name"])
        skipped = ui.yellow(f"↩️  Skipped {name}")
        problem = collections.collection_problem(name, ())
        if problem:
            ui.warn(f"{path}: {problem}")
            print(skipped)
            continue
        if cid not in existing:
            save({"id": cid, **theirs}, f"💾 Imported {name}", f"import {name}")
            continue
        mine = existing[cid]
        only_file, only_mine = differences(mine, theirs)
        if not only_file and not only_mine:
            print(f"{name}: nothing differs from yours")
            print(skipped)
            continue
        _show("Only in the file", only_file, short)
        _show("Only in yours", only_mine, short)
        if not ui.ASSUME_YES and not ui.has_terminal():
            ui.warn(f"{name} exists: pass --yes to merge, or run in a terminal to choose")
            print(skipped)
            continue
        answer = ui.choose(f"{name} exists: merge, replace, rename or skip?", "mrns", "m")
        if answer == "m" and not only_file:
            print(ui.yellow(f"↩️  Nothing to add to {mine['name']}"))
        elif answer == "m":
            save(merged(mine, theirs), f"🔀 Merged {len(only_file)} games into {mine['name']}",
                 f"merge {len(only_file)} games into {mine['name']}")
        elif answer == "r":
            save({"id": cid, **theirs}, f"💾 Replaced {name}", f"replace {name}")
        elif answer == "n" and (new := _new_name(existing)):
            save({**theirs, "id": store.slug(new), "name": new}, f"💾 Imported {new}", f"import {new}")
        else:
            print(skipped)
    return 0 if read_any else 2
