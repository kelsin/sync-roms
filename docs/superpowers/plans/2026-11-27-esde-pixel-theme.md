# Pixel for ES-DE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An ES-DE theme, "Pixel", built by sync-roms from the Spruce Pixel themes' sprites, palettes and font, installed by sync on `esde` and `emudeck` cards, with a sprite for every ES-DE system in `systems.json`.

**Architecture:** A new `custom_themes/esde/` package maps ES-DE system names to Pixel sprites and writes the whole theme (capabilities, theme XML per aspect ratio, colour schemes from `palettes.py`, sprite PNGs, font) into `cache/themes/esde/pixel-sync-roms/`, rebuilt only when its sources change. A new sync step copies it into the card's ES-DE `themes/` folder. `themeart.py` learns to put collection art into Pixel when ES-DE uses it. New sprites are drawn in batches the user approves.

**Tech Stack:** Python 3.12+, Pillow, `xml.etree.ElementTree` for writing XML, unittest.

**Spec:** `docs/superpowers/specs/2026-11-27-esde-pixel-theme-design.md`

## Global Constraints

- Theme folder name `pixel-sync-roms`; display name "Pixel". Never in storage; built from repo code and data only.
- Variants `consoles` ("Consoles") and `controllers` ("Controllers"). One colour scheme per `palettes.PALETTES` entry, label = palette name, all 35.
- Aspect ratios declared: `16:9`, `16:10`, `4:3`, `3:2`, `1:1`, `8:7`, `5:3_vertical`. Only names from ES-DE's list are valid (THEMES.md, https://gitlab.com/es-de/emulationstation-de/-/raw/master/THEMES.md).
- Colours: the palette's `text`, `list`, `selected`, `accent`, `dim`, `bar`, on black (`000000FF`). ES-DE colours are `RRGGBBAA`.
- Font: the bundled Fusion Pixel font (`data/themes/fusion-pixel/fusion-pixel-12px-proportional-ja.ttf`) with its `OFL.txt`; sizes chosen to land on multiples of 12 px at each layout's reference resolution.
- Sprites: `custom_themes/pixel/sprite.py` (`COLORS`, `render`, `place`), same canvas as the Spruce icons (`pixel/build.py` `ICON_SIZE`, `ICON_CENTER`), clean-line rules in `sprite.py`'s docstring: mirrored halves, regular steps, no odd outline pixels.
- Sync never changes ES-DE's `Theme` away from what the user picked, never selects Pixel, and never sets the variant or colour scheme. A new card (no `Theme`) still gets Art Book Next selected, as today.
- Guest cards get nothing from this (like the rest of `frontend_step`).
- Python 3.12; tests import `helpers` (which imports `isolate`) first. Commits: Conventional Commits, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run tests with `uv run python -m unittest tests.<module> -v` (stdin closed: append `< /dev/null`).

## Review Focus

1. A card whose ES-DE `Theme` is `pixel-sync-roms`: a sync must leave `Theme` alone and still refresh Pixel and its collection art (today `install_esde` writes `Theme` on every run). Task 9 pins it.
2. An `emudeck` sync where `frontend.emudeck_problem` reports a problem (no ES-DE folder): the Pixel step prints the skip reason and writes nothing. Task 8 pins it.
3. A Pixel copy on the card from an older build: files the new build no longer has are removed, sync-roms's own collection art and list are kept, and a sync stopped mid-copy is finished by the next (marker written last). Task 8 pins it.
4. A collection whose lower-cased name equals an ES-DE system name never overwrites that system's sprite (`themeart.usable` refuses reserved names already; the Pixel art writer must go through it). Task 9 pins it.
5. The card's `theme` flag off: no Pixel copy is made, and an existing one is left as it is. Task 8 pins it.

---

### Task 1: ES-DE system to sprite map

**Files:**
- Create: `src/sync_roms/custom_themes/esde/__init__.py` (empty docstring module)
- Create: `src/sync_roms/custom_themes/esde/systems.py`
- Test: `tests/test_esde_pixel.py`

**Interfaces:**
- Produces: `systems.ICONS: dict[str, str]`, ES-DE system name (the `esde` folder in `systems.json`) to a Pixel icon id drawn by `pixel.build.systems(kind)`; `systems.EXTRA: dict[str, dict[str, Callable]]`, ES-DE name to `{"CONSOLES": draw, "CONTROLLERS": draw}` for drawings that aren't Spruce icon ids (filled by Tasks 3 to 6); `systems.PENDING: set[str]`, ES-DE names still waiting for a drawing (emptied by Tasks 3 to 6); `systems.sprites(kind: str) -> dict[str, Callable[[], Sprite]]`, every mapped ES-DE name to its draw function for `kind` in `("CONSOLES", "CONTROLLERS")`; `systems.esde_names() -> list[str]`, the `esde` folders of `systems.json` in file order, deduplicated (`n3ds` is listed twice).

