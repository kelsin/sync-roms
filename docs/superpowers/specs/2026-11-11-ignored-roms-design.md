# Ignored ROMs and non-game review

Four parts, in this order:

1. Fix the non-game check (done: `screenscraper.is_notgame` matches any name starting with `ZZZ(NOTGAME)`, any case).
2. A shared ignore list: ROMs that stay in storage but that sync-roms never shows, syncs or scrapes.
3. Non-game review: a scrape no longer records ScreenScraper's non-game results. It lists them so the user can ignore
   each one, search ScreenScraper under another name, or leave it for later.
4. A one-time cleanup of the 221 non-game entries already in storage's scrape data.

## Why

Storage holds ROMs that aren't games: BIOS sets, test carts, demos, study software, dictionaries. ScreenScraper names
them `ZZZ(notgame):<name>`. The old check only matched the bare placeholder, so 221 of them were scraped as games
across 18 systems. The user wants to keep the files but never see them in sync-roms. ScreenScraper's flag is
sometimes wrong, though (it has real games such as Speed Buggy and Ko Punch as non-games, and it matched Jeep Jamboree
to a study cart), so nothing gets ignored without the user confirming it.

**Goals**

- An ignored ROM is invisible to sync-roms everywhere: sync, pickers, sets, collections, Surprise, budgets,
  `scrape`/`scrape --all`, upload and mirroring. Its files are never deleted from storage.
- The list is shared across machines and users of the same storage, not personal.
- New non-game results are reviewed by the user, never ignored automatically.

**Non-goals**

- No in-app way to un-ignore. The user edits `ignored.json` by hand.
- No ignore patterns or whole-system ignores. Entries are exact ROM paths.
- No change to BIOS handling. BIOS files in `BIOS/` are not ROMs and are never on the list.

**Anti-goals**

- Ignoring a ROM must never cause it to be deleted from storage, or uploaded again from a local copy.
- A real game must not get hidden without the user choosing it.

## Part 2: the ignore list

**Format.** `ignored.json` at the root of storage: `{system folder: [ROM path under that folder, ...]}`, with systems
and paths sorted. Example: `{"fbneo": ["bubsys.zip"], "nds": ["Berlitz - English Dictionary (Europe) (En,Fr,De,Es,It).zip"]}`.
The path is the same one scrape metadata uses as its key (`key.split("/", 1)[1]`).

**Local copy.** `~/.sync-roms/ignored.json` holds the last copy downloaded, plus the storage tag it had (builder's
call how: a sidecar file or a wrapper object). The tag is the file's ETag in S3, or sync-roms's "mtime-size" tag
for a storage folder.

**Refreshing it.** Once per run, the first time the list is needed, stat the storage file (one live stat, not
from the storage cache) and compare its tag with the local copy's. Download it when the tags differ or there is no
local copy. When the storage file doesn't exist, the list is empty and the local copy is removed. When storage can't
be reached, use the local copy with a warning. This read goes through `inventory.py` like every other storage read,
as a narrow function for this one file. `ignored.json` is itself ignored as a storage file: it is not a system folder,
so no system listing sees it.

**Where it applies.** `inventory.py` is the only reader of storage listings, so filter ignored ROM keys out in
`inventory.files`, `cached`, `stat` and `etags`. Everything above it (sync, pickers, sets, collections, Surprise,
budgets, scrape) then never sees them. Exceptions the builder must handle:

- **Upload** compares local files with storage. An ignored ROM must be skipped on both sides, so a local copy is
  never seen as missing from storage and uploaded again, and a storage copy is never seen as extra and removed.
- **Local mirror.** `--mirror` treats an ignored ROM like any file storage no longer lists: the next refresh deletes
  the mirror's copy (asking first above `MIRROR_PRUNE_ASK`, as today). Storage keeps its copy. No mirror-specific
  code beyond what the filtered listings already give.
- **Cards.** A ROM on a card that becomes ignored is no longer wanted, so the next sync removes it from the card as
  an extra, and removes its media the same way stale media is removed today. This is intended.
