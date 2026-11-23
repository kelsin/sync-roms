# Theme palettes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Custom spruce themes come in 28 palettes; `themes build`/`themes publish` build every selected style in every selected palette, chosen by flags or a terminal picker with color swatch bars, and `themes palettes` opens an overview image.

**Architecture:** A `palettes.py` data module; the pixel builder takes a palette and recolors the theme config and the selection-bar gray; the registry becomes styles x palettes (theme folder `<style> - <palette>`); a sheet renderer feeds both the overview command and the picker preview; the picker is `picker.filter_list(multi=True)` with swatch parts in `extras`.

**Tech Stack:** Python 3.12+, Pillow, Textual picker already in the repo, unittest (`helpers.StorageDir`), `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-23-theme-palettes-design.md` (builds on `2026-11-23-custom-spruce-themes-design.md`, already implemented in `src/sync_roms/custom_themes/`). The spec's appendix holds the 28 palettes verbatim: use those values exactly.

## Global Constraints

- Always `uv run python ...`; tests `uv run python -m unittest discover -s tests`; Python 3.12 compatible; test output pristine (run new tests once with `-W error`).
- Storage rules from CLAUDE.md apply (confirm before deleting; storage access through `s3.py`/`inventory.py`/`shared.py`; `s3.check_root()` before treating a missing file as absent); never touch the real storage `/Volumes/roms`: tests use throwaway folders only.
- A new command/flag needs `cli.TOPICS` text, `commands.second_words`, README Options table (checked by `tests/test_readme.py`), and CLAUDE.md. Setting `custom_theme_palettes` is a list written only by the picker (like `spruce_themes`; see how README/CONFIG_KINDS/`usersettings` treat `spruce_themes`).
- Conventional Commits; each commit ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Theme folder name is exactly `<style> - <palette>` (space, hyphen, space), e.g. `Pixel Consoles - Gruvbox`.
- Publish only touches the themes it builds this run; never deletes folders of unselected palettes; old `Pixel Consoles`/`Pixel Controllers` folders are not adopted or removed.
- No pixel-art frame redraw in this plan; the bar recolor of the base gray `(80, 73, 69)` is the only frame change.

## Review Focus

- No palette selected and no terminal/`--yes`: exit 2 with the palette names, never build or publish "nothing" silently.
- Unknown `--palette` or style name: exit 2 naming the known ones; duplicate `--palette` flags collapse.
- Publishing 2 palettes: both manifest entries written; a third palette's folder in storage untouched (and its manifest entry kept).
- Palette recolor must not touch any other pixel, keep alpha, and apply to every `skin*/` PNG including the per-resolution copies; config recolor changes only the listed keys and leaves other keys intact.
- Picker: Esc cancels without saving or building; the saved selection only changes when the picker confirms; a saved name that no longer exists is dropped silently.
- The swatch bar renders a visible color on the highlighted row (verify, with a fallback if the row style overrides the background).

## File Structure

- Create `src/sync_roms/custom_themes/palettes.py`: `Palette`, `PALETTES`, `get`, `names`.
- Create `src/sync_roms/custom_themes/pixel/recolor.py`: config and bar recolor.
- Create `src/sync_roms/custom_themes/palette_sheet.py`: sheet and panel images.
- Create `src/sync_roms/custom_themes/palette_picker.py`: picker rows, swatch parts, preview paths.
- Modify `custom_themes/__init__.py`, `pixel/build.py`, `pixel_consoles.py`, `pixel_controllers.py`, `commands.py`, `cli.py`, `usersettings.py` (docstring/setting), `README.md`, `CLAUDE.md`.
- Tests: extend `tests/test_custom_themes.py` (split into `tests/test_theme_palettes.py` for new tests if it becomes unwieldy).

---

### Task 1: Palettes, recolor and palette-aware build/publish

**Files:**
- Create: `custom_themes/palettes.py`, `custom_themes/pixel/recolor.py`
- Modify: `custom_themes/__init__.py`, `pixel/build.py`, `pixel_consoles.py`, `pixel_controllers.py`, `commands.py` (`themes_build`, `themes_publish`, parsers, help), `cli.py`, `README.md`, `CLAUDE.md`
- Test: `tests/test_theme_palettes.py` (new) and updates to `tests/test_custom_themes.py`

