# GPU drivers on Android cards

## Why

Custom Adreno drivers, mostly Mesa Turnip builds, make emulators on Snapdragon handhelds run much better. Emulators
(Dolphin, PPSSPP, Eden, Citron, Winlator, ...) install them from a zip through their own driver manager, into the
app's private storage, so sync cannot install them. It can put the zips on the card so they are there to pick.
Drivers are loaded per app through libadrenotools: no root, and no system setting changes.

## Goals

- Every `esde` card whose device has an Adreno GPU gets every suggested driver for that GPU in a root `Drivers/` folder,
  so the user can try them all.
- Sync checks GitHub for newer releases each run, stores new ones in storage, and copies from storage to the card.
- A repo skill redoes the research and opens a PR when recommendations change.

## Non-goals

- Installing drivers into emulators, or choosing one in an emulator's settings.
- Drivers for non-Adreno devices (Mali, PowerVR, x86) or for Linux firmwares (they ship Mesa themselves).
- A separate `drivers update` command: the sync-time check covers it.

## Anti-goals

- Touching files in the card's `Drivers/` that sync didn't put there.
- A GitHub outage or rate limit failing a sync: it warns and copies what storage has.

## Approaches

1. **Check at sync time, storage as the store (chosen).** Same shape as the Art Book Next theme (GitHub → storage →
   card), but run inside sync. The user wants storage to keep every driver and the check to happen without a separate
   command.
2. Download from GitHub straight to the card: no copy in storage, a download per card. Rejected: the user wants storage.
3. A `sync-roms drivers update` command like `themes update`: rejected, the user wants the check at sync time.

## Design

### Repo data

`devices.json`: each Adreno device gets `"gpu"`, an id from `drivers.json`. Non-Adreno devices have none.

| gpu | Devices |
|---|---|
| `adreno-610` | retroid-pocket-duo-lite |
| `adreno-630` | ayn-odin |
| `adreno-650` | ayaneo-pocket-micro-2, retroid-pocket-5, retroid-pocket-flip-2, retroid-pocket-mini, retroid-pocket-mini-v2 |
| `adreno-722` | retroid-pocket-duo, retroid-pocket-duo-lite-plus |
| `adreno-730` | ayaneo-pocket-vert |
| `adreno-740` | ayn-odin-2, ayn-odin-2-mini, ayn-odin-2-portal, ayn-thor, retroid-pocket-6, retroid-pocket-nova |
| `adreno-a32` (G3x Gen 2) | ayaneo-pocket-ace, -dmg, -ds, -evo, -s, -s-mini |
| `adreno-g3-gen-3` | ayaneo-konkr-pocket-fit, ayaneo-pocket-s2, ayaneo-pocket-s2-pro |
| `adreno-830` | ayn-odin-3 |
| `adreno-a12` (G1 Gen 2) | anbernic-rg55g1, retroid-pocket-classic |
| `adreno-a22` (G2 Gen 2) | retroid-pocket-g2 |

New `src/sync_roms/data/drivers.json`:

```json
{
  "drivers": [
    {"id": "mrpurple", "name": "MrPurple Turnip", "repo": "MrPurple666/purple-turnip", "asset": "^turnip_mrpurple_.*\\.zip$"},
    {"id": "mrpurple-t19", "name": "MrPurple Turnip T19", "repo": "MrPurple666/purple-turnip", "tag": "<exact tag>", "asset": "..."}
  ],
  "gpus": {
    "adreno-650": {"name": "Adreno 650", "drivers": ["k11-turnip-24-3-r9", "mrpurple-t19", "turnip-sd865-z", "armsx2-turnip"]}
  }
}
```

- `asset` is a regex on a release asset's file name. Exactly one asset of the chosen release must match.
- With `tag`, the entry is pinned to that release and never re-checked. Without it, the entry follows the newest
  release (not draft, not prerelease unless that repo only has prereleases) that has a matching asset. One rule covers
  repos that mix several kinds of builds in their releases (K11MCH1 also posts Qualcomm packages; StevenMXZ posts the
  A6xx/A7xx and Gen8 builds in one release).
- A GPU with an empty list gets no `Drivers/` folder.

Initial picks, from OverclockedHQ's Turnip guide (verified 2026-10-30) and Joey's Retro Handhelds' Snapdragon driver
list:

