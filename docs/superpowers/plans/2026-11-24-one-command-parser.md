# One Command Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every sync-roms command is parsed by one argparse subcommand parser. The old mode flags are gone, the commands have consistent names, and singular/plural aliases work.

**Architecture:** Right now `cli.translate()` rewrites the legacy commands (`sync`, `edit`, `devices`, `upload`, `diff`, `scrape …`, `clean scrapes`, `playlist`, `convert`, `tools install`, `mirror …`) into mode flags. `cli.build_parser`/`check_modes`/`dispatch_mode` then parse and run those flags. Each of those commands becomes a subparser in `commands.build_parser` with its own `fn`, the way `games`, `cards` and the others already work. After that, `translate`, `LEGACY`, `WORDS`, `TYPED`, `BOOL_FLAGS`, `PLAIN_FLAGS`, `VALUE_FLAGS`, `cli.build_parser`, `check_modes` and `dispatch_mode` are deleted. Plain `sync-roms [flags] [CARD]` is `sync`. The parser stays on stdlib argparse, so there is no new dependency.

**Tech Stack:** Python 3.12–3.15, argparse, unittest (`uv run python -m unittest discover -s tests`).

**Spec:** The conversation's agreed proposal, restated in full under Global Constraints.

## Global Constraints

- Use `uv run` for every Python command, and run the tests with stdin closed: `uv run python -m unittest discover -s tests < /dev/null`.
- Code must run on Python 3.12.
- Test modules that import `sync_roms` import `isolate` first (directly or via `helpers`).
- Conventional Commits, lowercase and imperative. Each commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never hand-edit `__version__`, `CHANGELOG.md` or `.release-please-manifest.json`.
- Renames:

  | Old | New |
  |---|---|
  | `convert [DIR]` (disc images) | `prepare [DIR]` |
  | `tools install` | `install` |
  | `clean scrapes` | `scrape clean` |
  | `cards convert` | `cards layout` |
  | `edit`, `games edit`, `cards edit` | `edit` only |

- `doctor --fix` runs `install` (`external.install_tools_command()`) when tools are missing.
- Remove every old mode flag, with no compatibility path: `-e/--edit`, `--upload`, `-c/--clean-scrapes`, `--m3u`, `--cd`, `--chd`, `--install-tools`, `--mirror`, `--use-mirror`, `--clear-mirror`, `--diff`, `--devices`, `--device-id`, `--scrape`, `--scrape-match`, `--scrape-review`, `--scrape-missing`, `--scrape-art`. Typing one is an argparse usage error (exit 2).
- Aliases (alias → main name):

  | Alias | Main name |
  |---|---|
  | `card` | `cards` |
  | `game` | `games` |
  | `set` | `sets` |
  | `collection` | `collections` |
  | `theme` | `themes` |
  | `save` | `saves` |
  | `device` | `devices` |
  | `layout` | `layouts` |
  | `playlists` | `playlist` |
  | `scrapes` | `scrape` |
  | `downloads` | `download` |
  | `umount` | `unmount` (kept) |

  Second word: `games set` → `games sets`.
- Completion and the help command list show main names only. `help ALIAS` and `ALIAS --help` show the main command's help.
- Keep each command's existing flags and their checks (`--replace`, `--system`, `--for onion|spruce|both`, `--workers`, `--all`, `--retry`, `--fill-media`, `--skip-media`, `--translated`, `--set-credentials`, `--json`, `-n/--dry-run`, `-y/--yes`, `-a/--ask`, `--device`, `--layout`, `--guest`, `--no-clean`, `--no-delete`, `--no-eject`, `--version`, `-h/--help`). Their error messages keep naming the command as typed in its main form (`scrape art`, never a flag).

## Review Focus

1. Plain `sync-roms`, `sync-roms /Volumes/CARD -n` and `sync-roms -n -y /Volumes/CARD` still sync. Global flags (`--profile`, `--root`, `--quiet`, `--verbose`) work before or after any command or alias. Test in Task 1.
2. A card folder named like a command or alias: a bare word that is a command (or alias) is the command, while a path with a separator (`./saves`, `/Volumes/card`) is a card to sync. Test in Task 1.
3. `scrape match gba "-weird.zip" 123`: ROM or game values that start with `-` are values, not options. Test in Task 2.
4. `--quiet` must not discard the stdout of data commands typed as aliases (`device`, `layout ID`, `card list`). Test in Task 4.
5. An old flag (`sync-roms --edit`, `sync-roms --m3u /x`) exits 2 with a usage error. It must never be read as a card folder or start a sync. Test in Task 3.

