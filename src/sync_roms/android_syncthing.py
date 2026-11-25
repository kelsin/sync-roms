"""Sets up Syncthing-Fork on an Android device over adb: its access, battery exemption, and the server and folders through its REST API."""
import io
import json
import re
import ssl
import time
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

from . import adb, android, android_access, applied, spruce_syncthing, ui

PACKAGE = "com.github.catfriend1.syncthingfork"
EXPORT = "/storage/emulated/0/backups/syncthing/config.zip"
WHERE = "Syncthing-Fork"
NO_EXPORT = ("Syncthing-Fork has no export at /storage/emulated/0/backups/syncthing/config.zip: export its settings "
             "(Settings > Import and Export > Export, no backup password) so config apply can add the server and folders")
DOWN = "Syncthing-Fork isn't running (its run conditions may keep it stopped); the server and folders aren't set"
ENCRYPTED = "is encrypted (export it without a backup password)"
PATHS = {"saves": android.DEFAULT_SAVES, "states": android.DEFAULT_STATES}


def read_export(data):
    """(API key, GUI port) from a Syncthing-Fork config export, or why it can't be used."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = next((i for i in z.infolist() if i.filename == "config.xml"), None)
            if info is None:
                return "has no config.xml"
            if info.flag_bits & 0x1:
                return ENCRYPTED
            try:
                raw = z.read(info)
            except (RuntimeError, NotImplementedError):
                return ENCRYPTED
    except zipfile.BadZipFile:
        return "isn't a zip"
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return "has a config.xml that can't be parsed"
    key = (root.findtext("gui/apikey") or "").strip()
    if not key:
        return "has no API key"
    match = re.search(r":(\d+)$", (root.findtext("gui/address") or "").strip())
    return key, int(match.group(1)) if match else 8384


def folder_paths(srv):
    """[(folder id, label, Android path)] of the server's folders."""
    return [(folder_id, label, PATHS[role]) for role, folder_id, label, _ in srv["folders"]]


def plan(config, srv, defaults_device, defaults_folder):
    """(entries, REST calls (method, path, body), warnings) to add the server and its folders to `config`."""
    server = srv["id"]
    entries, calls, warnings = [], [], []
    known = any(d["deviceID"].upper() == server for d in config.get("devices", []))
    entries.append(applied.Entry(WHERE, "device server", server if known else None, server, False))
    if not known:
        calls.append(("PUT", f"/rest/config/devices/{server}",
                      {**defaults_device, "deviceID": server, "name": "server", "addresses": [srv["address"]]}))
    folders = config.get("folders", [])
    for folder_id, label, path in folder_paths(srv):
        want = f"{path}, shared with the server"
        found = next((f for f in folders if f["id"] == folder_id), None)
        if found is not None:
            if found["path"].rstrip("/") != path:
                warnings.append(f"Syncthing-Fork folder {folder_id} is at {found['path']}, not {path}; left as it is")
            elif any(d["deviceID"].upper() == server for d in found.get("devices", [])):
                entries.append(applied.Entry(WHERE, f"folder {folder_id}", want, want, False))
            else:
                entries.append(applied.Entry(WHERE, f"folder {folder_id}", f"{path}, not shared with the server", want, False))
                calls.append(("PUT", f"/rest/config/folders/{folder_id}",
                              {**found, "devices": found.get("devices", []) + [{"deviceID": server}]}))
            continue
        other = next((f for f in folders if f["path"].rstrip("/") == path), None)
        if other is not None:
            warnings.append(f"Syncthing-Fork folder {other['id']} is already at {path}, so {folder_id} isn't added there; left as it is")
            continue
        entries.append(applied.Entry(WHERE, f"folder {folder_id}", None, want, False))
        calls.append(("PUT", f"/rest/config/folders/{folder_id}",
                      {**defaults_folder, "id": folder_id, "label": label, "path": path, "type": "sendreceive",
                       "devices": [{"deviceID": server}]}))
    return entries, calls, warnings


def _api(port, key, method, path, body=None):
    """The JSON answer of Syncthing-Fork's REST API on 127.0.0.1:port, None when empty."""
    request = urllib.request.Request(f"https://127.0.0.1:{port}{path}", method=method, headers={"X-API-Key": key},
                                     data=None if body is None else json.dumps(body).encode())
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10, context=ssl._create_unverified_context()) as response:
        raw = response.read()
    return json.loads(raw) if raw.strip() else None


def _up(port, key):
    """Whether the health check answers within 15 seconds."""
    deadline = time.monotonic() + 15
    while True:
        try:
            _api(port, key, "GET", "/rest/noauth/health")
            return True
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(1)


def _folder_part(serial, srv, dry_run):
    """entries for the server and folders (their REST calls sent unless a dry run), or [] with a warning when they can't be reached."""
    if not adb.is_file(serial, EXPORT):
        ui.warn(NO_EXPORT)
        return []
    found = read_export(adb.exec_out(serial, "cat", EXPORT))
    if isinstance(found, str):
        ui.warn(f"Syncthing-Fork's export {found}; the server and folders aren't set")
        return []
    key, remote = found
    port = adb.forward(serial, remote)
    try:
        if not _up(port, key):
            if not dry_run:
                adb.shell(serial, "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
            if dry_run or not _up(port, key):
                if dry_run:
                    print(ui.dim(DOWN))
                else:
                    ui.warn(DOWN)
                return []
        try:
            config = _api(port, key, "GET", "/rest/config")
            device = _api(port, key, "GET", "/rest/config/defaults/device")
            default = _api(port, key, "GET", "/rest/config/defaults/folder")
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            ui.warn("Syncthing-Fork refused the export's API key: export its settings again")
            return []
        entries, calls, warnings = plan(config, srv, device, default)
        for warning in warnings:
            ui.warn(warning)
        if not dry_run:
            for method, path, body in calls:
                _api(port, key, method, path, body)
        return entries
    finally:
        adb.forward_remove(serial, port)


def apply(serial, dry_run, failed):
    """Give Syncthing-Fork its access and, from its config export, the server and folders; trouble is warned about, adb and REST errors counted in `failed`."""
    if not spruce_syncthing.enabled():
        return
    try:
        if f"package:{PACKAGE}" not in adb.shell(serial, "pm", "list", "packages").split():
            print(ui.dim("Syncthing-Fork isn't installed: put its APK in os/android/APKs/ (config apply installs it) "
                           "or install it from F-Droid"))
            return
        access = android_access.entries(serial, PACKAGE, WHERE)
        if not dry_run:
            android_access.apply(serial, access)
            applied.show([e for e, _ in access], False)
        srv = spruce_syncthing.server()
        entries = _folder_part(serial, srv, dry_run) if srv else []
        applied.show(([e for e, _ in access] if dry_run else []) + entries, dry_run)
    except (adb.AdbError, OSError, ValueError) as e:
        ui.warn(f"Syncthing-Fork: {e}")
        failed.append("Syncthing-Fork")
