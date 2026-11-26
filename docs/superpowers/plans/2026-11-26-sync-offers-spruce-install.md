# Sync offers to install spruceOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sync of a mounted `spruce` card that lacks spruceOS offers to run the `cards install` flow first.

**Architecture:** `install.run`'s body moves into `install.install_card`; a new `install.offer` decides whether to ask and calls it; `cli.sync_card` calls `install.offer` right after `choose_card_setup`.

**Tech Stack:** Python 3.12+, unittest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-26-sync-offers-spruce-install-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest tests.test_install`, `uv run python tools/run_tests.py`).
- Test modules import `isolate` first (directly or via `helpers`).
- Code must run on Python 3.12.
- Conventional Commits, lowercase imperative (`feat(install): ...`).
- Match the module's terse style: short docstrings, `ui.*` helpers for output.

## Review Focus

- A card folder that isn't a mount point (tests, a local folder) never gets the offer — sync behaves as before.
- `--yes` / `--json` / no terminal never installs (it deletes files): hint only.
- A guest card never gets the offer.
- An install that fails (exit 1 or 3) stops the sync with that code; declining at either question lets the sync go on.
- After a successful install the sync uses the reloaded saved card (`spruce_os` set, so the 7z isn't staged again).

---

### Task 1: `install_card` and `offer` in `install.py`

**Files:**
- Modify: `src/sync_roms/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Produces:
  - `CORE = ("spruce", "App", "Emu")` — spruceOS's root folders.
  - `missing(base: str) -> bool` — True when any `CORE` folder isn't a directory at `base` (case-sensitive `os.path.isdir`).
  - `install_card(base: str, name: str, dry_run: bool, yes: bool) -> int` — exactly `run`'s current body from `listing = ...` onward (0 done or declined, 1 / 2 / 3 as today). `run(args)` keeps its card/mount/layout checks and returns `install_card(base, name, args.dry_run, args.yes)`.
  - `offer(base: str, name: str, dry_run: bool, interactive: bool) -> int` — returns 0 when nothing was offered, declined, or installed; the install's nonzero code when it failed. Behaviour:
    - not `_mounted(base)` or not `missing(base)`: return 0, print nothing.
    - prints `ui.bold(f"🌲 spruceOS isn't on {name}")`.
    - `dry_run`: print `ui.yellow("🧪 Would offer to install spruceOS first")`, return 0.
    - not `interactive`: print `ui.dim(f"  run `sync-roms cards install {name}` to install it")`, return 0.
    - `ui.confirm("Install spruceOS on it now? (a clean install: everything but Roms/ is deleted)")` (default yes) false: same hint, return 0.
    - yes: return `install_card(base, name, False, False)` — `yes=False` so it still lists what is kept and deleted and asks its own confirm before deleting.

- [ ] **Step 1: Write failing tests** in a new `class Offer(helpers.CardDir)` reusing `Run.setUp`'s patches (subclass `Run` or factor its setUp; `_mounted` patched True):
  - `test_offer_nothing_when_spruce_folders_exist`: make `spruce/`, `App/`, `Emu/` under the card; `offer(..., interactive=True)` returns 0, `confirm` not called, stdout empty.
  - `test_offer_nothing_when_not_mounted`: `_mounted` False, folders missing → 0, `confirm` not called.
  - `test_offer_dry_run_only_says_so`: folders missing, `dry_run=True` → 0, "Would offer to install spruceOS" in stdout, `confirm` and `downloads.run_downloads` not called.
  - `test_offer_without_terminal_hints`: `interactive=False` → 0, `cards install <name>` in stdout, nothing downloaded.
  - `test_offer_declined_hints`: `confirm` returns False → 0, hint printed, nothing downloaded.
  - `test_offer_accepted_installs`: `confirm` returns True (both questions) → 0, `unpack` called once, card's `spruce_os` is `spruceV4.6.0.7z` (same check as `test_run_installs_and_records`).
  - `test_offer_returns_install_failure`: accepted, `unpack` returns `"boom"` → 3.
  - `test_missing_checks_each_core_folder`: only `spruce/` and `App/` present → `missing` True; all three → False.
- [ ] **Step 2:** `uv run python -m unittest tests.test_install` — new tests FAIL (`offer` not defined).
- [ ] **Step 3:** Implement `CORE`, `missing`, `install_card`, `offer`; make `run` delegate.
- [ ] **Step 4:** `uv run python -m unittest tests.test_install` — all PASS (existing `Run` tests unchanged).
- [ ] **Step 5:** Commit `feat(install): offer spruceOS install for a card that lacks it`.

### Task 2: sync calls the offer

**Files:**
- Modify: `src/sync_roms/cli.py` (`sync_card`, right after `guest = ...` is computed, before `layout = layouts[layout_name]`)
- Modify: `README.md` (the `cards install` bullet, ~line 291: add one sentence), `src/sync_roms/cli.py` help for `cards install` (~line 349, one clause) if it fits the style
- Test: `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: `install.offer(base, name, dry_run, interactive) -> int` from Task 1.

- [ ] **Step 1: Write failing tests** in `SyncSmokeTest`, modelled on `test_spruce_sync_stages_spruceos` (spruce layout via `cli.picker.saved_setup`), patching `cli.install.offer` (import `install` in cli.py as the other modules are) with a `mock.Mock`:
  - `test_spruce_sync_offers_install`: `offer` returning 0 is called once with `(card_dir, basename, dry_run, interactive)`; run with `yes=True` → `interactive` False.
  - `test_spruce_sync_stops_when_install_fails`: `offer` returns 3 → sync exits 3 and `cli.downloads.run_downloads` is never called.
  - `test_guest_and_other_layouts_get_no_offer`: `esde` layout sync and a spruce `--guest` sync → `offer` not called.
- [ ] **Step 2:** `uv run python -m unittest tests.test_cli_sync -k offer -k install` — FAIL.
- [ ] **Step 3:** In `sync_card`: `if layout_name == "spruce" and not guest:` → `code = install.offer(base, card, args.dry_run, interactive=not (ui.ASSUME_YES or args.json) and ui.has_terminal())`; `if code: return code`; then `saved = store.saved_card(card)` so later steps see `spruce_os`. (Check that `saved` is what `spruce_os.install` reads; if it reads `store.saved_card` itself, the reload is still harmless.) Add the README sentence: a sync of a mounted spruce card missing `spruce/`, `App/` or `Emu/` offers this install first (with a terminal, without `--yes`).
- [ ] **Step 4:** `uv run python tools/run_tests.py` — all PASS (incl. `test_readme`).
- [ ] **Step 5:** Commit `feat(sync): offer to install spruceOS on a card without it`.
