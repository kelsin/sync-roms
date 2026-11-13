# Vita DLC and Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A synced Vita game brings all its DLC and its newest update, worked out from storage's file names at sync time; pickers and Surprise show only games.

**Architecture:** `vita.py` gets pure file-name parsing (`kind`, `is_extra`, `extras`). `store.synced_keys` adds a Vita game list's extras where a system's sync keys are decided (`available_keys`, `list_system`), so sync, mirroring and unwanted-file cleanup see them. Budget, the shared row builder, the card editor badge, Surprise, scrape and `.psvita` creation each get a small change.

**Tech Stack:** Python 3.11, `unittest` (run with `.venv/bin/python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-12-vita-dlc-updates-design.md`

## Global Constraints

- Extras are found by file name only: title id `[XXXX#####]` (four capital letters, five digits), DLC has `[DLC-`, update has `[PATCH]` with version `[vX.YY]`. Storage contents are never read for this.
- Only keys under `psvita/` are ever extras or have extras.
- Newest update only (highest numeric version); every DLC.
- Cards, sets and collections keep listing the game key only; nothing new is written to them.
- What storage holds is read only through `inventory.py` (`inventory.files`, `inventory.cached`, `inventory.stat`).
- The card's game count stays games only.
- Every changed line traces to the spec; match the surrounding style (docstrings, no type hints in signatures).

## Review Focus

- Sync from a storage folder with no storage cache: extras must still be found (names-only listing) and statted. Test in Task 2.
- An ignored DLC (in `ignored.json`) is never synced. Test in Task 2.
- A card that already lists a DLC key directly keeps it synced once (no duplicate) and keeps its row visible. Tests in Tasks 2 and 4.
- Update versions compare numerically (`v1.11` beats `v1.02`), and an update with no `[v…]` tag loses to any versioned one. Test in Task 1.
- Other systems are untouched: a `gba/` file named `... [PCSE00001] [PATCH].zip` is not an extra. Test in Task 1.

---

### Task 1: Vita file-name parsing and `.psvita` skipping

**Files:**
- Modify: `src/sync_roms/vita.py`
- Test: `tests/test_vita.py`

**Interfaces:**
- Produces:
  - `vita.BUCKET = "psvita"`
  - `vita.kind(name) -> "dlc" | "update" | "game"` (from the basename; DLC if it contains `[DLC-`, update if it contains `[PATCH]`)
  - `vita.is_extra(key) -> bool`: `key` starts with `"psvita/"` and `kind(key) != "game"`
  - `vita.extras(game_keys, folder_keys) -> {game key: [extra keys]}`: for each key in `game_keys` that is under `psvita/`, is a game and has a title id, its DLC in `folder_keys` with the same title id (sorted), then its newest update. Games with no extras are left out of the dict.

- [ ] **Step 1: Write the failing tests** in `tests/test_vita.py`, a new `class ExtrasTest(unittest.TestCase)`:

```python
GAME = "psvita/1001 Spikes [PCSE00349] [USA] [NoNpDRM].zip"
OLD = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip"
NEW = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
UNTAGGED = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [NoNpDRM].zip"
DLC_A = "psvita/5-Level Boost [PCSE00349] [USA] [DLC-ADDCONT049LVL000].zip"
DLC_B = "psvita/Accessory Pack [PCSE00349] [USA] [DLC-U000100PRM014ACA].zip"
OTHER = "psvita/Tearaway [PCSA00144] [USA] [NoNpDRM].zip"
OTHER_DLC = "psvita/Costume [PCSA00144] [USA] [DLC-X].zip"
NO_ID = "psvita/World of Final Fantasy.rar"
FOLDER = [GAME, OLD, NEW, UNTAGGED, DLC_B, DLC_A, OTHER, OTHER_DLC, NO_ID]

def test_kind(self):
    self.assertEqual([vita.kind(k) for k in (GAME, OLD, DLC_A, NO_ID)], ["game", "update", "dlc", "game"])

def test_is_extra_only_under_psvita(self):
    self.assertTrue(vita.is_extra(OLD))
    self.assertTrue(vita.is_extra(DLC_A))
    self.assertFalse(vita.is_extra(GAME))
    self.assertFalse(vita.is_extra("gba/Hack [PCSE00001] [PATCH].zip"))

def test_extras_are_every_dlc_then_the_newest_update(self):
    self.assertEqual(vita.extras([GAME], FOLDER), {GAME: [DLC_A, DLC_B, NEW]})

def test_untagged_update_loses_to_a_versioned_one_but_counts_alone(self):
    self.assertEqual(vita.extras([GAME], [GAME, UNTAGGED, OLD]), {GAME: [OLD]})
    self.assertEqual(vita.extras([GAME], [GAME, UNTAGGED]), {GAME: [UNTAGGED]})

def test_games_without_extras_and_non_games_are_left_out(self):
    self.assertEqual(vita.extras([OTHER, NO_ID, DLC_A, "gba/A [PCSE00349].zip"], FOLDER), {OTHER: [OTHER_DLC]})
    self.assertEqual(vita.extras([NO_ID], FOLDER), {})
```

And in `VitaTest`:

```python
def test_add_skips_dlc_and_update_zips(self):
    self.zip("G [PCSE00349] [USA] [NoNpDRM].zip", title_id="PCSE00349")
    self.zip("G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip", category="gp", title_id="PCSE00349")
    self.zip("D [PCSE00349] [USA] [DLC-X].zip", category="ac", title_id="PCSE00349")
    self.assertEqual(vita.add_psvita_files([self.dir]), [])
    self.assertEqual([f for f in self.files() if f.endswith(".psvita")], ["G [PCSE00349] [USA] [NoNpDRM].psvita"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest discover -s tests -p test_vita.py`
Expected: FAIL/ERROR (`module 'sync_roms.vita' has no attribute 'kind'`; the skip test reports two failures).

- [ ] **Step 3: Implement** `BUCKET`, `kind`, `is_extra`, `extras` in `src/sync_roms/vita.py`, and make `add_psvita_files` skip a zip whose `kind(f) != "game"`. Title id regex: `\[([A-Z]{4}\d{5})\]`; version regex: `\[v(\d+(?:\.\d+)*)\]` compared as a tuple of ints, with no tag ranking below every tagged version (e.g. key `(0, ())` vs `(1, (1, 11))`). Group `folder_keys` by title id once.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest discover -s tests -p test_vita.py`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/vita.py tests/test_vita.py
git commit -m "feat(vita): find a game's DLC and newest update by file name"
```

---

### Task 2: Sync keys include Vita extras

**Files:**
- Modify: `src/sync_roms/store.py:388-409` (`listed`, `available_keys`, `list_system`)
- Modify: `src/sync_roms/scrape_files.py:23` (`bucket_roms`)
- Modify: `README.md:279` (the Vita paragraph)
- Test: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `vita.BUCKET`, `vita.extras`, `vita.is_extra` (Task 1)
- Produces: `store.synced_keys(s) -> [bucket keys]`: `listed(s)`, then for the `psvita` system each listed game's extras from `inventory.files("psvita/", sizes=False)` that aren't already listed. No folder read when the system isn't `psvita` or lists nothing. `available_keys(s, have)` returns `synced_keys(s)` for a game list; `list_system(s)` stats `synced_keys(s)` on a share read.

- [ ] **Step 1: Write the failing tests** in `tests/test_inventory.py`, a new `class VitaSyncKeysTest(StorageFolder)` (place it above the `if __name__` block). `setUp` puts `psvita/G [PCSE00349] [USA] [NoNpDRM].zip` (4), `psvita/G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip` (5), `psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip` (6), `psvita/D [PCSE00349] [USA] [DLC-X].zip` (7) and `psvita/H [PCSE00001] [USA] [NoNpDRM].zip` (8). With `G`, `NEW`, `DLC` naming those keys and `VITA = {"bucket": "psvita", "games": [{"bucket": G}]}`:

```python
def test_without_a_cache_extras_are_found_and_statted(self):
    self.assertEqual(store.synced_keys(VITA), [G, DLC, NEW])
    self.assertEqual(store.list_system(VITA), {G: 4, DLC: 7, NEW: 6})
    self.assertEqual(store.available_keys(VITA, {}), [G, DLC, NEW])

def test_with_a_cache(self):
    self.build()
    with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("listed storage")), \
            mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted storage")):
        self.assertEqual(store.list_system(VITA), {G: 4, DLC: 7, NEW: 6})

def test_a_listed_dlc_is_not_doubled(self):
    s = {"bucket": "psvita", "games": [{"bucket": DLC}, {"bucket": G}]}
    self.assertEqual(store.synced_keys(s), [DLC, G, NEW])

def test_ignored_dlc_is_not_synced(self):
    with mock.patch.object(ignore, "_keys", frozenset({DLC})):
        self.assertEqual(store.synced_keys(VITA), [G, NEW])

def test_other_systems_do_not_read_the_folder(self):
    with mock.patch.object(inventory, "files", side_effect=AssertionError("listed")):
        self.assertEqual(store.synced_keys({"bucket": "gba", "games": [{"bucket": "gba/a.zip"}]}), ["gba/a.zip"])

def test_scrape_leaves_extras_out(self):
    from sync_roms import scrape_files
    self.assertEqual(scrape_files.bucket_roms([VITA])["psvita"], {G.split("/", 1)[1]})
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest discover -s tests -p test_inventory.py -k VitaSyncKeys`
Expected: ERROR (`module 'sync_roms.store' has no attribute 'synced_keys'`)

- [ ] **Step 3: Implement** `store.synced_keys(s)` beside `listed`, importing `vita` inside the function (`from . import vita  # imported here: vita imports chd, which imports this module`). Point `available_keys` and `list_system`'s share branch at it. In `scrape_files.bucket_roms`, drop keys where `vita.is_extra(k)` (import `vita` at the top of `scrape_files.py`).

- [ ] **Step 4: Update the README Vita paragraph** (`README.md:279`) with one sentence: a synced Vita game brings its DLC and newest update from `psvita/` (matched by the title id in the file names), on every layout. The `.psvita` file is only made for the game. The editors and Surprise list only games.

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest discover -s tests -p "test_inventory.py"` and `.venv/bin/python -m unittest discover -s tests -p "test_readme.py"`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add src/sync_roms/store.py src/sync_roms/scrape_files.py README.md tests/test_inventory.py
git commit -m "feat(vita): sync a game's DLC and newest update with it"
```

---

### Task 3: Budget counts a Vita game's extras

**Files:**
- Modify: `src/sync_roms/budget.py:21-37` (`game_costs`), `:84-87` (`fetch_bytes`)
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `vita.extras` (Task 1)
- Produces: `game_costs(card, system, keys)` (signature unchanged): a Vita game's cost also includes its extras' cached sizes. `fetch_bytes(system, keys, to_fetch)` (signature unchanged): `to_fetch` is called with the keys plus their extras.

- [ ] **Step 1: Write the failing tests** in `tests/test_budget.py`. Module level: `VITA = {"bucket": "psvita", "name": "Vita"}`, `G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"`, `DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"`, `UPD = "psvita/G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip"`. In `Budget`:

```python
def test_vita_game_costs_include_its_extras_and_count_once(self):
    self.cache["psvita/"] = {G: 1000, DLC: 20, UPD: 300}
    self.assertEqual(budget.game_costs({"layout": "other"}, VITA, [G]), ({G: 1320}, False))
    u = budget.system_usage({"layout": "other", "games": {"psvita": [g(G)]}}, VITA)
    self.assertEqual((u.bytes, u.count), (1320, 1))

def test_vita_fetch_counts_extras(self):
    self.cache["psvita/"] = {G: 1000, DLC: 20, UPD: 300}
    asked = []
    self.assertEqual(budget.fetch_bytes(VITA, [G], lambda s, keys: asked.extend(keys) or set(keys)), 1320)
    self.assertEqual(sorted(asked), sorted([G, DLC, UPD]))
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest discover -s tests -p test_budget.py -k vita`
Expected: FAIL (`{G: 1000}` != `{G: 1320}`; fetch 1000 != 1320)

- [ ] **Step 3: Implement** in `budget.py` (import `vita` at the top): in `game_costs`, after the costs dict is built (both return paths), add `sum(sizes[k] for k in extras)` to each game in `vita.extras(sized, sizes)`. In `fetch_bytes`, extend `keys` with their `vita.extras(keys, sizes)` before calling `to_fetch`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest discover -s tests -p test_budget.py`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/budget.py tests/test_budget.py
git commit -m "feat(vita): count a game's DLC and update in card budgets"
```

---

### Task 4: Editors and Surprise show only Vita games

**Files:**
- Modify: `src/sync_roms/edit.py:111-116` (`system_rows`)
- Modify: `src/sync_roms/cardedit.py:427-484` (`edit_system`: badge in `row_extras`)
- Modify: `src/sync_roms/surprise.py:144-155` (`units`)
- Test: `tests/test_edit.py`, `tests/test_cardedit.py`, `tests/test_surprise.py`

**Interfaces:**
- Consumes: `vita.is_extra`, `vita.extras` (Task 1); `budget.game_costs` including extras (Task 3)
- Produces: `edit.system_rows(s, in_bucket)` (signature unchanged) leaves out keys where `vita.is_extra(k)` unless the system lists them. `surprise.units` (signature unchanged) never yields an extra.

- [ ] **Step 1: Write the failing tests.** Each test module defines the same keys as Task 2: `G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"`, `DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"`, `NEW = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"`, `H = "psvita/H [PCSE00001] [USA] [NoNpDRM].zip"`.

`tests/test_edit.py`:

```python
def test_system_rows_hide_vita_extras_unless_listed(self):
    s = {"bucket": "psvita", "games": [{"bucket": DLC}]}
    self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [DLC, G])
    s["games"] = []
    self.assertEqual([r[1] for r in edit.system_rows(s, {G, DLC, NEW})], [G])
```

`tests/test_surprise.py`, next to `test_multi_disc_game_is_one_unit_playlist_first`:

```python
def test_vita_dlc_and_updates_are_never_units(self):
    vita_sys = {"bucket": "psvita", "bios": {"files": []}}
    self.assertEqual(surprise.units(vita_sys, {G, DLC, NEW}, None, set()), [[G]])
```

`tests/test_cardedit.py`, a new `class VitaFlow(Flow)` after `DiscFlow`: `setUp` sets `self.files["psvita/"] = {G: 10, DLC: 1, NEW: 2, H: 5}` (`H` a second game with no extras) and patches `store.repo_json` so `"systems"` also holds `{"name": "Sony PlayStation Vita", "bucket": "psvita", "folders": {"esde": "psvita"}, "bios": {"files": []}}` (copy `CATALOG`, don't change it: other tests count its systems).

```python
def test_only_games_are_rows_and_a_game_with_extras_is_marked(self):
    self.card()
    _, calls = self.run_system(returns([False, False]), bucket="psvita")
    _, labels, kw = calls[0]
    self.assertEqual(labels, [G.split("/", 1)[1], H.split("/", 1)[1]])
    self.assertEqual(kw["extras"][0][0], ("  🔗 3 files", "dim"))
    self.assertFalse(any("🔗" in text for text, _ in kw["extras"][1]))

def test_picking_a_game_saves_only_the_game(self):
    self.card()
    self.run_system(toggle(G.split("/", 1)[1]), bucket="psvita")
    self.assertEqual(store.card_games("c")["psvita"], [g(G)])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest discover -s tests -p "test_edit.py" -k vita`, then the same for `test_surprise.py` and `test_cardedit.py -k VitaFlow`
Expected: FAIL (extras appear as rows and units; no `🔗 3 files` badge)

- [ ] **Step 3: Implement.** `edit.system_rows`: filter `vita.is_extra(k) and k not in listed`. `surprise.units`: drop `vita.is_extra(k)` keys with the folder rows. `cardedit.edit_system`: compute `bundled = vita.extras(in_storage, in_storage)` beside `groups`. In `row_extras`, when the key isn't in `groups` but is in `bundled`, add `(f"  🔗 {len(bundled[key]) + 1} files", "dim")` in the same place as the disc badge. Import `vita` at the top of each module.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest discover -s tests -p "test_edit.py"`, `... -p "test_surprise.py"`, `... -p "test_cardedit.py"`, `... -p "test_collectionedit.py"`, `... -p "test_setedit.py"`
Expected: OK

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: OK (same test count as before plus the new ones, no failures)

- [ ] **Step 6: Commit**

```bash
git add src/sync_roms/edit.py src/sync_roms/cardedit.py src/sync_roms/surprise.py tests/test_edit.py tests/test_cardedit.py tests/test_surprise.py
git commit -m "feat(vita): list only games in the editors and Surprise"
```
