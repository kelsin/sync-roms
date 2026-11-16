"""Match fan-translated ROMs to ScreenScraper games and scrape them as translations, as
`sync-roms scrape match SYSTEM ROM GAME --translated` does; each matched ROM leaves `scrape review`.

Run from the repo root:
  uv run --frozen python .claude/skills/match-translations/scripts/match_translated.py DECISIONS.json [--dry-run]
DECISIONS.json: [{"system": "<storage folder>", "rom": "<ROM path in it>", "game": <ScreenScraper game id>}].
Without --dry-run this writes metadata and media to storage. Stops at the first quota error.
"""
import argparse
import json
import sys

from sync_roms import inventory, scrape_online, scrape_review, scrape_state, screenscraper, usersettings


class QuotaWatch:
    """The client, noting when a request raised QuotaExceeded (match_command and run_scrape handle it themselves)."""

    def __init__(self, client):
        self._client, self.quota_hit = client, False

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except screenscraper.QuotaExceeded:
                self.quota_hit = True
                raise
        return call


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("decisions")
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args()
    usersettings.apply_settings()
    if inventory.current() is None:
        sys.exit("No storage cache for the storage in use: run `sync-roms cache update` first.")
    with open(opts.decisions) as f:
        decisions = json.load(f)
    client = QuotaWatch(scrape_online.make_client())
    matched, failed = [], []
    for d in decisions:
        key, game = f"{d['system']}/{d['rom']}", int(d["game"])
        try:
            code = scrape_online.match_command(argparse.Namespace(
                system=d["system"], rom=d["rom"], game=str(game), skip_media=None, dry_run=opts.dry_run,
                confirmed=True, client=client, translated=True))
        except SystemExit as e:  # ui.fail
            code = e.code if isinstance(e.code, int) else 1
        if code == 0 and (opts.dry_run or scrape_state.manual_match(d["system"], d["rom"]) == game):
            matched.append(key)
            if not opts.dry_run:
                scrape_review._clear(key)
        else:
            failed.append(key)
        if client.quota_hit:
            print("ScreenScraper quota hit: stopping; run again tomorrow for the rest.", file=sys.stderr)
            break
    done = len(matched) + len(failed)
    print(json.dumps({"dry_run": opts.dry_run, "matched": matched, "failed": failed,
                      "not_tried": [f"{d['system']}/{d['rom']}" for d in decisions[done:]]}, indent=1, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
