# Format Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms format [--dry-run]` erases an SD card as exFAT or FAT32 with a picked volume label.

**Architecture:** New module `src/sync_roms/format_card.py` (not `format.py`: it would shadow the builtin where imported) reusing `flash.py`'s disk helpers, wired as a subparser like `flash`.

**Tech Stack:** Python 3.12+, `diskutil`, unittest. Run everything through `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-25-format-command-design.md`

## Global Constraints

- macOS only (`sys.platform != "darwin"` → `❌ format needs macOS`, exit 1).
- Partition scheme always `MBR`. Command: `["diskutil", "eraseDisk", "ExFAT"|"FAT32", label, "MBR", disk.id]`.
- FAT32: label uppercased, ≤ 11 characters, none of `"*+,./:;<=>?[\]|`. exFAT: ≤ 15 characters, none of `"*/:<>?\|`. No control characters, not empty/blank.
- Confirmation: typing the disk id (stripped) exactly; `--yes` never skips it.
- Test modules import `isolate` first (directly or via `helpers`); run tests with stdin closed: `uv run python -m unittest ... < /dev/null`.
- Conventional Commits; never touch `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.

## Review Focus

- A card swapped after the pick (same disk id, other size/name) → nothing erased, `❌ diskN changed since you picked it: not formatted`. (Task 1 test.)
- Esc in any picker or the typed-label prompt left empty → exit 0, nothing run. (Task 1 tests.)
- Card name with lowercase/space (`Odin SD`) under FAT32 → offered as `ODIN SD`; under exFAT as `Odin SD`; duplicates after uppercasing appear once. (Task 1 test.)
- `diskutil eraseDisk` failing → exit 1 with its stderr shown, no "✅". (Task 1 test.)
- Boot disk or storage disk can't be identified → stop before listing cards. (Task 1 test.)

---

### Task 1: `format_card.py`

**Files:**
- Create: `src/sync_roms/format_card.py`
- Test: `tests/test_format_card.py`

**Interfaces:**
- Consumes: `flash.disks_of(path) -> set`, `flash.external_disks(exclude) -> [Disk]`, `flash._disk_label(disk)`, `flash._same(a, b)`, `flash._run(cmd, capture=True)`, `flash._sudo()`, `flash.HINT`; `store.load_cards()`, `store.repo_json("layouts")`; `picker.filter_list`; `ui.ask`, `ui.failure`, `ui.red/yellow/green`, `ui.human_size`.
- Produces:
  - `FILESYSTEMS = [("exFAT", "ExFAT"), ("FAT32", "FAT32")]` (shown name, diskutil name)
  - `clean_label(label: str, fs: str) -> str` (FAT32 uppercases; strips surrounding whitespace)
  - `label_problem(label: str, fs: str) -> str | None` (None when valid, else a short reason)
  - `label_choices(fs: str) -> list[str]` — card names sorted (case-insensitive), then layout names uppercased in `layouts.json` order, each through `clean_label`, invalid ones dropped, duplicates dropped keeping first.
  - `erase_command(disk_id: str, fs: str, label: str) -> list[str]`
  - `run(args) -> int`

- [ ] **Step 1: Write failing tests** for the helpers:
  - `label_choices("FAT32")` with cards `{"MIYOOFLIP":…, "Odin SD":…, "averyverylongname":…}` and layouts `["esde", "spruce"]` == `["MIYOOFLIP", "ODIN SD", "ESDE", "SPRUCE"]`; with `"exFAT"` == `["MIYOOFLIP", "Odin SD", "esde"→"ESDE", "SPRUCE"]` i.e. `["MIYOOFLIP", "Odin SD", "ESDE", "SPRUCE"]` (`averyverylongname` is 17 chars: dropped from both).
  - a card named `spruce` with FAT32 gives `SPRUCE` once.
  - `label_problem("ROMS.1", "FAT32")` is not None; `label_problem("ROMS.1", "exFAT")` is None; `label_problem("A"*12, "FAT32")` not None; `label_problem("A"*15, "exFAT")` None; `label_problem("  ", "exFAT")` not None.
  - `erase_command("disk4", "FAT32", "SPRUCE") == ["diskutil", "eraseDisk", "FAT32", "SPRUCE", "MBR", "disk4"]`; exFAT gives `"ExFAT"`.
  Patch `store.load_cards` and `store.repo_json` with `mock.patch.object`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_format_card < /dev/null` → FAIL (module missing).

- [ ] **Step 3: Implement the helpers.**

