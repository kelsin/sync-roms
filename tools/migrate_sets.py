#!/usr/bin/env python3
"""One-off: copy the game sets from the repo into storage (sets/<id>.json).

    tools/migrate_sets.py [--from DIR] [--apply]

Copies every *.json in DIR (default src/sync_roms/data/sets in the repo) to storage's sets/<id>.json, byte for byte.
A set that is already in storage is kept (never overwritten), so running it again writes nothing. Every file is
checked (a JSON object with a games list) before anything is written. The source files are never edited or deleted.
Without --apply it only prints what it would write. Storage is the one sync-roms uses (set it with
ROMS_BUCKET/ROMS_ROOT or ~/.sync-roms/settings.json).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import inventory, runtime, s3, shared, store, ui, usersettings  # noqa: E402

DEFAULT_FROM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "sets")


def load_sources(folder):
    """[(file name, text)] of the *.json files in folder; ValueError when one isn't a set file."""
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError as e:
        raise ValueError(f"{folder}: {e}")
    out = []
    for name in names:
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            data = json.loads(text)
        except (OSError, ValueError) as e:
            raise ValueError(f"{path}: {e}")
        if not isinstance(data, dict) or not isinstance(data.get("games"), list):
            raise ValueError(f"{path}: not a JSON object with a games list")
        out.append((name, text))
    return out


def in_storage(key):
    try:
        shared.read(key)
        return True
    except s3.ERRORS as e:
        if s3.missing(e):
            return False
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="source", default=DEFAULT_FROM, help="folder of set files (default: the repo's)")
    parser.add_argument("--apply", action="store_true", help="write to storage (default: only print what would change)")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not an empty storage
        ui.fail(f"{runtime.ROOT} is missing", 1)
    try:
        sources = load_sources(args.source)
    except ValueError as e:
        ui.fail(str(e), 1)
    new = kept = 0
    try:
        for name, text in sources:
            key = store.SETS + name
            try:
                if in_storage(key):
                    kept += 1
                    continue
                if args.apply:
                    shared.write(key, text)
            except (*s3.ERRORS, OSError) as e:
                ui.fail(f"{key}: {e}", 1)
            new += 1
            print(f"{key}" + (" (written)" if args.apply else ""))
    finally:
        if args.apply:
            inventory.flush()  # the storage cache lists the files written (the CLI does this as it exits)
    print(f"kept {kept} already in storage")
    if not args.apply and new:
        print(f"Dry run: {new} file(s) would be written. Run again with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
