# Zelda Collection Art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every collection art id gets a ToTK-style picture, and spruce cards whose `spruce_theme` is a ToTK theme get those instead of the pixel boxes.

**Architecture:** A repo tool renders the existing outline drawings (`tools/gen_theme_art.py`) onto a gold ToTK card and commits the PNGs under `data/themes/totk-james/collections/`. `themeart` chooses that folder over `art-box/` for spruce when the card's theme is ToTK; `cli.py` passes the card's `spruce_theme` in.

**Tech Stack:** Python 3.12+, Pillow, unittest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-24-zelda-collection-art-design.md`

## Global Constraints

- Always `uv run`; tests: `uv run python -m unittest discover -s tests`. Code must run on Python 3.12.
- Test modules importing `sync_roms` import `isolate` (or `helpers`) first.
- Ids: every `art.json` id plus `surprise`. Sizes: `Imgs` 336x480, `Imgs_med` 210x300, `Imgs_small` 140x200.
- ToTK themes: exactly `("ToTK", "ToTK - James")`.
- Colours: cream `(250, 247, 221)` frame and title, gold `(255, 229, 153)` lines and divider. Title text from `art.json`, `"Surprise"` for `surprise`, in the ToTK theme's `HYLIA.TTF`.
- Conventional Commits, lowercase imperative. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never write to storage; the generator only reads `/Volumes/roms/os/spruceos/themes/ToTK`.

## Review Focus

- A card with no `spruce_theme`, or a theme not in the tuple (e.g. `"ToTK - James "`, other themes): gets `art-box` art. Test in Task 2.
- Switching a card from ToTK to another theme: the next install rewrites the pictures with `art-box`'s and reports a change. Test in Task 2.
- Long titles (`Handheld Greatest Hits`, `The Legend of Zelda`, `Strategy & Tactics`-style names): shrink to fit inside the frame, never clipped. Checked on the contact sheet in Task 1.
- Wide drawings (pokemon, kart-racers, light-gun): fit inside the frame above the divider. Contact sheet, Task 1.
- Non-spruce layouts are unaffected by `spruce_theme`. Existing tests in Task 2 keep passing.

---

### Task 1: Generator and committed art

**Files:**
- Create: `tools/gen_zelda_art.py`
- Create: `src/sync_roms/data/themes/totk-james/collections/{Imgs,Imgs_med,Imgs_small}/<id>.png` (generated)
- Modify: `src/sync_roms/data/themes/totk-james/README.md`, `CLAUDE.md` (Theme art data section, next to the `art-box/` bullet; the tests line at the end of Theme art)
- Test: `tests/test_themeart.py` (class `Assets`)

**Interfaces:**
- Produces: the PNG files at `src/sync_roms/data/themes/totk-james/collections/<size>/<id>.png`. Task 2 reads them.

Reference implementation of the approved look: the spike `style_card` in `/private/tmp/claude-501/-Users-kelsin-src-sync-roms--claude-worktrees-guide-header-dropdown-layout-e66825/de72c615-08db-4161-ac8d-56060b3c69af/scratchpad/zelda_spike.py` (functions `lines`, `swirls`, `glow`, `title`, `triforce`, `divider`, `frame`, `corner_mask`, `style_card`). Port those; drop styles B and C.

- [ ] **Step 1: Write the failing test** in `tests/test_themeart.py` class `Assets`:

```python
def test_every_art_has_zelda_art_in_three_sizes(self):
    from PIL import Image
    folder = os.path.join(store.REPO_DATA, "themes", "totk-james", "collections")
    for art_id in [*themeart.art_choices(), themeart.SURPRISE_ART]:
        for size, dims in (("Imgs", (336, 480)), ("Imgs_med", (210, 300)), ("Imgs_small", (140, 200))):
            with Image.open(os.path.join(folder, size, f"{art_id}.png")) as im:
                self.assertEqual(im.size, dims, (art_id, size))
                self.assertEqual(im.mode, "RGBA", (art_id, size))
```

(Import `store` the way the module already does, if it doesn't.)

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_themeart.Assets -v`. Expected: FAIL, file not found.

- [ ] **Step 3: Write `tools/gen_zelda_art.py`**: `uv run python tools/gen_zelda_art.py [--base DIR] [--sheet] [id ...]`. `--base` defaults to `/Volumes/roms/os/spruceos/themes/ToTK` (read HYLIA.TTF there). Ids default to every `gen_theme_art.ART` key; titles from `art.json` plus `{"surprise": "Surprise"}`. `render(art_id, font_path) -> Image` (RGBA 336x480) ports `style_card`; seed every random source from `zlib.crc32(art_id.encode())` (not `random.Random(str)`) so output is deterministic. `sizes(img) -> {size: Image}` resizes with LANCZOS to the three sizes. Writes with `optimize=True`. `--sheet` also writes a contact sheet of every id it rendered to `store.cache_dir()/theme-art/zelda/sheet.png` and prints the path. Keep the `gen_theme_art` import by `sys.path` like the spike; restore `gen_theme_art.W/H/STROKE` isn't needed since the tool is its own process.

