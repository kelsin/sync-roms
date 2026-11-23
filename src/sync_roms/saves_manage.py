"""Operations behind `sync-roms saves manage`: list, label, move, prune and delete stashes."""
import json
import os
import shutil

from . import muos_saves, saves, store, ui


def _real(path):
    return os.path.realpath(path)


def inside(path):
    """Whether path is somewhere under the stash folder (not the folder itself)."""
    root, p = _real(saves.stash_root()), _real(path)
    return p != root and p.startswith(root + os.sep)


def _files(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(n for n in names if os.path.isfile(os.path.join(folder, n)))


def _size(folder, names):
    total = 0
    for n in names:
        try:
            total += os.path.getsize(os.path.join(folder, n))
        except OSError:
            pass
    return total


def list_rows():
    """Every readable stash with what is missing or extra in its folder, then each unreadable stash folder."""
    rows = []
    for s in saves.load_stashes():
        listed = [f["name"] for f in s["files"]]
        present = _files(s["dir"])
        rows.append({**s, "missing": [n for n in listed if n not in present],
                     "extra": [n for n in present if n not in listed and n != "stash.json"],
                     "size": _size(s["dir"], [n for n in listed if n in present]), "unreadable": False})
    readable = {_real(r["dir"]) for r in rows}
    root = saves.stash_root()
    bad = []
    for system in sorted(_dirs(root)):
        for game in sorted(_dirs(os.path.join(root, system))):
            for stash in sorted(_dirs(os.path.join(root, system, game))):
                d = os.path.join(root, system, game, stash)
                names = _files(d)
                if names and _real(d) not in readable:
                    bad.append({"dir": d, "unreadable": True, "rel_dir": f"{system}/{game}/{stash}",
                                "files": names, "size": _size(d, names)})
    return rows + bad


def _dirs(path):
    try:
        return [n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n))]
    except OSError:
        return []


def _write(row, data):
    store.write_json(os.path.join(row["dir"], "stash.json"), data, **store.PRETTY)


def _read(row):
    with open(os.path.join(row["dir"], "stash.json"), encoding="utf-8") as f:
        return json.load(f)


def set_label(row, text, dry_run=False):
    """Store text as the stash's note; empty removes it."""
    text = text.strip()
    if not dry_run:
        data = _read(row)
        if text:
            data["note"] = text
        else:
            data.pop("note", None)
        _write(row, data)
    if text:
        row["note"] = text
    else:
        row.pop("note", None)


def _prune_empty(folder):
    """Remove the game and system folders above a stash folder when they are empty."""
    parent = os.path.dirname(folder)
    for _ in range(2):
        if not inside(parent):
            return
        try:
            os.rmdir(parent)
        except OSError:
            return
        parent = os.path.dirname(parent)


def move(row, system, catalog_systems, dry_run=False):
    """Move a stash to another system; the new folder, None when it is already there. ValueError when refused."""
    if row.get("unreadable"):
        raise ValueError("this stash can't be read, so it can't be moved")
    bucket = system["bucket"]
    if row["system"] == bucket:
        return None
    pickles = muos_saves.is_pickles(row)
    muos = system["folders"].get("muos")
    if pickles and not muos:
        raise ValueError(f"{system.get('name', bucket)} has no muOS folder, so a Pickles stash can't go there")
    if not inside(row["dir"]):
        raise ValueError("the stash is outside the stash folder")
    base = os.path.join(saves.stash_root(), bucket, row["game"], os.path.basename(row["dir"]))
    if saves._unsafe(row["game"]) or not inside(base):
        raise ValueError("the stash's game name would put it outside the stash folder")
    new, n = base, 1
    while os.path.exists(new):
        n += 1
        new = f"{base}-{n}"
    if dry_run:
        return new
    data = _read(row)
    os.makedirs(os.path.dirname(new), exist_ok=True)
    old = row["dir"]
    os.rename(old, new)
    data["system"] = bucket
    if pickles:
        for f in data["files"]:
            if "rel" in f:
                f["rel"] = "/".join([muos] + f["rel"].split("/")[1:])
    row["dir"] = new
    try:
        _write(row, data)
    except OSError:
        os.rename(new, old)
        row["dir"] = old
        _prune_empty(new)
        raise
    row["system"] = bucket
    row["files"] = data["files"]
    _prune_empty(old)
    return new


def delete(rows, dry_run=False):
    """Remove each stash folder and its empty game and system folders; how many went."""
    for r in rows:
        if not inside(r["dir"]):
            raise ValueError(f"{r['dir']} is outside the stash folder")
    done = 0
    for r in rows:
        if not dry_run:
            try:
                shutil.rmtree(r["dir"])
            except OSError as e:
                ui.warn(f"Couldn't delete {r['dir']}: {e}")
                continue
            _prune_empty(r["dir"])
        done += 1
    return done


def prune_picks(rows, keep):
    """Per row, whether it is beyond the newest `keep` readable stashes of its system, game and ROM dir."""
    picks = [False] * len(rows)
    groups = {}
    for i, r in enumerate(rows):
        if not r.get("unreadable"):
            groups.setdefault((r["system"], r["game"], muos_saves.stash_rel(r)), []).append(i)
    for idx in groups.values():
        idx.sort(key=lambda i: rows[i]["stashed"], reverse=True)
        for i in idx[keep:]:
            picks[i] = True
    return picks
