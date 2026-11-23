# ToTK - James Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A custom spruce theme `ToTK - James`, built from the `ToTK` PyUI theme in storage with no palette, that adds a Collections menu card (Rauru), keeps cards for Sidon, Riju, Mineru and Rauru, shows the Triforce plus "James" as its top-left title image, and blanks the main menu title.

**Architecture:** Finished art is committed in `src/sync_roms/data/themes/totk-james/`, made once by `tools/gen_totk_james.py` from the ToTK base theme and official character renders on Zelda Wiki. A new style module `custom_themes/totk_james.py` copies the base theme and lays the art and a config change over it. `custom_themes.build`/`publish` and `commands.palette_args` learn that a style with `PALETTES = False` is built once, named by its `STYLE`, and never needs a palette.

**Tech Stack:** Python 3.12+, Pillow (no numpy: it isn't a dependency), unittest.

**Spec:** This plan (decisions made with the user in conversation; see "Decisions").

## Decisions

- Theme folder name: `ToTK - James`. Base theme: `ToTK` (storage `os/spruceos/themes/ToTK/`).
- Main menu Collections card is Rauru: `skin/ic-collection-f.png` (focused) and `skin/ic-collection-n.png` (normal). PyUI reads those names (other themes, e.g. `NextUI Style by Diego Mussi`, have them).
- All four characters ship in the theme even if unused: `skin/ic-collection-<id>-f.png` and `-n.png` for `sidon`, `riju`, `mineru`, `rauru`. Switching is a one-line change to `COLLECTIONS` in the module.
- `skin/bg-title.png` (196x51, opaque black) becomes the base's Triforce (its columns x 7..32, rows 29..50, copied as-is) followed by the text `James` in the base's own `HYLIA.TTF`, text starting at x 35, glyph top at y 27, bottom at y 50, colour sampled from the base's text (about `(255, 229, 153)`).
- Main menu title blank: `"mainMenuTitle": ""` in the theme's `config.json` (PyUI's `Theme.get_main_menu_title()` reads it; absent means "PyUI"). Also set `"name": "ToTK - James"`.
- Nintendo art is committed (the user's choice: the ToTK theme already distributes the same kind of art). Credit it in `src/sync_roms/data/themes/totk-james/README.md`.

## Global Constraints

- Always run Python through `uv run`; tests: `uv run python -m unittest discover -s tests`.
- Code must run on Python 3.12.
- Test modules import `helpers` (or `isolate`) before `sync_roms`.
- Never put test files in storage; the generator reads storage, never writes it.
- Conventional Commits, lowercase imperative; end each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Match existing style; touch only what the task needs.

## Review Focus

1. `themes build "ToTK - James"` with no saved palettes and `--yes`/no terminal must build (exit 0), not exit 2 about palettes. Test in Task 2.
2. `themes build` with a terminal and only `ToTK - James` named must not open the palette picker. Test in Task 2.
3. `themes build` with no names builds the pixel styles in the chosen palettes plus `ToTK - James` once (not once per palette). Test in Task 2.
4. `--palette Gruvbox "ToTK - James"` builds `ToTK - James` once and ignores the palette (no `ToTK - James - Gruvbox`). Test in Task 2.
5. A base `config.json` with a UTF-8 BOM still gets `mainMenuTitle` set (read with `utf-8-sig`). Test in Task 2.

---

### Task 1: Generate and commit the art

**Files:**
- Create: `tools/gen_totk_james.py`
- Create: `src/sync_roms/data/themes/totk-james/bg-title.png`
- Create: `src/sync_roms/data/themes/totk-james/cards/{sidon,riju,mineru,rauru}-{f,n}.png`
- Create: `src/sync_roms/data/themes/totk-james/README.md`
- Test: `tests/test_totk_james.py` (data shape only here; Task 2 adds build tests)

**Interfaces:**
- Produces: the files above. Cards are 156x328 RGBA; `bg-title.png` is 196x51.

Reference implementation (numpy-based, proven to give good results) is in the session scratchpad: `/private/tmp/claude-501/-Users-kelsin-src-sync-roms--claude-worktrees-totk-theme-text-custom-6568e4/67214ae6-2d84-46fa-beba-c60f6747ad81/scratchpad/make.py` (with `bg2.py` for the background stitch). Port it to Pillow-only Python (plain loops over 156x328 pixels are fine). The tool:

- `uv run python tools/gen_totk_james.py [--base DIR]`; `--base` defaults to `/Volumes/roms/os/spruceos/themes/ToTK`. It only reads there.
- Downloads the renders (cached in `store.cache_dir()/theme-art/totk-james/`, or a `--cache` dir) with a plain User-Agent `sync-roms-tools`:
  - sidon: `https://cdn.wikimg.net/en/zeldawiki/images/5/54/TotK_Sidon_Artwork_2.png`
  - riju: `https://cdn.wikimg.net/en/zeldawiki/images/1/14/TotK_Riju_Artwork_2.png`
  - mineru: `https://cdn.wikimg.net/en/zeldawiki/images/1/10/TotK_Mineru_Artwork.png`
  - rauru: `https://cdn.wikimg.net/en/zeldawiki/images/a/a4/TotK_Rauru_Artwork_2.png`
- Background: the base's six focused cards `skin/ic-{game,favorite,recent,app,retroarch,setting}-f.png` share one swirl background at the same position. For each pixel take the colour of the first card pair (in `itertools.combinations` order) whose RGB differ by at most 4 per channel; treat as unknown where no pair agrees, where max−min channel > 25, or where max channel > 120. Fill unknowns from, in order: horizontal mirror, vertical mirror, both, then `roll` offsets dx in (40,−40,80,−80,60,−60,100,−100) × dy in (0,60,−60,120,−120); any left: grey 14.
- Frame: pixels where `ic-game-f.png` has alpha < 255, or where all six focused cards are identical and either near cream `(250,247,221)` (±30 per channel) or on the edge band (x ≤ 11, x ≥ 144, y ≤ 28, y ≥ 271), are copied from `ic-game-f.png`.
- Art: crop the render to its alpha bbox, then the window aspect 142:252, top at `top·h`, height `hf·h`, centred at `cx·w`; resize with LANCZOS to 142x252 and paste at (7,24) over the background. Values (top, hf, cx): sidon (0.02, 0.50, 0.60), riju (0.06, 0.45, 0.50), mineru (0.02, 0.42, 0.47), rauru (0.0, 0.80, 0.40).
- Normal card: alpha from `ic-game-n.png` (transparent pixels written as (255,255,255,0)); grey `g = round(lum(art)·0.25·a + min(lum(bg)·1.1, 64)·(1−a))`, where `a` is the art layer's alpha/255 and `lum = 0.299R+0.587G+0.114B`.
- Title: as in Decisions. Pick the font size so the cap height spans rows 27..50 like the original.
- Also writes a review sheet (all base cards and the new ones, 2x) to the cache, never to the repo, and prints its path.

- [ ] **Step 1: Write the failing data test** in `tests/test_totk_james.py`

```python
DATA = os.path.join(os.path.dirname(sync_roms.__file__), "data", "themes", "totk-james")

def test_cards_present_and_sized(self):
    for cid in ("sidon", "riju", "mineru", "rauru"):
        for state in ("f", "n"):
            with Image.open(os.path.join(DATA, "cards", f"{cid}-{state}.png")) as im:
                self.assertEqual(im.size, (156, 328))
                self.assertEqual(im.mode, "RGBA")

def test_title_size(self):
    with Image.open(os.path.join(DATA, "bg-title.png")) as im:
        self.assertEqual(im.size, (196, 51))
```

- [ ] **Step 2: Run it, expect FAIL** (files missing): `uv run python -m unittest tests.test_totk_james -v`
- [ ] **Step 3: Write `tools/gen_totk_james.py`** as above and run it: `uv run python tools/gen_totk_james.py`
- [ ] **Step 4: Look at the review sheet** (Read the PNG). The new cards must match the base cards: cream frame, drop shadow, swirl visible around the character, dim cards grey with visible swirl. The title must read "Triforce James" with no stray pixels. Report the sheet path to the controller.
- [ ] **Step 5: Write `README.md`** in the data folder: what the files are, how to regenerate (`tools/gen_totk_james.py`), credits: character art © Nintendo, from Zelda Wiki (the four file URLs); card frame, swirl background, Triforce and HYLIA font from the ToTK PyUI theme (adapted by CraigN aka CruxisMithos from NaraMakesGames' Onion theme; HYLIA font by Ruidacosta).
- [ ] **Step 6: Run the test, expect PASS**
- [ ] **Step 7: Commit**: `feat(themes): add the totk - james theme art` (tool, data folder, test).

### Task 2: The `ToTK - James` style and palette-free builds

**Files:**
- Create: `src/sync_roms/custom_themes/totk_james.py`
- Modify: `src/sync_roms/custom_themes/__init__.py` (`STYLES`, `build`, new `needs_palettes`)
- Modify: `src/sync_roms/commands.py` (`themes_build`, `themes_publish`: call `palette_args` only when needed)
- Modify: `src/sync_roms/cli.py` (themes build/publish help), `README.md` (lines ~176 and ~461), `CLAUDE.md` (custom themes bullet; repo data list for `data/themes/totk-james/`)
- Test: `tests/test_totk_james.py`, `tests/test_custom_themes.py` (`test_registry_styles` now lists three styles; only pixel styles have `BASE == "SPRUCE"`)

**Interfaces:**
- Consumes: Task 1's data files.
- Produces:
  - `totk_james.STYLE = "ToTK - James"`, `BASE = "ToTK"`, `PALETTES = False`, `CHARACTERS = ("sidon", "riju", "mineru", "rauru")`, `COLLECTIONS = "rauru"`.
  - `totk_james.build(base_dir, out_dir, palette=None) -> str`: replaces `<out_dir>/ToTK - James/` with a copy of the base, then writes `skin/bg-title.png`, the eight `skin/ic-collection-<id>-{f,n}.png`, `skin/ic-collection-{f,n}.png` (copies of `COLLECTIONS`' cards), and in every top-level `config*.json` sets `name` and `mainMenuTitle` (read `utf-8-sig`, write UTF-8 with `indent=4`). Returns the folder.
  - `custom_themes.needs_palettes(styles) -> bool`: True when any chosen style (all when None) lacks `PALETTES = False` (`getattr(module, "PALETTES", True)`).
  - `custom_themes.build(styles, palettes, out=None)`: ValueError "no palettes to build" only when a chosen palette style has no palettes; a palette-free style is built once into `built[module.STYLE]`, whatever the palettes. Base fetched once per `BASE` as now.
  - `commands.themes_build`/`themes_publish`: `chosen = palette_args(args) if custom_themes.needs_palettes(styles) else []`.

- [ ] **Step 1: Write failing tests**
  - `test_build_lays_art_over_base`: a temp base with `config.json` `{"name": "ToTK", "title": {"size": 30}}`, `skin/bg-title.png` (196x51 black) and `skin/ic-game-f.png`; `totk_james.build(base, out)` returns `out/ToTK - James`; its `skin/bg-title.png` bytes equal the data file's; `skin/ic-collection-f.png` bytes equal `cards/rauru-f.png`, `-n` likewise; all eight `ic-collection-<id>-<f|n>.png` exist; `skin/ic-game-f.png` is copied; config has `name == "ToTK - James"`, `mainMenuTitle == ""`, `title == {"size": 30}`.
  - `test_build_replaces_previous_output`: a stray file in `out/ToTK - James/` is gone after a build.
  - `test_bom_config` (Review Focus 5).
  - In `test_custom_themes.py`: `needs_palettes(["ToTK - James"])` is False, `needs_palettes(None)` and `needs_palettes(["Pixel Consoles"])` True; `custom_themes.build(["ToTK - James"], [])` with `fetch_base` patched to return a temp base gives `{"ToTK - James": ...}`; `build(None, [GRUVBOX])` gives keys `Pixel Consoles - Gruvbox`, `Pixel Controllers - Gruvbox`, `ToTK - James` (Review Focus 3, 4; patch `fetch_base` to return a SPRUCE or ToTK base by name); `build(["Pixel Consoles"], [])` still raises ValueError.
  - Command tests (Review Focus 1, 2): `themes build "ToTK - James"` with `ui.has_terminal` True and no saved palettes doesn't call `palette_picker.pick` and returns 0; with `ui.ASSUME_YES` and no saved palettes, returns 0.
- [ ] **Step 2: Run, expect FAIL**: `uv run python -m unittest tests.test_totk_james tests.test_custom_themes -v`
- [ ] **Step 3: Implement** the interfaces above; add `totk_james` to `STYLES`.
- [ ] **Step 4: Update docs**: cli.py help and README name the three styles and say `ToTK - James` has no palette (built once, from the ToTK theme in storage); CLAUDE.md's custom themes bullet gains `PALETTES = False` (built once as `<style>`, no palette needed) and the repo data list gains `data/themes/totk-james/` (made by `tools/gen_totk_james.py`).
- [ ] **Step 5: Run the full suite, expect PASS**: `uv run python -m unittest discover -s tests`
- [ ] **Step 6: Commit**: `feat(themes): add the totk - james theme`
