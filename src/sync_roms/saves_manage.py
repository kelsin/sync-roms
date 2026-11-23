"""Operations behind `sync-roms saves manage`: list, label, move, prune and delete stashes."""
import datetime
import json
import os
import shutil

from . import muos_saves, picker, saves, store, ui


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


KEY_HELP = [("Space/Tab", "pick the stash"), ("Enter", "list the stash's files"), ("w", "label the stash"),
            ("m", "move the picked stashes (or this one) to another system"),
            ("p", "pick all but the newest N stashes of each game"),
            ("d", "delete the picked stashes (or this one)"), ("Esc", "done")]


def _note(text):
    if not picker.queue_note(text):
        ui.warn(text)


def _label(row):
    if row["unreadable"]:
        return row["rel_dir"]
    rel = muos_saves.stash_rel(row)
    return row["game"] + (f" · {rel}" if rel else "")


def _extras(row, names):
    if row["unreadable"]:
        return [("", "dim"), ("", ""), ("", "dim"), ("", ""), (ui.human_size(row["size"]), ""), ("", "cyan"),
                ("unreadable", "red"), ("", "dim")]
    return [(names.get(row["system"], row["system"]), "dim"), (f"from {row['card']}", ""),
            (row["stashed"][:16].replace("T", " "), "dim"), (saves._counts([f["kind"] for f in row["files"]]), ""),
            (ui.human_size(row["size"]), ""), (row["core"] or "", "cyan"),
            (f"{len(row['missing'])} missing" if row["missing"] else "", "red"), (row.get("note", ""), "dim")]


def _file_rows(row):
    """(label, kind, path, mark) of each file of a stash: those stash.json lists, then the folder's others."""
    if row["unreadable"]:
        return [(n, (saves.classify(n) or (None, ""))[1], os.path.join(row["dir"], n), "") for n in row["files"]]
    out = [(saves._rel_prefix(f) + f["name"], f["kind"], os.path.join(row["dir"], f["name"]),
            "missing" if f["name"] in row["missing"] else "") for f in row["files"]]
    return out + [(n, "", os.path.join(row["dir"], n), "extra") for n in row["extra"]]


def _show_files(row):
    files = _file_rows(row)
    extras = []
    for _, kind, path, mark in files:
        try:
            st = os.stat(path)
            size, when = ui.human_size(st.st_size), datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            size = when = ""
        extras.append([(kind, "dim"), (size, ""), (when, "dim"), (mark, "red" if mark == "missing" else "dim")])
    title = row["rel_dir"] if row["unreadable"] else row["game"]
    picker.filter_list(f"💾 {title} files", [f[0] for f in files], extras=extras, hint="Esc back")


def _describe(row, names):
    if row["unreadable"]:
        return f"{row['rel_dir']} (unreadable)"
    parts = [row["game"], names.get(row["system"], row["system"]), row["stashed"][:16].replace("T", " ")]
    return " · ".join(parts + ([row["note"]] if row.get("note") else []))


@picker.one_app
def _manage(rows, systems, dry_run):
    """The stash list until Esc; (deleted, moved, labelled) counts."""
    names = {s["bucket"]: s.get("name", s["bucket"]) for s in systems}
    session = {"sel": [False] * len(rows)}
    deleted, moved, labelled = 0, 0, set()

    def on_note(i, text):
        row = rows[i]
        if row["unreadable"]:
            return "This stash can't be read, so it can't be labelled"
        try:
            set_label(row, text, dry_run=dry_run)
        except (OSError, ValueError) as e:
            return f"Couldn't label {row['game']}: {e}"
        labelled.add(id(row))
        what = f"labelled {text.strip()!r}" if text.strip() else "label removed"
        return f"{'Would be ' if dry_run else ''}{what}: {row['game']}"

    while rows:
        state = picker.filter_list(
            "🗂️ Stashed saves", [_label(r) for r in rows], multi=True, initial=[False] * len(rows), esc_asks=False,
            extras=[_extras(r, names) for r in rows], session=session, hotkeys=("enter", "m", "p", "d"),
            on_note=on_note, note_text=lambda i: rows[i].get("note", ""),
            hint="? help · Space toggle · Enter files · w label · m move · p prune · d delete · Esc done",
            key_help=KEY_HELP)
        if not isinstance(state, tuple):
            break
        key, i = state
        targets = [r for r, on in zip(rows, session["sel"]) if on] or ([rows[i]] if i is not None else [])
        if key == "enter" and i is not None:
            _show_files(rows[i])
        elif key == "m" and targets:
            current = next((n for n, s in enumerate(systems) if s["bucket"] == targets[0].get("system")), 0)
            pick = picker.filter_list("📦 Move to which system?", [s.get("name", s["bucket"]) for s in systems],
                                      cursor=current, hint="Enter move · Esc cancel")
            if pick is None:
                continue
            for r in targets:
                try:
                    old, new = r["dir"], move(r, systems[pick], systems, dry_run=dry_run)
                except ValueError as e:
                    _note(f"{_label(r)}: {e}")
                    continue
                except OSError as e:
                    ui.warn(f"Couldn't move {r['dir']}: {e}")
                    continue
                if new:
                    moved += 1
                    if dry_run:
                        print(ui.dim(f"  {old} → {new}"))
        elif key == "p":
            answer = ui.ask("✂️  Keep how many per game? [1] ").strip() or "1"
            if not answer.isdigit() or int(answer) < 1:
                _note(f"Keep how many: {answer!r} isn't a positive whole number")
                continue
            session["sel"] = prune_picks(rows, int(answer))
            _note(f"Picked {sum(session['sel'])} stash(es) to delete: press d")
        elif key == "d" and targets:
            print(ui.yellow(f"🗑️  {len(targets)} stash(es) to delete:"))
            for r in targets:
                print(ui.dim(f"  {_describe(r, names)}"))
            if not ui.ASSUME_YES and not ui.confirm(f"Delete {len(targets)} stash(es)? This can't be undone.",
                                                    default=False):
                continue
            try:
                delete(targets, dry_run=dry_run)
            except ValueError as e:
                ui.warn(str(e))
                continue
            gone = {id(r) for r in targets if dry_run or not os.path.exists(r["dir"])}
            if dry_run:
                for r in targets:
                    print(ui.dim(f"  would delete {r['dir']}"))
            deleted += len(gone)
            kept = [n for n, r in enumerate(rows) if id(r) not in gone]
            if session.get("row") is not None:
                session["row"] = min(sum(1 for n in kept if n < session["row"]), max(len(kept) - 1, 0))
            session["sel"] = [session["sel"][n] and id(rows[n]) not in gone for n in kept]
            rows[:] = [rows[n] for n in kept]
    return deleted, moved, len(labelled)


def manage_command(args):
    """`saves manage`: list every stash to inspect, label, move to another system, prune and delete."""
    if not ui.has_terminal():
        ui.fail("`saves manage` needs a terminal to pick from", 2)
    rows = list_rows()
    if not rows:
        print(ui.yellow(f"↩️  No stashed saves in {saves.stash_root()}"))
        return 0
    deleted, moved, labelled = _manage(rows, store.load_catalog()["systems"], args.dry_run)
    if not (deleted or moved or labelled):
        print(ui.yellow("↩️  Nothing changed"))
    elif args.dry_run:
        print(ui.yellow(f"🧪 Would delete {deleted} stash(es), move {moved}, label {labelled}"))
    else:
        print(ui.green(f"🗑️  Deleted {deleted} stash(es), moved {moved}, labelled {labelled}"))
    return 0
