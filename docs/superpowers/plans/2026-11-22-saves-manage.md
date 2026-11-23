# `saves manage` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms saves manage`, one interactive screen to inspect, label, move (system only), prune and delete
the stashes `saves stash` made; `saves apply` shows each stash's label.

**Architecture:** A new module `src/sync_roms/saves_manage.py` holds the stash operations (pure filesystem functions,
unit-tested) and `manage_command(args)`, a loop around `picker.filter_list` in multi mode whose hotkeys call those
operations. It reuses `saves.stash_root`, `saves.load_stashes`, `saves._counts`, `saves._unsafe`, `saves.STASH_KEYS`
and `muos_saves.is_pickles`/`stash_rel`. CLI wiring follows `saves stash`/`apply`.

**Tech Stack:** Python 3.12+, `uv`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-22-saves-manage-design.md`

## Global Constraints

- Always run Python through `uv run` (`uv run python -m unittest discover -s tests`). Code must run on Python 3.12.
- Test modules import `isolate` first (directly or via `helpers`), as `tests/test_saves.py` does.
- Personal JSON is written with `store.write_json(path, data, **store.PRETTY)`.
- Commits: Conventional Commits, lowercase imperative (`feat(saves): ...`), ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never act on a path outside `saves.stash_root()` (`os.path.realpath` check).
- Delete confirm: `ui.confirm(f"Delete {n} stash(es)? This can't be undone.", default=False)`, skipped when
  `ui.ASSUME_YES`.
- `--dry-run`: nothing on disk changes; each action prints what it would do (dim); the closing line says "Would ...".
- The game of a stash never changes.

## Review Focus

1. A stash folder deleted or edited by hand while the screen is open: the action on it warns (`OSError`) and the rest
   go on; the screen doesn't crash. → Task 1 `test_delete_warns_and_goes_on_when_a_folder_is_gone`.
2. Moving into a game folder that already has a stash folder of the same name: suffix `-2`, never overwrite.
   → Task 1 `test_move_suffixes_a_taken_folder`.
3. Prune with unreadable rows toggled: unreadable rows are never picked by prune (they are not stashes of a game).
   → Task 1 `test_prune_skips_unreadable`.
4. A muOS stash moved to a system with no muOS folder: refused, the stash untouched.
   → Task 1 `test_move_refuses_a_pickles_stash_without_muos_folder`.
5. A `stash.json` symlinked or a folder path escaping `stash_root()`: refused. → Task 1
   `test_delete_refuses_outside_stash_root`.

---

### Task 1: Stash operations

**Files:**
- Create: `src/sync_roms/saves_manage.py`
- Test: `tests/test_saves_manage.py` (imports `isolate`, `helpers`; makes stashes with `saves.write_stash` like
  `CommandTest.stash` in `tests/test_saves.py`)

**Interfaces:**
- Produces:
  - `list_rows() -> list[dict]`: every readable stash as `load_stashes()` returns it plus
    `"missing": [names listed but not in the folder]`, `"extra": [files in the folder not listed, stash.json excluded]`,
    `"size": total bytes of present files`, `"unreadable": False`; then each unreadable stash folder (a folder under
    `stash_root()/<system>/<game>/` that has files but whose `stash.json` is absent or rejected by `load_stashes`) as
    `{"dir", "unreadable": True, "rel_dir": path relative to stash_root(), "files": [names], "size"}`. Readable rows in
    `load_stashes()` order, unreadable ones after, by `rel_dir`.
  - `set_label(row, text, dry_run=False) -> None`: `text.strip()` stored as `"note"` in the row's `stash.json`; empty
    removes the key. Updates `row["note"]`.
  - `move(row, system, catalog_systems, dry_run=False) -> str | None`: system is a systems.json entry; returns the new
    folder, `None` when the row is already in that system; raises `ValueError(message)` when refused (unreadable row;
    Pickles stash and `system["folders"].get("muos")` falsy). Moves the folder to
    `stash_root()/<bucket>/<game>/<basename>` (`-2`, `-3`, ... when taken), rewrites `system`, and for a Pickles stash
    each file's `rel` first part to `system["folders"]["muos"]`; removes the old game and system folders when empty.
    Updates the row in place.
  - `delete(rows, dry_run=False) -> int`: removes each row's folder (`shutil.rmtree`) and then its game and system
    folders if empty; a row whose `realpath` isn't inside `realpath(stash_root())` raises `ValueError`; an `OSError`
    on one row is `ui.warn`ed and skipped. Returns the number deleted.
  - `prune_picks(rows, keep) -> list[bool]`: per row, True for readable stashes beyond the newest `keep` of their
    (system, game, `muos_saves.stash_rel`) group (by `stashed`), False otherwise.
  - `inside(path) -> bool`: `realpath(path)` is under `realpath(stash_root())` (and not equal to it).

- [ ] **Step 1: Write the failing tests** in `tests/test_saves_manage.py`, class `OpsTest(helpers.Cmd)` (or a
  `unittest.TestCase` using the isolated data folder):
  - `test_list_rows_reports_missing_extra_and_size`: a stash with `Game.srm` (4 bytes) and `Game.state.auto`; remove
    `Game.state.auto`, add `junk.txt` → row `missing == ["Game.state.auto"]`, `extra == ["junk.txt"]`, `size == 4`.
  - `test_list_rows_lists_unreadable_last`: a folder `gba/Game/20260101-000000-X/` with `Game.srm` and a `stash.json`
    of `"{"` → last row has `unreadable is True`, `rel_dir == "gba/Game/20260101-000000-X"`, `files == ["Game.srm",
    "stash.json"]`.
  - `test_set_label_writes_and_removes`: `set_label(row, " boss ")` → stash.json `note == "boss"`;
    `set_label(row, "")` → no `note` key; with `dry_run=True` the file is unchanged.
  - `test_move_rewrites_system_and_keeps_game_and_note`: gba stash with note moved to gb → folder now
    `stash_root()/gb/Game/<same basename>`, stash.json `system == "gb"`, `game == "Game"`, note kept, old
    `stash_root()/gba` gone.
  - `test_move_suffixes_a_taken_folder`: same basename already in `gb/Game/` → new folder ends with `-2`, the other
    untouched.
  - `test_move_same_system_returns_none`.
  - `test_move_pickles_switches_rel`: stash files with `rel: "GBA/Hacks"`, target system `folders["muos"] == "GB"` →
    every `rel == "GB/Hacks"`.
  - `test_move_refuses_a_pickles_stash_without_muos_folder`: `ValueError`, folder and stash.json unchanged.
  - `test_delete_removes_folder_and_empty_parents`: two stashes of one game, delete one → game folder stays; delete the
    other → `gba/` gone, `stash_root()` stays.
  - `test_delete_refuses_outside_stash_root`: a row whose `dir` is a temp folder elsewhere → `ValueError`, folder kept.
  - `test_delete_warns_and_goes_on_when_a_folder_is_gone`: first row's folder removed beforehand → returns 1, second
    deleted, a warning printed.
  - `test_delete_dry_run_keeps_everything`.
  - `test_prune_picks_all_but_newest`: three stashes of one game (stashed 01, 02, 03) and one of another game,
    `keep=1` → only the 01 and 02 rows True.
  - `test_prune_skips_unreadable`: an unreadable row → False.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_saves_manage -v`. Expected: FAIL (`ModuleNotFoundError:
  sync_roms.saves_manage` or missing attributes).

