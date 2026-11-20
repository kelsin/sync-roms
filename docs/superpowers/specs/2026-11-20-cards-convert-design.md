# `cards convert`: move a card's files to another layout

## Intent
A card already synced for one firmware layout (first case: Knulli) is being switched to another (first case: NextUI) on the
same filesystem. Re-copying every ROM from storage is slow, so rename what is already on the card into the new layout and let
the next sync fill the gaps.

## Goals
- `sync-roms cards convert NAME --layout ID [--dry-run] [--yes]` run against the mounted card (card root = the folder named NAME, as for sync).
- Preview of every rename first; nothing moves under `--dry-run`.
- Moves: system ROM folders (old layout's folder to the new one, per `systems.json` `folders`), BIOS (`bios_by_tag` aware),
  multi-disc games (`disc_folders` / `disc_dir` aware), RetroArch saves and states (reuse the naming and path logic in `saves.py`, including `save_naming`).
- After the moves, `cards.json` gets the new layout (device kept; the layout must be one the device runs).
- Works for any layout pair, not only Knulli to NextUI.

## Non-goals
- Moving files between different filesystems or reflashed/reformatted cards (nothing to move).
- Converting frontend metadata (gamelists, collections, media, themes, PICO-8/Surprise installs): the next sync writes these for the new layout. Old-layout leftovers are reported, not deleted.
- Changing `cards set --layout` (it stays a settings edit).

## Anti-goals
- Losing or overwriting a file: a destination that already exists is skipped and reported, never replaced.
- Touching anything not recognized as sync-roms content of the old layout.

## Constraints
- Systems with no folder in the new layout (`null`, e.g. 68 of 102 on Knulli to NextUI) are left in place and listed.
- Same-filesystem renames only; ROM bytes are never copied.
- Follows project rules: no new bucket layouts, no personal data in the repo, conventional commits, tests via `python -m unittest discover -s tests`.

## Approaches
1. **Explicit `cards convert` command (chosen).** Reviewable and predictable; `cards set` unchanged.
2. Fold into `cards set --layout`: one command, but a settings edit would move files and need a mounted card.
3. Sync auto-detects the mismatch and converts: no new command, but implicit and hard to preview.

## Decided with the user
- Approach 1.
- Same filesystem assumed (the user's Knulli data survives into the NextUI card).

## My calls (not yet confirmed)
- Existing-destination conflicts are skipped and reported.
- Requires confirmation unless `--yes`, like other destructive card commands.
- Saves are converted in the same run; a save whose game is not on the card is left alone.

## Left to the builder
Module placement and naming (likely a new `convert.py` plus a `cards` subcommand in `commands.py`/`cli.py`, help text, completion, README/docs), plan/apply split matching existing `plan_*` conventions, tests with temp-dir cards for Knulli to NextUI and one other pair.
