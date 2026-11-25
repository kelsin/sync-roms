# Splore Carts Into Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A spruce sync uploads every cart in the card's Splore cache that storage lacks (or holds an older revision of),
scrapes the new ones, adds them to the card's games, and renames Splore-import copies to their storage names.

**Architecture:** `bbs.py`'s upload-and-upgrade loop is factored into `bbs.add_carts`, shared by `download pico8` and a
new `splore.py`, which reads the card's cache and `favourites.txt`, asks once, calls `add_carts`, scrapes the new carts
with `scrape_online.run_scrape`, and updates the card. `cli.py` calls `splore.run` early in a non-guest spruce sync.

**Tech Stack:** Python 3.12+, unittest, uv.

**Spec:** `docs/superpowers/specs/2026-11-24-splore-carts-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest discover -s tests`); code must run on Python 3.12.
- Test modules import `helpers` (which imports `isolate`) before `sync_roms`.
- Storage only through `s3.py`, `inventory.py`, `shared.py`; catch `s3.ERRORS`; ask `inventory` what storage holds.
- Card text/binary writes through `cardfs`/`store.replace_file`; cards.json only through `store.write_cards`/`store.update_card`.
- Cache path on the card: `Emu/PICO8/.lexaloffle/pico-8/` (`bbs/carts/*.p8.png`, `bbs/*/*.p8.png`, `favourites.txt`).
- Conventional Commits; never edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A cart cached twice (`bbs/carts/x-1.p8.png` and `bbs/carts/x-2.p8.png`) → only `x-2` is offered (Task 2 test).
- A card revision equal to or older than storage's → nothing offered, nothing written (Task 2 test).
- A sync without a terminal and without `--yes` → nothing uploaded, a hint printed, the sync goes on (Task 3 test).
- The scrape exits through `ui.fail` (`SystemExit`) or raises → a warning, `splore.run` still adds the carts to the card
  and returns (Task 3 test).
- A `favourites.txt` with `\r\n` ends, padded fields, a `bbs/1/15133.p8.png` path in field 2, or fewer than 7 fields →
  parsed per the spec; short lines give no title (Task 2 test).

---

### Task 1: Factor `bbs.add_carts` out of `download_pico8`

**Files:**
- Modify: `src/sync_roms/bbs.py` (the body of `download_pico8` from `scrape_plan.load_metadata(..., fresh=True)` to the end)
- Test: `tests/test_bbs.py`

**Interfaces:**
- Produces: `bbs.add_carts(todo, fetch, tmp) -> (added_keys, upgraded, code)`.
  `todo`: list of `(old_key_or_None, cart)`, cart a dict with `"file"`, `"title"` (str or None), `"author"` (str or None).
  `fetch(cart, tmp) -> path or None` (None: skipped, already warned; may raise `_HTTP_ERRORS`/`OSError`, which stops the
  loop with a warning, as now). `added_keys`: the `pico8/<file>` keys of new carts whose metadata write succeeded, in
  order. `upgraded`: count. `code`: 0 or 1. Prints nothing beyond the current warnings; the caller prints its summary.
- Metadata for a cart whose `"title"` is None: a new cart writes no entry; an upgrade moves the old entry to the new file
  unchanged. `retarget`'s title: the written entry's `name`, else the old entry's `name`, else `names.title`-style
  fallback (the file name without `.p8.png`).

- [ ] **Step 1: Write the failing tests** in `class Download` (reuse its setUp/fixtures):
  - `test_add_carts_from_local_files`: `fetch` returns a PNG written in `tmp`; new cart with title `"T"`/author `"A"` →
    `pico8/x-0.p8.png` in storage, `scrapes/pico8/metadata.json` has `{"x-0.p8.png": {"name": "T", "developer": "A"}}`,
    return `(["pico8/x-0.p8.png"], 0, 0)`.
  - `test_add_carts_without_title_writes_no_metadata_entry`: same with `"title": None, "author": None` → key uploaded,
    metadata has no `x-0.p8.png`.
  - `test_add_carts_upgrade_without_title_keeps_the_old_entry`: storage `pico8/x-1.p8.png` with entry
    `{"name": "Old", "developer": "D"}`, card has a cart named `pico8/x-1.p8.png`; upgrade to `x-2` with title None →
    entry under `x-2.p8.png` equals `{"name": "Old", "developer": "D"}`, `x-1` gone, card's bucket is `pico8/x-2.p8.png`
    with title `"Old"`, return `([], 1, 0)`.