- [ ] **Step 4: Write failing `run` tests** in the style of `tests/test_flash.py`'s run tests (patch `flash._run` recording calls, `picker.filter_list`, `ui.ask`, `flash.external_disks` returning `[CARD]` with `CARD = flash.Disk("disk4", 64_000_000_000, "SD Card Reader", ("SHARE",))`, `flash.disks_of` returning `{"disk0"}`, `format_card.sys.platform`). Args has `dry_run`. Cases:
  - happy path, filesystem pick index 1 (FAT32), label pick index of `SPRUCE`, answer `disk4` → exit 0, calls include `["sudo", "-v"]` then the erase command; output has `✅`.
  - picking the last row `✏️  Type a label…` then typing `roms` under FAT32 → erase with `ROMS`; typing `bad/name` first re-asks (problem shown), then `roms` works.
  - wrong confirmation (`Disk4`, `""`) → exit 0, no erase, `Not formatted` in stderr.
  - `--dry-run` → exit 0, no sudo or erase, output contains the erase command joined by spaces.
  - Esc (filter_list returns None) at each of the three pickers → exit 0, no erase.
  - swapped card: `external_disks` returns `[CARD]` first, then a `Disk("disk4", 32_000_000_000, …)` → exit 1, no erase, `changed since you picked it` in stderr.
  - erase returns code 1 with stderr `boom` → exit 1, `boom` in stderr, no `✅`.
  - `disks_of` returning `set()` for `/` → exit 1, `external_disks` not called.
  - not darwin → exit 1.

- [ ] **Step 5: Run** → FAIL.

- [ ] **Step 6: Implement `run(args)`.** Flow: platform check → exclude = `disks_of("/")` (empty → `❌ couldn't tell which disk holds /: not formatting`, 1) plus `disks_of(runtime.ROOT)` when set → `external_disks(exclude)` (none → `❌ no SD card found`, 1) → if dry run print `🧪 Dry run: nothing is erased` → `🃏 Which SD card?` → `💽 Which filesystem?` (FILESYSTEMS names) → `🏷️  Which label?` (`label_choices(fs)` + `✏️  Type a label…`; typed label: `ui.ask("Label: ")`, cleaned, empty → exit 0, a problem is printed with `ui.failure` and asked again) → warning `⚠️  Everything on disk4 (size, name: volumes) will be erased and formatted <fs> named <label>.` (dry run: `would be erased`) → `Type disk4 to format it: ` / dry run `Type disk4 to see the rest of the dry run (nothing is erased): ` → mismatch: `❌ Not formatted`, 0 → dry run: print `Would run: <command>`, 0 → `flash._sudo()` → same-disk check via `external_disks(exclude)` and `_same` → `flash._run(["sudo", *erase_command(...)])` (eraseDisk needs root on some cards; run via sudo) → non-zero: `❌ format failed: <stderr or stdout>`, 1 → `✅ Formatted <disk> as <fs> named <label>`. Use `HINT` on every picker. Note: the happy-path test's expected call is `["sudo", "diskutil", "eraseDisk", …]`; adjust Step 4's assertion to that.

- [ ] **Step 7: Run** `uv run python -m unittest tests.test_format_card < /dev/null` → PASS.

- [ ] **Step 8: Commit** `feat(format): add format_card module` (with Co-Authored-By trailer).

### Task 2: Wire the command, help and README

**Files:**
- Modify: `src/sync_roms/commands.py` (`COMMANDS`, `format_cmd`, parser next to `flash` at ~1734, module docstring list)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS` after `flash`, `TOPICS["format"]` after flash's)
- Modify: `README.md` (Commands table row after `flash`, section `## Formatting an SD card (\`format\`)` after the flash section)

**Interfaces:**
- Consumes: `format_card.run(args)`.

- [ ] **Step 1:** Add `"format"` to `COMMANDS`; `def format_cmd(args): from . import format_card; return format_card.run(args)`; `p = sub.add_parser("format", add_help=False, allow_abbrev=False); common(p, card=False); p.set_defaults(fn=format_cmd)`.
- [ ] **Step 2:** `SUBCOMMANDS["format"] = ("", "erase an SD card as exFAT or FAT32 with a picked label")`; `TOPICS["format"]` in flash's style: usage line `sync-roms format [--dry-run]  erase an SD card as exFAT or FAT32 (macOS only)`, then a paragraph covering the card list and exclusions, filesystem, label list (card names, layout names uppercased, type your own; FAT32 uppercase ≤ 11, exFAT ≤ 15), typed disk-id confirm (`--yes` never skips; `--dry-run` stops there and shows the command), same-disk check, `sudo diskutil eraseDisk … MBR`, card left mounted.
- [ ] **Step 3:** README row `| \`format\` | [erase an SD card as exFAT or FAT32](#formatting-an-sd-card-format) with a picked label, macOS only | |` and a short bullet section mirroring the help.
- [ ] **Step 4: Run** the full suite `uv run python -m unittest discover -s tests < /dev/null` → PASS (`test_readme` checks the table against the parsers).
- [ ] **Step 5: Commit** `feat(format): add format command` (with trailer).
