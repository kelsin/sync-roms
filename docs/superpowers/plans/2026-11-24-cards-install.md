# `cards install` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms cards install [CARD] [--dry-run] [--yes]` wipes a spruce card's firmware files (keeping `Roms/`, `BIOS/`, `Saves/` and spruce themes) and unpacks storage's newest spruceOS 7z onto it.

**Architecture:** A new `src/sync_roms/install.py` holds the planning (pure, tested on a temp card folder) and the run (download with `downloads.run_downloads`, delete with a count bar, unpack with 7z `-aos` under a `ui.ProgressBar`). `commands.py` registers `cards install`; help, completion and README follow the existing `cards convert` entries.

**Tech Stack:** Python 3.12+, stdlib `unittest`, the `7z` tool via `external.find_tool("7z")`.

**Spec:** `docs/superpowers/specs/2026-11-24-cards-install-design.md`

## Global Constraints

- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests`. Code must run on Python 3.12.
- Test modules import `isolate` (or `helpers`) before `sync_roms`.
- Storage access only through `inventory.py` / `s3.py` / `downloads.py`; never write to storage.
- Only the `spruce` layout is installable; any other layout: `ui.fail("cards install supports only spruce cards; <card> is <layout>", 2)`.
- Kept root names (case-insensitive): `roms`, `bios`, `saves`, `themes`, `.spotlight-v100`, `.trashes`, `.fseventsd`, `system volume information`; also any `._*` name.
- In `Themes/`: keep entries whose lower-cased name is in `{n.lower() for n in spruce_themes.available()}`; delete the rest.
- 7z newest key: `inventory.newest(inventory.files(runtime.SPRUCE_PREFIX), runtime.SPRUCE_PREFIX, spruce_os.PATTERN)`.
- Card space margin: `spruce_os.MARGIN`. Temp space margin: `flash.SPARE`.
- Exit codes: 0 ok / dry run, 1 declined or no 7z in storage or download failed, 2 usage (no terminal without `--yes`, wrong layout), 3 deletion/unpack failures.
- Conventional Commits; commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A card whose root folders differ only in case from the kept names (`ROMS`, `bios`) — kept, not deleted. Test in Task 1.
- `Themes/` holding both a storage-known theme with different case and an unknown (Onion) one — the first kept, the second deleted. Test in Task 1.
- The download fails — nothing on the card is deleted (download happens before the confirm). Test in Task 1 (`run` with `run_downloads` returning 1).
- The user declines the confirm — nothing deleted, temp folder removed, exit 1. Test in Task 1.
- Dry run — nothing downloaded, deleted or recorded; the plan is printed. Test in Task 1.

---

### Task 1: `install.py` — plan and run

**Files:**
- Create: `src/sync_roms/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: `saves.card_setup(args) -> (base, name, (device, layout_name), catalog)`, `spruce_themes.available() -> [str]`, `downloads.run_downloads(todo, label, icon, base, failures) -> int`, `downloads.free_space(path)`, `external.find_tool("7z")`, `ui.ProgressBar(count, fraction, total_bytes)`, `ui.confirm`, `ui.has_terminal`, `store.update_card`, `store.saved_card`.
- Produces:
  - `KEEP: frozenset[str]` (lower-case root names from Global Constraints)
  - `plan(base: str, themes: set[str]) -> (deleted: list[str], kept: list[str])` — absolute paths; `deleted` holds root entries not kept plus `Themes/` entries whose lower name isn't in `themes` (already lower-cased); `kept` the kept root entries and kept theme folders. Sorted.
  - `unpacked_size(archive: str) -> int` — total unpacked bytes from `7z l -slt` (sum of `Size = ` lines).
  - `unpack(archive: str, base: str, total: int) -> str | None` — runs `[7z, "x", "-y", "-aos", "-bso0", "-bsp1", f"-o{base}", "--", archive]`, reads stdout for `(\d+)%` and drives a `ui.ProgressBar(1, fraction, total)`; returns None on success, else the tool's last stderr line. Kills the process on exception (like `external.run_tool`).
  - `run(args) -> int` — the command (`args.card`, `args.dry_run`, `args.yes`).

