# Syncthing-Fork setup over adb in `config apply`

## Intent

The setup guide's Android Syncthing steps are mostly manual: add the server as a remote device, accept `ra-saves`/`ra-states` at RetroArch's folders, keep Android from stopping the app. `sync-roms config apply` already reaches the device over adb and already writes the matching config on spruce cards (`spruce_syncthing.merge_config`). This change makes `config apply` do the Android side too, so a new Android device needs only: install Syncthing-Fork, export its settings once, run `config apply`, accept the device on the server, and set the run conditions.

## Goals

- On an Android device, `config apply` (while `syncthing` isn't `false` and `syncthing_server` is set) makes Syncthing-Fork:
  - know the server device (`syncthing_server.id`, `address` or `dynamic`), added only when missing;
  - have the two shared folders, ids from `syncthing_server.folders` (`saves`, `states`), labels from `syncthing.json`'s `spruce.folders`, at `android.DEFAULT_SAVES` / `android.DEFAULT_STATES` (the folders `cfg_wanted` points RetroArch at), shared with the server;
  - be exempt from battery optimization (`dumpsys deviceidle whitelist +<pkg>`);
  - have All files access (`appops set <pkg> MANAGE_EXTERNAL_STORAGE allow`), which it needs to read RetroArch's folders.
- `--dry-run` lists every one of those, changed or not, like the other `config apply` entries (`applied.Entry`).
- The setup guide's Android Syncthing section matches the new flow; CLAUDE.md's `config apply` paragraph says what it does.

## Non-goals

- Run conditions. They live in the app's private SharedPreferences; adb can't write them without root, and the export holds them as a Java-serialized map. The guide keeps the step (with where the screen is).
- Accepting the device on the server. sync-roms knows only the server's ID, not its API. (Possible follow-up: optional server API settings.)
- Installing Syncthing-Fork. An APK in `os/android/APKs/` is already installed by the APK step (no rule needed).
- Storing the API key anywhere.

## Anti-goals

- Never change anything else in Syncthing-Fork's config: an existing server device is left as it is, a folder id already at another path is warned about and left (same rules as `merge_config`).
- Never delete or rewrite the user's export.
- A failure in this part never stops the rest of `config apply`; it warns and counts as failed (exit 1), like the other parts.

## Constraints (from the Syncthing-Fork source, researchxxl/syncthing-android, and the Nova)

- Package `com.github.catfriend1.syncthingfork`. Its config is app-private (`run-as` refused: not debuggable).
- The REST API listens on the device's port 8384 over HTTPS with a self-signed cert (plain HTTP redirects), checked through `adb forward tcp:0 tcp:8384` (`/rest/noauth/health` → OK). It needs the `X-API-Key` header.
- The API key is in `<gui><apikey>` of the `config.xml` in the app's export: Settings → Import and Export → Export writes `/storage/emulated/0/backups/syncthing/config.zip` (default path; the user can change it, which we can't read), flat entries, `config.xml` among them. It's AES-encrypted when the user set a backup password; stdlib `zipfile` can't read that.
- The GUI port comes from that same `config.xml`'s `<gui><address>` (default 8384).

## Approaches

1. **REST API through `adb forward`, key from the export zip** (picked). One tap on the device (Export), then everything is automatic and repeatable on every `config apply`. Uses Syncthing's own API, so the app sees the change live and nothing private is touched.
2. **Paste the API key at a prompt.** Works with an encrypted export or none, but the key is 32 characters shown on the handheld, so it's retyped by hand each run, and it needs a terminal.
3. **Edit the exported zip and have the user Import it.** Could also set run conditions, but means rewriting a Java-serialized map, an Import that restarts the app and replaces its keys/index, and a second tap. Too risky for what it adds.

Approach 1, with no fallback prompt: a missing or encrypted export warns with what to do (export without a backup password) and skips the Syncthing folder part; the battery and storage entries still apply.

## Design

New module `src/sync_roms/android_syncthing.py`; `android_settings.apply` calls it in both the dry-run and real paths (after the APK step, so a Syncthing-Fork the APK step just installed is seen). It returns `[Entry]` for the dry run and appends to `failed` on error.

