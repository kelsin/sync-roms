# Pixel theme previews

## Why

The Pixel themes' `preview.png` (`pixel/build.py` `preview`) is a sheet of icons on black: it shows neither the
palette nor what the main screen looks like. The palette picker and `themes palettes` draw a separate list mock
(`palette_sheet.render_panel`) with no sprites. One image should show both, everywhere a preview is shown: on the
device's theme picker, in `themes pick`, the palette picker and the palettes sheet.

## Goals / non-goals

- Goal: one 640x480 image per (style, palette) that reads as the theme's main screen in that palette.
- Goal: the same renderer for the built theme, the palette picker and the palettes sheet.
- Non-goal: a pixel-accurate PyUI screenshot. It is a mock.
- Anti-goal: needing a built theme to draw it (the picker runs before any build).

## Approaches

- **Chosen: draw from code.** `preview_image(kind, palette, font_path)` renders the sprites (`menu.SPRITES`, the
  style's `game` sprite, `systems(kind)`, `ui_status.ICONS`) with `sprite.render` and draws text with the palette.
  Works before a build, so every place uses it.
- Rejected: compose from a built theme's files. Only possible after a build, so the picker would keep its own mock.

## Design

640x480 on black, text in the base theme's font (`nunwen.ttf`; Pillow's default font when missing):

- top bar: a wifi and a battery icon from `ui_status.ICONS`, top right;
- main menu row: Favorites, Games, Apps, Settings (`favorite`, the style's `game`, `app`, `setting` sprites);
  Favorites selected: its `sel`-state sprite and label in `selected` on a `bar` box; the others `n` sprites with
  `dim` labels;
- below: three game-list rows (middle one on `bar` in `selected`, others in `list`), and beside them three system
  icons from `systems(kind)`, one selected;
- bottom: a thin strip of the six palette colors (text, list, selected, accent, dim, bar).

Uses:

- `build.preview(dest, spec)` writes it as the theme's `preview.png`, with the theme's own `nunwen.ttf`.
- The palette picker draws it for `CONSOLES` (palettes aren't tied to a style).
- `palette_sheet` uses it at half size (320x240) per panel, five per row, with the caption kept; `render_panel`
  is replaced and its tests updated.

Tests: size 640x480, the palette's `bar` and `selected` present at known spots, swatch strip colors, a build writes
it, sheet size from the new panel size.

## Left to the builder

Exact coordinates, label sizes and which three system icons/game names to show.