- [ ] **Step 4: Generate** `uv run python tools/gen_zelda_art.py --sheet`, then run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Review the sheet.** Read the printed `sheet.png` (and crops at 2x of any doubtful cards). Every drawing sits inside the frame above the divider, every title fits inside the frame on one line, nothing is clipped. Fix placement (scale by the drawing's bounds, cap its height so it clears the divider) and title fitting until all ids pass. Report which ids needed attention.

- [ ] **Step 6: Docs.** README: a bullet for `collections/Imgs|Imgs_med|Imgs_small/<id>.png` (ToTK-style collection art for spruce cards, from the outline drawings of `gen_theme_art.py`, regenerate with `uv run python tools/gen_zelda_art.py`; it reads HYLIA from the ToTK theme). CLAUDE.md: one bullet after `art-box/` naming the folder, sizes, generator and that sync uses it on spruce cards whose `spruce_theme` is `ToTK` or `ToTK - James`; add the Zelda sizes to the tests line.

- [ ] **Step 7: Full tests** `uv run python -m unittest discover -s tests`. Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add tools/gen_zelda_art.py src/sync_roms/data/themes/totk-james tests/test_themeart.py CLAUDE.md
git commit -m "feat(themes): add ToTK-style collection art"
```

### Task 2: Sync picks the Zelda art on ToTK cards

**Files:**
- Modify: `src/sync_roms/themeart.py` (`usable`, `install`, `describe`, near `SPRUCE_SIZES`)
- Modify: `src/sync_roms/cli.py:1560-1593` (the `themeart.describe`/`install` calls for spruce)
- Modify: `CLAUDE.md` line 204 (the Spruce part: "from `art-box/`, or `totk-james/collections/` when the card's `spruce_theme` is a ToTK theme")
- Test: `tests/test_themeart.py` (class `Spruce`), and a cli test if one already covers the spruce art call

**Interfaces:**
- Consumes: Task 1's PNGs.
- Produces: `themeart.ZELDA_THEMES = ("ToTK", "ToTK - James")`; `themeart.ZELDA_ART` (abs path of `totk-james/collections`); `usable(layout_name, arts, spruce_theme=None)`, `install(layout_name, base, arts, owned=(), spruce_theme=None)`, `describe(layout_name, base, arts, owned=(), spruce_theme=None)`. For spruce, `usable` returns `{name: <ZELDA_ART>/Imgs/<id>.png}` when `spruce_theme in ZELDA_THEMES`, else the `art-box/Imgs` path as today. `install_spruce` is unchanged (it derives the other sizes from the png's grandparent folder).

- [ ] **Step 1: Write failing tests** in class `Spruce`:

```python
def zelda(self, art_id, size="Imgs"):
    return os.path.join(themeart.ZELDA_ART, size, f"{art_id}.png")

def test_totk_cards_get_the_zelda_art(self):
    for theme in themeart.ZELDA_THEMES:
        self.assertTrue(themeart.install("spruce", self.base, SURPRISE, spruce_theme=theme))
        for size in themeart.SPRUCE_SIZES:
            with open(self.path("Surprise", size), "rb") as f, open(self.zelda("surprise", size), "rb") as g:
                self.assertEqual(f.read(), g.read())

def test_other_themes_get_the_box_art(self):
    for theme in (None, "ToTK - James ", "Art Book Next"):
        themeart.install("spruce", self.base, SURPRISE, spruce_theme=theme)
        with open(self.path("Surprise"), "rb") as f, open(themeart.art_png("surprise", "art-box/Imgs"), "rb") as g:
            self.assertEqual(f.read(), g.read(), theme)

def test_switching_theme_swaps_the_art(self):
    themeart.install("spruce", self.base, SURPRISE, spruce_theme="ToTK")
    self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
    self.assertFalse(themeart.install("spruce", self.base, SURPRISE))
```

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_themeart.Spruce -v`. Expected: FAIL (`ZELDA_THEMES`/`spruce_theme` unknown).

- [ ] **Step 3: Implement** the Interfaces above in `themeart.py`; other layouts ignore `spruce_theme`.

- [ ] **Step 4: Wire cli.py**: both spruce calls (`themeart.describe` at ~1574 and `themeart.install` at ~1591) pass `spruce_theme=entry.get("spruce_theme")` (`entry` is the card dict already used there; confirm it holds the saved card's `spruce_theme`, else use `store.saved_card(card).get("spruce_theme")`). If a cli test mocks or asserts these calls, extend it to cover the new argument.

- [ ] **Step 5: Run** the Step 2 command, then `uv run python -m unittest discover -s tests`. Expected: all pass.

- [ ] **Step 6: Update CLAUDE.md line 204** as listed under Files.

- [ ] **Step 7: Commit**

```bash
git add src/sync_roms/themeart.py src/sync_roms/cli.py tests CLAUDE.md
git commit -m "feat(sync): use the ToTK collection art on spruce cards with a ToTK theme"
```
