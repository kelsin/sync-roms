# Android Bezels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync copies a device's bezels from storage's `os/android/bezels/<device id>/` to `Bezels/` on `esde` cards, `config apply` points RetroArch's overlay folder there, and the setup guide shows the on-device steps for devices that have bezels.

**Architecture:** A small `bezels.py` module owns the storage prefix and the listing (through `inventory.files`). `cli.py` adds its jobs next to the APK jobs; `android_settings.cfg_wanted` takes an optional overlay folder; `commands.guide_cmd` injects the device ids into the page like `cards-data`.

**Tech Stack:** Python 3.12+, unittest, `uv run`. One self-contained HTML page with inline JS.

**Spec:** `docs/superpowers/specs/2026-11-24-android-bezels-design.md`

## Global Constraints

- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests` (stdin closed: `< /dev/null`).
- Test modules import `isolate` (directly or via `helpers`) before `sync_roms`.
- Storage reads go through `inventory.py`; catch `s3.ERRORS`. Never call `s3.list_*` directly.
- Storage prefix: `os/android/bezels/`. Card folder: `Bezels/` at the card root. Overlay path on the device: `/storage/<volume>/Bezels/retroarch`.
- Only `esde` layout, never guest cards.
- The repo never names which devices have bezels (that's storage content).
- Conventional Commits, lowercase imperative; end each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Storage unreadable (unmounted share) during `guide`: the guide must still open with no Bezels section, not crash. → Task 3 test.
- A device with no bezels folder: sync adds no jobs and prints nothing about bezels; `config apply` sets no `overlay_directory`. → Tasks 1 and 2 tests.
- The listing's folder markers (keys ending in `/`) and `.DS_Store` must not become jobs. → Task 1 test.
- Another device's bezels (prefix collision, e.g. `magicx-zero40` vs `magicx-zero40-pro`) must not be copied: match on `<prefix><id>/`. → Task 1 test.
- `config apply --dry-run` lists `overlay_directory` with the other retroarch.cfg entries. → Task 2 test.

---

### Task 1: Sync copies bezels to esde cards

**Files:**
- Create: `src/sync_roms/bezels.py`
- Modify: `src/sync_roms/cli.py` (APK/driver job block ~1560-1600, the summary at ~1700, `todo_all` at ~1713 and ~1956, the per-kind list at ~1854, `run_downloads` at ~1977, `got` at ~2053; sync help text at ~69-80)
- Modify: `src/sync_roms/mirroring.py` (prefix list ~21-40)
- Modify: `CLAUDE.md` (storage table `os/` row; "What sync puts on a card")
- Test: `tests/test_bezels.py`, plus a sync test in `tests/test_cli_sync.py` modelled on its APK test

**Interfaces:**
- Produces: `bezels.PREFIX = "os/android/bezels/"`; `bezels.files(device_id: str | None) -> dict[str, int | None]` (storage key → size, only files under `PREFIX + device_id + "/"`, no folder markers, no `.DS_Store`; `{}` for `None`); `bezels.devices() -> list[str]` (sorted device ids with at least one file); `bezels.jobs(device_id, card_base) -> list[job]` in the same shape the APK jobs use, targets `card_base/Bezels/<path relative to the device folder>`.

- [ ] **Step 1: Write failing tests** in `tests/test_bezels.py` with `inventory.files` patched to return `{"os/android/bezels/magicx-zero40/": 0, "os/android/bezels/magicx-zero40/retroarch/gb.cfg": 86, "os/android/bezels/magicx-zero40/.DS_Store": 6, "os/android/bezels/magicx-zero40-pro/x.png": 1}`:
  - `test_files_only_the_device`: `files("magicx-zero40")` keys == `{"os/android/bezels/magicx-zero40/retroarch/gb.cfg"}`.
  - `test_devices`: `devices() == ["magicx-zero40", "magicx-zero40-pro"]`.
  - `test_jobs_target_bezels_folder`: the one job targets `<base>/Bezels/retroarch/gb.cfg`.
  - `test_no_device`: `files(None) == {}`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_bezels < /dev/null` → FAIL (no module).
- [ ] **Step 3: Implement `bezels.py`.** Build jobs with `downloads.add_job` or the tuple form the APK jobs use, whichever fits.
- [ ] **Step 4: Wire into `cli.py`:** for `layout_name == "esde" and not guest`, `bezel_jobs = downloads.with_sizes(bezels.jobs(device id, base))`, `bezel_todo = downloads.plan_downloads(bezel_jobs)`; add it everywhere `apk_todo` flows (summary row `("🖼️", "Bezels", ...)`, `todo_all`, the per-kind list as kind `"bezel"`, `run_downloads(bezel_todo, "Bezels", "🖼️", <card>/Bezels, failures)`, `got`). Add `bezels.PREFIX` to `mirroring.py`'s listed prefixes and wanted files. Update the sync help text that lists what Android cards get.
- [ ] **Step 5: Sync test** in `tests/test_cli_sync.py` next to the APK one: an esde card for `magicx-zero40` with bezels in the test storage gets `Bezels/retroarch/gb.cfg`; a guest card, a card for another device and a non-esde card get no `Bezels/`.
- [ ] **Step 6: Docs:** CLAUDE.md `os/` storage row mentions `os/android/bezels/<device id>/` (by hand); "What sync puts on a card" gets a bullet: esde cards get their device's bezels in `Bezels/`, unchanged files skipped, files gone from storage left on the card.
- [ ] **Step 7: Run all tests** `uv run python -m unittest discover -s tests < /dev/null` → OK.
- [ ] **Step 8: Commit** `feat(sync): copy the device's bezels to esde cards`.

