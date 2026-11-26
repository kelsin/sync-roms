#!/usr/bin/env python3
"""Summarize or apply the tag proposals agents wrote for a tag review (see export_tag_review.py).

    tools/apply_tag_proposals.py OUT_DIR [--summary | --apply] [--no-removals] [--skip-tag TAG ...]

Proposals are OUT_DIR/proposals/*.json: {"add": {key: [tag ids]}, "remove": {key: [tag ids]}, "new_tags": {id: {...}}},
read in file-name order (a later file overrides an earlier one for the same game and tag). Tag ids not in
vocabulary.json, tag ids deleted from storage's tags since the export, keys not in the export and keys that are files
of another record are ignored and reported. Both modes read storage's tags.json (the live tags and the records' files;
an unreachable storage is an error, never a skipped check). --summary (the default) writes nothing and prints the added
and removed counts per tag with sample titles. --apply writes the changes in one write through tags.change_games_tags;
new_tags are only listed, never created.
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import inventory, s3, shared, tags, ui, usersettings  # noqa: E402

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
    proposals = []
    for path in sorted(glob.glob(os.path.join(out_dir, "proposals", "*.json"))):
        proposals.append({**_read(path), "_file": os.path.basename(path)})
    return vocab, games, proposals


def live_tags():
    """The tags in storage's tags.json, read from storage itself: raises (s3.ERRORS, OSError, ValueError) when it
    can't be read, where tags.load() would warn and use the local copy."""
    s3.check_root()
    tags.reset()
    shared.load(tags.KEY, tags.parse, {"tags": {}, "games": {}, "declined": {}}, fallback=False)
    return tags.all_tags()


def plan(vocab, games, proposals, no_removals=False, skip_tags=()):
    """no_removals ignores every "remove" entry; skip_tags drops those tag ids from adds and removes. Raises when
    storage's tags can't be read. What the proposals change: {"changes": {key: (add ids, remove ids)} (only real
    changes, sorted lists), "unknown_tags": sorted ids not in the export's vocabulary, "deleted_tags": sorted ids in it
    that storage no longer has, "unknown_keys": sorted keys, "file_keys": keys that are files of another record,
    "conflicts": [(key, tag id)] for a tag in both add and remove of one file (kept keys only), "new_tags": {id:
    fields}, "new_tag_files": {id: [proposal files]}}."""
    live = live_tags()
    want = collections.defaultdict(dict)  # key -> {tag id: True to add, False to remove}
    unknown_tags, deleted_tags, unknown_keys, new_tags, owned, conflicts = set(), set(), set(), {}, set(), set()
    new_tag_files = collections.defaultdict(list)
    for proposal in proposals:
        kept = {}  # key -> {action: valid ids} for the keys that pass the checks
        for action, value in (("add", True), ("remove", False)):
            if action == "remove" and no_removals:
                continue
            for key, ids in proposal.get(action, {}).items():
                if key not in games:
                    unknown_keys.add(key)
                    continue
                if tags.owner(key) != key:
                    owned.add(key)
                    continue
                for tag_id in ids:
                    if tag_id in skip_tags:
                        continue
                    if tag_id not in vocab:
                        unknown_tags.add(tag_id)
                    elif tag_id not in live:
                        deleted_tags.add(tag_id)
                    else:
                        want[key][tag_id] = value
                        kept.setdefault(key, {}).setdefault(action, set()).add(tag_id)
        conflicts.update((key, t) for key, acts in kept.items() for t in acts.get("add", set()) & acts.get("remove", set()))
        for tag_id, fields in proposal.get("new_tags", {}).items():
            new_tags[tag_id] = {**new_tags.get(tag_id, {}), **fields}
            new_tag_files[tag_id].append(proposal.get("_file", "?"))
    changes = {}
    for key in sorted(want):
        have = games[key]["tags"]
        add = sorted(t for t, v in want[key].items() if v and t not in have)
        remove = sorted(t for t, v in want[key].items() if not v and t in have)
        if add or remove:
            changes[key] = (add, remove)
    return {"changes": changes, "unknown_tags": sorted(unknown_tags), "unknown_keys": sorted(unknown_keys),
            "deleted_tags": sorted(deleted_tags),
            "file_keys": sorted(owned), "conflicts": sorted(conflicts), "new_tags": new_tags,
            "new_tag_files": dict(new_tag_files)}


def summary_text(vocab, games, result):
    added, removed = collections.defaultdict(list), collections.defaultdict(list)
    for key, (add, remove) in result["changes"].items():
        for t in add:
            added[t].append(games[key]["title"])
        for t in remove:
            removed[t].append(games[key]["title"])
    lines = []
    for t in sorted(set(added) | set(removed), key=lambda t: (-len(added[t]), -len(removed[t]), t)):
        lines.append(f"{t} ({vocab[t]['name']}): added {len(added[t])}, removed {len(removed[t])}")
        if added[t]:
            lines.append("  added: " + "; ".join(added[t][:SAMPLES]))
        if removed[t]:
            lines.append("  removed: " + "; ".join(removed[t][:SAMPLES]))
    lines.append(f"Totals: {sum(map(len, added.values()))} tags added, {sum(map(len, removed.values()))} removed")
    lines.append(f"{len(result['changes'])} games change")
    if result["unknown_tags"]:
        lines.append("Ignored unknown tag ids: " + ", ".join(result["unknown_tags"]))
    if result["deleted_tags"]:
        lines.append("Ignored tag ids deleted since the export: " + ", ".join(result["deleted_tags"]))
    if result["unknown_keys"]:
        lines.append(f"Ignored {len(result['unknown_keys'])} keys not in the export: " +
                     ", ".join(result["unknown_keys"][:SAMPLES]) + (" ..." if len(result["unknown_keys"]) > SAMPLES else ""))
    if result["file_keys"]:
        lines.append(f"Ignored {len(result['file_keys'])} keys that are files of another record: " +
                     ", ".join(result["file_keys"][:SAMPLES]) + (" ..." if len(result["file_keys"]) > SAMPLES else ""))
    if result["conflicts"]:
        lines.append("Same tag in add and remove in one file: " +
                     ", ".join(f"{k} [{t}]" for k, t in result["conflicts"][:SAMPLES]) +
                     (" ..." if len(result["conflicts"]) > SAMPLES else ""))
    if result["new_tags"]:
        lines.append("Proposed new tags (never created here):")
        for i, f in sorted(result["new_tags"].items()):
            lines.append(f"  {i} ({f.get('name', '')}): " + ", ".join(result.get("new_tag_files", {}).get(i, [])))
    return "\n".join(lines)


def apply(result):
    """Write all the changes in one tags.change_games_tags write; returns how many games changed."""
    if result["changes"]:
        tags.change_games_tags(result["changes"])
    return len(result["changes"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out_dir", help="the export folder")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--summary", action="store_true", help="print what would change (default; writes nothing)")
    mode.add_argument("--apply", action="store_true", help="write the changes to tags.json in storage")
    parser.add_argument("--no-removals", action="store_true", help="ignore every remove entry")
    parser.add_argument("--skip-tag", action="append", default=[], metavar="TAG",
                        help="drop this tag id from adds and removes (repeatable)")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    try:
        s3.check_root()  # an unmounted share, not an empty storage
        vocab, games, proposals = load(args.out_dir)
        result = plan(vocab, games, proposals, args.no_removals, set(args.skip_tag))  # reads storage's tags
    except (OSError, ValueError, *s3.ERRORS) as e:
        ui.fail(str(e), 1)
    print(summary_text(vocab, games, result))
    if not args.apply:
        return 0
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
