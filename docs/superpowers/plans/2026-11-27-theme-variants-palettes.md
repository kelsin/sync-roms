# Theme Variants & Palettes (sync-roms side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one `Pixel` spruceOS theme that carries both variants and every palette as data (`options/`), so the device renders the user's choice, and make card sync respect what the device generates.

**Architecture:** The legacy per-palette build stays untouched; a second drawing pass with "recipe" shades records, per pixel, how each colour derives from the palette. Those recipe grids (and the bar-gray pixels of the base's own skins) are written as PUT2 templates. A new `Pixel` style builds the default look at the top level and writes `options/` (manifest, applied.json, both variants' files, templates). Card sync skips device-generated files and writes `options/selected.json` from a card setting.

**Tech Stack:** Python 3.12+, Pillow (build side only), `struct` + `zlib` for PUT2, `unittest`.

**Spec:** https://claude.ai/artifact/CHxfXBYr7Y76Q2kzJBGzvE (read it with the Artifact read action), sections "Format contract v1" and "sync-roms work" (Y1–Y3). Y4 (migration) is out of scope.

## Global Constraints

- Run everything with `uv run`; tests: `uv run python tools/run_tests.py`. Code must run on Python 3.12.
- Test modules import `isolate` (or `helpers`) before `sync_roms`.
- The legacy styles `Pixel Consoles` / `Pixel Controllers` must build byte-identical output to today. Don't change their drawing code paths beyond what Task 1 says.
- Never write to storage. Building reads the SPRUCE base from storage (`fetch_base`) only.
- Conventional Commits, lowercase imperative, each commit ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Accent Color (`accent/`) is out of scope: never read or written.
- Update CLAUDE.md where a task changes what it documents (custom themes bullet, Card fields table, spruce_themes bullet).

### Format amendments to contract v1 (decided; apply in `docs/theme-options-format.md`)

The artifact's contract, copied word for word, plus these amendments marked **Amended** (they are required for the byte-equality test):

