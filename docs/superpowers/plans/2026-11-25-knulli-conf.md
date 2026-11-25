# Knulli knulli.conf Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the user's RetroAchievements login, WiFi networks, hotkey scheme and allowlisted preferences into a Knulli card's `system/knulli.conf` on sync and `config apply`, import preferences with `config import`, and remind about Install Pico-8.

**Architecture:** One module, `src/sync_roms/knulli_conf.py`, builds `{key: value}` of everything sync wants and merges it into `knulli.conf` in one read and one write, reporting through `applied.Entry`/`applied.show`. Sync calls it next to the spruce steps; `settings_apply` and `commands.IMPORTERS` gain Knulli entries.

**Tech Stack:** Python (stdlib), `unittest`, run with `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-25-knulli-conf-design.md`

## Global Constraints

- Settings file: `system/knulli.conf` under the card root (`FILE = os.path.join("system", "knulli.conf")`), shown as `system/knulli.conf`.
- Never create the file. Missing → `ui.warn("system/knulli.conf is missing; Knulli settings skipped (boot the card once in Knulli Scarab first)")`, failure count 0.
- Merge in place: only wanted keys' lines change; other lines, comments and order are kept; a key not present as an active line is appended at the end; `#key=` comment lines are never touched; every active line of a duplicated key gets the value. Write with `cardfs.write_text` (LF).
- A key's active line is a line whose text before the first `=`, stripped, equals the key and that doesn't start with `#` after leading whitespace. The value is everything after the first `=` (may contain `=`), with a trailing `\r` stripped.
- Secret keys (value never printed): `global.retroachievements.password`, `global.retroachievements.webapikey`, `wifi.key`, `wifi2.key`, `wifi3.key`.
- No Syncthing, cores or autosave forcing; `ra_offline_proxy` and `ra_proxy_stats` are not written.
- Only non-guest syncs of `knulli` cards run it.
- Conventional Commits, lowercase imperative; commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests: `uv run python -m unittest discover -s tests` (stdin closed: `< /dev/null`).

## Review Focus

- Password containing `=` or `#` (e.g. `a=b#c`) → written and read back exactly; no quoting.
- CRLF `knulli.conf` (edited on Windows) → values compare without `\r`, so a second run reports nothing changed.
- Second sync with nothing changed → no write and no "set" lines (idempotent).
- File that has only the template's commented `#global.retroachievements=0` → real line appended, comment untouched.
- `ra_mode` `Manual` with a username set → only the username key is written; no `global.retroachievements` toggle.

---

### Task 1: knulli_conf core — merge and RetroAchievements

**Files:**
- Create: `src/sync_roms/knulli_conf.py`
- Test: `tests/test_knulli_conf.py`

**Interfaces:**
- Produces:
  - `FILE: str`, `SHOWN = "system/knulli.conf"`, `SECRET: frozenset[str]`
  - `parse(text: str) -> dict[str, str]` — active keys to values (last active line wins).
  - `merge(text: str, values: dict[str, str]) -> str`
  - `ra_values() -> dict[str, str]` — from settings.json `ra_mode`, `ra_username`, `ra_password`, `ra_api_key`.
  - `wanted(current: dict[str, str]) -> dict[str, str]` — every wanted key, in order RA, WiFi, hotkeys, preferences. Task 1 returns `ra_values()`; Tasks 2–4 add their parts here.
  - `entries(base: str) -> list[applied.Entry]` — one per wanted key (changed or not); `[]` and the warning when the file is missing; `[]` silently when nothing is wanted.
  - `install(card: str, layout_name: str, base: str, dry_run: bool) -> int` — 0 for non-`knulli`; merges, prints `applied.show([changed entries], dry_run)`, writes unless `dry_run`; always returns 0.