- [ ] **Step 2:** `uv run python -m unittest tests.test_bbs -v` → the three new tests FAIL (`add_carts` missing).
- [ ] **Step 3:** Move the loop and `finish()` into `add_carts`; `download_pico8` calls it with `_download` and prints
  `Added {len(added_keys)} and upgraded {upgraded}` as before.
- [ ] **Step 4:** `uv run python -m unittest tests.test_bbs -v` → all PASS (the existing Download tests unchanged).
- [ ] **Step 5:** Commit `refactor(pico8): share the cart upload loop of download pico8`.

### Task 2: `splore.py`: read the card's Splore cache

**Files:**
- Create: `src/sync_roms/splore.py`
- Test: `tests/test_splore.py`

**Interfaces:**
- Produces:
  - `CACHE = ("Emu", "PICO8", ".lexaloffle", "pico-8")`
  - `favourites(base) -> {cart base: (title or None, author or None)}`: lines of `favourites.txt` split on `|`, each
    field trimmed, `\r` dropped; field 2 (index 1) with any `…/` path and `.p8.png`/`.p8` dropped, then `bbs.identity`'s
    base; title from field 7 (index 6), author from field 5 (index 4), when the line has them and they're non-empty.
    Missing file → `{}`.
  - `cached(base) -> [cart]`: per cart base the highest revision found in `bbs/carts/*.p8.png` and `bbs/*/*.p8.png`
    (one level), skipping names starting `temp-`, names not matching `bbs._FILE`, and files not starting with `bbs._PNG`.
    Each cart: `{"file", "path", "title", "author"}`, title/author from `favourites(base)` by base, else None. Sorted by file.
  - `plan(base) -> (new, upgrades)`: `bbs.classify(cached(base), set(inventory.files("pico8/", sizes=False)), ignore.keys())`.

- [ ] **Step 1: Write the failing tests** (`helpers.CardDir`, card files under `self.cp(*splore.CACHE, ...)` with
  `bbs._PNG + b"..."` contents; storage files via `self.put`):
  - `test_highest_revision_per_cart`: `bbs/carts/x-1.p8.png`, `bbs/carts/x-2.p8.png`, `bbs/1/15133.p8.png` →
    files `["15133.p8.png", "x-2.p8.png"]`.
  - `test_skips_partial_odd_and_non_png`: `temp-y-0.p8.png`, `bad name.p8.png`, `z-0.p8.png` holding `b"not png"` → `[]`.
  - `test_favourites_fields`: line `"| x-2 \t| x |123|Ann | 0 | 0 |My Game |\r\n"` plus a line
    `"|bbs/1/15133.p8.png|\n"` → `{"x": ("My Game", "Ann"), "15133": (None, None)}`.
  - `test_titles_come_from_favourites`: cached `x-2` with that favourites line → its cart has title `"My Game"`, author `"Ann"`.
  - `test_plan_new_upgrade_and_already_held`: storage `pico8/x-1.p8.png`, `pico8/w-3.p8.png`; card `x-2`, `w-3`, `w-1`,
    `n-0` → new `["n-0.p8.png"]`, upgrades `[("pico8/x-1.p8.png", x-2 cart)]`.
  - `test_plan_skips_ignored`: ignore list `{"pico8": ["n-0.p8.png"]}` (via `ignore` the way `tests/test_bbs.py` sets it) → n-0 not new.
  - `test_no_cache_folder`: nothing on the card → `cached` is `[]`, `favourites` is `{}`.
