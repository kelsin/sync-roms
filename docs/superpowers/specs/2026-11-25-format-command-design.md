# `format` command

Intent: erase an SD card as exFAT or FAT32 with a chosen volume label, as safely as `flash` writes one.

- `sync-roms format [--dry-run]`, macOS only, in a new `format.py` reusing `flash.py`'s helpers (`disks_of`, `external_disks`, `_disk_label`, `_same`, `_run`, `_sudo`, `HINT`). No shared-module refactor.
- Flow: pick SD card (boot disk, temp folder's disk and storage's disk excluded, stop if they can't be told) → pick filesystem (exFAT, FAT32) → pick label → warning and type the disk id to confirm (`--yes` never skips it; `--dry-run` stops after the confirm and prints the command) → the card must still be the same disk → `diskutil eraseDisk ExFAT|FAT32 <LABEL> MBR <disk>` (MBR: handheld bootloaders) → the card stays mounted.
- Label picker: the card names from `cards.json` (sorted, unique), then every layout name in `layouts.json` uppercased, then `✏️ Type a label…`. FAT32 uppercases and allows 11 characters, exFAT 15; labels too long are left out of the list; a typed label that's empty, too long or has characters FAT doesn't allow is asked again.
- Wiring: `commands.COMMANDS` and parser, `cli.TOPICS`/`SUBCOMMANDS`, README Commands row and section, tests for the label list, label validation and the built command.

Approaches: reuse flash's helpers (picked); a shared `disks.py` for both commands (rejected: unrequested refactor).