- **Sets and collections** that list an ignored ROM drop it silently, the same way a missing ROM is handled today
  (builder's call whether `--check` warns about it).
- **`cache update`** still reads all of storage. The filter applies when reading the cache, not when building it.

**Writing it.** Only the review (Part 3) and the cleanup (Part 4) write the file. A write needs the write profile,
like any other storage write. It reads the storage file fresh, merges in the new entries, writes it, then updates the
local copy and its tag, and patches the storage cache through `inventory.wrote`.

## Part 3: non-game review

**During a scrape.** When ScreenScraper's result is a non-game (`is_notgame`), record no metadata and no media.
Mark the ROM as a pending non-game in personal scrape state, alongside the unknown ledger in `scrape_state.py`
(builder's call: a new file or a reason on the ledger entry). Save what ScreenScraper returned with it: the name
without the `ZZZ(notgame):` prefix, genre, year and the first line of the description. A pending ROM is skipped by
later scrapes, the same as an unknown one, until it is reviewed.

**At the end of a run** that produced pending non-games, and only on a terminal: print the count and ask whether to
review them now. A pipe or a declined review leaves them pending.

**The review.** One ROM at a time, sorted by system then file name. Show the system, file name, size, and the saved
ScreenScraper data. Then ask:

| Key | Action |
|---|---|
| `i` | Ignore: add it to `ignored.json` (Part 2) and clear its pending mark. |
| `s` | Search: ask for a name, suggesting the file name minus its extension and bracketed tags (Enter takes the suggestion; my call, since the prompt has no editable prefill). Show ScreenScraper's results and let the user pick one, as `resolve_manual` does now. A pick saves a manual match, clears the pending mark and scrapes that ROM right away. Cancelling the pick (an empty answer there) or no results go back to this prompt. |
| `k` (default) | Keep for later: it stays pending. |
| `I` | Ignore this one and every remaining ROM in the review, after a confirmation. |

Ignores are collected and written to `ignored.json` once at the end, or when the user stops with Ctrl-C (what was
confirmed is kept).

**Later.** `sync-roms scrape review [system]` opens the same review for every pending non-game. With nothing pending
it says so and exits.

A manual match to a game ScreenScraper itself calls a non-game still fails, as it does today. Such a ROM stays
pending (or the user ignores it).

## Part 4: one-time cleanup

The 221 entries whose metadata name starts with `ZZZ(notgame)`:

- **201 clear non-games** (BIOS and board sets, tests, demos, casino/trivia, educational, apps): add them to
  `ignored.json`, then delete their metadata entries and every scraper media file they have under `scrapes/<system>/`.
- **20 possibly real or unclear** (the list below): delete their metadata entries and media, and mark them as pending
  non-games, with their saved ScreenScraper data taken from the old metadata. They then show up in
  `sync-roms scrape review`.

This runs as a one-off script against the user's storage, not as product code. It prints the exact list of files it
will delete and asks before deleting. Five fbneo BIOS entries (`decocass`, `isgsm`, `neogeo`, `pgm`, `skns`) have no
ROM in `fbneo/`. They are on the ignore list anyway, since their metadata exists, and only their metadata and media
are deleted.

The 20 to review: gb `Jeep Jamboree - Off-Road Adventure (USA).zip`; mame `spdbuggy.zip`, `kopunch.zip`,
`shdancrb.zip`; nds `General Knowledge for Dummies (Europe) (En,Fr,De).zip`; fbneo `decomult.zip`, `bace.zip`,
`dderby.zip`, `neoprimo.zip`, `nblktiger.zip`, `timesup.zip`; msx2 `Garakuta (Japan).zip`; arduboy `ArduGods (World)`,
`Arduboy Says` (both), `LoveRush` (both), `Rick and Morty Game`, `Roshambo`, `Little Rook Chess`. The full
categorized list is in the report the user has; the script recomputes it from the metadata names and these 20.

**Unknown ledger (my call).** The old check already sent non-games it caught to the unknown ledger, which records no
reason (23 entries today). The cleanup script looks each unknown up again (23 lookups) and moves the ones that come
back as non-games to pending review. The rest stay unknown.

## Starting point (my call)

`main` has moved past this branch (#229, #231). Implementation starts from current `main` and carries the Part 1
change over. Card and sync details here are re-checked against the new sync code while planning.

## Docs

Update CLAUDE.md's data-files section: `ignored.json` lives in the root of storage, is shared, is cached at
`~/.sync-roms/ignored.json` and refreshed by tag. Also note that `inventory.py` filters ignored ROMs from every listing.

## Left to the builder

- How the local copy stores its tag, and where pending non-games are stored in personal scrape state.
- How the filter is threaded through `inventory.py` (one helper applied to every listing is expected).
- How upload skips ignored ROMs.
- Prompt wording and how the review shows ScreenScraper's data.
- Tests: follow the existing `tests/` style, covering the filter in each `inventory` read, upload not re-uploading an
  ignored ROM, the tag refresh, and each review action.