- [ ] **Step 3: Implement** the functions above in `src/sync_roms/saves_manage.py`. Write stash.json with
  `store.write_json(..., **store.PRETTY)`; move with `os.makedirs` + `os.rename` (same filesystem); collect unreadable
  folders by walking `stash_root()` to depth 3 and subtracting the `dir`s `load_stashes()` returned.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_saves_manage -v`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(saves): add stash label, move, prune and delete operations`.

### Task 2: The `saves manage` screen and its CLI wiring

**Files:**
- Modify: `src/sync_roms/saves_manage.py` (add `manage_command`)
- Modify: `src/sync_roms/commands.py` (`saves_manage` wrapper next to `saves_stash`/`saves_apply` ~line 1220;
  `second_words()["saves"]` → `["stash", "apply", "manage"]`; parser ~line 1385: `manage` gets `common(p, card=False)`
  only, no CARD, no `--retroarch`)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS["saves"]` usage `stash|apply|manage ...`; `TOPICS["saves"]` gains a
  `sync-roms saves manage [--dry-run] [--yes]` line and a short paragraph on its keys)
- Modify: `README.md` (`saves` row ~line 181, and a paragraph in "Moving saves between cards (`saves`)" ~line 464 on
  `manage`: list, keys, delete can't be undone, `--dry-run`, `--yes`)
- Test: `tests/test_saves_manage.py` (class `ManageCommandTest(helpers.Cmd)` with the same `lists()` fake of
  `picker.filter_list` as `tests/test_saves.py` `CommandTest`, `ui.has_terminal` patched True, `picker._Session`
  patched); `tests/test_saves.py` `SavesCliTest.test_completion_and_words` expects `["stash", "apply", "manage"]`.

**Interfaces:**
- Consumes: Task 1's `list_rows`, `set_label`, `move`, `delete`, `prune_picks`.
- Produces: `manage_command(args) -> int`.

Screen (follow the loop in `cardshare.py` ~line 198: `session` dict, re-enter `filter_list` after each hotkey,
tuple result = `(key, index)`, `session["sel"]` holds the toggles):
- `picker.filter_list("🗂️ Stashed saves", labels, multi=True, initial=[False]*n, esc_asks=False, extras=...,
  session=session, hotkeys=("enter", "m", "p", "d"), on_note=..., note_text=..., hint="? help · Space toggle · Enter
  files · w label · m move · p prune · d delete · Esc done", key_help=[...])`. Label: game (+ ` · <rel>` for Pickles),
  unreadable: `rel_dir`. Extras: system name (dim), `from <card>`, `stashed[:16]` with `T`→space (dim),
  `saves._counts(kinds)`, `ui.human_size(size)`, core (cyan), `N missing`/`unreadable` (red), note (dim).
- Targets of `m`/`d`: the toggled rows, else the highlighted one.
- `enter`: `picker.filter_list(f"💾 {game} files", ...)` single mode, rows = files (`<rel>/name`), extras kind, size,
  mtime, `missing` (red) / `extra` (dim); result ignored.
- `w` (`on_note`): `set_label`; returns a message; refused (message) on unreadable rows.
- `m`: system picker over the catalog's systems (`store.load_catalog()["systems"]`, names `s.get("name", s["bucket"])`,
  cursor on the current one), then `move` per target; `ValueError` → `picker.queue_note` (fall back to `ui.warn`).