- [ ] **Step 2:** `uv run python -m unittest tests.test_splore -v` → FAIL (module missing).
- [ ] **Step 3:** Implement the three functions and `CACHE`.
- [ ] **Step 4:** `uv run python -m unittest tests.test_splore -v` → PASS.
- [ ] **Step 5:** Commit `feat(pico8): read the carts in a spruce card's splore cache`.

### Task 3: `splore.run`: upload, scrape, add to the card, rename import copies

**Files:**
- Modify: `src/sync_roms/splore.py`
- Test: `tests/test_splore.py`

**Interfaces:**
- Consumes: `bbs.add_carts` (Task 1), `splore.plan`/`cached` (Task 2), `scrape_online.run_scrape`, `scrape_online.CREDENTIALS`,
  `scrape_online.make_client`, `usersettings.load_settings`, `drivers.can_write`, `inventory.tag`, `names.title`,
  `store.card_games`, `store.update_card`, `ui.confirm`, `ui.has_terminal`, `ui.ASSUME_YES`.
- Produces: `splore.run(card, base, pico8_dir, system, dry_run) -> int` (failure count, 0 or 1). `pico8_dir`: the card's
  PICO-8 ROM folder (`Roms/PICO8`). `system`: the pico8 entry of `systems` (passed to `run_scrape` as `{"pico8": system}`).

Behaviour, in order:
1. `new, upgrades = plan(base)`; nothing → go to step 6 (renames) and return 0.
2. Print a `🕹️  Splore carts on the card` block: `  new: <file>` / `  upgrade: <old> → <file>`, then counts.
   `dry_run`: also `would scrape N cart(s)` and the renames of step 6 as `would rename`; write nothing; return 0.
3. No write access (`drivers.can_write()` false): `ui.warn` and skip to step 6. No terminal and not `ui.ASSUME_YES`:
   print a dim hint (`run sync with --yes, or on a terminal, to add them`) and skip to step 6. Else
   `ui.confirm(f"Add these to {s3.location()} and scrape the new ones?", default=True)`; no → step 6.
4. `added, upgraded, code = bbs.add_carts(todo, fetch, tmp)` with `fetch` copying `cart["path"]` into `tmp`.
5. Scrape `added` when `usersettings.load_settings()` has every `scrape_online.CREDENTIALS` (else a dim hint
   `sync-roms scrape pico8`): `run_scrape(make_client(), {"pico8": system}, {"pico8": [(file, size, inventory.tag(key))]},
   set(), ask=False)`, sizes from `inventory.files("pico8/")`; `SystemExit` or `Exception` from it → `ui.warn` and go on.
   Then, unless `store.card_games(card).get("pico8")` is a dict (a full system), append
   `{"title": names.title(key), "bucket": key}` for each added key not already named there, and save with
   `store.update_card(card, games=...)`.
6. Renames: for each `.p8.png` in `pico8_dir` (top level) whose bytes equal a cached cart's file and whose name differs
   from that cart's `file`, while storage has `pico8/<file>` and `pico8_dir/<file>` doesn't exist: rename it to `file`.
   Print `  📦 Renamed <old> → <file>`.
- Return `code` (or 1 when the scrape failed).

