# Tags replace sets

## Intent

Sets exist to help find ROMs (never to sync a whole set). A game belongs to many groupings at once (a shmup, a
Cave game, a Best of 16-Bit pick), and sets model that badly: 46 set files hold 17,541 game entries for only
10,750 distinct games, 4,111 games sit in more than one set, and each copy repeats its title, series and
variants. Tags model it directly: a game carries any number of flat tags, each tag has an emoji, every game list
shows a game's tags as emoji, tags can be edited wherever a game is shown, and lists filter by tags.

## Goals

- Replace sets, set categories and set series with one flat list of tags. Every set, category and series
  becomes a tag (flat: "Cave inside Shmups" grouping is gone; `cave` and `shmups` are both tags).
- Store tags efficiently in one shared storage file, one record per game.
- Every tag has an emoji. Every list view that shows games shows all the game's tag emoji.
- Tags can be added to and removed from a game in every list view that shows games.
- Filter game lists by several tags: require some, exclude others.
- Suggest tags from ScreenScraper genres in the scraped metadata, reviewed before they are applied.
- Surprise can be limited to games with chosen tags.
- `sync-roms check` validates the tags file and reports games with no tags.

## Non-goals

- Tag-based collections written to cards (later, separately).
- Syncing games by tag. Tags only help find games; a card still syncs only its own picks.
- Nested or grouped tags.

## Anti-goals

- A tag ever putting games on a card by itself.
- Any real game list in the repo.
- Keeping per-game data duplicated across groupings.

## Constraints (from the project)

