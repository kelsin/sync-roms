# Save Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `sync-roms saves stash [CARD]` copies chosen RetroArch saves and states off a card into `~/.sync-roms/saves/`; `sync-roms saves apply [CARD]` copies chosen stashes onto a card, in the folders its layout's RetroArch reads.

**Architecture:** Layout data (`retroarch` in `layouts.json`), a new module `src/sync_roms/saves.py` with pure functions (classify, scan, stash write/read, target paths) and the two interactive flows, wired as a `saves` subcommand in `commands.py`, with help in `cli.py`, completion words, README and CLAUDE.md.

**Tech Stack:** Python 3.12 stdlib, `picker.filter_list`, `ui`, `unittest`. Run tests with `/Users/kelsin/src/sync-roms/.venv/bin/python -m unittest discover -s tests` (the system python lacks boto3).

**Spec:** `docs/superpowers/specs/2026-11-18-save-transfer-design.md` (read it; it is the authority).

## Global Constraints

- `layouts.json` gets, per layout, `"retroarch": {"dir": ..., "saves": ..., "states": ...}` exactly:
  - `esde`: `{"dir": "RetroArch", "saves": "saves/{core}", "states": "states/{core}"}`
  - `knulli`: `{"dir": "saves", "saves": "{system}", "states": "{system}"}`
  - `onion` and `allium`: `{"dir": "Saves/CurrentProfile", "saves": "saves/{core}", "states": "states/{core}"}`
  - `emudeck`: `{"dir": "Emulation/saves/retroarch", "saves": "saves", "states": "states"}`
  Paths are relative to the card root, `/`-separated; `{system}` is the system's folder in that layout (`folders[layout]`), `{core}` a RetroArch core library name subfolder. `--retroarch DIR` replaces `<card>/<dir>` with DIR.
