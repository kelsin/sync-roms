"""Print, as JSON, ScreenScraper's games for each query: {query: [[game id, title], ...]}.

Run from the repo root: uv run --frozen python .claude/skills/dedup-names/scripts/search_games.py SYSTEM QUERY [QUERY ...]
SYSTEM is a storage folder name (snes, gba, ...). Uses the ScreenScraper login in settings.json.
"""
import json
import sys

from sync_roms import scrape_online, store, usersettings


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    usersettings.apply_settings()
    system = next((s for s in store.repo_json("systems") if s["bucket"] == argv[0]), None)
    if not system or "screenscraper" not in system:
        sys.exit(f"{argv[0]} is no system with a ScreenScraper id")
    client = scrape_online.make_client()
    json.dump({q: client.search(system["screenscraper"], q) for q in argv[1:]}, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
