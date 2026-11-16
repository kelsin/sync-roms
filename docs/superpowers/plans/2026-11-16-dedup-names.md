# Dedup scraped names

## Intent

Some ROMs in storage show under the same name in the frontends because their `scrapes/<system>/metadata.json`
entries carry the same `name` (several fan translations of one game, a Japanese and a US release, a mis-scrape).
A new project skill, `dedup-names`, finds those groups, and after the user approves, gives each ROM a name that tells
it apart, or re-scrapes ROMs that were matched to the wrong game.

## Decisions (from the user)

- Names are the scraped name plus a short qualifier in parentheses: `The Legendary Starfy (Japan)`,
  `Chrono Trigger (Wakkoswami, Relocalized) - Translated`. The qualifier sits before ` - Translated`. The plainest or
  main version of a group may keep the bare name.
- Mis-scrapes (a ROM matched to another game) are re-scraped with `scrape match` after approval.
- Fixed names survive re-scrapes.

## Design

**Qualifier field.** A metadata entry may hold `"qualifier": "<text>"`. Its `name` is then
`<scraped name> (<qualifier>)`, followed by ` - Translated` when translated. In `screenscraper.py`, beside
`mark_translated`:

- `qualify(entry)`: a copy whose name carries the entry's qualifier (inserted before ` - Translated` when the name
  ends with it); unchanged when there is no qualifier, no name, or the name already carries it. Idempotent.
- `set_qualifier(entry, qualifier)`: a copy with the old qualifier (if any) taken out of the name, then the new one
  set and applied with `qualify`; `None` or `""` removes the qualifier and the field.

`scrape_online.record` keeps an old entry's `qualifier` on the new entry (also with `replace`) and applies `qualify`
before `mark_translated`, so a re-scrape gives the same name back. Nothing else changes: frontends read `name`.

**Skill** `.claude/skills/dedup-names/` with `SKILL.md` and three scripts (run from the repo root with
`uv run --frozen python ...`):

1. `scripts/find_duplicates.py` prints JSON `{"groups": [...], "skipped": {...}}`. A group is one system's ROMs whose
   shown name is the same (compare case-insensitively, after whitespace collapse). Each group:
   `{"system", "name", "roms": [{"rom", "name", "qualifier"?, "translated"?, "developer", "releasedate"}]}`.
   Only ROMs a frontend shows as a game count:
   - stored in storage (`inventory.files`, which leaves ignored ROMs out), not `vita.is_extra`;
   - not a disc of a multi-disc game (`m3u.disc_keys`); the `.m3u` stands for it;
   - not a file inside a folder named after a sibling set (`mame/area51/area51.chd` beside `mame/area51.zip`);
   - not a MAME/FBNeo set in a `clones.json` family: frontends show the clones.json name for those
     (`scrape_plan.variant_tags`), so they are counted in `skipped` instead.
   Needs the storage cache (`inventory.current()`), like update-variants.
2. `scripts/search_games.py SYSTEM QUERY [QUERY ...]` prints JSON `{query: [[game id, title], ...]}` from
   ScreenScraper's search (`scrape_online.make_client()`, `client.search(system["screenscraper"], query)`), for
   picking the right game of a mis-scrape.
3. `scripts/apply_names.py decisions.json` with
   `{"qualify": [{"system", "rom", "qualifier"}], "rescrape": [{"system", "rom", "game": <id>, "qualifier"?}]}`:
   - qualifies: one read and one write of each touched system's metadata.json (`scrape_online.load_metadata`,
     `s3.put_text(scrape_online.metadata_key(...), scrape_plan.dump_json(...))`), using `set_qualifier`; fails
     before writing anything when a ROM has no entry;
   - rescrapes: `scrape_online.match_command` with an `argparse.Namespace(system, rom, game=str(id),
     skip_media=None, translated=<screenscraper.is_translation(rom) or the entry's translated flag>, dry_run=False,
     confirmed=True)`; a given `qualifier` is set on the new entry afterwards the same way as qualifies;
   - prints each change, `--dry-run` prints and writes nothing.

**SKILL.md** steps: refresh the cache, find, judge each group (qualifier per ROM, or rescrape), look up game ids for
rescrapes, show one table and wait for approval, write decisions, dry run, apply. Judging rules:

- Same game, several versions (regions, revisions, translation groups or versions, hacks): give qualifiers that say
  what differs in few words: region (`Japan`), translation group and notable patch (`Aeon Genesis`,
  `Wakkoswami, Relocalized`), hack (`FastROM`), edition (`Deluxe`). The main/plainest version keeps the bare name;
  every other one gets a qualifier. Never repeat ` - Translated` or the base name in the qualifier.
- Different games under one name (a sequel, a sibling, a different release scraped as another game): rescrape, with
  the game id picked from `search_games.py`. When nothing on ScreenScraper fits, give a qualifier instead and say so.
- Can't tell: leave it out and list it for the user.

## Tests

`tests/test_qualifier.py` for `qualify`/`set_qualifier` (plain, translated, idempotent, change, removal); a test in
`tests/test_scrape_run.py` that a re-scrape keeps the qualifier (with and without replace, and with translated);
tests for `find_duplicates`'s grouping filters on fake inputs (pure function taking metadata, stored keys and
clones, kept separate from main) in `tests/test_dedup_names.py`, importing the script by path.
`python -m unittest discover -s tests` passes.