- [ ] **Step 1: Write the failing tests**

```python
class SystemsMap(unittest.TestCase):
    def test_every_esde_system_is_mapped_or_pending(self):
        names = set(esde_systems.esde_names())
        mapped = set(esde_systems.ICONS) | set(esde_systems.EXTRA)
        self.assertEqual(names - mapped, esde_systems.PENDING)

    def test_pending_and_mapped_are_disjoint(self):
        self.assertFalse(esde_systems.PENDING & (set(esde_systems.ICONS) | set(esde_systems.EXTRA)))

    def test_icons_point_at_drawn_sprites(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            drawn = pixel_build.systems(kind)
            for name, icon in esde_systems.ICONS.items():
                self.assertIn(icon, drawn, (kind, name))

    def test_sprites_render(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            for name, draw in esde_systems.sprites(kind).items():
                self.assertIsInstance(draw(), Sprite, (kind, name))

    def test_reuse(self):
        self.assertEqual(esde_systems.ICONS["mame-advmame"], esde_systems.ICONS["mame"])
        self.assertEqual(esde_systems.ICONS["naomi2"], "naomi")
        self.assertEqual(esde_systems.ICONS["naomigd"], "naomi")
        self.assertEqual(esde_systems.ICONS["msx2"], "msx")
        self.assertEqual(esde_systems.ICONS["fbneo"], "arcade")
        self.assertIn("mark3", esde_systems.EXTRA)  # the Japanese Master System drawing in pixel/variants.py
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: sync_roms.custom_themes.esde`): `uv run python -m unittest tests.test_esde_pixel -v < /dev/null`

- [ ] **Step 3: Implement `systems.py`**

Map by hand from `systems.json`'s `esde` and `spruce` folders and `pixel/ids.py` (e.g. `nes`→`fc`, `snes`→`sfc`, `genesis`→`md`, `psx`→`ps`, `atari7800`→`7800`, `pico8`→`pico`, `c64`→`c64`, `arcade`→`arcade`, `mame-advmame`→`mame`). `mark3` goes in `EXTRA` using `pixel.variants.mark3_console` / `mark3_pad`. Reuse for same hardware: `naomi2`/`naomigd`→`naomi`, `msx2`→`msx`, `n3ds` is one 3DS drawing (pending). Everything with no sprite yet goes in `PENDING`: expected about `pcfx, daphne, lowresnx, lutro, n64dd, 3do, uzebox, atarijaguarcd, cdimono1, gc, model2, model3, n3ds, ps2, ps3, ps4, psvita, stv, switch, triforce, type-x, wii, wiiu, xbox, xbox360, xboxone, arcadia, gamate, gamecom` (check `gamate`: `pixel/extras.py` may draw it already).

- [ ] **Step 4: Run, expect PASS**, then commit `feat(themes): map es-de systems to pixel sprites`.

---

### Task 2: Sprite contact sheet tool and research protocol

**Files:**
- Create: `tools/esde_sprite_sheet.py`
- Create: `docs/pixel-sprites.md` (the drawing protocol, used by Tasks 3 to 6)
- Test: `tests/test_esde_pixel.py` (class `SpriteSheet`)

**Interfaces:**
- Produces: `uv run python tools/esde_sprite_sheet.py [--out PATH] NAME...` writes one PNG: a row per ES-DE name in NAME, showing its Consoles and Controllers sprites, each `sel` and `n` state, rendered with `render(sprite, 4, state)` and enlarged 2x with nearest-neighbour, on black, labelled; then a reference row of 8 existing sprites (`gb, sfc, md, ps, n64, dc, neogeo, psp`) at the same scale. Default `--out` is `cache/themes/esde-sprites.png` under the data folder. Function `sheet(names: list[str]) -> PIL.Image.Image` in the tool (importable with `importlib` from tests).

- [ ] **Step 1: Failing test** `test_sheet_has_a_row_per_name_and_the_reference_row`: `sheet(["gb", "nes"])` height equals 3 rows (2 names + reference) of the row height the tool defines; width is at least 4 sprite cells.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Write the tool**, and `docs/pixel-sprites.md` with the protocol: for each system, search the web for photos of the real console (front, three-quarter) and its standard controller, note the defining shapes and colours (body outline, disc/cart slot, logo stripe, button layout and colours), pick the closest `COLORS` names (add a colour to `COLORS` only when no existing one is close, and say so in the batch report), draw in a `Sprite` sized like its neighbours in the existing set (similar consoles are within ±4 px of each other), mirror symmetric hardware, then make the sheet and compare against the references and the reference row. A reviewer subagent checks each sprite against the reference photos and the clean-line rules before the batch goes to the user.
- [ ] **Step 4: Run, expect PASS**; commit `feat(themes): add the pixel sprite contact sheet tool`.

