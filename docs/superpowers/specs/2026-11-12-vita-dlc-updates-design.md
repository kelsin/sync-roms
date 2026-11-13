# Vita DLC and updates

A PS Vita game synced to a card brings its DLC and newest update with it, worked out at sync time from what storage
holds. Pickers and Surprise show only the games.

## Why

Storage's `psvita/` folder holds 1,144 files: 183 games, 89 updates and 871 DLC. Today every one is its own row in the
game picker, Surprise can pick a DLC zip as a game, and a picked game arrives without its DLC or updates. The user
wants to pick a game and get all of it.

**Goals**

- A synced Vita game brings all its DLC and its newest update, on every sync, including ones added to storage after it
  was picked. This holds for every way a game gets on a card: direct picks, sets, collections and Surprise.
- The card, set and collection editors and Surprise show only games.
- Card budgets and the picker's size column count a game's DLC and update.

**Non-goals**

- No installing in Vita3K. The zips are left as they are, as today.
- No change to what's stored on cards, sets or collections: they keep listing the game key only.
- No other systems.

## Constraints

- Storage contents are only read when downloading, so a game's extras are found by file name. Every Vita file is named
  `Title [TITLEID] [Region] [tag]...zip`:
  - game: `... [PCSE00349] [USA] [NoNpDRM].zip`
  - update: `... [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip`
  - DLC: `5-Level Boost [PCSE00429] [USA] [DLC-ADDCONT049LVL000].zip` (named after the DLC, not the game)

  Each title id has exactly one game today; no DLC or update is orphaned.
- What storage holds is read only through `inventory.py`.
- Ignored ROMs stay out: the folder listing that extras come from already leaves them out.

## Approaches

- **A. One store helper (picked).** `vita.py` works out a game's extras from the folder's file names; `store.py` adds
  them where a system's sync keys are decided, so sync, the mirror and the cleanup of unwanted files see them. Budget,
  the shared row builder, Surprise, `.psvita` creation and scrape each get a small change.
- **B. At manifest load.** `merge_lists` would add extras to `s["games"]` as games: scrape would scrape them, game
  counts would include them, and every manifest load would list the Vita folder. Rejected.
- **C. Group by each zip's `param.sfo`.** Needs the file contents before downloading. Ruled out.

## Design

**`vita.py`**

- Parse a key's title id (`[PC?? + 5 digits]`) and kind from its file name: DLC (`[DLC-`), update (`[PATCH]`, version
  from `[vX.YY]`), else game.
- `extras(game_keys, folder_keys)`: for each game key, every DLC with its title id plus the update with the highest
  version. Keys that aren't games (or have no title id) get none.
- `is_extra(key)`: whether a key is a DLC or update.
- `add_psvita_files` skips extras: they have no game in them (`param.sfo` category `ac`/`gp`), so today they'd be
  reported as failures.

**Sync keys (`store.py`)**

- For the `psvita` system with a game list, the keys to sync are its listed games plus `vita.extras` of them against
  the folder's names (`inventory.files("psvita/", sizes=False)`). `list_system` stats those and `available_keys`
  returns them, so `cli.py`'s sync, `mirroring.py` and `find_extras` all include them. A full system already syncs
  every file.
- `scrape_files.py` leaves extras out: they aren't games.
- When a game leaves the card, its extras become unwanted files and are deleted with it. A newer update replaces the
  old one on the next sync.

**Budget (`budget.py`)**

- `game_costs` adds each Vita game's extras' sizes (from the size cache) to that game's cost, so the picker's size
  column and the card total include them. The game count stays games only.
- The download-size preview (`fetch_bytes`) counts the extras too.

**Pickers and Surprise**

- `edit.system_rows` (card, set and collection editors) leaves out extras that aren't listed. Listed ones stay so they
  can be switched off.
- A game with extras shows `🔗 N files` in the card editor, like a multi-disc game.
- `surprise.units` leaves out extras. Picking a game is enough: sync adds its extras.

**Every layout**

- Extras sync wherever the system has a folder (ES-DE, Knulli, EmuDeck). `.psvita` files are still only made on ES-DE
  and EmuDeck.

**README**

- The Vita paragraph says a game's DLC and newest update are synced with it.

## Calls made (the user can change these)

- Newest update only, not every version: Vita updates contain the earlier ones.
- Extras sync on every layout with a Vita folder.
- The `🔗 N files` badge for games with extras.

## Left to the builder

- Function names and where in `store.py` the helper sits.
- How extras of a game the card excludes are handled (they follow the game: not synced).
- Tests: `vita.extras` parsing (DLC, multiple updates, no title id, non-game keys), sync keys for a Vita card, budget
  costs including extras, rows and Surprise units without extras, `.psvita` creation skipping extras.
