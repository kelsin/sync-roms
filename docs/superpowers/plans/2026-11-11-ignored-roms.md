# Ignored ROMs and Non-Game Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A shared `ignored.json` in storage hides non-game ROMs from every part of sync-roms. Scrapes stop recording
ScreenScraper non-game results and let the user review them instead. A one-off script cleans up the 221 existing entries.

**Architecture:** A new `ignore.py` owns the list: it refreshes the local copy by storage tag once per run, answers
`is_ignored(key)`, and merges new entries in. `inventory.py` and `store.listed` filter ignored keys, so everything
above them stops seeing those ROMs. Upload filters its local side. Scrapes record non-games as pending in
`scrape_state.py`, and a new `scrape_review.py` runs the review at the end of a scrape and from `scrape review`.

**Tech Stack:** Python 3.11+, stdlib `unittest`, boto3/botocore (existing).

**Spec:** `docs/superpowers/specs/2026-11-11-ignored-roms-design.md`

## Global Constraints

- Conventional Commits, imperative and lowercase (e.g. `feat(scrape): ...`).
- Never delete ROM files from storage.
- Storage reads go through `inventory.py`. The ignore list's single-file stat is a new `inventory` function.
- The storage key is `ignored.json` at the root of storage. The local copy is `os.path.join(store.data_dir(), "ignored.json")`.
- Pending non-games are personal: `os.path.join(store.data_dir(), "scrape-notgames.json")`.
- Run tests with: `uv run --python 3.12 --with-editable . --with Pillow python -m unittest discover -s tests`
  (the local default Python is 3.10, which CI doesn't test).
- No test may reach real storage for the ignore list. `tests/isolate.py` preloads an empty list (Task 2).

## Review Focus

1. **Upload with an ignored ROM in the local folder** must not upload it or count it as new. Test in Task 4.
2. **A card or set listing an ignored ROM** drops it silently, with no "missing ROM(s)" warning. Test in Task 3.
3. **Storage unreachable, or `ignored.json` missing, at start**: use the local copy with one warning, or an empty
   list when storage has no file. Never crash. Test in Task 2.
4. **Ctrl-C or EOF partway through a review** keeps the ignores already chosen. Test in Task 6.
5. **A `--retry` scrape** must not look up pending non-games again. Test in Task 5.

---

### Task 1: Commit the non-game check fix

**Files:**
- Modify: `src/sync_roms/screenscraper.py`, `tests/test_screenscraper.py` (already changed, uncommitted)
- Add: `docs/superpowers/specs/2026-11-11-ignored-roms-design.md`, this plan

- [ ] **Step 1:** Run the suite. Expected: `OK`.
- [ ] **Step 2: Commit**

```bash
git add src/sync_roms/screenscraper.py tests/test_screenscraper.py docs/superpowers/specs/2026-11-11-ignored-roms-design.md docs/superpowers/plans/2026-11-11-ignored-roms.md
git commit -m "fix(scrape): treat any ZZZ(notgame) name as a non-game"
```

### Task 2: The ignore list (`ignore.py`)

**Files:**
- Create: `src/sync_roms/ignore.py`
- Modify: `src/sync_roms/inventory.py` (add `tag`), `tests/isolate.py` (preload empty)
- Test: `tests/test_ignore.py`

**Interfaces:**
- Produces:
  - `inventory.tag(key: str) -> str | None`: a live stat of one storage file, never the cache. For S3 it returns
    `head_object(...)["ETag"]` (None on a 404 `ClientError`). For a storage folder it returns
    `f"{st.st_mtime_ns}-{st.st_size}"` from `os.stat(s3.safe_join(runtime.ROOT, key))` (None on `FileNotFoundError`).
    It reads `runtime.ROOT`, never the mirror. Other `s3.ERRORS` propagate.
  - `ignore.KEY = "ignored.json"`
  - `ignore.keys() -> frozenset[str]`: full keys (`"system/rom path"`), loaded once per run (cached in `ignore._keys`).
  - `ignore.is_ignored(key: str) -> bool`
  - `ignore._read() -> str`: the storage file's text, from real storage and never the local mirror
    (`s3.get_text` reads the mirror when one is in use). Open `s3.safe_join(runtime.ROOT, KEY)` when `runtime.ROOT`
    is set, else `s3.s3_client().get_object(Bucket=runtime.BUCKET, Key=KEY)`.
  - `ignore.add(entries: dict[str, list[str]]) -> int`: merges entries into the storage file, read fresh with
    `_read()` (missing means `{}`), sorted systems and sorted paths. Writes with `s3.put_text`, then refreshes the
    local copy and `_keys`. Returns how many were new.
  - `ignore.reset()`: sets `_keys = None`, so the next `keys()` loads again.
- Local copy format: `{"tag": str, "ignored": {system: [paths]}}`.

**The load (`keys()` when `_keys is None`):**
- Get `t = inventory.tag(KEY)`. On `s3.ERRORS`, use the local copy, warn once with `ui.warn` ("Couldn't check
  ignored.json in storage (...); using the local copy"), and use an empty list if there is no local copy.
- If `t is None`, delete the local copy if one exists and use an empty list.
- If `t` equals the local copy's `"tag"`, use the local copy.
- Otherwise, `json.loads(_read())`, write the local copy with the new tag, and use that. Invalid JSON in
  storage: warn and fall back the same way as on an error.
- Skip malformed parts (a value that isn't a list, a path that isn't a string). Never raise from `keys()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ignore.py`. The class uses the `StorageFolder` pattern from
  `tests/test_inventory.py` (ROOT is a temp folder, DataDir for the local copy), calls `ignore.reset()` in `setUp`,
  and adds a cleanup that restores `ignore._keys = frozenset()`.
  - `test_no_file_in_storage_means_nothing_ignored`: `ignore.keys() == frozenset()`, and no local copy is written.
  - `test_reads_storage_file_and_saves_local_copy`: put `ignored.json` = `{"fbneo": ["bubsys.zip"]}`. Then
    `ignore.is_ignored("fbneo/bubsys.zip")` is true, `ignore.is_ignored("fbneo/sf2.zip")` is false, and the local
    copy's `"ignored"` equals the storage content.
  - `test_reads_storage_not_mirror`: with `runtime._mirror_root` set to an empty folder, `keys()` still reads the
    storage file.
  - `test_same_tag_uses_local_copy`: after a first load, patch `ignore._read` to raise. `ignore.reset()` then `keys()`
    still works, and `_read` is not called.
  - `test_changed_file_is_downloaded_again`: rewrite the storage file with different content of the **same length**
    and bump its mtime (`os.utime`). After `reset()`, `keys()` reflects the new content.
  - `test_storage_error_falls_back_to_local_copy_with_warning`: patch `inventory.tag` to raise `OSError`. `keys()`
    returns the local copy's keys, and the output has one warning.
  - `test_storage_file_removed_drops_local_copy`.
  - `test_add_merges_sorted_and_counts_new`: storage has `{"nds": ["b.zip"]}`. `ignore.add({"nds": ["a.zip", "b.zip"], "gb": ["c.zip"]})`
    returns 2, the storage file is `{"gb": ["c.zip"], "nds": ["a.zip", "b.zip"]}`, and `is_ignored("nds/a.zip")` is true.
  - `test_tag_for_folder_changes_with_content` (in this file, for `inventory.tag`), and `test_tag_missing_is_none`.
- [ ] **Step 2: Run** `... python -m unittest tests.test_ignore`. Expected: FAIL (`No module named sync_roms.ignore`).
- [ ] **Step 3: Implement** `inventory.tag` and `ignore.py` as specified above. Use `store.write_json` for the local copy.
- [ ] **Step 4:** In `tests/isolate.py`, after `from sync_roms import store`, add `from sync_roms import ignore` and
  `ignore._keys = frozenset()` with a comment: no test reads the ignore list from storage unless it calls `ignore.reset()`.
- [ ] **Step 5: Run** the new tests and then the full suite. Expected: `OK`.
- [ ] **Step 6: Commit** `feat(ignore): add a shared ignore list in storage`

### Task 3: Filter ignored ROMs from every listing

**Files:**
- Modify: `src/sync_roms/inventory.py` (`files`, `cached`, `stat`, `etags`), `src/sync_roms/store.py` (`listed`)
- Test: `tests/test_inventory.py`, `tests/test_sync_flow.py` (or the closest existing sync test file)

**Interfaces:**
- Consumes: `ignore.keys()`, `ignore.is_ignored(key)` (Task 2).
- Produces: `inventory._unignored(listing: dict) -> dict`, which drops keys in `ignore.keys()`. It's a no-op when the
  set is empty. `etags` filters on `prefix + path`, since its keys are relative to the prefix.

- [ ] **Step 1: Write the failing tests** (patch `ignore._keys = frozenset({"gba/b.zip"})` in each):
  - In `tests/test_inventory.py`, `IgnoredTest(StorageFolder)` runs every case both with a built cache and without one:
    - `test_files_drops_ignored`: `inventory.files("gba/") == {"gba/a.zip": 1}`.
    - `test_cached_drops_ignored`, `test_stat_drops_ignored` (`inventory.stat(["gba/a.zip", "gba/b.zip"])` keeps only a).
    - `test_etags_drops_ignored`: `"b.zip" not in inventory.etags("gba/")`.
    - `test_cache_file_still_holds_ignored`: after `build()`, the saved `storage-cache.json` `files` still has `gba/b.zip`.
  - `test_listed_drops_ignored`: `store.listed({"games": [{"bucket": "gba/a.zip"}, {"bucket": "gba/b.zip"}]}) == ["gba/a.zip"]`.
  - In the sync flow tests, `test_ignored_listed_game_is_not_reported_missing`: a card lists `gba/b.zip`, which is
    ignored. Sync output has no "missing" line for it and downloads nothing for it.
  - A collections test: a collection naming an ignored ROM doesn't put it on the card. Find where collection games
    become keys. If that path doesn't go through `store.listed`, filter there too.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `_unignored` and apply it to the four reads, live and cached. In `store.listed`, drop
  keys where `ignore.is_ignored(key)`.
- [ ] **Step 4: Run** the full suite. Expected: `OK`.
- [ ] **Step 5: Commit** `feat(ignore): hide ignored ROMs from every storage listing`

### Task 4: Upload skips ignored ROMs

**Files:**
- Modify: `src/sync_roms/upload.py` (`plan_rom_upload`, `replace_command`)
- Test: `tests/test_upload.py`

- [ ] **Step 1: Write the failing tests:**
  - `test_plan_rom_upload_skips_ignored`: the local folder has `a.zip` and `b.zip`, storage has neither, and
    `gba/b.zip` is ignored. `new` holds only `gba/a.zip`.
  - `test_replace_never_deletes_or_uploads_ignored`: storage has `gba/b.zip` and the local folder doesn't, with
    `gba/b.zip` ignored. The delete list is empty. Then the reverse case: local has it and storage doesn't, so it's
    not uploaded.
- [ ] **Step 2: Run** them. Expected: FAIL on the upload case (the storage side is already filtered by Task 3).
- [ ] **Step 3: Implement.** In `plan_rom_upload`, skip paths whose key `ignore.is_ignored(key)`. In
  `replace_command`, drop ignored paths from `local` before `diff.plan_replace`.
- [ ] **Step 4: Run** the full suite. Expected: `OK`.
- [ ] **Step 5: Commit** `feat(ignore): never upload or delete ignored ROMs`

### Task 5: Scrapes record non-games as pending

**Files:**
- Modify: `src/sync_roms/screenscraper.py`, `src/sync_roms/scrape_state.py`, `src/sync_roms/scrape_online.py`
  (`scrape_rom`, `run_batch`, `find_candidates`)
- Test: `tests/test_screenscraper.py`, `tests/test_scrape_state.py`, `tests/test_scrape_run.py`

**Interfaces:**
- Produces:
  - `screenscraper.notgame_info(raw) -> dict` with keys `name` (the name with the `ZZZ(notgame)` prefix removed, and
    the `:` and whitespace after it stripped), `genre`, `year` (the first 4 characters of the release date) and
    `desc` (the description's first line, at most 200 characters). Missing fields are `""`. Refactor `parse_game` so
    both share the field parsing (`parse_game` still returns `({}, {})` for a non-game).
  - `scrape_state.NOTGAMES = "scrape-notgames.json"` → `{"system/rom": info}`.
  - `scrape_state.mark_notgame(system, rom, info: dict)`, `scrape_state.clear_notgame(system, rom)`,
    `scrape_state.notgames() -> dict[str, dict]` (a copy). Each one is written right away, under `_lock`.
  - `_Snapshot.is_notgame(system, rom) -> bool`.
  - `scrape_rom` returns `("notgame", (how, info))` for a non-game. It no longer returns `("unknown", (how, "notgame"))`.

- [ ] **Step 1: Write the failing tests:**
  - `test_notgame_info`: for `noms` = `ZZZ(notgame):Bubble System Bios`, genre `Various / System` and date
    `1985-01-01`, the result is `{"name": "Bubble System Bios", "genre": "Various / System", "year": "1985", "desc": ""}`.
    A bare `ZZZ(NOTGAME)` name gives `name == ""`.
  - `test_mark_and_clear_notgame` (`tests/test_scrape_state.py`): survives a reload, and `notgames()` returns the info.
  - Update `test_notgame_result_is_unknown_and_writes_nothing` in `tests/test_scrape_run.py` and rename it
    `test_notgame_result_is_pending_and_writes_nothing`. The ROM is in `scrape_state.notgames()` with its info, not in
    the unknown ledger, and no metadata or media is written.
  - `test_forced_notgame_is_a_failure_with_its_own_message` keeps passing unchanged.
  - `test_pending_notgame_not_looked_up_again_even_with_retry`: `find_candidates(..., retry=True)` leaves out a ROM
    marked pending.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** In `run_batch`, a `"notgame"` status for a ROM in `forced` keeps today's failure message.
  Otherwise call `scrape_state.mark_notgame(name, rom, info)`, set `outcomes[rom] = None`, and print
  `ui.dim(f"     🚫 {name}/{rom}: ScreenScraper lists it as a non-game")`. `find_candidates` leaves out
  `state.is_notgame(system, r)` whatever `retry` is.
- [ ] **Step 4: Run** the full suite. Expected: `OK`.
- [ ] **Step 5: Commit** `feat(scrape): keep non-game results for review instead of recording them`

### Task 6: The review (`scrape_review.py`)

**Files:**
- Create: `src/sync_roms/scrape_review.py`
- Test: `tests/test_scrape_review.py`

**Interfaces:**
- Consumes: `scrape_state.notgames/clear_notgame`, `ignore.add`, `scrape_online.resolve_manual`,
  `scrape_online.match_command`, `scrape_online.make_client`, `scrape_online._RomClient`.
- Produces:
  - `search_name(rom: str) -> str`: the file name without its extension and without `(...)`/`[...]` groups,
    whitespace collapsed. `"Jeep Jamboree - Off-Road Adventure (USA).zip"` gives `"Jeep Jamboree - Off-Road Adventure"`.
  - `review(systems: dict[str, dict], keys: list[str], sizes: dict[str, int], client=None) -> int`: the interactive
    loop over `keys` (sorted by system, then ROM). It returns 0. It creates `client` with `make_client()` on the first
    search only.
  - `review_command(args) -> int` (`args.system`: a storage folder name or `""`/None for all).

**One ROM's screen:** `system/rom  size`, then `ScreenScraper: <name> · <genre> · <year>` (skipping empty parts),
then the description on a dim line if there is one. Prompt: `[i]gnore · [s]earch · [k]eep for later · [I]gnore all the rest  (k): `.
- `i`: queue `(system, rom)` for ignore.
- `s`: ask `Search name [<search_name>]: `, where an empty answer uses the suggestion. Then
  `game_id = resolve_manual(_RomClient(client), system, query)`. If that raises `NotFound` (no results or cancelled),
  print why and show the same ROM's prompt again. On a pick, call
  `match_command(argparse.Namespace(system=name, rom=rom, game=str(game_id), skip_media=None, dry_run=False))`.
  When `scrape_state.manual_match(name, rom) == game_id` afterwards, call `clear_notgame` and move to the next ROM.
  Otherwise show the same ROM's prompt again.
- `k` or an empty answer: move on, leaving it pending.
- `I`: `ui.confirm(f"Ignore this and the {n} remaining ROM(s)?", default=False)`. On yes, queue them all and stop.
- Any other answer: show the prompt again.
- A `try/finally` around the loop: when the queue isn't empty, `ignore.add` the queued ROMs, `clear_notgame` each
  one, and print `🙈 Ignored N ROM(s)`. `KeyboardInterrupt` and EOF (`ui.ask` returns `""` on EOF, which counts as
  `k`, so EOF just runs out the list) still write the queue.

`review_command`: on a non-terminal, `ui.fail("scrape review needs a terminal", 2)`. Otherwise take the pending keys
from `scrape_state.notgames()`, filtered to `args.system` when it's given. With none, print
`ui.green("No non-game results to review ✨")` and return 0. Sizes come from `inventory.stat(keys)`. A key whose ROM is
gone from storage or already ignored gets `clear_notgame` and is skipped. Then call `review`.

- [ ] **Step 1: Write the failing tests** (patch `ui.ask`/`ui.confirm` with scripted answers, `ignore.add` with a
  recorder, `match_command`, and the client):
  - `test_search_name_strips_tags_and_extension`, with the Jeep Jamboree example and `"Game [b] (Rev 1).7z"` → `"Game"`.
  - `test_ignore_one_keep_one`: answers `i`, then `k`. `ignore.add` is called once with the first ROM only, the first is
    no longer pending, and the second still is.
  - `test_ignore_all_rest_after_confirm`: answers `I`, then confirm yes. Every ROM is added.
  - `test_search_pick_scrapes_and_clears`: answers `s`, then `""` (use the suggestion). `resolve_manual` returns 42,
    `match_command` gets `game="42"`, and the fake saves the match. The ROM is no longer pending.
  - `test_search_cancel_returns_to_prompt`: `resolve_manual` raises `NotFound("cancelled")`, then the answer is `k`.
    Nothing is ignored, and the ROM is still pending.
  - `test_ctrl_c_keeps_chosen_ignores`: answers `i`, then `ui.ask` raises `KeyboardInterrupt`. `ignore.add` was called
    with the first ROM, and the `KeyboardInterrupt` propagates.
  - `test_review_command_nothing_pending`, `test_review_command_needs_a_terminal`,
    `test_review_command_skips_gone_or_ignored`.
- [ ] **Step 2: Run** them. Expected: FAIL (`No module named sync_roms.scrape_review`).
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the full suite. Expected: `OK`.
- [ ] **Step 5: Commit** `feat(scrape): review non-game results to ignore or match them`

### Task 7: Wire the review into scrapes and the CLI, plus docs

**Files:**
- Modify: `src/sync_roms/scrape_online.py` (`run_scrape`), `src/sync_roms/cli.py` (the `--scrape-review` flag,
  `LEGACY`, `check_modes`, dispatch, `SUBCOMMANDS` usage for `scrape`), `README.md`, `CLAUDE.md`
- Test: `tests/test_scrape_cli.py`, `tests/test_scrape_run.py`, `tests/test_readme.py` (must keep passing)

**Interfaces:**
- CLI: `sync-roms scrape review [SYSTEM]` translates to `--scrape-review [SYSTEM]`
  (`ap.add_argument("--scrape-review", nargs="?", const="")`). `LEGACY[("scrape", "review")] = ["--scrape-review"]`,
  placed before `("scrape",)`. `check_modes` counts it as a mode (`args.scrape_review is not None`). Dispatch: after
  `inventory.prepare()`, set `args.system = args.scrape_review or None` and return `scrape_review.review_command(args)`.
- `run_scrape`: record `before = set(scrape_state.notgames())` at the start. After the results report and before the
  return, compute `new = sorted(set(scrape_state.notgames()) - before)`. If `new` and `sys.stdin.isatty()`, print
  `🚫 N ROM(s) came back as non-games` and `ui.confirm("Review them now?", default=True)`. On yes, call
  `scrape_review.review(systems, new, sizes, client)`, with sizes from the `todo` items. On a pipe, or on no, print
  `ui.dim("   Review them later with: sync-roms scrape review")`. The return code doesn't change.

- [ ] **Step 1: Write the failing tests:**
  - `test_scrape_review_subcommand_translates` (in the existing `translate` tests' style):
    `["scrape", "review", "nds"]` gives `["--scrape-review", "nds"]`, and `["scrape", "review"]` gives `["--scrape-review"]`.
  - `test_scrape_review_conflicts_with_other_modes`: `--scrape --scrape-review` exits with code 2.
  - `test_run_scrape_offers_review_on_tty`: a non-game result, with isatty patched true and confirm yes, calls
    `scrape_review.review` once with that key.
  - `test_run_scrape_on_pipe_prints_hint`: with isatty false, `review` isn't called and the output has `sync-roms scrape review`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the CLI and `run_scrape` changes.
- [ ] **Step 4: Docs.** In `README.md`, add an options-table row for `--scrape-review [SYSTEM]` (`test_readme` checks
  the table against the parser) and a short "Non-games" paragraph in the scraping section covering pending results,
  the review keys, `scrape review`, and `ignored.json` in storage being shared and edited by hand to un-ignore. In
  `CLAUDE.md`'s data-files section, add `ignored.json`: it lives at the root of storage, is shared, is cached at
  `~/.sync-roms/ignored.json`, and is refreshed by storage tag. `inventory.py` and `store.listed` filter ignored ROMs
  out of everything. Also list `scrape-notgames.json` among the personal files.
- [ ] **Step 5: Run** the full suite. Expected: `OK`.
- [ ] **Step 6: Commit** `feat(scrape): offer the non-game review after a scrape and as scrape review`

### Task 8: One-time cleanup of the 221 existing entries (not committed)

Run this after Tasks 1–7 have landed. The script lives in the session scratchpad. It touches the user's storage, so
every destructive step waits for the user's go-ahead in chat as well as the script's own prompt.

**Script** `cleanup_notgames.py`, run with `uv run --python 3.12 --with-editable <repo> python -I cleanup_notgames.py [--apply]`:
- Hard-code the 20 review keys from the spec's Part 4 list. Match the Arduboy entries by file-name prefix, and assert
  exactly 20 are found.
- For each system with a `scrapes/<system>/metadata.json` (via `scrape_online.load_metadata`), find the entries whose
  `name` uppercased starts with `ZZZ(NOTGAME)`. Assert there are 221 in total.
- Media to delete: `scrape_online._media_keys(inventory.files(f"scrapes/{system}/"), system, stem)`, keeping types in
  `scrape_online.SCRAPER_TYPES`.
- Without `--apply`: write the full list (ignore entries, review entries, metadata entries and media keys) to a text
  file next to the script, and print the counts. Delete nothing.
- With `--apply`: `ignore.add` the 201. For each of the 20, `scrape_state.mark_notgame` with info built from the old
  entry (the name with its prefix stripped, `genre`, `releasedate[:4]`, the first line of `desc`). Then write each
  changed `metadata.json` without the 221 entries (`s3.put_text(scrape_online.metadata_key(system),
  scrape_plan.dump_json(data))`), call `s3.delete_keys(media)`, and `inventory.flush()`.
- Unknown ledger: for the keys in `scrape-unknown.json` (23 today), clear each from the ledger. Build `todo` from
  `inventory.etags(f"{system}/")` and call `scrape_online.run_scrape(make_client(), systems, todo, set())` with its
  own confirm. Non-games among them become pending, and the review offer follows.

- [ ] **Step 1:** Write the script, then run it without `--apply`. Send the user the list file.
- [ ] **Step 2:** After the user approves in chat, run it with `--apply`. Expected: 201 ignored, 20 pending, 221
  metadata entries removed, and the media count matching the list.
- [ ] **Step 3:** Verify. Run `sync-roms scrape review` and check that the 20 are listed (quit with `k`). Spot-check
  that `inventory.files("fbneo/")` has no `bubsys.zip`.
