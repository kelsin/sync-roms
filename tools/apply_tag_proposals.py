#!/usr/bin/env python3
"""Summarize or apply the tag proposals agents wrote for a tag review (see export_tag_review.py).

    tools/apply_tag_proposals.py OUT_DIR [--summary | --apply]

Proposals are OUT_DIR/proposals/*.json: {"add": {key: [tag ids]}, "remove": {key: [tag ids]}, "new_tags": {id: {...}}},
read in file-name order (a later file overrides an earlier one for the same game and tag). Tag ids not in
vocabulary.json and keys not in the export are ignored and reported. --summary (the default) is read-only and prints
the added and removed counts per tag with sample titles. --apply writes the changes through tags.change_game_tags;
new_tags are only listed, never created.
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import inventory, runtime, s3, tags, ui, usersettings  # noqa: E402

SAMPLES = 5


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(out_dir):
    """(vocabulary, {key: {"title", "tags"}}, [proposal dicts in file-name order])."""
    vocab = _read(os.path.join(out_dir, "vocabulary.json"))
    games = {}
    for path in sorted(glob.glob(os.path.join(out_dir, "systems", "*.json"))):
        for row in _read(path):
            games[row["key"]] = {"title": row["title"], "tags": set(row["tags"])}
    proposals = [_read(p) for p in sorted(glob.glob(os.path.join(out_dir, "proposals", "*.json")))]
    return vocab, games, proposals


def plan(vocab, games, proposals):
    """What the proposals change: {"changes": {key: (add ids, remove ids)} (only real changes, sorted lists),
    "unknown_tags": sorted ids, "unknown_keys": sorted keys, "new_tags": {id: fields}}."""
    want = collections.defaultdict(dict)  # key -> {tag id: True to add, False to remove}
    unknown_tags, unknown_keys, new_tags = set(), set(), {}
    for proposal in proposals:
        for action, value in (("add", True), ("remove", False)):
            for key, ids in proposal.get(action, {}).items():
                if key not in games:
                    unknown_keys.add(key)
                    continue
                for tag_id in ids:
                    if tag_id in vocab:
                        want[key][tag_id] = value
                    else:
                        unknown_tags.add(tag_id)
        new_tags.update(proposal.get("new_tags", {}))
    changes = {}
    for key in sorted(want):
        have = games[key]["tags"]
        add = sorted(t for t, v in want[key].items() if v and t not in have)
        remove = sorted(t for t, v in want[key].items() if not v and t in have)
        if add or remove:
            changes[key] = (add, remove)
    return {"changes": changes, "unknown_tags": sorted(unknown_tags), "unknown_keys": sorted(unknown_keys),
            "new_tags": new_tags}


def summary_text(vocab, games, result):
    added, removed = collections.defaultdict(list), collections.defaultdict(list)
    for key, (add, remove) in result["changes"].items():
        for t in add:
            added[t].append(games[key]["title"])
        for t in remove:
            removed[t].append(games[key]["title"])
    lines = []
    for t in sorted(set(added) | set(removed), key=lambda t: (-len(added[t]) - len(removed[t]), t)):
        lines.append(f"{t} ({vocab[t]['name']}): +{len(added[t])} -{len(removed[t])}")
        if added[t]:
            lines.append("  add: " + "; ".join(added[t][:SAMPLES]))
        if removed[t]:
            lines.append("  remove: " + "; ".join(removed[t][:SAMPLES]))
    lines.append(f"{len(result['changes'])} games change")
    if result["unknown_tags"]:
        lines.append("Ignored unknown tag ids: " + ", ".join(result["unknown_tags"]))
    if result["unknown_keys"]:
        lines.append(f"Ignored {len(result['unknown_keys'])} keys not in the export: " +
                     ", ".join(result["unknown_keys"][:SAMPLES]) + (" ..." if len(result["unknown_keys"]) > SAMPLES else ""))
    if result["new_tags"]:
        lines.append("Proposed new tags (never created here): " +
                     ", ".join(f"{i} ({f.get('name', '')})" for i, f in sorted(result["new_tags"].items())))
    return "\n".join(lines)


def apply(result):
    """Write each game's changes through tags.change_game_tags; returns how many games changed."""
    for key, (add, remove) in result["changes"].items():
        tags.change_game_tags(key, add=add, remove=remove)
    return len(result["changes"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out_dir", help="the export folder")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--summary", action="store_true", help="print what would change (default; reads only)")
    mode.add_argument("--apply", action="store_true", help="write the changes to tags.json in storage")
    args = parser.parse_args(argv)
    try:
        vocab, games, proposals = load(args.out_dir)
    except (OSError, ValueError) as e:
        ui.fail(str(e), 1)
    result = plan(vocab, games, proposals)
    print(summary_text(vocab, games, result))
    if not args.apply:
        return 0
    usersettings.apply_settings()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):
        ui.fail(f"{runtime.ROOT} is missing", 1)
    try:
        try:
            n = apply(result)
        finally:
            inventory.flush()
    except (*s3.ERRORS, OSError) as e:
        ui.fail(str(e), 1)
    print(f"{n} games written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