- File kinds by name: `<stem>.srm` → `"save"`; `<stem>.state`, `<stem>.state<digits>`, `<stem>.state.auto` → `"state"`; `<state file name>.png` (e.g. `x.state1.png`, `x.state.auto.png`) → `"thumbnail"`, whose stem is its state's stem. Anything else is ignored. Stem of a state is the name before `.state`; of `.srm` the name before `.srm`.
- ROM stem: file name cut at the last dot. The card's ROMs are every file under `<card>/<roms_dir>/<folders[layout]>` (recursive, hidden subfolders included) for each system with a non-null folder in the layout.
- A save file's game is `(system id, stem)` where system id is the system's `bucket`. In `{system}` folders the system is given by the folder. Otherwise it's the one system whose ROMs include that stem; a stem in no system or several is skipped and counted.
- Stash folder: `<store.data_dir()>/saves/<system>/<stem>/<YYYYMMDD-HHMMSS>-<card>/`, files under their own names plus `stash.json`: `{"system", "game", "card", "layout", "core" (str or null), "stashed" (local ISO time, seconds), "files": [{"name", "kind"}]}` written with `store.write_json(path, data, **store.PRETTY)`. One stash per (game, core) per run; never replaced. If the folder name already exists (same second), add `-2`, `-3`, ...
- Card: `os.path.basename(abspath(CARD or cwd))`, looked up in `store.load_cards()`; it must exist with a `layout` that is in `layouts.json`, else `ui.fail(..., 2)` naming `sync-roms cards set NAME --layout ...`. Folder must exist, else `ui.fail(..., 2)`.
- Apply lists stashes of systems the card syncs: system has a folder in the layout and (device is `"full"`/None or the system is in the device's systems — use `store.load_catalog()` and `store.system_applies`; resolve the device dict like `picker.saved_setup` does).
- Apply never overwrites a differing file without `ui.confirm(..., default=False)`; identical files (same bytes) are skipped silently. `--dry-run` copies nothing and prints what would be copied.
- A stash with `core: null` applied to a `{core}` layout asks the core folder via `picker.filter_list` single mode over existing core subfolders of the target's saves+states folders plus a last row "Type a name…" (then `ui.ask`); with `ui.ASSUME_YES` or no terminal (`ui.has_terminal()` false) that stash is skipped with a warning.
- Both commands need a terminal for their lists: without one, `ui.fail("`saves stash` needs a terminal to pick from", 2)` (same for apply).
- Nothing is ever written to storage. Copy with `shutil.copy2`.
- Match the existing code style: short docstrings, no type hints, `ui.green/yellow/dim/bold` output with emoji like the other commands.
- Conventional Commits; commit messages without any AI attribution or Co-Authored-By lines.

---

### Task 1: Layout data and `saves.py` core functions

**Files:** Modify `src/sync_roms/data/layouts.json`. Create `src/sync_roms/saves.py`, `tests/test_saves.py`.

Pure, testable functions in `saves.py` (names are binding; tests import them):

- `classify(name)` → `(stem, kind)` or `None`, per the kinds constraint.
- `rom_stems(base, layout_name, layout, systems)` → `{stem: {system ids}}` from the card's ROM folders.
- `scan(base, layout_name, layout, systems, retroarch_dir=None)` → `(games, skipped)`: `games` is `{(system, stem): [entry]}` with each entry `{"path": abs path, "name": file name, "kind", "core": str or None, "size", "mtime"}`; `skipped` counts files whose game couldn't be found. `{core}` subfolders are listed one level; missing folders are fine (empty). Follows symlinks (EmuDeck). Thumbnails without their state file are still kept as files of that game.
- `stash_root()` → `os.path.join(store.data_dir(), "saves")`.
- `write_stash(card, layout_name, system, stem, core, entries, now=None, dry_run=False)` → stash folder path; copies the entries' files and writes `stash.json`.
- `load_stashes(systems=None)` → list of `{"dir": path, **stash.json}` for every readable `stash.json` under `stash_root()` (bad JSON or missing keys skipped), filtered to `systems` (a set of ids) when given, sorted by (game casefolded, system) then `stashed` newest first.
- `target_dir(base, layout_name, layout, system, kind, core, retroarch_dir=None)` → abs folder for a file of `kind` (`save` → saves path; `state`/`thumbnail` → states path), filling `{system}` from `system["folders"][layout_name]` and `{core}` from core (raise `ValueError` when the path needs a core and core is None).
- `core_folders(base, layout, retroarch_dir=None)` → sorted names of existing subfolders of the `{core}` parents of saves and states (empty when the layout has no `{core}`).
- `plan_apply(stash, base, layout_name, layout, system, core, retroarch_dir=None)` → list of `(src path, dst path, state)` where state is `"new"`, `"same"` (identical bytes) or `"differs"`.

Tests (tmp dirs via `tempfile.TemporaryDirectory`, `helpers.touch`; patch `store.data_dir` to a tmp dir or rely on the isolated HOME): classify every kind and rejects (`x.sav`, `x.png`, `x.state.bak`); scan an onion-shaped card (`Roms/GBA/Game.zip`, `Saves/CurrentProfile/saves/gpSP/Game.srm`, `.../states/gpSP/Game.state.auto` and `.state.auto.png`, plus an orphan `Other.srm` counted in skipped); scan a knulli card (`roms/gba/Game.zip`, `saves/gba/Game.state1`, `.state1.png`, `.srm`) with core None; scan with `retroarch_dir`; ambiguous stem in two systems is skipped; write_stash + load_stashes round trip (files copied, json fields, same-second suffix `-2`); target_dir for every layout in the real `layouts.json` (with core for `{core}` ones, ValueError without); plan_apply new/same/differs; the shipped `layouts.json` has a `retroarch` entry with `dir`/`saves`/`states` for every layout.

- [ ] Write failing tests, implement, run the full suite green, commit `feat(saves): read and stash retroarch saves per layout`.

### Task 2: `saves stash` / `saves apply` commands, help and docs

**Files:** Modify `src/sync_roms/saves.py`, `src/sync_roms/commands.py`, `src/sync_roms/cli.py`, `README.md`, `CLAUDE.md`. Test `tests/test_saves.py` (extend).

- `saves.stash_command(args)` and `saves.apply_command(args)` per the spec's flows (Stash: games list none on, then files list all on, `extras` columns as the spec says; Apply: stash rows, refusing two stashes of one game with `picker.queue_note` or a printed warning and reopening; core question; conflict confirm; final summary; states warning naming the stash's core). Return exit codes (0 normal, also 0 on Esc/nothing chosen with a `↩️  Nothing stashed`/`↩️  Nothing applied` line).
- `commands.py`: add `"saves"` to `COMMANDS`; parser `saves` with subcommands `stash` and `apply`, each `common(p, card=False)`, positional `card` (`nargs="?"`), `--retroarch DIR`; `second_words()["saves"] = ["stash", "apply"]`. Import `saves` lazily inside small wrapper functions like `collections_edit` does if that's the module's pattern.
- `cli.py`: `SUBCOMMANDS["saves"] = ("stash|apply [CARD] [--retroarch DIR]", "copy RetroArch saves and states off a card, or onto one")` placed after `cards`; `TOPICS["saves"]` explaining both commands, the stash folder, the per-layout folder table, `--retroarch` (Android internal storage copy, EmuDeck real folder), and that states only load in the core they were made with.
- `README.md`: a `### Moving saves between cards (`saves`)` section near the cards docs with the same content, and `--retroarch` in the Options table (tests/test_readme.py checks every parser flag is there).
- `CLAUDE.md`: in the `~/.sync-roms/` row of the Data files table, mention `saves/` (`<system>/<stem>/<stamp>-<card>/` with `stash.json`, written by `saves stash`, read by `saves apply`; personal, never in storage). Keep it one concise clause.
- Tests: drive both flows with `helpers.feed_list` / patched `picker.filter_list` and `ui.confirm`: stash end-to-end on an onion card into the isolated data dir; apply that stash onto a knulli card (lands in `saves/gba/`), onto an esde card (core reused: `RetroArch/states/gpSP/`); a differing target declined keeps the old bytes; dry-run writes nothing; unknown card fails with exit 2; `saves` parses via `commands.run(["saves", "stash", path])`; completion lists `saves`.

- [ ] Write failing tests, implement, run the full suite green, commit `feat(saves): add saves stash and apply commands`.
