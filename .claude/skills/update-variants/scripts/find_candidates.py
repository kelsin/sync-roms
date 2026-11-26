"""Print, as JSON, the storage ROMs that may be variants of tagged games, and variants whose ROM left storage.

Run from the repo root: uv run --frozen python .claude/skills/update-variants/scripts/find_candidates.py [--baseline]
--baseline marks every ROM that is no record's file or variant as checked, without judging it, so later runs only see new
uploads.
Reads storage only through the storage cache (sync-roms cache update refreshes it).
"""
import json
import os
import re
import sys
from collections import defaultdict

from sync_roms import inventory, m3u, names, scrape_plan, shared, store, tags, usersettings, vita

CHECKED = "variants-checked.json"  # a storage key
REISSUE = re.compile(r"^(classic nes series|famicom mini \d*|nes classics|sega ages( \d+)?)\s*[-:]\s*", re.I)


def norm(title):
    """A title reduced for matching: no region/revision tags, re-release prefixes, articles or punctuation."""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", title)
    t = REISSUE.sub("", t.strip()).lower().replace("&", "and")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in ("the", "a"))


def clone_parent(key):
    """An arcade set's family (system:parent), or None off MAME/FBNeo."""
    system, _, rest = key.partition("/")
    stem = os.path.splitext(rest)[0]
    return f"{system}:{stem}" if system in names.SYSTEMS else None


def main():
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if inventory.current() is None:
        sys.exit("No storage cache for the storage in use: run `sync-roms cache update` first.")
    checked = shared.load(CHECKED, json.loads, {})
    stored = set()
    for s in store.repo_json("systems"):
        stored.update(store.folder_keys(s["bucket"], say=False))
    found = find(tags.load()["games"], stored, checked, baseline="--baseline" in sys.argv[1:])
    if found is None:
        return
    json.dump(found, sys.stdout, indent=1, ensure_ascii=False)
    print()


def find(records, stored, checked, baseline=False):
    """The output dict from tags.json's game records, the storage keys and the checked ROMs (None after a
    baseline, which marks the new ROMs as checked).

    A ROM that is a record's own key is tagged on its own, yet still a candidate variant of another, related game
    (a remaster or translation carries its own tags); it is never offered for its own game, for that game's files or
    for a ROM already listed as that game's variant. Files of any record and variants are never candidates themselves."""
    games, listed = {}, set()  # listed: files of a record and variants, never candidates
    for key, rec in records.items():
        listed.update(rec.get("files", []))
        games[key] = {"game": key, "title": names.title(key), "system": key.partition("/")[0],
                      "tags": rec["tags"], "variants": rec.get("variants", [])}
        for v in rec.get("variants", []):
            listed.update([v["bucket"], *v.get("files", [])])

    by_title, by_family = defaultdict(list), defaultdict(list)
    for key, info in games.items():
        by_title[norm(info["title"])].append(key)
        if clone_parent(key):
            by_family[clone_parent(key)].append(key)

    unlisted = sorted(k for k in stored - listed if not vita.is_extra(k))
    groups = m3u.file_groups(unlisted)
    # a multi-disc game is checked once any of its files is: a judged one's discs would otherwise come back
    new = [k for k in unlisted if not any(g in checked for g in groups.get(k, [k]))]
    if baseline:
        shared.update(CHECKED, json.loads, {}, lambda c: c.update(
            {k: "baseline: in storage before variants were tracked" for k in new}), scrape_plan.dump_json)
        print(f"Marked {len(new)} unlisted ROM(s) as checked in storage's {CHECKED}")
        return None
    matches, unmatched, seen = defaultdict(list), 0, set()
    for key in new:
        if key in seen:
            continue
        group = groups.get(key, [key])
        seen.update(group)
        bucket = group[0]
        title = names.title(bucket)
        found = set(by_title.get(norm(title), [])) | set(by_family.get(clone_parent(bucket), []))
        found -= set(group)  # a tagged ROM is not a variant of itself
        found = {g for g in found if bucket not in {v["bucket"] for v in games[g]["variants"]}}
        if not found and not any(k in games for k in group):
            unmatched += 1
        for game in found:
            matches[game].append({"bucket": bucket, "title": title, **({"files": group[1:]} if len(group) > 1 else {})})

    stale = [{"game": key, "bucket": v["bucket"]} for key, info in games.items() for v in info["variants"]
             if v["bucket"] not in stored]
    return {"matches": [{**games[k], "candidates": c} for k, c in sorted(matches.items())],
            "stale": stale, "unmatched": unmatched, "checked_file": CHECKED}


if __name__ == "__main__":
    main()
