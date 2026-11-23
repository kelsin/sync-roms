# `config apply`: settings onto a spruce card or an Android device

## Why

Settings only reach a device during a full `sync` today, and only on spruce cards. Android devices (ES-DE + RetroArch) are set up by hand from the setup guide, and the Nova already drifted from it (Cloud Sync configs on, no trailing slash on the WebDAV URL). Wireless debugging lets sync-roms write those settings over adb. Saves move to Syncthing, so RetroArch Cloud Sync is turned off.

## Goals

- `sync-roms config apply [CARD] [--dry-run] [--yes]`:
  - **Spruce card**: CARD is a card name (its folder `/Volumes/<name>`) or a folder, or no CARD and the current folder is a card's root (its basename is a saved card). Runs what sync's spruce step writes for settings: `spruce_settings.install`, `spruce_wifi.install`, `spruce_syncthing.run`.
  - **Android**: CARD names an Android card (`android.is_android`), or no CARD and the current folder isn't a card: `android.resolve` (device picker, set up, SD card, which card).
  - A mounted card of another layout, or a mounted Android card: refused, exit 2, saying what's supported (Android is applied over adb: run without a folder).
- `--dry-run` lists **every** setting `apply` would set, each with its value and whether it would change (`would set` / `already set`), secrets shown as `(hidden)`. Nothing is written. Sync's own output stays as it is.
- Android writes:
  1. RetroArch's `retroarch.cfg` (`/storage/emulated/0/Android/data/<pkg>/files/retroarch.cfg`, `pkg` from `android.retroarch_package`), after `android.wait_closed` (RetroArch has `config_save_on_exit`):
     - While `spruce_syncthing` is on: `syncthing.json`'s `retroarch` keys, and `savefile_directory` / `savestate_directory` = `android.DEFAULT_SAVES` / `DEFAULT_STATES`.
     - RetroAchievements from `spruce_ra_*`: mode `Disabled` → `cheevos_enable` false; `Casual`/`Softcore` → `cheevos_enable` true, `cheevos_hardcore_mode_enable` false; `Hardcore` → both true; `Manual` or unset → neither touched. `spruce_ra_username` → `cheevos_username`; `spruce_ra_password` → `cheevos_password`; when the username changes, `cheevos_token` is set to `""` so RetroArch logs in again.
     - Cloud Sync off, always: `cloud_sync_enable` false, `webdav_url`, `webdav_username`, `webdav_password` `""`.
  2. While `spruce_syncthing` is on: ES-DE's emulator per system for `syncthing.json`'s `cores`, as `<alternativeEmulator><label>…</label></alternativeEmulator>` at the top of `/storage/<volume>/ES-DE/gamelists/<esde folder>/gamelist.xml` (created with an empty `<gameList />` when missing; only systems whose ROM folder exists on the card). The label per core comes from ES-DE's Android `es_systems.xml`, kept in `syncthing.json` as `esde_labels` (`{core: label}`). ES-DE is the home app and always running: before writing, ask (default yes; `--yes` skips) and `am force-stop org.es_de.frontend`, then relaunch it with the HOME intent. Declining skips the ES-DE part.
  3. APKs: every `.apk` in storage's `os/android/APKs/` whose package isn't installed on the device (`pm list packages`) is installed; installed ones are left as they are (no upgrades). Sync still copies the folder to the card. Rules, in repo data `src/sync_roms/data/android-apks.json` (matched on the file name, case-insensitive prefix):
     - `dawn-zero` never.
     - `gamenative`, `DroidDeck` only on devices whose tier (`device-systems.json`) is the Retroid Pocket Nova's (`switch`) or a later one in the chain (`full` counts).
     - `Eden` only when the card's device plays `switch` (its systems after the personal overlay; `full` plays all).
     - `gba-ds` only on dual-screen devices (`screen2`; `full` counts as one).
     - `RAOfflineProxy*.apk` only when the card has RAOfflineProxy on (as sync).
     - The package name comes from the APK's binary `AndroidManifest.xml`. When the card's `APKs/` holds the same file at the same size, it is read on the device (`adb exec-out unzip -p <apk> AndroidManifest.xml`) and installed from there (`pm install <path>`, nothing sent over the network); otherwise the storage file is fetched to the temp folder (`s3.download`), read locally and installed with `adb install`. A `pm install` from the card that fails falls back to the storage copy.
     - `--dry-run` lists every APK: `would install`, `already installed` or `skipped (<reason>)`.
- Files are pulled to a temp folder, edited by pure functions on text, and only changed files are pushed back. Each write prints what it set, like sync's spruce lines.
- Setup guide: remove the Cloud saves section; the Android Syncthing steps say `sync-roms config apply` sets the RetroArch folders, save settings and ES-DE emulators. README and `cli.TOPICS` describe `config apply`.

## Non-goals

- No adb `config import` (later).
- No APK upgrades or uninstalls, no Play Store apps, no Obtainium import, no Wi-Fi, hotkeys, shaders, standalone emulator settings, Syncthing-Fork pairing.
- `spruce_settings` (PyUI preferences) and `wifi_networks` don't apply to Android; silently not applicable.
- No rename of the `spruce_*` settings.

## Anti-goals

- Never write a RetroArch config while RetroArch runs, never print a password, never overwrite a file that couldn't be parsed (warn and skip), never touch lines/entries other than the listed keys.

## Approaches

- **Chosen: stage and edit locally.** Pull `retroarch.cfg` and the gamelists into a temp folder, edit them with pure functions, push changed ones. Testable without a device, matches `android.Session` in `saves`.
- Edit in place with `adb shell sed`: quoting-fragile, untestable, rejected.
- Apply during `sync`: Android cards sync through a mounted SD card, where `retroarch.cfg` (internal storage) isn't reachable. Rejected.

## Left to the builder

- Module layout (suggested: `settings_apply.py` for the command and dry-run listing, `android_settings.py` for the Android edits). For the spruce dry-run listing, the spruce modules may grow a plan function returning every entry with old and new values, as long as sync's output is unchanged.
- cfg editing: reuse the line-replace approach of `spruce_syncthing.retroarch_writes` (keep line ends, append missing keys).
- Exit codes follow `config import` and `saves` (2 usage, 1 lost device connection).
