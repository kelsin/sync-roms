# Retro Box Art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every collection art id a retro game box picture (hand-made 32x32 pixel sprite, art title, badge) in three PNG sizes, and install those on Spruce cards in place of the 300x300 square art.

**Architecture:** Source data (sprites as text grids, a palette, a pixel font) lives in `src/sync_roms/data/themes/art-book-next/`. `tools/gen_box_art.py` draws each box at 84x120 base pixels, scales it, and writes `art-box/Imgs|Imgs_med|Imgs_small/<id>.png`, which are committed. `themeart.py` copies the three sizes to `Collections/Imgs*/` on Spruce cards.

**Tech Stack:** Python 3.12+, Pillow, unittest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-22-retro-box-art-design.md`

## Global Constraints

- Always `uv run`; code must run on Python 3.12.
- Output is deterministic: same inputs, same PNG bytes. Badge and badge colour come from `hashlib.sha256(art_id.encode()).digest()`, never `random` or `hash()`.
- No real console logos, seals, slogans or trade dress.
- Box colour per id = `ART[art_id][1]` from `tools/gen_theme_art.py` (import it; it has a `__main__` guard).
- Title = `art.json` title (`surprise`: "Surprise"), upper-cased. Never the collection's own name.
- Badges: `16-BIT`, `16 MEG`, `1-2 PLAYERS`, `1-4 PLAYERS`, `BATTERY BACKUP`, `STEREO SOUND`, `HI-SCORE`, `TURBO`, `NEW!`, `ARCADE HIT`, `PASSWORD SAVE`, `COLLECTOR'S`.
- Frame colours (C = box colour, `shade(C, f)` = each channel × f, clamped 0..255): title band and footer `#14121C`, box outline `#0C0A10`, sprite outline `#181020`, stripes `shade(C, 0.70/0.85/1.00)`, sunburst 16 rays alternating C and `shade(C, 1.18)`, spine `shade(C, 0.55)` with highlight `shade(C, 1.35)`, title lines alternate white `#FFFFFF` and gold `#FAD048`, each glyph with a 1 px `#181020` drop shadow (right and down).
- Sizes: full 336x480 (base ×4, nearest), med 210x300 and small 140x200 (from full, `Image.LANCZOS`). Mode RGB.
- Collection art is repo data; nothing goes to storage. PyUI loads only `Collections/Imgs/<name>.png` and same-named `Imgs_med/`, `Imgs_small/` PNGs.
- Review images (contact sheets) never get committed; write them to the session scratchpad.

## Review Focus

1. A three-line title (`dungeon-crawlers`, "DUNGEON CRAWLERS & ROGUELIKES") must still leave the sprite whole with its margin → Task 1 test `test_sprite_fits_under_a_three_line_title`.
2. Every title and badge character must be in the font (`&`, `'`, `-`, `!`, digits) → Task 1 `test_every_title_and_badge_renders`; Task 6 runs it across all ids.
3. A card that never had `Imgs_med/` or `Imgs_small/` gets them created; a card with the old 300x300 `Imgs/<name>.png` gets it replaced → Task 6 `test_all_three_sizes_are_written_to_a_fresh_card`, `test_old_square_art_is_replaced`.
4. An owned collection losing its art loses all three sizes, while the user's own files in any of the three folders stay → Task 6 `test_owned_collections_without_art_lose_all_sizes_and_other_files_stay`.
5. A dry run writes nothing in any of the three folders → Task 6 `test_describe_prints_and_writes_nothing`.

---

### Task 1: Box generator, font, palette and the first sprite

**Files:**
- Create: `tools/gen_box_art.py`
- Create: `src/sync_roms/data/themes/art-book-next/box-font.json`
- Create: `src/sync_roms/data/themes/art-book-next/box-palette.json`
- Create: `src/sync_roms/data/themes/art-book-next/sprites/action-classics.txt`
- Create: `src/sync_roms/data/themes/art-book-next/art-box/{Imgs,Imgs_med,Imgs_small}/action-classics.png`
- Test: `tests/test_box_art.py` (imports `gen_box_art` with `sys.path.insert(0, <repo>/tools)` like `tests/test_setup_guide.py`)

