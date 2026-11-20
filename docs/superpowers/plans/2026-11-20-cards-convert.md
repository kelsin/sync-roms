# cards convert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms cards convert [CARD] --layout ID [--dry-run] [--yes]` renames a synced card's ROMs, BIOS and RetroArch saves/states from its saved layout into another layout on the same filesystem, then saves the new layout.

**Architecture:** New `src/sync_roms/convert.py` with pure planners returning `[(src, dst)]` moves plus a skipped list; an `apply_moves` that renames (never overwrites); `commands.py` wires the subcommand. Planners work from what is on the card (walking the old folders), not from storage. Saves reuse `saves.scan` / `saves.target_dir` / `saves.minui_name`; BIOS reuses `downloads.bios_folders`; ROM paths reuse `downloads.rom_rel` and `m3u.game_folders`.

**Tech Stack:** Python stdlib, `unittest` (`python -m unittest discover -s tests`), temp-dir cards (see `tests/helpers.py`: `touch`, `write_json`, isolated data dir).

**Spec:** docs/superpowers/specs/2026-11-20-cards-convert-design.md

## Global Constraints

- Same-filesystem renames only (`os.rename`); ROM bytes never copied; no reformatting.
- A destination that already exists is skipped and reported, never replaced.
- Systems with no folder in the new layout (`folders[layout]` null) are left in place and listed.
- Frontend metadata (gamelists, collections, media, themes, PICO-8/Surprise installs) is not converted; leftovers are reported, not deleted.
- `cards set --layout` is unchanged.
- The target layout must be one the card's saved device runs (reuse `commands.setup_from_flags`); the card needs a saved layout.
- Conventional commits; imperative lowercase; no layout-specific data added to the repo's JSON.

## Review Focus

- Case-only renames on a case-insensitive filesystem (`roms`→`Roms`, `bios`→`Bios`): src and dst are the same file; must rename, not "conflict".
- Knulli states have no core but NextUI states need `<tag>-<core>`: those states are skipped and reported, saves still move.
- Several systems sharing one ROM folder (WS/NGP) and several systems sharing one NextUI tag folder: each file moves once.
- Re-running after a partial or finished conversion: moves nothing, no errors, no duplicate work.
- A save whose game is not on the card, and files starting `._` or `.`: left alone.

---

### Task 1: ROM and BIOS move planner

**Files:**
- Create: `src/sync_roms/convert.py`
- Test: `tests/test_convert.py`

**Interfaces:**
- Produces: `plan_roms(base, systems, old_name, old, new_name, new) -> (moves, skipped)` and `plan_bios(base, systems, old_name, old, new_name, new) -> (moves, skipped)`; `moves` is `[(src, dst)]` absolute paths, `skipped` is `[(label, reason)]`. `systems` is the manifest list (each has `bucket`, `folders`, optional `nextui_bios_tags`); `old`/`new` are layout dicts from `layouts.json`.
- Produces: `apply_moves(moves) -> (done, conflicts)`: renames each (makes parent dirs); `conflicts` is the moves whose dst exists as a different file.

- [ ] **Step 1: Write failing tests** in `tests/test_convert.py` (use a small `LAYOUTS` dict copied from `layouts.json` for knulli and nextui and two systems, e.g. `gba` with folders knulli `gba` / nextui `Game Boy Advance (GBA)`, and `arcade` with nextui `null`):
  - `test_roms_move_to_new_folder`: `roms/gba/Game.zip` plans to `Roms/Game Boy Advance (GBA)/Game.zip`.
  - `test_disc_game_gets_its_own_folder`: `roms/psx/Game (Disc 1).cue`, `Game (Disc 2).cue`, `Game.m3u` plan into `Roms/<psx folder>/Game/…` (rel path from `downloads.rom_rel(key, None, (), m3u.game_folders(keys))`, keys being `"<bucket>/<file>"`).
  - `test_system_without_new_folder_is_skipped`: `roms/arcade/x.zip` stays, `skipped` has `("arcade", ...)`.
  - `test_bios_goes_into_tag_folder`: `bios/gba_bios.bin` plans to `Bios/GBA/gba_bios.bin`; with several target folders (the tag plus `nextui_bios_tags`) the file moves to the first and the others are reported in `skipped` with reason "extra tag folder; sync will add it".
  - `test_dotfiles_ignored`: `._x`, `.DS_Store` never planned.
  - `test_case_only_rename_is_a_move`: `apply_moves` on `roms/gba/Game.zip` → `Roms/gba/Game.zip` ends with only the new spelling (use a real rename through a temp name).
  - `test_existing_destination_is_a_conflict`: dst exists with other content → in `conflicts`, src untouched.
  - `test_rerun_plans_nothing`: after `apply_moves`, `plan_roms` returns no moves.
