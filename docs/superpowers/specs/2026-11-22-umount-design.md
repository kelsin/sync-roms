# `sync-roms umount` design

## Intent

A helper to tidy and unmount an SD card without running a sync: the user picks a card from a list (disk id, size,
media name, volume names) and gets the same end-of-run tidy sync does, then the card is unmounted.

## Goals / non-goals

- Goal: pick a mounted external card, run sync's card tidy on each of its mounted volumes, `diskutil unmountDisk` it.
- Non-goals: no arguments, no new cleanup logic, no storage access, no other OS (macOS only, fails clearly elsewhere).

## Approaches

1. **Reuse `clean.py` and `flash.py`'s disk listing (picked).** The tidy is `clean.clean_dirs()` (`.metadata_never_index`,
   `.fseventsd/no_log`, `._` deletion with retries, the sudo `mdutil` offer) and the unmount is `clean.eject()`;
   `flash.external_disks` already lists external physical disks with size, name and volume names.
2. Write a separate cleaner: duplicates sync's tidy and drifts from it. Rejected.

## Design

- New module `umount.py`, `run(args)`, wired as a `commands.COMMANDS` command (`commands.build_parser`), with
  `cli.SUBCOMMANDS`/`cli.TOPICS` entries and a README Options row.
- Picker "🃏 Which card?" lists the external physical disks that have at least one mounted volume, minus the disk
  holding storage's `root` (when it is a folder on an external disk), labelled like flash's
  (`disk4  64 GB  SD Card Reader  (KNULLI, SHARE)`). It asks even with one card; none prints an error (exit 1); Esc exits 0.
- Mount points come from the `diskutil list -plist` listing (`MountPoint` of each partition / APFS volume): `flash.Disk`
  gains a `mounts` field.
- For each mount point: `clean.clean_dirs()` with `_clean_root` set to it (^C skips the tidy, as in sync), then
  `diskutil unmountDisk <disk>` through `clean.eject()`, which now reports success so `umount` exits 1 on failure.

## Left to the builder

Test layout, exact help wording.