---

### Tasks 3 to 6: Sprite batches (each ends with the user's approval)

Each batch task has the same shape. New drawings live in `src/sync_roms/custom_themes/pixel/modern.py` (Tasks 3 and 4) and `src/sync_roms/custom_themes/pixel/esde_extra.py` (Tasks 5 and 6), each exporting `CONSOLES` and `CONTROLLERS` dicts keyed by **ES-DE system name**. They are not added to `pixel/build.py`'s `BATCHES`, so the Spruce themes don't change. `esde/systems.py` adds each drawn name to `EXTRA` and removes it from `PENDING`.

| Task | Batch | Systems (ES-DE names) |
|---|---|---|
| 3 | Nintendo | `gc`, `wii`, `wiiu`, `switch`, `n3ds`, `n64dd` |
| 4 | Sony and Microsoft | `ps2`, `ps3`, `ps4`, `psvita`, `xbox`, `xbox360`, `xboxone` |
| 5 | Other consoles | `3do`, `cdimono1`, `pcfx`, `atarijaguarcd`, `arcadia`, `gamecom`, `gamate` (if pending), `uzebox` |
| 6 | Arcade boards and engines | `model2`, `model3`, `stv`, `triforce`, `type-x`, `daphne`, `lowresnx`, `lutro` |

Controllers for arcade boards follow `pixel/arcade.py`'s pattern (a stick panel, `_panel`); engines (`lowresnx`, `lutro`, `uzebox`) follow `arcade.py`'s `SHARED` engines (one drawing used for both kinds, its own logo-like mark).

