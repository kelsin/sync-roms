"""Print, as JSON, the fan-translated ROMs waiting for `sync-roms scrape review` (non-games and unknowns).

Run from the repo root: uv run --frozen python .claude/skills/match-translations/scripts/list_translated.py [SYSTEM]
Read-only; makes no ScreenScraper request. Reads storage only through the storage cache (sync-roms cache update).
"""
import json
import sys

from sync_roms import inventory, scrape_online, scrape_review, scrape_state, screenscraper, usersettings


def main():
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if inventory.current() is None:
        sys.exit("No storage cache for the storage in use: run `sync-roms cache update` first.")
    only = sys.argv[1] if len(sys.argv) > 1 else None
    systems = {s["bucket"]: s for s in scrape_online._pick_systems(only) if "screenscraper" in s}
    notgames = scrape_state.notgames()
    keys = {k for k in set(notgames) | scrape_state.unknown()
            if k.split("/", 1)[0] in systems and screenscraper.is_translation(k)}
    keys -= scrape_review._scraped(keys)
    stored = inventory.stat(sorted(keys))
    out = []
    for key in sorted(k for k in keys if k in stored):
        name, rom = key.split("/", 1)
        out.append({"key": key, "system": name, "screenscraper": systems[name]["screenscraper"],
                    "system_name": systems[name].get("name"), "rom": rom, "search_name": scrape_review.search_name(rom),
                    "kind": "notgame" if key in notgames else "unknown",
                    **({"screenscraper_said": notgames[key]} if key in notgames else {})})
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
