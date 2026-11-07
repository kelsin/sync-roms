# ScreenScraper Scrape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms scrape` finds available ROMs with no scrape metadata, scrapes them from ScreenScraper on the computer, and uploads the results to `scrapes/` in the bucket or storage folder, where sync already installs them.

**Architecture:** A new `screenscraper.py` is a thin API client with pure parsing functions. A new `scrape_online.py` finds candidates, matches (hash from a storage folder, ETag MD5 or name+size on S3, saved manual matches), downloads media to a temp dir in batches, then reuses `upload.run_uploads` (including its Onion/Slot `shrink` jobs) and `scrape_plan.merge_metadata` + `s3.put_text`. A small `scrape_state.py` holds the user's local state in `~/.sync-roms/`.

**Tech Stack:** Python 3.9+, stdlib `urllib`/`hashlib`/`zlib` (no new dependency), `unittest` (tests live in `tests/`, run with `python -m unittest`).

**Spec:** `docs/superpowers/specs/2026-11-03-screenscraper-scrape-design.md`

## Global Constraints

- Work on a new branch off `main` (e.g. `kelsin/screenscraper-scrape`); `main` already has folder storage (`runtime.ROOT`, #100).
- Conventional Commits, imperative, lowercase. No AI attribution in commits or PR text.
- Output formats are the existing ones: `scrapes/<system>/metadata.json` keyed by ROM path **with** extension; media at `scrapes/<system>/<type>/<ROM path without extension>.<ext>` using `scrape_plan.MEDIA_TYPES` folder names; derived `onion/` and `slot/` PNGs via `upload.run_uploads` 4-tuples `(key, path, size, (max w, max h))`.
- Reads use `s3.*` (honoring `runtime.ROOT`/mirror); writes use the write profile (`s3.put_text`, `upload.run_uploads`). One confirmation per run before writing; `--dry-run` writes nothing.
- Credentials (ScreenScraper user/password, dev id/password) live only in `~/.sync-roms/settings.json` (mode 600), never in the repo, bucket, logs or output.
- Never download whole ROMs from S3 to hash them; hashing happens only when `s3.read_root()` is set.
- Personal state (hash cache, manual matches, unknown ledger) lives in `store.data_dir()`; repo files carry no notes about bucket contents.
- Name+size matches are trusted and reported separately.
- Media types default to all on, each switchable off.

## Review Focus

- A ROM already in `metadata.json` is never re-scraped or overwritten (re-run is a no-op).
- Interrupt or quota stop mid-run: everything uploaded so far is complete (media before its metadata entry), and a re-run continues.
- ROMs in subfolders (`Disc 1/game.cue`), multi-disc/`.m3u` and ROMs with dots in the name keep correct keys and stems.
- ScreenScraper returns "not found", an empty media list, HTTP 429/430/431 or a malformed body: the ROM is recorded (not found) or retried later, nothing crashes, no partial entry.
- `settings.json` that is missing, unreadable or not a dict still loads as `{}` and is not made world-readable.

---

### Task 1: Verify the ScreenScraper API contract

**Files:**
- Create: `docs/superpowers/notes/screenscraper-api.md`
- Create: `tests/fixtures/screenscraper/` (saved sample responses)

**Interfaces:**
- Produces: a notes file stating, from ScreenScraper's current docs, the facts later tasks rely on.

- [ ] **Step 1:** Read ScreenScraper's API documentation (api2 `jeuInfos.php`, `ssuserInfos.php`, `systemesListe.php`). Record in the notes file: whether developer credentials (devid, devpassword, softname) are required beyond the user's login and how to obtain them; the lookup parameters (`systemeid`, `romnom`, `romtaille`, `md5`, `sha1`, `crc`, `gameid`); which hash a zip or CHD is matched by; the response field paths for names/description/dates/genres/players/rating; the media `type` strings and which ES-DE folder each maps to (expected: `box-2D`→covers, `box-3D`→3dboxes, `box-2D-back`→backcovers, `ss`→screenshots, `sstitle`→titlescreens, `marquee`→marquees, `video`→videos, `manuel`→manuals, `fanart`→fanart, `support-2D`→physicalmedia, `mixrbv1`/`mixrbv2`→miximages; confirm or correct); region/language fallback order; the quota fields (`maxthreads`, `maxrequestsperday`, `requeststoday` or their real names); and the HTTP codes for not found and quota exceeded.
- [ ] **Step 2:** If developer credentials are required, stop and tell the user what to request from ScreenScraper before continuing; the user's answer decides settings names in Task 2.
- [ ] **Step 3:** Save one real (credential-free) response each for a found game, a not-found game and the quota endpoint under `tests/fixtures/screenscraper/`. If no live call is possible, hand-write fixtures from the documented shape and say so in the notes.
- [ ] **Step 4:** Commit the spec, this plan, the notes and fixtures: `git add docs tests/fixtures && git commit -m "docs: add screenscraper scrape design, plan and api notes"`

### Task 2: Settings file permissions and ScreenScraper credentials

**Files:**
- Modify: `src/sync_roms/usersettings.py` (`load_settings`, `save_setting`)
- Test: `tests/test_settings_permissions.py`

**Interfaces:**
- Produces: `load_settings()` ensures `settings.json` mode is `0o600` on every successful read; `save_setting` creates/replaces it as `0o600`. New saved keys `screenscraper_user`, `screenscraper_password` (plus the dev credential keys Task 1 requires), read by Task 5 via `load_settings()`; not part of `SETTINGS`/`resolve_settings`, not echoed by `config show`.

- [ ] **Step 1: Write failing tests** (temp `store.data_dir` patched): `test_load_fixes_loose_mode` (file written 0o644 → after `load_settings()` mode is `0o600`), `test_save_creates_600` (fresh `save_setting("bucket","b")` → mode `0o600`), `test_load_missing_or_bad_json_is_empty_and_does_not_create_file`, `test_config_show_hides_credentials` (output has no password value).
- [ ] **Step 2:** Run `python -m unittest tests.test_settings_permissions -v`; expect FAIL.
- [ ] **Step 3:** Implement: `os.chmod(path, 0o600)` after a successful open/parse when `stat.S_IMODE` differs (ignore `OSError`); in `save_setting` write via `os.open(..., 0o600)` then chmod. Skip chmod on `win32`.
- [ ] **Step 4:** Run the new tests plus `python -m unittest discover tests`; expect PASS.
- [ ] **Step 5:** Commit: `feat(settings): keep settings.json at mode 600`

### Task 3: ScreenScraper client and response parsing

**Files:**
- Create: `src/sync_roms/screenscraper.py`
- Test: `tests/test_screenscraper.py` (uses Task 1 fixtures)

**Interfaces:**
- Produces:
  - `class Quota(NamedTuple): max_threads: int; used_today: int; max_today: int`
  - `class NotFound(Exception)`, `class QuotaExceeded(Exception)`, `class ApiError(Exception)`
  - `class Client(user: str, password: str, dev: dict, opener=urllib.request.urlopen)` with `quota() -> Quota`, `lookup(system_id: int, rom_name: str, size: int, md5: str|None=None, sha1: str|None=None, crc: str|None=None) -> dict`, `game(game_id: int) -> dict`, `search(system_id: int, name: str) -> list[tuple[int, str]]`, `download(url: str, dest: str) -> None`
  - `parse_game(raw: dict, regions: tuple[str, ...]) -> tuple[dict, dict[str, str]]` → `(metadata fields as parse_gamelist produces: name, desc, developer, publisher, genre, players, rating 0-1, releasedate ISO; {ES-DE media type folder: url})`
  - `MEDIA_MAP: dict[str, str]` ScreenScraper media type → `scrape_plan.MEDIA_TYPES` name

- [ ] **Step 1: Write failing tests:** `test_parse_game_maps_fields` (fixture → exact expected fields), `test_parse_game_maps_media_types_and_prefers_region`, `test_lookup_not_found_raises` (fixture/HTTP code from Task 1), `test_lookup_quota_raises_quota_exceeded`, `test_quota_parse`, `test_password_never_in_error_text` (a failing request's exception message doesn't contain the password).
- [ ] **Step 2:** Run `python -m unittest tests.test_screenscraper -v`; expect FAIL.
- [ ] **Step 3:** Implement with `urllib` and an injectable `opener` so tests pass fixtures; add a `User-Agent` of `sync-roms/<version>`; build query strings with `urllib.parse.urlencode`; map media with `MEDIA_MAP`, dropping types not in `scrape_plan.MEDIA_TYPES`; `download` writes to `dest + ".part"` then `os.replace`.
- [ ] **Step 4:** Run the tests; expect PASS.
- [ ] **Step 5:** Commit: `feat(scrape): add screenscraper api client`

### Task 4: Local scrape state (hash cache, manual matches, unknown ledger)

**Files:**
- Create: `src/sync_roms/scrape_state.py`
- Test: `tests/test_scrape_state.py`

**Interfaces:**
- Produces (all under `store.data_dir()`, JSON via `scrape_plan.dump_json`, tolerant of missing/corrupt files → empty):
  - `cached_hashes(system: str, rom: str, size: int, mtime: int) -> dict|None` and `save_hashes(system, rom, size, mtime, hashes: dict) -> None` (`{"md5","sha1","crc"}`)
  - `manual_match(system: str, rom: str) -> int|None` and `save_match(system, rom, game_id: int) -> None`
  - `is_unknown(system, rom) -> bool`, `mark_unknown(system, rom) -> None`, `clear_unknown(system: str|None=None) -> None`

- [ ] **Step 1: Write failing tests** with a temp data dir: round-trips for each function, `test_hash_cache_misses_when_size_or_mtime_changes`, `test_corrupt_file_reads_as_empty`, `test_clear_unknown_one_system_only`.
- [ ] **Step 2:** Run `python -m unittest tests.test_scrape_state -v`; expect FAIL.
- [ ] **Step 3:** Implement; ROM identity is `system + "/" + ROM path`; write atomically (`.tmp` then `os.replace`).
- [ ] **Step 4:** Run the tests; expect PASS.
- [ ] **Step 5:** Commit: `feat(scrape): keep scrape matches and hashes in the user data folder`

### Task 5: Candidates, hashing and matching

**Files:**
- Create: `src/sync_roms/scrape_online.py` (candidates/matching part)
- Test: `tests/test_scrape_match.py`

**Interfaces:**
- Consumes: `scrape_files.bucket_roms(systems) -> {bucket folder: {ROM path}}`, `s3.list_with_etags(prefix) -> {path: (size, etag)}`, `s3.read_range`, `s3.read_root()`, `scrape_state.*`, `screenscraper.Client`.
- Produces:
  - `find_candidates(systems: list[dict], roms: dict, metadata: dict[str, dict]) -> dict[str, list[str]]` → per system folder, available ROM paths with no key in that system's `metadata.json` (skipping `scrape_state.is_unknown` unless `retry=True` parameter), sorted.
  - `hash_file(system: str, rom: str, size: int, mtime: int) -> dict` → `{"md5","sha1","crc"}`; reads in 8 MiB chunks via `s3.read_range`; uses/updates the cache; only called when `s3.read_root()`.
  - `match(client, system: dict, rom: str, size: int, etag: str) -> tuple[int, str]` → `(game_id, how)` with `how` in `"manual"|"hash"|"name+size"`; order: saved manual match; folder → computed hashes; S3 → ETag as MD5 only when it has no `-`; then `client.lookup` by name+size; raises `screenscraper.NotFound`.
  - `resolve_manual(client, system: dict, query: str) -> int` → an integer string is a game id; otherwise `client.search` and an interactive pick via `ui` prompts.

- [ ] **Step 1: Write failing tests** with a fake client recording calls: `test_candidates_exclude_rom_with_metadata`, `test_candidates_skip_unknown_unless_retry`, `test_subfolder_rom_key_kept` (`Disc 1/a.cue`), `test_folder_backend_hashes_file_and_caches` (second call doesn't read the file), `test_s3_uses_etag_md5_only_when_single_part`, `test_s3_multipart_etag_falls_back_to_name_size`, `test_folder_never_uses_fake_etag`, `test_manual_match_wins`, `test_name_size_match_is_labelled`, `test_s3_never_calls_read_range_for_hashing`.
- [ ] **Step 2:** Run `python -m unittest tests.test_scrape_match -v`; expect FAIL.
- [ ] **Step 3:** Implement; ScreenScraper system ids come from a new optional `screenscraper` id on each system in `systems.json` — add the ids for every system there and extend `tests/test_set_data.py`-style validation (or the existing `check` command) so a missing id is reported, not guessed. Systems without an id are skipped with a warning.
- [ ] **Step 4:** Run the tests; expect PASS.
- [ ] **Step 5:** Commit: `feat(scrape): find unscraped roms and match them on screenscraper`

### Task 6: The scrape run (download, upload, quota, dry run)

**Files:**
- Modify: `src/sync_roms/scrape_online.py` (run part)
- Test: `tests/test_scrape_run.py`

**Interfaces:**
- Consumes: Tasks 3-5, `upload.run_uploads`, `scrape_plan.merge_metadata`, `scrape_plan.dump_json`, `scrape_plan.can_shrink`, `scrape_plan.ONION_*`/`SLOT_*`, `s3.put_text`, `ui.confirm`.
- Produces:
  - `report(systems_candidates, matches) -> str` lines per system: scraped-to-be count, matched by hash / name+size / manual, unmatched list.
  - `scrape_command(args) -> int` (`args.system`, `args.retry`, `args.skip_media`, `args.dry_run`) returning 0 / 1.
  - `match_command(args) -> int` for `scrape match SYSTEM ROM GAME` (saves via `scrape_state.save_match`, then scrapes that one ROM).

- [ ] **Step 1: Write failing tests** with a fake client and temp folder storage (pattern from `tests/test_root.py`): `test_dry_run_writes_nothing`, `test_media_uploaded_before_metadata_entry`, `test_existing_metadata_entries_preserved_and_rerun_is_noop`, `test_quota_exceeded_stops_cleanly_and_keeps_finished_roms`, `test_not_found_marks_unknown_and_writes_nothing_for_it`, `test_skip_media_type_not_downloaded`, `test_onion_and_slot_jobs_created_for_art` (Onion not for subfolder ROMs; Slot only for `SLOT_LABEL_MAX` systems; skipped with a warning when `can_shrink()` is false), `test_credentials_missing_fails_with_how_to_set_them`, `test_failed_media_download_leaves_no_metadata_entry`.
- [ ] **Step 2:** Run `python -m unittest tests.test_scrape_run -v`; expect FAIL.
- [ ] **Step 3:** Implement `scrape_command`: apply settings (`usersettings.ensure_bucket()` is done by the caller), list ROMs/metadata, build and print the report, return after the report on `--dry-run`, confirm once, then process candidates in batches of 25 within the client's `max_threads`: lookup → `parse_game` → download media into one `tempfile.TemporaryDirectory` → `upload.run_uploads(files + derived)` → on full success merge the batch's metadata into the system's `metadata.json` (re-read it from storage first) and `s3.put_text`. Stop on `QuotaExceeded` after finishing the in-flight batch and print how to continue.
- [ ] **Step 4:** Run the tests; expect PASS.
- [ ] **Step 5:** Commit: `feat(scrape): scrape missing roms from screenscraper into the bucket`

### Task 7: CLI wiring, docs and help

**Files:**
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS`, `TOPICS`, `LEGACY`, `build_parser`, `check_modes`, dispatch), `README.md`, `src/sync_roms/data/` completion if generated from `SUBCOMMANDS`
- Test: `tests/test_scripting.py` and `tests/test_completion.py` additions

**Interfaces:**
- Consumes: `scrape_online.scrape_command`, `scrape_online.match_command`.
- Produces: `sync-roms scrape [--system ID] [--retry] [--skip-media TYPES] [--dry-run]` and `sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME`; legacy flags `--scrape`, `--scrape-match`; `scrape --set-credentials` prompts for user/password (and dev credentials if required) and saves them via `save_setting`.

- [ ] **Step 1: Write failing tests:** `translate(["scrape"])`/`translate(["scrape","match","gba","a.zip","123"])` produce the legacy forms; `check_modes` rejects `--retry` outside `scrape`; completion lists `scrape`; `test_readme.py` expectations (read it first) still hold.
- [ ] **Step 2:** Run `python -m unittest tests.test_scripting tests.test_completion tests.test_readme -v`; expect FAIL.
- [ ] **Step 3:** Wire the subcommand like `upload scrapes`; add a README section ("Scraping from ScreenScraper") covering credentials (mode 600), report, matching order per backend, manual match, quota behavior and the local state files.
- [ ] **Step 4:** Run `python -m unittest discover tests`; expect all PASS. Manually run `sync-roms scrape --dry-run` against a temp folder root with a fake data set if available.
- [ ] **Step 5:** Commit: `feat(cli): add the scrape command`
