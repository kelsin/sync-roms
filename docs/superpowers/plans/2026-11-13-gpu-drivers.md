# GPU Drivers on Android Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync puts every suggested Adreno driver for a card's device into the card's root `Drivers/`, checking GitHub
for newer releases each run and keeping them in storage; a repo skill refreshes the recommendations by PR.

**Architecture:** Repo data (`drivers.json`, a `gpu` field per device) says which drivers each device gets. A new
`drivers.py` picks releases from the GitHub API, refreshes `os/drivers/<id>.zip` + `.tag` in storage, and builds
download jobs; `cli.sync` runs it like the APK jobs. A shared `github.py` holds the HTTP helper `themeart` already uses.

**Tech Stack:** Python 3 stdlib (`urllib`, `zipfile`, `re`, `json`), `unittest`, boto3 via the existing `s3.py`.

**Spec:** `docs/superpowers/specs/2026-11-13-gpu-drivers-design.md`

## Global Constraints

- Storage keys: `os/drivers/<driver id>.zip` and `os/drivers/<driver id>.tag` (tag text + `\n`). Upload
  the `.zip` before the `.tag`. Never delete from storage.
- Card path: `<card>/Drivers/<driver id>-<safe tag>.zip`; safe tag = tag with every char outside `[A-Za-z0-9._-]`
  replaced by `_`.
- Only `esde` cards whose device's `gpu` has a non-empty driver list get drivers.
- Card cleanup touches only names in the card's `drivers` list in `cards.json`.
- Storage reads go through `inventory.py`; never call `s3.list_sizes`/`stat_sizes` elsewhere.
- GitHub or network errors never fail a sync: warn (`ui.warn`/yellow) naming the driver, keep storage's copy.
- No write access (S3 and `boto3.Session(profile_name=runtime.WRITE_PROFILE)` raises `ProfileNotFound`): skip GitHub with
  one dim line `🎮 no write access to storage: copying the drivers it has`. A storage folder (`runtime.ROOT`) is writable.
- Summary line: `🎮 Drivers: N to download (size), M already present`, shown only when the card has driver jobs.
- Commits: Conventional Commits, lowercase imperative. No AI attribution in commits or PRs.
- Repo files never describe the bucket's contents.

## Review Focus

- A release with two assets matching one regex (e.g. `-Linux`/`-Wayland` variants): must not upload an arbitrary one —
  warn and keep storage's copy. Test in Task 2.
- A downloaded asset that isn't a zip (HTML error page, truncated): must not reach storage. Test in Task 3.
- GitHub rate limit (HTTP 403/429) on the 5th of 8 drivers: the first 4 still update, the rest warn. Test in Task 3.
- A driver dropped from a GPU's list, or a device's `gpu` changed: its old zip leaves the card, files the user added
  stay. Test in Task 4.
- A pinned driver already in storage: no GitHub call at all, even with a stale `.tag`. Test in Task 3.

---

### Task 1: Driver data and GPU fields

**Files:**
- Create: `src/sync_roms/data/drivers.json`
- Modify: `src/sync_roms/data/devices.json` (add `gpu` to Adreno devices)
- Modify: `src/sync_roms/commands.py` (data validation near line 592: drivers checks)
- Test: `tests/test_drivers_data.py`

**Interfaces:**
- Produces: `store.repo_json("drivers")` → `{"drivers": [{"id", "name", "repo", "asset", "tag"?}], "gpus": {gpu id: {"name", "drivers": [ids]}}}`;
  device dicts carry optional `"gpu"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_drivers_data.py` (use `helpers`, read repo files like `test_firmware.py` does):
  - `test_every_gpu_driver_id_exists`: every id in every `gpus[*].drivers` is a `drivers[*].id`.
  - `test_every_device_gpu_exists`: every device `gpu` is a key of `gpus`.
  - `test_driver_ids_unique_and_regexes_compile`: ids unique, match `^[a-z0-9-]+$`, `re.compile(asset)` works, `repo` matches `^[\w.-]+/[\w.-]+$`.
  - `test_every_driver_is_used`: every driver id appears in some gpu's list.
  - `test_gpu_assignments`: exactly the device→gpu table in the spec (Design › Repo data), and no other device has `gpu`.