- [ ] **Step 1: Write failing tests** in `tests/test_install.py` using `helpers.CardDir` (see `tests/test_spruce_os.py` for card setup and mocking `inventory.files`):
  - `test_plan_keeps_roms_bios_saves_any_case`: root has `ROMS/`, `bios/`, `Saves/`, `.Trashes/`, `._x`, `App/`, `miyoo/`, `autorun.inf` → deleted == `[App, autorun.inf, miyoo]` paths, `ROMS`, `bios`, `Saves`, `.Trashes`, `._x` kept.
  - `test_plan_keeps_only_spruce_themes`: `Themes/ART_BOOK_NEXT/`, `Themes/TechDweeb_BMO/`, `Themes/x.7z`; `plan(base, {"art_book_next"})` → deleted has `Themes/TechDweeb_BMO` and `Themes/x.7z`, kept has `Themes/ART_BOOK_NEXT`; `Themes` itself never in deleted.
  - `test_unpacked_size_sums_sizes`: mock `subprocess.run` stdout `"Path = a\nSize = 10\n\nPath = b\nSize = 5\n"` → 15.
  - `test_run_rejects_other_layout`: card layout `onion` → `SystemExit` code 2.
  - `test_run_dry_run_touches_nothing`: dry run → `run_downloads` not called, `App/` still there, card has no `spruce_os`, output names `App`.
  - `test_run_download_failure_deletes_nothing`: `run_downloads` returns 1 → exit 1, `App/` still there.
  - `test_run_declined_deletes_nothing`: `ui.confirm` → False → exit 1, `App/` still there, temp folder gone (patch `tempfile.mkdtemp` to a known path and assert it's removed).
  - `test_run_installs_and_records`: `--yes`, `run_downloads` → 0, `unpack` mocked → None → `App/` gone, `Roms/` kept, card's `spruce_os == "spruceV4.6.0.7z"`, `boot_logos` removed, `spruce_themes_installed` filtered to kept theme folders.
  - `test_unpack_skips_existing` (skip if `external.find_tool("7z")` is None): build a real 7z with `7z a` holding `Saves/spruce/spruce-config.json` ("new") and `App/a` in a temp dir; card has `Saves/spruce/spruce-config.json` ("old") → after `unpack`, config reads "old", `App/a` exists.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_install -v` — Expected: FAIL (`No module named sync_roms.install` / ImportError).

- [ ] **Step 3: Implement `install.py`.** `run` order: `card_setup` → layout check → newest 7z (none: `ui.failure` + 1) → `plan` with `spruce_themes.available()` → print kept (dim) and deleted (with `ui.human_size` of each, sizes by `os.walk`) → dry run prints `🧪 Dry run: nothing downloaded, deleted or unpacked` and returns 0 → no `--yes` and no terminal: `ui.fail(..., 2)` → temp space check (`shutil.disk_usage(tmp).free < size + flash.SPARE` → failure 1) → `tempfile.mkdtemp(prefix="sync-roms-install-")`, `try/finally shutil.rmtree` → `run_downloads([(key, path, size)], "spruceOS", "🌲", tmp, failures)` → `unpacked_size` → card space check (`free_space(base) + deleted bytes < unpacked + spruce_os.MARGIN` → failure 1) → confirm `Delete N items from <card> and install spruceOS <name>?` (skipped with `--yes`) → delete with convert's count bar pattern (`convert.remove_media(deleted, base, step)` reused with `convert._progress`; failures warned, exit 3 before unpacking) → `unpack` (error: warn, 3) → `store.update_card(name, spruce_os=<name>, spruce_themes_installed=<filtered sorted>)` and drop `boot_logos` (write via `store.load_cards`/`store.write_cards` if `update_card` can't pop) → green `✅ spruceOS <name> installed on <card>` + dim `(run a sync to fill in the rest)`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_install -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `feat(cards): install spruceOS onto a card with cards install`.

### Task 2: CLI wiring, help, completion, README

**Files:**
- Modify: `src/sync_roms/commands.py` (`cards` second words near line 1369; `cards` parsers near line 1503; a `cards_install(args)` beside `cards_convert`)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS["cards"]` usage string at line 32; the `cards` help in `TOPICS`)
- Modify: `README.md` (line 184 cards row, the cards section near line 277)
- Test: `tests/test_commands.py` or the existing test that covers `cards convert` parsing (find with `grep -rn "convert" tests/test_*command*`)

**Interfaces:**
- Consumes: `install.run(args) -> int` from Task 1.
- Produces: `cards install [CARD] [--dry-run] [--yes]` parsed by `commands.build_parser`, `install` in `commands.second_words()["cards"]`.

- [ ] **Step 1: Write failing test**: `build_parser().parse_args(["cards", "install", "TF2", "--dry-run", "--yes"])` → `card == "TF2"`, `dry_run`, `yes`, `fn is commands.cards_install`; `"install" in commands.second_words()["cards"]`.
- [ ] **Step 2: Run it** — Expected: FAIL.
- [ ] **Step 3: Wire it**: `p = csub.add_parser("install", allow_abbrev=False); common(p, card=False); p.add_argument("card", nargs="?"); p.set_defaults(fn=cards_install)`; `cards_install` imports `install` lazily like `cards_convert`. Add `install` to the usage strings and a `cards install` line to `TOPICS["cards"]` and a README bullet after the `cards convert` one: what it keeps (`Roms/`, `BIOS/`, `Saves/`, spruce themes in `Themes/`), that the rest of the card root is deleted, the release unpacked without replacing kept files, progress bars, `--dry-run`, `--yes`, spruce only, needs 7z.
- [ ] **Step 4: Run** `uv run python -m unittest discover -s tests` — Expected: all PASS (incl. `tests/test_readme.py`).
- [ ] **Step 5: Commit** `feat(cards): add cards install to the CLI, help and README`.
