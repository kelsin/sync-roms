# Arcade game names in the editors

## Why

The card, set and collection editors label MAME and FBNeo games by set name (`sf2ce`, `mslug3`), which is hard to
pick from. Devices already get proper names from scraping; the editors should too.

## Goals / non-goals

- Goal: editor rows for `mame` and `fbneo` show a proper game name, and newly picked games save it as their `title`.
- Non-goal: changing gamelists or anything on the device; other systems; rewriting existing saved titles.
- Anti-goal: identical rows for versions of one game (clones must stay distinguishable).

## Name rule (option A, matches the gamelists)

For a set `stem` in system `s`:

1. In `clones.json[s]` (parent or clone): the DAT description, as `scrape_plan.variant_tags` uses for gamelists.
2. Else the `name` in storage's `scrapes/<s>/metadata.json` for that ROM path.
3. Else the set name (`store.key_title`, as today).

## Approaches

1. **Local copy refreshed on tag change (picked).** `~/.sync-roms/names.json` holds `{system: {"tag", "names"}}`
   built from each system's `metadata.json`; reread only when `inventory.tag(metadata key)` differs. Every scrape
   writer changes that tag, so names follow scrapes on any machine.
2. Scraper writes the names file when it finishes: only the scraping machine gets names; every other
   `metadata.json` writer needs the same hook.
3. Read `metadata.json` on every editor open: no cache, ~2MB of mostly descriptions per open, slow on S3.

## Design

- New module `names.py`, modeled on `ignore.py`: `title(key)` returns the name by the rule above for `mame/` and
  `fbneo/` keys and `store.key_title(key)` for everything else. Names load once per run per system, lazily.
- If storage can't be checked, use the local copy with a warning; if there is none, fall back to set names.
- Callers of `store.key_title` that build editor rows or new `title`s (`edit.py`, `commands.py`, `surprise.py`,
  `store.py`'s row title) switch to `names.title`. Existing `title`s in cards/sets are left as they are; rows built
  from storage listings show the current name.

## Left to the builder

Exact cache file shape, and whether `store.py:288` needs the change (check what it builds).
