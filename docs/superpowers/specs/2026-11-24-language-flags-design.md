# Language flags on game lists

## Intent

See at a glance, on every list of games, whether a game can be played in English.

## Goals

- A flag column on each game row in the editors, based on the file name's tags.
- The parsing of tags shared by Surprise and the editors, so there's no duplication.

Non-goals: flags in printed CLI file lists (`diff`, `upload`), flags in sets or storage data.

## Approaches

1. **Picked:** a new `languages.py` module holds the region and language tag parsing, moved out of `surprise.py`, plus `flag(key)`. Surprise and the editors use it, and the editors show the flag as a row column (picker `extras`).
2. Put the flag in the row label. Rejected because the `/` filter would match it and the columns wouldn't line up.

## Design

- `languages.py`:
  - `REGIONS`, `ENGLISH_REGIONS` and `LANGUAGE` move here from `surprise.py`.
  - `english(name)` returns True, False, or None when there's no tag. A `[T-En…]` translation counts as English. Then come the language tags (`(En,Fr)`), then the region tags.
  - `flag(key)` takes a bucket key and returns:
    - 🇺🇸 when the game is English.
    - Otherwise the flag of the first non-English language tag (`Ja` 🇯🇵, `Fr` 🇫🇷, `De` 🇩🇪, …), else of the first region (`Japan` 🇯🇵, `Korea` 🇰🇷, …, `Asia` 🌏).
    - "" when there's no tag, or the tag isn't in the map.
- `surprise.is_candidate` uses `languages.english(stem) is not False`, so a ROM with no tag is still a candidate (as today). The behaviour change: `(Japan) [T-En …]` ROMs become Surprise candidates.
- Card editor (`cardedit._row_extras`): a flag column before the size column.
- `edit.toggle_games` (set and collection game lists, add-from-system and add-from-set lists): `extras` with the flag column.
- Set editor's "Change a game's category" and "Set a game's series" pickers: the flag column too. The two near-identical blocks become one helper.
- The column is the same `("  " + flag, "dim")` part everywhere, built by one helper.

## Left to the builder

- The exact language-to-flag and region-to-flag maps: the common tags in storage (Ja, Fr, De, Es, It, Nl, Pt, Sv, Ko, Zh and the regions in `REGIONS`), each to its obvious flag.
- Tests: `english`/`flag` cases (language tag, region, translation, no tag, mixed), Surprise's existing tests still passing, and a translated ROM becoming a candidate.