- [ ] **Step 2: Run** `python -m unittest tests.test_convert -v`; expect ImportError/FAIL.
- [ ] **Step 3: Implement `plan_roms`, `plan_bios`, `apply_moves` in `convert.py`.** Approach: for each system with an old folder on the card, walk it (skip dotfiles and `.media`), flatten its relative paths to bucket-style keys by stripping the old layout's `disc_dir` prefix and, when the old layout has `disc_folders`, the one-level game folder; compute the new rel with `downloads.rom_rel` using the new layout's `disc_dir`/`disc_keys` or `game_folders`. Systems sharing an old folder are planned once (first in systems order). For layouts with `disc_dir` on either side, rewrite is only needed for `.m3u` lines: out of scope here, report a `.m3u` that would need it in `skipped` (reason "playlist paths differ between layouts; sync rewrites it") only when exactly one side has `disc_dir`, and leave it in place. `apply_moves`: `os.makedirs` the parent; if dst exists and `os.path.samefile(src, dst)` rename via `src + ".convert-tmp"`; if it exists otherwise, record a conflict; afterwards prune directories emptied under the old system/BIOS folders (never the layout's `roms_dir`/`bios_dir` roots themselves unless they are case-only renamed away).
- [ ] **Step 4: Run** `python -m unittest tests.test_convert -v`; all PASS.
- [ ] **Step 5: Commit** `feat(convert): plan and apply rom and bios moves between layouts`

### Task 2: Saves and states planner

**Files:**
- Modify: `src/sync_roms/convert.py`
- Test: `tests/test_convert.py`

**Interfaces:**
- Consumes: `saves.scan(base, layout_name, layout, systems, retroarch_dir=None) -> (games, skipped_count)`; `saves.target_dir(base, new_name, new, system, kind, core)` (raises `ValueError`); `saves.minui_name(srm_name, rom_names)`; `saves.rom_names(base, new_name, new, system)`. Task 1 ROM moves must already be applied (or the planner is given the ROM names the new layout will have).
- Produces: `plan_saves(base, systems, old_name, old, new_name, new) -> (moves, skipped)`, same shapes as Task 1.

- [ ] **Step 1: Write failing tests:**
  - `test_knulli_save_to_nextui_gets_rom_name`: `saves/gba/Game.srm` with `Roms/Game Boy Advance (GBA)/Game.gba` on the card plans to `Saves/GBA/Game.gba.sav`.
  - `test_knulli_state_has_no_core_for_nextui`: `saves/gba/Game.state` → skipped with reason mentioning core; the save beside it still moves.
  - `test_save_without_rom_is_left_alone`: no ROM on card → not planned (matches `saves.scan` skipped count).
  - `test_nextui_to_esde_save_loses_sav_naming`: `Saves/GBA/Game.gba.sav` plans to `RetroArch/saves/<core>/Game.srm` only when a core is known, else skipped (reason "needs a core").
- [ ] **Step 2: Run** the new tests; expect FAIL.
- [ ] **Step 3: Implement `plan_saves(...)`.** Scan with the old layout; for each entry compute `target_dir` for the new layout (core from the entry; `ValueError` → skipped with its message); rename to `minui_name` when the new layout is minui and kind is `save` (non-psx, `.srm`), to RetroArch's name (entry `name` already normalized by `scan`) otherwise; ROM names for `minui_name` come from the new layout's folder on disk (`saves.rom_names`).
- [ ] **Step 4: Run** `python -m unittest tests.test_convert -v`; PASS.
- [ ] **Step 5: Commit** `feat(convert): plan save and state moves between layouts`

### Task 3: `cards convert` command

**Files:**
- Modify: `src/sync_roms/convert.py` (add `convert_command(args) -> int`)
- Modify: `src/sync_roms/commands.py` (subparser near `cards rename`, ~line 1301; `words["cards"]` completion list, ~line 1179; dispatch)
- Modify: `src/sync_roms/cli.py` (`"cards"` help text ~line 148; command summary if `cards` subcommands are listed elsewhere)
- Modify: `README.md` (where `cards rename` is documented)
- Modify: `CLAUDE.md` only if a data-files table row needs it (it does not; skip unless tests demand)
- Test: `tests/test_convert.py`, `tests/test_completion.py` (add `convert`)

**Interfaces:**
- Consumes: `plan_roms`, `plan_bios`, `plan_saves`, `apply_moves` from Tasks 1-2; `store.load_manifest([card])`, `store.update_card(name, layout=...)`, `commands.setup_from_flags(manifest, current, device_id, layout)`, `picker.saved_setup`, `ui.confirm`, `ui.fail`.
- Produces: `sync-roms cards convert [CARD] --layout ID [--dry-run] [--yes]`; CARD is the mounted card's folder (default cwd), its basename is the card name, as in `saves._card`.

- [ ] **Step 1: Write failing tests** (temp-dir card + isolated data dir with a saved card entry for device `anbernic-rg35xx-sp`-style Knulli setup):
  - `test_dry_run_moves_nothing_and_keeps_layout`: prints the moves, files and `cards.json` unchanged.
  - `test_convert_moves_files_and_saves_layout`: after `--yes`, files are at NextUI paths and `cards.json` layout is `nextui`.
  - `test_unknown_or_unsupported_layout_fails`: layout the device doesn't run → exit 2, nothing moved.
  - `test_unsaved_card_fails`: no saved layout → exit 2 with the `cards set` hint.
  - `test_conflicts_reported_and_layout_still_saved`: conflicts listed, exit 0, layout saved (sync reconciles the rest).
  - `test_rerun_is_noop`: second run moves nothing and says so.
- [ ] **Step 2: Run** them; expect FAIL.
- [ ] **Step 3: Implement `convert_command` and the wiring.** Order: resolve card and saved setup, validate `--layout` with `setup_from_flags`; plan ROMs, BIOS; print a grouped summary (counts per system, skipped with reasons, leftover old-layout frontend folders such as `gamelist.xml`/`.media` named but untouched); stop on `--dry-run`; confirm unless `--yes`; `apply_moves` for ROMs/BIOS; then `plan_saves` (needs the moved ROMs) and `apply_moves`; finally `store.update_card(name, layout=new)`. Add `convert` to the completion words and help text; add a README line next to `cards rename`.
- [ ] **Step 4: Run** `python -m unittest discover -s tests`; all PASS.
- [ ] **Step 5: Manual check** on a throwaway Knulli-style temp card: `sync-roms cards convert <dir> --layout nextui --dry-run`, then without it; list the result tree and confirm no file lost.
- [ ] **Step 6: Commit** `feat(cards): add convert to move a card's files to another layout`
