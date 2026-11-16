---
name: match-translations
description: Use when asked to match or scrape the fan-translated ROMs waiting in `sync-roms scrape review`, or `[T-En]` ROMs ScreenScraper doesn't know (their English titles are listed under the original Japanese name).
---

# Match translations

Fan translations (`[T-En ...]` and the other tags `screenscraper.is_translation` counts) carry an English title that
ScreenScraper doesn't know; it lists the game under its original Japanese (romaji) name. This skill finds that name,
and matches each ROM to the game as a translation (titled "<name> - Translated", as `sync-roms scrape match SYSTEM ROM
GAME --translated` does), after the user approves. Matching writes metadata and media to storage.

Run every command from the repo root.

## 1. List the ROMs

```bash
uv run --frozen python .claude/skills/match-translations/scripts/list_translated.py [SYSTEM] > <scratchpad>/translated.json
```

Each entry has `system` (storage folder), `system_name`, `rom`, `search_name` (the English title from the file name),
`kind` (`notgame` or `unknown`) and, for a non-game, `screenscraper_said`. It makes no ScreenScraper request. Empty:
tell the user there is nothing to match and stop.

## 2. Find each game

Per ROM, find the game's original Japanese title, romanized as ScreenScraper lists it, on the web (screenscraper.fr
game pages, Wikipedia, romhacking.net's page for the translation, GameFAQs). Then search ScreenScraper:

```bash
uv run --frozen python .claude/skills/match-translations/scripts/search.py SYSTEM "<Japanese title>"
```

It prints `[{"id", "title"}]` (one quota request each; keep them few, the quota is daily). No hit: try a variant
(without the subtitle, colon vs dash, the English or alternate title). Pick the result that is the same game on that
system, not a sequel or another release. Not confident: leave the ROM out and list it.

## 3. Show the proposal and wait

Show one table (ROM, Japanese title found, ScreenScraper id and title) and the ROMs left out. Write nothing until the
user approves; apply their corrections.

## 4. Match

Write the approved matches to `<scratchpad>/decisions.json`:

```json
[{"system": "snes", "rom": "<rom from step 1>", "game": 12345}]
```

```bash
uv run --frozen python .claude/skills/match-translations/scripts/match_translated.py <scratchpad>/decisions.json --dry-run
uv run --frozen python .claude/skills/match-translations/scripts/match_translated.py <scratchpad>/decisions.json
```

It scrapes each ROM as its game, takes matched ROMs off the review lists, stops at a quota error, and prints
`matched`, `failed` and `not_tried`. Report them; ROMs left out or failed stay in `sync-roms scrape review`.
