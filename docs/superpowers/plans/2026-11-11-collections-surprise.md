# Custom Collections and Surprise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop ES-DE themes/collections/settings and personal sets, add personal custom collections (editor, cards, ES-DE/Knulli frontend files) and a per-card Surprise collection picked at sync time.

**Architecture:** New modules `collections.py` (personal collection files), `collectionedit.py` + `listedit.py` (editor), `frontend.py` (ES-DE/Knulli collection files with ownership) and `surprise.py` (candidate rules, picking, history, sync step). Collection and surprise games enter a card's selection through `store.card_locked_games`, merged after exclusions; the card editor shows them as locked rows. Parts run in order A → B → C; each part leaves the suite green.

**Tech Stack:** Python 3 stdlib, curses UI (`picker.filter_list`), `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-11-collections-surprise-design.md`

## Global Constraints

- Task headings are `Task N (Xk)`: N is the run order; text refers to tasks by Xk (A1-A3, B1-B8, C1-C7).

- Tests: `python -m unittest discover -s tests` (CI's command); one file `python -m unittest discover -s tests -p 'test_x.py' -v`. Baseline before Part A: `Ran 760 tests … OK`.
- Test first for every behaviour; use `tests/helpers.py` / `tests/isolate.py` so nothing touches the real `~/.sync-roms`, storage or `/Volumes`.
- Conventional Commits, lowercase imperative. No `Co-Authored-By`, Claude or AI mention in any commit message (user rule).
- No real game lists in the repo (test fixtures use made-up or minimal names).
- Personal data lives under `store.data_dir()`: `collections/<id>.json`, `surprises.json`, `settings.json` key `surprise_ttl_days` (default 183).
- Card fields: `collections`, `frontend_collections`, `surprise` (`false` = off, absent = on), `surprises`.
- Markers: 💖 collection games, 🎁 surprises. Keys: card system list `l` collections, `u` Surprise; game lists `p` past surprises.
- Frontend layouts are exactly `esde` and `knulli`; sync-roms only touches collection files it recorded in `frontend_collections`.
- Keep README, CLAUDE.md's data-files table and `cards.schema.json` in step with each part.
- Line numbers in Parts B and C are from before Part A; re-find them by the quoted code.

## Review Focus

- A card whose storage is a local mirror: surprise candidates must come from real storage and the new picks must reach the mirror before downloading (C4/C5 tests with `runtime._mirror_root` set).
- A collection or surprise game the card also picks directly, or that a set covers: synced once, shown once (💖/🎁 wins), never duplicated in the frontend file (B2 `test_load_manifest_adds_them_after_picks_and_excluded_never_drops_them`; C3 dedupes surprises against collection games).
- ES-DE or Knulli settings file missing, empty, or with the `CollectionSystemsCustom` line absent: created/added without touching other lines (B6 `set_enabled` tests).
- A collection name that sanitises to empty, or two that sanitise alike (`A.B` and `AB`): the empty one is left out, the alike ones share one file with their lines merged and deduplicated (B6 `Wanted` test).
- A system with fewer candidates than its share, or no candidates at all, and a run where every system is exhausted: fewer than 10 surprises, no crash, no endless loop (C2 `test_every_system_runs_out_returns_what_there_is`).

---

## Part A: drop ES-DE extras and personal sets

### Task 1 (A1): `--upload-scrapes` stops reading ES-DE themes, collections and settings

Test command for the whole suite: `python3 -m unittest discover -s tests` (what CI runs, `.github/workflows/test.yml`).
Baseline before Part A: `Ran 760 tests` … `OK`. A single class: `python3 -m unittest tests.test_firmware_scrapes.<Class> -v`.

**Files:**
- Modify: `src/sync_roms/scrape_files.py:1` (docstring: "gamelists, settings, upload and cleanup" → "gamelists, media, upload and cleanup")
- Modify: `src/sync_roms/scrape_files.py:151-178` (delete the themes, collections and settings blocks of `plan_upload`; `return plan` stays)
- Modify: `src/sync_roms/scrape_files.py:182-185` (`text_keys`)
- Modify: `src/sync_roms/scrape_files.py:297` ("Files to upload (media, themes)" → "Files to upload (media)")
- Modify: `src/sync_roms/scrape_files.py:327-338` (`plan_clean` docstring and the `parts[1] == "esde"` check)
- Modify: `src/sync_roms/scrape_files.py:372` (`clean_scrapes` fetch)
- Modify: `README.md:380-382` (delete the three `themes/…`, `collections/*.cfg`, `settings/es_settings.xml` rows), `README.md:391-392` (delete "Themes, collections and settings are never touched.")
- Test: `tests/test_firmware_scrapes.py` (new class `EsdeExtrasUploadTest`, after `DerivedUploadTest`, ~line 449)

**Interfaces:**
- Consumes: nothing new.
- Produces: `scrape_files.text_keys(existing) -> list[str]` returns only `…/metadata.json` keys. `plan_upload(es_dir, roms, existing, remote_texts)` signature unchanged; its `texts` only ever hold `scrapes/<system>/metadata.json`. `scrape_plan.merge_lines` / `safe_settings` are now unused by `scrape_files` (Task A2 deletes them).

- [ ] **Step 1: Write the failing tests**

```python
class EsdeExtrasUploadTest(unittest.TestCase):
    def test_themes_collections_and_settings_are_not_uploaded(self):
        with tempfile.TemporaryDirectory() as es:
            touch(os.path.join(es, "themes", "my-theme", "theme.xml"))
            touch(os.path.join(es, "downloaded_media", "snes", "covers", "A.png"))
            os.makedirs(os.path.join(es, "collections"))
            with open(os.path.join(es, "collections", "custom-Fav.cfg"), "w") as f:
                f.write("%ROMPATH%/snes/A.sfc\n")
            os.makedirs(os.path.join(es, "settings"))
            with open(os.path.join(es, "settings", "es_settings.xml"), "w") as f:
                f.write('<?xml version="1.0"?>\n<bool name="ScraperRegionFallback" value="true" />\n')
            plan = scrape_files.plan_upload(es, {"snes": {"A.sfc"}}, {}, {})
        self.assertEqual([k for k, *_ in plan["files"]], ["scrapes/snes/covers/A.png"])
        self.assertEqual(plan["texts"], [])
        self.assertFalse(any("/esde/" in k for k, *_ in plan["files"] + plan["texts"] + plan["derived"]))

    def test_text_keys_are_metadata_only(self):
        existing = {"scrapes/gba/metadata.json": 1, "scrapes/esde/collections/custom-Fav.cfg": 1,
                    "scrapes/esde/settings.json": 1, "scrapes/gba/covers/A.png": 1}
        self.assertEqual(scrape_files.text_keys(existing), ["scrapes/gba/metadata.json"])

    def test_clean_leaves_old_esde_objects_alone(self):
        existing = {"scrapes/esde/themes/t/theme.xml": 1, "scrapes/esde/settings.json": 1,
                    "scrapes/esde/collections/custom-Fav.cfg": 1}
        self.assertEqual(scrape_files.plan_clean(existing, {}, {})[:2], ([], []))
```

The third test already passes; it guards the removal of the `parts[1] == "esde"` check (themes/collections are not in
`BUCKET_MEDIA` and `settings.json` isn't `metadata.json`, so nothing changes).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_firmware_scrapes.EsdeExtrasUploadTest -v`
Expected: `test_themes_collections_and_settings_are_not_uploaded` FAIL (`scrapes/esde/themes/my-theme/theme.xml` in files,
collection and settings texts), `test_text_keys_are_metadata_only` FAIL, `test_clean_leaves_old_esde_objects_alone` ok.

- [ ] **Step 3: Implement in `src/sync_roms/scrape_files.py`**

- Delete lines 151-178 (themes walk, collections merge, settings merge).
- `text_keys(existing) -> list[str]`: `[k for k in existing if k.endswith("/metadata.json")]`; docstring "Keys under
  scrapes/ of the metadata.json files we merge into."
- `clean_scrapes` line 372: `s3.fetch_texts(text_keys(existing))` (the filter is now redundant).
- `plan_clean`: drop `or parts[1] == "esde"` from line 338 and the sentence "Themes, collections and settings
  (scrapes/esde/) are never touched." from the docstring.
- Line 297 label: `"🖼️  Files to upload (media): "`.
- README: delete rows 380-382 and the last sentence of the `--clean-scrapes` paragraph (391-392).
- `json` stays imported (gamelist and clean still use it).

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_firmware_scrapes -v` then `python3 -m unittest discover -s tests`
Expected: all `ok`; full suite `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/scrape_files.py tests/test_firmware_scrapes.py README.md
git commit -m "refactor(scrapes): stop uploading es-de themes, collections and settings"
```

### Task 2 (A2): Sync and the mirror stop listing or installing `scrapes/esde/`

**Files:**
- Modify: `src/sync_roms/scrape_plan.py:10` (delete `from xml.sax.saxutils import escape, unescape`; only lines 115 and 373 use them)
- Modify: `src/sync_roms/scrape_plan.py:15` (section comment → "Scraped data (media, metadata)")
- Modify: `src/sync_roms/scrape_plan.py:34-42` (delete `SETTING_PREFIXES`, `SETTING_EXCLUDE`, `SETTING_UI`, `SETTING_LINE`)
- Modify: `src/sync_roms/scrape_plan.py:90-120` (delete `merge_lines`, `share_setting`, `safe_settings`)
- Modify: `src/sync_roms/scrape_plan.py:368-429` (delete `setting_line`, `update_settings`, `plan_esde_extras`)
- Modify: `src/sync_roms/scrape_plan.py:432-449` (`load_scrape_data`), `:474-497` (`build_scrape_plan`), `:500-504` (`describe_scrape_plan`), `:507-509` (`apply_scrape_plan`)
- Modify: `src/sync_roms/cli.py:896`, `:901`, `:977`
- Modify: `src/sync_roms/mirroring.py:12-13` (docstring), `:17`, `:20`, `:36`
- Modify: `README.md:226-228` (delete the "For the `esde` layout every sync also brings the shared extras…" paragraph), `README.md:451` (drop ", and all of `scrapes/esde/`" → "…metadata and media for those ROMs.")
- Test: `tests/test_firmware_scrapes.py` (delete `UnsafeKeyTest` 451-456 and `ShareSettingTest` 459-463; update `build_scrape_plan` call sites at lines 57-67, 74, 80, 122, 325; new class `EsdeExtrasSyncTest`; line 11 import adds `mirroring`)
- Test: `tests/test_sync_flow.py:165-166`

**Interfaces:**
- Consumes: Task A1 (nothing in `scrape_files` calls `merge_lines`/`safe_settings` any more).
- Produces:
  - `scrape_plan.load_scrape_data(systems) -> dict[str, tuple[dict, dict]]` — {bucket: (listing, metadata)}; no
    `esde` parameter, no second/third return value.
  - `scrape_plan.build_scrape_plan(layout_name, systems, data, rom_rels, dest_of, es_dir, present, base) -> dict` with
    keys exactly `"jobs"`, `"gamelists"`, `"writes"` (no `"extras"`).
  - `describe_scrape_plan(plan)` / `apply_scrape_plan(plan, base)` read only those three keys.
  - `mirroring.mirror_wanted(manifest)` lists `BIOS/`, `os/onion/Themes/` and per-system `scrapes/<bucket>/` only.
  - Part B writes its own `CollectionSystemsCustom` editor (`frontend.set_enabled`); nothing here is kept for it.

- [ ] **Step 1: Write the failing tests** (in `tests/test_firmware_scrapes.py`, after `DerivedUploadTest`/`EsdeExtrasUploadTest`; delete `UnsafeKeyTest` and `ShareSettingTest`)

```python
class EsdeExtrasSyncTest(unittest.TestCase):
    def test_sync_plan_has_no_esde_extras(self):
        with tempfile.TemporaryDirectory() as base:
            es = os.path.join(base, "ES-DE")
            plan = scrape_plan.build_scrape_plan("esde", [GBA], {"gba": (LISTING, META)}, {"gba": ["A.zip"]},
                                                 lambda s: os.path.join(base, "ROMs", "gba"), es, lambda p: True, base)
        self.assertEqual(set(plan), {"jobs", "gamelists", "writes"})
        self.assertFalse(any(k.startswith("scrapes/esde/") for k, *_ in plan["jobs"]))
        self.assertFalse(any(os.path.relpath(p, es).split(os.sep)[0] in ("themes", "collections", "settings")
                             for p, _ in plan["writes"]))

    def test_load_scrape_data_never_lists_scrapes_esde(self):
        with mock.patch.object(scrape_plan.s3, "list_sizes", return_value={}) as ls, \
                mock.patch.object(scrape_plan.s3, "fetch_texts", return_value={}) as ft:
            data = scrape_plan.load_scrape_data([GBA])
        self.assertEqual(data, {"gba": ({}, {})})
        self.assertEqual([c.args[0] for c in ls.call_args_list], ["scrapes/gba/"])
        ft.assert_called_once_with([])

    def test_mirror_wanted_skips_scrapes_esde_but_keeps_onion_themes(self):
        listings = {"BIOS/": {"BIOS/gba_bios.bin": 1}, "os/onion/Themes/": {"os/onion/Themes/t/a.png": 2},
                    "scrapes/esde/": {"scrapes/esde/themes/t/theme.xml": 3},
                    "gba/": {"gba/A.zip": 4}, "scrapes/gba/": {"scrapes/gba/covers/A.png": 5}}
        manifest = {"systems": [{"bucket": "gba", "games": [{"bucket": "gba/A.zip"}], "bios": {"files": ["gba_bios.bin"]}}]}
        with mock.patch.object(mirroring.s3, "read_root", return_value=None), \
                mock.patch.object(mirroring.s3, "list_sizes", side_effect=lambda p, sizes=True: listings.get(p, {})) as ls:
            wanted = mirroring.mirror_wanted(manifest)
        self.assertEqual(wanted, {"gba/A.zip": 4, "scrapes/gba/covers/A.png": 5, "BIOS/gba_bios.bin": 1,
                                  "os/onion/Themes/t/a.png": 2})
        self.assertNotIn("scrapes/esde/", [c.args[0] for c in ls.call_args_list])
```

Update existing call sites (drop the two `{}, {}` arguments after `data`): lines 57-58 (`args` tuple), 74, 122, 325.
Line 66: `apply_scrape_plan({"jobs": [], "gamelists": {}, "writes": plan["writes"]}, base)`. Line 80:
`self.assertEqual((plan["gamelists"], plan["writes"]), ({}, []))`.

`tests/test_sync_flow.py:165-166`, with exact arity so the cli wiring is checked:
```python
st.enter_context(mock.patch.object(scrape_plan, "load_scrape_data", lambda systems: {}))
st.enter_context(mock.patch.object(scrape_plan, "build_scrape_plan",
                                   lambda layout, systems, data, rels, dest_of, es_dir, present, base:
                                   {"jobs": [], "gamelists": {}, "writes": []}))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_firmware_scrapes tests.test_sync_flow`
Expected: errors — `TypeError` (missing/extra positional arguments) in `build_scrape_plan`/`load_scrape_data` tests and
the sync-flow tests that reach the scrape step; `test_mirror_wanted_…` FAIL (`scrapes/esde/themes/t/theme.xml` in wanted).

- [ ] **Step 3: Implement**

- `scrape_plan.py`: delete the constants and functions listed under Files and the `xml.sax.saxutils` import (`re`,
  `json` stay: `parse_gamelist`, `dump_json`, `load_scrape_data` use them).
- `load_scrape_data(systems)`: list each `scrapes/<bucket>/`, fetch only the `metadata.json` keys present, return
  `data`. Docstring: "The storage's scrape data for the chosen systems: {storage folder: (listing, metadata)}."
- `build_scrape_plan(layout_name, systems, data, rom_rels, dest_of, es_dir, present, base)`: plan starts as
  `{"jobs": [], "gamelists": defaultdict(dict), "writes": []}`; delete lines 495-496. Docstring drops "ES-DE extras".
- `describe_scrape_plan`: `jobs = plan["jobs"]`; the writes suffix reads `f", {len(plan['writes'])} text file(s)"`.
- `apply_scrape_plan`: `downloads.run_downloads(plan["jobs"], …)`; docstring "Download the media, then write the
  gamelists and text files."
- `cli.py:896` → `scraped["data"] = scrape_plan.load_scrape_data(chosen)`; `:901` →
  `scrape_plan.build_scrape_plan(layout_name, chosen, scraped["data"], scraped["rels"], dest_of, es_dir, present, base)`;
  `:977` → `if clean_card and (plan["jobs"] or plan["writes"] or plan["gamelists"]):`. Onion themes (`cli.py:858-875`,
  `:954-955`) are untouched.
- `mirroring.py`: prefixes tuple at line 17 becomes `("BIOS/", runtime.THEMES_PREFIX)`, line 20 `bios, themes = …`,
  delete line 36; docstring ends "…the scraped data of those ROMs, and storage's Onion themes."
- README: delete 226-228; line 451 as listed.

- [ ] **Step 4: Run to verify they pass**

Run: `grep -n -E "esde/|merge_lines|share_setting|safe_settings|setting_line|update_settings|plan_esde_extras|SETTING_" src/sync_roms/{scrape_plan,scrape_files,mirroring,cli}.py README.md`
Expected: no output (tests keep `scrapes/esde/` keys on purpose: they check those objects are ignored).
Run: `python3 -m unittest discover -s tests`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/scrape_plan.py src/sync_roms/cli.py src/sync_roms/mirroring.py tests/test_firmware_scrapes.py tests/test_sync_flow.py README.md
git commit -m "refactor(sync): stop installing es-de themes, collections and settings"
```

### Task 3 (A3): Remove personal sets

**Files:**
- Modify: `src/sync_roms/store.py:428-430` (delete `personal_sets_dir`), `:466-487` (`load_sets`), `:494-516` (delete `personal_set_problem`, `save_personal_set`). `set_slug`, `set_data`, `set_text`, `read_set_file`, `repo_set_files`, `PRETTY`, `key_title`, `sort_games` stay (setedit, edit and Part B use them).
- Modify: `src/sync_roms/setedit.py:19` (drop "(personal sets aren't included)"), `:23` (drop the comment ", next to the personal-set writer")
- Modify: `src/sync_roms/commands.py:404`, `:408` (`check_sets`)
- Modify: `src/sync_roms/cardedit.py:11` (delete `MAKE_SET_KEY`), `:16` (`LIST_HINT`), `:297` (hotkeys), `:309-312` (the `else:` make-set branch)
- Modify: `src/sync_roms/edit.py:213-236` (delete `make_set_from_extras`)
- Modify: `src/sync_roms/cli.py:179` (`TOPICS["check"]`: "the sets (built-in and ~/.sync-roms/sets)" → "the sets")
- Modify: `README.md:486-487`, `:507`, `:526`; `CLAUDE.md:62`
- Test: `tests/test_editor_data.py` — delete class `PersonalSets` (lines 21-78: `test_save_and_load_alongside_repo_sets`, `test_ids_cannot_collide`, `test_hand_placed_colliding_file_is_skipped_and_bad_json_ignored`, `test_editor_makes_a_set_from_extras`, `test_editor_refuses_empty_extras_and_colliding_name`); replace `CheckSystemsKey.test_personal_set_files_are_checked` (134-147); trim `CheckBucketKeys.test_missing_keys_are_reported_per_file` (150-162); keep `target()` (used by `Notes`)
- Test: `tests/test_cardedit.py` (new test in `Flow`)

**Interfaces:**
- Consumes: nothing from A1/A2.
- Produces: `store.load_sets() -> list[dict]` reads only `REPO_DATA/sets/*.json` (sorted by name lowercased); no
  warnings about `~/.sync-roms/sets/`. Gone: `store.personal_sets_dir`, `store.save_personal_set`,
  `store.personal_set_problem`, `cardedit.MAKE_SET_KEY`, `edit.make_set_from_extras`. The system list's hotkeys are
  `(FULL_KEY, CLEAR_ALL_KEY)`, so `m` is free there (Part B adds `COLLECTIONS_KEY = "l"` to this tuple). A card's
  `games.sets` id that no longer loads is still dropped by the existing `prune_unknown_sets`.

- [ ] **Step 1: Write the failing tests**

`tests/test_editor_data.py`, replacing `PersonalSets`:
```python
class NoPersonalSets(DataDir):
    def test_load_sets_ignores_the_data_folder_sets(self):
        os.makedirs(self.path("sets"))
        self.write_json("sets/mine.json", {"name": "Mine", "games": []})
        self.write_json("sets/pinball.json", {"name": "Fake", "games": []})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            sets = store.load_sets()
        self.assertEqual(sorted(x["id"] for x in sets), sorted(x["id"] for x in store.repo_set_files()))
        self.assertEqual([x["name"] for x in sets if x["id"] == "pinball"], ["Pinball"])
        self.assertEqual(err.getvalue(), "")

    def test_personal_set_helpers_are_gone(self):
        for name in ("personal_sets_dir", "save_personal_set", "personal_set_problem"):
            self.assertFalse(hasattr(store, name), name)
        self.assertFalse(hasattr(edit, "make_set_from_extras"))
```
(`DataDir.write_json(name, data)` writes under the throwaway data dir, `tests/helpers.py:56`.)

`CheckSystemsKey`, replacing `test_personal_set_files_are_checked`:
```python
    def test_files_in_the_data_folder_sets_are_not_checked(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde"}})
        os.makedirs(self.path("sets"))
        self.write_json("sets/mine.json", {"name": "Mine", "games": [{"title": "B", "system": "nope", "bucket": "nope/B.zip"}]})
        with open(self.path("sets/bad.json"), "w") as f:
            f.write("{oops")
        self.assertEqual(commands.check_data(), [])
```

`CheckBucketKeys.test_missing_keys_are_reported_per_file`: drop the `sets/mine.json` part (the `os.makedirs`, the file
and the `nes` listing; personal sets are no longer read, so `nes/D2.zip` would never be reported). It becomes:
```python
    def test_missing_keys_are_reported_per_file(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"device": "full", "layout": "esde",
                             "games": {"gba": [{"title": "A", "bucket": "gba/A.zip"}, {"title": "B", "bucket": "gba/B.zip"}]}}}, f)
        problems = commands.check_data(lambda system: {"gba/A.zip"} if system == "gba" else set())
        self.assertTrue(any("gba/B.zip" in p for p in problems))
        self.assertFalse(any("gba/A.zip" in p for p in problems))
        self.assertEqual(commands.check_data(), [])
```
(B1 brings the multi-file case back as `collections/mine.json`.)

`tests/test_cardedit.py`, in `Flow`:
```python
    def test_system_list_offers_no_make_set_key(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        kw = self.run_card(returns(None))[0][2]
        self.assertNotIn("m", kw["hotkeys"])
        self.assertNotIn("make set", kw["hint"])
        self.assertFalse(hasattr(cardedit, "MAKE_SET_KEY"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_editor_data tests.test_cardedit`
Expected: `test_load_sets_ignores_the_data_folder_sets` FAIL ("mine" loaded, a "pinball" warning on stderr),
`test_personal_set_helpers_are_gone` FAIL, `test_files_in_the_data_folder_sets_are_not_checked` FAIL (problems for
`sets/mine.json` and `sets/bad.json`), `test_system_list_offers_no_make_set_key` FAIL (hotkeys include `"m"`);
the trimmed `test_missing_keys_are_reported_per_file` passes before and after.

- [ ] **Step 3: Implement**

- `store.load_sets() -> list[dict]`: `return sorted(repo_set_files(), key=lambda x: x["name"].lower())`. Docstring:
  "Game sets from the repo's data/sets/*.json, sorted by name." plus the existing file-shape lines (475-477); drop the
  personal-file sentence and the `~/.sync-roms/sets` mention. Delete `personal_sets_dir`, `personal_set_problem`,
  `save_personal_set`.
- `commands.check_sets`: `folders = [(store.REPO_DATA + "/sets", "")]`; docstring "Check every repo set file and
  return …". Keep the loop as is.
- `cardedit.py`: delete line 11; `LIST_HINT = "Enter games · f full · D clear all · Esc back · / filter"`; line 297
  `hotkeys=(FULL_KEY, CLEAR_ALL_KEY)`; delete the `else:` branch 309-312 (the `elif key == CLEAR_ALL_KEY:` branch and
  the `continue` stay). `META_KEY = "m"` on the game list is unrelated and stays.
- `edit.py`: delete `make_set_from_extras` (213-236); `os`, `note`, `new_target` are still used elsewhere.
- `setedit.py:19,23`: drop the personal-set wording.
- `cli.py:179` (`TOPICS["check"]`): "Validates cards.json, device-systems.json and the sets: bad JSON, …".
- Remove imports the deleted tests leave unused in `tests/test_editor_data.py` (check `tempfile`, `mock`, `picker`,
  `cardedit` with `python3 -m pyflakes tests/test_editor_data.py` if available, else grep).
- README:
  - 486-487: "…`f` again brings the game list back), `m` saves the card's picked games as a personal set. Games save…"
    → "…`f` again brings the game list back). Games save…".
  - 507: delete the "Personal sets are files in `~/.sync-roms/sets/<id>.json` …" paragraph (and its blank line).
  - 526: "A set file (in the package's `data/sets/` or your `~/.sync-roms/sets/`) is" → "A set file (in the package's
    `data/sets/`) is".
- CLAUDE.md line 62: after "An old `~/.sync-roms/games.json` is left on disk and never read." add "Old personal sets
  in `~/.sync-roms/sets/` are left on disk and never read; sets only come from the repo."

- [ ] **Step 4: Run to verify they pass**

Run: `grep -rn -E "personal_set|personal_sets_dir|save_personal_set|MAKE_SET_KEY|make_set_from_extras|make set|sync-roms/sets" src/ README.md`
Expected: no output (the new tests and CLAUDE.md name the removed helpers and `~/.sync-roms/sets/` on purpose).
Run: `python3 -m unittest discover -s tests`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/store.py src/sync_roms/setedit.py src/sync_roms/commands.py src/sync_roms/cardedit.py src/sync_roms/edit.py src/sync_roms/cli.py tests/test_editor_data.py tests/test_cardedit.py README.md CLAUDE.md
git commit -m "refactor(sets): remove personal sets"
```

## Part B: custom collections

### Interface corrections and additions (read first)

- **`merge_lists` does not take collection games.** `load_manifest` applies `excluded` *after* `merge_lists`
  (`store.py:324-330`), so games merged there would be excluded. Corrected: `merge_lists` is unchanged; new
  `store.merge_locked(systems: list[dict], locked: dict[str, list[dict]]) -> None` appends locked games (deduplicated by
  bucket key) and `load_manifest` calls it after the exclusion step. `budget` calls `store.card_locked_games` directly.
- **`card_locked_games` shape:** `{system bucket: [{"title", "bucket", "from"}]}`, each game's keys (`[bucket] + files`) expanded into
  entries of their own (as `store.set_games` does), so sync, the mirror and the budget see every disc. No `"system"`
  key (the shape `merge_lists` produces). Collection ids the card names that don't load are skipped.
- **Module name:** `sync_roms/collections.py` is fixed by the interfaces. Relative imports never clash with the stdlib,
  but `budget.py`, `edit.py`, `cli.py` and `m3u.py` already `from collections import ...`; import it everywhere as
  `from . import collections as colls` (`store.py` imports it inside `load_manifest`: `collections.py` imports `store`).
- **Added (part C may use them):** `collections.remove_from_cards(collection_id) -> list[str]`;
  `frontend.wanted_collections(layout_name, collections, systems, on_card) -> dict[str, list[str]]` (C passes a
  `{"name": "Surprise", "games": [...]}` pseudo collection in `collections`); `frontend.describe_collections(plan,
  layout_name) -> None`; `commands.CARD_FIELDS` (tuple of card fields `games export/import` carry as `@field value`
  lines; C appends its fields); new module `listedit.py` (concept-free list helpers moved out of `setedit.py`).
- Line numbers below are from before part A; A removes the personal-set code in `store.py:428-516`, `edit.py:213-236`,
  `cardedit.py:11,16,297,309-312` and `commands.py:408`, so later numbers in those files move up.

Run one test file: `python -m unittest discover -s tests -p 'test_collections.py' -v`. Whole suite (CI's command):
`python -m unittest discover -s tests`.

### File Structure

- Create `src/sync_roms/collections.py`: collection files in `~/.sync-roms/collections/` (load, save, delete, name
  check, removing an id from cards).
- Create `src/sync_roms/data/collections.schema.json`: a collection file's schema.
- Create `src/sync_roms/listedit.py`: concept-free games-list helpers shared by the set and collection editors.
- Create `src/sync_roms/collectionedit.py`: the collection editor (local save, no git/gh).
- Create `src/sync_roms/frontend.py`: ES-DE/Knulli custom collection files and `CollectionSystemsCustom`.
- Modify `store.py` (locked games, selection), `budget.py` (counts them), `cardedit.py` (`l` hotkey, 💖 rows),
  `edit.py` (menu entry), `setedit.py` (imports helpers from `listedit`), `commands.py` (check, export/import, CLI
  group, completion), `cli.py` (help, sync wiring), `data/cards.schema.json`, `README.md`, `CLAUDE.md`.
- Tests: create `tests/test_collections.py`, `tests/test_collectionedit.py`, `tests/test_frontend.py`; extend
  `tests/test_budget.py`, `tests/test_cardedit.py`, `tests/test_edit.py`, `tests/test_editor_data.py`,
  `tests/test_commands.py`, `tests/test_sync_flow.py`.

### Task 4 (B1): Collection files, schema and `check`

**Files:**
- Create: `src/sync_roms/collections.py`, `src/sync_roms/data/collections.schema.json`, `src/sync_roms/frontend.py`
  (only `safe_name` for now)
- Modify: `src/sync_roms/commands.py:403-448` (`check_sets`), `:456-570` (`check_data`, cards loop `:529-546`), `:596`
  (`check_cmd` message); `src/sync_roms/cli.py:31` (`check` summary); `src/sync_roms/data/cards.schema.json`;
  `CLAUDE.md:49-68` (data-files table)
- Test: `tests/test_collections.py` (new), `tests/test_editor_data.py:116-122`

**Interfaces:**
- Consumes: `store.data_dir()`, `store.write_json`, `store.PRETTY`, `ui.warn`.
- Produces: `collections.collections_dir() -> str`; `load_collections() -> list[dict]` (each
  `{"id", "name", "description" ("" when absent), "games"}`, sorted by name lowercased);
  `save_collection(collection: dict) -> None`; `delete_collection(collection_id: str) -> None`;
  `collection_problem(name: str, existing_ids) -> str | None`; `collection_games(collection: dict) -> list[dict]`;
  `slug(name: str) -> str`; `remove_from_cards(collection_id: str) -> list[str]`;
  `commands.check_game_file(problems: list, path: str, where: str, systems: set) -> list[tuple[str, str]] | None`.

- [ ] **Step 1: Write the failing tests** in `tests/test_collections.py` (header as in `tests/test_budget.py`:
  `sys.path` insert, `import isolate`, `from helpers import DataDir`, `from sync_roms import collections, commands, store, ui`)

```python
FAVS = {"name": "Favs", "games": [{"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}]}


class Files(DataDir):
    def test_save_and_load_round_trip_sorted_by_name_without_the_id(self):
        collections.save_collection({"id": "zelda", "name": "zelda", "description": "", "games": []})
        collections.save_collection({"id": "favs", **FAVS})
        self.assertEqual([c["id"] for c in collections.load_collections()], ["favs", "zelda"])
        self.assertEqual(self.read("collections/favs.json"), FAVS)
        self.assertEqual(self.read("collections/zelda.json"), {"name": "zelda", "games": []})
        with open(self.path("collections/favs.json"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("}\n"))

    def test_unreadable_file_is_warned_and_skipped(self):
        collections.save_collection({"id": "favs", **FAVS})
        with open(self.path("collections/bad.json"), "w") as f:
            f.write("{")
        with mock.patch.object(ui, "warn") as warn:
            self.assertEqual([c["id"] for c in collections.load_collections()], ["favs"])
        self.assertIn("collections/bad.json", warn.call_args[0][0])

    def test_no_folder_is_no_collections_and_delete_removes_the_file(self):
        self.assertEqual(collections.load_collections(), [])
        collections.save_collection({"id": "favs", **FAVS})
        collections.delete_collection("favs")
        self.assertFalse(os.path.exists(self.path("collections/favs.json")))

    def test_collection_problem(self):
        self.assertEqual(collections.collection_problem(" ** ", []), "A collection needs a name with letters or digits.")
        self.assertEqual(collections.collection_problem("Favs!", ["favs"]), "There is already a collection with the id favs.")
        self.assertIsNone(collections.collection_problem("Favs 2", ["favs"]))
        for name in ("Surprise", "surprise.", "SUR*PRISE"):  # safe_name drops * and .
            self.assertEqual(collections.collection_problem(name, []), "Surprise is used by the Surprise option.")

    def test_collection_games_skips_entries_without_a_bucket(self):
        self.assertEqual(collections.collection_games({"games": [{"title": "x"}, *FAVS["games"]]}), FAVS["games"])

    def test_remove_from_cards_rewrites_only_cards_that_use_it(self):
        self.write_json("cards.json", {"a": {"collections": ["favs", "x"]}, "b": {"collections": ["favs"]}, "c": {}})
        self.assertEqual(collections.remove_from_cards("favs"), ["a", "b"])
        self.assertEqual(self.read("cards.json"), {"a": {"collections": ["x"]}, "b": {"collections": []}, "c": {}})


class Check(DataDir):
    def test_collection_files_are_checked(self):
        os.makedirs(self.path("collections"))
        self.write_json("collections/mine.json", {"name": "Mine", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
            {"title": "B", "system": "nope", "bucket": "nope/B.zip"},
            {"title": "C", "system": "gba", "bucket": "nes/C.zip"}]})
        with open(self.path("collections/bad.json"), "w") as f:
            f.write("{")
        problems = commands.check_data()
        self.assertIn("collections/mine.json: nope/B.zip: unknown system 'nope'", problems)
        self.assertIn("collections/mine.json: 'nes/C.zip' isn't under gba/", problems)
        self.assertTrue(any(p.startswith("collections/bad.json: not valid JSON") for p in problems))
        self.assertEqual(len(problems), 3)

    def test_card_collection_fields_are_checked(self):
        collections.save_collection({"id": "mine", "name": "Mine", "games": []})
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "collections": ["mine", "ghost"],
                                             "frontend_collections": "Mine"}})
        self.assertEqual(commands.check_data(), ["cards.json: c: unknown collection 'ghost'",
                                                 "cards.json: c: 'frontend_collections' must be a list of names"])
```

  In `tests/test_editor_data.py` `test_schemas_exist_and_cover_what_cards_store` add `"collections",
  "frontend_collections"` to the key loop, and `self.assertEqual(self.load("collections.schema.json")["required"],
  ["name", "games"])`. In its `CheckBucketKeys` (trimmed by A3) add the multi-file case back for collections:

```python
    def test_bucket_keys_cover_every_key_of_a_collection_game(self):
        os.makedirs(self.path("collections"))
        self.write_json("collections/mine.json", {"name": "Mine", "games": [
            {"title": "D", "system": "nes", "bucket": "nes/D.zip", "files": ["nes/D2.zip"]}]})
        problems = commands.check_data(lambda system: {"nes/D.zip"} if system == "nes" else set())
        self.assertTrue(any("nes/D2.zip" in p for p in problems))
        self.assertFalse(any("nes/D.zip" in p for p in problems))
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_collections.py' -v` — Expected: ERROR, `cannot import name 'collections' from 'sync_roms'`.
  Run: `python -m unittest discover -s tests -p 'test_editor_data.py' -v` — Expected: FAIL in `test_schemas_exist...`.

- [ ] **Step 3: Implement**

  - `collections.py`: `collections_dir()` is `os.path.join(store.data_dir(), "collections")`, read at call time
    (tests patch `data_dir`). `slug(name)` is its own copy of the set slug rule (`[^a-z0-9]+` → `-`, stripped); sets and
    collections share no code. `load_collections` reads `*.json` in file-name order, catching
    `(OSError, ValueError, AttributeError)` with `ui.warn(f"collections/{name}: couldn't be read ({e}), skipped")`.
    `save_collection` makes the folder and writes `{"name", "description" (only when non-empty), "games"}` with
    `store.write_json(..., **store.PRETTY)`. `collection_problem` messages exactly as in the test; a name whose
    `frontend.safe_name(name).lower() == "surprise"` is refused (Part C's Surprise collection owns that file name).
    `frontend.py` is created here holding only `safe_name` (rule in B6; no imports of `store` or `collections`, so
    `collections` imports it at module level); B6 adds the rest and its `Names` test. `remove_from_cards`
    loads cards, drops the id from each card's `collections` list (key kept, possibly `[]`), writes once with
    `store.write_cards` when anything changed, returns the changed card names sorted.
  - `commands.py`: move the per-file body of `check_sets` (`:410-447`, the open/parse and per-game checks) into
    `check_game_file(problems, path, where, systems)` (returns the `(system, key)` pairs, or None when the file is
    unusable); `check_sets` loops repo set files over it; a new `check_collections(problems, systems)` loops
    `collections_dir()` with `where = f"collections/{name}"` and returns `{where: pairs}`. `check_data` adds its result
    to `wanted` (so `--bucket-keys` covers collections) and, per card: `collections` must be a list of known ids
    (`f"cards.json: {name}: unknown collection {i!r}"`, or `"'collections' must be a list of collection ids"`),
    `frontend_collections` a list of strings (message as in the test). `check_cmd` success line: `"✅ cards.json,
    device-systems.json, the sets and your collections look fine"`; `cli.SUBCOMMANDS["check"]` summary likewise.
  - `collections.schema.json`: draft-07, object, `required: ["name", "games"]`, `name` string, `description` string,
    `games` array of `{title (string), system (string), bucket (string, minLength 1), files (array of strings),
    category (string), note (string)}` with `required: ["title", "system", "bucket"]`.
  - `cards.schema.json`: `collections` (array of strings, "Ids of the user's collections synced whole to this card")
    and `frontend_collections` (array of strings, "Custom collection names sync-roms wrote to the card's frontend").
  - `CLAUDE.md` data-files table, `~/.sync-roms/` row: add `collections/<id>.json` (one per collection:
    `{"name", "description"?, "games"}` like a set file, own loader/schema, never in the repo or storage) and the card
    fields `collections` (ids, top level of the card, synced whole, `excluded` never applies) and
    `frontend_collections` (names sync wrote to ES-DE/Knulli, so only those files are touched).

- [ ] **Step 4: Run to verify they pass** — both commands from Step 2. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/collections.py src/sync_roms/frontend.py src/sync_roms/data/collections.schema.json src/sync_roms/data/cards.schema.json src/sync_roms/commands.py src/sync_roms/cli.py CLAUDE.md tests/test_collections.py tests/test_editor_data.py
git commit -m "feat(collections): add personal collection files and check them"
```

### Task 5 (B2): Collection games in the selection and the budget

**Files:**
- Modify: `src/sync_roms/store.py:209-214` (add `card_locked_games`, `merge_locked` after `card_excluded`), `:316-332`
  (`load_manifest`); `src/sync_roms/budget.py:40-68`
- Test: `tests/test_collections.py`, `tests/test_budget.py`

**Interfaces:**
- Consumes: B1 `collections.load_collections`, `collection_games`.
- Produces: `store.card_locked_games(entry: dict, collections_by_id: dict) -> dict[str, list[dict]]`;
  `store.merge_locked(systems: list[dict], locked: dict[str, list[dict]]) -> None`; `load_manifest(card_names)` now
  includes every named card's collection games (so `mirroring.refresh_mirror`, which calls it with
  `all_card_names()`, mirrors them unchanged).

- [ ] **Step 1: Write the failing tests.** In `tests/test_collections.py`:

```python
FF7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
       "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}


class Selection(DataDir):
    def setUp(self):
        super().setUp()
        collections.save_collection({"id": "favs", "name": "Favs", "games": FAVS["games"] + [FF7]})
        collections.save_collection({"id": "more", "name": "More", "games": [{"title": "Zelda", "system": "gba", "bucket": "gba/Zelda.zip"}]})

    def by_id(self):
        return {c["id"]: c for c in collections.load_collections()}

    def test_locked_games_expand_files_and_say_where_they_come_from(self):
        locked = store.card_locked_games({"collections": ["favs", "ghost"]}, self.by_id())
        self.assertEqual(sorted(locked), ["gba", "psx"])
        self.assertEqual(locked["gba"], [{"title": "Ruby", "bucket": "gba/Ruby.zip", "from": "💖 Favs"}])
        self.assertEqual([g["bucket"] for g in locked["psx"]], ["psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"])
        self.assertEqual(store.card_locked_games({}, self.by_id()), {})

    def test_load_manifest_adds_them_after_picks_and_excluded_never_drops_them(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "collections": ["favs"],
                                             "games": {"gba": [{"bucket": "gba/A.zip"}, {"bucket": "gba/Ruby.zip"}]},
                                             "excluded": {"gba": ["gba/Ruby.zip"]}}})
        gba = next(s for s in store.load_manifest(["c"])["systems"] if s["bucket"] == "gba")
        self.assertEqual([g["bucket"] for g in gba["games"]], ["gba/A.zip", "gba/Ruby.zip"])

    def test_every_cards_collections_are_in_the_mirror_list(self):
        self.write_json("cards.json", {"a": {"collections": ["favs"]}, "b": {"collections": ["more"]}})
        gba = next(s for s in store.load_manifest(store.all_card_names())["systems"] if s["bucket"] == "gba")
        self.assertEqual(sorted(g["bucket"] for g in gba["games"]), ["gba/Ruby.zip", "gba/Zelda.zip"])