- [ ] **Step 1: Write failing tests** in `tests/test_knulli_conf.py` (class base `helpers.CardDir`, settings via `usersettings.save_settings`, file at `self.cp("system", "knulli.conf")`):
  - `test_parse_skips_comments_and_keeps_equals`: `parse("#a=1\nb = x=y\r\nc=\n")` → `{"b": "x=y", "c": ""}`.
  - `test_merge_replaces_appends_and_keeps_comments`: `merge("#global.retroachievements=0\nfoo=1\nglobal.retroachievements.username=old\n", {"global.retroachievements.username": "me", "global.retroachievements": "1"})` → `"#global.retroachievements=0\nfoo=1\nglobal.retroachievements.username=me\nglobal.retroachievements=1\n"`.
  - `test_merge_updates_every_duplicate`: two `k=a` lines → both `k=b`.
  - `test_merge_adds_newline_before_append` when the text doesn't end with `\n`.
  - `test_ra_modes`: `Disabled` → `{"global.retroachievements": "0"}`; `Casual` and `Softcore` → `{"global.retroachievements": "1", "global.retroachievements.hardcore": "0"}`; `Hardcore` → `"1"`/`"1"`; `Manual` with `ra_username="me"` → `{"global.retroachievements.username": "me"}` only.
  - `test_api_key`: 32 alphanumerics → `global.retroachievements.webapikey`; `"short"` → not written and a warning naming `ra_api_key`.
  - `test_install_writes_and_hides_secrets`: `ra_password="a=b#c"` → file line `global.retroachievements.password=a=b#c`; stdout contains `(hidden)`, never `a=b#c`.
  - `test_install_twice_writes_nothing_second_time`: second run's stdout is empty and the file mtime is unchanged.
  - `test_crlf_file_is_idempotent`: file written with `\r\n` and the wanted values already present → `entries` all unchanged.
  - `test_missing_file_warns_and_creates_nothing`: no `system/` → stderr has `system/knulli.conf is missing`, no file created, return 0.
  - `test_other_layout_does_nothing`: `install("c", "spruce", ...)` returns 0 and touches nothing.
  - `test_dry_run_does_not_write`.

- [ ] **Step 2: Run and verify they fail**

Run: `uv run python -m unittest tests.test_knulli_conf < /dev/null`
Expected: FAIL (`ModuleNotFoundError: sync_roms.knulli_conf`).