- [ ] **Step 1: Failing test** `test_batch_<n>_drawn`: for each name of the batch, `name in esde_systems.EXTRA` and `name not in esde_systems.PENDING`, and both kinds render a `Sprite` whose `bounds()` width and height are each between 16 and 30 px (the existing set's range; adjust the bounds to the measured min and max of `pixel_build.systems(kind)` if they differ, and keep that measure in the test).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Research and draw** each system per `docs/pixel-sprites.md`.
- [ ] **Step 4: Self-review**: make the sheet (`tools/esde_sprite_sheet.py <batch names>`), read it, and have a reviewer subagent compare each sprite with its reference photos and the reference row; redraw what fails.
- [ ] **Step 5: Run tests, expect PASS.**
- [ ] **Step 6: User approval (blocking)**: send the user the sheet (SendUserFile) with one line per system naming the reference used; redraw anything they reject and show it again. Do not start the next batch before approval.
- [ ] **Step 7: Commit** `feat(themes): draw pixel sprites for <batch>` (the sheet itself is never committed).

After Task 6, add `test_nothing_pending`: `self.assertEqual(esde_systems.PENDING, set())`.

---

### Task 7: Theme files, colour schemes and variants

**Files:**
- Create: `src/sync_roms/custom_themes/esde/build.py`
- Test: `tests/test_esde_pixel.py` (class `ThemeFiles`)

**Interfaces:**
- Consumes: `systems.sprites(kind)`, `systems.esde_names()`, `palettes.PALETTES`, `sprite.render/place`.
- Produces: `build.THEME = "pixel-sync-roms"`; `build.RATIOS = ("16:9", "16:10", "4:3", "3:2", "1:1", "8:7", "5:3_vertical")`; `build.build(out_dir: str) -> str` writes `<out_dir>/pixel-sync-roms/` (replacing it) and returns that path. Layout of the folder: `capabilities.xml`, `theme.xml` (root: includes, variables, colour schemes), `layouts/<ratio with : and . replaced by ->.xml` (filled by Tasks 7b and 7c), `systems/consoles/<esde name>.png`, `systems/controllers/<esde name>.png` (both rendered `sel` state, placed on `ICON_SIZE`), `art/tile.png` (white rounded tile, tinted by `${pixelBar}`), `font/fusion-pixel-12px-proportional-ja.ttf`, `font/OFL.txt`, `README.md` (one line: generated by sync-roms, from the Pixel themes).

- [ ] **Step 1: Failing tests**
  - `test_capabilities_declares_variants_schemes_ratios`: parse `capabilities.xml`; variant names == `{"consoles", "controllers"}`; colour scheme names are the 35 palette names slugged (`slug(name)`: lower case, non-alphanumerics to `-`), labels are the palette names; aspect ratios == `set(build.RATIOS)`.
  - `test_every_scheme_sets_every_colour`: in `theme.xml`, each `<colorScheme>` defines `pixelText`, `pixelList`, `pixelSelected`, `pixelAccent`, `pixelDim`, `pixelBar`, each `RRGGBBFF` equal to its palette's value; e.g. SNES `pixelBar` == `5B50D8FF`.
  - `test_every_system_has_both_sprites`: for every `esde_names()`, both PNGs exist and are `ICON_SIZE`.
  - `test_variant_paths`: the `consoles` variant sets `pixelSystemArt` to `./systems/consoles/${system.theme}.png`, `controllers` to `./systems/controllers/${system.theme}.png`.
  - `test_build_is_deterministic`: two builds give byte-identical trees.
  - `test_every_xml_parses`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Check element and property names against THEMES.md before writing them (variables, `<variant>`, `<colorScheme>`, `<aspectRatio>`, `<include>`); write XML with `ElementTree` and `indent`, UTF-8, `\n` line ends.
- [ ] **Step 4: Run, expect PASS**; commit `feat(themes): build the pixel es-de theme files`.

### Task 7b: System view (carousel) layouts

**Files:** Modify `src/sync_roms/custom_themes/esde/build.py` (a `system_view(ratio) -> Element` per ratio); Test `tests/test_esde_pixel.py` (class `SystemView`).

Layout per the spec: carousel, `horizontal` for every ratio but `5:3_vertical` (`vertical`); `staticImage` `${pixelSystemArt}`; the selected item drawn larger (`itemScale`) with unfocused items dimmed and desaturated (Spruce's `n` state: check the carousel's unfocused-item properties in THEMES.md); `art/tile.png` tinted `${pixelBar}` behind the centre item; system name (`${system.fullName}`) below in `${pixelText}`, game count in `${pixelAccent}`; a help bar at the bottom in `${pixelDim}`. Element sizes and positions are the builder's (relative coordinates).

- [ ] Tests: `test_carousel_per_ratio` (every ratio's layout has one carousel, `vertical` only in `5:3_vertical`); `test_colours_are_variables` (every `color`/`textColor` in the system view is a `${pixel...}` variable).
- [ ] Run FAIL, implement, run PASS, commit `feat(themes): add the pixel es-de system view`.

### Task 7c: Game list layouts

**Files:** Modify `src/sync_roms/custom_themes/esde/build.py` (`gamelist_view(ratio) -> Element`); Test class `GamelistView`.

Per the spec: text list (selected row background `${pixelBar}`, selected text `${pixelSelected}`, others `${pixelList}`); scraped image `imageType` `miximage`; labels and values for genre, players, release date, rating (label text in `${pixelAccent}`); description, except in `5:3_vertical`. Wide ratios: list on the left (about 46% width), details right. `5:3_vertical`: art and metadata on top, list below. No video element.

- [ ] Tests: `test_gamelist_has_list_image_metadata` (each ratio has the list, a miximage image, the four metadata fields); `test_vertical_has_no_description` (only `5:3_vertical` lacks it); `test_font_sizes_are_multiples_of_12` (for each ratio's reference height, `fontSize * height` rounds to a multiple of 12; reference heights: 16:9 1080, 16:10 800, 4:3 960, 3:2 640, 1:1 720, 8:7 1080, 5:3_vertical 800).
- [ ] Run FAIL, implement, run PASS, commit `feat(themes): add the pixel es-de game list`.

### Task 7d: Look at it

- [ ] Render a preview of the system view and game list for `16:9` and `5:3_vertical` in the SNES palette (a throwaway script in the scratchpad that draws the layout's boxes and sprites with Pillow from the built XML positions is enough; if ES-DE is installed on this Mac, point it at the built theme instead and take screenshots). Send the previews to the user and adjust on their feedback before Task 8.

---

### Task 8: Cached build and the sync step

**Files:**
- Create: `src/sync_roms/esde_pixel.py`
- Modify: `src/sync_roms/cli.py` (sync: call it next to `frontend_step`, dry run at the `frontend_step(True)` call and real at `frontend_step(False)`, both under `if not guest`)
- Test: `tests/test_esde_pixel.py` (class `Install`, using a temp card folder with `layout_name="esde"` and the `helpers` card fixtures used by `tests/test_themeart.py`)

**Interfaces:**
- Consumes: `build.build`, `build.THEME`, `themeart._esde_dir`'s pattern (`frontend.esde_dir(layout_name, base)/themes/`), `cardfs.write_bytes` (returns whether it changed), `store.cache_dir()`.
- Produces: `esde_pixel.THEME = build.THEME`; `esde_pixel.cached() -> str` (the built theme folder in `cache/themes/esde/`, rebuilt when the SHA-256 over the source files of `custom_themes/esde/`, `custom_themes/pixel/`, `palettes.py`, the font, and `data/themes/art-book-next/art-box/Imgs/` differs from `.sync-roms-build` in it); `esde_pixel.install(layout_name: str, base: str) -> bool` (copies changed files, removes files not in the build except `.sync-roms-collections` and the collection art it lists, writes the marker `.sync-roms-build` last, returns whether anything changed); `esde_pixel.describe(layout_name, base) -> None` (prints `🎨 would install Pixel for ES-DE into <path>` / `would update` / nothing when current); `esde_pixel.dest(layout_name, base) -> str`.
- Sync step rules: only `layout_name in frontend.ESDE_LAYOUTS`, the card's `theme` flag on (`store.card_flag(entry, "theme")`), and no `esde_problem` (then print the same skip as `frontend_step`'s `skipped()`). Prints `🎨 Installed Pixel for ES-DE` / `🎨 Updated Pixel for ES-DE` when it changed something. Sets `clean._clean_root = base` when it changed a card (not `emudeck`).

- [ ] **Step 1: Failing tests**: `test_install_copies_theme_and_marker`; `test_second_install_changes_nothing` (returns False); `test_stale_file_removed_but_collection_art_kept` (Review Focus 3); `test_stopped_copy_is_finished` (marker removed → next install rewrites it and returns True); `test_theme_flag_off_installs_nothing_and_keeps_existing` (Review Focus 5, through the sync step's helper); `test_emudeck_problem_skips` (Review Focus 2); `test_never_touches_theme_setting` (`es_settings.xml` unchanged after install); `test_cached_rebuilds_only_when_sources_change` (patch the hash function's inputs).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**, plus the full suite: `uv run python tools/run_tests.py < /dev/null`.
- [ ] **Step 5: Commit** `feat(sync): install the pixel es-de theme on es-de cards`.

---

### Task 9: Collection art in Pixel

**Files:**
- Modify: `src/sync_roms/themeart.py` (`esde_wanted`, `install_esde`, `describe_esde`)
- Modify: `src/sync_roms/cardedit.py:450` (the S menu line: `🎨 Theme (Art Book Next and Pixel for ES-DE, collection art)`)
- Test: `tests/test_themeart.py` (new class `PixelArt`)

**Interfaces:**
- Consumes: `esde_pixel.dest`, `esde_pixel.THEME` (re-export of `build.THEME`).
- Behaviour: `esde_wanted` is true for no `Theme`, Art Book Next, or `pixel-sync-roms`. When `Theme` is `pixel-sync-roms`, `install_esde` writes each collection's box art (`art-box/Imgs/<art id>.png`, found from the outline art path's file name) to `systems/consoles/<name lower>.png` and `systems/controllers/<name lower>.png` in Pixel's folder, keeps `.sync-roms-collections` there as it does for Art Book Next, removes art of collections gone (unless `keep`), and **does not write `Theme`**. Otherwise behaviour is unchanged.

- [ ] **Step 1: Failing tests**: `test_pixel_selected_gets_box_art_in_both_variants`; `test_pixel_selected_theme_setting_unchanged` (Review Focus 1); `test_pixel_removes_gone_collection_art`; `test_reserved_name_never_overwrites_a_system_sprite` (a collection named `snes` is refused by `usable` and `systems/consoles/snes.png` is unchanged: Review Focus 4); `test_new_card_still_gets_art_book_next`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**, then the full suite.
- [ ] **Step 5: Commit** `feat(themes): put collection art in pixel when es-de uses it`.

---

### Task 10: Docs

**Files:** Modify `CLAUDE.md` (Data files → Personal data `cache/` list: `themes/esde/`; "What sync puts on a card": a bullet for Pixel on `esde`/`emudeck`; Custom themes bullet: the ES-DE build and `esde/systems.py`; Theme art data: Pixel gets the `art-box/` art); `README.md` where it describes themes, if it does. Run `uv run python -m unittest tests.test_readme -v < /dev/null`.

- [ ] Edit, run the README test and the full suite, commit `docs: describe the pixel es-de theme`.

### Task 11: On-device check

- [ ] Ask the user to sync a 16:9 `esde` card and the MagicX Zero 40, pick Pixel in ES-DE's UI Settings, switch variants and a few colour schemes, and report what looks wrong. Fix in follow-up commits.
