"""Tags on games: tags.json at the root of storage, one record per tagged game plus the tag definitions.

{"tags": {id: {"name", "emoji", "description"?}},
 "games": {bucket key: {"tags": [ids], "files"?: [keys], "variants"?: [{"bucket", "note", "files"?}]}},
 "declined": {bucket key: [tag ids]}}

The file is shared (see shared.py): read once per run, and every write changes a fresh copy of the storage file, so
machines editing different games merge. A record with no tags and no variants is removed. Titles are never stored
(names.title), nor the system (the part of the key before the first "/")."""
import copy
import json
import threading

from . import names, shared, store, usersettings

KEY = "tags.json"
_lock = threading.RLock()
_data = None  # the loaded file, None until loaded this run
_owner = {}  # {file key: key of the record it belongs to}
slug = store.slug


def _empty():
    return {"tags": {}, "games": {}, "declined": {}}


def _strings(value):
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else None


def _variant(v):
    if not isinstance(v, dict) or not isinstance(v.get("bucket"), str):
        return None
    out = {"bucket": v["bucket"], "note": v["note"] if isinstance(v.get("note"), str) else ""}
    if _strings(v.get("files")):
        out["files"] = _strings(v["files"])
    return out


def _tag(t):
    if not (isinstance(t, dict) and isinstance(t.get("name"), str) and isinstance(t.get("emoji"), str)
            and t["name"] and t["emoji"]):
        return None
    return {k: t[k] for k in ("name", "emoji", "description") if isinstance(t.get(k), str) and t[k]}


def _game(g):
    ids = _strings(g.get("tags")) if isinstance(g, dict) else None
    if ids is None:
        return None
    out = {"tags": sorted(set(ids))}
    if _strings(g.get("files")):
        out["files"] = _strings(g["files"])
    variants = [v for v in (_variant(v) for v in g["variants"]) if v] if isinstance(g.get("variants"), list) else []
    if variants:
        out["variants"] = variants
    return out if out["tags"] or variants else None


def _clean(data):
    """The data with anything malformed left out."""
    if not isinstance(data, dict):
        return _empty()
    tag_defs = data.get("tags") if isinstance(data.get("tags"), dict) else {}
    games = data.get("games") if isinstance(data.get("games"), dict) else {}
    declined = data.get("declined") if isinstance(data.get("declined"), dict) else {}
    out = {"tags": {i: t for i, t in ((i, _tag(t)) for i, t in tag_defs.items()) if t},
           "games": {k: g for k, g in ((k, _game(g)) for k, g in games.items()) if g},
           "declined": {}}
    for key, ids in declined.items():
        if _strings(ids):
            out["declined"][key] = sorted(set(_strings(ids)))
    return out


def parse(text):
    """The file's data; malformed parts are left out, bad JSON raises ValueError."""
    return _clean(json.loads(text))


def _lines(entries):
    return "{\n" + ",\n".join(f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(entries[k], ensure_ascii=False)}"
                              for k in sorted(entries)) + ("\n  }" if entries else "  }")


def dump(data):
    """The file's text: sorted, one tag and one game per line, a trailing newline."""
    parts = [f'  "{name}": {_lines(data[name]) if data[name] else "{}"}' for name in ("tags", "games", "declined")]
    return "{\n" + ",\n".join(parts) + "\n}\n"


def _set(data):
    global _data
    _data = data
    _owner.clear()
    for key, rec in data["games"].items():
        for f in rec.get("files", ()):
            _owner[f] = key


def load():
    """The tags data, read once per run."""
    with _lock:
        if _data is None:
            _set(shared.load(KEY, parse, _empty()))
        return _data


def reset():
    """Forget the loaded data, so the next load() checks storage again."""
    global _data
    with _lock:
        _data = None
        _owner.clear()


def all_tags():
    """{tag id: {"name", "emoji", ...}}."""
    return load()["tags"]


def record(key):
    """The game's record, None when it has none."""
    return load()["games"].get(key)


def tags_of(key):
    """The game's tag ids, sorted."""
    rec = record(key)
    return list(rec["tags"]) if rec else []


