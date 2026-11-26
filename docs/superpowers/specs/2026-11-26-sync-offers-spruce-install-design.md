# Sync offers to install spruceOS on a card that lacks it

## Why

A new spruce card needs `sync-roms cards install` before its first sync, and that line is easy to forget. Sync should
offer it.

## Design

- After `choose_card_setup` in `cli.sync_card`, when the layout is `spruce`, the card isn't a guest card, the folder is
  a mounted card root (`install._mounted`) and any of `spruce/`, `App/`, `Emu/` is missing at the card root, sync
  prints that spruceOS isn't on the card and asks to install it now (default yes).
- Yes: the same flow as `cards install` (download, test, list kept/deleted, confirm, unpack, record `spruce_os`), then
  the sync goes on with the saved card reloaded.
- No, `--yes`, `--json` or no terminal: never installs (it deletes files); prints a one-line hint naming
  `sync-roms cards install <card>` and goes on.
- `--dry-run`: says it would offer the install.
- The offer doesn't depend on the card having no picks: the install keeps `Roms/` and asks first, and picks made with
  `sync-roms edit` before the first sync are normal (my call).
- `install.run`'s body becomes `install.install_card(base, name, dry_run, yes)`, used by the command and by sync.

## Approaches

- **Sync offers it (picked):** covers every way a card is first synced, setup prompt included.
- `cards new` offers it: misses cards set up by the sync's setup prompt, the common path.

## Not in scope

Other layouts; reinstalling over a card that has spruceOS.