### Task 2: config apply sets RetroArch's overlay folder

**Files:**
- Modify: `src/sync_roms/android_settings.py` (`cfg_wanted`, `_retroarch_part`, `_write_retroarch`, `apply`)
- Modify: `src/sync_roms/settings_apply.py:54-57` (pass the device id)
- Modify: `src/sync_roms/cli.py` `config apply` help text (~534); CLAUDE.md `config apply` bullet
- Test: `tests/test_android_settings.py`

**Interfaces:**
- Consumes: `bezels.files(device_id)` from Task 1.
- Produces: `cfg_wanted(overlay_dir: str | None = None) -> dict` (adds `overlay_directory` when given, before `CLOUD_SYNC`); `android_settings.apply(target, layout, systems, dry_run, device_id=None)`.

- [ ] **Step 1: Failing tests:** `test_cfg_wanted_overlay` → `cfg_wanted("/storage/ABCD-1234/Bezels/retroarch")["overlay_directory"] == "/storage/ABCD-1234/Bezels/retroarch"`; `test_cfg_wanted_no_overlay` → key absent with no argument; an `apply` dry-run test (using the file's existing fake-adb setup) with `bezels.files` patched to one file for the device shows `overlay_directory` among the entries, and with `{}` doesn't.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_android_settings < /dev/null` → FAIL.
- [ ] **Step 3: Implement:** `apply` computes `overlay = f"/storage/{target.volume}/Bezels/retroarch" if device_id and bezels.files(device_id) else None` (a storage error: warn and use `None`), passes it to `_retroarch_part` and `_write_retroarch`, which pass it to `cfg_wanted`. `settings_apply` passes the saved setup's device id (check what `picker.saved_setup` returns at index 0).
- [ ] **Step 4: Help text and CLAUDE.md:** `config apply` also points RetroArch's overlay folder at the card's `Bezels/retroarch` when storage has bezels for the device.
- [ ] **Step 5: Run all tests** → OK.
- [ ] **Step 6: Commit** `feat(config): point retroarch's overlay folder at the card's bezels`.

### Task 3: Setup guide shows bezel steps

**Files:**
- Modify: `src/sync_roms/commands.py` `guide_cmd` (~1134)
- Modify: `src/sync_roms/data/setup-guide.html` (a `<script id="bezels-data" type="application/json">[]</script>` next to `cards-data`; `matches` ~1470 gets `bezels`; ctx gets `bezels: BEZELS.includes(device.id)`; a new `SECTIONS` entry)
- Modify: CLAUDE.md "Setup guide" (the `bezels` filter and the `bezels-data` block)
- Test: `tests/test_setup_guide.py` (or the test file that covers `guide_cmd`)

**Interfaces:**
- Consumes: `bezels.devices()` from Task 1.

- [ ] **Step 1: Failing tests:** `guide_cmd` with `bezels.devices` patched to `["magicx-zero40"]` writes a page whose `bezels-data` block is `["magicx-zero40"]`; patched to raise `OSError` (in `s3.ERRORS`) writes `[]` and still returns 0 (patch `webbrowser.open` to return True); the shipped page's `bezels-data` block is `[]`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `guide_cmd`** filling `id="bezels-data">[]<` the same way as cards.
- [ ] **Step 4: Page section** `id: "bezels"`, title "Bezels", `when: { layout: ["esde"], bezels: [true] }`, items (copy, may be tightened to the page's tone):
  - RetroArch: sync puts the bezels in `Bezels/retroarch/` and `config apply` points RetroArch's overlay folder there. In a game: Quick Menu → On-Screen Display → On-Screen Overlay: Display Overlay on, Overlay Preset: the bezel's `.cfg`, Overlay Opacity 1.00. Settings → Video → Scaling: Integer Scale off, Aspect Ratio Custom, Custom Viewport X/Y/width/height fitting the game in the bezel's open area. Save with Quick Menu → Overrides → Save Core Overrides, or Save Game Overrides when the bezel is for some of the core's games only (vertical arcade games).
  - DraStic: copy `Bezels/drastic/*.png` into DraStic's `backgrounds/` folder (in the folder DraStic uses for its data). In a game: Menu → Edit Screens and Virtual Pad → the portrait layout → Set background image, place the two screens above and below the image's divider, save.
- [ ] **Step 5: Run** `uv run python tools/update_setup_guide.py` if the page's embedded data needs it, then all tests → OK. Open the generated page in a browser for `magicx-zero40` / `esde` with the block filled and check the section shows, and not for another device.
- [ ] **Step 6: Commit** `feat(guide): show bezel setup steps for devices with bezels`.
