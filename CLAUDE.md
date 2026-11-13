# sync-roms

Tooling for syncing ROMs to and from the `roms.valefor.com` S3 bucket (region `us-east-1`).

## AWS profiles

Always pass `--profile` explicitly.

| Profile | Use for |
|---|---|
| `roms-readonly` | Anything that only reads: `ls`, `cp` from the bucket, `sync` from the bucket, `head-object` |
| `roms` | Anything that writes: `cp`/`sync` to the bucket, `rm`, `mv` |

Default to `roms-readonly`. Only use `roms` when a write is actually needed, and confirm with the user before any command that deletes or overwrites (`rm`, `mv`, `sync --delete`).

**Never put backup or test files in the bucket.** No `.bak` copies, scratch uploads, or test objects under `roms.valefor.com`. Keep those local.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org) for every commit and for PR titles: `<type>[scope]: <description>` (`feat`, `fix`, `refactor`, `docs`, `chore`, ...), imperative and lowercase. Merge PRs with squash so the PR title becomes the commit message on `main`.

## Bucket layout

Top-level prefixes are one per system, lowercase (`BIOS/`, `gba/`, `genesis/`, `dreamcast/`, `mame/`, `atari2600/`, ...). List them with:

```bash
aws s3 ls s3://roms.valefor.com/ --profile roms-readonly
```

## Common commands

```bash
# List a system
aws s3 ls s3://roms.valefor.com/gba/ --profile roms-readonly

# Download one file
aws s3 cp s3://roms.valefor.com/gba/game.zip . --profile roms-readonly

# Download a system (bucket -> local)
aws s3 sync s3://roms.valefor.com/gba/ ./gba/ --profile roms-readonly

# Upload (local -> bucket) -- needs write profile
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms

# Preview any write first
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms --dryrun
```

## Data files

Only one bucket layout is supported; don't add support for others. The bucket name is not hardcoded: it is the `bucket` setting in `~/.sync-roms/settings.json`, asked for on first run. BIOS files always live at `BIOS/<file>` in the bucket, so the path is derived, never stored. Whether a file exists comes from listing `BIOS/`.

BIOS lists in `systems.json` cover every emulator a system can use (default and alternate libretro cores, standalone emulators), not just the default one. These files are small, so users get all of them all the time. Don't trim a list down to the default emulator's needs. Redundant extras that no emulator needs (e.g. a dozen regional dumps of one PS1 BIOS) are not kept.

The old single `roms.json` is split by whether the data is personal. Nothing here is read from or written to the bucket.

