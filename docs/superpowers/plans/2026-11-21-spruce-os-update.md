# Stage spruceOS updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `spruce` cards, sync copies the newest `spruceV<version>.7z` from storage's `os/spruceos/` to the card root, unextracted, once per version, for the on-device EZ Updater.

**Architecture:** A new `spruce_os.py` with `newest(listing)` and `install(card, layout_name, base, dry_run)`, shaped like `raofflineproxy.install` (once per file name via a card field). `cli.py` calls it at the same four places it calls `raofflineproxy.install`; `mirroring.mirror_wanted` adds the newest 7z.

**Tech Stack:** Python stdlib, `unittest` (`python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-21-spruce-os-update-design.md`

## Global Constraints

- Storage prefix is exactly `os/spruceos/` (lowercase, as on the NAS). Add `SPRUCE_PREFIX = "os/spruceos/"` to `runtime.py` next to `ROCKNIX_PREFIX`.
- File pattern: `re.fullmatch(r"spruceV\d+(\.\d+)*\.7z", name)` on the part after the prefix (so no subfolders, no `spruceOTA-*`, no installers). Newest by `onion_surprise._natural`.
- Card field `spruce_os`: the 7z file name last staged. Set only after a successful copy.
- Never extract. Never delete anything on the card except the root file named by the old `spruce_os`, and only when that name itself matches the pattern.
- Storage reads only through `inventory.files(runtime.SPRUCE_PREFIX)`; the copy through `s3.download((key, path, size))` (it writes `<path>.part` and renames, and removes the `.part` on failure).
- Conventional Commits.

## Review Focus

- A card that already has the same 7z at its root (user copied it by hand) and no `spruce_os` record: don't re-copy 1.6 GB when the size matches the listing; just record it.
- A `spruceV*.7z` on the card root that sync did not stage (not the recorded name): left alone when a newer one is staged.
- A hand-edited `spruce_os` like `../x.7z` or `Roms`: never removed (pattern check).
- Copy fails (card full, storage error): warning, returns 1, `spruce_os` unchanged, old staged file still there, no `.part` left.
- EZ Updater deleted the staged file after applying it: with `spruce_os` equal to the newest, nothing is copied again.

---

### Task 1: `spruce_os` module

**Files:**
- Create: `src/sync_roms/spruce_os.py`
- Modify: `src/sync_roms/runtime.py` (add `SPRUCE_PREFIX`)
- Test: `tests/test_spruce_os.py` (style of `tests/test_raofflineproxy.py`: `helpers.StorageDir`, `store.update_card("c", layout="spruce")`, card folder in `self.tmp.name`, storage files written under the StorageDir's storage root so `inventory.files` and `s3.download` find them; check how `test_raofflineproxy.py` places storage files and copy that)

**Interfaces:**
- Produces: `spruce_os.newest(listing: dict[str, int]) -> str | None` (a storage key); `spruce_os.install(card: str, layout_name: str, base: str, dry_run: bool) -> int` (failure count, 0 or 1).

- [ ] **Step 1: Write failing tests** in `tests/test_spruce_os.py`:
  - `test_newest_compares_versions_as_numbers`: listing `{"os/spruceos/spruceV4.6.0.7z", "os/spruceos/spruceV4.10.0.7z", "os/spruceos/spruceOTA-v4.5.6-to-v4.6.0.7z", "os/spruceos/spruceos-installer-windows.exe", "os/spruceos/old/spruceV9.0.0.7z"}` → `"os/spruceos/spruceV4.10.0.7z"`; `newest({})` is `None`.
  - `test_other_layouts_get_nothing`: layout `"onion"` → returns 0, card folder empty, no `spruce_os`.
  - `test_no_release_in_storage_does_nothing`: returns 0, nothing written.
  - `test_stages_the_newest_7z_at_the_card_root`: storage has `spruceV4.6.0.7z` (bytes `b"new"`) → card root file `spruceV4.6.0.7z` has `b"new"`, no other files on the card, `spruce_os == "spruceV4.6.0.7z"`, output contains `spruceV4.6.0.7z` and `EZ Updater`.
  - `test_once_per_version_even_after_the_updater_removed_it`: `spruce_os` already `spruceV4.6.0.7z`, card empty → returns 0, card still empty.
  - `test_same_file_already_on_the_card_is_recorded_without_copying`: card root has `spruceV4.6.0.7z` with the same size as storage's, no record → `s3.download` not called (`mock.patch.object(spruce_os.s3, "download")`), `spruce_os` set.
  - `test_newer_version_removes_only_the_one_sync_staged`: record `spruceV4.5.6.7z`, card root has `spruceV4.5.6.7z` and `spruceV4.0.0.7z`; storage has `spruceV4.6.0.7z` → card has `spruceV4.0.0.7z` and `spruceV4.6.0.7z` only.
  - `test_recorded_name_outside_the_pattern_is_never_removed`: record `Roms`, card has a `Roms/` folder with a file; afterwards it is still there. Same with record `../outside.7z` and a file at `os.path.join(self.tmp.name, "outside.7z")`.
  - `test_dry_run_writes_nothing`: output contains `Dry run` and the name; card empty; no record.
  - `test_failed_copy_warns_and_keeps_the_old_file`: record `spruceV4.5.6.7z` with that file on the card; patch `spruce_os.s3.download` to raise `OSError("No space left")` → returns 1, record still `spruceV4.5.6.7z`, old file still there, no `.part` file on the card.

- [ ] **Step 2: Run** `python -m unittest tests.test_spruce_os -v` → FAIL (`No module named sync_roms.spruce_os` / `SPRUCE_PREFIX`).

- [ ] **Step 3: Implement** `newest` and `install` in `src/sync_roms/spruce_os.py`. `install`: return 0 unless `layout_name == "spruce"`; key = `newest(inventory.files(runtime.SPRUCE_PREFIX))`, return 0 if none; return 0 when the card's `spruce_os` equals the name; dry run prints `ui.dim(f"🧪 Dry run: would stage spruceOS {name} at the card root")`; skip the download when `os.path.getsize(target) == listing[key]`; on `(OSError, *s3.ERRORS)` `ui.warn(f"Couldn't stage spruceOS {name} on the card: {e}")` and return 1; then remove the old recorded file (pattern match, `os.path.isfile`, `contextlib.suppress(OSError)`), `store.update_card(card, spruce_os=name)`, print `f"🌲 spruceOS {ui.green(name)} → card root (run Apps → EZ Updater on the device)"`.

- [ ] **Step 4: Run** `python -m unittest tests.test_spruce_os -v` → all PASS.

- [ ] **Step 5: Commit** `feat(spruce): stage the newest spruceOS release for EZ Updater`.

### Task 2: Wire into sync, mirror and docs

**Files:**
- Modify: `src/sync_roms/cli.py` (import `spruce_os`; next to each `raofflineproxy.install(card, layout_name, base, …)` call, four of them: nothing-to-sync path, dry-run plan, real sync, and any other found by `grep -n "raofflineproxy.install" src/sync_roms/cli.py`, add the same `spruce_os.install(...)` call with the same `dry_run` argument and, where the result is added to `failed`, add it too)
- Modify: `src/sync_roms/mirroring.py` (`mirror_wanted`: fetch `inventory.files(runtime.SPRUCE_PREFIX)` with the others; add the `spruce_os.newest` key and its size; mention it in the docstring)
- Modify: `CLAUDE.md` (a paragraph after the RAOfflineProxy one; add `spruce_os` to the cards.json field list next to `raofflineproxy_app`)
- Modify: `src/sync_roms/data/setup-guide.html` (a step for `when: { layout: ["spruce"] }`: "After a sync that staged a new spruceOS release, run Apps → EZ Updater on the device. It backs up your settings, applies the update and shuts down. It can't jump major versions (3.x to 4.x).", placed in the existing spruce setup section, wherever spruce's device steps live; follow the page's structure)
- Test: `tests/test_firmware_scrapes.py`, `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: `spruce_os.install`, `spruce_os.newest`, `runtime.SPRUCE_PREFIX` (Task 1).

- [ ] **Step 1: Write failing tests:**
  - `test_firmware_scrapes.py::test_mirror_wanted_includes_the_newest_spruceos_7z` (beside `test_mirror_wanted_includes_the_newest_surprise_app_zip`, same mocking): listings `{"os/spruceos/": {"os/spruceos/spruceV4.5.6.7z": 1, "os/spruceos/spruceV4.6.0.7z": 2, "os/spruceos/spruceOTA-v4.5.6-to-v4.6.0.7z": 3}}` → `{"os/spruceos/spruceV4.6.0.7z": 2}`.
  - `test_cli_sync.py::test_spruce_sync_stages_spruceos` (modeled on `test_onion_sync_installs_surprise_app_and_list`): a spruce card sync puts `spruceV4.6.0.7z` at the card root and records `spruce_os`; the same with `--dryrun` writes nothing.

- [ ] **Step 2: Run** both tests → FAIL.

- [ ] **Step 3: Make the code and doc changes listed under Files.**

- [ ] **Step 4: Run** `python -m unittest discover -s tests` → all PASS (includes `tests/test_setup_guide.py`).

- [ ] **Step 5: Commit** `feat(spruce): stage spruceOS on sync and mirror it`.