**Interfaces:**
- Produces (in `tools/gen_box_art.py`):
  - `W, H = 84, 120`; `SIZES = {"Imgs": (336, 480), "Imgs_med": (210, 300), "Imgs_small": (140, 200)}`; `BADGES` (the list above, in that order)
  - `ids() -> list[str]`: sorted `{"surprise", *art.json}`
  - `title(art_id) -> str`; `badge(art_id) -> tuple[str, tuple[int, int, int]]` (text, colour from white `#ECF0F8`, gold `#FAD048`, C mixed halfway to white)
  - `load_sprite(art_id) -> Image` (32x32 RGBA; `.` transparent)
  - `wrap(text, width=72) -> list[str]`: wraps at spaces by measured pixel width; raises `ValueError` past 3 lines
  - `layout(art_id) -> dict` with `title_band`, `picture` (x0, y0, x1, y1 inclusive, base pixels) and `sprite` (x, y of the 64x64 sprite)
  - `render(art_id) -> Image` (84x120 RGB); `sizes(art_id) -> dict[str, Image]`
  - CLI: `uv run python tools/gen_box_art.py [id ...] [--sheet PATH]` writes the three PNGs per id (all ids without arguments) and, with `--sheet`, a contact sheet of those ids' full-size boxes, 6 per row on `#24263A`, ids labelled
- Data formats:
  - `box-palette.json`: `{char: "#rrggbb"}`, `K` = `#181020` outline. At least 3-step ramps (highlight, base, shadow) for grey/steel, red, orange, gold, green, teal, blue, purple, pink, brown, skin, plus white and black. `.` is transparent and not listed.
  - `box-font.json`: `{char: [5 rows of "#"/"."]}`, each glyph 3–5 wide, advance = width + 1. Covers A–Z, 0–9, space, `&`, `'`, `-`, `!`, `:`.
  - `sprites/<id>.txt`: 32 lines of 32 palette characters; first and last row and column all `.` so the outline is never cut.

Layout (base pixels): spine x 0..4, highlight x 5. Title band y 0..`4 + 8·lines + 2`, text left-aligned at x 9 starting y 4, line height 8. Stripe lines at band bottom + 1, + 3, + 5. Footer y 108..119, badge right-aligned 4 px from the right edge at y 111. Picture area from band bottom + 7 to y 106, x 7..81. Sprite drawn at 2× (64x64), centred in the picture area; sunburst centred on the sprite and clipped to the picture area.

- [ ] **Step 1: Write the failing tests**

```python
def test_sizes_and_mode(self):
    for name, size in gen_box_art.SIZES.items():
        im = gen_box_art.sizes("action-classics")[name]
        self.assertEqual((im.size, im.mode), (size, "RGB"))

def test_render_is_deterministic(self):
    self.assertEqual(gen_box_art.render("action-classics").tobytes(), gen_box_art.render("action-classics").tobytes())

def test_badge_is_stable_and_from_the_list(self):
    self.assertEqual(gen_box_art.badge("rpg"), gen_box_art.badge("rpg"))
    self.assertIn(gen_box_art.badge("rpg")[0], gen_box_art.BADGES)
    self.assertGreater(len({gen_box_art.badge(i)[0] for i in gen_box_art.ids()}), 6)

def test_every_badge_fits_one_line(self):
    for b in gen_box_art.BADGES:
        self.assertEqual(len(gen_box_art.wrap(b)), 1, b)

def test_every_title_and_badge_renders(self):  # every character is in the font, every title wraps to <= 3 lines
    for art_id in gen_box_art.ids():
        self.assertLessEqual(len(gen_box_art.wrap(gen_box_art.title(art_id))), 3, art_id)

def test_sprite_fits_under_a_three_line_title(self):
    lay = gen_box_art.layout("dungeon-crawlers")
    x0, y0, x1, y1 = lay["picture"]
    x, y = lay["sprite"]
    self.assertTrue(x0 + 2 <= x and x + 64 <= x1 - 1 and y0 + 2 <= y and y + 64 <= y1 - 1)

def test_badge_has_a_clear_pixel_above_it(self):  # the footer's top row stays footer colour
    im = gen_box_art.render("action-classics")
    self.assertEqual({im.getpixel((x, 108)) for x in range(6, 83)}, {(0x14, 0x12, 0x1C)})

def test_sprites_have_a_clear_border_and_known_colours(self):
    for f in sorted(os.listdir(SPRITES)):
        rows = read(f).splitlines()
        self.assertEqual([len(r) for r in rows], [32] * 32, f)
        self.assertTrue(set("".join(rows)) <= set(PALETTE) | {"."}, f)
        self.assertEqual(set(rows[0] + rows[-1] + "".join(r[0] + r[-1] for r in rows)), {"."}, f)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run python -m unittest tests.test_box_art -v`
