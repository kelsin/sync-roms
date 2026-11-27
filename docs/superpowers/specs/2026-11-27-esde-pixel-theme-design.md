# Pixel for ES-DE: design

## Intent

The user loves the Pixel themes sync-roms builds for spruceOS (`Pixel Consoles` / `Pixel Controllers`, 35 palettes) and wants the option to use them on ES-DE too (`esde` Android cards and `emudeck`). The ES-DE version keeps the Pixel look (black background, pixel-art sprites, the palette's colours, the Fusion Pixel font) and uses ES-DE's extra room for game details.

ToTK for ES-DE is a later, separate project.

## Goals

- One ES-DE theme, **Pixel**, built by sync-roms from repo code and installed by sync next to the Art Book Next copy. The user picks it in ES-DE's own UI Settings, like any theme.
- Consoles and Controllers are theme **variants**; the 35 palettes of `custom_themes/palettes.py` are **color schemes**. Both are picked in ES-DE's UI settings.
- Layouts for every aspect ratio the `esde`/`emudeck` devices in `devices.json` need: 16:9, 16:10, 4:3, 3:2, 1:1, 8:7 (the 31:27 and 10:9 devices), and `5:3_vertical` (MagicX Zero 40, 480x800).
- **System view**: a carousel. The selected system's sprite is large on a rounded `bar`-coloured tile (like Spruce's selected main-menu item), the neighbours smaller, the system name below in `text` and the game count in `accent`. Horizontal on wide screens, vertical (top to bottom) on `5:3_vertical`.
- **Game list view**: the text list (selected row on the `bar` colour, others in `list`) beside the scraped art (miximage), the metadata labels (genre, players, release date, rating; label names in `accent`) and the description. On `5:3_vertical`: art and metadata on top, list below, no description.
- A Pixel sprite, in both variants, for **every system in `systems.json` that has an ES-DE folder**. About 20 already exist under another id (e.g. `pico8`, `atari7800`): map them. About 25 are new drawings, two each (console and pad): GameCube, Wii, Wii U, Switch, PS2, PS3, PS4, PS Vita, 3DS/New 3DS, Xbox, Xbox 360, Xbox One, 3DO, CD-i, Jaguar CD, PC-FX, 64DD, Model 2, Model 3, ST-V, NAOMI 2/GD, Triforce, Type X, Daphne, and the others the mapping step finds missing.
- Collections (custom and Surprise) get the box art (`data/themes/art-book-next/art-box/Imgs/<id>.png`, the same boxes Spruce cards get) when Pixel is ES-DE's theme, by the user's decision.

## Non-goals

- ToTK for ES-DE (next project).
- Systems ES-DE knows that `systems.json` doesn't list: never on a card.
- Changing the Spruce Pixel themes, except sharing sprites with them (new sprites may appear on Spruce too where Spruce has the system).
- Storage: the theme is never put in storage.

## Anti-goals

- New sprites that don't look like the existing set: crooked edges, off-palette colours, a different scale or style, or a real-world lookalike instead of the actual hardware.
- A slower sync: the build is cached and only redone when the code or data changes.
- Touching an ES-DE theme the user picked other than Pixel or Art Book Next.

## Constraints

- Sprites use `custom_themes/pixel/sprite.py` (named colours from `COLORS`, `render` adds outline and bevel) and follow its rules: one half drawn and mirrored, regular steps, no odd outline pixels (see also the memory "pixel sprites clean lines"). Same canvas and placement as the existing sprites (`ICON_SIZE`, `ICON_CENTER` in `pixel/build.py`).
- Each new sprite is drawn from web reference images of the real hardware (and its real controller), and reviewed against those references and a contact sheet of the existing sprites before it is accepted.
- ES-DE theme format per THEMES.md (gitlab.com/es-de/emulationstation-de): `capabilities.xml` declares variants, color schemes and aspect ratios (only the listed names: 16:9, 16:10, 3:2, 4:3, 5:3, 5:4, 8:7, 19.5:9, 20:9, 21:9, 32:9, each with `_vertical`, and 1:1). Colour schemes are sets of variables. Per-system art through `${system.theme}` / `${system.name}` variables; an unthemed system shows its full name in the carousel.
- Fusion Pixel is crisp at multiples of 12 px. ES-DE's `fontSize` is a fraction of the screen height, so pick each layout's sizes to land on multiples of 12 at the device resolutions where possible.
- Python 3.12; storage rules of CLAUDE.md (the theme never reads or writes storage).

