#!/usr/bin/env python3
"""One-off: mark already scraped fan translations in storage's scrapes/<system>/metadata.json.

    tools/mark_translations.py [--write]

For every ROM whose file name carries a translation tag and whose entry isn't marked yet, adds
" - Translated" to its name and sets "translated". Prints each change; without --write nothing is written.
Makes no ScreenScraper calls.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import s3, scrape_online, scrape_plan, screenscraper, store, ui, usersettings  # noqa: E402


def changes(metadata):
    """{ROM: new entry} for the tagged ROMs whose entry would change."""
    out = {}
    for rom, entry in metadata.items():
        if isinstance(entry, dict) and screenscraper.is_translation(rom):
            new = screenscraper.mark_translated(entry)
            if new != entry:
                out[rom] = new
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true", help="write the changes (default: only print them)")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    total = 0
    for system in store.repo_json("systems"):
        name = system["bucket"]
        try:
            metadata = scrape_online.load_metadata(name)
        except ValueError as e:
            ui.warn(f"Skipping {name}: {e}")
            continue
        found = changes(metadata)
        if not found:
            continue
        for rom, new in found.items():
            old_name = metadata[rom].get("name")
            print(f"{name}/{rom}: {old_name or '(no name)'} → {new.get('name') or 'translated'}")
        total += len(found)
        if args.write:
            s3.put_text(scrape_online.metadata_key(name), scrape_plan.dump_json({**metadata, **found}))
    print(f"{total} entr{'y' if total == 1 else 'ies'} {'updated' if args.write else 'would change (use --write)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
