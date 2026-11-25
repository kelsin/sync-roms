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
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share: change nothing
        sys.exit(f"The storage folder {runtime.ROOT} is missing (is the share mounted?), nothing was changed")
    with open(path) as f:
        decisions = json.load(f)
    add, remove = decisions.get("add", []), decisions.get("remove", [])
    touched, missing = tags.edit_variants(add, remove)  # one write, on a fresh copy of the file

    def change(checked):
        checked.update(decisions.get("checked", {}))
        for a in add:
            if a["game"] in missing:  # not judged against a record: offered again next time
                continue
            for k in [a["bucket"], *a.get("files", [])]:
                checked[k] = f"variant of {a['game']}"

    shared.update(CHECKED, json.loads, {}, change, scrape_plan.dump_json)
    if missing:
        print(f"No tags.json record, skipped: {', '.join(missing)}")
    print(f"Games changed: {', '.join(touched) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
