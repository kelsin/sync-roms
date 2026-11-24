# Zelda collection art for ToTK spruce cards

## Why

Spruce cards using the ToTK themes show the pixel box art (`art-box/`) for collections, which clashes with the theme's dark Zonai-swirl cards, cream frames and HYLIA lettering. Every collection (the 81 `art.json` ids and `surprise`) gets a picture in that style.

## Goals, non-goals

- Goal: a ToTK-style picture for every art id, in Spruce's three sizes, chosen automatically on ToTK cards.
- Non-goal: new drawings. The pictures reuse the outline drawings of `tools/gen_theme_art.py`.
- Non-goal: other layouts or other themes. ES-DE, Knulli, ROCKNIX and muOS keep the art they get today.
- Anti-goal: a new per-card setting the user has to keep in step with the theme.

## Approaches

1. **Follow the card's theme (picked).** Sync copies the Zelda art when the card's `spruce_theme` is a ToTK theme. No new setting, and switching the theme in the S menu switches the art. Limit: a theme picked on the device itself isn't seen.
2. A per-card setting in the S menu. Works with any theme, but it's one more choice to keep in step by hand.
3. Ship the art inside the theme. PyUI reads collection pictures from `Collections/Imgs*/` on the card, not from the theme, so this would need a spruce fix. Ruled out.

## Design

- **Look (style A, "Card"):** 336x480 with rounded corners (transparent outside them); a near-black background of Zonai concentric-ring clusters; a cream (250, 247, 221) rounded frame; the outline drawing in gold (255, 229, 153) with a soft warm glow, centred in the upper part; a gold divider line with a small Triforce; the title from `art.json` (`Surprise` for `surprise`) in the theme's HYLIA font, cream, shrunk to fit.
- **Generator:** `tools/gen_zelda_art.py [id ...]` reads HYLIA from the ToTK theme in storage (like `gen_totk_james.py`; `--base DIR` to override), imports the drawings and `_ink` from `gen_theme_art.py`, and writes `src/sync_roms/data/themes/totk-james/collections/Imgs|Imgs_med|Imgs_small/<id>.png` (336x480, 210x300, 140x200, matching `art-box/`), deterministic per id. `--sheet` writes a contact sheet to the cache for review, never the repo. The output is committed.
- **Sync:** `themeart` picks the Zelda folder instead of `art-box` for Spruce when the card's `spruce_theme` is `ToTK` or `ToTK - James` (one tuple in code). `install_spruce` already writes by content, so a theme change swaps the pictures on the next sync, and `describe_spruce` reports it in a dry run.
- **Tests:** every `art.json` id and `surprise` has all three sizes, at the right size; a ToTK spruce card gets the Zelda files and any other theme (or none) gets `art-box`'s.
- **Docs:** CLAUDE.md's Theme art data section and `totk-james/README.md` (generator and credits) mention the new folder.

## Left to the builder

The exact placement, glow strength and title fitting, judged on the full contact sheet; how the theme is passed into `themeart.install`/`describe`.