Flow:

1. Skip silently when `spruce_syncthing.enabled()` is false. Skip with a dim hint when the package isn't installed ("install Syncthing-Fork to sync saves"). Without a valid `spruce_syncthing.server()`, only the battery and storage entries apply.
2. Battery and storage: read `dumpsys deviceidle whitelist` and `appops get <pkg> MANAGE_EXTERNAL_STORAGE`; entries under `Android (Syncthing-Fork)`; set only what differs.
3. API key: `adb exec-out cat` the zip into memory (no temp file on the device), read `config.xml` from it with `zipfile`, take `apikey` and the GUI port. Missing zip / encrypted / no key → warn with the step and skip the folder part. A missing export is a setup state, not a failure: it warns and doesn't change the exit code.
4. `adb forward tcp:0 tcp:<port>` (new `adb.forward`/`adb.forward_remove`), always removed in `finally`. Wait for `/rest/noauth/health` up to ~15 s; if it isn't running, launch the app once (`monkey -p <pkg> 1` or its launcher activity) and wait again; still down → warn (run conditions may keep it stopped) and skip. A dry run never launches the app: when it isn't answering, it prints a dim note and lists no device/folder entries.
5. `GET /rest/config`. A 403 → warn the export's key is stale (export again). Plan the same changes `merge_config` makes:
   - server device missing → `PUT /rest/config/devices/<id>` from `GET /rest/config/defaults/device` with `deviceID`, `name: "server"`, `addresses: [address]`;
   - per folder: a folder with that id at the wanted path → add the server to its `devices` when missing; with that id at another path → warn, leave; no such id but another folder at the path → warn, leave (as `merge_config` does); none → `PUT /rest/config/folders/<id>` from `GET /rest/config/defaults/folder` with `id`, `label`, `path`, `type: "sendreceive"`, `devices: [{"deviceID": server}]`.
   Entries under `Syncthing-Fork`: `device server`, `folder <id>` (new values describe the wanted state).
6. Storage on Android 10 and older (SDK < 30, `getprop ro.build.version.sdk`): `pm grant <pkg> android.permission.READ_EXTERNAL_STORAGE` and `WRITE_EXTERNAL_STORAGE` instead of the appop (state from `dumpsys package`).
7. HTTP: `urllib.request` with an unverified SSL context (localhost through adb only), JSON bodies, short timeouts. Errors (`URLError`, HTTP errors, adb errors in this part) → warn and append `"Syncthing-Fork"` to `failed`.

Pure functions (plan from a config dict + server + paths → entries and REST calls; key/port from zip bytes) carry the logic and the tests; the adb/HTTP shell around them stays thin and is tested with fakes.

### Guide (Android section) after the change

1. Install Syncthing-Fork from F-Droid and open it once.
2. Syncthing-Fork: Settings → Import and Export → Export, without a backup password (`config apply` reads its API key from the export; the export also holds the device's keys).
3. With RetroArch closed and the device on Wireless debugging, run `config apply`: the existing sentence, plus that it adds the server and `ra-saves`/`ra-states` at RetroArch's folders to Syncthing-Fork, gives it All files access and exempts it from battery optimization.
4. Server UI: accept the new device, tick `ra-saves` and `ra-states` on its Sharing tab. Save. (unchanged)
5. Syncthing-Fork: set its run conditions (Settings → Run conditions) so it runs when switching devices. (the user's step, with where the screen is)

The old "Add Remote Device" and "accept ra-saves/ra-states" steps go.

## Calls made after the builder check

- Failures (exit 1) are only unexpected errors once the device answered: adb errors in this part, HTTP errors other than 403, bad JSON. Setup states warn and don't fail: no/encrypted export, no `<apikey>`, a 403 (stale key: export again), the app not answering.
- No `modTimeWindowS` on Android folders: Android's shared storage isn't FAT, and the spruce side keeps its own setting.

## Left to the builder

- Exact entry key wording, timeouts, how the app is launched when stopped.
- Whether health waiting needs a spinner.
