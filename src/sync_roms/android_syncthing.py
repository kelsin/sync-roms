"""Syncthing-Fork on an Android device: reading its config export and planning the server and folders to add."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from . import android, applied

PACKAGE = "com.github.catfriend1.syncthingfork"
EXPORT = "/storage/emulated/0/backups/syncthing/config.zip"
WHERE = "Syncthing-Fork"
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