def emoji_of(key):
    """The emoji of the game's tags, joined with no separator, in tag-name order; a file of a record counts as
    its game."""
    return "".join(t["emoji"] for t in defs_of(key))


def defs_of(key):
    """The definitions ({"name", "emoji", "description"?, ...}) of the game's tags, in tag-name order; a file of a
    record counts as its game."""
    data = load()
    rec = data["games"].get(key) or data["games"].get(_owner.get(key))
    defs = [data["tags"][i] for i in (rec["tags"] if rec else ()) if i in data["tags"]]
    return sorted(defs, key=lambda t: t["name"].casefold())


def games_with(required, excluded):
    """The keys of the records (and their files) that have every required tag and none of the excluded."""
    out = set()
    for key, rec in load()["games"].items():
        have = set(rec["tags"])
        if set(required) <= have and not set(excluded) & have:
            out.add(key)
            out.update(rec.get("files", ()))
    return out


def variant_index():
    """The variants of the games, both ways: (variants, parents).

    variants is {canonical bucket key: [variant entries as in the file]}. parents is {variant bucket key:
    {"bucket", "system", "title"} of its canonical game}."""
    variants, parents = {}, {}
    for key, rec in load()["games"].items():
        for v in rec.get("variants", ()):
            variants.setdefault(key, []).append(dict(v))
            parents.setdefault(v["bucket"], {"bucket": key, "system": key.partition("/")[0], "title": names.title(key)})
    return variants, parents


def _tidy(data):
    """Drop records with no tags and no variants, and declined entries with no ids."""
    for key in [k for k, g in data["games"].items() if not g["tags"] and not g.get("variants")]:
        del data["games"][key]
    for key in [k for k, ids in data["declined"].items() if not ids]:
        del data["declined"][key]


def _write(change):
    """Apply change(data) to a fresh copy of the storage file; the cache becomes the result, which is returned."""
    def run(data):
        change(data)
        _tidy(data)

    with _lock:
        result = shared.update(KEY, parse, _empty(), run, dump)
        _set(result)
        return result


def _replace(ids, old, new):
    """ids with old swapped for new (or dropped when new is None), sorted and without duplicates."""
    return sorted({new if i == old else i for i in ids} - {None})


def owner(key):
    """The key of the record the game's tags live in: the record's for one of its files, else key."""
    load()
    return _owner.get(key, key)


def change_game_tags(key, add=(), remove=()):
    """The game gets the tags in add and loses those in remove; the others it has in storage are kept."""
    def change(data):
        rec = data["games"].get(key)
        if rec is None and not add:
            return
        rec = data["games"].setdefault(key, {"tags": []})
        rec["tags"] = sorted((set(rec["tags"]) | set(add)) - set(remove))
    return _write(change)


def add_tags(pairs):
    """One write: each game of {key: [tag ids]} gets the ids, on top of the tags it has."""
    def change(data):
        for key, ids in pairs.items():
            rec = data["games"].setdefault(key, {"tags": []})
            rec["tags"] = sorted({*rec["tags"], *ids})
    return _write(change)


def retag_games(tag_id, add=(), remove=(), files=None):
    """One write: the tag goes on the games in add (files: {key: the extra files its record gets}) and off those in
    remove."""
    def change(data):
        for key in add:
            rec = data["games"].setdefault(key, {"tags": []})
            rec["tags"] = sorted({*rec["tags"], tag_id})
            if files and files.get(key) and "files" not in rec:
                rec["files"] = list(files[key])
        for key in remove:
            if key in data["games"]:
                data["games"][key]["tags"] = _replace(data["games"][key]["tags"], tag_id, None)
    return _write(change)


def define_tag(tag_id, fields):
    """Create the tag, or update the given fields of it (a field set to None is removed)."""
    def change(data):
        tag = data["tags"].setdefault(tag_id, {})
        tag.update({k: v for k, v in fields.items() if v is not None})
        for k, v in fields.items():
            if v is None:
                tag.pop(k, None)
    return _write(change)


def _retag(data, old, new):
    for rec in data["games"].values():
        rec["tags"] = _replace(rec["tags"], old, new)
    for key, ids in data["declined"].items():
        data["declined"][key] = _replace(ids, old, new)