- [ ] **Step 2:** Run `python -m unittest tests.test_drivers_data -v`. Expected: FAIL (no drivers.json).
- [ ] **Step 3: Fill the data.** Device→gpu and gpu→drivers exactly per the spec's two tables. For each driver, look
  at the repo's real releases (`gh api "repos/OWNER/REPO/releases?per_page=30" --jq '.[]|[.tag_name,.prerelease,(.assets|map(.name)|join(","))]|@tsv'`)
  and write an `asset` regex that matches exactly one asset of the intended release, and for pinned ones the exact
  `tag`. Pinned: K11MCH1 v24.3.0 r9, MrPurple T19, MrPurple T24, K11MCH1 Turnip v26.0.0 R7, Qualcomm v819.1. Latest:
  the rest. Separate ids for StevenMXZ's A6xx/A7xx build and its Gen8 build (same repo, different `asset`). For the
  Vauzi-17 regex exclude `-exp`. If a repo or tag can't be found, stop and report it rather than guessing.
  Add the same checks as Step 1 to the data validation in `commands.py` (problems list, `drivers.json: ...` messages).
- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(drivers): add suggested adreno drivers and device gpus`

### Task 2: Shared GitHub helper and release picking

**Files:**
- Create: `src/sync_roms/github.py`
- Create: `src/sync_roms/drivers.py`
- Modify: `src/sync_roms/themeart.py` (use `github.get` instead of `_github`; keep `themeart._github` name only if
  tests patch it — update `tests/test_themeart.py` to patch `github.get` instead)
- Test: `tests/test_drivers.py`

**Interfaces:**
- Produces:
  - `github.get(url: str, accept: str | None = None)` → response context manager (moved `themeart._github`).
  - `github.json(url: str)` → parsed JSON of `get(url, "application/vnd.github+json")`.
  - `drivers.PREFIX = "os/drivers/"`
  - `drivers.load() -> dict` (`store.repo_json("drivers")`)
  - `drivers.for_device(device: dict | None, layout_name: str) -> list[dict]` — driver entries for that device's gpu, in list order; `[]` unless `layout_name == "esde"`.
  - `drivers.pick_release(driver: dict, releases: list[dict]) -> tuple[str, dict]` — (tag, asset dict with `name`, `browser_download_url`, `size`); raises `drivers.NoAsset(message)` when none or more than one asset matches.
  - `drivers.card_name(driver_id: str, tag: str) -> str`

- [ ] **Step 1: Write failing tests** in `tests/test_drivers.py`:
  - `test_pinned_picks_its_tag`: releases `[v2 (match), v1 (match)]`, driver with `tag: "v1"` → `"v1"`.
  - `test_latest_skips_releases_without_a_matching_asset`: `[v840 (Qualcomm_840.zip), v26 (Turnip_v26.zip)]`, asset `^Turnip_v.*\.zip$` → `"v26"`.
  - `test_drafts_skipped_prereleases_used_only_when_all_are`: `[draft v3, prerelease v2, v1]` → `v1`; `[prerelease v2, prerelease v1]` → `v2`.
  - `test_two_matching_assets_raise`: one release with `T-A8xx.zip` and `T-A8xx-Linux.zip`, asset `A8xx` → `NoAsset`.
  - `test_no_match_raises`.
  - `test_card_name`: `card_name("mrpurple", "vturnip_mrpurple_T30-toasted.adpkg") == "mrpurple-vturnip_mrpurple_T30-toasted.adpkg.zip"`; `card_name("x", "v1/2 b") == "x-v1_2_b.zip"`.
  - `test_for_device`: a device with `gpu: "adreno-650"` on `esde` gets 4 entries in spec order; on `knulli` `[]`; no gpu `[]`; `None` device `[]`.
- [ ] **Step 2:** Run `python -m unittest tests.test_drivers -v`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement `github.py` and the `drivers.py` functions above. For a pinned driver `pick_release` is
  called with `[release]` from `/releases/tags/{tag}`; for latest, with `/releases?per_page=30`.
- [ ] **Step 4:** Run `python -m unittest tests.test_drivers tests.test_themeart -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(drivers): pick driver releases from github`

### Task 3: Refresh storage from GitHub

**Files:**
- Modify: `src/sync_roms/drivers.py`
- Modify: `src/sync_roms/s3.py:256-259` (`put_file` on S3 patches the cache: `inventory.wrote(key, os.path.getsize(path))`)
- Test: `tests/test_drivers.py`

**Interfaces:**
- Consumes: Task 2's `pick_release`, `github.json`, `github.get`, `PREFIX`.
- Produces:
  - `drivers.can_write() -> bool`
  - `drivers.refresh(entries: list[dict], dry_run: bool) -> None` — for each entry: skip a pinned one whose `.zip` is in
    `inventory.files(PREFIX)`; else fetch release(s), compare with stored `.tag` (`s3.get_text`, missing → none), and when
    different download `browser_download_url` to a temp file, check `zipfile.is_zipfile`, `s3.put_file(<id>.zip)`, then
    `s3.put_text(<id>.tag, tag + "\n")`; when a mirror is in use (`runtime._mirror_root`) also copy the zip and tag
    there at the same keys. Prints `🎮 <name>: <old or "none in storage"> → <tag>` per update; dry run prints
    `🧪 Dry run: would store <name> <tag>` and writes nothing. Any `OSError`/`http.client.HTTPException`/`NoAsset`/
    `s3.ERRORS` → `ui.warn(f"Couldn't update the {name} driver: {e}")`, next entry.
  - `drivers.stored_tag(driver_id: str) -> str | None`

- [ ] **Step 1: Write failing tests** (storage folder in a temp dir via `runtime.ROOT`, `github.json`/`github.get` patched):
  - `test_new_tag_stores_zip_then_tag`: stored `v1`, GitHub `v2` → `.zip` bytes are the download, `.tag` is `"v2\n"`; patch `s3.put_file`/`put_text` with wrappers recording call order: zip first.
  - `test_same_tag_downloads_nothing`: `github.get` for the asset never called.
  - `test_pinned_in_storage_makes_no_github_call`: `github.json` not called.
  - `test_not_a_zip_keeps_storage`: download returns `b"<html>"` → stored files unchanged, warning names the driver.
  - `test_rate_limit_midway_keeps_earlier_updates`: 3 entries, `github.json` raises `HTTPError(403)` on the 2nd → 1st updated, 3rd still checked and updated, one warning.
  - `test_dry_run_writes_nothing`.
  - `test_mirror_gets_the_new_zip`: with `runtime._mirror_root` set, the mirror has `os/drivers/<id>.zip` and `.tag`.
  - `test_can_write`: `runtime.ROOT` set → True; S3 with `ProfileNotFound` patched → False.
- [ ] **Step 2:** Run `python -m unittest tests.test_drivers -v`. Expected: new tests FAIL.
- [ ] **Step 3:** Implement `can_write`, `stored_tag`, `refresh`; fix `s3.put_file`.
- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(drivers): store new driver releases at sync time`

