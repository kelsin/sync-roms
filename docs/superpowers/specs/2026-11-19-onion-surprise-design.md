# Onion Surprise app and surprise.json

## Why

Onion has no custom collections, so a card's surprises can't show up the way they do on ES-DE and Knulli. The separate
onion-surprise app (`~/src/onion-surprise`, installed at `App/Surprise/`) shows a list read from `Roms/surprise.json`
and launches games the way Onion does. Sync should install that app and write the list.

## Goals

- Onion cards (`onion` layout) with Surprise on get the newest Surprise app from storage and a `Roms/surprise.json` of
  the card's current surprises.
- Installing never damages the card: a bad zip changes nothing, and nothing outside `App/Surprise/` is touched but
  the app's icon, `Icons/Default/app/surprise.png`.

## Non-goals

- Allium or any other layout.
- Removing the app when Surprise is turned off.
- Building or publishing the app (onion-surprise's own release job puts `Surprise-vX.Y.Z.zip` in storage's `os/onion/`).

## Approaches

- **Newest zip by version tag (picked):** `os/onion/Surprise-v<semver>.zip`, newest by natural sort, like PICO-8.
  Untagged or `-dirty` names are ignored.
- Newest by modification time: rejected; re-copying an old zip would make it "newest".

## Design

### App install (new module, modelled on `pico8.py`)

- Key: newest `os/onion/Surprise-v*.zip` matching `Surprise-v\d+(\.\d+)*\.zip`, read through `inventory.files`.
- Runs only for `onion` cards where `surprise.enabled(entry)`. The card's `surprise_app` field records the zip name
  installed; nothing happens when it matches and `App/Surprise/config.json` and `App/Surprise/surprise` exist.
- Safe install: download to a temp file; check every member is under `App/Surprise/` with no absolute or `..` paths
  (and not a symlink), apart from the optional icon `Icons/Default/app/surprise.png` and the directory entries leading
  to it, and `App/Surprise/config.json` and `App/Surprise/surprise` are present. Any failure warns,
  counts one failure and changes nothing. Then extract to `App/.Surprise.new/`, remove `App/Surprise/` and rename the
  new folder into place; chmod the top-level `surprise` and `launch.sh` to 0755. Only then write the icon, when the zip
  has it, to `Icons/Default/app/surprise.png` on the card (parents created; only that file overwritten). Then `store.update_card(card, surprise_app=name)`.
- Dry run prints what would be installed.

### surprise.json

- Format and constraints from onion-surprise's `docs/surprise-json.md`: JSON Lines, keys `label, rompath, imgpath,
  launch, type` in that order, compact, `type` 5; no `"`, `:`, `\` or control characters (stripped from labels; an
  entry whose paths contain them is skipped); every value under 256 bytes and line under 1024 bytes (else skipped).
- Entries: the card's `surprises` (as saved now), each file of a surprise that is on the card in the system's Onion
  ROM folder. A multi-disc game is its playlist (`.m3u`), as Onion lists it.
- `launch`: read each `Emu/*/config.json` on the card; map its `rompath` (normalised, relative to the Emu folder) to
  the Emu folder; `launch` is `/mnt/SDCARD/Emu/<EMU>/<launch key>`. Several Emu folders for one ROM folder: prefer the
  one named like the ROM folder, else the first by name. No Emu folder: the game is left out.
- `rompath` `/mnt/SDCARD/Emu/<EMU>/../../Roms/<SYS>/<rel>`; `imgpath` the same with `Imgs/<stem>.png`, only when that
  file is on the card; `label` the surprise's `title`.
- Written only when the contents change; removed when there are no entries or Surprise is off. Sync owns the file.
- Dry run says whether it would be written or removed.

## Left to the builder

Where in `cli.py`'s sync the two steps run (after downloads, next to `pico8.run` / `frontend_step`), the module
name, and the test layout.