```

  In `tests/test_budget.py` `Budget`:

```python
    def test_collection_games_count_like_picks_and_ignore_exclusions(self):
        fav = {"id": "fav", "name": "Fav", "games": [{"system": "gba", "bucket": "gba/C.zip"}, {"system": "gba", "bucket": "gba/A.zip"}]}
        with mock.patch("sync_roms.collections.load_collections", lambda: [fav]):
            u = self.usage({"games": {"gba": [g("gba/A.zip")]}, "collections": ["fav"],
                            "excluded": {"gba": ["gba/C.zip"]}}, "other")
        self.assertEqual((u.bytes, u.count), (500, 2))
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_collections.py' -v` — Expected: FAIL/ERROR in `Selection`
  (`no attribute 'card_locked_games'`). Run: `python -m unittest discover -s tests -p 'test_budget.py' -v` — Expected:
  FAIL `(100, 1) != (500, 2)`.

- [ ] **Step 3: Implement**

  - `card_locked_games`: for each id in `entry.get("collections")` (a non-list is ignored) that is in
    `collections_by_id`, every key of each game (`[bucket] + files`; `files` are its other keys) becomes `{"title", "bucket", "from": f"💖 {name}"}`
    under the game's `system`, first occurrence wins per system.
  - `merge_locked`: appends to the system with that bucket, skipping keys already in its `games`; unknown systems
    skipped; leaves a full system's flag alone.
  - `load_manifest`: after the exclusion block (`:326-330`), `from . import collections` and, for each name in
    `card_names`, `merge_locked(manifest["systems"], card_locked_games(cards.get(n) or {}, by_id))`.
  - `budget._system_usage(card, system, sets, collections_by_id)`: in the list branch, append the locked keys of that
    system not already in `keys` after the excluded filter. `system_usage`/`system_usages` load the collections once
    (`{c["id"]: c for c in colls.load_collections()}`) next to `load_sets()`.

