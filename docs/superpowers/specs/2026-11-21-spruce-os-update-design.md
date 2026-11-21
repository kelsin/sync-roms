# Stage spruceOS updates on spruce cards

## Intent

When syncing a `spruce` card, also put the latest spruceOS release from storage's `os/spruceos/` on it, safely: nothing important on the card is ever overwritten.

## Approaches

- **Stage the release 7z for EZ Updater (chosen).** Copy `spruceV<version>.7z` unextracted to the card root; the user runs Apps → EZ Updater on the device, which backs up settings and applies it. Nothing on the card is replaced by sync.
- **Extract the release over the card root.** Rejected: it replaces `App`, `Emu`, `RetroArch`, `spruce`, `miyoo`, `.tmp_update` and more, and spruce's own manual-update steps say to delete everything but `Roms`, `Saves`, `Persistent`, `Collections`, `Themes` and `BIOS` first, which is the opposite of "no overriding anything important".
- **Stage the `spruceOTA-*` delta.** Rejected: spruce doesn't document where it goes or how it is applied.

## Design

- Pick the newest `spruceV<version>.7z` under `os/spruceos/` in the storage inventory (`inventory.py`), comparing versions by digit runs as numbers. Ignore `spruceOTA-*` and the installers. No version in code.
- On `spruce` cards only, copy it to the card root unextracted.
- Once per version: a new card field `spruce_os` (in `cards.json` and its schema) records the 7z name sync last staged. When it equals the newest, sync doesn't copy again, even if EZ Updater has since deleted the file.
- When a newer one is staged, remove only the previous `spruce_os` file from the card root if still present. Never remove anything else.
- The copy counts toward the card's size budget like other sync writes, and shows in dry run.
- Docs: CLAUDE.md `os/` notes; the setup guide's spruce section gets an "after sync, run Apps → EZ Updater" step.

## Non-goals

Fresh installs onto blank cards, extracting, OTA deltas, detecting the installed version on the card, major-version jumps (EZ Updater doesn't support 3.x → 4.x).

## Left to the builder

Where in the sync flow this hooks in (follow how `onion_surprise.py` installs once per zip), message wording, tests for version pick, once-per-version and cleanup.