def _retarget_limits(old, new):
    """The surprise_tags setting and every card's surprise_tags with old swapped for new (dropped when new is None);
    written only where something changed."""
    ids = usersettings.load_settings().get("surprise_tags")
    if isinstance(ids, list) and old in ids:
        usersettings.save_setting("surprise_tags", _replace(ids, old, new) or None)
    cards = store.load_cards()
    changed = False
    for entry in cards.values():
        ids = entry.get("surprise_tags") if isinstance(entry, dict) else None
        if isinstance(ids, list) and old in ids:
            kept = _replace(ids, old, new)
            if kept:
                entry["surprise_tags"] = kept
            else:
                del entry["surprise_tags"]
            changed = True
    if changed:
        store.write_cards(cards)


def merge_tag(src_id, dst_id):
    """Move src's games and declined suggestions to dst, then delete src. Raises ValueError when storage has no
    tag dst."""
    def change(data):
        if dst_id not in data["tags"]:
            raise ValueError(f"there is no tag {dst_id} in storage any more")
        data["tags"].pop(src_id, None)
        _retag(data, src_id, dst_id)
    result = _write(change)
    _retarget_limits(src_id, dst_id)
    return result


def delete_tag(tag_id):
    def change(data):
        data["tags"].pop(tag_id, None)
        _retag(data, tag_id, None)
    result = _write(change)
    _retarget_limits(tag_id, None)
    return result


def retarget(old_key, new_key):
    """A renamed ROM: its key as a record, a file, a variant bucket and a declined entry becomes new_key."""
    swap = lambda k: new_key if k == old_key else k  # noqa: E731

    def change(data):
        games = {}
        for key, rec in data["games"].items():
            rec = copy.deepcopy(rec)
            if "files" in rec:
                rec["files"] = [swap(f) for f in rec["files"]]
            for v in rec.get("variants", ()):
                v["bucket"] = swap(v["bucket"])
                if "files" in v:
                    v["files"] = [swap(f) for f in v["files"]]
            key = swap(key)
            if key in games:  # the new key already had a record: both are kept
                have = games[key]
                have["tags"] = sorted(set(have["tags"]) | set(rec["tags"]))
                for field in ("files", "variants"):
                    if field in rec:
                        have[field] = have.get(field, []) + rec[field]
            else:
                games[key] = rec
        data["games"] = games
        for old in [k for k in data["declined"] if k == old_key]:
            data["declined"][new_key] = sorted(set(data["declined"].get(new_key, [])) | set(data["declined"].pop(old)))
    return _write(change)


def decline(pairs):
    """Remember {key: [tag ids]} as suggestions the user turned down."""
    def change(data):
        for key, ids in pairs.items():
            data["declined"][key] = sorted(set(data["declined"].get(key, [])) | set(ids))
    return _write(change)


def edit_variants(add, remove):
    """One write on a fresh copy of the file: each remove ({"game", "bucket"}) leaves the game's variants, each add
    ({"game", "bucket", "note", "files"?}) joins them unless that bucket is there. A game with no record is skipped,
    never created. Returns (the keys of the games changed, the keys skipped), both sorted."""
    changed, missing = set(), set()

    def change(data):
        changed.clear()
        missing.clear()
        for key in sorted({x["game"] for x in [*add, *remove]}):
            rec = data["games"].get(key)
            if rec is None:
                missing.add(key)
                continue
            gone = {r["bucket"] for r in remove if r["game"] == key}
            variants = [v for v in rec.get("variants", ()) if v["bucket"] not in gone]
            for a in add:
                if a["game"] == key and all(v["bucket"] != a["bucket"] for v in variants):
                    entry = {"bucket": a["bucket"], "note": a["note"]}
                    if a.get("files"):
                        entry["files"] = list(a["files"])
                    variants.append(entry)
            if variants != rec.get("variants", []):
                changed.add(key)
                if variants:
                    rec["variants"] = variants
                else:
                    rec.pop("variants", None)
    _write(change)
    return sorted(changed), sorted(missing)
