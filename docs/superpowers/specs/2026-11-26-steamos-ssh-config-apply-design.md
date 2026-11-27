# SteamOS setup: `config push` and `config apply` for EmuDeck

## Intent

Set up a Steam Deck or Steam Machine (EmuDeck, the `emudeck` layout) so its RetroArch saves and states sync cleanly with the user's Syncthing server and its other devices, with the same settings as everywhere else. sync-roms runs on the device itself (as EmuDeck syncs already do: they write the gamelists of the local ES-DE). The Mac sends it the user's personal settings and collections over SSH with one command. The setup guide gets full directions, from turning on SSH to checking that saves sync.

Why: SteamOS devices are the only ones with Syncthing in the guide but no automation, and their guide steps are generic ("Install Syncthing").

## Goals

- **`sync-roms config push USER@HOST`** (run on the Mac) copies over SSH:
  - `settings.json` without the storage and machine-local keys (see below), merged into the device's own `settings.json` so the device's own values for those keys stay. Written mode 600.
  - `collections/`: the device's collections are made to match the Mac's (new and changed copied, ones the Mac doesn't have removed).
  - It prints what changed (keys added, changed and removed; collections added, changed and removed; secrets never printed) and supports `--dry-run`.
- **`sync-roms config apply`** on the device, for an `emudeck` card, applies everything needed for clean Syncthing use:
  1. **RetroArch** (`retroarch.cfg` of EmuDeck's RetroArch): `retroarch.json` settings, `syncthing.json`'s `retroarch` keys (saves and states sorted by core, not in the content folder, the autosave interval), auto save/load, RetroAchievements from `ra_*`, Cloud Sync off.
  2. **Cores**: ES-DE's alternative emulator per system from `syncthing.json`'s `cores`/`esde_labels`, so every device uses the same core and so the same per-core save folder.
  3. **Syncthing**: uses the Syncthing already on the device, whatever installed it; installs one only when there is none. Adds the server device and the `saves`/`states` folders (ids from `syncthing_server`) at RetroArch's real save and state folders, with `modTimeWindowS` 2, through the REST API.
  4. **Things that would break clean sync**, each warned about:
     - EmuDeck's own Cloud Saves on, since it writes to the same folders;
     - a RetroArch per-core override that sets the save or state folder.
  - `--dry-run` lists every setting, changed or not, and writes nothing.
- Works for both `steam-deck` and `steam-machine` cards.
- Guide: full SteamOS directions (below).

## Non-goals

- Hotkeys: Steam Input and EmuDeck own the controller mapping on SteamOS.
- Existing saves: never moved or listed, even ones the per-core sorting hides (the same as spruce and Android).
- Standalone emulators' saves (PCSX2, Dolphin, ...): only RetroArch saves and states sync, as on the other devices.
- Bezels, APKs, RAOfflineProxy, GPU drivers.
- Pushing cards, tags or scrapes: the device makes its own card on its first sync, and tags and scrapes come from storage.
- Windows or generic Linux PCs.

## Anti-goals

- **Only one Syncthing, and never ask the user to uninstall or undo anything.** An existing Syncthing (Flatpak such as SyncThingy, a Decky plugin, a binary anywhere) is used as it is.
- `config push` never sends or changes `bucket`, `root`, `endpoint`, `profile` or `write_profile`. The device gets its storage settings from its own first-run prompt.
- No `sudo`, and nothing written outside the user's home and the Emulation folder.
- Nothing installed on the Mac.
- Secrets (RetroAchievements password, ScreenScraper password, Syncthing API key, WiFi passwords) never printed.

## Constraints

- Python 3.12 compatible; tests isolated with `isolate`; no real SSH or Syncthing in tests.
- `config push` uses only the system `ssh`/`scp` (`subprocess`) with `BatchMode=yes` and a connect timeout, so a missing key fails fast instead of prompting.
- New command and flags go through `commands.build_parser`, `cli.TOPICS`, `cli.SUBCOMMANDS` and `commands.second_words`; the README tables match (`tests/test_readme.py`).
- CLAUDE.md is updated for the new command, `config apply`'s `emudeck` support and the guide.

## Approaches

The user first picked running `config apply` on the Mac and doing everything over SSH (stage files on the Mac, reach Syncthing through `ssh -L`), over an sshfs mount (needs macFUSE) and over copying a helper script to the device. They then changed this to the current approach, which they judged best:

- **sync-roms on the device, settings pushed from the Mac (picked).** EmuDeck sync already runs on the device, `config apply` becomes local file edits that reuse the Android helpers as they are, an existing Syncthing is easy to find locally, and only the small `config push` uses SSH.
- Everything over SSH from the Mac: no install on the device, but a whole SSH transport to build and test, and EmuDeck card syncs still need sync-roms on the device anyway.

## Design

### `config push`

- Keys never sent: `bucket`, `root`, `endpoint`, `profile`, `write_profile` (storage, by the user's decision), and `mirror`, `eject`, `storage_cache_declined` (paths and answers that belong to the Mac; builder's call, marked here as such).
- The device's data folder: `store.data_dir()` worked out on the device (`$XDG_DATA_HOME/sync-roms`, else `~/.sync-roms`) by reading `XDG_DATA_HOME` over SSH.
- Reads the device's `settings.json` (when present), merges it (the device keeps its own values for the keys never sent, takes the Mac's for every other key, and loses keys the Mac doesn't have, except those never sent), and writes it with a temp name then `mv`, so a dropped connection never leaves half a file; then `chmod 600`.
- Collections the same way, file by file.
- No terminal or `--yes` needed: it only changes the device's copies of the user's own data, and it shows what it did.

### `config apply` for `emudeck`

- `settings_apply.run` routes a card whose layout is `emudeck` to a new `steamos_settings.apply`. It runs locally: the card's folder is the folder that holds `Emulation/` (as for sync).
- Paths: RetroArch config `~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg` (EmuDeck's Flatpak RetroArch; missing: warn and skip); ES-DE gamelists from `frontend.esde_dir("emudeck", base)`, skipped with the `frontend.emudeck_problem` reason when this ES-DE doesn't serve the card.
- RetroArch: `android_settings.cfg_wanted` is split so SteamOS gets everything except the hotkeys, the overlay folder and `savefile_directory`/`savestate_directory` (EmuDeck's folders stay; they are what gets shared). RetroArch must be closed (`pgrep`): wait for it with a prompt, as on Android; without a terminal, fail.
- ES-DE: `esde_wanted`/`gamelist_apply` as on Android. ES-DE rewrites gamelists when it exits, so when it is running, ask before writing (declining skips the ES-DE part).
- Save and state folders are resolved to their real paths (`os.path.realpath`), since Syncthing doesn't follow symlinks and EmuDeck links `Emulation/saves/retroarch/*`.

### Syncthing on the device

Only while `spruce_syncthing.enabled()`.

- **Finding one:** a running `syncthing` process, or the config of a known install: `~/.local/state/syncthing/config.xml`, `~/.config/syncthing/config.xml`, and the same paths under each Flatpak app's `~/.var/app/<app id>/` (builder: list the app ids of the Flatpak and Decky Syncthings to check). Its `config.xml` gives the GUI address, whether TLS is on, and the API key. `android_syncthing._api` is made to take http or https.
- **Flatpak sandbox:** when the found Syncthing is a Flatpak that can't see the save folders (`flatpak info --show-permissions`), `config apply` adds `flatpak override --user --filesystem=<folder>` for them (no sudo) and says to restart that app.
- **Installing one when none is found:** download the newest `syncthing-linux-amd64-v*.tar.gz` (arm64 on arm64) from `github.com/syncthing/syncthing` releases, check it against the release's `sha256sum.txt`, put the binary in `~/.local/bin/`, install the tarball's `etc/linux-systemd/user/syncthing.service` with `ExecStart` pointing there, then `systemctl --user enable --now syncthing`. Game Mode is an autologged-in user session, so the service runs there (builder: confirm on SteamOS). The binary is never replaced afterwards (Syncthing updates itself).
- **Configuring:** wait for the API to answer, then `android_syncthing.plan` with the resolved folder paths (it gets a parameter for them instead of `folder_paths(srv)`'s Android defaults) and the same REST calls.
- A device already set up by hand: the server and folders already there are left as they are, as `plan` does today.

### Guide (`setup-guide.html`, platform `steamos`)

A SteamOS section, in order:

No steps for setting up SSH: the user's SSH access is set up separately (Tailscale) and is out of scope; the guide only says `config push` needs SSH access to the device.

1. On the device: install uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`), then `uv tool install git+https://github.com/kelsin/sync-roms`.
2. On the Mac: `sync-roms config push USER@HOST` (again after changing settings or collections; collections are made on the Mac only).
3. On the device: the first `sync-roms` asks for storage and sets up the card (device and layout `emudeck`), then syncs.
4. With RetroArch closed: `sync-roms config apply` on the device: what it sets.
5. Server UI: accept the new device and tick `ra-saves` and `ra-states` on its Sharing tab.
6. After an EmuDeck update or "reset configuration", run `config apply` again.

The Syncthing section's "Desktop" subsection keeps only `windows`; "Pair and share" no longer applies to `steamos`; the Flatpak `~/.var` note goes. `tests/test_setup_guide.py` must pass.

### Tests

- `config push`: keys never sent stay out and the device's values for them stay; merge and removal; collections matched; temp-then-`mv`; dry run writes nothing; secrets not printed. `subprocess` mocked.
- `config apply` for `emudeck`: on a temp home with a fake EmuDeck tree: entries on dry run; only changed files written; missing cfg skipped; RetroArch running; ES-DE running and declined; real paths through symlinks.
- Syncthing: an existing install found at each known path (and a Flatpak override added when needed); install only when none; http and https API; folder paths are the resolved ones.
- Warnings: Cloud Saves on, a per-core override setting the save or state folder.

## Left to the builder

- Module split (for example `config_push.py`, `steamos_settings.py`, `steamos_syncthing.py`).
- The fake device tree and transport used in tests.
- Guide wording and placement within the order above.
- Exact paths that need checking on a current SteamOS and EmuDeck (marked above).
