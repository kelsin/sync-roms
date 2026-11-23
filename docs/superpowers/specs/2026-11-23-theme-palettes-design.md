# Theme palettes: pick them in `themes build` and `themes publish`

Builds on `2026-11-23-custom-spruce-themes-design.md` (the registry, `themes build`, `themes publish`, the manifest).

## Intent

The user wants every custom theme in many color variants and to choose which ones to build and publish, from a terminal UI that shows each palette's colors. They reviewed 28 palettes in a mock-up sheet and want all of them kept. They also want a command that opens that overview image.

## Goals

- A palette is data: a name and six colors (text, list, selected, accent, dim, bar). All 28 from the reviewed sheet are kept, in that order: Gruvbox, Arcade, Candy, Mint, Game Boy, Pocket, Virtual Boy, Famicom, NES, SNES, Genesis, Dreamcast, PlayStation, Neo Geo, PICO-8, Commodore, Amber CRT, Green CRT, Nord, Dracula, Solarized, Synthwave, Sunset, Ocean, Sakura, Forest, Grape, Monochrome (hex values as in the reviewed sheet; kept in one module `src/sync_roms/custom_themes/palettes.py`).
- A built theme is one style (Pixel Consoles, Pixel Controllers) in one palette. Theme (folder) name: `<style> - <palette>`, e.g. `Pixel Consoles - Gruvbox`.
- `themes build` and `themes publish` take `--palette NAME` (repeatable), `--all-palettes`, and the existing positional style names. With a terminal and no palette flag, a multi-select picker opens listing every palette with a color bar and (in terminals that draw images) a preview image; the chosen set is saved as the setting `custom_theme_palettes` (a list of names) and is the picker's starting selection next time. With `--yes` or no terminal and no flag, the saved selection is used; none saved means exit 2 naming the options.
- `sync-roms themes palettes` writes the palette overview image (`store.cache_dir()/themes/palettes.png`, generated from the palette data, so it never goes stale) and opens it in the default viewer (like `sync-roms guide`).
- Each palette changes: every `config*.json` color of the base theme (text colors, list and grid colors, total counter, screensaver clock/date/battery), and the base theme's selection-bar gray `(80, 73, 69)` in the skin images (bar fill) and their pre-scaled copies.

## Non-goals and anti-goals

- No pixel-art redraw of the frames (list/grid/popup/loading bar) in this round: that is a separate design that will use these palette colors. The bar recolor above is the only frame change here.
- Publish never deletes the folders of palettes that aren't selected this run (it only touches the themes it builds). Folders left over from the earlier single-palette themes (`Pixel Consoles`, `Pixel Controllers`) are not adopted or removed; they stay until the user deletes them.
- No per-palette art changes (icons are the same in every palette).
- No palette editor.

## Constraints from the codebase

- The picker is `picker.filter_list(title, labels, multi=True, initial=..., extras=..., preview=...)`: `extras` are `(text, style)` parts per row, `preview` returns an image path (drawn only where the terminal shows images, never in tmux). A color bar is a part per swatch with a Rich style (`"on #RRGGBB"`); the style is joined with the row's own style, so it must be checked on the highlighted row.
- Settings: `custom_theme_palettes` joins `settings.json` (CLAUDE.md "Personal data"); `tests/test_readme.py` compares README Options/Settings with the parsers and `commands.CONFIG_KINDS`; it needs its own save path like `spruce_themes` (a list chosen in the UI, not a `config set` name).
- Everything from the first spec still applies (storage rules, cache folders, determinism, the manifest, publish safety).

## Approaches

1. **Themes generated as style × palette, palette chosen at build/publish time (chosen).** The registry holds the styles; a palette parameter produces `<style> - <palette>` themes, each its own folder in storage and its own manifest entry. Fits "PyUI has one config per theme"; reuses build, publish and the manifest unchanged.
2. A palette switch inside one theme folder. Rejected: PyUI reads one `config.json` per theme; nothing in the Theme Design Guide describes switching palettes in a theme.
3. Palette baked into the theme module code, one module per palette. Rejected: 56 modules for data.

## Design

