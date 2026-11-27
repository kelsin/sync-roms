# Drawing Pixel sprites for ES-DE systems

For whoever draws a console and controller sprite pair (`CONSOLES`, `CONTROLLERS`, keyed by ES-DE system name)
in `src/sync_roms/custom_themes/pixel/`. Read `pixel/sprite.py` and a neighbour in the existing set first.

## Steps

1. **Research.** Search the web for photos of the real console (front and three-quarter views) and its standard
   controller. Note the defining shapes and colours: body outline, disc or cartridge slot, logo stripe, button
   layout and button colours. Name the reference you used for each system.
2. **Colours.** Pick the closest names in `sprite.COLORS`. Add a colour only when none is close, and say so in the
   batch report.
3. **Draw** a `Sprite` sized like its neighbours: similar consoles are within 4 px of each other, and every sprite
   is about 16 to 30 px wide and tall (measure `pixel_build.systems(kind)` when unsure).
4. **Look.** `uv run python tools/esde_sprite_sheet.py NAME...` writes `cache/themes/esde-sprites.png` (under the
   data folder): per name, consoles then controllers, selected then unselected, with a reference row of eight
   existing sprites below. Read the PNG and compare with the reference photos and with that row. Redraw what
   doesn't match.
5. **Review.** A reviewer subagent checks each sprite against the reference photos and the rules below before a
   batch goes to the user. The sheet is never committed.

## Clean-line rules

- Draw one half and `mirror()` symmetric hardware, so both sides match exactly.
- Use `rrect`, `ellipse` and `line` (regular steps). Never hand-place single odd pixels on an outline;
  `render` adds the 1 px outline and the light/dark bevel itself.
- Straight and diagonal edges step in regular 1:1, 2:1 or 1:2 pixel steps; curves step evenly; no jogs or
  stray pixels. Crooked sprites are rejected.
- Use 2 to 3 tones per colour, lit from the top left, and make the sprite stand out against a dark background.
- Keep a clear border inside the sprite's grid.
- Enlarge the sheet and look at every edge before finishing.
