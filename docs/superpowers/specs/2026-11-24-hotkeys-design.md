# One hotkey scheme: spruceOS's defaults, Start quits

## Intent

The same RetroArch hotkeys on every device, set by sync-roms wherever it can reach the config, so nothing is bound by hand on spruce cards or Android devices. The scheme is spruceOS's defaults (the user's main devices need the fewest changes) with one change: quit is hotkey + Start instead of hotkey + B.

| Action | Hotkey + |
|---|---|
| RetroArch menu | X |
| Save state | R1 |
| Load state | L1 |
| Slot − / + | D-pad Left / Right |
| Fast-forward (toggle) | R2 |
| Slow motion (toggle) | L2 |
| Show FPS | Y |
| Quit | Start |

The hotkey button is the layout's own (Select on spruce and Android; spruce's `raHotkeyMiyoo`/`raHotkeyTrimUI` setting may pick another).

## Goals

- `spruce` cards: quit set to hotkey + Start on every sync (and `config apply`), nothing else in RetroArch's hotkeys touched.
- Android (`config apply` over adb): the whole scheme in RetroArch's `retroarch.cfg`, with hotkeys that would clash unbound.
- The setup guide's Hotkeys section rewritten around this scheme: short, saying what sync-roms sets and only the steps left by hand.

## Non-goals

- No other layouts' configs (Knulli, muOS, Onion, Allium, NextUI, EmuDeck): guide only.
- No standalone emulators (their settings are in app-private storage adb can't reach): guide only, and only what is known.
- No setting to turn this off; it is the scheme.

## Anti-goals

- Copying spruce's per-device button tables into the repo (they break on spruce updates).
- Leaving unchecked guesses in the guide.

## Approaches

1. **Picked.** Spruce: change only quit, reading the device's Start value from spruce's own platform script on the card. Android: write the full scheme with Android's standard gamepad keycodes.
2. Spruce: write the full scheme from a per-device table in the repo. Rejected: duplicates spruce, numbering differs per device and driver, and spruce already ships the rest of the scheme.
3. Android: read the device's RetroArch autoconfig profile for the pad's codes. Rejected: the profile lives in `/data/user/0/<pkg>/autoconfig`, which adb can't read; the standard codes were checked on both devices instead.

## Facts the design rests on (spruceOS 4.6.0, two Android devices)

- Spruce's live RetroArch config is `Saves/ra-configs/retroarch-<platform>.cfg` (seeded from `RetroArch/platform/retroarch-<platform>.cfg.bak` at first launch; sync already edits these files for Syncthing and warns when none exists yet). At each launch spruce rewrites only the hotkey-enable line (`RA_HOTKEY_LINE`), the language and RetroAchievements lines; other hotkey lines stay. `set_default_ra_hotkeys` runs only from spruce's "Reset RA hotkeys" task.
- Each platform's script `spruce/scripts/platform/<family>/<platform>.cfg` sets `RA_HOTKEY_LINE` (`input_enable_hotkey_btn`, or `input_enable_hotkey` on the A30, which uses keyboard names) and `RA_START_VAL` (Start in that numbering: `6` Brick, `10` Anbernic XX, `9` RGB30, `enter` A30), either itself or in a family file it sources (`. /mnt/SDCARD/spruce/scripts/platform/h700/AnbernicXXCommon.cfg`).
- spruce's quit default is `input_exit_emulator_btn` (B) and, with keyboard names, `input_exit_emulator`.
- Android RetroArch binds hotkeys by Android keycode. Both devices (Retroid Pocket Nova, RG Cube) use `Generic.kl`: Select 109, Start 108, X 99, Y 100, L1 102, R1 103, L2 104, R2 105, D-pad `h0left`/`h0right`/`h0up`/`h0down`. Both ship vendor hotkeys that clash (Nova: hotkey on 98, hold fast-forward on R2, toggle fast-forward on L2; RG Cube: slots on L2/R2, fast-forward on A).

## Design

### Spruce (sync and `config apply`)

For each `Saves/ra-configs/retroarch-<P>.cfg` on a `spruce` card:

- Find `<P>`'s platform script (`spruce/scripts/platform/*/<P>.cfg`), read `RA_HOTKEY_LINE` and `RA_START_VAL` from it or the files it sources (last assignment wins). The quit key is `RA_HOTKEY_LINE` with `enable_hotkey` replaced by `exit_emulator`; its value is `RA_START_VAL`.
- Set that line, other lines and line ends kept (same text edit as the Syncthing RetroArch settings). Already right: nothing written.
- Skip with a warning when the script or the values can't be found, or when the card's hotkey button is Start (the hotkey-enable line equals `RA_START_VAL`: quit on hotkey + Start would be Start + Start).
- Runs on every spruce sync (not guest cards, as with the other spruce settings) whether or not Syncthing is on, in the same place as the spruce settings write; `config apply --dry-run` lists the entry.

### Android (`config apply`)

`android_settings.cfg_wanted` adds the scheme's keys to `retroarch.cfg`:

- `input_enable_hotkey_btn` 109, `input_menu_toggle_btn` 99, `input_save_state_btn` 103, `input_load_state_btn` 102, `input_state_slot_decrease_btn` `h0left`, `input_state_slot_increase_btn` `h0right`, `input_toggle_fast_forward_btn` 105, `input_toggle_slowmotion_btn` 104, `input_fps_toggle_btn` 100, `input_exit_emulator_btn` 108; each one's `_axis` `nul`.
- Unbound (`_btn` and `_axis` `nul`): `input_hold_fast_forward`, `input_hold_slowmotion`, `input_rewind`, `input_pause_toggle`, `input_reset`, `input_screenshot`, `input_shader_next`, `input_shader_prev`, `input_shader_toggle`, `input_netplay_game_watch`, `input_disk_eject_toggle`, `input_disk_next`, `input_disk_prev`, `input_close_content`, `input_menu_toggle_gamepad_combo` `0`, `input_quit_gamepad_combo` `0`, so no vendor preset leaves a second action on a scheme button. (The exact list is the builder's: every RetroArch hotkey `_btn` key not in the scheme, checked against the two devices' configs.)
- The values live in repo data (`src/sync_roms/data/hotkeys.json`: the scheme's actions, Android's keycodes, the keys to clear) so the guide and tests read the same scheme.

### Guide

Rewrite the Hotkeys section ([setup-guide.html](../../../src/sync_roms/data/setup-guide.html)) as planned earlier: one table of the scheme with the layout's real combos; spruce and Android say "set by sync-roms" (spruce: by sync; Android: by `config apply`); other layouts list only the manual steps to reach the scheme, combos that can't match marked; unverified entries and long "other shortcuts" lists removed; Android standalones only where there is something to bind. Update `tests/test_setup_guide.py` for the new data.

## Left to the builder

- Module placement (a `spruce_hotkeys.py` beside `spruce_settings.py` is the suggestion) and the dry-run/print lines, matching the spruce settings' style.
- The exact clear list on Android.
- CLAUDE.md: a line for the new module and data file.