### Task 4: Sync drivers to the card

**Files:**
- Modify: `src/sync_roms/drivers.py`
- Modify: `src/sync_roms/cli.py` (next to the APK jobs ~line 959, the summary tuple ~1007, `todo_all` ~1014, the
  dry-run counts ~1083, `run_downloads` ~1134, `got` ~1172)
- Modify: `src/sync_roms/mirroring.py:18` (add `drivers.PREFIX` to the prefixes in `mirror_wanted`, docstring too)
- Modify: `src/sync_roms/commands.py:267` (`CARD_FIELDS` gains `"drivers"`; validation: `drivers` is a list of names)
- Test: `tests/test_drivers.py`, `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces:
  - `drivers.jobs(entries: list[dict], drivers_dir: str) -> list[tuple[str, str, int]]` — `(PREFIX + id + ".zip", <drivers_dir>/card_name(id, stored_tag(id)), size)` for each entry whose zip is in storage; others reported once with `ui.report_missing`.
  - `drivers.prune(card: str, drivers_dir: str, current: list[str], dry_run: bool) -> list[str]` — removes files in `drivers_dir` named in the card's saved `drivers` list but not in `current`, then (not dry run) `store.update_card(card, drivers=sorted(current))`; returns removed names.

- [ ] **Step 1: Write failing tests**:
  - `test_jobs_name_files_by_id_and_tag`.
  - `test_prune_removes_only_recorded_names`: `Drivers/` has `a-v1.zip` (recorded), `mine.zip` (not recorded), `a-v2.zip` current → removes `a-v1.zip` only; `cards.json` `drivers == ["a-v2.zip"]`.
  - `test_prune_drops_a_driver_no_longer_suggested`: recorded `b-v1.zip`, current `[]` → removed.
  - `test_prune_dry_run_keeps_files_and_list`.
  - In `test_cli_sync.py`, following its existing sync-test pattern: an `esde` card with an `adreno-650` device and stored driver zips gets them in `Drivers/` and prints the `🎮 Drivers:` line; a `knulli` card gets no `Drivers/` and no line; a card with no write access makes no GitHub call.
- [ ] **Step 2:** Run the new tests. Expected: FAIL.
- [ ] **Step 3: Wire into sync.** `entries = drivers.for_device(device, layout_name)`; if entries: `drivers.refresh(entries, args.dry_run)` when `drivers.can_write()` else the dim line from Global Constraints; build `driver_jobs = downloads.with_sizes(drivers.jobs(entries, os.path.join(base, "Drivers")))`, `driver_todo = downloads.plan_downloads(driver_jobs)`; add `("🎮", "Drivers", driver_todo, driver_jobs, False)` to the summary, `driver_todo` to `todo_all`, the dry-run counts and `got`; run `downloads.run_downloads(driver_todo, "Drivers", "🎮", drivers_dir, failures)`; after downloads call `drivers.prune(card, drivers_dir, [os.path.basename(p) for _, p, _ in driver_jobs], args.dry_run)` and print `🧹 Removed old driver <name>` per removal. Refresh runs before the jobs are built so a new zip is copied this sync.
- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(drivers): copy suggested drivers to android cards`