| Where | Files | Holds |
|---|---|---|
| Repo, `src/sync_roms/data/` | `layouts.json`, `systems.json`, `devices.json`, `device-systems.json`, `ratio-systems.json`, `drivers.json` | Frontend folder layouts; systems (name, id, folder per layout, required BIOS filenames, `rom_files` (BIOS files from `BIOS/` that are copied into the system's ROM folder, by file name, e.g. MAME-style BIOS zips), libretro cores, optional `screenscraper` system id, native aspect `ratio`); device hardware (id, name, SoC, `screen` ratio and optional `screen2` for a second screen, the firmwares it runs, the first being its default; Adreno devices also a `gpu` id); suggested Adreno GPU drivers (`drivers.json`: `drivers` of id, name, GitHub `repo`, `asset` regex that must match exactly one asset of the chosen release, optional pinned `tag`; `gpus` of gpu id to name and driver ids; no `tag` means the newest non-draft release, prereleases as fallback; sync keeps each driver's zip and `.tag` in storage's `os/drivers/`, written by sync only, and `esde` cards get them as `Drivers/<id>-<tag>.zip`, refreshed with the `refresh-drivers` skill); each device's recommended systems and a short note on why (`device-systems.json` is an ordered chain of tiers: the first lists its systems, each later one only `add`s to the tier before it; a device names its tier and only sets `note` when it differs; loaded lists come out in `systems.json` order). Same for everyone. `ratio-systems.json` holds per-ratio overrides and a `dual_screen` list; a device's highlighted systems are those matching its `screen` ratio (exact string), the overrides and, with `screen2`, the dual-screen list, limited to what it can play; the personal overlay never changes them. |
| `~/.sync-roms/` | `cards.json` (per card: device, layout and its `games`; also `surprise`, false when Surprise is off, and `surprises`, `[{"system","bucket","title","files"?}]`), `surprises.json` (history of picks: system, bucket, title, card, ISO date; pruned past `surprise_ttl_days`, default 183, on write), `device-systems.json` (optional overlay), `collections/<id>.json` (one per collection) | Each card's games to sync per system (with their notes). `--edit` edits a card's games. A list may also hold `"sets": [set ids]` to sync whole sets (live references). A system's entry in a card's `games` may be `{"full_system": true}` instead of a list to sync its whole bucket folder; no card uses it by default. The overlay is `{device id: {"add": [...], "remove": [...]}}` of system ids, applied to the repo defaults; notes always come from the defaults. A collection file is `{"name", "description"?, "games"}` like a set file but with its own loader and schema, and never lives in the repo or storage. A card's `collections` (top level of the card) lists collection ids synced whole; `excluded` never applies to them. `frontend_collections` lists the names sync wrote to ES-DE/Knulli, so only those files are touched. A card's `drivers` lists the `Drivers/` zip names sync put on the card; only those are removed when they go stale. |

`ignored.json` at the root of storage (`{system folder: [ROM paths]}`) lists ROMs sync-roms never shows, syncs, uploads or scrapes; it is shared, not personal. `ignore.py` reads it once per run when its storage tag (ETag, or `<mtime_ns>-<size>` in a storage folder) differs from the copy in `~/.sync-roms/ignored.json`, and `scrape review` adds to it. `inventory.py`'s reads and `store.listed` leave ignored ROMs out, so nothing above them sees them; ROM files are never deleted. Non-game scrape results wait for review in `~/.sync-roms/scrape-notgames.json` (personal).

Editors and new game titles name MAME and FBNeo sets through `names.title`: the `clones.json` name for a set in a family, else the scraped `name` from `scrapes/<system>/metadata.json`, else the file name. `names.py` keeps the scraped names in `~/.sync-roms/names.json` with each metadata file's storage tag and rereads one only when its tag changes, from storage itself (never the mirror). Sync's own paths (`store.set_games`) keep file names.

What storage holds (keys, sizes, a bucket's ETags) is read only through `inventory.py`, from `~/.sync-roms/storage-cache.json` (built by `sync-roms cache update`, patched by sync-roms's own writes in `s3.py`); never call `s3.list_sizes`/`stat_sizes`/`list_with_etags`/`list_folders` from elsewhere. Only file contents come from storage.

There is no personal core list: a card's `games` is the only games list, and a card with no picks syncs no games. An old `~/.sync-roms/games.json` is left on disk and never read. Old personal sets in `~/.sync-roms/sets/` are left on disk and never read; sets only come from the repo. `device-systems.json` is a shared default read from the repo (never copied); users adjust it with the optional add/remove overlay. Never put a real game list in the repo.

`src/sync_roms/data/themes/art-book-next/` holds the Art Book Next collection art (`art/<id>.png`: `surprise` plus the ids listed in `art.json`, which a collection picks with `"art"`; every set has art under its id, and `tools/gen_theme_art.py` draws them all, following the rules under Theme art below) and the logo font's outlines (`logo-font.json`, OFL). Sync copies them into the card's copy of the theme (ES-DE; the theme itself is a GitHub archive in storage's `os/esde/themes/`, refreshed by `sync-roms themes update`) or theme customizations (Knulli).

Games in a set file may have an optional `category` string; the set editor groups rows by it (in file order). Prefer one set with categories over several related top-level sets (e.g. `shmups.json`: Touhou, Psikyo, Cave, Other).

Repo files must not contain notes about the bucket's contents ("not in the bucket", "bucket has..."). Device notes say only why the systems were chosen, concisely.

## Theme art

Rules for changing or adding a picture in `tools/gen_theme_art.py` (run it with a Python that has Pillow: `python tools/gen_theme_art.py [id ...]`). The reference is the theme's own Outline set, `_inc/systems/artwork-outline/*.png` in the archive in storage's `os/esde/themes/`: steady off-white lines about 6px wide with a slightly rough edge, corners joined, shapes closed, nothing drawn through a shape in front of it.

Lines:

- No wobble. Never add drift, jitter or varying thickness to "look hand-drawn"; it reads as loose and messy. The rough edge in `_ink` is the only texture.
- Every line end must land on another stroke, run off the band, or be an obviously free mark (impact dashes, a motion trail, a dashed path). An end that stops a few units short of an outline, or pokes past it, is the main thing that looks messy.
- Don't hand-pick the point where a detail meets a curved outline. Draw the detail too long inside `with p.inside(shape):` and it is cut at the outline.
- Overlap is drawn back to front: the shape in front gets `opaque=True` and hides what is behind it. Don't leave gaps in the back shape by hand, and never let lines cross through a front shape.
- A line may end on a straight edge at computed coordinates, but stay clear of that edge's rounded corners (the corner radius, in units, from each vertex).
- Prefer `arc`, `rounded` polygons and `mirror` of one half over a closed `spline` through a few points, which comes out lumpy. Use `spline` for open curves and for outlines with ten or so evenly spaced points.
- Close shapes. An open-ended fin, flame, cuff or body looks unfinished.

Size and placement:

- Drawings live in a box of about -50..50 units, y down, 3.3px per unit; the stroke is about 1.8 units wide, so keep parallel lines and small details at least 5 units apart. A solid dot is two small concentric circles (radius about 2.2 and 0.8).
- The band is slanted and about 340px wide where the picture sits, and `CENTER` is right of its middle. A picture wider than about 75 units runs off the band's right edge, and that look is wanted: the theme's own pictures are cut off on the right, and about 30 of ours lose 10 to 40px there. Don't move or shrink a picture to keep it whole on the right; give a wide one 10 to 20px of cut rather than letting it just touch the edge. Use a smaller `scale` and a negative x offset in `ART` only when more than about 40px would go, and keep the left edge clear.

Subject:

- One picture per meaning. Before adding one, check `art.json` for an entry that already means the same thing (a genre and a set of the same genre, two kinds of fist). If two exist, ask which to keep; the kept picture goes under the set's id, and the other id is removed from `ART`, `art.json`, `art/` and the tests.
- Draw the thing from the games, not a real-world lookalike: a console light gun (long thin barrel, boxy body, cable), not a pistol.
- A series may get its character when asked. Get the proportions of the right form: Pikachu has long slim ears with a short tip band, a head smaller than its chubby body, small solid eyes and a large stepped tail; wide triangular ears on a big head is Pichu.
- When asked to redo a picture without a subject, say which subject was chosen. When two concepts are equally plausible, show both and let the user pick.

Checking:

- Never finish without looking at the result. Read the generated PNG (the drawing is in y 600..1050), and also crop that part and enlarge it 2x to check every join, line end and overlap.
- Compare with the pictures next to it in a contact sheet of all of `art/`, and show the user that sheet or the changed pictures. Keep review images out of the commit.
- `python -m unittest discover -s tests` checks that every `art.json` id and every set has a PNG.

## Devices

`anbernic-rg-sp` ("Anbernic RG SP") is Anbernic's newer, separate device. It is not the RG35XX SP or the RG34XX SP, which are their own entries.

## Notes

- Use `--dryrun` before any `sync` to the bucket; add `--delete` only when explicitly asked.
- Keep the trailing `/` on prefixes so `sync`/`ls` target the directory, not a name prefix.