- [ ] **Step 1: Write the failing tests** (`helpers.CardDir`; mock `ui.has_terminal`, `ui.confirm`, `drivers.can_write`,
  `scrape_online.run_scrape`, `scrape_online.make_client`; credentials via `usersettings` settings in the data folder):
  - `test_uploads_scrapes_and_adds_the_new_cart`: cached `n-0` (favourites title `"N"`), confirm yes, credentials set →
    `pico8/n-0.p8.png` in storage, `run_scrape` called once with todo `{"pico8": [("n-0.p8.png", size, tag)]}` and
    `ask=False`, card `c`'s `games["pico8"]` is `[{"title": "N", "bucket": "pico8/n-0.p8.png"}]`, returns 0.
  - `test_upgrade_retargets_and_is_not_scraped`: storage `x-1` named on the card, cached `x-2` → card names
    `pico8/x-2.p8.png`, `run_scrape` not called, nothing appended.
  - `test_full_system_card_gets_no_entries`: card `games["pico8"] = {"full_system": True}` → unchanged after the run.
  - `test_dry_run_writes_nothing`: storage and cards.json unchanged; output has `new: n-0.p8.png` and `would scrape 1`.
  - `test_declined_uploads_nothing`: confirm no → storage unchanged, card unchanged.
  - `test_no_terminal_without_yes_skips_with_a_hint`: `has_terminal` false, `ASSUME_YES` false → storage unchanged,
    output names `--yes`, returns 0.
  - `test_no_credentials_skips_the_scrape`: credentials absent → uploaded and added, `run_scrape` not called, output has
    `sync-roms scrape pico8`.
  - `test_scrape_that_exits_is_a_warning`: `run_scrape` raises `SystemExit(3)` → card still gets the entry, returns 1.
  - `test_import_copy_is_renamed`: storage `pico8/x-2.p8.png`, cached `x-2` with bytes B, `Roms/PICO8/My Game.p8.png`
    with bytes B → renamed to `Roms/PICO8/x-2.p8.png`; a same-bytes copy when `x-2.p8.png` is already there stays.
- [ ] **Step 2:** `uv run python -m unittest tests.test_splore -v` → the new tests FAIL.
- [ ] **Step 3:** Implement `run` as above.
- [ ] **Step 4:** `uv run python -m unittest tests.test_splore -v` → PASS.
- [ ] **Step 5:** Commit `feat(pico8): add a spruce card's splore carts to storage and the card`.

### Task 4: Call it from sync, and document it

**Files:**
- Modify: `src/sync_roms/cli.py` (in the sync flow after `guest` is final for the pre-editor step and before the card
  editor / `surprise.run_surprise`, around lines 1430-1450)
- Modify: `CLAUDE.md` (the "What sync puts on a card" bullets and the Storage table's `<system>/` and `scrapes/` "Written
  by" cells: add `sync (spruce Splore carts)`), `README.md` (the spruce/PICO-8 part, one short paragraph)
- Test: `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: `splore.run(card, base, pico8_dir, system, dry_run)` (Task 3).

- [ ] **Step 1: Write the failing tests** in `tests/test_cli_sync.py`, following its spruce-card tests:
  - `test_spruce_sync_runs_splore`: a spruce card sync with `splore.run` mocked → called once with the card name, the
    card base, `<roms_dir>/PICO8`, the pico8 system and the dry-run flag, before the card editor runs.
  - `test_guest_and_other_layouts_skip_splore`: a guest spruce card and an onion card → not called.
  - `test_new_splore_cart_is_synced_to_the_card` (unmocked, `--yes`, no credentials): cached `n-0` on the card → after
    the sync `Roms/PICO8/n-0.p8.png` exists and no extras prompt names it.
- [ ] **Step 2:** `uv run python -m unittest tests.test_cli_sync -v` → the new tests FAIL.
- [ ] **Step 3:** Add the call: only when `layout_name == "spruce"`, not `guest`, and the card syncs pico8 (its folder from
  `systems.json`'s `folders["spruce"]`); its result adds to the run's failures; reload the card's picks afterwards
  (`reload_changes()` where defined) so the editor and plan see the new games. Make sure files uploaded this run are seen
  by the copy step (storage cache patched by `s3.py`; with a local mirror, the copy reads storage for keys the mirror
  lacks); add whatever that takes.
- [ ] **Step 4:** Update `CLAUDE.md` and `README.md`; `uv run python -m unittest tests.test_readme -v` → PASS.
- [ ] **Step 5:** `uv run python -m unittest discover -s tests` → all PASS.
- [ ] **Step 6:** Commit `feat(sync): bring splore carts from spruce cards into storage`.
