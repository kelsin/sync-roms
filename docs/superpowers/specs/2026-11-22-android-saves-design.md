# `saves stash` / `saves apply` over wireless adb design

## Intent

Moving RetroArch saves between devices with `saves stash` and `saves apply` is awkward on Android handhelds: the card
stays in the device and RetroArch keeps its saves on internal storage (`/storage/emulated/0/RetroArch`), so today the
user copies that folder to the Mac by hand and runs the command with `--retroarch DIR`. The user wants to name or pick
the card and the device, and have sync-roms reach the device over wireless adb, find RetroArch's folders and do the
copying itself.

## Goals / non-goals / anti-goals

- Goal: `saves stash` and `saves apply` work on an Android card (an `esde` card whose device isn't `windows-pc`, the
  setup guide's `platformOf` rule) over adb, with no manual copy.
- Goal: with no card argument, or naming an Android card, show the adb devices it sees, or walk the user through
  pairing a new device for Wireless debugging, then do the stash or apply.
- Goal: a path to a mounted card keeps working exactly as today.
- Non-goals: USB-only setup help (a USB device that shows in `adb devices` simply works), other commands over adb
  (sync, mirror), non-RetroArch emulators, a Python adb library, Windows/Linux-specific adb install help.
- Anti-goals: writing anything to the device in `--dry-run`; overwriting a different save without the existing
  confirmation; leaving the user's saves only in a temp folder.

## Approaches

1. **Stage a temp copy and reuse today's code (picked).** Build a temp card folder: zero-byte placeholders for the
   card's ROM tree (from `adb shell find`) and a pull of RetroArch's saves and states folders. Run the existing
   `scan`/`plan_apply` on it with `retroarch_dir`, then push back only the files apply wrote. Saves are small, and
   `saves.py` barely changes.
2. Put `saves.py`'s file access behind a local/adb layer so only picked files move. Cleaner, but it touches every
   function in `saves.py` for little gain at these sizes. Rejected.
3. A Python adb library (`adb-shell` and similar). These don't handle Android 11+ wireless pairing, which is the part
   the user most wants help with, and Homebrew `adb` is already installed. Rejected.

## Design

### Picking the card and the device (decided with the user)

- `CARD` is a path when it is an existing folder: today's behaviour, no adb.
- `CARD` is a card name in `cards.json` (not a folder): an Android card goes over adb. Any other card fails (exit 2)
  saying to pass its mounted path.
- No `CARD`: when the current folder's name is a card in `cards.json`, the current folder is that card's path (today's
  behaviour); otherwise the adb flow, starting at the device picker.
- `--retroarch DIR` still applies to path mode. With adb it is an error (exit 2).

### The adb flow (new module `android.py`, my call on the name)

- `adb` is found with `shutil.which`. When it's missing: fail with `brew install android-platform-tools` (exit 2).
- **Device picker** "📱 Which device?": every `adb devices -l` entry in state `device`, labelled with its model
  (`getprop ro.product.model`) and the card in it (see below), offline/unauthorized ones shown as hints, and a last row
  "➕ Set up a new device". Asked even with one device; Esc exits 0.
- **Which card is in the device (decided with the user):** a card remembers its SD card's volume id (the `<id>` of
  `/storage/<id>/`, e.g. `6AF3-53E9`) in a new card field `android_volume`, so the card is recognised in any handheld.
  A device's card is the one whose `android_volume` matches a volume it has mounted; a volume no card has asks once
  "🃏 Which card is this?" from the Android cards (those whose `device` matches the model first) and is saved on that
  card, taken off any other card that had it *(my call)*. A named card picks the connected device holding its volume;
  when none does, the device picker is shown. Picking a device whose card is another one fails (exit 2) naming both.
  `--dry-run` still saves `android_volume` (it changes nothing on the device or in storage) *(my call)*.
- **Set up a new device:** printed steps (Settings → About → tap Build number 7 times; Developer options → Wireless
  debugging on, same Wi-Fi as the Mac; "Pair device with pairing code"). Then `adb mdns services` is polled for an
  `_adb-tls-pairing._tcp` service, falling back to typing the `IP:port` shown. The flow asks for the 6-digit code and
  runs `adb pair`, then `adb connect` (the `_adb-tls-connect._tcp` service, else ask for the `IP:port` on the Wireless
  debugging screen). It ends on the device picker again.
- **Reconnect:** before the picker, `adb connect` every `_adb-tls-connect._tcp` service `adb mdns services` lists that
  isn't connected yet (paired devices after a reboot or port change).

### Finding the folders on the device

- **SD card:** each `/storage/<id>/` other than `emulated` and `self` that has the layout's `roms_dir` (`ROMs/`).
  With several, the one matching the card's `android_volume`, else ask which.
- **RetroArch:** packages from `pm list packages` matching `com.retroarch*`, with several asking which. Read
  `/storage/emulated/0/Android/data/<pkg>/files/retroarch.cfg` for `savefile_directory`, `savestate_directory`,
  `sort_savefiles_enable`, `sort_savestates_enable`, `sort_*_by_content_enable` and `*_in_content_dir`. An empty or
  `default` directory means `/storage/emulated/0/RetroArch/saves` (`states`). *(My call.)*
- **Unreadable config:** a missing or unreadable `retroarch.cfg` fails (exit 2) saying where it looked, rather than
  guessing folders RetroArch may never read *(my call)*.
- **Unsupported config:** saves or states in the content dir, or sorted by content, fails with which setting to change
  (exit 2).
- **Sort by core:** over adb the device's own `sort_savefiles_enable` / `sort_savestates_enable` decide, per kind: off
  means the flat folder (the layout's `saves`/`states` template without `/{core}`, passed as a modified layout copy).
  Mounted cards are unchanged *(my call)*.
- The ROM placeholders and the pulled folders go in a temp folder: saves into `<tmp>/RetroArch/saves`, states into
  `<tmp>/RetroArch/states`, ROMs as empty files under `<tmp>/<roms_dir>/...`. The existing code runs with
  `base=<tmp>`.

### Stash and apply

- **RetroArch running (decided with the user):** before pulling (stash and apply), `pidof <pkg>`; when it runs, ask the
  user to save in-game and close RetroArch on the device, then check again (Enter re-checks, Esc exits 0). Never
  force-stopped. A RetroArch still open in memory would write its own save over a pushed one, and a stash would pull a
  stale one.

- **Stash:** pull (`adb pull`), then the existing stash. Nothing is written to the device.
- **Apply:** pull, then the existing apply on the temp copy, which collects the destination files it copied. Each of
  those is pushed to its device path (`mkdir -p` of the parent, then `adb push`). A push failure is reported per file
  and exits 1. `--dry-run` pulls and plans but never pushes.
- The temp folder is removed at the end, ^C included.
- Output names the device and card: `📱 POCKETNOVA on Retroid Pocket Nova (RetroArch com.retroarch.aarch64)`.
- `adb pull -a` keeps mtimes *(my call)*.

### Docs and data

- `cli.TOPICS["saves"]`, the README Options row, and the CLAUDE.md card fields table (`android_volume`, written
  by `saves`), plus `cards.schema.json`.

## Left to the builder

- Subprocess wrapper shape. Tests fake `adb` (a fake `subprocess.run` or a fake `adb` script on `PATH`), never a real
  device.
- How `apply_command` reports the files it wrote. Exact prompt wording and the mDNS poll timeout.
