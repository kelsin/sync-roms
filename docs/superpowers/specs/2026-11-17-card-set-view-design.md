# Card editor: view a set across systems

## Why

In the card editor (`sync-roms edit` and the editor opened during a sync, both `cardedit.edit_card`), sets are only reachable inside one system (`s` in `edit_system`). The user wants to open a set first and pick its games from every system in one list.

## Goals

- `s` in the card's system list opens a picker of the sets that have games, in storage, on systems the card can play. Each set shows how many of those games are synced (`3/12`, ✅).
- Enter on a set opens one game list over every playable system: the set's games grouped by category (file order), then system and title, labelled `System — Title` (like `edit.set_rows`).
- Toggling behaves exactly as in a system's game list: direct picks vs. set references and `excluded`, collection-locked rows, multi-disc linking, playlists hiding their discs, sizes per row and the card status (with `to_fetch` during a sync), notes (`w`), variants (`v`).
- Changes are saved to `cards.json` when the list is left (and on Ctrl-C), like `edit_system`.

## Non-goals / anti-goals

- No key that adds or removes a whole set in this view; the picker's `a` select-all is off there. Sets are for finding games.
- Games on systems the card can't play, or not in storage, are hidden.
- No metadata, past-surprise or set filters inside the set view.
- Full systems: their rows show on and locked (every file is synced already).

## Approaches

1. **Shared multi-system model (chosen).** Move `edit_system`'s per-system state (picks, set-reference coverage, exclusions, locks, groups, costs, save) into a model that can cover several systems; `edit_system` uses it for one, the set view for many. Same behaviour by construction.
2. Reuse `edit.toggle_games` (already multi-system). Rejected: no sizes, exclusions, collection locks or disc linking, so it would not work "as normal".
3. Copy `edit_system`'s logic into a second function. Rejected: two copies of the toggle rules drift.

## Left to the builder

The model's shape, how the status is summed across systems, and the test layout, following `tests/test_cardedit.py`.