- Shared storage files go through `shared.py` (mirrored in `~/.sync-roms/storage/`, writes via `shared.update`,
  which re-reads storage and applies only this run's change, so machines merge).
- What storage holds is read only through `inventory.py`.
- Game keys are bucket keys (`nes/Legend of Zelda, The (USA) (Rev 1).zip`); the system follows from the key's
  folder.
- Editors name games with `names.title`.
- The one-version-per-game rule and variants stay (CLAUDE.md, "A game appears once across all sets").
- Theme art rules (CLAUDE.md "Theme art") still govern any tag art.

## Approaches

- **A. One `tags.json` at the storage root (picked).** One record per game plus the tag definitions, about
  1–1.5 MB. Read once per run; the all-games view needs all of it anyway; `shared.update` keeps merges safe.
  Every edit rewrites the whole file, fine at this size.
- **B. `tags/<system>.json` per system plus `tags/tags.json`.** Smaller writes, mirrors `scrapes/<system>/`, but
  ~60 files read per run and stitching code. Only pays off if the file grows a lot.
- Rejected: keeping the set files and calling them tags (keeps the duplication; one game's tags span many files);
  tags inside `scrapes/<system>/metadata.json` (mixes curation into scrape output that re-scrapes rewrite).

## Design

### Storage format: `tags.json` (storage root, shared)

```json
{
  "tags": {
    "shmups": {"name": "Shmups", "emoji": "🚀", "description": "...", "art": "shmups"},
    "cave":   {"name": "Cave", "emoji": "🐝"}
  },
  "games": {
    "nes/Legend of Zelda, The (USA) (Rev 1).zip": {
      "tags": ["zelda", "action-classics"],
      "variants": [{"bucket": "nes/... [T-En ...].zip", "note": "NES: fan retranslation of the script"}]
    },
    "psx/Final Fantasy VII (USA) (Disc 1).chd": {"tags": ["final-fantasy", "jrpg-essentials"],
                                                 "files": ["psx/... (Disc 2).chd", "psx/... (Disc 3).chd"]}
  },
  "declined": {"snes/Some Game (USA).sfc": ["sports"]}
}
```

- Tag id: lowercase slug, the key in `tags`. `name` and `emoji` required; `description` and `art` (an `art.json`
  id, for the tag picker's preview) optional.
- A game record: `tags` (sorted ids; may be empty only when the record has variants, so removing a game's last
  tag keeps its variants — my call), optional `files` (extra keys toggled with the game, as in
  sets), optional `variants` (as in sets). No `title` and no `system`: titles come from `names.title`, the system
  from the key. A record with no tags and no variants is removed.
- `declined`: genre suggestions the user turned down, `{key: [tag ids]}`, so they are not suggested again.
- Written sorted (tags by id, games by key), one game per line, so diffs stay readable.
- Module `tags.py` owns it: load once per run through `shared.load`, write through `shared.update` with a change
  function that applies only this run's edits (add/remove a tag on a game, tag definition edits, renames), so two
  machines editing different games merge.

### Migration (one-time, scripted)

`tools/migrate_sets_to_tags.py`, deterministic, dry by default (prints the tags it would create, merges, and
counts), `--write` to put `tags.json` in storage.

- Each set becomes a tag with the set's id, name, description and art; its emoji is the set's current emoji
  (`themeart.set_emoji`).
- Tags are pruned to roughly 150–200 so every tag has its own emoji and games carry a few each. Rules (reviewed by
  the user before `--write`): series with at least 15 games become tags; smaller series are dropped unless they
  match a kept tag; categories become tags except system names (redundant), generic qualifiers that only mean
  something inside their set ("Other", "Mainline"), and fan-translations' genre categories (genre suggestions
  cover them); names that mean the same thing merge (series "Super Mario" into set tag `mario`, "Visual Novel"
  into "Visual Novels").
- The user approved the resulting list as proposed on 2026-11-25: 206 tags (46 from sets, the rest from
  categories and series), 486 series and 44 categories pruned, including the merges of fan-translations'
  "Platformer", "Puzzle" and "Racing" categories into the Platformers, Puzzle and Racing tags.
- Every kept tag gets a unique emoji, drafted in the script's mapping table and reviewed by the user.
- A game's record is the union of the tags, `files` and `variants` from every set that lists it.
- Once `tags.json` holds every set game and every kept tag, the set files are deleted from storage (the user
  asked for it on 2026-11-25), after a local copy in `~/.sync-roms/sets-archive/` and the user's confirmation at
  that step.

### What goes away

- `sets/*.json` reading/writing, `store.load_sets` and friends, `SETS_KEY` whole-set sync (`merge_lists` set
  expansion, `games sets list|add|remove`, "Full set" cover notes, the set part of `excluded`, budget and
  cardshare set handling, `check`'s card `"sets"` validation (replaced by a notice that a leftover `"sets"` key
  is ignored). No card uses whole-set sync today.
- `sync-roms sets edit` and `setedit.py`, the `r` series filter, `data/series.json`, set categories in the
  editors.

### Editors

- **Tag column:** every game list view (card editor system list, all-games view, collection editor lists, the
  add-from-system and all-systems add lists, the surprise keep/replace list) shows the game's tag emoji as a
  column via `picker.filter_list` extras.
- **Edit tags on a row:** hotkey `t` on the highlighted game opens a checklist of all tags (emoji, name, game
  count), the game's tags checked; Space toggles, Enter saves to `tags.json`. The list ends with "New tag…"
  (asks for name and emoji; id is the slug). Saved immediately, independent of the card's own save.
- **Filter by tags:** hotkey `s` (was set filter) opens a tag list where Space cycles each tag through
  off → required (✅) → excluded (🚫). The list shows games having every required tag and none of the excluded.
  The filter line shows the active tags. `c` clears it as today.
- **Card-level tag view:** the card editor's top-level `s` (was "pick a set") opens the all-games view with a
  tag filter picked first.
- **Variants:** unchanged in behaviour (🔀 column, `v`), indexed from `tags.json` game records.
- **Tag editor:** `sync-roms tags edit` (replaces `sets edit`): list of tags with emoji, name and game count;
  per tag: rename, change emoji, description, art, view/toggle its games (add from a system or from another
  tag), merge into another tag (moves its games, deletes it), delete (removes it from every game, confirmed).

### Genre suggestions

`sync-roms tags suggest [system ...]`:

- Reads `genre` from `scrapes/<system>/metadata.json`; a repo data file `src/sync_roms/data/genre-tags.json`
  maps ScreenScraper genre strings (matched on the part before ` / `, or the full string when listed) to tag ids.
- Suggestions cover one version per game: every scraped, non-ignored ROM in storage except those that are a
  variant, an extra `files` entry, or another version (same scraped `name` on the same system) of a tagged game,
  skipping (key, tag) pairs the game already has or that are in `declined`. A suggestion may tag an untagged game.
- Review list (same toggler as other lists, grouped by suggested tag): all suggestions start checked; unchecked
  ones are saved to `declined`, checked ones are added.

### Surprise by tag

- Global setting `surprise_tags` and per-card `surprise_tags` (card editor S menu, next to excluded systems; card
  value overrides the global). When set, Surprise picks only games having any of those tags. Absent means no
  limit (today's behaviour).

### check

- `tags.json`: unknown tag ids on games, tags missing name or emoji, tags with no games, keys or variant keys not
  in storage, bad `files`.
- Notice: count of untagged games per system, over the same one-version-per-game pool genre suggestions use.
- A leftover `"sets"` key on a card is noted as ignored.

### Other code

- `bbs.retarget` renames the key in `tags.json` (games and variant buckets) instead of warning about sets.
- update-variants skill scripts read and write `tags.json` game records.
- Docs: CLAUDE.md and README sections on sets, set art, categories, series and the one-version rule are
  rewritten for tags.

## Left to the builder

- Exact module split between `tags.py`, `store.py` and the editors.
- Test layout (replace `test_sets.py`, `test_set_data.py`, `test_setedit.py` with tag equivalents).
- The migration script's mapping table contents beyond the examples, shown to the user before `--write`.
