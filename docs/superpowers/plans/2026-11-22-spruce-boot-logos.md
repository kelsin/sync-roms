# Device Resolutions and Spruce Boot Logos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every device's pixel resolution, and have sync stage the user's personal boot logos for the card's device on `spruce` cards.

**Architecture:** `devices.json` gains `resolution`/`resolution2`. A new module, `spruce_bootlogo.py`, shaped like `spruce_os.py`, copies `<data dir>/bootlogos/<resolution>/*.png|bmp` into the card's `App/BootLogo/Imgs/` and records what it put there in the card field `boot_logos`.

**Tech Stack:** Python 3.12+, stdlib only, `unittest`. Always `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-22-spruce-boot-logos-design.md`

## Global Constraints

- Read the repo's `CLAUDE.md` first; it overrides defaults. Run everything with `uv run` (`uv run python -m unittest discover -s tests`).
- Code must run on Python 3.12.
- A test module that imports `sync_roms` imports `isolate` first (directly or through `helpers`).
- No logo art, personal names or images in the repo. Nothing is read from or written to storage.
- Never create, overwrite or remove anything in `App/BootLogo/` except files named in the card's `boot_logos`.
- Conventional Commits; never hand-edit `__version__`, `CHANGELOG.md` or `.release-please-manifest.json`.
- Match existing style; touch only what the task needs.

## Review Focus

