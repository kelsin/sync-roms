"""Print, as JSON, ScreenScraper's search results ([{"id", "title"}]) for a name on one system. One quota request.

Run from the repo root: uv run --frozen python .claude/skills/match-translations/scripts/search.py SYSTEM QUERY
SYSTEM is the storage folder (e.g. snes).
"""
import json
import sys

from sync_roms import scrape_online, screenscraper, usersettings


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: search.py SYSTEM QUERY")
    usersettings.apply_settings()
    system = scrape_online._pick_systems(sys.argv[1])[0]
    if "screenscraper" not in system:
        sys.exit(f"{system['bucket']} has no ScreenScraper system id")
    try:
        results = scrape_online._RomClient(scrape_online.make_client()).search(system["screenscraper"], sys.argv[2])
    except screenscraper.NotFound:
        results = []
    except (screenscraper.ApiError, screenscraper.QuotaExceeded) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)
    json.dump([{"id": i, "title": t} for i, t in results], sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
