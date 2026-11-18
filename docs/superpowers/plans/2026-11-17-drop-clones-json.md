# Drop clones.json Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Remove `src/sync_roms/data/clones.json` (MAME/FBNeo DAT names and parent/clone families) from the repo. Game names for MAME, FBNeo and PICO-8 sets come from the scraped `name` in storage's `scrapes/<system>/metadata.json`, else the file name. This keeps game references out of git.

**Architecture:** `names.title` loses its clones lookup (the scraped-name fallback it already has becomes the only source). `scrape_plan` loses `variant_tags` and the `family` argument, so gamelist names for these systems come from the scraped metadata like every other system. `surprise.is_candidate` loses its arcade "family" branch and judges MAME/FBNeo ROMs by their scraped title with the same rules as other systems. Skills, tool, data file, tests and docs that mention clones are removed or updated.

**Tech Stack:** Python standard library, `unittest`.

## Global Constraints

- Run tests with `PYTHONPATH=<worktree>/src /Users/kelsin/src/sync-roms/.venv/bin/python -m unittest discover -s tests` (the venv is editable-installed to the main checkout).
- `store.repo_json("clones")` and the file must have no callers left when the plan is done: `grep -rn "clones" src tools tests .claude CLAUDE.md README.md` finds only unrelated words (e.g. "clones the repo" in `setedit.py`) and the dated historical docs under `docs/superpowers/` (leave those).
- `names.title` order becomes: scraped `name` from `scrapes/<system>/metadata.json` (for pico8 the same), else the file name (pico8 without `.p8.png`). Nothing else about `names.py` changes (its tag cache, `reset`, `SYSTEMS`).
- Surprise: for the arcade systems (`names.SYSTEMS` minus `pico8`, i.e. mame and fbneo) `is_candidate` runs the same checks the other systems run on the file stem, but on `names.title(key)` instead (a scraped name; falls back to the file name when unscraped). BIOS exclusion (`base in bios or "[BIOS]" in base`) stays first. Other systems unchanged.
- Gamelist output for MAME/FBNeo no longer gets `sortname` family tags; the `name` tag comes from the scraped metadata via the normal path.
- Commits: Conventional Commits, imperative, lowercase, no attribution lines of any kind.
- Match the codebase's style; remove only code your change orphans; do not touch the dated docs under `docs/superpowers/`.

## Review Focus

- `plan_scrapes` and its callers (`scrape_plan.py:327-334` area, tests) no longer pass or accept `family`.
- Surprise on an arcade system with scraped names still excludes BIOS, prototypes/hacks/Japan-first titles by the generic rules and still returns standalone (clone-less) ROMs, which the old `parents`-only rule never did.
- `tools/gen_clones.py` and `tests/test_clones.py` are deleted, nothing imports them.

---

### Task 1: names.py and scrape_plan.py

**Files:**
- Modify: `src/sync_roms/names.py`, `src/sync_roms/scrape_plan.py`
- Modify tests: whatever `grep -rn "clones\|family\|variant_tags" tests` shows for these two modules (e.g. `tests/test_editor_data.py`, scrape plan tests, names tests). Do not touch `tests/test_clones.py` (Task 3 deletes it), `tests/test_surprise.py` (Task 2) or `tests/test_dedup_names.py` (Task 3).

- [ ] **Step 1:** In `names.py`, remove `_clones`, the `store.repo_json("clones")` load, the clone/parent lookups in `title`, and the reset of `_clones`; update the module docstring to the new order. Add/adjust a test that an arcade key with scraped metadata gets the scraped name and one without gets its file name.
- [ ] **Step 2:** In `scrape_plan.py`, delete `variant_tags`, the `family` parameter of `plan_scrapes` (and its docstring line), the `if family:` tag update, and the `clones = store.repo_json("clones")` / `clones.get(...)` plumbing at the caller. Remove imports this orphans (`re` only if unused elsewhere). Update/delete the tests of `variant_tags` and the ones passing `family`; keep a test that MAME gamelist entries take their name from metadata.
- [ ] **Step 3:** Run the full suite (tests for Task 2's and Task 3's areas still pass because those modules are untouched); commit `refactor(names): name arcade sets from scraped metadata only`.

### Task 2: surprise.py

**Files:**
- Modify: `src/sync_roms/surprise.py`, `tests/test_surprise.py`

- [ ] **Step 1:** Rewrite the arcade tests in `tests/test_surprise.py` (the `clones` fixture near line 58) to scraped names: tests that a MAME/FBNeo ROM whose scraped title has a Japan-first region group is not a candidate, a plain scraped title is, a ROM with no clones entry (standalone) is, and BIOS stays excluded. Use however the file's existing tests stub `names.title` / storage.
- [ ] **Step 2:** Implement per Global Constraints: drop the `family` parameter from `is_candidate` and `units`, drop `store.repo_json("clones")` in `_pools`, and for arcade systems run the stem checks on `names.title(key)`. Remove anything orphaned.
- [ ] **Step 3:** Run the full suite; commit `refactor(surprise): judge arcade sets by their scraped title`.

### Task 3: remove clones.json, its tool, tests, skills and docs

**Files:**
- Delete: `src/sync_roms/data/clones.json`, `tools/gen_clones.py`, `tests/test_clones.py`
- Modify: `.claude/skills/dedup-names/scripts/find_duplicates.py` and its `SKILL.md`, `tests/test_dedup_names.py`, `.claude/skills/update-variants/scripts/find_candidates.py` (only if it reads clones), `tests/test_editor_data.py` (the `repo_json("clones")` missing-file test: keep the behaviour it checks by using another data name, or delete it if it only existed for clones), `CLAUDE.md`, `README.md`

- [ ] **Step 1:** Delete the three files. In `find_duplicates.py` remove the clones skip (`why_skipped`'s clones reason, the `clones` argument of `find`, and the `store.repo_json("clones")` call in `main`); update `SKILL.md` (drop the `clones` skipped-count text) and `tests/test_dedup_names.py` (drop `CLONES` and the clones count assertion).
- [ ] **Step 2:** Update `CLAUDE.md` (the "Editors and new game titles name MAME, FBNeo and PICO-8 sets through `names.title`" paragraph: drop the clones.json sentence start; remove any other clones mention) and `README.md`/`find_candidates.py` mentions of clones.json or `gen_clones`.
- [ ] **Step 3:** Run the full suite and `grep -rn "clones" src tools tests .claude CLAUDE.md README.md`; commit `chore: remove clones.json`.
