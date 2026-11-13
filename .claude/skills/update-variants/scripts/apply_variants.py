"""Apply approved variant changes to every set listing each game, and remember the ROMs that were judged.

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

from sync_roms import store

SETS = os.path.join(store.REPO_DATA, "sets")
CHECKED = os.path.join(store.data_dir(), "variants-checked.json")


def main(path):
    with open(path) as f:
        decisions = json.load(f)
    add, remove = decisions.get("add", []), decisions.get("remove", [])
    sets = store.repo_set_files()
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
            writes.append((set_id, store.set_text(game_set)))
    for set_id, text in writes:  # every edit above succeeded: only now write
        with open(os.path.join(SETS, f"{set_id}.json"), "w") as f:
            f.write(text)
        touched.add(set_id)
    try:
        with open(CHECKED) as f:
            checked = json.load(f)
    except FileNotFoundError:
        checked = {}
    checked.update(decisions.get("checked", {}))
    for a in add:
        for k in [a["bucket"], *a.get("files", [])]:
            checked[k] = f"variant of {a['game']}"
    with open(CHECKED, "w") as f:
        json.dump(checked, f, indent=1, ensure_ascii=False, sort_keys=True)
    print(f"Sets changed: {', '.join(sorted(touched)) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