## Approaches

1. **Built by sync from repo code (picked).** A module writes the whole theme into `cache/` and sync copies it onto `esde` cards' ES-DE folder (`themes/`), and for `emudeck` into the machine's ES-DE folder. No storage step, since everything comes from the repo.
2. Built and published to storage like the Spruce custom themes: adds a publish step and lets storage drift from code, for a theme that needs nothing from storage.
3. One ES-DE theme per palette: 70 entries in ES-DE's theme list, when colour schemes already switch palettes on the device.

## Decided

- Approach 1.
- Carousel for the system view (mockups in `.superpowers/brainstorm/esde-pixel-1.html`, carousel picked over a grid).
- Game details on the ES-DE game list.
- The 5:3 vertical layout for the Zero 40.
- Every missing sprite drawn, with web research and review, matching the existing graphics.
- **The user approves the new sprites batch by batch**: each batch (6 to 8 systems, both variants) is drawn from references, self-reviewed against them and the existing set, then shown to the user as an enlarged contact sheet next to the existing sprites; the next batch starts only after approval, and rejected sprites are redrawn first.

## My calls (correct me)

- **No new card setting.** Pixel gets its own sync step, outside the collections step: it installs and updates Pixel on every non-guest `esde`/`emudeck` sync while the card's `theme` flag is on, whatever the card's collections and whatever theme ES-DE has selected (with dry-run text, and the machine's ES-DE folder for `emudeck`). The user picks it in ES-DE.
- **Theme selection stays as today.** A new card still gets Art Book Next selected (`install_esde`'s current behaviour); sync never changes `Theme` once it is set, never selects Pixel, and never sets ES-DE's variant or colour scheme. Collection art goes into whichever of the two ES-DE uses: `esde_wanted` becomes "unset, Art Book Next, or Pixel", and the art step writes into the selected one.
- **Reuse before drawing.** A system that is the same hardware or cabinet as one already drawn reuses that sprite: `mark3` the Japanese Master System, `naomi2`/`naomigd` NAOMI, `mame-advmame` and `arcade` MAME/FBNeo, `msx2` MSX, `n3ds` 3DS, and similar. Only distinct hardware gets a new drawing (the reviewer counted about 35 systems without a sprite id before reuse).
- **ES-DE version:** current ES-DE 3.x (colour schemes, variants and font size presets all available), on Android and EmuDeck alike.
- The picked mockup (`.superpowers/brainstorm/esde-pixel-1.html`) is git-ignored; this doc's System view and Game list view goals describe it fully.
- The theme folder name is `pixel-sync-roms`, shown as "Pixel".
- Collection art in Pixel is the `art-box/Imgs/<id>.png` box art, copied as is, by the user's decision (not the 32x32 sprites).
- Game list video: not shown (keeps the look still and simple); the miximage is the picture.
- The card editor's S menu theme line is reworded to say it covers both themes.

## Left to the builder

- Exact element sizes and positions per aspect ratio (relative coordinates).
- Cache key and how the build is skipped when unchanged.
- Module layout under `custom_themes/` (an `esde/` package is suggested) and test shape (`tests/` checks of the theme XML: every system with an ES-DE folder has a sprite in both variants, every colour scheme has every variable, every declared aspect ratio has a layout).
- The order the new sprites are drawn in.