1. **Entries are 10 bytes**: `alpha u8, kind u8, src u16, target u8, t u16, r u8, g u8, b u8` (little endian). `t` is in thousandths: the mix amount is the float `t / 1000`. (`t/255` can't reproduce `.35`, `.45`, `.5`, `.7`: dozens of channel values round differently.)
2. **kind 2** = entry `src` (an earlier entry, `src` < this entry's index) mixed toward `target` by `t/1000`. kind 1's `src` is the role index. kind 0 ignores `src`/`target`/`t`. (The unselected key mixes `dark` toward black again: two roundings.)
3. **Mixing is exactly** `round(a + (b - a) * t)` per channel with Python's `round` (half to even), `a` the source channel, `b` the target channel; `target 0` (none) means the source colour itself.
4. **`igmKeys` values** are `{"role": "<id>", "suffix": "FF"}` objects (igm.json colours are 8-digit `#RRGGBBAA`); `configKeys` values stay plain role ids.
5. **Shipped `applied.json` re-apply after a theme update**: when sync-roms copies a changed `options/` file to a card it also copies storage's top-level files and `applied.json` (the defaults), so the device re-applies the user's `selected.json` on next boot.

## Review Focus

1. A palette whose mix lands on .5 → template render must still equal Pillow output (Task 3's all-palette test).
2. A user who set custom colours on the device (`palette: null`) → a later sync never overwrites `selected.json` unless the card setting changed since sync last wrote it (Task 6 test).
3. Storage republishes `Pixel` while the card shows a non-default palette → the card gets the new files and storage's `applied.json`, and keeps `selected.json` (Task 5 test).
4. An image with more than 256 distinct RGBA entries → 2-byte indexes, still round-trips (Task 2 test).
5. A theme without `options/manifest.json` → sync behaves exactly as today (Task 5 test).

---

### Task 1: Recipe shades and the recording frames pass

**Files:**
- Create: `src/sync_roms/custom_themes/pixel/recipe.py`
- Modify: `src/sync_roms/custom_themes/pixel/frames.py` (`_mix`, `apply`)
- Test: `tests/test_recipe.py`

**Interfaces:**
- Produces:
  - `recipe.ROLES = ("text", "list", "selected", "accent", "dim", "bar")` (manifest role order).
  - `@dataclass(frozen=True) class Recipe: src: "str | Recipe | tuple"; target: "None | tuple" = None; t: float = 0.0` — `src` a role id, a nested `Recipe`, or a fixed `(r, g, b)`; `target` None, `(255,255,255)`, `(0,0,0)` or a fixed rgb.
  - `recipe.shades() -> frames.Shades` with each role `Recipe(role)`, `hi=Recipe("bar", WHITE, .35)`, `sh=Recipe("bar", BLACK, .4)`, `mid=Recipe("bar", BLACK, .45)`, `dark=Recipe("bar", BLACK, .7)`, `ink=Recipe(INK rgb)`.
  - `recipe.resolve(r: Recipe | tuple, palette) -> tuple` (rgb), using `frames._mix` arithmetic.
  - `frames._mix(a, b, t)`: when `a` is a `Recipe`, returns `Recipe(a, b, t)`; tuples behave as today.
  - `frames.apply(theme_dir, palette, canvases=None, recipes=None)`: when `recipes` is a dict, after drawing each frame as today, draws it again on a fresh `Canvas` (same size, cell, box, background) with `recipe.shades()` and stores that Canvas under the same `"<folder>/<file>"` key. Legacy output is unchanged.

- [ ] **Step 1: Write failing tests** in `tests/test_recipe.py`: `test_resolve_matches_shades` (for every palette in `palettes.PALETTES`, each `Shades` field of `frames.shades(p)` equals `resolve(getattr(recipe.shades(), f), p)`); `test_mix_composes` (`frames._mix(Recipe("bar", BLACK, .7), BLACK, .5)` resolves for every palette to `frames._mix(frames._mix(bar, BLACK, .7), BLACK, .5)`); `test_recorded_frames_resolve_to_drawn` (use `make_base` from `tests/test_frames.py`; `apply(..., recipes=d)` for three palettes; every recorded canvas, with each cell resolved, equals the drawn file's pixels — compare `canvas.image()` after mapping cells through `resolve`).
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_recipe -v` → FAIL (no module).
- [ ] **Step 3: Implement** `recipe.py` and the `frames.py` changes. Canvas already stores any value per cell; don't change `Canvas`.
- [ ] **Step 4: Run** `uv run python -m unittest tests.test_recipe tests.test_frames -v` → PASS.
- [ ] **Step 5: Commit** `feat(themes): record pixel frames as palette recipes`.

### Task 2: PUT2 codec and the format document

**Files:**
- Create: `src/sync_roms/custom_themes/templates.py`, `docs/theme-options-format.md`
- Test: `tests/test_templates.py`

**Interfaces:**
- Consumes: `recipe.Recipe`, `recipe.ROLES`.
- Produces:
  - `templates.encode(width: int, height: int, pixels: list) -> bytes` — `pixels` row-major, each an RGBA tuple (fixed) or `(Recipe, alpha)`; builds the entry table (nested recipes become kind-2 entries placed before their users, deduplicated), u16 indexes when more than 256 entries (flags bit0), zlib level 9.
  - `templates.decode(data: bytes) -> (width, height, entries, indexes)`; raises `ValueError` on a bad magic.
  - `templates.render(data: bytes, colors: dict) -> (width, height, bytes RGBA)` — pure stdlib (no Pillow), `colors` `{role id: "#RRGGBB"}`; the reference the device mirrors.
  - `templates.from_canvas(canvas) -> bytes` (cells → `(Recipe, 255)`, background → its fixed colour, empty → `(0,0,0,0)`, at the canvas's pixel size, same geometry as `Canvas.image()`).
  - `templates.from_bar_image(path) -> bytes | None` — a PNG whose `recolor.BAR_GRAY` pixels become `(Recipe("bar"), alpha)` and others fixed; None when it has no bar gray.
- [ ] **Step 1: Write the doc**: the artifact's "Format contract v1" section word for word, then the five amendments from this plan's Global Constraints, marked "Amended".
- [ ] **Step 2: Write failing tests**: `test_round_trip_fixed` (4×4 image of fixed colours renders identically); `test_role_and_mix_entries` (a 2×1 template with `Recipe("bar")` and `Recipe("bar", WHITE, .35)` renders to the palette's bar and `frames._mix(bar, WHITE, .35)` for Nord); `test_nested_recipe_is_kind2` (decode shows a kind-2 entry whose `src` < its own index); `test_two_byte_indexes` (a 20×15 image of 300 distinct colours sets flags bit0 and round-trips); `test_bad_magic` raises `ValueError`; `test_from_canvas_matches_image` (a Canvas drawn with tuples equals `canvas.image()` bytes after `render`); `test_render_uses_no_pillow` (run `render` in a subprocess with `sys.modules["PIL"] = None`).
- [ ] **Step 3: Run** `uv run python -m unittest tests.test_templates -v` → FAIL.
- [ ] **Step 4: Implement** `templates.py` per the amended format (`b"PUT2"`, `<4H` header, `<BBHBHBBB` entries).
- [ ] **Step 5: Run** the tests → PASS.
- [ ] **Step 6: Commit** `feat(themes): add the put2 theme template format`.

### Task 3: Shared key tables and byte-equality for every palette

**Files:**
- Modify: `src/sync_roms/custom_themes/pixel/recolor.py`
- Test: `tests/test_templates_equality.py`

**Interfaces:**
- Produces:
  - `recolor.CONFIG_KEYS: dict[str, str]` — exactly the artifact's `configKeys` map (path syntax: dotted keys, `name[field=value]`).
  - `recolor.IGM_KEYS: dict[str, dict]` — `"colors.selection": {"role": "bar", "suffix": "FF"}`, `accent→accent`, `title_line→dim`, `text→list`, `text_selected→selected`, `text_title→text`, `battery→text`, all suffix `"FF"`.
  - `recolor.set_path(data, path, value) -> bool` (False when the path isn't there; never creates keys).
  - `recolor_config` and `igm_config` rewritten on top of these tables, same output as today.
- [ ] **Step 1: Write failing tests**: `test_recolor_config_unchanged` (for every palette, the table-driven `recolor_config` on the base test config equals a copy of the current implementation kept in the test); `test_igm_config_unchanged` (same for `igm_config`); `test_frame_templates_match_every_palette` (with `make_base`, for every palette: `frames.apply(dir_p, p, recipes=d)` on a fresh copy; each `templates.render(templates.from_canvas(d[k]), colors_of(p))` equals the RGBA bytes of the written file `k`); `test_bar_templates_match_every_palette` (for each base skin PNG with bar gray: `render(from_bar_image(gruvbox_copy))` with p equals `recolor_bar` output with p).
- [ ] **Step 2: Run** → FAIL on the missing names.
- [ ] **Step 3: Implement** the tables and `set_path`; refactor the two functions.
- [ ] **Step 4: Run** `uv run python -m unittest tests.test_templates_equality tests.test_theme_palettes tests.test_frames -v` → PASS.
- [ ] **Step 5: Commit** `refactor(themes): drive pixel colour keys from one table`.

### Task 4: The `Pixel` style with `options/`

**Files:**
- Create: `src/sync_roms/custom_themes/pixel_options.py`
- Modify: `src/sync_roms/custom_themes/__init__.py` (register in `STYLES`), `src/sync_roms/custom_themes/pixel/build.py` (pass `recipes` through `build_theme`, an optional `description`), CLAUDE.md (custom themes bullet)
- Test: `tests/test_pixel_options.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `pixel_options.STYLE = "Pixel"`, `BASE = "SPRUCE"`, `PALETTES = False`, `OPTIONS = True`, `DEFAULT_VARIANT = "consoles"`, `DEFAULT_PALETTE = "Gruvbox"`, `VARIANTS = {"consoles": ("Consoles", "CONSOLES"), "controllers": ("Controllers", "CONTROLLERS")}`.
  - `pixel_options.build(base_dir, out_dir) -> str` (the `<out_dir>/Pixel` path).
  - `build_theme(base_dir, out_dir, name, kind, palette, canvases=None, recipes=None, description=None)`.
- Build steps: build each variant in Gruvbox into a temp folder (the consoles one with `recipes=`), description `"Pixel-art consoles or controllers on black, in any palette."`; the variant files are every relative path whose bytes differ between the two builds, excluding `config*.json`; copy the consoles build to `<out>/Pixel`; write each variant's files to `options/variants/<id>/<rel>`; write `options/templates/<rel>.tpl` for every recorded frame and for every other `skin*/` PNG that `from_bar_image` returns bytes for (skip files in the variant set and files the build drew); write `options/manifest.json` (artifact schema, `formatVersion: 1`, roles from `recipe.ROLES` with capitalised names, `configKeys` = `CONFIG_KEYS`, `igmKeys` = `IGM_KEYS`, all palettes from `palettes.py` in order) and `options/applied.json` = `{"variant": "consoles", "palette": "Gruvbox", "colors": {...}}`. Never write `selected.json`.
- [ ] **Step 1: Write failing tests** (with `make_base` from `tests/test_custom_themes.py`): `test_registered_built_once` (`"Pixel"` in `STYLES`, `needs_palettes(["Pixel"])` False); `test_top_level_is_the_consoles_gruvbox_theme` (every top-level file except `config*.json`'s name/description equals a legacy `Pixel Consoles - Gruvbox` build); `test_variant_files` (both variant folders list the same paths, which include `icons/` system icons and `skin/ic-game-n.png`, and no `config*.json`); `test_applying_controllers_nord_equals_legacy` (a test-local `apply(theme_dir, variant, palette)` doing the artifact's algorithm with `templates.render` and `set_path` gives, for every file the legacy `Pixel Controllers - Nord` build has except `preview.png` and the config name/description/igm `name`, identical bytes or JSON); `test_no_template_on_a_variant_file`; `test_manifest_shape` (formatVersion 1, 6 roles, 41 palettes, `defaultPalette` Gruvbox); `test_no_selected_json`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run python -m unittest tests.test_pixel_options tests.test_custom_themes -v` → PASS.
- [ ] **Step 5: Commit** `feat(themes): build one pixel theme with variants and palettes as data`.

### Task 5: Card sync leaves device-generated files alone

**Files:**
- Modify: `src/sync_roms/spruce_themes.py` (`todo`, new helpers), CLAUDE.md (spruce_themes bullet)
- Test: `tests/test_sync_spruce_themes.py`

**Interfaces:**
- Produces: `spruce_themes.generated(rels: set[str]) -> set[str]` — given a theme's storage-relative paths, when `options/manifest.json` is among them: the variant targets (`options/variants/<id>/<rel>` → `<rel>`), template targets (`options/templates/<rel>.tpl` → `<rel>`), every top-level `config*.json`, `igm.json` and `options/applied.json`; else an empty set.
- Rule in `todo(jobs)`: group jobs by theme folder; for a theme with a manifest, when no job under `options/` (other than `applied.json`) is out of date, drop the jobs for `generated` paths whose card file exists; otherwise keep every job (full refresh, storage's `applied.json` included). Never a job or a deletion for `options/selected.json`.
- [ ] **Step 1: Write failing tests**: `test_options_theme_keeps_generated_files` (card has every file, a generated PNG and config differ from storage → no jobs for them); `test_options_change_refreshes_everything` (a changed `.tpl` → jobs for the generated files and `applied.json`, `selected.json` untouched); `test_missing_generated_file_is_copied`; `test_selected_json_never_touched`; `test_theme_without_manifest_unchanged` (a config that differs is still copied).
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_sync_spruce_themes -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sync): keep the colours a spruce card renders for an options theme`.

### Task 6: Card setting writes `options/selected.json`

**Files:**
- Create: `src/sync_roms/theme_options.py`
- Modify: `src/sync_roms/cardedit.py` (S menu row), `src/sync_roms/custom_themes/palette_picker.py` (`pick_one`), `src/sync_roms/cli.py` (call next to both `spruce_themes.select` calls), `src/sync_roms/data/cards.schema.json`, CLAUDE.md (Card fields table)
- Test: `tests/test_theme_options.py`

**Interfaces:**
- Produces:
  - Card fields `theme_options` (`{theme folder: {"variant": id, "palette": name}}`, set in the card editor) and `theme_options_written` (the same shape, what sync last wrote).
  - `theme_options.manifest(name) -> dict | None` — storage's `os/spruceos/themes/<name>/options/manifest.json` through `s3` (catching `s3.ERRORS`), None without one.
  - `theme_options.selected(manifest, variant, palette) -> dict` — `{"variant", "palette", "colors"}` (all roles).
  - `theme_options.write(card, base, names, dry_run) -> bool` — for each synced theme with a manifest and a card setting that differs from `theme_options_written`: write `Themes/<name>/options/selected.json` with `store.replace_file`/`cardfs.write_text`, record `theme_options_written` (not on a dry run, which prints what it would write); returns whether it wrote. An unknown variant or palette is warned about and skipped.
  - `palette_picker.pick_one(title, names, palettes_by_name, current) -> str | None | False` (single pick with swatches and previews; False on Esc).
  - Card editor S menu, spruce cards: `🎨 Theme options: <variant> · <palette>` per theme in `theme_options`, plus one for the card's `spruce_theme` when its manifest exists; Enter picks the variant (`picker.filter_list`) then the palette.
- [ ] **Step 1: Write failing tests**: `test_write_selected_json` (setting Nord/controllers → file content and `theme_options_written`); `test_unchanged_setting_never_overwrites_device_choice` (the card's `selected.json` holds custom colours, setting equals `theme_options_written` → untouched); `test_changed_setting_overwrites`; `test_dry_run_writes_nothing`; `test_unknown_palette_warns`; `test_theme_without_manifest_skipped`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_theme_options -v` → FAIL.
- [ ] **Step 3: Implement** module, picker, editor row, cli calls, schema, CLAUDE.md.
- [ ] **Step 4: Run** `uv run python tools/run_tests.py` → all PASS.
- [ ] **Step 5: Commit** `feat(cards): choose a spruce theme's variant and palette per card`.

### Task 7: Real-base verification

- [ ] **Step 1:** `uv run sync-roms themes build Pixel` (reads the SPRUCE base from storage; writes only `cache/themes/build/Pixel`).
- [ ] **Step 2:** A scratchpad script (not committed) builds `Pixel Controllers - Nord` and `Pixel Consoles - Synthwave` and applies those choices to a copy of `Pixel` with `templates.render`; every file except `preview.png` and the config/igm names must match. Report the `options/` size and template count.
- [ ] **Step 3:** Commit any fixes; no commit when there are none.
