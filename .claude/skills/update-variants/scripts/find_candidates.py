"""Print, as JSON, the storage ROMs that may be variants of set games, and set variants whose ROM left storage.

Run from the repo root: uv run --frozen python .claude/skills/update-variants/scripts/find_candidates.py [--baseline]
--baseline marks every ROM no set lists as checked, without judging it, so later runs only see new uploads.
Reads storage only through the storage cache (sync-roms cache update refreshes it).
"""
import json
import os
import re
import sys
from collections import defaultdict
from functools import cache

from sync_roms import inventory, m3u, names, store, usersettings, vita

CHECKED = os.path.join(store.data_dir(), "variants-checked.json")
REISSUE = re.compile(r"^(classic nes series|famicom mini \d*|nes classics|sega ages( \d+)?)\s*[-:]\s*", re.I)


def norm(title):
    """A title reduced for matching: no region/revision tags, re-release prefixes, articles or punctuation."""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", title)
    t = REISSUE.sub("", t.strip()).lower().replace("&", "and")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(w for w in t.split() if w not in ("the", "a"))


@cache
def clones(system):
    return store.repo_json("clones").get(system, {}).get("clones", {})


def clone_parent(key):
    """An arcade set's family (system:parent), or None off MAME/FBNeo."""
    system, _, rest = key.partition("/")
    stem = os.path.splitext(rest)[0]
    clones_ = clones(system)
    return f"{system}:{clones_[stem][0] if stem in clones_ else stem}" if system in names.SYSTEMS else None


def main():
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if inventory.current() is None:
        sys.exit("No storage cache for the storage in use: run `sync-roms cache update` first.")
    try:
        with open(CHECKED) as f:
            checked = json.load(f)
    except FileNotFoundError:
        checked = {}

    games, referenced = {}, set()
    for game_set in store.repo_set_files():
        for g in game_set["games"]:
            key = g.get("bucket")
            if not key:
                continue
            referenced.update([key, *g.get("files", [])])
            info = games.setdefault(key, {"game": key, "title": g.get("title") or names.title(key),
                                          "system": g.get("system"), "sets": [], "variants": []})
            info["sets"].append(game_set["id"])
            for v in g.get("variants", []):
                referenced.update([v["bucket"], *v.get("files", [])])
                if all(v["bucket"] != x["bucket"] for x in info["variants"]):
                    info["variants"].append(v)

    stored = set()
    for s in store.repo_json("systems"):
        stored.update(k for k in inventory.files(f"{s['bucket']}/", sizes=False) if not k.endswith("/"))

    by_title, by_family = defaultdict(list), defaultdict(list)
    for key, info in games.items():
        by_title[norm(info["title"])].append(key)
        if clone_parent(key):
            by_family[clone_parent(key)].append(key)

    unlisted = sorted(k for k in stored - referenced if not vita.is_extra(k))
    groups = m3u.file_groups(unlisted)
    # a multi-disc game is checked once any of its files is: a judged one's discs would otherwise come back
    new = [k for k in unlisted if not any(g in checked for g in groups.get(k, [k]))]
    if "--baseline" in sys.argv[1:]:
        checked.update({k: "baseline: in storage before variants were tracked" for k in new})
        with open(CHECKED, "w") as f:
            json.dump(checked, f, indent=1, ensure_ascii=False, sort_keys=True)
        print(f"Marked {len(new)} unlisted ROM(s) as checked in {CHECKED}")
        return
    matches, unmatched, seen = defaultdict(list), 0, set()
    for key in new:
        if key in seen:
            continue
        group = groups.get(key, [key])
        seen.update(group)
        bucket = group[0]
        title = names.title(bucket)
        found = set(by_title.get(norm(title), [])) | set(by_family.get(clone_parent(bucket), []))
        if not found:
            unmatched += 1
        for game in found:
            matches[game].append({"bucket": bucket, "title": title, **({"files": group[1:]} if len(group) > 1 else {})})

    stale = [{"game": key, "bucket": v["bucket"]} for key, info in games.items() for v in info["variants"]
             if v["bucket"] not in stored]
    out = {"matches": [{**games[k], "candidates": c} for k, c in sorted(matches.items())],
           "stale": stale, "unmatched": unmatched, "checked_file": CHECKED}
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