- `p`: `ui.ask("✂️  Keep how many per game? [1] ")`, empty → 1, not a positive int → note; then
  `session["sel"] = prune_picks(rows, keep)` and a note "Picked N stash(es) to delete: press d".
- `d`: print the targets (game, system, date, note), confirm (Global Constraints), `delete`; deleted rows leave the
  list, `session["sel"]` rebuilt for the remaining rows.
- Esc (`None`) or plain Enter-on-states result: leave. Closing line: `🗑️  Deleted N stash(es), moved M, labelled L`
  (green), or `🧪 Would delete ...` with `--dry-run`; `↩️  Nothing changed` (yellow) when all zero.
- No stashes: `↩️  No stashed saves in <stash_root()>` (yellow), exit 0. No terminal:
  `ui.fail("`saves manage` needs a terminal to pick from", 2)`.

- [ ] **Step 1: Write the failing tests** in `ManageCommandTest`, each driving `run_cmd("saves", "manage", ...)` with
  `lists(...)` answers (a tuple `("d", 0)` for a hotkey, `None` to leave) and `ui.ask`/`ui.confirm` patched:
  - `test_no_stashes_says_so`: exit 0, output has "No stashed saves".
  - `test_delete_highlighted_after_confirm`: answers `("d", 0)`, `None`; confirm True → stash folder gone, output
    "Deleted 1 stash(es)".
  - `test_delete_declined_keeps_it`: confirm False → folder kept, "Nothing changed".
  - `test_yes_skips_the_question`: `--yes`, confirm patched to raise → folder gone.
  - `test_dry_run_deletes_nothing`: `--dry-run` → folder kept, output "Would delete 1".
  - `test_move_to_another_system`: answers `("m", 0)`, the gb index in the system list, `None` → stash under `gb/`.
  - `test_prune_then_delete`: three stashes of one game; answers `("p", 0)`, then a callable asserting
    `session` picks reach the delete: `("d", 0)`, `None`; ask "1", confirm True → only the newest left.
  - `test_enter_lists_files`: answers `("enter", 0)`, `None` (files list), `None` → the second `calls` entry's labels
    are the stash's file names.
  - `test_needs_a_terminal`: `has_terminal` False → exit 2.
  - Update `SavesCliTest.test_completion_and_words` to `["stash", "apply", "manage"]` and assert
    `"sync-roms saves manage" in cli.TOPICS["saves"]`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_saves_manage tests.test_saves -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `manage_command` and the wiring above.

- [ ] **Step 4: Run** the full suite `uv run python -m unittest discover -s tests`. Expected: PASS (incl.
  `tests/test_readme.py`).

- [ ] **Step 5: Try it by hand**: `uv run sync-roms saves manage --dry-run` in a terminal against the real data folder
  (dry run only: it must change nothing), check the list, Enter, `p`, `d` prompts.

- [ ] **Step 6: Commit** `feat(saves): add saves manage to inspect, label, move, prune and delete stashes`.

### Task 3: Labels in `saves apply`

**Files:**
- Modify: `src/sync_roms/saves.py` (`apply_command` extras, ~line 527: append `(stash.get("note", ""), "dim")`)
- Modify: `README.md` `apply` paragraph ~line 464 and `cli.TOPICS["saves"]` apply lines: "shows each stash's label
  (set in `saves manage`)".
- Test: `tests/test_saves.py` `ApplyCommandTest`

- [ ] **Step 1: Write the failing test** `test_apply_shows_the_label`: stash, then set `"note": "boss"` in its
  stash.json; answers `None` → `self.calls[0][2]["extras"][0][-1] == ("boss", "dim")`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_saves -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the extra column.
- [ ] **Step 4: Run** `uv run python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(saves): show stash labels in saves apply`.
