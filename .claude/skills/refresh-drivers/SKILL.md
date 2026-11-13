---
name: refresh-drivers
description: Use when asked to refresh, update or check the driver recommendations, or whether the turnip drivers (custom Adreno GPU drivers) are still current. Re-researches the suggested drivers and opens a PR if the data changed.
---

# Refresh driver recommendations

Drivers are loaded per app through libadrenotools (no root, no system change), so only Adreno devices matter. Data: `src/sync_roms/data/drivers.json` (`drivers`, `gpus`) and the `gpu` field of Adreno devices in `src/sync_roms/data/devices.json`. Follow CLAUDE.md (Conventional Commits, squash merge, no AI attribution in commits or PR bodies, no notes about the bucket's contents in repo files).

1. **Read** `drivers.json` and the `gpu` fields in `devices.json`.
2. **Research again**:
   - https://overclockedhq.com/guides/gpu-drivers-turnip
   - https://www.joeysretrohandhelds.com/resources/best-custom-drivers-for-snapdragon-devices/
   - newer guides found by search
   - each driver's repo: `gh api "repos/<repo>/releases?per_page=100"`. Is it still active or renamed, do asset names still match, does each pinned tag still exist?
   - Adreno devices in `devices.json` without a `gpu`.
3. **Update** picks, pins, asset regexes and `gpu` fields. Rules:
   - Suggest every driver a guide recommends for a GPU, not just one.
   - Pin a `tag` only where a guide names a specific build; otherwise leave it unpinned.
   - An unpinned entry uses the newest non-draft release that has exactly one matching asset (prereleases only as a fallback), from releases fetched with `per_page=100`. So each `asset` regex must match exactly one asset of the intended release; more than one is an error.
   - Every `gpus` driver id must exist in `drivers`, and every device `gpu` in `gpus`.
4. **Test**: `python -m unittest discover -s tests` must pass.
5. **Ship**: if `git diff` is empty, say nothing changed and open nothing. Otherwise: update `main`, branch `chore/refresh-drivers-YYYY-MM-DD` off it, commit `chore(drivers): refresh driver recommendations`, push, and `gh pr create` with that title and a body listing each change and its source. Merge is a squash.
