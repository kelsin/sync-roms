#!/usr/bin/env python3
"""One-off: move the old local scrape state (in the data folder) into storage.

    tools/migrate_scrape_state.py [--apply]

Reads scrape-{matches,unknown,nomedia,hashes}.json (flat {"system/rom": value}), scrape-notgames.json and
variants-checked.json, and merges them into storage: scrapes/<system>/{matches,unknown,nomedia,hashes}.json,
scrapes/notgames.json and variants-checked.json. Entries already in storage are kept (storage wins on a conflict,
the kept-for-later list is joined), so running it again changes nothing. Without --apply it only prints what it would
write. The old local files are never edited or deleted. Storage is the one sync-roms uses (--bucket/--root are not
taken: set it with ROMS_BUCKET/ROMS_ROOT or ~/.sync-roms/settings.json).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import runtime, s3, scrape_plan, scrape_state, shared, store, ui, usersettings  # noqa: E402

KINDS = {"scrape-matches.json": scrape_state.MATCHES, "scrape-unknown.json": scrape_state.UNKNOWN,
         "scrape-nomedia.json": scrape_state.NOMEDIA, "scrape-hashes.json": scrape_state.HASHES}
NOTGAMES = "scrape-notgames.json"
CHECKED = "variants-checked.json"


def _object(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _old(name):
    """The old local file's object, {} when it isn't there; ValueError when it is malformed."""
    path = os.path.join(store.data_dir(), name)
    try:
        with open(path, encoding="utf-8") as f:
            return _object(f.read())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: {e}")


def _add_missing(entries):
    """A change that adds the entries storage doesn't have yet."""
    def change(data):
        for k, v in entries.items():
            data.setdefault(k, v)
    return change


def _add_notgames(entries):
    def change(data):
        for k, v in entries.items():
            if k == scrape_state.KEPT:
                if isinstance(v, list):
                    have = data.get(k)
                    have = have if isinstance(have, list) else []
                    data[k] = sorted({x for x in have + v if isinstance(x, str)})
            else:
                data.setdefault(k, v)
    return change


def plan():
    """[(storage key, old entries, change)] for everything the old files hold."""
    out = []
    for name, kind in KINDS.items():
        per_system, skipped = {}, 0
        for key, value in _old(name).items():
            system, _, rom = key.partition("/")
            if system and rom:
                per_system.setdefault(system, {})[rom] = value
            else:
                skipped += 1
        if skipped:
            print(f"skipped {skipped} malformed key(s) in {name}")
        for system, entries in sorted(per_system.items()):
            out.append((f"{scrape_plan.SCRAPES}/{system}/{kind}", entries, _add_missing(entries)))
    for key, entries, change in ((scrape_state.NOTGAMES, _old(NOTGAMES), _add_notgames),
                                 (CHECKED, _old(CHECKED), _add_missing)):
        if entries:
            out.append((key, entries, change(entries)))
    return out


def _current(key):
    try:
        return _object(shared.read(key))
    except s3.ERRORS as e:
        if s3.missing(e):
            return {}
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog="Entries already in storage are kept; the notgames \"kept\" list is unioned.")
    parser.add_argument("--apply", action="store_true", help="write to storage (default: only print what would change)")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not an empty storage
        ui.fail(f"{runtime.ROOT} is missing", 1)
    try:
        steps = plan()
    except ValueError as e:
        ui.fail(str(e), 1)
    total = 0
    for key, entries, change in steps:
        try:
            if args.apply:
                before = _current(key)
                after = shared.update(key, _object, {}, change, scrape_plan.dump_json)
            else:
                before = _current(key)
                after = json.loads(json.dumps(before))
                change(after)
        except (*s3.ERRORS, ValueError) as e:
            ui.fail(f"{key}: {e}", 1)
        added = sum(1 for k in after if k not in before)
        changed = after != before
        total += changed
        print(f"{key}: {len(entries)} old, {added} new" + (" (written)" if args.apply and changed else "")
              + ("" if changed else " (nothing to change)"))
    if not args.apply and total:
        print(f"Dry run: {total} file(s) would change. Run again with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
