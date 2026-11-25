# Android bezels on esde cards

## Why

The MagicX Zero 40 (Android, `esde` layout) has a 480x800 portrait screen, so it needs bezels made for that screen: RetroArch overlays (GB, vertical arcade) and a DraStic NDS background. They're kept in storage; syncing a card should put them on it so they're there on the device without copying by hand.

## Goals

- `esde` cards whose device has bezels in storage get them in a `Bezels/` folder at the card root, on every sync.
- `config apply` points RetroArch's overlay folder at the card's `Bezels/retroarch/` over adb, so RetroArch's Overlay Preset picker opens there.

## Non-goals

- Turning overlays on or writing per-core/per-game overrides (viewport, which preset): the user picks those in RetroArch.
- Setting up DraStic: its background picker only reads its own `backgrounds/` folder, chosen in the app. The user copies `Bezels/drastic/nds.png` there once on the device.
- Other layouts (spruce, knulli, ...).

## Approaches

1. Copy only: files on the card, the user points RetroArch at them by hand.
2. **Copy, and `config apply` sets RetroArch's overlay folder (picked).** Same copy, plus one retroarch.cfg key the user would otherwise set by hand.
3. Push into internal storage over adb: needs the device plugged in for every change and duplicates what the card already holds.

## Design

- **Storage:** `os/android/bezels/<device id>/`, any files and subfolders, copied as they are. The existing `os/android/bezels/zero40/` is renamed to `os/android/bezels/magicx-zero40/` (a storage move, done once by hand with the user's OK).
- **Sync** (`cli.py`, next to the APK and driver jobs): for an `esde`, non-guest card, every file under `os/android/bezels/<card's device id>/` is a job to `<card>/Bezels/<relative path>`, through `downloads` like the APKs (unchanged files skipped), shown in the download summary with the other card extras. Files no longer in storage are left on the card, as with `APKs/`. `runtime.BEZELS_PREFIX = "os/android/bezels/"`.
- **Local mirror** (`mirroring.py`): keeps `os/android/bezels/` like the APKs.
- **`config apply`** (`android_settings.cfg_wanted`): when storage holds bezels for the card's device, add `overlay_directory = "/storage/<volume>/Bezels/retroarch"`. Listed with the other retroarch.cfg entries, so `--dry-run` shows it.
- **Setup guide:** a "Bezels" section, shown for an `esde` device that has bezels in storage, with the on-device steps: RetroArch (Quick Menu → On-Screen Display → On-Screen Overlay: Display Overlay on, Overlay Preset from `Bezels/retroarch/`, opacity 1.00; Video → Scaling: Integer Scale off, Aspect Ratio Custom, a Custom Viewport that fits the game in the bezel's open area; save a Core Override, or a Game Override when the bezel is for some of a core's games, such as vertical arcade games) and DraStic (copy `Bezels/drastic/*.png` into DraStic's `backgrounds/` folder; in a game, Menu → Edit Screens and Virtual Pad → the portrait layout → Set background image, then place the screens around the image's divider and save). Which devices have bezels is storage content, so it never goes in the repo: `guide_cmd` fills a `bezels-data` block (like `cards-data`) with the device ids that have a folder under `os/android/bezels/` (empty when storage can't be read: the guide still opens), and the page's `matches` gets a `bezels: [true]` filter.
- **Docs:** CLAUDE.md's setup guide section (the new filter and block), CLAUDE.md's storage table (`os/` row) and "What sync puts on a card"; `cli.py`'s sync and `config apply` help text where it lists what Android cards get.
- **Tests:** sync puts a device's bezels under `Bezels/` on an esde card and not on a guest card, another device's or a non-esde card; `cfg_wanted` adds `overlay_directory` only when the device has bezels.

## Left to the builder

Exact function boundaries, and how `config apply` learns the card's device id (from the saved setup it already loads).