- [ ] **Step 4: Run to verify they pass** — both commands from Step 2, then the whole suite. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/store.py src/sync_roms/budget.py tests/test_collections.py tests/test_budget.py
git commit -m "feat(collections): sync a card's collection games and count them in its budget"
```

### Task 6 (B3): Card editor: `l` toggles collections, 💖 rows are locked

**Files:**
- Modify: `src/sync_roms/cardedit.py:10-20` (keys, hints), `:244-315` (`edit_card`: hotkeys `:297`, tuple branch
  `:302-313`), `:363-551` (`edit_system`: `states` `:414-418`, `row_extras` `:430-440`, `apply` `:452-467`,
  `filter_list` call `:525-530`)
- Test: `tests/test_cardedit.py` (class `Flow`, `:116`)

**Interfaces:**
- Consumes: B2 `store.card_locked_games`; B1 `collections.load_collections`.
- Produces: `cardedit.COLLECTIONS_KEY = "l"`; `cardedit.pick_collections(name: str, playable: set[str]) -> None`;
  `edit_system` locked rows driven by each locked game's `"from"` (C adds 🎁 rows by extending
  `card_locked_games`, no cardedit change needed beyond its own hotkeys).

- [ ] **Step 1: Write the failing tests** in `tests/test_cardedit.py` `Flow` (add `collections` to the
  `from sync_roms import ...` line; files go to the throwaway data dir):

```python
    def favs(self, *more):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [
            {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}, {"title": "Red", "system": "gb", "bucket": "gb/Red.gb"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.chd"}, *more]})

    def test_collections_hotkey_shows_playable_counts_and_space_toggles(self):
        self.favs({"title": "Pokemon", "system": "nds", "bucket": "nds/Pokemon.nds"})
        self.card()
        nds = {**system("nds", "Nintendo DS"), "folders": {}}  # the device runs it, but esde has no folder for it
        with mock.patch.dict(CATALOG, systems=CATALOG["systems"] + [nds]), \
                mock.patch.dict(DEVICE, systems=["gba", "gb", "nds"]):
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns((" ", 0)), returns(None), returns(None))
        self.assertEqual(calls[1][1], ["Favs  (2 playable, 2 not playable)"])
        self.assertEqual(calls[1][2]["extras"], [[("  ✅ on the card", "green")]])
        self.assertEqual(self.read("cards.json")["c"]["collections"], ["favs"])

    def test_enter_toggles_a_collection_off_again(self):
        self.favs()
        self.card(collections=["favs"])
        self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(0), returns(None), returns(None))
        self.assertEqual(self.read("cards.json")["c"]["collections"], [])

    def test_no_collections_is_a_note(self):
        self.card()
        with mock.patch.object(edit, "note") as note:
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(None))
        self.assertEqual(len(calls), 2)  # the system list twice, no collection list
        self.assertIn("sync-roms collections edit", note.call_args[0][0])

    def test_collection_games_are_on_locked_and_marked_even_when_excluded(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gba": ["gba/Ruby.zip"]})
        changed, calls = self.run_system(toggle())
        _, labels, kw = calls[0]
        i = labels.index("Ruby.zip")
        self.assertTrue(kw["initial"][i])
        self.assertEqual([n for n, on in enumerate(kw["locked"]) if on], [i])
        self.assertEqual(kw["locked_note"][i], "From 💖 Favs; take it off the card to remove this game")
        self.assertIn(("  💖 Favs", "cyan"), kw["extras"][i])
        self.assertFalse(changed)

    def test_collection_games_count_in_the_game_view_and_system_list(self):
        self.favs()
        self.card(size="1 GB", collections=["favs"])
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {}, "BIOS/": {}}
        _, calls = self.run_system(toggle())
        kw = calls[0][2]
        self.assertIn("· 2 file(s)", kw["status"](kw["initial"])[0])  # Ruby here, Red on Game Boy
        extras = self.run_card(returns(None))[0][2]["extras"]
        self.assertIn(("  1 picked", "green"), extras[0])
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_cardedit.py' -v` — Expected: the five new tests ERROR/FAIL
  (`no attribute 'COLLECTIONS_KEY'`, no `locked` kwarg).

- [ ] **Step 3: Implement**

  - `pick_collections(name, playable)`: `colls.load_collections()`; none → `edit.note(ui.yellow("ℹ️  No collections
    yet: make one in sync-roms collections edit (or 💖 Collections in sync-roms edit)."))`. Otherwise a single-mode
    `picker.filter_list("💖 Collections on <name> (Space/Enter toggles)", labels, extras=..., cursor=pos,
    hotkeys=(" ", "\t"), on_hotkey=...)` loop: label `f"{c['name']}  ({p} playable" + (f", {n} not playable)" if n
    else ")")` counting each game once by its `system` in/not in `playable`; extras `[("  ✅ on the card", "green")]`
    when on, else `[]`. Space/Tab toggles in place (`on_hotkey`, like `pick_set`), Enter toggles and reopens on that row,
    Esc returns. Each toggle saves at once: `store.update_card(name, collections=ids)` (on: appended; off: removed;
    an empty list is kept as `[]`).
  - `edit_card`: add `COLLECTIONS_KEY` to `hotkeys`; tuple branch calls
    `pick_collections(name, {s["bucket"] for s in can_play(catalog["systems"], setup)})`: only systems the setup
    syncs, i.e. the device can play them and `s["folders"].get(layout)` is set (`can_play` checks both through
    `store.system_applies`); taken before the storage-folder filter. `LIST_HINT = "Enter games · f full · l
    collections · D clear all · Esc back"` (61 cells; C6 adds `u surprise`; `tests/test_editor_data.py` `Hints`
    checks the 80-cell limit).
  - `edit_system`: `locked_from = {g["bucket"]: g["from"] for g in store.card_locked_games(card_entry(name, setup,
    cards), {c["id"]: c for c in colls.load_collections()}).get(bucket, [])}`. `states` → a key in `locked_from` is
    always on. `row_extras` appends `(f"  {from}", "cyan")`. `filter_list` gets `locked=[k in locked_from for k in keys]`
    and `locked_note=[f"From {locked_from[k]}; take it off the card to remove this game" if k in locked_from else ""
    for k in keys]`. `apply` skips keys in `locked_from` (a linked disc toggle must not add a direct pick or an
    exclusion for them). The budget needs no change here: `budget.game_costs` already sizes every row and `status`
    counts every key whose state is on.

