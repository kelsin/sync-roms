# Card editor: keep what's on the card (`k`)

## Intent
During sync, files already on the card that aren't in the card's picks are offered for deletion. A key in the card editor's system list adds those that match storage ROMs to the picks, so they stay.

## Goals
- `k` on the system list scans every system's ROM folder on the card and picks each file that matches a storage key (path compared as `downloads.find_extras` does: `rom_rel`, case and Unicode form left out).
- Skips full systems and games already synced (direct pick or set) and excluded ones stay excluded-aware: an excluded match is un-excluded and picked, since the user is asking to keep it.
- Reports how many card files were picked in how many systems. (An unmatched-files count was dropped: it can't agree with `find_extras`; the delete prompt lists the real extras.)
- Saves through `CardPicks`; the list recounts sizes (`changed = ALL`).

## Non-goals
- Standalone `--edit`: no card path there, so `k` appears only in the editor opened by sync.
- No change to the delete prompt or `--no-delete`.
- No new data format.

## Approaches
1. `k` in the system list, all systems at once (chosen by the user).
2. An "add these instead" answer in the delete prompt (declined).

## Left to the builder
Multi-disc keys (`disc_dir`), and the hint/help text.