- `palettes.py`: `Palette` (frozen dataclass: `name`, `text`, `list`, `selected`, `accent`, `dim`, `bar`; hex strings), `PALETTES: dict[str, Palette]` in sheet order, `get(name)`.
- Registry: each style module exposes `STYLE` (e.g. `"Pixel Consoles"`), `BASE` and `build(base_dir, out_dir, palette)`. `custom_themes.theme_name(style, palette)`, `custom_themes.styles()`, `build(selected_styles, palettes, out)` and `publish(selected_styles, palettes, dry_run)` take palettes explicitly; `names()` lists style names only. The earlier `THEMES[name]` registry keyed by theme name is replaced by `STYLES`.
- `pixel/build.py`: `build_theme(base_dir, out_dir, name, kind, palette)` applies the palette: config colors (every `config*.json`: `batteryPercentage`, `title`, `hint`, `currentpage` colors = `text`; `total` = `accent`; `grid.color` = `dim`, `grid.selectedcolor` = `accent`; `list.color` = `list`, `list.selectedcolor` = `selected`; screensaver clock = `selected`, date = `text`, battery = `accent`) and recolors the bar gray in every PNG of `skin*/` that has it (kept exact-pixel, alpha kept). The sprites stay identical across palettes; each theme is built in full (a shared per-style template is a later optimization).
- `palette_sheet.py`: renders the overview image (a grid of panels like the reviewed sheet: name, a list screen using the palette colors, swatch row; Pillow, using the base theme's font when present else Pillow's default) and `picker_preview(palette)` image per palette (a single panel).
- CLI (`commands.py`): `themes palettes`, and `--palette`/`--all-palettes` on `themes build` and `themes publish`; shared helper `choose_palettes(args) -> list[Palette]` (flags, else picker, else saved selection, else exit 2). `custom_theme_palettes` is saved from the picker only. Unknown palette names exit 2 naming the known ones.
- Docs and tests: README Options rows and a short paragraph; `cli.TOPICS`; CLAUDE.md (setting, module, naming); tests: palette module (28 palettes, unique names, valid hex), config recolor (every listed key follows the palette; unlisted keys untouched), bar recolor (exact color replaced, other pixels untouched, pre-scaled copies too), `theme_name`, build for two palettes writes two folders with different configs and identical icons, publish for two palettes (two manifest entries, unselected palette's folder untouched), `choose_palettes` (flags, saved selection, none saved exits 2, picker result saved) and the picker's color-bar extras (hex background style on each swatch part), sheet image size and non-empty, `themes palettes` opens the viewer (webbrowser patched).

## Left to the builder

Exact config key names present in the real base `config*.json` (the base has per-resolution configs; apply to all), the sheet's layout details, picker column layout, how the picker verifies the color-bar rendering, setting-save mechanics (follow `themes pick`), help text wording.

## Appendix: the 28 palettes (verbatim)

Order: text, list, selected, accent, dim, bar. Use these values exactly.

```python
# name: (text, list, selected, accent, dim, bar)
PALETTES = {
 "Gruvbox":      ("#EBDBB2","#FBF1C7","#FBF1C7","#D65D0E","#7C6F64","#504945"),
 "Arcade":       ("#F6F3FF","#A9ABC4","#FFD43F","#FFD43F","#62647F","#342E78"),
 "Candy":        ("#F6F3FF","#C9B8E8","#FF7FB8","#FF7FB8","#6A5C8F","#4A2F6B"),
 "Mint":         ("#F6F3FF","#9FD8D0","#4FE0CF","#43C8F0","#4B6F72","#1F4A52"),
 "Game Boy":     ("#9BBC0F","#8BAC0F","#E0F8D0","#E0F8D0","#306230","#306230"),
 "Pocket":       ("#E8E8E0","#B8B8B0","#FFFFFF","#FFFFFF","#707068","#484840"),
 "Virtual Boy":  ("#FF3030","#B02020","#FF8080","#FF8080","#601010","#400808"),
 "Famicom":      ("#F1E4C3","#D8C9A3","#FFFFFF","#EE4B3F","#8C5B3C","#A3303F"),
 "NES":          ("#E8E8E8","#B0B0B0","#FFFFFF","#EE4B3F","#707070","#8B2A2A"),
 "SNES":         ("#E4E0F4","#B7B0D8","#FFFFFF","#A66BE2","#6D668F","#5B50D8"),
 "Genesis":      ("#F6F3FF","#9A9BB5","#FFFFFF","#EE4B3F","#4A4C66","#1F3F9E"),
 "Dreamcast":    ("#FFFFFF","#C7D0DA","#FFFFFF","#F7992A","#6A7788","#E06A10"),
 "PlayStation":  ("#E8ECF2","#AEB6C4","#FFFFFF","#43C8F0","#68707F","#35507A"),
 "Neo Geo":      ("#FFD43F","#E8C23A","#FFFFFF","#EE4B3F","#8C7A25","#3A2A00"),
 "PICO-8":       ("#FFF1E8","#C2C3C7","#FFEC27","#FF77A8","#5F574F","#1D2B53"),
 "Commodore":    ("#A0A0FF","#7C70DA","#FFFFFF","#7C70DA","#4A3FA0","#352879"),
 "Amber CRT":    ("#FFB000","#CC8C00","#FFD060","#FFD060","#6B4A00","#3A2800"),
 "Green CRT":    ("#33FF33","#22C022","#B8FFB8","#B8FFB8","#0F6B0F","#083A08"),
 "Nord":         ("#ECEFF4","#D8DEE9","#FFFFFF","#88C0D0","#4C566A","#434C5E"),
 "Dracula":      ("#F8F8F2","#BDC0D4","#FFFFFF","#FF79C6","#6272A4","#44475A"),
 "Solarized":    ("#EEE8D5","#93A1A1","#FDF6E3","#B58900","#586E75","#073642"),
 "Synthwave":    ("#F6F3FF","#C8A8F0","#FF4FD8","#2DE2E6","#6A4C93","#3A1C71"),
 "Sunset":       ("#FFE8D6","#F2C4A0","#FFFFFF","#FF8C42","#8A5A5A","#6B2D5C"),
 "Ocean":        ("#E0F4FF","#9CCFE8","#FFFFFF","#3DB5FF","#4A7088","#14405E"),
 "Sakura":       ("#FFF0F5","#F4C7D8","#FFFFFF","#FF7FB8","#9A6B80","#7A3A5A"),
 "Forest":       ("#E8F4DC","#A8D08D","#FFFFFF","#FFD43F","#5E7F4A","#2D5A2D"),
 "Grape":        ("#F0E6FF","#C4A8F0","#FFFFFF","#FFD43F","#7A5CAE","#5B2A9E"),
 "Monochrome":   ("#FFFFFF","#BBBBBB","#FFFFFF","#FFFFFF","#666666","#333333"),
}
```