### Task 5: Docs and refresh skill

**Files:**
- Modify: `CLAUDE.md` (Data files table: `drivers.json` and the `gpu` device field; `~/.sync-roms/cards.json` row: the card's `drivers` list; storage's `os/drivers/`)
- Modify: `README.md` (what an Android card gets: `Drivers/` and how to import a zip in an emulator's driver manager; check `tests/test_readme.py` for what it enforces)
- Create: `.claude/skills/refresh-drivers/SKILL.md`

- [ ] **Step 1:** Write the docs changes. Keep CLAUDE.md wording in its existing terse style.
- [ ] **Step 2:** Write the skill with frontmatter `name: refresh-drivers`, a `description` that triggers on "refresh/update/check the driver recommendations" and "are the turnip drivers still current", and the steps from the spec (Design › Repo skill): read data; research (OverclockedHQ Turnip guide, Joey's Retro Handhelds Snapdragon driver list, newer guides found by search, each repo's releases via `gh api`); update `drivers.json`/`devices.json` under the same rules (every suggested driver; pin only where a guide names a specific build; regex matches exactly one asset); run `python -m unittest discover -s tests`; if `git diff` is non-empty, branch `chore/refresh-drivers-YYYY-MM-DD` off up-to-date `main`, commit `chore(drivers): refresh driver recommendations`, push, `gh pr create` with a body listing each change and its source; otherwise report no changes and open nothing. Follow CLAUDE.md commit and PR rules.
- [ ] **Step 3:** Run `python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 4: Commit** `docs(drivers): document drivers and add refresh skill`
