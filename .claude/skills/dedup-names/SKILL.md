---
name: dedup-names
description: Use when several ROMs show under the same name in the frontends, or when asked to find, fix or tell apart duplicate scraped names (fan translations of one game, regional releases, mis-scrapes) in storage's scrapes metadata.
---

# Dedup names

Frontends show a ROM under the `name` of its entry in storage's `scrapes/<system>/metadata.json`. This skill finds
ROMs of one system shown under the same name and, after the user approves, gives each a name that tells it apart
(a `qualifier`, see "Data files" in CLAUDE.md), or re-scrapes ROMs that were matched to the wrong game.

**It only edits metadata entries.** It never renames, moves or deletes ROMs or media, and never touches sets.

Run every command from the repo root.

## 1. Find duplicates

```bash
uv run sync-roms cache update
uv run --frozen python .claude/skills/dedup-names/scripts/find_duplicates.py > <scratchpad>/duplicates.json
```

The output has:
- `groups`: `system`, the shared `name` and its `roms` (`rom`, `name`, `qualifier`, `translated`, `developer`,
  `releasedate`). Only ROMs shown as a game count: discs of a multi-disc game (its `.m3u` stands for them), files
  in a set's folder, Vita extras and entries whose ROM isn't in the storage cache are left out.
- `skipped`: counts of what was left out (`discs`, `set_folders`, `vita_extras`, `not_stored`); mention the counts.

No groups: tell the user there is nothing to fix and stop.

## 2. Judge each group

Read each ROM's file name, developer and release date, and decide per ROM:

| Group | Verdict |
|---|---|
| Same game, several versions (regions, revisions, translation groups or versions, hacks) | qualify: the main or plainest version keeps the bare name, every other ROM gets a qualifier |
| Different games under one name (a sequel, a sibling, another release scraped as this game) | rescrape the wrong ROM(s) with the right game id |
| Rescrape, but nothing on ScreenScraper fits | qualify instead, and say so |
| Can't tell | leave it out of the decisions; list it for the user |

A qualifier says what differs in a few words: region (`Japan`), translation group and notable patch
(`Aeon Genesis`, `Wakkoswami, Relocalized`), hack (`FastROM`), edition (`Deluxe`). The name becomes
`<name> (<qualifier>)`, before ` - Translated`, so never repeat ` - Translated` or the base name in it. Examples:

| ROM | Shown name |
|---|---|
| `Densetsu no Stafy (Japan).zip` beside a translation, both scraped as `Densetsu No Stafy` | `Densetsu No Stafy (Japan)` |
| `Chrono Trigger (Japan) [T-En by Wakkoswami v1.0] [Relocalized].zip` | `Chrono Trigger (Wakkoswami, Relocalized) - Translated` |
| `Mickey & Donald - Magical Adventure 3 (Japan) [T-En by RPGOne v1.5] [FastROM hack by kandowontu v1.0].zip` beside the plain RPGOne one | `Mickey To Donald - Magical Adventure 3 (FastROM, kandowontu) - Translated` |
| `Runabout 3D - Drive Impossible (Japan).zip` shown as Crash City Mayhem, its US release | `Crash City Mayhem (Japan)` |
| `Dragon Quest III (Japan) [T-En by DQ Translations v1.1].zip` shown as `Dragon Quest 1 And 2 - Translated` | rescrape: another game |

For a rescrape, find the game id:

```bash
uv run --frozen python .claude/skills/dedup-names/scripts/search_games.py <system> "<title>" ["<other title>" ...]
```

It prints `{query: [[game id, title], ...]}`. Each query is a ScreenScraper request; search only for rescrapes.

More than about 60 groups: split them into batches and give each to a subagent with this section; collect their
verdicts as the decisions file below.

## 3. Show the proposal and wait

Show the user one table (system, ROM, old name, new name or the rescrape's game id and title), the groups you
couldn't judge and the skipped counts. Write nothing until the user approves; apply their corrections.

## 4. Apply

Write the approved decisions to `<scratchpad>/decisions.json`:

```json
{"qualify": [{"system": "snes", "rom": "<ROM path>", "qualifier": "Aeon Genesis"}],
 "rescrape": [{"system": "3ds", "rom": "<ROM path>", "game": 12345, "qualifier": "Japan"}]}
```

```bash
uv run --frozen python .claude/skills/dedup-names/scripts/apply_names.py <scratchpad>/decisions.json --dry-run
uv run --frozen python .claude/skills/dedup-names/scripts/apply_names.py <scratchpad>/decisions.json
```

Check the dry run's changes, then apply. Pipe nothing in and answer nothing: rescrapes run `scrape match` with
`confirmed=True`, so it never asks (a fan translation is re-scraped as translated). A rescrape's `qualifier` is
optional and set after it. A qualifier stays through later re-scrapes. Then run `find_duplicates.py` again: a
rescrape can land on a name another ROM already has (several ROMs rescraped to one game, or to a game that is
already in storage), and those groups are judged and applied the same way. Report what changed and any failed
rescrapes. Nothing is committed: the changes are in storage.
