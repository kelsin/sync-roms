"""Apply approved variant changes to the games' records in storage's tags.json, and remember the ROMs that were
judged.

Run from the repo root: uv run --frozen python .claude/skills/update-variants/scripts/apply_variants.py decisions.json

decisions.json:
  {"add": [{"game": "<game record key>", "bucket": "<variant bucket>", "note": "<what it adds>", "files": [...]?}],
   "remove": [{"game": "<game record key>", "bucket": "<variant bucket>"}],
   "checked": {"<storage key>": "<why it is not a variant>"}}
Every added variant's ROM and files are also recorded as checked.
"""
import json
import os
import sys

from sync_roms import runtime, scrape_plan, shared, tags, usersettings

CHECKED = "variants-checked.json"  # a storage key


def main(path):
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share: change nothing rather than some games
        sys.exit(f"The storage folder {runtime.ROOT} is missing (is the share mounted?), nothing was changed")
    with open(path) as f:
        decisions = json.load(f)
    add, remove = decisions.get("add", []), decisions.get("remove", [])
    records = tags.load()["games"]
    missing = sorted({x["game"] for x in add + remove} - set(records))
    if missing:
        sys.exit("No tags.json game record has these games, nothing was changed: " + ", ".join(missing))
    touched = []
    for key in sorted({x["game"] for x in add + remove}):
        before = records[key].get("variants", [])
        gone = {r["bucket"] for r in remove if r["game"] == key}
        variants = [v for v in before if v["bucket"] not in gone]
        for a in add:
            if a["game"] == key and all(v["bucket"] != a["bucket"] for v in variants):
                variants.append({"bucket": a["bucket"], "note": a["note"], **({"files": a["files"]} if a.get("files") else {})})
        if variants != before:
            tags.set_variants(key, variants)  # one write per game, each on a fresh copy of the file
            touched.append(key)

    def change(checked):
        checked.update(decisions.get("checked", {}))
        for a in add:
            for k in [a["bucket"], *a.get("files", [])]:
                checked[k] = f"variant of {a['game']}"

    shared.update(CHECKED, json.loads, {}, change, scrape_plan.dump_json)
    print(f"Games changed: {', '.join(touched) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
