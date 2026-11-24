# `cards install`: a fresh firmware install on a card

## Why

To set up a new device, I flash TF1, may convert a TF2 card from another firmware (`cards convert --layout spruce`),
then want the firmware itself put on the card. The card's ROMs, BIOS and saves stay; everything else from the old
firmware goes, and the release is unpacked fresh.

## Goals

- `sync-roms cards install [CARD] [--dry-run] [--yes]`: card picked like `cards convert` (`saves.card_setup`: a
  card name/path, else the current folder). What gets installed comes from the card's layout; only `spruce` is
  supported now, others exit 2 with a clear message.
- Spruce: the newest `os/spruceos/spruceV<version>.7z` (`spruce_os.PATTERN`, `inventory.newest`).
- Kept at the card root: `Roms/`, `BIOS/`, `Saves/` (convert moves saves and states into `Saves/saves/`,
  `Saves/states/`), the theme folders in `Themes/` whose name storage's `os/spruceos/themes/` has
  (`spruce_themes.available()`, case ignored), and OS/filesystem folders (`.Spotlight-V100`, `.Trashes`,
  `.fseventsd`, `System Volume Information`, `._*`). Everything else at the root is deleted, and the other
  `Themes/` entries.
- Unpack with 7z's skip-existing mode (`-aos`): outside the kept folders everything is new from the 7z; inside them
  the card's files win.
- Progress bars with speed and time left like the rest of the tool: the download (`downloads.run_downloads`), the
  deletion (count bar, like convert's) and the unpack (7z's percent via `external.run_tool`, a `ui.ProgressBar` by
  the 7z's unpacked size).
- `--dry-run`: lists the 7z, what would be deleted (per root entry, with sizes where cheap) and kept; downloads,
  deletes and writes nothing.
- Confirm before deleting (`ui.confirm`); `--yes` skips it; no terminal and no `--yes` exits 2.
- After success: `store.update_card(card, spruce_os=<7z name>)` so sync doesn't stage it, and drop records of files
  that lived in replaced folders: `spruce_themes_installed` filtered to the kept theme folders, `boot_logos` cleared.
- Help (`cli.TOPICS`), completion (`commands.second_words`), README options.

## Non-goals

- Other firmwares (the layout switch is where they'd go later).
- Picking a disk from a list (flash's picker); the card is a saved card folder.

## Approaches

1. **Delete then unpack onto the card with `-aos` (picked).** One 7z pass, the card's merged files win for free.
2. Unpack to a temp folder, then copy with per-folder rules: twice the I/O and temp space, more code.
3. Unpack with overwrite (`-aoa`) into kept folders: would replace a converted card's `Saves/spruce` config and
   BIOS files with the release's; skip-existing is what "merge" means here.

## Order

1. Resolve card, layout (spruce), newest 7z; exit 1 if storage has none.
2. Plan deletions; print kept and deleted. Dry run stops here.
3. Check free temp space for the 7z (as flash does) and card space for the unpacked size minus what deletion frees.
4. Download the 7z to a temp folder (progress bar).
5. Confirm, delete (progress bar), unpack (progress bar), remove the temp folder (always, in `finally`).
6. Update the card record; print a green done line pointing at a sync.

Downloading before the confirm means a failed download never leaves a half-wiped card.

## Left to the builder

Module name (`install.py` with the spruce part beside `spruce_os.py`), exact messages, exit codes matching convert
(1 declined, 3 failures).