---

### Task 1: Move the plain commands into `commands.build_parser`, add the default `sync`, `prepare`, `install` and `doctor --fix`

**Files:**
- Modify: `src/sync_roms/commands.py` (`COMMANDS`, `build_parser`, `run`, `doctor_cmd`, new fns)
- Modify: `src/sync_roms/cli.py` (`run`: routing; `sync_card` keeps its body; `SUBCOMMANDS`/`TOPICS` entries for `convert`→`prepare`, `tools`→`install`)
- Modify: `src/sync_roms/upload.py`, `diff.py`, `m3u.py`, `chd.py`, `mirroring.py` (read `args.dir`/`args.action` instead of `args.upload`/`args.diff`/`args.m3u`/`args.chd`/`args.mirror`/`args.use_mirror`/`args.clear_mirror`; `chd.py`'s messages say `prepare` and `install`)
- Modify: `src/sync_roms/spruce_themes.py`, `install.py` (their "tools install" messages say `install`)
- Test: `tests/test_commands.py`, `tests/test_chd.py`, `tests/test_spruce_themes.py`, `tests/test_cli_sync.py`

**Interfaces:**
- Produces: these subparsers in `commands.build_parser`, each setting `fn`:
  - `sync [base_dir]`, with `-n -y -a --json --device --layout --guest --no-clean --no-delete --no-eject`; `fn=sync_cmd`, which calls `cli.sync_card(args)` (lazy import)
  - `edit` (`-y`); `fn=edit_cmd`
  - `devices [device_id] [--json]`; `fn=devices_cmd`, which calls `cli.list_devices`
  - `upload [dir] [-n -y --replace]`
  - `diff [dir] [--system ID] [--json] [-y]`
  - `playlist [dir] [-n -y]`
  - `prepare [dir] [-n -y]`; `fn` calls `chd.chd_command(args)`
  - `install`; `fn` calls `external.install_tools_command()`
  - `mirror [dir] [-n -y]` / `mirror use DIR` / `mirror clear`. Build it as one parser: `action` positional with nargs `?` and choices `use`/`clear`, plus `dir`. A first word that is neither `use` nor `clear` is the `dir`; a hand check in `mirror_cmd` handles this, because argparse choices can't do it.
- Produces: `commands.prepare_storage(args, need_root=True) -> None`. It is the old `dispatch_mode` preamble: `usersettings.ensure_bucket()`; with `need_root`, fail with exit 3 when `runtime.ROOT` is set and missing; `inventory.prepare()` unless `args.json`. `edit` passes `need_root=False`. Every storage command calls it before its work.
- Produces: `commands.refresh_mirror(code, args) -> int`. It is the old post-edit step: refresh the saved mirror after a successful non-dry run. `edit` and Task 2's `scrape clean` use it.
- Produces: `doctor --fix`. After the checks, when any of `external.TOOL_FORMULAE` is missing, it calls `external.install_tools_command()` and returns its code.
- Produces: in `cli.run`, after `extract_globals`, find the first word that isn't a leading bool flag. When that word is not a command name (in `commands.COMMANDS`, `help`, or later an alias), insert `sync` before it. Leading flags move behind the command, as `run` does today. `--version` at the front still prints the version.
- Every command's `--dry-run`-has-no-effect check stays in `commands.run`'s list: add `edit`, `install`, `mirror clear`, `devices` and `diff`. `--json` on `sync` without `--dry-run` fails with exit 2 and the old message, reworded for the commands that take `--json`.

- [ ] **Step 1: Write the failing tests** in `tests/test_commands.py`, class `PlainCommands`. Mock the fn targets (`cli.sync_card`, `upload.upload_command`, `diff.diff_command`, `m3u.m3u_command`, `chd.chd_command`, `external.install_tools_command`, `mirroring.mirror_command`, `edit.edit_manifest`) and drive `cli.run([...])`:
  - `test_bare_card_is_sync`: `run(["-n", "/tmp/card"])` calls `sync_card` with `base_dir == "/tmp/card"` and `dry_run is True`. `run([])` calls `sync_card` with `base_dir is None`.
  - `test_path_named_like_command_is_sync`: `run(["./saves"])` calls `sync_card` with `base_dir == "./saves"`.
  - `test_prepare_and_install`: `run(["prepare", "/x"])` calls `chd_command` with `args.dir == "/x"`. `run(["install"])` calls `install_tools_command`.
  - `test_removed_names_fail`: each of `["convert", "/x"]`, `["tools", "install"]`, `["games", "edit"]`, `["cards", "edit"]` raises `SystemExit` with code 2. (`convert` becomes a card path, so this one must assert it fails as "isn't a command or a folder" with code 2.)
  - `test_mirror_forms`: `mirror` → `action is None, dir is None`; `mirror /m` → `dir == "/m"`; `mirror use /m` → `action == "use", dir == "/m"`; `mirror clear` → `action == "clear"`.
  - `test_doctor_fix_installs_missing_tools`: with `external.find_tool` patched to return None, `run(["doctor", "--fix"])` calls `install_tools_command` once. With every tool found, it does not call it.
  - `test_global_flags_any_position`: `run(["upload", "/x", "--root", "/r"])` and `run(["--root", "/r", "upload", "/x"])` both set `runtime.OVERRIDES["root"] == "/r"`. Drive this through `cli.sync` with `sys.argv` patched.
- [ ] **Step 2: Run and confirm they fail.** Run: `uv run python -m unittest tests.test_commands.PlainCommands < /dev/null`. Expected: failures and errors (unknown commands `prepare`/`install`, no `dir` attribute).
- [ ] **Step 3: Implement** the subparsers, `prepare_storage`, `refresh_mirror`, the `sync` default in `cli.run`, `doctor --fix`, the attribute renames in the five modules, and the message renames (`grep -rn "tools install\|sync-roms convert\|\`convert" src`). Drop `devices`, `upload`, `diff`, `playlist`, `convert`, `tools`, `mirror` and `edit` from `LEGACY`, and add them to `commands.COMMANDS` (`prepare` and `install` too). The legacy path then serves only `scrape` and `clean`. Before writing the `sync` subparser, read every `args.` use in `cli.sync_card` and its callees so that the subparser defines each attribute.
- [ ] **Step 4: Run the new tests, then the whole suite.** Fix existing tests that used the old forms, and move each to the command form. Expected: `OK`.
- [ ] **Step 5: Commit.** Message: `refactor(cli): parse sync, edit and the plain commands as subcommands; rename convert to prepare and tools install to install`

### Task 2: Move `scrape` into `commands.build_parser` and add `scrape clean`

**Files:**
- Modify: `src/sync_roms/commands.py`, `src/sync_roms/cli.py` (delete `LEGACY`'s scrape/clean entries; `SUBCOMMANDS`/`TOPICS`: `clean` removed, `scrape` usage gains `clean`)
- Modify: `src/sync_roms/scrape_online.py`, `scrape_review.py`, `scrape_art.py`, `scrape_files.py` (only if they read a removed attribute)
- Test: `tests/test_scrape_cli.py`, `tests/test_cli_errors.py`, `tests/test_scrape_state.py`

**Interfaces:**
- Consumes: `commands.prepare_storage`, `commands.refresh_mirror` (Task 1).
- Produces: a `scrape` parser with optional subcommands. Bare `scrape [SYSTEM]` takes `--system --retry --all --fill-media --skip-media --set-credentials -n -y`. The subcommands are `match SYSTEM ROM GAME [--translated --skip-media -n -y]`, `review [SYSTEM]`, `missing [SYSTEM] [--system --all]`, `art [SYSTEM] [--system --for {onion,spruce,both} (default both) --workers N --replace -n -y]` and `clean [-n -y]` (fn: `scrape_files.clean_scrapes`, then `refresh_mirror`). Each fn sets `args.system` from whichever of the positional or `--system` was given, as `check_modes` did.
- Keep these checks, with the same messages: two systems given; a system that looks like a path; `--set-credentials` must be alone; `--skip-media` parsed through `scrape_online._check_skip`; `--dry-run` has no effect on `scrape missing`/`scrape review`.
- Values after `scrape match` that start with `-` stay values. Move the `Parser.literal` mechanism from `cli.Parser` into `commands`' `Parser`, keyed on the three words after `scrape match`.

- [ ] **Step 1: Write the failing tests** in `tests/test_scrape_cli.py`:
  - `test_scrape_forms`: `scrape` → system None; `scrape gba` → `"gba"`; `scrape --system gba` → `"gba"`; `scrape missing gba` → missing_command with system `"gba"`; `scrape art gba --for spruce` → target `"spruce"`; `scrape art` → target `"both"`.
  - `test_scrape_two_systems_fails`: `scrape gba --system nes` exits 2.
  - `test_scrape_match_dash_values`: `scrape match gba -odd.zip -5` gives `system, rom, game == ("gba", "-odd.zip", "-5")`.
  - `test_scrape_clean`: `scrape clean -n` calls `clean_scrapes` with `dry_run` True, and `clean scrapes` exits 2.
  - `test_set_credentials_alone`: `scrape --set-credentials --retry` exits 2.
- [ ] **Step 2: Run and confirm they fail.** Run: `uv run python -m unittest tests.test_scrape_cli < /dev/null`. Expected: failures.
- [ ] **Step 3: Implement**, and port the existing tests in these three files to the command forms.
- [ ] **Step 4: Run the whole suite.** Expected: `OK`.
- [ ] **Step 5: Commit.** Message: `refactor(cli): parse scrape as subcommands and move clean scrapes to scrape clean`

### Task 3: Delete the legacy flag parser

**Files:**
- Modify: `src/sync_roms/cli.py`: delete `LEGACY`, `WORDS`, `TYPED`, `BOOL_FLAGS`, `PLAIN_FLAGS`, `VALUE_FLAGS`, `translate`, `cli.Parser`, `build_parser`, `check_modes` and `dispatch_mode`. Simplify `run` and `is_data_command` (no `--devices`). Keep `--version`/`-h` at top level.
- Modify: `src/sync_roms/commands.py`: `second_words()` built only from the parser's own subparsers (walk `build_parser()`), and `all_flags()` walks only `build_parser()` (drop the `--device-id` exclusion). `ui.py`: drop its `WORDS` use if it was the legacy one.
- Modify: `src/sync_roms/themeart.py` only if its `translate(` is `cli.translate` (check first; it may be unrelated).
- Test: `tests/test_cli_errors.py`, `tests/test_commands.py`, `tests/test_scripting.py`, `tests/test_cli_sync.py`, `tests/test_completion.py`

**Interfaces:**
- Consumes: every command now has its own subparser (Tasks 1–2).
- Produces: `commands.second_words() -> dict[str, list[str]]`, same shape as today.

- [ ] **Step 1: Write the failing test** `test_old_flags_are_usage_errors` in `tests/test_cli_errors.py`. Each of `--edit`, `-e`, `--upload`, `-c`, `--clean-scrapes`, `--m3u`, `--cd`, `--chd`, `--install-tools`, `--mirror`, `--use-mirror /x`, `--clear-mirror`, `--diff`, `--devices`, `--scrape`, `--scrape-match a b c`, `--scrape-review`, `--scrape-missing`, `--scrape-art`, alone and followed by `/tmp`, exits 2 with `cli.sync_card` never called. Add `test_completion_has_no_old_flags`: none of those strings is in `commands.all_flags()`.
- [ ] **Step 2: Run and confirm it fails** (the flags still parse). Run: `uv run python -m unittest tests.test_cli_errors < /dev/null`.
- [ ] **Step 3: Delete the code listed above**, then port or delete the tests that exercised `translate`/`check_modes` (keep the behaviors they checked, now driven through `cli.run`). Confirm the cleanup with `grep -rn "translate(\|check_modes\|LEGACY\|PLAIN_FLAGS\|VALUE_FLAGS\|TYPED\|--scrape-\|--m3u\|--install-tools" src tests`: the output must be empty except for unrelated `translate(` hits in `themeart.py` and the fixtures.
- [ ] **Step 4: Run the whole suite.** Expected: `OK`.
- [ ] **Step 5: Commit.** Message: `refactor(cli)!: remove the old mode flags and the legacy parser`

### Task 4: Aliases, `cards layout`, help and completion

**Files:**
- Modify: `src/sync_roms/cli.py` (`ALIASES`, `SUBCOMMANDS`, `TOPICS`, `run`, `is_data_command`)
- Modify: `src/sync_roms/commands.py` (`aliases=` on each subparser; `cards convert`→`cards layout`; `games sets` gets `aliases=["set"]`; `run`'s bare-`cards` shortcut accepts `card`)
- Modify: `src/sync_roms/convert.py` (docstrings and messages: `cards layout`)
- Test: `tests/test_commands.py`, `tests/test_completion.py`

**Interfaces:**
- Produces: `cli.ALIASES: dict[str, str]`, alias → main name, exactly the table in Global Constraints. `commands.build_parser` reads it, so the two can't drift: `aliases=[a for a, m in cli.ALIASES.items() if m == name]`.
- Produces: `cli.canonical(word) -> str` (`ALIASES.get(word, word)`), used by `run`'s routing, `help`, `-h` topic lookup, `is_data_command` and `commands.run`'s dry-run name check. args.command may hold the alias, so normalize it.

- [ ] **Step 1: Write the failing tests:**
  - `test_every_alias_runs_main_command`: for each alias in `cli.ALIASES`, `commands.build_parser().parse_args([alias, …minimal args…]).fn` is the main command's fn. Use `card list`, `game list --card X`, `set edit`, `collection edit`, `theme pick`, `save manage`, `device`, `layout`, `playlists /x`, `scrapes missing`, `downloads pico8`, `umount`.
  - `test_games_set_alias`: `games set list --card X` reaches `games_sets`.
  - `test_cards_layout`: `cards layout C --layout onion` calls `convert.convert_command`, and `cards convert` exits 2.
  - `test_help_for_alias`: `help card` and `card --help` print the same text as `help cards`.
  - `test_quiet_keeps_alias_data_stdout`: `is_data_command(["device"])`, `is_data_command(["layout", "x"])` and `is_data_command(["card", "list"])` are True.
  - `test_completion_main_names_only`: the bash completion script contains `cards`, not ` card ` as a command word, and `second_words()["cards"]` contains `layout`, not `convert`.
- [ ] **Step 2: Run and confirm they fail.** Run: `uv run python -m unittest tests.test_commands tests.test_completion < /dev/null`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole suite.** Expected: `OK`.
- [ ] **Step 5: Commit.** Message: `feat(cli): add singular and plural command aliases and rename cards convert to cards layout`

### Task 5: README, CLAUDE.md and the README test

**Files:**
- Modify: `README.md`. The Commands table's last column becomes `Aliases` (from `cli.ALIASES`) and the "Every mode is a command" line is reworded. Remove the "(old flags)" row from Options. Rename the rows and sections for `prepare` (was `convert`, anchor `#preparing-disc-images-prepare`), `install`, `scrape clean`, `cards layout` and `edit`, and fix every link to the renamed anchors.
- Modify: `CLAUDE.md`. Rewrite the CLI section: every command is a subparser in `commands.build_parser` listed in `commands.COMMANDS`, with its help in `cli.TOPICS` and its aliases in `cli.ALIASES`; plain `sync-roms [CARD]` is `sync`. Replace `clean scrapes` with `scrape clean`, and `convert` with `prepare` where it means disc images (the Storage table's scrapes row, the CHD mentions).
- Test: `tests/test_readme.py`

- [ ] **Step 1: Write the failing test** `test_commands_table_aliases_match`. Parse the Commands table's `Aliases` column into `{alias: command word}` and compare it with `cli.ALIASES`. Also check that every `cli.SUBCOMMANDS` name appears in the table's first column.
- [ ] **Step 2: Run and confirm it fails.** Run: `uv run python -m unittest tests.test_readme < /dev/null`.
- [ ] **Step 3: Edit README.md and CLAUDE.md.** Afterwards, `grep -n "tools install\|clean scrapes\|cards convert\|games edit\|cards edit\|--m3u\|--install-tools\|Old flag" README.md CLAUDE.md` must return nothing.
- [ ] **Step 4: Run the whole suite.** Expected: `OK`.
- [ ] **Step 5: Commit.** Message: `docs: describe the renamed commands and their aliases`
