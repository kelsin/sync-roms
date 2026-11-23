# Guest Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A card marked `guest` gets a sync that only copies ROMs, BIOS and scrapes, deletes only the recognized ROMs deselected this session (and their media), never overwrites a card file, and is hidden from `cards list` without `--all`.

**Architecture:** A new `guest.py` holds the pure guest logic (recognize card files, seed picks, work out deletions, filter jobs so nothing is overwritten, find a deleted ROM's media). `cli.sync_card` calls it behind a `guest` boolean and gates every non-copy step with `if not guest`. The card editor gets a `G` key; `cards list` gets `--all`.

**Tech Stack:** Python 3.12+ stdlib, `unittest`, `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-23-guest-cards-design.md`

## Global Constraints

- Always `uv run`; tests: `uv run python -m unittest discover -s tests`. Code must run on Python 3.12.
- A test module importing `sync_roms` imports `isolate` first (directly or via `helpers`).
- Never put test files in storage; tests use the isolated data folder and temp card folders.
- Card field is `guest`: present and `true` only on guest cards, absent otherwise. Write it with `store.update_card`.
- Card storage reads go through `inventory` (`inventory.files`, `inventory.stat`, `inventory.cached`) only; card file reads through `cardfs`.
- Nothing on the card is overwritten in a guest sync: ROMs, BIOS, media, text files written only where no file exists; gamelists only gain `<game>` entries for ROMs without one.
- Recognized = name match as `card_match` (case and Unicode form ignored, `downloads.name_key`) **and** `downloads.is_current(card_path, storage_size, disc_dir)`.
- Conventional Commits, lowercase, imperative. End commits with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Non-guest syncs behave exactly as before (the existing test suite passes unchanged).

## Review Focus

1. A card on a case-sensitive filesystem with `Game.ZIP` where storage has `Game.zip`: recognized, not downloaded again, deleted at its own path when deselected. (Task 1 test `test_recognized_keeps_the_card_spelling`, Task 4 test `test_guest_sync_does_not_redownload_a_differently_spelled_rom`.)
2. A same-named friend file of a different size: never seeded, never deleted, never overwritten. (Task 1 `test_recognized_skips_a_different_size`, Task 4 `test_guest_sync_leaves_a_same_named_file_of_another_size`.)
3. `G` turned **off** during a guest sync must not turn that run into a normal sync (a normal sync sweeps every unpicked file, the friend's included). Plan call: turning guest off takes effect on the next sync; the running sync stays guest. (Task 3 test `test_turning_guest_off_mid_sync_keeps_this_run_guest`.)
4. A guest card with old `surprises` saved: none are synced. (Task 2 `test_guest_card_surprises_are_not_in_the_manifest`.)
5. `--yes`/no terminal on a guest card: no editor, nothing deleted, BIOS and scrapes filled in. (Task 4 `test_guest_sync_with_yes_deletes_nothing`.)

Note for the user: item 3 is a plan-level change to the spec, which said turning `G` off mid-sync makes it a normal sync. It's safer this way.

---

### Task 1: `guest.py` core logic

**Files:**
- Create: `src/sync_roms/guest.py`
- Test: `tests/test_guest.py`

**Interfaces:**
- Produces:
  - `is_guest(entry) -> bool`: `entry.get("guest") is True` for a dict, else False.
  - `recognized(dest: str, keys: list[str], sizes: dict[str, int], disc_dir: str | None = None, folders: dict | None = None) -> dict[str, str]`: `{storage key: card path as spelled on the card}` for keys whose file is on the card under a matching name (walk `dest`, and `dest/disc_dir` when set, with `downloads.walk_roms`; match `downloads.name_key(downloads.rom_rel(k, disc_dir, m3u.disc_keys(keys) if disc_dir else (), folders))` against `name_key` of each card file's relative path) and `downloads.is_current(card_path, sizes.get(k), disc_dir)`. Keys with no size are skipped.
  - `seed_games(seed: dict[str, dict[str, str]]) -> dict`: the `games` value for cards.json: `{bucket: sorted keys}` for buckets with keys, via `store.sorted_list`.
  - `save_seed(card: str, seed) -> None`: one `cards.json` write that sets `games = seed_games(seed)` and removes `excluded`, `collections`, `systems_off`, `surprises` from the entry (keeps every other field).
  - `apply_seed(systems: list[dict], seed) -> None`: in memory, for dry runs: each system's `games = [{"bucket": k, "title": store.key_title(k)} for k in sorted(seed.get(bucket, {}))]`, `full_system = False`.
  - `deletions(seed, picked: dict[str, set[str]], skipped: set[str]) -> list[str]`: card paths of `seed[b][k]` for `k not in picked.get(b, set())`, buckets in `skipped` left out; sorted, unique.
  - `new_files(jobs: list[tuple]) -> list[tuple]`: jobs `(key, path, size)` whose `cardfs.size(path) is None`.
  - `new_gamelist_entries(gamelists: dict[str, dict[str, dict]]) -> dict`: `{gamelist path: {rom rel: tags}}` keeping only ROMs with no `<game>` whose `path` is `./<rom rel>` in that file (parse like `scrape_plan.update_gamelist`; a missing file keeps all; files left with no entries dropped).

- [ ] **Step 1: Write the failing tests** in `tests/test_guest.py` (import `isolate` first; temp card folders with `helpers.touch`):
  - `test_is_guest`: `is_guest({"guest": True})` True; `{}`, `{"guest": "yes"}`, `None` False.
  - `test_recognized_matches_name_and_size`: card `gba/Game.zip` (5 bytes), `gba/Mine.zip`; keys `["gba/Game.zip", "gba/Other.zip"]`, sizes `{"gba/Game.zip": 5, "gba/Other.zip": 3}` → `{"gba/Game.zip": <dest>/Game.zip}`.
  - `test_recognized_skips_a_different_size`: card `Game.zip` 4 bytes, size 5 → `{}`.
  - `test_recognized_keeps_the_card_spelling`: card `GAME.zip`, key `gba/Game.zip` same size → value ends with `GAME.zip`.
  - `test_recognized_finds_discs_in_disc_dir`: Onion-style `disc_dir=".discs"`, keys `psx/G.m3u`, `psx/G (Disc 1).chd`; card has `G.m3u` (storage text with the disc dir prefix, as `m3u.prefix_playlists` writes it) and `.discs/G (Disc 1).chd` → both recognized.
  - `test_save_seed_replaces_picks_and_keeps_setup`: card entry `{"device": "x", "layout": "esde", "games": {"nes": ["nes/A.zip"]}, "excluded": {...}, "collections": ["c"], "systems_off": ["nes"], "surprises": [...], "guest": True}`; `save_seed("card", {"gba": {"gba/Game.zip": "/p"}})` → entry is `{"device": "x", "layout": "esde", "games": {"gba": ["gba/Game.zip"]}, "guest": True}`.
  - `test_deletions_are_seed_minus_picks_without_skipped`: seed `{"gba": {"gba/A.zip": "/a", "gba/B.zip": "/b"}, "nes": {"nes/C.zip": "/c"}}`, picked `{"gba": {"gba/A.zip"}}`, skipped `{"nes"}` → `["/b"]`.
  - `test_new_files_drops_existing_paths`: one job to an existing file, one to a missing → only the missing.
  - `test_new_gamelist_entries_skips_roms_already_listed`: gamelist file with `<game><path>./A.zip</path></game>`; input `{path: {"A.zip": {...}, "B.zip": {...}}, missing_path: {"C.zip": {...}}}` → `{path: {"B.zip": ...}, missing_path: {"C.zip": ...}}`.

- [ ] **Step 2: Run and see them fail**
  Run: `uv run python -m unittest tests.test_guest -v`
  Expected: FAIL, `ImportError` / no module `guest`.

- [ ] **Step 3: Implement `src/sync_roms/guest.py`** with the functions above. Import `store`, `downloads`, `cardfs`, `m3u`, `scrape_plan` at the top only if that causes no circular import (check `tests/test_imports.py`); otherwise import inside the functions, as the repo does.

- [ ] **Step 4: Run the tests**
  Run: `uv run python -m unittest tests.test_guest -v`
  Expected: PASS.

- [ ] **Step 5: Commit** `feat(guest): add guest card logic for seeding, deletions and no-overwrite`

---

### Task 2: guest flag in cards.json, the manifest and `cards list`

**Files:**
- Modify: `src/sync_roms/store.py` (`card_locked_games`, around line 282)
- Modify: `src/sync_roms/commands.py` (`cards_list` at 443, its parser at 1469)
- Modify: `src/sync_roms/data/cards.schema.json`, `CLAUDE.md` (Card fields table), `README.md` (wherever `cards list` is documented)
- Test: `tests/test_guest.py`, `tests/test_commands.py`

**Interfaces:**
- Consumes: `guest.is_guest`.
- Produces: `cards list --all`; JSON rows gain `"guest": bool`.

- [ ] **Step 1: Write the failing tests**
  - `test_guest_card_surprises_are_not_in_the_manifest` (test_guest.py): a card with `guest: true`, Surprise on (layout `esde`), `surprises: [{"system": "gba", "bucket": "gba/S.zip", "title": "S"}]` → `store.card_locked_games(entry, {})` has no `gba/S.zip`; without `guest` it has it.
  - In test_commands.py, next to the existing `cards list` tests: `test_cards_list_hides_guest_cards` (two cards, one `guest: true`; output names only the other, and a dim line contains `1 guest card hidden` and `--all`), `test_cards_list_all_shows_guest_cards_marked` (both named; the guest row contains `👤`), `test_cards_list_json_has_guest_field` (`--all --json` rows have `guest` True/False; `--json` alone omits the guest card).
  - `cards.schema.json` validation test (wherever the schema is tested) accepts `"guest": true`.

- [ ] **Step 2: Run and see them fail**
  Run: `uv run python -m unittest tests.test_guest tests.test_commands -v`
  Expected: the new tests FAIL.

- [ ] **Step 3: Implement**
  - `card_locked_games`: surprises are added only when `surprise.enabled(entry) and not guest.is_guest(entry)`.
  - `cards_list`: skip guest entries unless `args.all`; with `--all` add `👤 ` before a guest row's name; after the table (text output only) print `ui.dim(f"{n} guest card(s) hidden (--all shows them)")` when any were hidden, with the singular `1 guest card hidden`. Add `"guest": guest.is_guest(cards[name])` to each row.
  - Parser: `p.add_argument("--all", action="store_true")` on `cards list`; add `--all` to completion if `commands.second_words`/completion lists per-command flags (check `tests/test_completion.py`).
  - Schema: `"guest": {"type": "boolean", "const": true}` (or the schema's style for flags).
  - CLAUDE.md Card fields table, new row: `` `guest` | `--guest`, card editor's `G` | `true` on a guest card (a friend's card): its sync only copies ROMs, BIOS and scrapes, deletes only the recognized ROMs deselected that session, never overwrites a card file; hidden from `cards list` without `--all`. Absent otherwise. ``
  - README: document `cards list --all`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_guest tests.test_commands tests.test_readme tests.test_completion -v` → PASS.

- [ ] **Step 5: Commit** `feat(cards): hide guest cards from cards list unless --all`

---

### Task 3: `G` in the card editor and the editor hook

**Files:**
- Modify: `src/sync_roms/cardedit.py` (keys at top, `edit_card` at 273)
- Modify: `src/sync_roms/surprise.py` (`run_surprise` at 261: pass `on_guest` through to `edit_card`)
- Test: `tests/test_cardedit.py`

**Interfaces:**
- Consumes: `guest.is_guest`.
- Produces:
  - `cardedit.GUEST_KEY = "G"`, in `LIST_KEYS` as `("G", "guest card: a friend's card; syncs only copy ROMs, BIOS and scrapes (again to undo)")` and `LIST_HINT` gains `· G guest`.
  - `cardedit.toggle_guest(name) -> bool`: flips the card's `guest` (sets `True` / pops it) in one `cards.json` write; returns the new state.
  - `cardedit.edit_card(name, setup=None, to_fetch=None, card_match=None, on_guest=None)`: on `G`, `toggle_guest(name)`; if it turned on and `on_guest` is given, call `on_guest()` (the sync's reseed) and recount every system (`changed = ALL`). The title adds ` · 👤 guest` while on.
  - `surprise.run_surprise(..., card_match=None, on_guest=None)`: passes `on_guest` to both `edit_card` calls.

- [ ] **Step 1: Write the failing tests** (test_cardedit.py, using the existing editor test helpers such as `helpers.feed_list`/`pilot_list`):
  - `test_g_toggles_guest`: pressing `G` twice in the system list sets then removes `guest` in cards.json.
  - `test_g_on_calls_on_guest_once`: with `on_guest` a mock, `G` (on) calls it once; `G` again (off) doesn't call it.
  - `test_title_shows_guest`: with `guest: true` saved, the list title contains `👤 guest`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_cardedit -v` → new tests FAIL.

- [ ] **Step 3: Implement** as in Interfaces; `G` goes in `hotkeys` and is handled in the `isinstance(i, tuple)` branch.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_cardedit tests.test_surprise -v` → PASS.

- [ ] **Step 5: Commit** `feat(cardedit): toggle a card as a guest card with G`

---

### Task 4: guest sync in `cli.sync_card`

**Files:**
- Modify: `src/sync_roms/cli.py` (`build_parser` 661, `PLAIN_FLAGS` 620, `check_modes` 705, help text for the sync topic near line 82, `sync_card` 1023-1709)
- Modify: `README.md` (Options table: `--guest`)
- Test: `tests/test_guest_sync.py` (new; reuse `SyncSmokeTest.run_sync`'s patching pattern from `tests/test_cli_sync.py`, with a real temp card folder and `store.load_cards`/`update_card` on the isolated data folder)

**Interfaces:**
- Consumes: everything in Task 1; `cardedit.edit_card(..., on_guest=)`, `surprise.run_surprise(..., on_guest=)` from Task 3.
- Produces: `sync-roms CARD --guest`.

Behavior, in `sync_card` order:

1. `--guest`: `ap.add_argument("--guest", action="store_true")`, in `PLAIN_FLAGS`, and in `check_modes`'s "only apply to syncing a card" check with `--no-delete`. After `choose_card_setup`, if `args.guest and not args.dry_run`: `store.update_card(card, guest=True)`. `guest = args.guest or guest.is_guest(store.saved_card(card))` (name the module import so it doesn't clash, e.g. `from . import guest as guests`).
2. Guest skips: `nextui_folders.migrate`, `spruce_emu.legacy_systems` (the `dropped += legacy` block), and the `dropped` device systems (set `dropped = []`).
3. `reseed()`: closure. For each system in `systems` (the synced list): `names = inventory.files(bucket + "/", sizes=False)`, keys = `[k for k in names if not k.endswith("/")]` minus ignored (`ignore.is_ignored`); names matched as in `guest.recognized`, then sizes from `inventory.stat(matched_candidates)` (only for name matches, so a share isn't stat'ed whole). `seed[bucket] = guest.recognized(dest_of(s), ...)`. Not a dry run: `guest.save_seed(card, seed)` then `reload_changes()`; dry run: `guest.apply_seed(systems, seed)` then `listings.clear(); relist()`. Systems whose folder is missing on the card get `{}`.
4. If `guest`: `reseed()` before the editor; then, instead of `run_surprise`/`fill_surprises`: when `interactive and not args.dry_run`, `cardedit.edit_card(card, (device, layout_name), to_fetch, card_match)` then `reload_changes()`. Not guest: `run_surprise(..., on_guest=on_guest)` where `on_guest` sets `nonlocal guest = True` and calls `reseed()`; after it, `if not guest: fill_surprises(...)`; reload as now. A guest that `G` turned off mid-run stays guest this run (Review Focus 3).
5. Skipped when guest (dry run and real): `install_apps`, `onion_surprise.write_list`, `stage_spruce` (also the early `if not chosen` path), APK jobs, drivers (refresh, jobs, prune), `theme_jobs` and `theme_plan` (so no `t` answer and no theme removal/selection), `frontend_step`, `spruce_fixes.run`, `vita.add_psvita_files`, the over-capacity warning, `scrape_plan.prune_empty_systems`. `spruce_emu_step` and `downloads.hide_discs` still run.
6. Deletions: when guest, no `downloads.find_extras` loop (so `extras`, `renames`, `card_moves` are empty). After the editor, `picked = {s["bucket"]: set(available(s)) for s in systems}`, `skipped = store.systems_off(store.saved_card(card))`, `extras = guest.deletions(seed, picked, skipped)` → existing `--no-delete` / `delete_extras` / dry-run "would delete" / JSON `delete` handling.
7. No overwrite: when guest, seeded keys' jobs use the seed's card path (`rom_jobs` path replaced by `seed[bucket][key]` when present), then `rom_todo = guest.new_files(rom_todo)`, `bios_todo = guest.new_files(bios_todo)`; in `build_plan`, `plan["jobs"] = guest.new_files(plan["jobs"])`, `plan["writes"]` kept only for paths with `cardfs.size(path) is None`, `plan["gamelists"] = guest.new_gamelist_entries(plan["gamelists"])`.
8. Stale media: when guest, instead of `scrape_plan.stale_media`, the media of the deleted ROMs: for systems with deletions, `scrape_plan.build_scrape_plan(layout_name, those systems, scrape_plan.load_scrape_data(those systems), {bucket: [storage rels of deleted keys]}, dest_of, es_dir, lambda p: True, base)["jobs"]` paths that exist on the card (`cardfs.size(p) is not None`), computed **before** the ROMs are deleted and removed with `remove_stale_media` after; `--no-delete` lists them with `list_kept`. Dry run reports the count as now.

- [ ] **Step 1: Write the failing tests** in `tests/test_guest_sync.py` (esde layout from `helpers.MANIFEST` unless stated; storage via `list_sizes`; patch `cli.downloads.run_downloads` to record jobs):
  - `test_guest_flag_saves_guest_on_the_card`: `--guest` → `store.saved_card(card)["guest"] is True`; with `--dry-run` it isn't saved.
  - `test_guest_sync_seeds_picks_from_the_card`: card has `gba/Game.zip` (storage size) and `gba/Mine.zip`; saved picks `{"nes": ["nes/X.zip"]}` → after sync, `games == {"gba": ["gba/Game.zip"]}`.
  - `test_guest_sync_with_yes_deletes_nothing`: card has `Game.zip` and `Mine.zip`; no file removed; BIOS jobs for the system are downloaded.
  - `test_guest_sync_deletes_only_deselected_recognized_roms`: patch `cli.cardedit.edit_card` to remove `gba/Game.zip` from the card's games (interactive: patch `ui.has_terminal` True, no `--yes`, confirm the delete prompt via `ui.choose` → `"y"`, and the download confirm) → `Game.zip` gone, `Mine.zip` stays, and a media file of `Game.zip` (e.g. ES-DE `downloaded_media/gba/covers/Game.png`) gone while `Other.png` (no ROM) stays.
  - `test_x_skips_a_system`: editor patch adds `gba` to `systems_off` and removes its picks → nothing in `gba` deleted or downloaded.
  - `test_guest_sync_leaves_a_same_named_file_of_another_size`: card `Game.zip` 1 byte, storage 5 → not deleted, not downloaded.
  - `test_guest_sync_does_not_redownload_a_differently_spelled_rom`: card `GAME.ZIP` with storage's size; patch `cardfs`'s view only if the test FS is case-insensitive (macOS) — assert no ROM job for `gba/Game.zip`.
  - `test_guest_sync_never_overwrites_bios_or_media`: card has a BIOS file and a cover of another size → neither in the download jobs.
  - `test_guest_sync_skips_settings_steps`: patch `cli.pico8.run`, `cli.onion_surprise.install`, `cli.raofflineproxy.install`, `cli.spruce_settings.install`, `cli.spruce_wifi.install`, `cli.spruce_syncthing.run`, `cli.spruce_os.install`, `cli.spruce_bootlogo.install`, `cli.spruce_fixes.run`, `cli.spruce_themes.plan`, `cli.drivers.for_device`, `cli.frontend.plan_collections`, `cli.surprise.run_surprise`, `cli.surprise.fill_surprises` with mocks on a `spruce` layout guest card → none called; `cli.spruce_emu.plan` is called.
  - `test_turning_guest_on_in_the_editor_reseeds`: non-guest card; patched `run_surprise` calls its `on_guest` after setting `guest` → the card's games equal the seed and `fill_surprises` isn't called.
  - `test_turning_guest_off_mid_sync_keeps_this_run_guest`: guest card; patched `edit_card` pops `guest` → no `find_extras` sweep (patch it to fail the test if called).
  - `test_normal_sync_unchanged`: run the existing `tests/test_cli_sync.py` and `tests/test_sync_flow.py` (step 4).

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_guest_sync -v` → FAIL.

- [ ] **Step 3: Implement** behavior 1–8 above. Keep each `if not guest` next to the step it skips.

- [ ] **Step 4: Run the whole suite**
  Run: `uv run python -m unittest discover -s tests`
  Expected: `OK` (no failures; includes `test_readme`).

- [ ] **Step 5: Commit** `feat(sync): add guest syncs that only copy ROMs, BIOS and scrapes`

---

### Task 5: docs

**Files:**
- Modify: `CLAUDE.md` (a short "Guest cards" bullet in "What sync puts on a card": the steps a guest sync runs and skips, the seed, deletions, no-overwrite, `G`, `--guest`)
- Modify: `README.md` (a short Guest cards section)

- [ ] **Step 1:** Write both, matching the files' tone; no notes about storage contents.
- [ ] **Step 2:** `uv run python -m unittest tests.test_readme -v` → PASS.
- [ ] **Step 3: Commit** `docs: describe guest cards`