- [ ] **Step 4: Run to verify they pass** — the Step 2 command and `-p 'test_editor_data.py'` (`Hints`). Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cardedit.py tests/test_cardedit.py
git commit -m "feat(edit): add collections to a card with l and lock their games on"
```

### Task 7 (B4): The collection editor

**Files:**
- Create: `src/sync_roms/listedit.py`, `src/sync_roms/collectionedit.py`
- Modify: `src/sync_roms/setedit.py:28-83` (`view`, `insert_game`, `reconcile`, `recategorize`, `ask_category`,
  `game_label` move to `listedit.py`; `setedit` imports them back under the same names)
- Test: `tests/test_collectionedit.py` (new); `tests/test_setedit.py` must pass unchanged

**Interfaces:**
- Consumes: B1 `collections.load_collections`, `save_collection`, `delete_collection`, `collection_problem`,
  `slug`, `remove_from_cards`; `edit.toggle_games`, `edit.system_rows`, `edit.set_rows`, `edit.note`,
  `edit.DELETE_KEY`; `m3u.file_groups`.
- Produces: `collectionedit.edit_collections() -> int`; `collectionedit.edit_one(collection: dict, systems: list,
  keys_of) -> None`; `collectionedit.system_rows(entry: dict, in_storage: set) -> list`;
  `collectionedit.fold_discs(games: list[dict], in_storage: set) -> None`. Part C adds its past-surprises filter to
  the "add games from a system" list in `edit_one`.

- [ ] **Step 1: Write the failing tests** in `tests/test_collectionedit.py` (header like `tests/test_setedit.py`, plus
  `from helpers import DataDir` and `from sync_roms import collectionedit, collections, edit, listedit, picker, setedit, store, ui`):

```python
SYSTEMS = [{"name": "Game Boy Advance", "bucket": "gba"}, {"name": "PlayStation", "bucket": "psx"}]
DISCS = {"psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd", "psx/Crash.chd"}
RUBY = {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}


class Shared(unittest.TestCase):
    def test_set_editor_uses_the_shared_helpers(self):
        for name in ("view", "insert_game", "reconcile", "recategorize", "ask_category", "game_label"):
            self.assertIs(getattr(setedit, name), getattr(listedit, name))


class Discs(unittest.TestCase):
    def test_a_multi_disc_game_is_one_row_and_keeps_its_discs(self):
        entry = {"bucket": "psx", "name": "PlayStation", "full_system": False, "games": []}
        self.assertEqual([r[1] for r in collectionedit.system_rows(entry, DISCS)], ["psx/Crash.chd", "psx/FF7.m3u"])
        games = [{"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u"}, {"title": "Crash", "system": "psx", "bucket": "psx/Crash.chd"}]
        collectionedit.fold_discs(games, DISCS)
        self.assertEqual(games[0]["files"], ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"])
        self.assertNotIn("files", games[1])


class Editor(DataDir):
    def run_editor(self, picks, asks=(), confirm=True, edit_one=None):
        picks, confirms = iter(picks), []
        with mock.patch.object(store, "repo_json", return_value=SYSTEMS), \
                mock.patch.object(picker, "filter_list", lambda *a, **k: next(picks)), \
                mock.patch.object(ui, "ask", side_effect=list(asks)), \
                mock.patch.object(ui, "confirm", lambda text, **k: confirms.append(text) or confirm), \
                mock.patch.object(edit, "note") as note, \
                mock.patch.object(collectionedit, "edit_one", edit_one or (lambda c, systems, keys_of: c["games"].append(dict(RUBY)))), \
                mock.patch("subprocess.run") as run:
            code = collectionedit.edit_collections()
        run.assert_not_called()  # no git, no gh
        return code, confirms, note

    def test_new_collection_is_saved_on_done(self):
        code, _, _ = self.run_editor([0, 2], asks=["Favs", "my faves"])  # ➕ New, then (one collection) ✅ Done
        self.assertEqual(code, 0)
        self.assertEqual(self.read("collections/favs.json"), {"name": "Favs", "description": "my faves", "games": [RUBY]})

    def test_quit_discards_everything(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.run_editor([(edit.DELETE_KEY, 0), 2])  # delete, then (no collections left) 🚪 Quit, confirmed
        self.assertTrue(os.path.exists(self.path("collections/favs.json")))

    def test_deleting_a_collection_cards_use_confirms_and_removes_it_from_them(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.write_json("cards.json", {"a": {"collections": ["favs", "x"]}, "b": {"collections": ["favs"]}, "c": {}})
        _, confirms, _ = self.run_editor([(edit.DELETE_KEY, 0), 1])  # delete, then ✅ Done
        self.assertIn("a, b", confirms[0])
        self.assertFalse(os.path.exists(self.path("collections/favs.json")))
        self.assertEqual(self.read("cards.json"), {"a": {"collections": ["x"]}, "b": {"collections": []}, "c": {}})

    def test_declined_delete_keeps_it(self):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [RUBY]})
        self.run_editor([(edit.DELETE_KEY, 0), 2], confirm=False)  # still one collection: index 2 is ✅ Done
        self.assertTrue(os.path.exists(self.path("collections/favs.json")))

    def test_an_empty_collection_is_refused_on_done(self):
        _, _, note = self.run_editor([0, 2, 3], asks=["Empty", ""], edit_one=lambda c, s, k: None, confirm=True)
        self.assertIn("Empty has no games", note.call_args_list[0][0][0])
        self.assertFalse(os.path.exists(self.path("collections")))
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_collectionedit.py' -v` — Expected: ERROR, `cannot import name 'collectionedit'`.

- [ ] **Step 3: Implement**

  - `listedit.py`: the six helpers moved verbatim (rename the `game_set` parameter of `view` to `listing`; docstrings
    say "a games list" rather than "set"). `setedit.py` replaces their definitions with
    `from .listedit import ask_category, game_label, insert_game, recategorize, reconcile, view`.
  - `collectionedit.py` mirrors `setedit.edit_sets`/`edit_one` (same menus, labels and hints with "collection" and 💖
    in place of "set" and 📦) with these differences:
    - `working = {c.pop("id"): c for c in copy.deepcopy(colls.load_collections())}`; systems from
      `store.repo_json("systems")` sorted by name; `keys_of` lists storage once per system as `setedit` does.
    - Menu: collections, `➕ New collection`, `✅ Done (save)`, `🚪 Quit without saving`; Esc = Done.
      `d` asks `ui.confirm(f"🗑️  Delete collection {name}?" + (f" Cards {', '.join(names)} use it and lose it too." if
      names else ""), default=False)` where `names` are cards whose `collections` hold the id; a confirmed delete is
      only recorded in `working` (Quit undoes it).
    - Done: a non-deleted collection with no games → `edit.note(ui.yellow(f"ℹ️  {name} has no games. Add some or delete
      it first."))` and back to the menu. Otherwise save every new or changed one with `save_collection`, and for each
      deleted id `delete_collection` + `remove_from_cards`; print `💖 Saved` with the folder; return 0. Quit with
      pending changes confirms first (as `setedit:281`).
    - New: name loop on `collection_problem(name, working)`; id `colls.slug(name)`; then the description; the id never
      changes on rename (cards reference it).
    - `edit_one`: as `setedit.edit_one` (switch games off via `edit.set_rows`, add from a system, change category,
      rename/description; `w` notes come from `edit.toggle_games`), except "add games from a system" uses
      `system_rows` and calls `fold_discs(collection["games"], keys_of(bucket))` after `reconcile`.
    - `system_rows(entry, in_storage)`: `edit.system_rows` minus the disc keys of each `m3u.file_groups` group whose
      `.m3u` is in storage. `fold_discs`: a game whose bucket is such an `.m3u` and has no `files` gets the group's
      discs, in group order.

- [ ] **Step 4: Run to verify they pass**

  Run: `python -m unittest discover -s tests -p 'test_collectionedit.py' -v` and
  `python -m unittest discover -s tests -p 'test_setedit.py' -v` — Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/listedit.py src/sync_roms/collectionedit.py src/sync_roms/setedit.py tests/test_collectionedit.py
git commit -m "feat(collections): add the collection editor"
```

### Task 8 (B5): Reach the editor: `edit` menu, `sync-roms collections edit`, help, completion, README

**Files:**
- Modify: `src/sync_roms/edit.py:406-429` (`menu()`); `src/sync_roms/commands.py:12` (`COMMANDS`), `:676-688`
  (`second_words`), `:767-769` (parser, next to `sets`); `src/sync_roms/cli.py:16-18` (`SUBCOMMANDS`), `:75-82`
  (`TOPICS`, add `collections` after `sets`); `README.md:263-264` (commands table), `:478-510` (editor section)
- Test: `tests/test_edit.py:91-185`, `tests/test_collectionedit.py`

**Interfaces:**
- Consumes: B4 `collectionedit.edit_collections() -> int`.
- Produces: top menu `["💳 Cards", "📦 Sets", "💖 Collections", "🧩 Device systems", "✅ Done (review & save)",
  "🚪 Quit without saving"]` (Done is index 4); CLI `sync-roms collections edit`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_edit.py`, update `test_top_menu_entries_are_exactly_...` to
  the list above (rename it `..._cards_sets_collections_and_device_systems`) and shift every top-menu index in the
  existing `run_edit`/`run_menu` picks (`Device systems` 2 → 3, `Done` 3 → 4). Add:

```python
    def test_choosing_collections_opens_the_collection_editor(self):
        from sync_roms import collectionedit
        with mock.patch.object(collectionedit, "edit_collections", return_value=0) as run:
            self.assertEqual(self.run_menu([2, 4]), 0)
        run.assert_called_once()
```

  In `tests/test_collectionedit.py`:

```python
class Wiring(unittest.TestCase):
    def test_command_help_and_completion(self):
        from sync_roms import cli
        with mock.patch.object(collectionedit, "edit_collections", return_value=0) as run:
            self.assertEqual(commands.run(["collections", "edit"]), 0)
        run.assert_called_once()
        self.assertEqual(commands.second_words()["collections"], ["edit"])
        self.assertEqual(cli.SUBCOMMANDS["collections"][0], "edit")
        self.assertIn("sync-roms collections edit", cli.TOPICS["collections"])
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_edit.py' -v` and
  `python -m unittest discover -s tests -p 'test_collectionedit.py' -v` — Expected: FAIL (menu list, `KeyError: 'collections'`).

- [ ] **Step 3: Implement**

  - `edit.menu()`: insert `"💖 Collections"` at index 2 (its `extras` entry `[]`), dispatch `i == 2` to a local
    `edit_collections()` that runs `collectionedit.edit_collections()` then `note("")` (as `edit_sets` does, without
    the `SystemExit` guard: it needs no tools); Device systems becomes 3, Done 4. Docstring of `edit_manifest` names
    Collections.
  - `commands.py`: `"collections"` in `COMMANDS`; parser `collections` → `edit` with
    `fn=lambda a: collectionedit.edit_collections()` (import `collectionedit` inside the lambda to avoid an import
    cycle through `edit`); `second_words()["collections"] = ["edit"]`.
  - `cli.py`: `SUBCOMMANDS["collections"] = ("edit", "edit your collections of favourite games (saved in
    ~/.sync-roms/collections/)")`; `"edit"` summary becomes `"interactive editor: cards, sets, collections, device
    systems (same as `games edit`)"`; `TOPICS["collections"]` in the style of `TOPICS["sets"]`: the command line, saved
    straight to `~/.sync-roms/collections/<id>.json` on Done (Quit discards), no git/gh, same keys as the set editor,
    deleting one used by cards asks and removes it from them, `l` in a card's system list adds one to a card.
  - `README.md`: commands table row for `collections edit`; the editor section's menu list gains **Collections**; the
    card-editor paragraph documents `l` (playable counts, Space/Enter toggles a whole collection) and 💖 rows (always
    on, can't be switched off, exclusions don't apply, counted in the budget); a short "Collections" paragraph after
    the set editor one: file location and format (as a set file), personal, never in storage or the repo.

- [ ] **Step 4: Run to verify they pass** — the Step 2 commands, then `python -m unittest discover -s tests -p 'test_completion.py' -v` and `-p 'test_readme.py'`. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/edit.py src/sync_roms/commands.py src/sync_roms/cli.py README.md tests/test_edit.py tests/test_collectionedit.py
git commit -m "feat(collections): open the collection editor from edit and sync-roms collections edit"
```

### Task 9 (B6): `frontend.py`: custom collection files and `CollectionSystemsCustom`

**Files:**
- Modify: `src/sync_roms/frontend.py` (B1 created it with `safe_name`)
- Test: `tests/test_frontend.py` (new, `unittest.TestCase` with a `tempfile.TemporaryDirectory` as the card root)

**Interfaces:**
- Consumes: `downloads.rom_rel`, `ui.warn`.
- Produces (as in interfaces.md, plus two): `FRONTEND_LAYOUTS = {"esde", "knulli"}`; `safe_name(name) -> str`;
  `collection_path(layout_name, base, name) -> str`; `settings_path(layout_name, base) -> str`;
  `collection_line(layout_name, folder, rel) -> str`; `set_enabled(text, layout_name, add: set[str], remove: set[str])
  -> str`; `plan_collections(layout_name, base, wanted: dict[str, list[str]], owned: list[str]) -> dict` with keys
  `writes, deletes, enable, disable, owned, warnings`; `apply_collections(plan, layout_name, base) -> None`;
  `wanted_collections(layout_name: str, collections: list[dict], systems: list[dict], on_card) -> dict[str, list[str]]`
  (`on_card(system, rel) -> bool`); `describe_collections(plan, layout_name) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
ESDE_SETTINGS = ('<?xml version="1.0"?>\n<bool name="ScrapeRatings" value="true" />\n'
                 '<string name="CollectionSystemsCustom" value="Mine,Old" />\n<string name="Theme" value="x" />\n')
LINE = '<string name="CollectionSystemsCustom" value="Favs" />'


class Names(unittest.TestCase):
    def test_safe_name_drops_what_es_de_rejects(self):
        self.assertEqual(frontend.safe_name(' A*"b,c.d/e:f;g<h>i\\j|k\nl\tm\rn '), "Abcdefghijklmn")

    def test_paths_and_lines(self):
        j = os.path.join
        self.assertEqual(frontend.collection_path("esde", "/c", "Favs"), j("/c", "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertEqual(frontend.collection_path("knulli", "/c", "Favs"),
                         j("/c", "system", "configs", "emulationstation", "collections", "custom-Favs.cfg"))
        self.assertEqual(frontend.settings_path("esde", "/c"), j("/c", "ES-DE", "settings", "es_settings.xml"))
        self.assertEqual(frontend.settings_path("knulli", "/c"), j("/c", "system", "configs", "emulationstation", "es_settings.cfg"))
        self.assertEqual(frontend.collection_line("esde", "gba", "Sub/A.zip"), "%ROMPATH%/gba/Sub/A.zip")
        self.assertEqual(frontend.collection_line("knulli", "gba", "Sub/A.zip"), "./roms/gba/Sub/A.zip")


class Enabled(unittest.TestCase):
    def test_set_enabled_keeps_other_names_and_the_rest_of_the_file(self):
        self.assertEqual(frontend.set_enabled(ESDE_SETTINGS, "esde", {"Favs"}, {"Old"}),
                         ESDE_SETTINGS.replace('value="Mine,Old"', 'value="Mine,Favs"'))

    def test_a_missing_line_is_added(self):
        text = '<?xml version="1.0"?>\n<string name="Theme" value="x" />\n'
        self.assertEqual(frontend.set_enabled(text, "esde", {"Favs"}, set()), text + LINE + "\n")
        cfg = '<?xml version="1.0"?>\n<config>\n\t<string name="A" value="b" />\n</config>\n'
        self.assertEqual(frontend.set_enabled(cfg, "knulli", {"Favs"}, set()), cfg.replace("</config>", f"\t{LINE}\n</config>"))

    def test_an_empty_file_gets_a_minimal_one(self):
        self.assertEqual(frontend.set_enabled("", "esde", {"Favs"}, set()), f'<?xml version="1.0"?>\n{LINE}\n')
        self.assertEqual(frontend.set_enabled("", "knulli", {"Favs"}, set()), f'<?xml version="1.0"?>\n<config>\n\t{LINE}\n</config>\n')

    def test_names_are_xml_escaped(self):
        text = '<string name="CollectionSystemsCustom" value="A&amp;B" />\n'
        self.assertEqual(frontend.set_enabled(text, "esde", {"R&B"}, set()),
                         '<string name="CollectionSystemsCustom" value="A&amp;B,R&amp;B" />\n')


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def test_new_collection_is_written_enabled_and_owned(self):
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, [])
        path = frontend.collection_path("esde", self.base, "Favs")
        self.assertEqual(plan, {"writes": [(path, "%ROMPATH%/gba/A.zip\n")], "deletes": [], "enable": {"Favs"},
                                "disable": set(), "owned": ["Favs"], "warnings": []})
        frontend.apply_collections(plan, "esde", self.base)
        self.assertEqual(self.read(path), "%ROMPATH%/gba/A.zip\n")
        self.assertIn('value="Favs"', self.read(frontend.settings_path("esde", self.base)))

    def test_a_name_clash_with_a_user_made_file_is_skipped_with_a_warning(self):
        path = frontend.collection_path("esde", self.base, "Favs")
        self.put(path, "mine\n")
        plan = frontend.plan_collections("esde", self.base, {"Favs": ["%ROMPATH%/gba/A.zip"]}, [])
        self.assertEqual((plan["writes"], plan["owned"], plan["enable"]), ([], [], set()))
        self.assertEqual(plan["warnings"], ["ES-DE already has a custom collection Favs that sync-roms didn't write; skipped"])
        frontend.apply_collections(plan, "esde", self.base)
        self.assertEqual(self.read(path), "mine\n")

    def test_an_owned_file_is_rewritten(self):
        path = frontend.collection_path("knulli", self.base, "Favs")
        self.put(path, "edited in the frontend\n")
        plan = frontend.plan_collections("knulli", self.base, {"Favs": ["./roms/gba/A.zip"]}, ["Favs"])
        self.assertEqual(plan["writes"], [(path, "./roms/gba/A.zip\n")])

    def test_a_renamed_or_removed_collection_deletes_the_old_file_and_unlists_it(self):
        old = frontend.collection_path("esde", self.base, "Old")
        self.put(old, "x\n")
        self.put(frontend.settings_path("esde", self.base), ESDE_SETTINGS)
        plan = frontend.plan_collections("esde", self.base, {"New": ["%ROMPATH%/gba/A.zip"]}, ["Old"])
        self.assertEqual((plan["deletes"], plan["disable"], plan["owned"]), ([old], {"Old"}, ["New"]))
        frontend.apply_collections(plan, "esde", self.base)
        self.assertFalse(os.path.exists(old))
        self.assertIn('value="Mine,New"', self.read(frontend.settings_path("esde", self.base)))

    def test_nothing_wanted_or_owned_touches_nothing(self):
        frontend.apply_collections(frontend.plan_collections("esde", self.base, {}, []), "esde", self.base)
        self.assertEqual(os.listdir(self.base), [])


class Wanted(unittest.TestCase):
    def test_names_that_sanitise_alike_share_one_file_and_an_empty_one_is_dropped(self):
        gba = {"bucket": "gba", "folders": {"esde": "gba"}}
        a = {"name": "A.B", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"}]}
        b = {"name": "AB", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"},
                                     {"title": "Y", "system": "gba", "bucket": "gba/Y.zip"}]}
        dots = {"name": "...", "games": [{"title": "X", "system": "gba", "bucket": "gba/X.zip"}]}
        got = frontend.wanted_collections("esde", [a, b, dots], [gba], lambda s, rel: True)
        self.assertEqual(got, {"AB": ["%ROMPATH%/gba/X.zip", "%ROMPATH%/gba/Y.zip"]})

    def test_lines_are_the_synced_games_on_systems_the_card_syncs(self):
        favs = {"name": "Fa.vs", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/Sub/A.zip"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u", "files": ["psx/FF7 (Disc 1).chd"]},
            {"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"}]}
        empty = {"name": "Empty", "games": [{"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"}]}
        gba, psx = {"bucket": "gba", "folders": {"esde": "gba"}}, {"bucket": "psx", "folders": {"esde": "psx"}}
        on_card = lambda s, rel: rel != "Gone.zip"  # noqa: E731
        self.assertEqual(frontend.wanted_collections("esde", [favs, empty], [gba], on_card), {"Favs": ["%ROMPATH%/gba/Sub/A.zip"]})
        self.assertEqual(frontend.wanted_collections("esde", [favs], [gba, psx], on_card),
                         {"Favs": ["%ROMPATH%/gba/Sub/A.zip", "%ROMPATH%/psx/FF7.m3u"]})
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_frontend.py' -v` — Expected: ERROR/FAIL, `module 'sync_roms.frontend' has no attribute 'collection_path'` (and the rest);
  `test_safe_name_drops_what_es_de_rejects` passes (B1).