- [ ] **Step 3: Implement `knulli_conf.py`** with the interfaces above. Reuse `spruce_settings.MODES` and `spruce_settings.API_KEY` (don't copy them); read the file with `cardfs.text`, write with `cardfs.write_text`. Mode mapping: `Disabled` → toggle `0` (no hardcore key); `Casual`/`Softcore` → `1` + hardcore `0`; `Hardcore` → `1` + `1`; `Manual` or unset → none.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run python -m unittest tests.test_knulli_conf < /dev/null`
Expected: OK.

- [ ] **Step 5: Commit** — `feat(knulli): write retroachievements settings into knulli.conf`

---

### Task 2: WiFi networks

**Files:**
- Modify: `src/sync_roms/knulli_conf.py`
- Test: `tests/test_knulli_conf.py`

**Interfaces:**
- Consumes: `wanted(current)` from Task 1.
- Produces: `wifi_values(current: dict[str, str]) -> dict[str, str]`, added to `wanted` after RA.

Slots are `wifi`, `wifi2`, `wifi3` (keys `<slot>.ssid`, `<slot>.key`). Final list = settings.json `wifi_networks` entries (`{"ssid", "psk"?}`, entries without a text `ssid` skipped) in order, then the networks already in the file's slots (in slot order, non-empty ssid) whose SSID isn't in the list, cut to three. Write `ssid` and `key` (`psk` or `""`) for slots 1..len(final). No `wifi_networks` → `{}`.

- [ ] **Step 1: Write failing tests**
  - `test_wifi_fills_slots_in_order`: two networks, empty file → `wifi.ssid=A`, `wifi.key=pa`, `wifi2.ssid=B`, `wifi2.key=` (open network).
  - `test_wifi_keeps_device_networks_after_yours`: file has `wifi.ssid=Home`/`wifi.key=h`, list `[{"ssid": "A", "psk": "pa"}]` → slot 1 `A`, slot 2 `Home`/`h`.
  - `test_wifi_same_ssid_takes_your_key`: file `wifi.ssid=A`/`wifi.key=old`, list A/new → slot 1 key `new`, no duplicate slot.
  - `test_wifi_more_than_three_warns`: four networks → first three written; warning names the fourth SSID. Device networks pushed out → warning names them too.
  - `test_wifi_keys_hidden` in output.

- [ ] **Step 2: Run, verify fail** — `uv run python -m unittest tests.test_knulli_conf < /dev/null`, FAIL on the new tests.
- [ ] **Step 3: Implement `wifi_values`** and add it to `wanted`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `feat(knulli): write saved wifi networks into knulli.conf`

---

### Task 3: Hotkey scheme

**Files:**
- Modify: `src/sync_roms/data/hotkeys.json`, `src/sync_roms/knulli_conf.py`
- Test: `tests/test_knulli_conf.py`, `tests/test_hotkeys_data.py`

**Interfaces:**
- Produces: `hotkey_values() -> dict[str, str]` (from `store.repo_json("hotkeys")["knulli"]`), added to `wanted` after WiFi.

Derived from Knulli configgen's `libretroControllers.py` defaults (x load, y save, a reset, start exit, up slot+, down slot−, left rewind, right fast-forward, L1 screenshot, R1 AI service, L2/R2 shaders, b menu) and its remap loop; the result is X menu, R1 save, L1 load, Left slot−, Right slot+, R2 fast-forward toggle, Start quit (already the default), with A reset and L2 shader-prev left over.

- [ ] **Step 1: Write failing tests**
  - `test_hotkeys_data.py`: `hotkeys.json["knulli"] == {"global.hotkey_b": "x", "global.hotkey_y": "pagedown", "global.hotkey_x": "pageup", "global.hotkey_down": "left", "global.hotkey_up": "right", "global.hotkey_right": "r2", "global.toggle_fast_forward": "1"}`.
  - `test_knulli_conf.py` `test_hotkeys_written`: an empty-but-present file gets exactly those seven lines.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3:** Add the `"knulli"` block to `hotkeys.json`, and extend its `"note"` with: `Knulli cards get the scheme as knulli.conf hotkey remaps; Knulli has no slow-motion or Show FPS hotkey, so those two are left out there.` Implement `hotkey_values`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `feat(knulli): set the shared hotkey scheme in knulli.conf`

---

### Task 4: Preferences allowlist and config import

**Files:**
- Create: `src/sync_roms/data/knulli-settings.json`
- Modify: `src/sync_roms/knulli_conf.py`, `src/sync_roms/commands.py:730` (`IMPORTERS`), `src/sync_roms/cli.py` (config help, ~line 505–530)
- Test: `tests/test_knulli_conf.py`

**Interfaces:**
- Produces:
  - `allowed() -> list[str]` — `store.repo_json("knulli-settings")["keys"]`.
  - `wanted_settings() -> dict[str, str]` — allowlisted entries of settings.json `knulli_settings` (`{key: value}`, values as strings; non-dict → warn `knulli_settings in settings.json must be {key: value}; ignored`; unknown keys → one warning listing them, `knulli_settings in settings.json has settings that aren't shared, ignored: ...`). Added to `wanted` last.
  - `import_settings(path: str) -> int` — registered as `IMPORTERS["knulli"]`.

`knulli-settings.json`: `{"note": "Your own Knulli preferences, safe on any Knulli device. Left out: hardware, display output, audio, network, services, login and hotkey settings.", "keys": ["global.shaderset", "global.integerscale", "global.bezel", "global.ratio", "global.smooth", "global.rewind", "global.autosave", "global.incrementalsavestates", "global.quickresume", "global.retroachievements.leaderboards", "global.retroachievements.verbose", "global.retroachievements.screenshot", "global.retroachievements.challenge_indicators", "global.retroachievements.richpresence", "global.retroachievements.encore", "global.retroachievements.unofficial", "global.retroachievements.sound", "system.language", "system.timezone"]}`.

`import_settings` mirrors `spruce_settings.import_settings` (same Identical / Different-or-new listing, the `ynp` prompt, `choose_required`, "Nothing imported." paths) over the allowlisted keys active in the card's `knulli.conf`; missing file → `ui.fail(f"{file} is missing; is {path} a Knulli card that has been booted once?", 2)`; none of the keys present → `ui.fail("system/knulli.conf has none of the settings that can be saved", 2)`; saves `settings["knulli_settings"]` merged with what is there; success line `💾 Saved N Knulli setting(s) from system/knulli.conf in settings.json`.

- [ ] **Step 1: Write failing tests**
  - `test_preferences_written`: `knulli_settings={"global.smooth": "0", "system.hostname": "x"}` → `global.smooth=0` written, `system.hostname` not, warning names `system.hostname`.
  - `test_import_yes_saves_allowlisted_only`: card file `global.smooth=0\nsystem.hostname=X\n#global.rewind=1\n`, answer `y` (patch `ui.choose_required`) → `knulli_settings == {"global.smooth": "0"}`.
  - `test_import_nothing_differs`: saved equals card → prints `Nothing differs`, settings unchanged.
  - `test_import_missing_file_fails` with exit code 2.
  - `test_config_import_dispatches_knulli`: a saved card with layout `knulli` → `commands.import_settings` calls `knulli_conf.import_settings`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the data file, `allowed`, `wanted_settings`, `import_settings`, the `IMPORTERS` entry. Update the config help: `config import` reads "(spruceOS or Knulli preferences)"; add a paragraph: `For a Knulli card it copies the allowlisted preferences (shaders, scaling, rewind, autosave, quick resume, the RetroAchievements display options, language and timezone) from system/knulli.conf into settings.json's knulli_settings. knulli_settings isn't a config set name: import it, or edit settings.json by hand ({"key": "value"}).`
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `feat(knulli): sync and import knulli preferences`

---

### Task 5: Wire into sync, config apply, and the PICO-8 reminder

**Files:**
- Modify: `src/sync_roms/cli.py` (`stage_spruce` ~1206, no-games path ~1228–1236, end of run ~1828, imports line 14, config help), `src/sync_roms/settings_apply.py`, `src/sync_roms/pico8.py`
- Test: `tests/test_settings_apply.py`, `tests/test_pico8.py`, `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: `knulli_conf.install`, `knulli_conf.entries` (Task 1).
- Produces: `pico8.remind(layout_name: str, wrote: list[str]) -> None` — for `knulli` and a non-empty `wrote`, prints `ui.bold(f"🕹️  PICO-8 {os.path.basename(path)} is on the card: run Device Settings → Install Pico-8 on the device to install it")` per path; nothing for other layouts.

- [ ] **Step 1: Write failing tests**
  - `test_settings_apply.py` `test_knulli_card_applies_knulli_conf`: a `knulli` card with `system/knulli.conf` and `ra_username` set → `config apply <folder>` writes the username line, returns 0; with `--dry-run` writes nothing and stdout has `would set`.
  - `test_settings_apply.py` `test_other_layout_message`: an `onion` card fails with `config apply supports spruce and Knulli cards and Android devices, not onion`.
  - `test_pico8.py` `test_remind_knulli_only`: `remind("knulli", ["/x/roms/pico8/pico-8_0.2.6b_raspi.zip"])` prints `Install Pico-8`; `remind("spruce", [...])` prints nothing.
  - `test_cli_sync.py` `test_knulli_sync_writes_knulli_conf`: a knulli card sync (follow the file's existing knulli sync test setup) with `ra_username` set ends with the line in `system/knulli.conf`; a guest sync does not.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement**
  - `cli.py`: import `knulli_conf`; in `stage_spruce` add `failed += knulli_conf.install(card, layout_name, base, dry_run)` and change its docstring to "...on a spruce card, and the knulli.conf settings on a Knulli card". In the no-games path pass a `pico8_wrote = []` list to `install_apps(args.dry_run, pico8_wrote)` and call `pico8.remind(layout_name, pico8_wrote)` beside `spruce_os.remind`; at the end of the full run call `pico8.remind(layout_name, pico8_wrote)` beside `spruce_os.remind(spruce_staged)`.
  - `settings_apply.py`: add `_knulli(base, name, dry_run)` — dry run `applied.show(knulli_conf.entries(base), True)` and 0, else `knulli_conf.install(name, "knulli", base, False)`; accept `layout in ("spruce", "knulli")`; new error text as in the test; module docstring names Knulli.
  - Config help for `config apply`: "apply the saved settings to a spruce or Knulli card or an Android device", and a sentence: `A mounted Knulli card gets the RetroAchievements login, WiFi networks, hotkey scheme and knulli_settings in system/knulli.conf.`
- [ ] **Step 4: Run the full suite** — `uv run python -m unittest discover -s tests < /dev/null`, expected OK.
- [ ] **Step 5: Commit** — `feat(knulli): apply knulli.conf settings on sync and config apply`

---

### Task 6: Docs and setup guide

**Files:**
- Modify: `CLAUDE.md` (Knulli/settings notes in "Data files"), `README.md` (config apply/import), `src/sync_roms/data/setup-guide.html` (Knulli RetroAchievements ~1013, HOTKEY_LAYOUT.knulli ~693, Knulli WiFi if present, PICO-8 ~1576)
- Test: `tests/test_setup_guide.py` (existing)

- [ ] **Step 1:** CLAUDE.md: add one paragraph after the ROCKNIX paragraph: Knulli cards (Scarab) get `system/knulli.conf` merged by `knulli_conf.py` on every non-guest sync and `config apply` — RA login/mode/Web API key from the `ra_*` settings, up to three `wifi_networks`, the hotkey scheme as `global.hotkey_*` remaps (`hotkeys.json` `knulli`), and the allowlisted `knulli_settings` (`data/knulli-settings.json`, read back by `config import`); the file is never created; a sync that put a PICO-8 zip on the card reminds to run Device Settings → Install Pico-8.
- [ ] **Step 2:** README: list Knulli under `config apply` and `config import`.
- [ ] **Step 3:** Setup guide: Knulli RetroAchievements and WiFi steps say sync writes them (set with `sync-roms config set ra_username …`, `wifi_networks` in settings.json); the Knulli hotkey table matches the new scheme with a note that slow motion and Show FPS aren't available; the Knulli PICO-8 step keeps "run Device Settings → Install Pico-8" and says sync puts the zip there. Only those steps; no new guessed settings.
- [ ] **Step 4:** `uv run python -m unittest discover -s tests < /dev/null` → OK; open the guide (`uv run sync-roms guide`) and check the Knulli device view shows the edited steps.
- [ ] **Step 5: Commit** — `docs(knulli): describe knulli.conf settings`