**Interfaces:**
- Produces:
  - `palettes.Palette` (frozen dataclass: `name, text, list, selected, accent, dim, bar`, hex strings), `palettes.PALETTES: dict[str, Palette]` (28, spec order), `palettes.get(name) -> Palette` (KeyError), `palettes.names() -> list[str]` (spec order).
  - `pixel.recolor.recolor_config(config: dict, palette: Palette) -> None` (mutates), `pixel.recolor.recolor_bar(theme_dir: str, palette: Palette) -> None` (every `.png` under every `skin*/` folder: exact RGB `(80, 73, 69)` becomes the palette bar color, alpha kept).
  - `pixel.build.build_theme(base_dir, out_dir, name, kind, palette) -> str` (the existing function plus a palette; applies both recolors to the output, including per-resolution configs).
  - Style modules (`pixel_consoles`, `pixel_controllers`): `STYLE` (`"Pixel Consoles"`/`"Pixel Controllers"`), `BASE = "SPRUCE"`, `build(base_dir, out_dir, palette) -> str` writing `<out_dir>/<theme_name>/`.
  - `custom_themes.theme_name(style: str, palette_name: str) -> str`, `custom_themes.STYLES: dict[str, module]`, `custom_themes.styles() -> list[str]` sorted ignoring case, `custom_themes.build(styles: list[str] | None, palettes: list[Palette], out: str | None = None) -> dict[str, str]` ({theme name: folder}; `styles=None` = all; KeyError for an unknown style; ValueError for empty `palettes`), `custom_themes.publish(styles, palettes, dry_run=False) -> int`. `THEMES`/`names()` and the per-theme `NAME` are replaced.
  - CLI: `themes build` and `themes publish` take positional style names, repeatable `--palette NAME`, `--all-palettes`; `commands.palette_args(args) -> list[Palette]` (flags only in this task: duplicates collapse keeping first order; none given => `ui.fail(..., 2)` listing palette names and mentioning `--palette`/`--all-palettes`; unknown => exit 2 naming the known ones).

- [ ] **Step 1: Failing tests.** `tests/test_theme_palettes.py` (use `helpers`; build a mini base like the tests in `test_custom_themes.py`, with a `config.json` containing every key listed below plus an unrelated key, a `skin/bg-list-l.png` filled with `(80,73,69,255)` plus one differently colored pixel, a half-transparent `(80,73,69,128)` pixel, and a `skin_720x480/bg-list-l.png` copy):
  - `test_palettes_data`: 28 palettes, names equal the spec appendix order (first `"Gruvbox"`, last `"Monochrome"`), unique, all colors match `^#[0-9A-F]{6}$`; `get("Candy").accent == "#FF7FB8"`; `get("Nope")` raises KeyError.
  - `test_recolor_config`: after `recolor_config(cfg, get("Arcade"))`: `batteryPercentage.color`, `title.color`, `hint.color`, `currentpage.color` == text; `total.color` == accent; `grid.color` == dim; `grid.selectedcolor` == accent; `list.color` == list; `list.selectedcolor` == selected; `screensaver.widgets` clock color == selected, date == text, battery == accent; every other key unchanged (`"fontSize"`, fonts, the unrelated key); a config lacking `grid` does not raise.
  - `test_recolor_bar`: exact base gray pixels become `get("Famicom").bar` with alpha kept (the half-transparent one keeps alpha 128), other pixels unchanged, the per-resolution copy too; a non-`skin*` folder PNG with the gray is untouched.
  - `test_build_two_palettes`: `custom_themes.build(["Pixel Consoles"], [get("Gruvbox"), get("Candy")], out)` returns two entries keyed `"Pixel Consoles - Gruvbox"` and `"Pixel Consoles - Candy"`, both folders exist, their `config.json` `title.color` differ, and their `icons/sel/gba.png` are byte-identical.
  - `test_theme_name`, `test_unknown_style_raises_keyerror`, `test_empty_palettes_raises_valueerror`.
  - CLI (`commands.run([...])` with the storage-mini-base pattern of the existing `Fetch` tests): `themes build --palette Arcade --palette Arcade` builds one theme per style; `--all-palettes` builds 28 per style (patch `custom_themes.build` and assert its arguments instead of building 56); no flag exits 2 listing names; `--palette Nope` exits 2.
  - Publish: `publish(["Pixel Consoles"], [Gruvbox, Candy])` writes both manifest entries (`os/spruceos/custom-themes.json`) and both folders; a pre-existing unselected `Pixel Consoles - Mint` folder and its manifest entry are untouched; republishing uploads nothing.
  Update `tests/test_custom_themes.py` for the new registry API (`names()`/`THEMES` gone; `build`/`publish` signatures; theme names with palette suffixes).