| gpu | drivers |
|---|---|
| adreno-610 | none |
| adreno-630 | MrPurple T24 (pinned) |
| adreno-650 | K11MCH1 Turnip v24.3.0 r9 (pinned), MrPurple T19 (pinned), Turnip SD865 Z (AlexSanz0902/turnip-sd865-z), ARMSX2 Turnip (bmdhacks/armsx2-turnip) |
| adreno-722 | Vauzi-17/710 (regular build, not `-exp`), faux123/turnip-faux123-driver, sherft2607/turnip-adreno722-duo, ARMSX2 Turnip |
| adreno-730 | StevenMXZ Turnip (A6xx/A7xx build), MrPurple (latest) |
| adreno-740 | Balemuni Apex (Balemuni/Balemunis-Aurora), MrPurple (latest), StevenMXZ Turnip, ARMSX2 Turnip |
| adreno-a32, adreno-g3-gen-3 | K11MCH1 Turnip v26.0.0 R7 (pinned), MrPurple (latest) |
| adreno-830 | StevenMXZ Turnip Gen8, ARMSX2 Turnip |
| adreno-a12 | Qualcomm driver v819.1 from K11MCH1 (pinned; Turnip doesn't run on this GPU) |
| adreno-a22 | none |

### Storage

`os/drivers/<driver id>.zip` is that driver's current zip and `os/drivers/<driver id>.tag` its release
tag. A new release overwrites both, so nothing is ever deleted. Only sync-roms writes there, without asking (the user
asked for sync to store new drivers; the same as `themes update` replacing its archive). Reads go through
`inventory.py` like everything else; writes use `s3.put_file`/`put_text`, which keep the storage cache current.
(Builder's call: the `.zip` is written before the `.tag`, so an interrupted upload is retried next sync.)

On the card a driver is `Drivers/<driver id>-<tag>.zip` (tag made file-name safe). The id keeps names unique across
repos, the tag shows the version in the emulator's file picker, and a new release gets a new name, so the size-only
"already present" check never keeps a stale zip.

`os/drivers/` joins the prefixes `mirroring.mirror_wanted` keeps, so a mirror has them too.

### Sync

For an `esde` card whose device has a `gpu` with drivers:

1. For each of its drivers not pinned, or pinned but not yet in storage, ask GitHub for the release
   (`/repos/{repo}/releases` or `/releases/tags/{tag}`). Reuse `themeart._github`, moved somewhere shared.
2. If the release tag differs from storage's `.tag`: download the matching asset to a temp file, check it is a
   readable zip, upload the `.zip`, then the `.tag`. With `--dry-run`, only report.
3. Any GitHub or network error, or no matching asset: warn with the driver name, keep storage's copy.
4. Copy each driver's zip into `<card>/Drivers/<driver id>-<tag>.zip` through the existing download plan (sizes,
   "already present", the summary: `🎮 Drivers: N to download (size), M already present`). A zip uploaded in step 2 is
   copied to the card from its temp file, so a mirror refreshed before the sync doesn't need it yet.
5. Remove zips in `Drivers/` that the card's `drivers` list in `cards.json` names but that are no longer current
   (an older tag, or a driver no longer suggested), then save the list of current names. Files sync never put there
   are never touched.

Write access is checked before asking GitHub anything: on S3, whether the write profile exists (as `sync-roms config`
already checks); a storage folder is writable as it is. Without it, sync skips the GitHub check with one dim line and
copies what storage already has, so users without write access never download zips they can't store.

### Repo skill

`.claude/skills/refresh-drivers/SKILL.md`, run on request ("refresh the driver recommendations"):

1. Read `drivers.json` and the `gpu` fields in `devices.json`.
2. Redo the research: the guides above and any newer ones, each repo's releases page (still active? renamed? asset
   names still match?), and Adreno devices in `devices.json` without a `gpu`.
3. Update the data: picks, pins, asset regexes, `gpu` fields. Same rules as this design: every suggested driver,
   pins only where a guide names a specific build.
4. Run `python -m unittest discover -s tests`.
5. If anything changed: a branch off `main`, a Conventional Commit (`chore(drivers): ...`), push, and a PR whose
   body lists each change with its source. If nothing changed, say so and open nothing.

### Docs

CLAUDE.md's data files table gains `drivers.json` and the `gpu` device field; README describes `Drivers/`.

### Tests

- `drivers.json` is valid: every gpu's driver ids exist, every device `gpu` exists, regexes compile.
- Release picking: pinned vs newest-with-matching-asset, no match, more than one match.
- Sync-time update with a faked GitHub: new tag uploads and deletes the old zip, same tag does nothing, an error keeps
  the stored copy, dry run writes nothing.
- Card cleanup removes only names sync recorded.

## Left to the builder

- Exact tags and asset regexes for each entry, checked against each repo's real releases.
- Where the shared GitHub helper lives.
