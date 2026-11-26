#!/usr/bin/env python3
"""Export the tag vocabulary and every system's games for a review of their tags (reads storage, writes only OUT_DIR).

    tools/export_tag_review.py OUT_DIR

Writes OUT_DIR/vocabulary.json ({tag id: {"name", "description"}}) and OUT_DIR/systems/<system>-<n>.json, chunks of at
most 400 games: [{"key", "title", "tags": [tag ids]}]. Ignored ROMs are left out. OUT_DIR is scratch space: never
storage.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import inventory, names, runtime, s3, store, tags, ui, usersettings  # noqa: E402

CHUNK = 400


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def vocabulary():
    return {i: {"name": t["name"], "description": t.get("description", "")} for i, t in sorted(tags.all_tags().items())}


def games(system):
    """[{"key", "title", "tags"}] of the system's games in storage, sorted by key."""
    listing = inventory.files(f"{system}/", sizes=False)
    return [{"key": k, "title": names.title(k), "tags": tags.tags_of(k)} for k in sorted(listing)
            if tags.owner(k) == k]  # a file of another record (a disc) is tagged with its game


def export(out_dir, systems):
    """Write the vocabulary and the chunks; returns the chunk file names written."""
    write_json(os.path.join(out_dir, "vocabulary.json"), vocabulary())
    written = []
    for system in systems:
        rows = games(system)
        for n, start in enumerate(range(0, len(rows), CHUNK), 1):
            name = f"{system}-{n}.json"
            write_json(os.path.join(out_dir, "systems", name), rows[start:start + CHUNK])
            written.append(name)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out_dir", help="scratch folder to write into (never storage)")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not an empty storage
        ui.fail(f"{runtime.ROOT} is missing", 1)
    try:
        written = export(args.out_dir, [s["bucket"] for s in store.repo_json("systems")])
    except (*s3.ERRORS, OSError) as e:
        ui.fail(str(e), 1)
    print(f"{len(written)} chunks in {os.path.join(args.out_dir, 'systems')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
