# Knulli settings through knulli.conf

## Why

Spruce cards get the user's RetroAchievements login, WiFi networks, hotkey scheme and preferences written by sync and
`config apply`, and `config import` reads preferences back. Knulli cards get none of that; the setup guide has manual
steps instead. This brings Knulli to the same level, without Syncthing (out of scope for Knulli for now).

## What Knulli reads

Knulli Scarab (20260511 and later) keeps its settings in `system/knulli.conf` on the SHARE partition (`/userdata`):
one `key=value` per line, `#` comments, unquoted values. Knulli's docs tell users to edit it by hand, ES rewrites only the
keys it changes, and `S26system` runs `dos2unix` on it each boot. RetroArch's own cfg is rebuilt on every launch, so
`knulli.conf` is the only place a setting sticks. Sources are in the research notes of this design's conversation
(knulli-linux `package/system/knulli-system/knulli.conf`, ES `SystemConf.cpp`, configgen `libretroControllers.py`).

Constraints:

- First boot reformats SHARE to exFAT, and `S12populateshare` copies the stock `knulli.conf` only when it is missing.
  So sync never creates the file: with no `system/knulli.conf` it warns ("boot the card once in Knulli Scarab first")
  and skips. That also covers Gladiator II and older (`batocera.conf`), which are not supported.
- Merge in place: change only the lines of keys sync wants, keep every other line, comment and order; a key not in the
  file is appended. Keep the file's line endings.

## Approaches

- **A. One module, one write (picked).** `knulli_conf.py` collects every wanted key and merges them into `knulli.conf`
  in one read and one write. Matches spruce, where all settings land in one `spruce-config.json` write; one dry-run list.
- B. One module per area (settings, wifi, hotkeys), each editing `knulli.conf`. Smaller modules, but the same file is read
  and written several times and each must preserve the others' lines.

## Keys

From the shared settings in `settings.json` (no new names):

| Setting | knulli.conf |
|---|---|
| `ra_mode` | `Manual`: nothing. `Disabled`: `global.retroachievements=0`. `Casual`/`Softcore`: `=1` and `global.retroachievements.hardcore=0`. `Hardcore`: `=1` and `.hardcore=1` |
| `ra_username`, `ra_password` | `global.retroachievements.username`, `.password` (Knulli stores it plain) |
| `ra_api_key` | `global.retroachievements.webapikey` (same 32-character check as spruce) |
| `wifi_networks` | `wifi.ssid`/`wifi.key`, `wifi2.*`, `wifi3.*` in list order; open networks get an empty key. Slots the list doesn't fill keep what the device has. More than three networks: warn and use the first three |

`ra_offline_proxy` and `ra_proxy_stats` are not written: RAOfflineProxy patches `knulli.conf` itself while it runs.
Password and API key values are never shown (like spruce's `HIDDEN`).

Hotkeys, from `data/hotkeys.json`'s scheme. Knulli already quits on hotkey + Start. Its remap keys
`global.hotkey_<default button>=<new button>` move Knulli's existing actions, so sync sets the remaps that put
menu on X, save state on R1, load state on L1, slot down/up on D-pad Left/Right and fast-forward on R2 as a toggle
(`global.toggle_fast_forward=1`). Slow motion and Show FPS have no Knulli hotkey and are left out (noted in
`hotkeys.json`'s note and the guide's Knulli hotkey table). The exact remap set, including what moves off the buttons
the scheme takes, is the builder's to derive from `libretroControllers.py`'s defaults.

Preferences: a new `settings.json` key `knulli_settings`, `{knulli.conf key: value}`, limited to the allowlist in
`src/sync_roms/data/knulli-settings.json`: the `global.*` gameplay keys (shaderset, autosave, rewind, quickresume and
similar) and the RetroAchievements toggles other than the login (`leaderboards`, `verbose`, `screenshot`,
`challenge_indicators`, `richpresence`, `encore`, `unofficial`, `sound`), plus `system.language` and `system.timezone`.
No hardware, audio, network, service or login keys. Keys outside the allowlist are ignored with a warning.

## Where it runs

- Every non-guest Knulli sync, alongside the other card steps, and its dry run.
- `config apply CARD` accepts Knulli cards (today: spruce and Android only) and runs the same merge; `--dry-run` lists
  each change with `applied.Entry`.
- `config import CARD` gets a Knulli importer: reads the allowlisted keys from the card's `knulli.conf` into
  `knulli_settings`, with spruce's Yes/No/Pick prompt.
- `config set` validates `knulli_settings` like `spruce_settings`.

## PICO-8

Unchanged: sync puts the newest zip in `roms/pico8/` once per zip and the user runs Device Settings → Install Pico-8,
which unpacks it, deletes the zip and sets `pico8.core`. New: a sync that put a new zip on a Knulli card ends with a
bold reminder to run Install Pico-8, like `spruce_os.remind`. Spruce needs no change (spruceOS reads the three files
from `BIOS/`, which sync already does).

## Docs

CLAUDE.md (settings and the Knulli layout notes), README/help for `config apply`/`import`, and the setup guide's
Knulli RetroAchievements, WiFi and hotkey steps become "sync does this" where it now does.

## Out of scope

Syncthing, per-system cores and autosave (they existed for Syncthing), OS update staging, themes, sample cleanup,
boot logos.