- [ ] **Step 3: Implement** (`frontend.py`, no imports of `store` or `collections`)

  - Roots: esde `ES-DE`, knulli `system/configs/emulationstation` (card root is `/userdata`); collection files in
    `<root>/collections/custom-<name>.cfg`; settings `ES-DE/settings/es_settings.xml` and
    `<root>/es_settings.cfg`. Lines: esde `%ROMPATH%/<folder>/<rel>`, knulli `./roms/<folder>/<rel>` (Knulli's
    `roms_dir` in `layouts.json`).
  - `safe_name`: drop `* " , . / : ; < > \ |`, `\n`, `\t`, `\r`, then `strip()`.
  - `set_enabled`: find the line with `re.compile(r'<string name="CollectionSystemsCustom" value="([^"]*)"\s*/>')`;
    names are the value `xml.sax.saxutils.unescape`d and split on `,` (empty parts dropped); keep their order minus
    `remove`, append `add` names not already there in sorted order; write back with `saxutils.escape(value,
    {'"': "&quot;"})`, replacing only the matched span. No match: esde appends `LINE + "\n"` (after a newline if the
    text doesn't end with one); knulli inserts `"\t" + LINE + "\n"` before the last `</config>` (appends when there is
    none). `text == ""` → the minimal files in the tests. An empty result keeps the line with `value=""`.
  - `plan_collections`: for each wanted name in sorted order: not in `owned` and its file exists → warning (exact text in
    the test, the layout label from `{"esde": "ES-DE", "knulli": "Knulli"}`), skipped; else a write with
    `"\n".join(lines) + "\n"`. `deletes`: owned names not written whose file exists. `enable` = written names,
    `disable` = owned names not written, `owned` = written names sorted.
  - `apply_collections`: makedirs + write each file (`encoding="utf-8", newline="\n"`), remove each delete; when
    `enable` or `disable` is non-empty, read the settings file (`""` when missing), and write `set_enabled(...)` back
    (making its folder) only when the text changed.
  - `wanted_collections`: `{s["bucket"]: s for s in systems}`; per collection, per game whose `system` is there (its
    `files` never listed), `rel = downloads.rom_rel(game["bucket"], False)`, kept when `on_card(system, rel)`; key
    `safe_name(name)`; two collections with one safe name share it (lines merged, deduplicated, in order); names with
    no lines left out.
  - `describe_collections`: one dim line per write (`💖 would write <file name> (<n> game(s))`), delete (`would delete
    <file name>`) and the names enabled/unlisted in the settings file; warnings with `ui.warn`.

- [ ] **Step 4: Run to verify they pass** — the Step 2 command. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/frontend.py tests/test_frontend.py
git commit -m "feat(sync): write custom collection files for es-de and knulli"
```

### Task 10 (B7): Sync writes the card's collections into ES-DE and Knulli

**Files:**
- Modify: `src/sync_roms/cli.py:12` (imports), `:903-930` (dry-run block), `:981-985` (after `prune_empty_systems`,
  before `clean_android_media`); `README.md` (new "Collections in ES-DE and Knulli" subsection under "How it works"
  `:603`)
- Test: `tests/test_sync_flow.py:140-173` (`SyncFlowTest.run_sync`) and new tests in `SyncFlowTest`

**Interfaces:**
- Consumes: B6 `frontend.FRONTEND_LAYOUTS`, `wanted_collections`, `plan_collections`, `apply_collections`,
  `describe_collections`; B1 `collections.load_collections`; `store.update_card`.
- Produces: a local `frontend_step(dry_run: bool) -> None` inside `sync_card` that part C's Surprise extends with its
  pseudo collection.

- [ ] **Step 1: Write the failing tests.** Extend `run_sync` with keyword params `manifest=MANIFEST`, `setup=(None,
  "esde")`, `files=()` (paths created under the card folder before the run), `colls=()` (patched in as
  `collections.load_collections`) and `after=None` (called with the card folder before it is removed; its result is
  kept in `self.after`). Then:

```python
GAME = {"title": "Game", "system": "gba", "bucket": "gba/Game.zip"}
FAVS = {"id": "favs", "name": "Favs", "games": [GAME]}


def read_from(card_dir, *parts):
    path = os.path.join(card_dir, *parts)
    return open(path).read() if os.path.exists(path) else None


    def test_esde_card_gets_its_collection_written_enabled_and_owned(self):
        _, _, updates, _, _, _ = self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], files=["ROMs/gba/Game.zip"],
                                               after=lambda d: (read_from(d, "ES-DE", "collections", "custom-Favs.cfg"),
                                                                read_from(d, "ES-DE", "settings", "es_settings.xml")))
        cfg, settings = self.after
        self.assertEqual(cfg, "%ROMPATH%/gba/Game.zip\n")
        self.assertIn('<string name="CollectionSystemsCustom" value="Favs" />', settings)
        self.assertIn({"frontend_collections": ["Favs"]}, updates)

    def test_knulli_card_writes_under_system_configs(self):
        manifest = {**MANIFEST, "systems": [{**MANIFEST["systems"][0], "folders": {"knulli": "gba"}}],
                    "layouts": {"knulli": {"label": "Knulli", "roms_dir": "roms", "bios_dir": "bios"}}}
        self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], manifest=manifest, setup=(None, "knulli"),
                      files=["roms/gba/Game.zip"],
                      after=lambda d: (read_from(d, "system", "configs", "emulationstation", "collections", "custom-Favs.cfg"),
                                       read_from(d, "system", "configs", "emulationstation", "es_settings.cfg")))
        cfg, settings = self.after
        self.assertEqual(cfg, "./roms/gba/Game.zip\n")
        self.assertIn("<config>", settings)

    def test_dry_run_describes_and_writes_nothing(self):
        _, out, updates, _, _, _ = self.run_sync(cards={"collections": ["favs"]}, colls=[FAVS], dry_run=True,
                                                 after=lambda d: os.path.exists(os.path.join(d, "ES-DE", "collections")))
        self.assertIn("custom-Favs.cfg", out)
        self.assertFalse(self.after)
        self.assertFalse([u for u in updates if "frontend_collections" in u])

    def test_a_collection_game_on_a_system_the_device_cant_play_is_ignored(self):
        psx = {"name": "PlayStation", "bucket": "psx", "folders": {"esde": "psx"}, "bios": {"files": []},
               "games": [{"bucket": "psx/FF7.chd"}]}
        device = {"id": "d", "name": "D", "note": "", "systems": ["gba"]}
        favs = {**FAVS, "games": [GAME, {"title": "FF7", "system": "psx", "bucket": "psx/FF7.chd"}]}
        self.run_sync(cards={"collections": ["favs"]}, colls=[favs], manifest={**MANIFEST, "systems": MANIFEST["systems"] + [psx]},
                      setup=(device, "esde"), files=["ROMs/gba/Game.zip", "ROMs/psx/FF7.chd"],
                      after=lambda d: read_from(d, "ES-DE", "collections", "custom-Favs.cfg"))
        self.assertEqual(self.after, "%ROMPATH%/gba/Game.zip\n")
```

- [ ] **Step 2: Run to verify they fail**

  Run: `python -m unittest discover -s tests -p 'test_sync_flow.py' -v` — Expected: the four new tests FAIL (no
  collection file, no `custom-Favs.cfg` in the output); existing tests still pass with the new defaults.

- [ ] **Step 3: Implement** in `sync_card`

  - `frontend_step(dry_run)`: return at once unless `layout_name in frontend.FRONTEND_LAYOUTS`. Read the card's entry
    fresh (`store.load_cards().get(card) or {}`), its `collections` ids against `colls.load_collections()` (in the
    card's order) and its `frontend_collections`; nothing wanted and nothing owned → return. `wanted =
    frontend.wanted_collections(layout_name, card_colls, systems, on_card)` with `systems` (the card's synced systems:
    device plays them and the layout has a folder, so other games are ignored silently). `on_card(s, rel)` is
    `os.path.exists(os.path.join(dest_of(s), rel))`, and in a dry run also true for keys of a chosen system that are in
    its storage listing (they would be downloaded). `plan = frontend.plan_collections(layout_name, base, wanted, owned)`.
    Dry run: `frontend.describe_collections(plan, layout_name)` only. Otherwise warnings via `ui.warn`,
    `frontend.apply_collections(plan, layout_name, base)`, mark the card for cleaning (`clean._clean_root = base`)
    when `clean_card` and anything was written or deleted, and `store.update_card(card, frontend_collections=
    plan["owned"])` when it differs from `owned`. Print `💖 Wrote <n> collection(s) for <label>` when any were written.
  - Call it with `True` in the dry-run block after the scrape description (`:920`), and with `False` after the
    `prune_empty_systems` loop (`:983`), so ROMs are on the card first.
  - `README.md`: the frontend table from the spec (files, line formats, `CollectionSystemsCustom`), the name rule,
    ownership (only files sync-roms wrote; a clash with a frontend-made collection is skipped with a warning; removed
    or renamed collections are deleted and unlisted), "files are rewritten each sync, so edits made to them in the
    frontend are lost", and "close the frontend before syncing: it rewrites its settings file from memory". Only
    ES-DE and Knulli cards get them; `--dry-run` lists what would be written.

- [ ] **Step 4: Run to verify they pass** — the Step 2 command, then the whole suite. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cli.py README.md tests/test_sync_flow.py
git commit -m "feat(sync): show a card's collections as custom collections in es-de and knulli"
```

### Task 11 (B8): `games export`/`import` carry `collections` and `frontend_collections`

**Files:**
- Modify: `src/sync_roms/commands.py:261-292` (`games_export`, `games_import`); `src/sync_roms/cli.py:60-71`
  (`TOPICS["games"]` export/import lines); `README.md:511-531` ("Editing from scripts")
- Test: `tests/test_commands.py` (`GamesTest`, `:33`)

**Interfaces:**
- Consumes: B1 `collections.load_collections`; `store.load_cards`, `store.update_card`.
- Produces: `commands.CARD_FIELDS = ("collections", "frontend_collections")` — card-entry list fields written as
  `@<field> <value>` lines, one per value, after the games; part C appends `surprise` / `surprises` handling.

- [ ] **Step 1: Write the failing tests** in `GamesTest`:

```python
    def test_export_and_import_carry_collections_and_frontend_names(self):
        from sync_roms import collections
        collections.save_collection({"id": "favs", "name": "Favs", "games": []})
        cards = self.read("cards.json")
        cards["SD"].update(collections=["favs"], frontend_collections=["Favs"])
        self.write_json("cards.json", cards)
        self.assertEqual(self.run_cmd("games", "export")[1].splitlines(), ["@collections favs", "@frontend_collections Favs"])
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        listing = os.path.join(self.tmp.name, "list.txt")
        with open(listing, "w") as f:
            f.write("@collections favs\n@collections ghost\n@frontend_collections Favs\n@bogus x\n")
        code, _, err = self.run_cmd("games", "import", listing, "-n")
        self.assertEqual((code, self.read("cards.json")["SD"].get("collections")), (0, None))
        code, _, err = self.run_cmd("games", "import", listing)
        self.assertEqual(code, 0)
        self.assertIn("ghost", err)
        self.assertIn("@bogus", err)
        entry = self.read("cards.json")["SD"]
        self.assertEqual((entry["collections"], entry["frontend_collections"]), (["favs"], ["Favs"]))
```

- [ ] **Step 2: Run to verify it fails**

  Run: `python -m unittest discover -s tests -p 'test_commands.py' -v` — Expected: FAIL (export prints nothing; import
  warns `skipping '@collections favs'`).

- [ ] **Step 3: Implement**

  - `games_export`: after the games, for each field in `CARD_FIELDS` with a list value in the card's entry, print
    `@<field> <value>` per value.
  - `games_import`: lines starting with `@` split as `field, _, value = line[1:].partition(" ")`; unknown fields warn
    `skipping {line!r}: unknown card field`; `collections` values not among `load_collections()` ids warn
    `unknown collection {value!r}, skipped`. A field with at least one line replaces the card's value; each one adds a
    `("+", f"{field}: {', '.join(values)}")` change. Saving goes through `finish` with a save function that saves the
    games and then `store.update_card(args.card, **fields)`, so `-n` saves neither.
  - `TOPICS["games"]` and README "Editing from scripts": the `@collections ID` / `@frontend_collections NAME` lines
    and that import replaces those fields when the file has them.

- [ ] **Step 4: Run to verify it passes** — the Step 2 command, then the whole suite
  (`python -m unittest discover -s tests`). Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/commands.py src/sync_roms/cli.py README.md tests/test_commands.py