- [ ] **Step 2: Run to verify failure.** `uv run python -m unittest tests.test_theme_palettes tests.test_custom_themes -v` Expected: FAIL/ImportError.

- [ ] **Step 3: Implement.** `palettes.py` (values verbatim from the spec appendix); `recolor.py`; `build_theme(..., palette)` calls `recolor_config` on every `config*.json` it already rewrites (after the name/author/description rewrite) and `recolor_bar` before the per-resolution handling finishes (so pre-scaled copies are covered; recolor every `skin*` folder); update the two style modules; replace the registry in `__init__.py` (`STYLES`, `styles()`, `theme_name`, `build`, `publish`, and every use of `THEMES`/`NAME` inside `publish`/`plan` code: theme names are now `theme_name(style, palette.name)`; the ownership/skip rules and manifest logic are unchanged and per theme name); CLI flags, `palette_args`, error messages (unknown style lists `custom_themes.styles()`), help text and README/CLAUDE.md updates (naming, flags, that old single-palette folders aren't adopted).

- [ ] **Step 4: Run tests** `uv run python -W error -m unittest tests.test_theme_palettes tests.test_custom_themes tests.test_readme tests.test_commands tests.test_completion -v` Expected: PASS; then the full suite once.

- [ ] **Step 5: Commit** `feat(themes): build custom themes in many palettes`

---

### Task 2: Overview image and `themes palettes`

**Files:**
- Create: `custom_themes/palette_sheet.py`
- Modify: `commands.py` (command, parser, `second_words`), `cli.py` (help), `README.md`
- Test: `tests/test_theme_palettes.py`

**Interfaces:**
- Consumes: Task 1's `palettes`.
- Produces: `palette_sheet.render_panel(palette: Palette, font_path: str | None = None) -> PIL.Image.Image` (RGB, 300x215: palette name, a "Games" title with counter, three list rows with the selection bar behind row 2 and selected text, three grid labels with the accent on the middle one, "A  Open   B  Back" hint line, six swatches text/list/selected/accent/dim/bar), `palette_sheet.render_sheet(palettes, font_path=None, columns=5) -> Image` (grid of numbered panels `"<n>. <name>"`, 8 px gaps on a `(28,28,28)` background), `palette_sheet.write_sheet(path) -> str` (all palettes, creating folders, returns the path), `palette_sheet.font_path() -> str | None` (the base theme's `nunwen.ttf` in `store.cache_dir()/themes/base/SPRUCE/` when present, else None: Pillow's default font at a readable size). CLI: `sync-roms themes palettes` writes `store.cache_dir()/themes/palettes.png`, prints the path, opens it with `webbrowser.open(pathlib.Path(path).as_uri())`, `ui.fail("Couldn't open a viewer: open the file above yourself", 1)` when it can't (like `guide_cmd`).

- [ ] **Step 1: Failing tests:** `test_render_panel_size_and_colors` (size 300x215; the pixel at the selection bar location equals the palette's bar color; the swatch row has all six colors in order); `test_render_sheet_size` (28 palettes, 5 columns: width `5*300+6*8`, height `6*215+7*8`); `test_write_sheet_creates_png` (valid PNG at the path under a temp cache dir); `test_palettes_command_opens_viewer` (patch `webbrowser.open` returning True: exit 0 and path printed; returning False: exit 1 with the message); `test_font_path_falls_back` (None when the base theme isn't cached).
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** the module and command (reuse the drawing from the reviewed mock: row heights 30 px, selection bar full width, swatches 40x12); add to `second_words()["themes"]`, `cli.TOPICS`, README rows.
- [ ] **Step 4: Run** `uv run python -W error -m unittest tests.test_theme_palettes tests.test_readme tests.test_commands tests.test_completion -v` Expected: PASS; full suite once.
- [ ] **Step 5: Commit** `feat(themes): add themes palettes to open the palette overview`

---

### Task 3: Picker with color bars, saved selection

**Files:**
- Create: `custom_themes/palette_picker.py`
- Modify: `commands.py` (`palette_args` gains the picker and saved-selection paths), `usersettings.py` (docstring/accessors for `custom_theme_palettes` like `spruce_themes`), `README.md`, `CLAUDE.md`, `cli.py`
- Test: `tests/test_theme_palettes.py`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: `palette_picker.swatches(palette: Palette) -> list[tuple[str, str]]` (six `("  ", "on <hex>")` parts in order text, list, selected, accent, dim, bar, separated so each swatch is its own column), `palette_picker.pick(title: str, chosen: list[str]) -> list[str] | None` (a `picker.filter_list(..., multi=True, initial=<chosen on>, extras=<swatches per row>, preview=<panel image path for the row>, hint=...)`: returns chosen palette names in spec order, `None` on Esc; panel previews are written once to `store.cache_dir()/themes/palette-previews/<name>.png` via `palette_sheet.render_panel`), `palette_picker.saved() -> list[str]` (the setting `custom_theme_palettes`, dropping names that no longer exist, `[]` when unset) and `palette_picker.save(names: list[str]) -> None` (through `usersettings.load_settings/save_settings`, sorted in spec order). `commands.palette_args(args)` order of precedence: `--all-palettes`; `--palette` flags; then, with a terminal and without `--yes`, the picker (starting from `saved()`; `None` => exit 0 printing a cancel line; nothing chosen => exit 2 "no palette chosen"; confirmed choice => `save`); otherwise `saved()`; empty => exit 2 listing names and options. Flags never change the saved setting.

- [ ] **Step 1: Failing tests:** `test_swatches` (six parts, each style `"on #RRGGBB"` equal to the palette color in order); `test_pick_passes_rows_and_returns_names` (patch `picker.filter_list` to capture its arguments and return states: labels are the 28 names in order with the saved ones `initial`-on, `multi=True`, extras are the swatches, `preview("0")`-style callback returns an existing PNG path; the returned names follow spec order; Esc (`None`) returns None); `test_saved_drops_unknown_names`; `test_save_roundtrip_sorted`; `test_palette_args_prefers_flags_over_saved`; `test_palette_args_uses_saved_without_terminal_or_yes` (`ui.ASSUME_YES` patched true; picker not called); `test_palette_args_none_saved_exits_2`; `test_palette_args_runs_picker_with_terminal_and_saves` (patch `ui.has_terminal` true and `palette_picker.pick`; the confirmed names are saved and returned as Palette objects); `test_palette_args_cancel_does_not_save`; and a rendering check of the swatch bar on the highlighted row: use the repo's existing picker test harness (read `tests/test_picker_session.py` for how Textual lists are driven headlessly) to render a list whose extras carry `"on #ff0000"` and assert the rendered row's segment for that part has background `#ff0000` both on a normal row and the highlighted row; if the highlighted row's style overrides it, change `swatches` to use a foreground block (`("██", "<hex>")`) and assert that instead, documenting why in the module docstring.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Follow `spruce_themes.pick` and `themes_pick` for UI and settings patterns. Document `custom_theme_palettes` in `usersettings` docstring, README Settings (a list, like `spruce_themes`, not a `config set` name: check `tests/test_readme.py` and `commands.CONFIG_KINDS` for what must stay in sync), `cli.TOPICS`, CLAUDE.md "Personal data" settings list. The preview callback must tolerate a terminal without image support (filter_list drops it).
- [ ] **Step 4: Run** `uv run python -W error -m unittest tests.test_theme_palettes tests.test_readme tests.test_commands tests.test_picker_session tests.test_completion -v` Expected: PASS; then the full suite once.
- [ ] **Step 5: Commit** `feat(themes): pick palettes in a terminal list with color bars`