Expected: FAIL, `ModuleNotFoundError: gen_box_art`.

- [ ] **Step 3: Write the palette, the font and `sprites/action-classics.txt`**

The sprite is the mockup's diagonal sword, from the hilt at bottom left to the tip at top right: blade steel ramp with a white centre line, gold guard and pommel, brown grip, `K` outline. To see the mockup, run `uv run python /private/tmp/claude-501/-Users-kelsin-src-sync-roms--claude-worktrees-spruice-art-book-theme-a47411/bf4eb921-fa08-4f17-9617-e18840673ed2/scratchpad/mock.py <scratchpad>/mock.png` if it still exists; otherwise follow this description.

- [ ] **Step 4: Implement `tools/gen_box_art.py` to the interface above**

- [ ] **Step 5: Run the tests**

Run: `uv run python -m unittest tests.test_box_art -v`
Expected: all PASS except `test_every_title_and_badge_renders` only if a glyph is missing (fix the font).

- [ ] **Step 6: Generate and look at the result**

Run: `uv run python tools/gen_box_art.py action-classics --sheet <scratchpad>/sheet-1.png`. Read the sheet, then crop the full-size box and enlarge it 2x. Check that no badge or title touches the coloured area, that the sprite is whole and centred, and that the sunburst stays inside the picture area. The three-line title case is covered by `test_sprite_fits_under_a_three_line_title`.

- [ ] **Step 7: Commit**

```bash
git add tools/gen_box_art.py tests/test_box_art.py src/sync_roms/data/themes/art-book-next/{box-font.json,box-palette.json,sprites,art-box}
git commit -m "feat(spruce): generate retro box art for collections"
```

---

### Tasks 2–5: Sprites, in four batches

Each batch is the same task on its own ids, taken from `gen_box_art.ids()` minus `action-classics`:

- Task 2: `3d-platformers` … `final-fantasy` (the first 20)
- Task 3: the next 20
- Task 4: the next 20
- Task 5: the last 21 (ends with `zelda`)

**Files:** `sprites/<id>.txt` and `art-box/*/<id>.png` for the batch's ids.

**Interfaces:** consumes `tools/gen_box_art.py` (CLI, `--sheet`) and `box-palette.json` from Task 1. Palette colours may be added; existing ones are never changed (that would alter committed boxes).

- [ ] **Step 1: Look at each id's Outline picture** (`art/<id>.png`) to get the subject. The sprite shows the same thing, as a 16-bit game sprite would draw it: chunky, `K`-outlined, lit from the top left, 2–3 tones per colour, filling about 24–30 of the 32 pixels on its longer side. Characters keep the right form (CLAUDE.md "Subject": Pikachu has long slim ears, a head smaller than its body, a stepped tail). Colours should stand out against the id's box colour.
- [ ] **Step 2: Write `sprites/<id>.txt` for every id in the batch.**
- [ ] **Step 3: Run** `uv run python -m unittest tests.test_box_art -v`. Expected: PASS.
- [ ] **Step 4: Generate** `uv run python tools/gen_box_art.py <ids> --sheet <scratchpad>/sheet-<task>.png`. Read the sheet, then open each box enlarged. Redraw any sprite that reads poorly at the 140x200 small size, or that blends into its box colour.
- [ ] **Step 5: Hand the sheet path back to the controller.** It shows the user, who approves or names sprites to redo; redo them and repeat step 4 until they're approved.
- [ ] **Step 6: Commit** `feat(spruce): add box art sprites (batch N)`.

---

### Task 6: Install the box art on Spruce cards and retire the square art

**Files:**
- Modify: `src/sync_roms/themeart.py` (`art_png` docstring, `usable`, the Spruce section around lines 504–530)
- Modify: `tests/test_themeart.py` (`Assets.test_every_art_has_a_square_spruce_picture`, `class Spruce`)
- Delete: `tools/gen_spruce_art.py`, `src/sync_roms/data/themes/art-book-next/art-spruce/`
- Modify: `CLAUDE.md` (Theme art data list, line 183; Theme art "One picture per meaning", line 212; Checking, line 221; the Spruce collections cell and the "Theme art data" paragraph that says `Collections/Imgs/<name>.png`)