1. `App/BootLogo/Imgs/` missing on the card: warn, create nothing, record nothing, no failure counted.
2. A personal logo named like one of spruce's own in `Imgs/` (any letter case, e.g. `spruce.png` vs `Spruce.png`): skipped with a warning, spruce's file byte-for-byte unchanged, never recorded, never removed later.
3. The personal `bootlogos/` folder (or the resolution's folder) deleted while the card still records logos: the recorded files and their `Yes, flash <name>.<ext>` copies are removed and `boot_logos` cleared; with `keep=True` they stay and stay recorded.
4. Device `full`, an unknown device id, a device with no `resolution`, or `magicx-zero40`: nothing read, written, removed or printed, even when the card records logos.
5. A copy that raises `OSError` (card full or read-only): warned, counted as one failure, and `boot_logos` records only the files that did land.

Each is pinned by a test in Task 2.

---

### Task 1: `resolution` in `devices.json`

**Files:**
- Modify: `src/sync_roms/data/devices.json`
- Modify: `CLAUDE.md` (the `devices.json` bullet under "Repo data")
- Test: `tests/test_devices_data.py` (create)

**Interfaces:**
- Produces: each device dict from `store.repo_json("devices")` has `"resolution": "<W>x<H>"` when it has `"screen"`, and `"resolution2"` when it has `"screen2"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_devices_data.py` (import `isolate`, then `from sync_roms import store`), over `store.repo_json("devices")`, each in a `subTest(d["id"])`:
  - `test_resolution_exactly_when_screen`: `("resolution" in d) == ("screen" in d)` and `("resolution2" in d) == ("screen2" in d)`.
  - `test_resolutions_are_well_formed`: each present value matches `^[1-9]\d*x[1-9]\d*$`.
  - `test_resolution_matches_the_recorded_ratio`: for `(screen, resolution)` and `(screen2, resolution2)`, with ratio `a:b` and `WxH`, `abs((W / H) / (a / b) - 1) < 0.02`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_devices_data -v`. Expected: FAIL (no `resolution`).

- [ ] **Step 3: Add the values.** Source: the research file handed to the builder (`resolutions.json`), `{device id: {"resolution", "resolution2"?}}` (the two devices with `null` have no `screen`; copy only those two keys, not `source` or `note`). Put `resolution` directly after `screen` and `resolution2` directly after `screen2` in each device object, keeping the file's existing one-device-per-line formatting and every other byte unchanged (a throwaway script outside the repo is fine; check `git diff --stat` shows only that file and that no line changed other than by the inserted keys).

- [ ] **Step 4: Run** the new tests and the whole suite (`uv run python -m unittest discover -s tests`). Expected: PASS. If `tests/test_setup_guide.py` fails, run `uv run python tools/update_setup_guide.py` (it should not need to: the guide embeds a fixed key list).

- [ ] **Step 5: Document.** In `CLAUDE.md`'s `devices.json` bullet, after "`screen` ratio, optional `screen2` (second screen)", add: `resolution` (native pixels, `<W>x<H>` as the device is held; the base model's when variants differ) and `resolution2` with `screen2`.

- [ ] **Step 6: Commit**

```bash
git add src/sync_roms/data/devices.json tests/test_devices_data.py CLAUDE.md
git commit -m "feat(devices): record each device's screen resolution"
```

---

### Task 2: Stage personal boot logos on spruce cards

**Files:**
- Create: `src/sync_roms/spruce_bootlogo.py`
- Modify: `src/sync_roms/cli.py` (import list near line 13; `stage_spruce` near line 1138)
- Modify: `src/sync_roms/data/cards.schema.json` (beside `drivers`)
- Modify: `src/sync_roms/commands.py` (`CARD_FIELDS` near line 316; the `("frontend_collections", "drivers")` list-of-names check near line 1000)
- Modify: `CLAUDE.md` (Personal data; Card fields table; "What sync puts on a card")
- Test: `tests/test_spruce_bootlogo.py` (create); extend the `drivers` cases in `tests/test_cardshare.py` and `tests/test_commands.py`

**Interfaces:**
- Consumes: `resolution` from Task 1; `store.data_dir()`, `store.saved_card(card)`, `store.update_card(card, **values)`, `store.repo_json("devices")`, `ui.warn`, `ui.dim`, `ui.green`.
- Produces: `spruce_bootlogo.install(card, layout_name, device, base, dry_run, wrote=None, keep=False) -> int` (the failure count). `device` is the card's device id (or `"full"`), `base` the card folder. `wrote`, a list, gets the card paths it wrote. Module constants: `FOLDER = "bootlogos"`, `IMGS = os.path.join("App", "BootLogo", "Imgs")`, `UNSUPPORTED = {"magicx-zero40"}` (spruce devices whose Boot Logo app can't run), `CONFIRM = "Yes, flash "`.

**Behaviour of `install`** (in this order):
1. Return 0 silently unless `layout_name == "spruce"`, `device` is a device id in `devices.json` with a `resolution`, and `device not in UNSUPPORTED`.
2. `wanted`: the files directly in `<data dir>/bootlogos/<resolution>/` whose name ends in lowercase `.png` or `.bmp` and doesn't contain `Yes, flash` (missing folder: none). `recorded`: the card's saved `boot_logos` (a list of names; anything else counts as empty).
3. Nothing wanted and nothing recorded: return 0 silently.
4. `Imgs/` is not a folder on the card: `ui.warn` that the card has no `App/BootLogo/Imgs` (spruceOS isn't installed) and return 0, creating nothing.
5. For each wanted name not in `recorded` whose name matches an existing `Imgs/` entry case-insensitively: `ui.warn` that it is one of spruce's own names, and skip it.
6. Copy each remaining wanted file whose card copy is missing or whose bytes differ. An `OSError` on one file: `ui.warn`, count one failure, go on.
7. Stale: each recorded name not wanted. Without `keep`, remove `Imgs/<name>` and `Imgs/Yes, flash <name>` (missing files ignored) and drop it from the record; with `keep`, leave both and keep it recorded.
8. Save `boot_logos` (sorted names that are on the card from sync: copied now or recorded and still wanted, plus kept stale ones) with `store.update_card` only when it changed; an empty list is stored as absent the way `store.update_card` drops other emptied fields, or as `[]` if it has no such convention.
9. When something was copied, print one line: the count, `→ App/BootLogo/Imgs`, and "run Apps → Boot Logo on the device".
10. `dry_run`: write, remove and record nothing; print one `ui.dim("🧪 Dry run: would …")` line when there is something to copy or remove.

- [ ] **Step 1: Write the failing tests** in `tests/test_spruce_bootlogo.py`, on `helpers.CardDir` as `tests/test_spruce_os.py` does (`store.update_card("c", layout="spruce")`; logos made with `helpers.touch` under `os.path.join(store.data_dir(), "bootlogos", "640x480")`; device `"miyoo-a30"`, which is 640x480; `Imgs/` made with `os.makedirs` in `setUp`). One test per line:
  - `test_copies_matching_logos_and_records_them`: `K.png` and `A.bmp` wanted → both in `Imgs/` with the same bytes, `saved_card["boot_logos"] == ["A.bmp", "K.png"]`, returns 0, `wrote` holds both card paths, stdout mentions `Boot Logo`.
  - `test_second_run_copies_nothing`: run twice; second run's stdout is empty and `wrote == []`.
  - `test_changed_logo_is_copied_again`: rewrite `K.png` with other bytes, run → card copy has the new bytes.
  - `test_other_resolution_folder_is_ignored`: a logo only in `720x480/` → `Imgs/` stays empty, no `boot_logos`.
  - `test_ignores_uppercase_extension_other_types_and_confirm_names`: `K.PNG`, `notes.txt`, `Yes, flash K.png` in the folder → nothing copied.
  - `test_not_spruce_full_unknown_unsupported_are_silent_noops`: for `(layout, device)` in `("onion", "miyoo-a30")`, `("spruce", "full")`, `("spruce", "nope")`, `("spruce", "magicx-zero40")` with a recorded `boot_logos=["K.png"]` and `Imgs/K.png` present → file still there, record unchanged, no output, returns 0. (Review Focus 4)
  - `test_missing_imgs_folder_warns_and_creates_nothing`: remove `Imgs/` → returns 0, stderr mentions `App/BootLogo/Imgs`, `App/BootLogo` not created, no `boot_logos`. (Review Focus 1)
  - `test_spruces_own_name_is_skipped_case_insensitively`: card has `Imgs/Spruce.png` (bytes `b"own"`), wanted `spruce.png` → card file still `b"own"`, not recorded, stderr warns; then delete the personal file and run again → `Imgs/Spruce.png` still there. (Review Focus 2)
  - `test_removed_logo_is_cleaned_with_its_confirm_copy`: after a first run, add `Imgs/Yes, flash K.png`, delete the whole personal `bootlogos` folder, run → both files gone, `boot_logos` empty or absent; an unrelated `Imgs/Other.png` untouched. (Review Focus 3)
  - `test_keep_leaves_stale_logos_recorded`: same, with `keep=True` → both files stay, `K.png` still recorded. (Review Focus 3)
  - `test_copy_failure_counts_and_records_only_what_landed`: `mock.patch("shutil.copyfile")` (or whichever copy call the module uses) raising `OSError` for `K.png` only → returns 1, stderr warns, `boot_logos == ["A.bmp"]`. (Review Focus 5)
  - `test_dry_run_writes_and_records_nothing`: `dry_run=True` with one logo to copy and one stale → `Imgs/` unchanged, record unchanged, stdout contains `Dry run`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_spruce_bootlogo -v`. Expected: FAIL (no module).

- [ ] **Step 3: Implement `spruce_bootlogo.py`** per the Interfaces and Behaviour above, with a one-line module docstring in the style of `spruce_os.py`.

- [ ] **Step 4: Run** the module's tests. Expected: PASS.

- [ ] **Step 5: Wire it in.** In `cli.py`'s `stage_spruce`, before `spruce_os.install` (logos are small; the 7z stays last): `failed = spruce_bootlogo.install(card, layout_name, device, base, dry_run, wrote, keep=args.no_delete)`, then add the other two calls to `failed` as now. Confirm `device` in that scope is the device id string; if it is a dict, pass its `id`. `wrote` already drives `clean._clean_root`.

- [ ] **Step 6: Card field plumbing**, each mirroring `drivers`:
  - `cards.schema.json`: `"boot_logos"`, array of strings, description "Boot logo file names sync-roms copied to a spruce card's App/BootLogo/Imgs".
  - `commands.py`: add `"boot_logos"` to `CARD_FIELDS` and to the `("frontend_collections", "drivers")` check.
  - Tests: wherever `tests/test_cardshare.py` and `tests/test_commands.py` cover `drivers` as a sync-written field (export strips or keeps it, `check` flags a non-list), add the same assertion for `boot_logos`; write the test first and see it fail.

- [ ] **Step 7: Document in `CLAUDE.md`.**
  - Personal data: `bootlogos/<W>x<H>/`: the user's own boot logos (`.png`, `.bmp`), one folder per device `resolution`; never in the repo or storage.
  - Card fields table: `boot_logos` | sync | The logo file names sync put in a `spruce` card's `App/BootLogo/Imgs/`; only those are overwritten or removed.
  - "What sync puts on a card": one bullet for `spruce_bootlogo.py` covering which cards (spruce, a device with a `resolution`, not `UNSUPPORTED`), that `Imgs/` is never created, spruce's own names are skipped, stale ones go with their `Yes, flash` copy unless `--no-delete`, Miyoo Mini cards are staged ahead of the spruce release that shows the app there, and that flashing is the user's step in Apps → Boot Logo.

- [ ] **Step 8: Run the whole suite** (`uv run python -m unittest discover -s tests`). Expected: PASS. If `tests/test_readme.py` fails, make the README change it names and nothing more.

- [ ] **Step 9: Commit**

```bash
git add src/sync_roms/spruce_bootlogo.py src/sync_roms/cli.py src/sync_roms/commands.py src/sync_roms/data/cards.schema.json tests CLAUDE.md
git commit -m "feat(spruce): stage personal boot logos on spruce cards"
```