git commit -m "feat(games): carry a card's collections through games export and import"
```

## Part C: Surprise

**Interface corrections and additions (read before C1):**

- A surprise is `{"system", "bucket", "title", "files"?}`, not just `{"system","bucket","title"}`: a multi-disc game is one
  surprise, `bucket` is its first key (the `.m3u` when storage has one, else disc 1) and `"files"` lists the game's
  OTHER keys (`unit[1:]`, only when non-empty), exactly as collections and sets use it. One expansion,
  `[bucket] + files`, serves both in `card_locked_games`. History entries keep only `bucket` (the first key).
- `save_history(entries, today: datetime.date)`, `recent(history, today: datetime.date, ttl: int) -> set[str]`.
- `run_surprise(card_name, setup, chosen_systems, interactive, dry_run)`: `setup` is `(device or None, layout name)`,
  `chosen_systems` the run's system dicts from `store.load_manifest([card])` (with `"games"`). Returns the card's
  surprises after the step (on a dry run: the saved ones, unchanged; previewed fills are only printed).
- Added: `surprise.enabled(entry: dict) -> bool` (`entry.get("surprise") is not False`),
  `surprise.COLLECTION = "Surprise"`, `surprise.past_keys(bucket: str) -> set[str]` (history keys within the TTL, for the
  `p` filters), `mirroring.storage_reads()` (context manager: `runtime._mirror_root = None` inside, restored after; the
  mirror redirects reads only through `s3.read_root()` at s3.py:40-42), `ui.has_terminal() -> bool` (the check at
  ui.py:194, which `require_terminal` then uses), `cardedit.toggle_surprise(name: str) -> bool` (new state).
- The past-surprises filter key is `p`: `g`/`G`, `j`/`k`, `/`, `?`, `z`, `u`, `o`, `w`, `a`, Tab and Space are
  `filter_list` built-ins (picker.py:389-460), and `s`/`m`/`c` are taken in the game list.

Test command: `python -m unittest discover -s tests -p '<file>' -v` (one file; add `-k <name>` for one test);
whole suite `python -m unittest discover -s tests` (.github/workflows/test.yml:23).

### File Structure

- Create `src/sync_roms/surprise.py`: candidate rules, units, slot allocation, history, the sync step.
- Create `tests/test_surprise.py`: rules, picking, history, `run_surprise` against a folder storage (`StorageDir`).
- Modify `src/sync_roms/store.py`: `card_locked_games` adds surprises.
- Modify `src/sync_roms/mirroring.py`: `storage_reads()`.
- Modify `src/sync_roms/ui.py`: `has_terminal()`.
- Modify `src/sync_roms/cli.py`: `sync_card` runs the step, reloads, refreshes the mirror, warns on capacity, writes the
  Surprise collection.
- Modify `src/sync_roms/cardedit.py`, `src/sync_roms/collectionedit.py` (Part B): `u` toggle, `p` filter.
- Modify `src/sync_roms/commands.py`: `check` validates surprises; `games export/import` carry them.
- Modify `src/sync_roms/data/cards.schema.json`, `README.md`, `CLAUDE.md`.
- Tests also in `tests/test_sync_flow.py`, `tests/test_cardedit.py`, `tests/test_commands.py` (or wherever `check` /
  `games export` are tested now: `grep -ln "check_data\|games_export" tests/`).

### Task 12 (C1): Candidate rules and units

**Files:**
- Create: `src/sync_roms/surprise.py`
- Test: `tests/test_surprise.py`

**Interfaces:**
- Consumes: `m3u.file_groups(keys)` (m3u.py:44, playlist first then discs), `clones.json` shape
  `{"parents": {stem: title}, "clones": {stem: [parent, title]}}` (read with `store.repo_json("clones")`, as
  scrape_plan.py:477 does).
- Produces: `SLOTS = 10`, `RECOMMENDED_SHARE = 2 / 3`, `DEFAULT_TTL_DAYS = 183`, `COLLECTION = "Surprise"`,
  `ENGLISH_REGIONS`, `is_candidate(key, system, family, bios) -> bool`, `units(system, keys, family, bios) -> list[list[str]]`.

- [ ] **Step 1: Write the failing tests** (`unittest.TestCase`, plain asserts)

```python
GBA = {"bucket": "gba", "bios": {"files": ["gba_bios.bin"]}}
IN = ["Super Mario Advance (USA, Europe).zip", "Castlevania - Aria of Sorrow (USA).zip",
      "Golden Sun (Europe) (En,Fr,De).zip", "Sonic Advance (Japan) (En,Ja).zip", "Tetris (World) (Rev 1).zip",
      "Final Fantasy Tactics Advance (USA, Australia).zip", "Pokemon Stadium (Australia).zip",
      "Hockey Night (Canada).zip", "Lemmings (UK).zip", "VitaShell.vpk", "Homebrew Game (2019).zip"]
OUT = ["Mother 3 (Japan).zip", "Rhythm Tengoku (Japan).zip", "Densetsu no Stafy (Japan) (Rev 1).zip",
       "Super Mario Bros. (Europe) (Fr,De).zip", "Star Fox 2 (Japan) (Proto).zip",
       "Pokemon - Ruby Version (USA) (Beta).zip", "Metroid Fusion (USA) (Demo) (Kiosk).zip",
       "Sonic Jam (Japan) (Sample).zip", "Action 52 (USA) (Unl).zip", "Street Fighter II (World) (Pirate).zip",
       "Zelda (USA) (Hack).zip", "Tetris (World) [h1].zip", "Tetris (World) [b2].zip", "[BIOS] Game Boy Advance (World).zip",
       "gba_bios.bin", "Kirby's Adventure (USA) (Virtual Console).zip", "Super Mario Bros. 3 (USA) (Switch Online).zip",
       "Castlevania (USA) (Castlevania Anniversary Collection).zip", "Mega Man 2 (USA) (Capcom Classics Mini Mix).zip",
       "Contra (USA) (Classic Mini).zip"]

def test_full_english_names(self):
    bios = {"gba_bios.bin"}
    self.assertEqual([n for n in IN if not surprise.is_candidate("gba/" + n, GBA, None, bios)], [])
    self.assertEqual([n for n in OUT if surprise.is_candidate("gba/" + n, GBA, None, bios)], [])

def test_arcade_parents_only_and_not_japan(self):
    family = {"parents": {"10yard": "10-Yard Fight (World, set 1)", "armedf": "Armed F (Japan)",
                          "1943j2": "1943 Kai (Japan 900227)"},
              "clones": {"10yardj": ["10yard", "10-Yard Fight (Japan)"]}}
    mame = {"bucket": "mame", "bios": {"files": []}}
    got = {k: surprise.is_candidate(f"mame/{k}.zip", mame, family, set())
           for k in ("10yard", "armedf", "1943j2", "10yardj", "neogeo")}
    self.assertEqual(got, {"10yard": True, "armedf": False, "1943j2": False, "10yardj": False, "neogeo": False})

def test_multi_disc_game_is_one_unit_playlist_first(self):
    psx = {"bucket": "psx", "bios": {"files": []}}
    keys = {"psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd", "psx/FF7 (USA).m3u",
            "psx/Spyro (USA).chd", "psx/Demo Disc (USA) (Demo).chd", "psx/sub/"}
    self.assertEqual(sorted(surprise.units(psx, keys, None, set())),
                     [["psx/FF7 (USA).m3u", "psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd"],
                      ["psx/Spyro (USA).chd"]])
```

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_surprise.py' -v` — Expected: FAIL, `No module named 'sync_roms.surprise'` / ImportError.

- [ ] **Step 3: Implement `is_candidate` and `units` in `src/sync_roms/surprise.py`**

Decisions:
- Work on the file name's stem; tags are the `(...)` and `[...]` groups after the title (`re.findall`).
- Out when the basename is in `bios`, the name contains `[BIOS]`, a `[...]` group starts with `b` or `h`
  (`\[[bh][^\]]*\]`), or any comma part of a `(...)` group starts with one of `NOT_FULL = ("Proto", "Beta", "Demo",
  "Sample", "Kiosk", "Pirate", "Hack", "Unl")`.
- Re-release/compilation tags (any `(...)` group containing one of): `RERELEASE = ("Virtual Console", "Switch Online",
  "Classic Mini", "Mini Mix", "Mega Drive Mini", "Genesis Mini", "Collection", "Anthology", "Archives", "Sega Ages",
  "Sega Channel", "Evercade", "Steam", "GOG", "Retro-Bit", "Limited Run", "e-Reader")`.
- English: a language group is a `(...)` whose comma parts all match `^[A-Z][a-z](-[A-Za-z]+)?$`; with one, English iff a
  part is `En` or starts `En-`. Else the region group is the first `(...)` whose comma parts are all in a full No-Intro
  `REGIONS` set (USA, World, Europe, UK, Australia, Canada, Japan, Korea, Asia, China, Taiwan, Hong Kong, Brazil, France,
  Germany, Spain, Italy, Netherlands, Sweden, Scandinavia, Russia, Latin America, Unknown); English iff it shares a part
  with `ENGLISH_REGIONS = {"USA", "World", "Europe", "UK", "Australia", "Canada"}`. No language and no region group:
  English (untagged/homebrew).
- `family` given (MAME/FBNeo): candidate iff the stem is in `family["parents"]` and no `(...)` group of the parent's title
  has a first comma part whose first word is `Japan`; the No-Intro tag rules are skipped (arcade names have none), BIOS
  rules still apply.
- `units`: drop keys ending `/`; group with `m3u.file_groups(keys)` (dedupe groups by `tuple`), other keys alone; a unit
  is a candidate when `is_candidate(unit[0], ...)` holds.

- [ ] **Step 4: Run** the Step 2 command — Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/surprise.py tests/test_surprise.py
git commit -m "feat(surprise): add the full english game rules for surprise candidates"
```

### Task 13 (C2): Slot allocation and tiers

**Files:**
- Modify: `src/sync_roms/surprise.py`
- Test: `tests/test_surprise.py`

**Interfaces:**
- Consumes: units (`list[list[str]]`) from C1.
- Produces: `pick(pools, kept, need, recommended, recent, others_current, rng) -> list[dict]` — pools
  `{system bucket: [units]}` (already without taken units); returns new surprises
  `{"system", "bucket": unit[0], "title": store.key_title(unit[0]), "files"?: unit[1:]}` (`files` only when non-empty).

- [ ] **Step 1: Write the failing tests**

```python
def pool(system, n):
    return [[f"{system}/G{i} (USA).zip"] for i in range(n)]

def count(picked):
    return collections.Counter(p["system"] for p in picked)

def test_seven_three_split_counts_kept(self):
    pools = {s: pool(s, 20) for s in "abcd"}
    kept = [{"system": "a", "bucket": "a/K1.zip", "title": "K1"}, {"system": "a", "bucket": "a/K2.zip", "title": "K2"},
            {"system": "c", "bucket": "c/K3.zip", "title": "K3"}]
    got = count(surprise.pick(pools, kept, 7, {"a", "b"}, set(), set(), random.Random(1)))
    self.assertEqual(got["a"] + got["b"], 5)
    self.assertEqual(got["c"] + got["d"], 2)
    self.assertEqual(sum(got.values()), 7)

def test_full_ten_is_seven_three_spread_evenly(self):
    pools = {s: pool(s, 20) for s in "abcde"}
    got = count(surprise.pick(pools, [], 10, {"a", "b", "c"}, set(), set(), random.Random(2)))
    self.assertEqual(sorted(got[s] for s in "abc"), [2, 2, 3])
    self.assertEqual(sorted(got[s] for s in "de"), [1, 2])

def test_recommended_system_with_few_candidates_passes_slots_on(self):
    pools = {"a": pool("a", 2), "b": pool("b", 20), "c": pool("c", 20)}
    got = count(surprise.pick(pools, [], 10, {"a"}, set(), set(), random.Random(3)))
    self.assertEqual(got["a"], 2)
    self.assertEqual(got["b"] + got["c"], 8)
    self.assertEqual(sorted((got["b"], got["c"])), [4, 4])

def test_two_systems_both_recommended_split_five_five(self):
    pools = {"a": pool("a", 20), "b": pool("b", 20)}
    got = count(surprise.pick(pools, [], 10, {"a", "b"}, set(), set(), random.Random(4)))
    self.assertEqual(got, {"a": 5, "b": 5})

def test_no_recommended_systems_gives_all_slots_to_the_others(self):
    got = count(surprise.pick({"a": pool("a", 20)}, [], 10, set(), set(), set(), random.Random(5)))
    self.assertEqual(got, {"a": 10})

def test_multi_disc_game_takes_one_slot(self):
    disc = ["p/FF7 (USA).m3u", "p/FF7 (USA) (Disc 1).chd", "p/FF7 (USA) (Disc 2).chd"]
    got = surprise.pick({"p": [disc, ["p/Spyro (USA).chd"]]}, [], 10, set(), set(), set(), random.Random(6))
    self.assertEqual(len(got), 2)
    ff7 = next(x for x in got if x["bucket"] == "p/FF7 (USA).m3u")
    self.assertEqual(ff7, {"system": "p", "bucket": "p/FF7 (USA).m3u", "title": "FF7 (USA)", "files": disc[1:]})
    self.assertNotIn("files", next(x for x in got if x["bucket"] == "p/Spyro (USA).chd"))

