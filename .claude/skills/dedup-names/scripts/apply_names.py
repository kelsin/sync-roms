"""Apply approved name fixes to storage's scrapes/<system>/metadata.json: qualifiers, and re-scrapes of mis-scraped ROMs.

Run from the repo root: uv run --frozen python .claude/skills/dedup-names/scripts/apply_names.py decisions.json [--dry-run]

decisions.json:
  {"qualify": [{"system", "rom", "qualifier"}],
   "rescrape": [{"system", "rom", "game": <ScreenScraper game id>, "qualifier"?}]}
A re-scrape runs `sync-roms scrape match` without asking; its qualifier is set on the new entry afterwards.
Prints each change; --dry-run writes nothing and makes no ScreenScraper calls.
"""
import argparse
import json
import sys
from collections import defaultdict

from sync_roms import s3, scrape_online, scrape_plan, screenscraper, usersettings


def qualify_all(items, dry_run):
    """Set each item's qualifier: one read and one write per system. Exits before writing when a ROM has no entry."""
    by_system, writes = defaultdict(list), []
    for item in items:
        by_system[item["system"]].append(item)
    for system, todo in sorted(by_system.items()):
        metadata = scrape_online.load_metadata(system)
        missing = [i["rom"] for i in todo if not isinstance(metadata.get(i["rom"]), dict)]
        if missing:
            sys.exit(f"No {system} metadata entry for these ROMs, nothing was changed: " + ", ".join(missing))
        for i in todo:
            new = screenscraper.set_qualifier(metadata[i["rom"]], i.get("qualifier"))
            print(f"{system}/{i['rom']}: {metadata[i['rom']].get('name')} → {new.get('name')}")
            metadata[i["rom"]] = new
        writes.append((system, metadata))
    if not dry_run:  # every system read and checked above: only now write
        for system, metadata in writes:
            s3.put_text(scrape_online.metadata_key(system), scrape_plan.dump_json(metadata))


def rescrape(item, dry_run):
    """Re-scrape one ROM as the given game, then set its qualifier. Returns whether it worked."""
    system, rom = item["system"], item["rom"]
    entry = scrape_online.load_metadata(system).get(rom, {})
    translated = screenscraper.is_translation(rom) or bool(entry.get("translated"))
    if dry_run:
        print(f"{system}/{rom}: {entry.get('name')} → re-scrape as ScreenScraper game {item['game']}"
              + (f", qualifier {item['qualifier']}" if item.get("qualifier") else ""))
        return True
    args = argparse.Namespace(system=system, rom=rom, game=str(item["game"]), skip_media=None, translated=translated,
                              dry_run=False, confirmed=True)
    if scrape_online.match_command(args):
        print(f"{system}/{rom}: re-scrape failed, its qualifier was not set")
        return False
    if item.get("qualifier"):
        qualify_all([item], dry_run)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("decisions")
    parser.add_argument("--dry-run", action="store_true", help="print the changes, write nothing")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    with open(args.decisions) as f:
        decisions = json.load(f)
    qualify_all(decisions.get("qualify", []), args.dry_run)
    ok = [rescrape(item, args.dry_run) for item in decisions.get("rescrape", [])]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