**Interfaces:**
- Consumes: `art-box/<size>/<id>.png` for every id (Tasks 1–5).
- Produces: `themeart.SPRUCE_SIZES = ("Imgs", "Imgs_med", "Imgs_small")`; `usable("spruce", arts)` returns `{name: art_png(art_id, "art-box/Imgs")}`. `install_spruce` and `describe_spruce` write and remove `Collections/<size>/<name>.png` for each size, taking each size's source from the sibling folder of the `Imgs` path. `install`'s signature and return value are unchanged.

- [ ] **Step 1: Write the failing tests** (in `test_themeart.py`; `Spruce.path(name, size="Imgs")`)

```python
def test_every_art_has_box_art_in_three_sizes(self):  # replaces the square-art test
    for art_id in [*themeart.art_choices(), themeart.SURPRISE_ART]:
        for size, dims in (("Imgs", (336, 480)), ("Imgs_med", (210, 300)), ("Imgs_small", (140, 200))):
            with Image.open(themeart.art_png(art_id, f"art-box/{size}")) as im:
                self.assertEqual(im.size, dims, (art_id, size))

def test_all_three_sizes_are_written_to_a_fresh_card(self):
    self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
    for size in themeart.SPRUCE_SIZES:
        with open(self.path("Surprise", size), "rb") as f, open(themeart.art_png("surprise", f"art-box/{size}"), "rb") as g:
            self.assertEqual(f.read(), g.read())
    self.assertFalse(themeart.install("spruce", self.base, SURPRISE))

def test_old_square_art_is_replaced(self):
    write(self.path("Surprise"), "old 300x300")
    self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
    with Image.open(self.path("Surprise")) as im:
        self.assertEqual(im.size, (336, 480))

def test_owned_collections_without_art_lose_all_sizes_and_other_files_stay(self):
    themeart.install("spruce", self.base, {"Surprise": "surprise", "Favs": "rpg"})
    for size in themeart.SPRUCE_SIZES:
        write(self.path("Mine", size), "x")
    self.assertTrue(themeart.install("spruce", self.base, SURPRISE, {"Surprise", "Favs"}))
    for size in themeart.SPRUCE_SIZES:
        self.assertFalse(os.path.exists(self.path("Favs", size)))
        self.assertTrue(os.path.exists(self.path("Surprise", size)))
        self.assertTrue(os.path.exists(self.path("Mine", size)))
```

Keep the existing `Spruce` tests, changing each to check all three sizes where it checks `Imgs`. `test_describe_prints_and_writes_nothing` also asserts that no `Imgs_med` or `Imgs_small` file appears for `Surprise`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run python -m unittest tests.test_themeart -v`
Expected: FAIL (`SPRUCE_SIZES` missing; the old art written).

- [ ] **Step 3: Implement the `themeart.py` changes to the interface above. Delete `art-spruce/` and `tools/gen_spruce_art.py`, and update CLAUDE.md.**

The CLAUDE.md text, in its own style:
- Theme art data: `art-box/Imgs|Imgs_med|Imgs_small/<id>.png` are retro game boxes for Spruce: 336x480, 210x300, 140x200, drawn by `tools/gen_box_art.py` from `sprites/<id>.txt` (32x32 pixel sprites, `box-palette.json`) with the art's title in `box-font.json` and a badge picked by the id's hash. Run it after changing a sprite and commit both.
- "One picture per meaning": `sprites/`, `art-box/` in place of `art-spruce/`.
- Checking: the tests check for a PNG in `art/`, a sprite, and the three `art-box/` sizes.
- Spruce collections: `Collections/Imgs/<name>.png`, plus `Imgs_med/` and `Imgs_small/` (PyUI reads only PNG there, never QOI), from `art-box/`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run python -m unittest discover -s tests`
Expected: OK. Also `grep -rn "art-spruce\|gen_spruce_art" src tests tools CLAUDE.md` prints nothing.

- [ ] **Step 5: Commit** `feat(spruce): install retro box art for collections on spruce cards`