def test_best_tier_first(self):
    units = [["a/Fresh.zip"], ["a/Past.zip"], ["a/Other.zip"]]
    for seed in range(20):
        got1 = surprise.pick({"a": units}, [], 1, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
        got2 = surprise.pick({"a": units}, [], 2, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
        got3 = surprise.pick({"a": units}, [], 3, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
        self.assertEqual([x["bucket"] for x in got1], ["a/Fresh.zip"])
        self.assertEqual({x["bucket"] for x in got2}, {"a/Fresh.zip", "a/Past.zip"})
        self.assertEqual(len(got3), 3)

def test_need_zero_picks_nothing(self):
    self.assertEqual(surprise.pick({"a": pool("a", 5)}, [], 0, {"a"}, set(), set(), random.Random(0)), [])

def test_every_system_runs_out_returns_what_there_is(self):
    got = surprise.pick({"a": pool("a", 2), "b": pool("b", 1), "c": []}, [], 10, {"a"}, set(), set(),
                        random.Random(7))
    self.assertEqual(count(got), {"a": 2, "b": 1})
    self.assertEqual(surprise.pick({}, [], 10, set(), set(), set(), random.Random(7)), [])
```

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_surprise.py' -v` — Expected: FAIL, `module 'sync_roms.surprise' has no attribute 'pick'`.

- [ ] **Step 3: Implement `pick` in `src/sync_roms/surprise.py`**

The split and the round robin aren't pinned by the signature, so:

```python
def pick(pools, kept, need, recommended, recent, others_current, rng):
    left = {b: list(u) for b, u in pools.items()}
    groups = {g: [b for b in sorted(left) if (b in recommended) == g] for g in (True, False)}
    for g in groups.values():
        rng.shuffle(g)
    kept_rec = sum(1 for k in kept if k["system"] in recommended)
    want_rec = min(max(round(SLOTS * RECOMMENDED_SHARE) - kept_rec, 0), need)
    out = []

    def tier(unit):
        return 2 if unit[0] in others_current else 1 if unit[0] in recent else 0

    def fill(group, slots):
        """Round robin over the group's systems; a system with nothing left passes its turn on. Returns unused slots."""
        while slots and any(left[b] for b in groups[group]):
            for b in groups[group]:
                if not slots:
                    break
                if left[b]:
                    best = min(map(tier, left[b]))
                    unit = rng.choice([u for u in left[b] if tier(u) == best])
                    left[b].remove(unit)
                    out.append(surprise_of(b, unit))
                    slots -= 1
        return slots

    rest = fill(False, need - want_rec + fill(True, want_rec))
    fill(True, rest)
    return out
```

`surprise_of(bucket, unit)` builds the dict described in Interfaces.

- [ ] **Step 4: Run** the Step 2 command — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/surprise.py tests/test_surprise.py
git commit -m "feat(surprise): pick surprises seven from recommended systems, three from the rest"
```

### Task 14 (C3): History, settings, card state and check

**Files:**
- Modify: `src/sync_roms/surprise.py`
- Modify: `src/sync_roms/store.py` (`card_locked_games`, added by B)
- Modify: `src/sync_roms/usersettings.py:22-23` (docstring lists `surprise_ttl_days`)
- Modify: `src/sync_roms/commands.py:456-575` (`check_data`), `:588-597` (`check_cmd` success text); `src/sync_roms/cli.py:31`
  (`SUBCOMMANDS["check"]`)
- Modify: `src/sync_roms/data/cards.schema.json:6-16`
- Test: `tests/test_surprise.py`, the `check` tests file

**Interfaces:**
- Consumes: `store.card_locked_games(entry, collections_by_id)` from B; `store.write_json`, `store.PRETTY`.
- Produces: `ttl_days() -> int`, `load_history() -> list[dict]`, `save_history(entries, today) -> None`,
  `recent(history, today, ttl) -> set[str]`, `past_keys(bucket) -> set[str]`, `enabled(entry) -> bool`;
  `card_locked_games` returns surprises with `"from": "🎁 Surprise"` when `enabled(entry)`.

- [ ] **Step 1: Write the failing tests** (`class History(helpers.DataDir)`, `class Locked(unittest.TestCase)`,
  `class Mirror(StorageCase)`)

At the top of `tests/test_surprise.py` (after the imports: add `contextlib`, `json`, `os`, `mock`, and
`from sync_roms import cardedit, mirroring, picker, runtime, store, surprise`), the storage base the C3 mirror test and
C4's `Step` build on. `helpers.StorageDir` gives `self.tmp`, `self.root` (made), `self.data` (not made: `store.data_dir`
returns it) and `put(key)`; `isolate` makes the run hermetic:

```python
class StorageCase(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        os.makedirs(self.data)

    def write_cards(self, cards):
        store.write_cards(cards)

    def read_cards(self):
        with open(os.path.join(self.data, "cards.json")) as f:
            return json.load(f)
```

C4 adds `card`, `chosen`, `surprise`, `patched` and `fail_call` to it.


```python
def test_save_prunes_past_the_ttl_and_recent_reads_within_it(self):
    today = datetime.date(2026, 11, 11)
    old = {"system": "gba", "bucket": "gba/Old.zip", "title": "Old", "card": "SD", "date": "2026-05-01"}
    new = {"system": "gba", "bucket": "gba/New.zip", "title": "New", "card": "SD", "date": "2026-10-01"}
    surprise.save_history([old, new], today)
    self.assertEqual(self.read("surprises.json"), [new])
    self.assertEqual(surprise.recent([old, new], today, 183), {"gba/New.zip"})

def test_ttl_comes_from_settings_default_183(self):
    self.assertEqual(surprise.ttl_days(), 183)
    self.write_json("settings.json", {"surprise_ttl_days": 30})
    self.assertEqual(surprise.ttl_days(), 30)

def test_unreadable_history_is_empty(self):
    with open(self.path("surprises.json"), "w") as f:
        f.write("{nope")
    self.assertEqual(surprise.load_history(), [])

def test_card_locked_games_adds_surprises_only_when_on(self):
    s = {"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}
    disc = {"system": "psx", "bucket": "psx/F (USA).m3u", "title": "F (USA)",
            "files": ["psx/F (USA) (Disc 1).chd", "psx/F (USA) (Disc 2).chd"]}
    got = store.card_locked_games({"surprises": [s, disc]}, {})
    self.assertEqual([g["bucket"] for g in got["gba"]], ["gba/A (USA).zip"])
    self.assertEqual(got["gba"][0]["from"], "🎁 Surprise")
    self.assertEqual([g["bucket"] for g in got["psx"]], [disc["bucket"]] + disc["files"])
    self.assertEqual(store.card_locked_games({"surprise": False, "surprises": [s]}, {}), {})

def test_mirror_wanted_includes_current_surprises(self):  # in Mirror(StorageCase)
    self.put("gba/A (USA).zip")
    self.write_cards({"SD": {"device": "full", "layout": "esde",
                             "surprises": [{"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}]}})
    self.assertIn("gba/A (USA).zip", mirroring.mirror_wanted(store.load_manifest(store.all_card_names())))
```

`check` tests (DataDir, `commands.check_data()`):

```python
def test_check_flags_bad_surprise_data(self):
    self.write_json("cards.json", {"SD": {"surprise": "yes", "surprises": [{"system": "gba"}]}})
    self.write_json("surprises.json", [{"system": "nope", "bucket": "x", "title": "t", "card": "SD", "date": "soon"}])
    problems = commands.check_data()
    self.assertIn("cards.json: SD: 'surprise' must be true or false", problems)
    self.assertIn("cards.json: SD: surprises: each must have system, bucket and title", problems)
    self.assertIn("surprises.json: unknown system 'nope'", problems)  # one entry: both of its problems are reported
    self.assertIn("surprises.json: 'soon' isn't an ISO date", problems)
```

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_surprise.py' -v` and the check tests file — Expected: FAIL (`ttl_days` missing, no 🎁 rows, no new problems).

- [ ] **Step 3: Implement**

- `surprise.py`: history path `os.path.join(store.data_dir(), "surprises.json")`; `load_history` returns `[]` for a
  missing/invalid file or a non-list (warn once via `ui.warn` on invalid JSON, never overwrite it: `save_history` skips
  writing and warns when the file exists but doesn't parse, like `store.write_cards` does at store.py:404). Dates via
  `datetime.date.fromisoformat`; entries with a bad date are dropped on write. `save_history` writes with
  `store.write_json(path, kept, **store.PRETTY)`. `past_keys(bucket)` = `recent(load_history(), date.today(),
  ttl_days())` limited to keys under `bucket + "/"`.
- `card_locked_games`: after B's collection games, when `surprise.enabled(entry)`, add each well-formed surprise
  (`system`, `bucket` strings) as games for every key in `[bucket] + files` (the same expansion as B's collection
  games), each
  `{"title", "bucket", "from": "🎁 Surprise"}`, deduplicated by key with B's collection games (collection first).
  Import `surprise` lazily inside the function if a cycle appears (`surprise` imports `store`).
- `check_data`: per card, `surprise` must be a bool when present; `surprises` a list of objects with string `system`
  (known system), `bucket` (under `system/`) and `title` — exact messages as in the test; add surprise buckets to
  `wanted` so `--bucket-keys` checks them. Load `surprises.json` with the existing `load()`: must be a list; each entry an
  object with known `system`, `bucket` under it, string `title` and `card`, `date` parsing with
  `datetime.date.fromisoformat` — messages `surprises.json: must be a list`, `surprises.json: unknown system {s!r}`,
  `surprises.json: {date!r} isn't an ISO date`, `surprises.json: entry needs system, bucket, title, card and date`.
  Each entry is checked in full: no `continue` after its first problem, so the test's one entry reports both
  "unknown system 'nope'" and "'soon' isn't an ISO date" (only the "entry needs ..." shape problem skips the rest of
  that entry, since its fields can't be read).
  `check_cmd`'s success line keeps B1's wording with `surprises.json` added: "✅ cards.json, surprises.json,
  device-systems.json, the sets and your collections look fine"; `cli.SUBCOMMANDS["check"]` summary to match:
  `("", "validate cards.json, surprises.json, the device overlay, the sets and your collections")`.
- `cards.schema.json`: `"surprise": {"type": "boolean", "description": "false turns Surprise off (absent: on)"}`,
  `"surprises": {"type": "array", "items": {"type": "object", "required": ["system", "bucket", "title"],
  "properties": {"system": {"type": "string"}, "bucket": {"type": "string"}, "title": {"type": "string"},
  "files": {"type": "array", "items": {"type": "string"}, "description": "the game's other files"}}}}`.

- [ ] **Step 4: Run** the Step 2 commands — Expected: PASS; then the whole suite — Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/surprise.py src/sync_roms/store.py src/sync_roms/usersettings.py src/sync_roms/commands.py src/sync_roms/cli.py src/sync_roms/data/cards.schema.json tests/
git commit -m "feat(surprise): keep surprise history and sync a card's surprises"
```

### Task 15 (C4): The sync step `run_surprise`

**Files:**
- Modify: `src/sync_roms/surprise.py`
- Modify: `src/sync_roms/mirroring.py` (add `storage_reads` above `use_mirror`, ~line 100)
- Test: `tests/test_surprise.py` (`class Step(helpers.StorageDir)`)

**Interfaces:**
- Consumes: C1-C3; `store.load_cards`, `store.update_card` (store.py:393), `store.recommended_systems` (store.py:115),
  `s3.list_folders` (s3.py:80), `s3.list_sizes(prefix, sizes=False)` (s3.py:73), `picker.filter_list(..., multi=True,
  initial=...)` (picker.py:227), `cardedit.edit_card(name, setup)` (cardedit.py:244).
- Produces: `run_surprise(card_name, setup, chosen_systems, interactive, dry_run, rng=None, today=None) -> list[dict]`
  (`rng`/`today` are test seams, default `random.Random()` / `date.today()`); `mirroring.storage_reads()`.

- [ ] **Step 1: Write the failing tests**

Helpers, added to C3's `StorageCase` (exact definitions; the tests below call them this way), and the test class:

```python
    # in StorageCase
    def card(self, **entry):
        self.write_cards({"SD": {"device": "full", "layout": "esde", **entry}})

    def chosen(self):
        return [s for s in store.load_manifest(["SD"])["systems"] if s["bucket"] in ("gba", "gb")]

    def surprise(self, system, i):
        ext = "gb" if system == "gb" else "zip"
        return {"system": system, "bucket": f"{system}/G{i} (USA).{ext}", "title": f"G{i} (USA)"}

    def fail_call(self, *a, **k):
        raise AssertionError(f"unexpected call {a!r} {k!r}")

    @contextlib.contextmanager
    def patched(self, filter_list=None, edit_card=None):
        """picker.filter_list and cardedit.edit_card replaced; one left out does nothing and returns None."""
        noop = lambda *a, **k: None  # noqa: E731
        with mock.patch.object(picker, "filter_list", filter_list or noop), \
                mock.patch.object(cardedit, "edit_card", edit_card or noop):
            yield


class Step(StorageCase):
    def setUp(self):
        super().setUp()
        for i in range(15):
            self.put(f"gba/G{i} (USA).zip")
            self.put(f"gb/G{i} (USA).gb")
        self.card()

    def run_step(self, interactive, dry_run, seed):
        """run_surprise on the dry-run tests, with its printed lines."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), interactive, dry_run, rng=random.Random(seed))
        return got, out.getvalue()
```

(`io` joins the file's imports; `random` is there since C2.)

```python
def test_interactive_asks_which_to_replace_then_opens_the_editor(self):
    current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
    self.card(surprises=current)
    lists, edits = [], []
    with self.patched(filter_list=lambda title, labels, **kw: lists.append((title, labels, kw)) or [True] + [False] * 9,
                      edit_card=lambda name, setup=None: edits.append(name)):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(1))
    title, labels, kw = lists[0]
    self.assertEqual(title, "Pick the surprises to replace")
    self.assertEqual(kw["initial"], [False] * 10)
    self.assertEqual(len(got), 10)
    self.assertNotIn(current[0], got)
    self.assertTrue(all(c in got for c in current[1:]))
    self.assertEqual(store.load_cards()["SD"]["surprises"], got)
    self.assertEqual([h["bucket"] for h in surprise.load_history()], [g["bucket"] for g in got if g not in current])
    self.assertEqual(edits, ["SD"])

def test_surprises_outside_the_run_are_dropped(self):
    self.card(surprises=[self.surprise("gba", 0), self.surprise("psx", 0)])
    with self.patched(filter_list=lambda t, labels, **kw: [False] * len(labels)):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(2))
    self.assertNotIn("psx", {g["system"] for g in got})
    self.assertIn(self.surprise("gba", 0), got)

def test_dry_run_keeps_every_surprise_and_only_previews_the_empty_slots(self):
    self.card(surprises=[self.surprise("gba", 0)])
    before = self.read_cards()
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got, out = self.run_step(True, True, 3)
    self.assertEqual(got, [self.surprise("gba", 0)])  # the saved ones; the 9 fills are only printed
    self.assertIn("🎁 would ask which surprises to replace", out)
    self.assertIn("9 new pick(s)", out)
    self.assertEqual(self.read_cards(), before)
    self.assertFalse(os.path.exists(os.path.join(self.data, "surprises.json")))

def test_unattended_dry_run_says_it_would_replace_them_all(self):
    current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
    self.card(surprises=current)
    before = self.read_cards()
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got, out = self.run_step(False, True, 3)
    self.assertEqual(got, current)
    self.assertIn("🎁 would replace all 10 surprises", out)
    self.assertNotIn("new pick", out)  # no empty slot to preview
    self.assertEqual(self.read_cards(), before)
    self.assertFalse(os.path.exists(os.path.join(self.data, "surprises.json")))

def test_unattended_replaces_all_ten_and_saves(self):
    current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
    self.card(surprises=current)
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(4))
    self.assertEqual(len(got), 10)
    self.assertFalse(any(c in got for c in current))
    self.assertEqual(store.load_cards()["SD"]["surprises"], got)
    self.assertEqual(len(surprise.load_history()), 10)

def test_card_selection_and_other_cards_current_are_respected(self):
    picks = {"gba": [{"bucket": f"gba/G{i} (USA).zip"} for i in range(14)]}  # one GBA game left unpicked
    self.card(games=picks)
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(5))
    self.assertEqual([g["bucket"] for g in got if g["system"] == "gba"], ["gba/G14 (USA).zip"])

def test_full_systems_are_left_out_of_the_pools(self):
    self.card(games={"gb": {"full_system": True}})
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(7))
    self.assertEqual(len(got), 10)
    self.assertEqual({g["system"] for g in got}, {"gba"})

def test_off_clears_surprises_keeps_history_and_picks_nothing(self):
    self.card(surprise=False, surprises=[self.surprise("gba", 0)])
    surprise.save_history([{**self.surprise("gba", 0), "card": "SD", "date": "2026-11-01"}], datetime.date(2026, 11, 11))
    with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        self.assertEqual(surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False), [])
    self.assertNotIn("surprises", store.load_cards()["SD"])
    self.assertEqual(len(surprise.load_history()), 1)

def test_candidates_come_from_storage_not_the_mirror(self):
    mirror = os.path.join(self.tmp.name, "mirror")  # holds nothing
    os.makedirs(mirror)
    with mock.patch.object(runtime, "_mirror_root", mirror), self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(6))
    self.assertEqual(len(got), 10)
    self.assertEqual(runtime._mirror_root, mirror)
```


- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_surprise.py' -k Step -v` — Expected: FAIL, no `run_surprise`.

- [ ] **Step 3: Implement**

`mirroring.storage_reads()`: `contextlib.contextmanager`; saves `runtime._mirror_root`, sets `None`, restores in `finally`.

`run_surprise` decisions:
- `entry` = the card's saved entry. Off (`not enabled(entry)`): when `entry.get("surprises")` and not `dry_run`,
  rewrite the entry without `surprises` (`store.load_cards()` → pop → `store.write_cards`); return `[]`. No history change.
- `run_ids = {s["bucket"] for s in chosen_systems}`; `current` = saved surprises whose `system` is in `run_ids`.
- Replace (not a dry run): `interactive` and `current` → `picker.filter_list("Pick the surprises to replace",
  [f"{x['title']}  ({system name})" for x in current], multi=True, initial=[False] * len(current))`; `None` (Esc) means
  replace none. Unattended: replace all of `current`. `kept` = the rest.
- Dry run never changes surprises: `kept = current` (nothing replaced), and when `current` is non-empty print
  `🎁 would ask which surprises to replace` (interactive) or `🎁 would replace all {len(current)} surprises`
  (unattended). Only the empty slots (`SLOTS - len(current)`) are picked, as a printed preview.
- Pool: under `mirroring.storage_reads()`: `folders = s3.list_folders()`, wrapped in `except (*s3.ERRORS, SystemExit)`:
  warn once (`ui.warn(f"Couldn't list storage for surprises: {e}")`) and treat it as no folders known, so there is no
  pool. Then for each chosen system with `s["bucket"] in folders` and not `s.get("full_system")` (a full system
  syncs everything already, so it is left out of the pools), `keys = s3.list_sizes(f"{bucket}/", sizes=False)`;
  listing errors (`s3.ERRORS`) skip that system with `ui.warn`.
- `taken` = every key in the chosen systems' `"games"` (the card's direct picks, sets and locked games, which includes
  every current surprise) plus kept surprises' keys; a unit is dropped when it shares a key with `taken`.
- `family` = `store.repo_json("clones").get(bucket)`; `bios` = `set(s["bios"]["files"])`.
- `recommended` = `store.recommended_systems(device, store.repo_json("systems"))` when `setup[0]`, else `set()`.
- `others_current` = first keys of surprises on every other card where `enabled(other entry)`.
- `new = pick(pools, kept, SLOTS - len(kept), recommended, recent(load_history(), today, ttl_days()), others_current, rng)`;
  result `kept + new`.
- Print `🎁 Surprise: N new pick(s)` and each new title + system dim (nothing when N is 0); on a dry run add
  "(dry run: not saved)" and return `current` (the saved surprises: what this dry run's download plan and frontend
  description use; the previewed fills are in neither).
- Save: `store.update_card(card, surprises=result)`; `save_history(load_history() + [{system, bucket, title, card, date:
  today.isoformat()} for new], today)`.
- `interactive and not dry_run`: `cardedit.edit_card(card_name, setup)` (import inside the function: `cardedit` imports
  much of the package).

- [ ] **Step 4: Run** the Step 2 command — Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/surprise.py src/sync_roms/mirroring.py tests/test_surprise.py
git commit -m "feat(surprise): pick a card's surprises during sync"
```

### Task 16 (C5): Wire Surprise into `sync_card`

**Files:**
- Modify: `src/sync_roms/ui.py:192-195` (`has_terminal`, used by `require_terminal`)
- Modify: `src/sync_roms/cli.py:11` (module-level imports gain `budget`, `surprise`), `:670-990` — after `chosen = [systems[i] for i in chosen]` (:801); listing block of the
  picker loop (:751-758) pulled into a local `relist()`; capacity warning before `if args.dry_run:` (:903); the
  Surprise collection in Part B's `plan_collections` block.
- Test: `tests/test_sync_flow.py` (`SyncFlowTest.run_sync`, :141-180); `tests/test_cli_sync.py` (`SyncSmokeTest.run_sync`, :34-53)

**Interfaces:**
- Consumes: `surprise.run_surprise`, `surprise.enabled`, `surprise.COLLECTION`, `mirroring.storage_reads`,
  `mirroring.refresh_mirror(root, dry_run)` (mirroring.py:41), `budget.card_usage`, `budget.card_capacity`
  (budget.py:89/99), `cardedit.card_entry`, `cardedit.size_text`, B's `frontend.plan_collections` /
  `frontend.collection_path`.
- Produces: `ui.has_terminal() -> bool`.

- [ ] **Step 1: Write the failing tests** — give `run_sync` a `prepare=None` callable (run on `card_dir` before the
  sync) and make its unused `extra` param a tuple of `(target, name, value)` patches, entered after the defaults so
  they override them. Both existing sync harnesses patch `cli.surprise.run_surprise` to `lambda *a, **k: []` by
  default, so no old test picks surprises from (or lists) storage: `SyncFlowTest.run_sync` in
  `tests/test_sync_flow.py` (:141-173, an `st.enter_context(mock.patch.object(cli.surprise, "run_surprise", ...))`
  next to the `scrape_plan` patches) and `SyncSmokeTest.run_sync` in `tests/test_cli_sync.py` (:34-53,
  `(cli.surprise, {"run_surprise": lambda *a, **k: []})` in the default tuple, before `+ tuple(patches)`). Record
  `run_surprise` calls:

```python
def surprise_calls(self, result=(), **kw):
    calls = []
    fake = lambda card, setup, chosen, interactive, dry_run: calls.append((interactive, dry_run, [s["bucket"] for s in chosen])) or list(result)
    return calls, self.run_sync(extra=((cli.surprise, "run_surprise", fake),), **kw)

def test_yes_runs_surprise_unattended(self):
    calls, _ = self.surprise_calls(yes=True)
    self.assertEqual(calls, [(False, False, ["gba"])])

def test_dry_run_describes_the_saved_surprises_and_saves_nothing(self):
    saved = [{"system": "gba", "bucket": "gba/Game.zip", "title": "Game"}]
    calls, (code, out, updates, *_) = self.surprise_calls(result=saved, cards={"surprises": saved}, yes=True, dry_run=True)
    self.assertEqual(calls, [(False, True, ["gba"])])
    self.assertEqual(code, 0)
    self.assertIn("custom-Surprise.cfg (1 game(s))", out)
    self.assertFalse([u for u in updates if "surprises" in u or "frontend_collections" in u])

def test_terminal_run_is_interactive(self):
    with mock.patch.object(ui, "has_terminal", return_value=True):
        calls, _ = self.surprise_calls(cards={"systems": ["gba"]}, yes=False)
    self.assertEqual(calls[0][:2], (True, False))

def test_over_capacity_warns_and_goes_on(self):
    big = budget.Usage(2 * 10 ** 9, 1, False)
    warned = []
    code, *_ = self.run_sync(cards={"size": "1 GB"}, extra=(
        (cli.surprise, "run_surprise", lambda *a: []), (cli.budget, "card_usage", lambda *a, **k: big),
        (ui, "warn", warned.append)))
    self.assertEqual(code, 0)
    self.assertIn(f"{self.card}'s picks take 2 GB of its 1 GB: 1 GB over", warned)

def test_mirror_is_refreshed_again_after_the_surprise_step(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    root = tmp.name
    open(os.path.join(root, runtime.MIRROR_MARKER), "w").close()
    seen = []
    code, *_ = self.run_sync(settings={"mirror": root}, extra=(
        (cli.surprise, "run_surprise", lambda *a: []),
        (mirroring, "refresh_mirror", lambda r, dry_run=False: seen.append((r, runtime._mirror_root)) or 0)))
    self.assertEqual(seen, [(root, None), (root, None)])  # use_mirror, then after the step: both read storage
```

(`run_sync` gains `settings=None` passed to the `load_settings` patch, exposes the card's name as `self.card`, and
patches `runtime._mirror_root` to `None` for the run so `use_mirror` setting it doesn't leak into other tests.)

```python
def test_surprise_off_removes_its_collection_file(self):
    def prepare(card_dir):
        self.cfg = frontend.collection_path("esde", card_dir, "Surprise")
        os.makedirs(os.path.dirname(self.cfg), exist_ok=True)
        open(self.cfg, "w").close()
    code, _, updates, *_ = self.run_sync(cards={"surprise": False, "frontend_collections": ["Surprise"]}, prepare=prepare)
    self.assertEqual(code, 0)
    self.assertFalse(os.path.exists(self.cfg))
    last = [u for u in updates if "frontend_collections" in u][-1]
    self.assertNotIn("Surprise", last["frontend_collections"])
```

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_sync_flow.py' -v` — Expected: the new tests FAIL
  (`cli` has no `surprise`, no warning, file still there); old tests PASS.

- [ ] **Step 3: Implement in `sync_card`**

- `cli.py` imports `surprise` and `budget` at module level (tests patch `cli.surprise` / `cli.budget`). Check the
  chain for cycles first: `budget` → `commands` → `setedit` → `edit` (`edit` imports `cardedit` only inside a
  function, `commands` imports `cli` only inside functions), and `surprise` → `store`/`m3u`/`picker`/`mirroring`
  (`cardedit` inside `run_surprise`). Run `python -c "import sync_roms.cli"`; if a cycle appears, fall back to a
  function-local import in `sync_card` and patch `sync_roms.surprise.run_surprise` / `sync_roms.budget.card_usage`
  in the tests instead.
- `ui.has_terminal()`: `sys.stdin.isatty() and (_real_stdout or sys.stdout).isatty()`; `require_terminal` uses it.
- After :801: `interactive = not (ui.ASSUME_YES or args.json) and ui.has_terminal()`; `surprises =
  surprise.run_surprise(card, (device, layout_name), chosen, interactive, args.dry_run)`.
- Not a dry run: when `runtime._mirror_root` is set, `with mirroring.storage_reads(): mirroring.refresh_mirror(root)`
  (warn on `s3.ERRORS`/`SystemExit` as `use_mirror` does, mirroring.py:105-109); then `systems = reload_systems()`,
  drop the `listings`/`size_cache` entries of systems whose `store.listed(s)` changed, run `relist()` (the
  `todo`/`listings`/`avail`/`discs` lines of :752-758, now shared with the loop), and `chosen = [s for s in systems if
  s["bucket"] in chosen ids]`. The editor may have changed `saved` too: re-read it (`store.load_cards().get(card)`).
- Before :903: when `surprise.enabled(saved or {})`, `capacity = budget.card_capacity(saved or {})`; if set and
  `budget.card_usage(cardedit.card_entry(card, (device, layout_name)), systems).bytes > capacity`:
  `ui.warn(f"{card}'s picks take {size_text(used)} of its {saved['size']}: {size_text(used - capacity)} over")`.
- Part B's collections block: when `surprise.enabled(saved)` and `surprises`, add
  `{"name": surprise.COLLECTION, "games": surprises}` to the collections passed to B's
  `frontend.wanted_collections` (so its lines are built exactly like collection games'); `owned` handling (B) then deletes and unlists `custom-Surprise.cfg` when Surprise is off or empty.
  In a dry run B's block only describes; Surprise follows it. On a dry run `surprises` is the saved list
  (`run_surprise` changes nothing then), so the frontend description and the download plan (from `chosen`, whose
  games `load_manifest` built with the saved surprises through `card_locked_games`) agree; the previewed fills are in
  neither.

- [ ] **Step 4: Run** the Step 2 command, then the whole suite — Expected: PASS / OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/ui.py src/sync_roms/cli.py tests/test_sync_flow.py tests/test_cli_sync.py
git commit -m "feat(sync): pick surprises after the systems are chosen"
```

### Task 17 (C6): Editor keys: `u` toggles Surprise, `p` finds past surprises

**Files:**
- Modify: `src/sync_roms/cardedit.py:10-18` (keys, hints), `:244-315` (`edit_card`), `:363-546` (`edit_system`: `filt`,
  `where` :517-518, hotkeys :527, branches :535-545)
- Modify: `src/sync_roms/collectionedit.py` (Part B: the `filter_list` that lists one system's games to add)
- Test: `tests/test_cardedit.py` (`Flow`, `Script`, `returns`, `toggle` at :85-150)

**Interfaces:**
- Consumes: `surprise.enabled`, `surprise.past_keys(bucket)`.
- Produces: `SURPRISE_KEY = "u"`, `PAST_SURPRISE_KEY = "p"`, `toggle_surprise(name) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_u_toggles_surprise_and_the_title_shows_it(self):
    self.card(size="1 GB")
    calls = self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns((cardedit.SURPRISE_KEY, 0)), returns(None))
    self.assertIn("🎁 Surprise on", calls[0][0])
    self.assertIn("🎁 Surprise off", calls[1][0])
    self.assertIn("🎁 Surprise on", calls[2][0])
    self.assertNotIn("surprise", self.read("cards.json")["c"])

def test_u_off_saves_false(self):
    self.card(size="1 GB")
    self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(None))
    self.assertIs(self.read("cards.json")["c"]["surprise"], False)

def test_p_narrows_the_game_list_to_past_surprises(self):
    self.card()
    with mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
        _, calls = self.run_system(returns((cardedit.PAST_SURPRISE_KEY, 0)), returns((cardedit.CLEAR_KEY, 0)),
                                   lambda labels, kw: [False] * len(labels))
    self.assertEqual(calls[1][1], ["Ruby.zip"])
    self.assertIn("🎁 past surprises only (c shows all)", calls[1][0])
    self.assertEqual(len(calls[2][1]), len(calls[0][1]))

def test_surprise_rows_are_locked_in_the_game_list(self):
    self.card(surprises=[{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}])
    _, calls = self.run_system(returns(None))
    labels, kw = calls[0][1], calls[0][2]
    i = labels.index("Zelda.zip")
    self.assertTrue(kw["locked"][i])
    self.assertIn("🎁 Surprise", str(kw["extras"][i]) + str(kw.get("locked_note")))
```

Plus one test in the collection editor's test file: `p` there narrows its add-games list the same way (same shape as
`test_p_narrows_the_game_list_to_past_surprises`, against B's function).

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_cardedit.py' -v` — Expected: new tests FAIL
  (`SURPRISE_KEY` missing). The locked-row test may already pass once C3 is in (B's locked rows); keep it as a guard.

- [ ] **Step 3: Implement**

- `toggle_surprise(name)`: load cards, pop `"surprise"` when it is `False`, else set it `False`; `store.write_cards`;
  return the new state.
- `edit_card`: title `f"💳 {name} — its systems (⭐ for the device) · 🎁 Surprise {'on' if on else 'off'}"` from
  `surprise.enabled(card)`; `SURPRISE_KEY` in `hotkeys`, handled in the tuple branch (not `on_hotkey`, so the list
  reopens with the new title at the same `pos`). `LIST_HINT = "Enter games · f full · l collections · u surprise · D
  clear all · Esc back"` (74 cells).
- `edit_system`: `PAST_SURPRISE_KEY` in `hotkeys`; it sets `filt = ("🎁 past surprises", surprise.past_keys(bucket))`
  and the `where` part for that filter reads `🎁 past surprises only` (a set filter keeps `📦 {name} only`); `c` clears
  as now. `GAMES_HINT = "Space toggle · Enter done · / search · s set · m meta · c clear · p past"` (72 cells; both
  hints stay within the 80 cells `tests/test_editor_data.py` `Hints` checks). With no past surprises on the system, `edit.note(ui.yellow("ℹ️  No
  past surprises on {system name}."))` and no filter.
- `collectionedit.py`: the same key, filter and note on its system games list.

- [ ] **Step 4: Run** the Step 2 command, the collection editor's tests and `-p 'test_editor_data.py'` (`Hints`) — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cardedit.py src/sync_roms/collectionedit.py tests/
git commit -m "feat(edit): toggle surprise per card and filter games to past surprises"
```

### Task 18 (C7): Export/import and docs

**Files:**
- Modify: `src/sync_roms/commands.py:261-289` (`games_export`, `games_import`; B8's `CARD_FIELDS`)
- Modify: `src/sync_roms/cli.py:69-70` (games help lines)
- Modify: `README.md:486` (system list keys), the game list keys paragraph, `:511-531` (Editing from scripts), `:564`
  (A card's games in cards.json), a new `### Surprise` section after `### Full sets` (:550), the settings mention of
  `surprise_ttl_days`
- Modify: `CLAUDE.md:60` (data-files table `~/.sync-roms/` row)
- Test: `tests/test_commands.py` (`GamesTest`, next to B8's test; `CardCmd.run_cmd` adds `--card SD` itself)

**Interfaces:**
- Consumes: B8 `commands.CARD_FIELDS` and its `@field value` lines; `surprise.enabled`; `store.update_card`,
  `store.key_title`; `m3u.file_groups`; `s3.list_sizes`.
- Produces: `CARD_FIELDS = ("collections", "frontend_collections", "surprise", "surprises")`. Export lines
  `@surprise false` (only when off) and `@surprises <bucket key>` (one per surprise, its first key; `files` are not
  written). Import rebuilds each surprise's `files` from `m3u.file_groups` over its system's storage listing (chosen
  over putting every key on the line: the line stays one key, like every other export line).

- [ ] **Step 1: Write the failing tests** (in `GamesTest`)

```python
    def test_export_carries_surprise_state(self):
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprise": False, "surprises": [
            {"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}], "games": {"gba": [{"bucket": "gba/B.zip"}]}}})
        code, out, _ = self.run_cmd("games", "export")
        self.assertEqual(out.splitlines(), ["gba/B.zip", "@surprise false", "@surprises gba/A (USA).zip"])

    def test_import_reads_surprise_lines(self):
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write("gba/B.zip\n@surprise false\n@surprises gba/A (USA).zip\n@surprises nope/X.zip\n@surprise maybe\n")
        with mock.patch.object(commands.s3, "list_sizes", lambda prefix, sizes=True: {}):
            code, _, err = self.run_cmd("games", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("nope/X.zip", err)
        self.assertIn("@surprise maybe", err)
        entry = self.read("cards.json")["SD"]
        self.assertIs(entry["surprise"], False)
        self.assertEqual(entry["surprises"], [{"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}])
        self.assertEqual(entry["games"]["gba"][0]["bucket"], "gba/B.zip")

    def test_multi_disc_surprise_round_trips(self):
        ff7 = {"system": "psx", "bucket": "psx/FF7 (USA).m3u", "title": "FF7 (USA)",
               "files": ["psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd"]}
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprises": [ff7]}})
        out = self.run_cmd("games", "export")[1]
        self.assertEqual(out.splitlines(), ["@surprises psx/FF7 (USA).m3u"])
        path = self.path("list.txt")
        with open(path, "w") as f:
            f.write(out)
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde"}})
        listing = dict.fromkeys([ff7["bucket"], *ff7["files"], "psx/Spyro (USA).chd"], 1)
        with mock.patch.object(commands.s3, "list_sizes", lambda prefix, sizes=True: listing if prefix == "psx/" else {}):
            self.assertEqual(self.run_cmd("games", "import", path)[0], 0)
        self.assertEqual(self.read("cards.json")["SD"]["surprises"], [ff7])
```

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_commands.py' -v` — Expected: FAIL (no `@surprise`
  lines in the export; import warns `skipping '@surprise false': unknown card field`).

- [ ] **Step 3: Implement** (on B8's `@field value` handling; no separate syntax or parser)

- `CARD_FIELDS` gains `"surprise"` and `"surprises"`. Export, after B8's list fields: `@surprise false` when
  `not surprise.enabled(entry)` (nothing when on), then `@surprises <s["bucket"]>` per saved surprise.
- Import, in B8's `@` branch: `@surprise false` → `surprise=False`; `@surprise true` → the key is dropped (saved by
  popping it from the loaded cards and `store.write_cards`, as `toggle_surprise` does); any other value warns
  `skipping {line!r}: expected @surprise true or false`. `@surprises KEY`: the part before `/` must be a known system
  (`system_ids()`) with a file name after it, else warn `skipping {line!r}: expected @surprises SYSTEM/file`. For each
  system with accepted keys, list storage once (`s3.list_sizes(f"{system}/", sizes=False)`; on
  `(*s3.ERRORS, SystemExit)` warn once and import without `files`); `group = m3u.file_groups(listing).get(key)`; the
  surprise is `{"system", "bucket": key, "title": store.key_title(key)}` plus `"files": [k for k in group if k !=
  key]` when that is non-empty (the game's other keys, as everywhere). Changes `("+", "@surprise false")` /
  `("+", f"@surprises {key}")`; as for B8's fields, at least one `@surprises` line replaces the saved list, and the
  save passed to `finish` writes them with `store.update_card(card, surprise=False?, surprises=[...])`, so `-n`
  saves nothing.
- README: Surprise section (on by default, `u` in the system list, 10 picks 7/3, the replace prompt and editor during
  sync, unattended/dry-run behaviour, history in `surprises.json` with `surprise_ttl_days` default 183, `p` filter,
  🎁 rows, the ES-DE/Knulli "Surprise" collection and its reserved name, mirror note); key lists gain `u` and `p`;
  export format lines `@surprise false` / `@surprises SYSTEM/file` (and `TOPICS["games"]` likewise).
- CLAUDE.md data-files row: `cards.json` per card also holds `surprise` (false = off) and `surprises`
  (`[{"system","bucket","title","files"?}]`); add `surprises.json` (history of picks: system, bucket, title, card, ISO
  date; pruned past `surprise_ttl_days`, default 183, on write).

- [ ] **Step 4: Run** the tests file, then the whole suite (`tests/test_readme.py` checks the options table) — Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/commands.py src/sync_roms/cli.py README.md CLAUDE.md tests/
git commit -m "docs(surprise): document surprise and carry it through games export and import"
```
