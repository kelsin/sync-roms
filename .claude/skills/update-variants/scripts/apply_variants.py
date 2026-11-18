"""Apply approved variant changes to every set in storage listing each game, and remember the ROMs that were judged.

Run from the repo root: uv run --frozen python .claude/skills/update-variants/scripts/apply_variants.py decisions.json

decisions.json:
  {"add": [{"game": "<set entry bucket>", "bucket": "<variant bucket>", "note": "<what it adds>", "files": [...]?}],
   "remove": [{"game": "<set entry bucket>", "bucket": "<variant bucket>"}],
   "checked": {"<storage key>": "<why it is not a variant>"}}
Every added variant's ROM and files are also recorded as checked.
"""
import json
import os
import sys

from sync_roms import runtime, s3, shared, store, usersettings

CHECKED = "variants-checked.json"  # a storage key


def main(path):
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share: change nothing rather than some sets
        sys.exit(f"The storage folder {runtime.ROOT} is missing (is the share mounted?), nothing was changed")
    with open(path) as f:
        decisions = json.load(f)
    add, remove = decisions.get("add", []), decisions.get("remove", [])
    sets = store.set_files()
    if store.sets_from_fallback():  # older than storage's, maybe: editing them would undo another machine's changes
        sys.exit("The sets were read from the local copies (storage couldn't be checked), nothing was changed")
    loaded = {game_set["id"]: game_set for game_set in store.set_files()}  # as read, before the edits below
    listed = {g.get("bucket") for game_set in sets for g in game_set["games"]}
    missing = sorted({x["game"] for x in add + remove} - listed)
    if missing:
        sys.exit("No set lists these games, nothing was changed: " + ", ".join(missing))
    touched, writes = set(), []
    for game_set in sets:
        changed = False
        for g in game_set["games"]:
            for r in remove:
                if g.get("bucket") == r["game"] and g.get("variants"):
                    kept = [v for v in g["variants"] if v["bucket"] != r["bucket"]]
                    if len(kept) != len(g["variants"]):
                        if kept:
                            g["variants"] = kept
                        else:
                            del g["variants"]
                        changed = True
            for a in add:
                if g.get("bucket") == a["game"]:
                    if all(v["bucket"] != a["bucket"] for v in g.get("variants", [])):
                        entry = {"bucket": a["bucket"], "note": a["note"], **({"files": a["files"]} if a.get("files") else {})}
                        g.setdefault("variants", []).append(entry)
                        changed = True
        if changed:
            set_id = game_set.pop("id")
            writes.append((set_id, game_set))
    try:
        changed = [set_id for set_id, _ in writes if store.set_changed(set_id, loaded[set_id])]
    except s3.ERRORS as e:
        sys.exit(f"Couldn't check the sets in storage ({e}), nothing was changed")
    if changed:
        sys.exit(f"{', '.join(changed)} changed in storage while this ran (another machine?), nothing was changed")
    for set_id, game_set in writes:  # every edit above succeeded and no set changed in storage: only now write
        store.write_set(set_id, game_set)
        touched.add(set_id)
    def change(checked):
        checked.update(decisions.get("checked", {}))
        for a in add:
            for k in [a["bucket"], *a.get("files", [])]:
                checked[k] = f"variant of {a['game']}"

    shared.update(CHECKED, json.loads, {}, change,
                  lambda c: json.dumps(c, indent=1, ensure_ascii=False, sort_keys=True))
    print(f"Sets changed: {', '.join(sorted(touched)) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
