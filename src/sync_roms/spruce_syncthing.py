"""The Syncthing settings sync puts on spruce cards (data/syncthing.json), switched off by `syncthing: false`."""
import glob
import json
import os
import re
import xml.etree.ElementTree as ET

from . import applied, cardfs, spruce_emu, store, ui, usersettings

NO_WIFI_SKIPS = ("Network Settings", "enableSyncthing")
CARD_ROOT = "/mnt/SDCARD/"
DEVICE_ID = re.compile(r"[A-Z2-7]{7}(-[A-Z2-7]{7}){7}")
CONFIG = ("Saves", "syncthing", "config", "config.xml")
GUI_PASSWORD = "$2a$10$Eycxnvj3BtN8fq7suC4.W.ZrDRyH6fgN/pFY.LrOJCG6xIBeDSxdO"  # bcrypt of spruce's public default


def data():
    return store.repo_json("syncthing")


def enabled():
    return usersettings.load_settings().get("syncthing") is not False


def forced_keys():
    """Every (section, key) the Syncthing data sets on a spruce card."""
    return {(section, key) for section, keys in data()["spruce"]["settings"].items() for key in keys}


def forced_settings(card):
    """[(section, key, value)] sync sets on the card's spruce-config.json: [] when off, and without enableSyncthing on a device with no WiFi."""
    if not enabled():
        return []
    no_wifi = _no_wifi(card)
    return [(section, key, value) for section, keys in data()["spruce"]["settings"].items()
            for key, value in keys.items() if not (no_wifi and (section, key) == NO_WIFI_SKIPS)]


def _no_wifi(card):
    device = store.saved_card(card).get("device")
    return any(d.get("id") == device and d.get("network") is False for d in store.repo_json("devices"))


def server():
    """The validated `syncthing_server` setting, or None when unset or malformed (malformed warns once).

    {"id": uppercased device ID, "address": str, "folders": [(role, folder id, label, card path)]}."""
    setting = usersettings.load_settings().get("syncthing_server")
    if setting is None:
        return None
    shared = data()["spruce"]["folders"]
    problem = None
    if not isinstance(setting, dict):
        problem = "must be an object"
    else:
        ident = setting.get("id")
        ids = setting.get("folders")
        if not isinstance(ident, str) or not DEVICE_ID.fullmatch(ident.upper()):
            problem = '"id" must be the server\'s Syncthing device ID'
        elif "address" in setting and not (isinstance(setting["address"], str) and setting["address"]):
            problem = '"address" must be a non-empty string'
        elif not isinstance(ids, dict) or not all(isinstance(ids.get(role), str) and ids[role] for role in shared):
            problem = '"folders" must give a folder id for ' + " and ".join(f'"{role}"' for role in shared)
    if problem:
        ui.warn(f"syncthing_server in settings.json is ignored: {problem}")
        return None
    return {"id": setting["id"].upper(), "address": setting.get("address", "dynamic"),
            "folders": [(role, setting["folders"][role], folder["label"], CARD_ROOT + folder["path"])
                        for role, folder in shared.items()]}


def _insert(root, element, after):
    """Put element after the last root child tagged `after` (or first when there is none)."""
    children = list(root)
    index = max((i for i, child in enumerate(children) if child.tag == after), default=-1)
    root.insert(index + 1, element)


def folder_settings():
    """(ignore permissions, max conflicts, versioning type, versions kept) wanted on every shared folder."""
    wanted = data()["folder"]
    return wanted["ignore_permissions"], wanted["max_conflicts"], wanted["versioning"]["type"], wanted["versioning"]["keep"]


def versioning_text(kind, keep):
    return f"{kind}, keep {keep}"


def _versioning(folder):
    """The folder's versioning as `versioning_text`, None when it has none."""
    element = folder.find("versioning")
    if element is None or not element.get("type"):
        return None
    param = next((p for p in element.findall("param") if p.get("key") == "keep"), None)
    return versioning_text(element.get("type"), None if param is None else param.get("val"))


def _apply_folder_settings(folder, label, lines):
    """Set ignorePerms, maxConflicts and versioning on a config.xml folder element; one line per change."""
    ignore, conflicts, kind, keep = folder_settings()
    for tag, value in (("ignorePerms", str(ignore).lower()), ("maxConflicts", str(conflicts))):
        element = folder.find(tag)
        if element is None:
            element = ET.SubElement(folder, tag)
        if element.text != value:
            element.text = value
            lines.append(f"   config.xml: {label} {tag} = {value}")
    if _versioning(folder) != versioning_text(kind, str(keep)):
        old = folder.find("versioning")
        if old is not None:
            folder.remove(old)
        element = ET.SubElement(folder, "versioning", {"type": kind})
        ET.SubElement(element, "cleanupIntervalS").text = "3600"
        ET.SubElement(element, "fsPath")
        ET.SubElement(element, "fsType").text = "basic"
        ET.SubElement(element, "param", {"key": "keep", "val": str(keep)})
        lines.append(f"   config.xml: {label} versioning = {versioning_text(kind, keep)}")


def _server_device(srv):
    device = ET.Element("device", {"id": srv["id"], "name": "server", "compression": "metadata", "introducer": "false"})
    ET.SubElement(device, "address").text = srv["address"]
    ET.SubElement(device, "paused").text = "false"
    ET.SubElement(device, "autoAcceptFolders").text = "false"
    return device


def _new_folder(srv, folder_id, label, path):
    folder = ET.Element("folder", {"id": folder_id, "label": label, "path": path, "type": "sendreceive"})
    ET.SubElement(folder, "filesystemType").text = "basic"
    ET.SubElement(folder, "device", {"id": srv["id"], "introducedBy": ""})
    ET.SubElement(folder, "modTimeWindowS").text = "2"
    _apply_folder_settings(folder, label, [])
    return folder


def _fresh_root():
    root = ET.Element("configuration", {"version": "37"})
    gui = ET.SubElement(root, "gui", {"enabled": "true", "tls": "false"})
    ET.SubElement(gui, "address").text = "0.0.0.0:8384"
    ET.SubElement(gui, "user").text = "spruce"
    ET.SubElement(gui, "password").text = GUI_PASSWORD
    ET.SubElement(ET.SubElement(root, "options"), "listenAddress").text = "default"
    return root


def merge_config(old, srv):
    """(new text or None when unchanged, lines, warnings): the server device and shared folders merged into a Syncthing config.xml text.

    `old` None builds a fresh config. Anything else in the config is kept."""
    lines, warnings = [], []
    if old is None:
        root = _fresh_root()
        lines.append("   config.xml: new config")
    else:
        try:
            root = ET.fromstring(old)
        except ET.ParseError:
            return None, [], ["Saves/syncthing/config/config.xml can't be parsed; the Syncthing server and folders left as they are"]
        if root.tag != "configuration":
            return None, [], ["Saves/syncthing/config/config.xml isn't a Syncthing config; the Syncthing server and folders left as they are"]
    before = ET.tostring(root, encoding="unicode")
    if not any(d.get("id") == srv["id"] for d in root.findall("device")):
        _insert(root, _server_device(srv), "device" if root.find("device") is not None else "folder")
        lines.append("   config.xml: server device")
    for _, folder_id, label, path in srv["folders"]:
        found = next((f for f in root.findall("folder") if f.get("id") == folder_id), None)
        if found is None:
            clash = next((f for f in root.findall("folder") if (f.get("path") or "").rstrip("/") == path.rstrip("/")), None)
            if clash is not None:
                warnings.append(f"Syncthing folder {clash.get('id')} is already at {path} in config.xml, so {folder_id} isn't added there; left as it is")
                continue
            _insert(root, _new_folder(srv, folder_id, label, path), "folder")
            lines.append(f"   config.xml: folder {label} at {path}")
            continue
        if (found.get("path") or "").rstrip("/") != path.rstrip("/"):
            warnings.append(f"Syncthing folder {folder_id} is at {found.get('path')} in config.xml, not {path}; left as it is")
            continue
        if not any(d.get("id") == srv["id"] for d in found.findall("device")):
            _insert(found, ET.Element("device", {"id": srv["id"], "introducedBy": ""}), "device")
            lines.append(f"   config.xml: {label} shared with the server")
        window = found.find("modTimeWindowS")
        if window is None:
            window = ET.SubElement(found, "modTimeWindowS")
        if window.text != "2":
            window.text = "2"
            lines.append(f"   config.xml: {label} modTimeWindowS = 2")
        _apply_folder_settings(found, label, lines)
    if old is not None and ET.tostring(root, encoding="unicode") == before:
        return None, [], warnings
    if old is None:
        ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n", lines, warnings


def _config_plan(card, base, srv):
    """(writes, lines, warnings) for config.xml given the validated server (None: nothing to do)."""
    if srv is None or _no_wifi(card):
        return [], [], []
    path = os.path.join(base, *CONFIG)
    old = cardfs.text(path) or None
    if old is None and not cardfs.is_dir(os.path.join(base, "Saves")):
        return [], [], ["Saves/ is missing (spruceOS isn't installed?); Syncthing's config not written"]
    new, lines, warnings = merge_config(old, srv)
    return ([(path, new)] if new is not None else []), lines, warnings


def config_writes(card, base):
    """(writes, lines, warnings): Saves/syncthing/config/config.xml with the server device and shared folders."""
    return _config_plan(card, base, server())


def _cores(base, warnings):
    """Yield (folder, core, path, old text, config) for each Emu/<FOLDER>/config.json that exists and can be read."""
    seen = set()
    systems = {s["bucket"]: s for s in store.repo_json("systems")}
    for system, core in data()["cores"].items():
        folder = systems.get(system, {}).get("folders", {}).get("spruce")
        if not folder or folder in seen:
            continue
        seen.add(folder)
        path = os.path.join(base, "Emu", folder, "config.json")
        try:
            old = cardfs.text(path)
            if not old:
                continue
            config = json.loads(old)
            if not isinstance(config, dict):
                raise ValueError
        except (OSError, ValueError):
            warnings.append(f"Emu/{folder}/config.json can't be read; its core left as it is")
            continue
        yield folder, core, path, old, config


def _offering(config, core):
    """[entry dict] of the config's Emulator* entries that offer the core."""
    options = config.get("menuOptions")
    return [entry for key, entry in (options.items() if isinstance(options, dict) else [])
            if key.startswith("Emulator") and isinstance(entry, dict) and isinstance(entry.get("options"), list)
            and core in entry["options"]]


def core_writes(base):
    """(writes [(path, text)], lines, warnings): each Emu/<FOLDER>/config.json that exists, with the Syncthing core selected in every Emulator* entry that offers it."""
    writes, lines, warnings = [], [], []
    for folder, core, path, old, config in _cores(base, warnings):
        changed = False
        for entry in _offering(config, core):
            if entry.get("selected") != core:
                entry["selected"] = core
                changed = True
        if changed:
            writes.append((path, spruce_emu._dump(config, old)))
            lines.append(f"   Emu/{folder}: {core}")
    return writes, lines, warnings


def _pattern(key):
    return re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=.*?(?=\r?$)", re.M)


def retroarch_writes(base):
    """(writes, lines, warnings): each Saves/ra-configs/retroarch-*.cfg with the Syncthing save settings set, other lines kept."""
    paths = sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "ra-configs", "retroarch-*.cfg")))
    if not paths:
        return [], [], ["Saves/ra-configs has no retroarch-*.cfg yet; launch a game once on the device, then sync again for RetroArch's save settings"]
    writes, lines, warnings = [], [], []
    for path in paths:
        try:
            old = cardfs.raw_text(path)  # raw: cardfs.text would turn CRLF into LF
        except (OSError, ValueError):
            warnings.append(f"Saves/ra-configs/{os.path.basename(path)} can't be read; its save settings left as they are")
            continue
        eol = "\r\n" if "\r\n" in old else "\n"
        new = old
        for key, value in data()["retroarch"].items():
            line = f'{key} = "{value}"'
            pattern = _pattern(key)
            if pattern.search(new):
                updated = pattern.sub(lambda m: m.group(0) if m.group(0) == line or _same(m.group(0), value) else line, new)
            else:
                updated = new + ("" if not new or new.endswith("\n") else eol) + line + eol
            if updated != new:
                new = updated
                lines.append(f"   {os.path.basename(path)}: {key} = {value}")
        if new != old:
            writes.append((path, new))
    return writes, lines, warnings


def _same(line, value):
    """True when a cfg line already holds value (quoted or not)."""
    return line.split("=", 1)[1].strip().strip('"') == value


def _config_entries(base, srv):
    where = "/".join(CONFIG)
    text = cardfs.text(os.path.join(base, *CONFIG)) or ""
    root = None
    if text:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []  # merge_config warns about it
        if root.tag != "configuration":
            return []
    found = root is not None and any(d.get("id") == srv["id"] for d in root.findall("device"))
    result = [applied.Entry(where, "server", srv["id"] if found else None, srv["id"], False)]
    for _, folder_id, label, path in srv["folders"]:
        folder = next((f for f in root.findall("folder") if f.get("id") == folder_id), None) if root is not None else None
        old_path = None if folder is None else (folder.get("path") or "").rstrip("/")
        result.append(applied.Entry(where, label, old_path, path.rstrip("/"), False))
        shared = None if folder is None else ("yes" if any(d.get("id") == srv["id"] for d in folder.findall("device")) else "no")
        result.append(applied.Entry(where, f"{label} shared with server", shared, "yes", False))
        window = None if folder is None else folder.findtext("modTimeWindowS")
        result.append(applied.Entry(where, f"{label} modTimeWindowS", window, "2", False))
        ignore, conflicts, kind, keep = folder_settings()
        for tag, value in (("ignorePerms", str(ignore).lower()), ("maxConflicts", str(conflicts))):
            result.append(applied.Entry(where, f"{label} {tag}", None if folder is None else folder.findtext(tag), value, False))
        result.append(applied.Entry(where, f"{label} versioning", None if folder is None else _versioning(folder),
                                    versioning_text(kind, keep), False))
    return result


def entries(card, base):
    """[Entry] for every Syncthing core and RetroArch save setting, changed or not; [] when Syncthing is off."""
    if not enabled():
        return []
    warnings = []
    result = []
    for folder, core, _, _, config in _cores(base, warnings):
        offering = _offering(config, core)
        if offering:
            old = next((e.get("selected") for e in offering if e.get("selected") != core), core)
            result.append(applied.Entry(f"Emu/{folder}/config.json", "core", old, core, False))
    for path in sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "ra-configs", "retroarch-*.cfg"))):
        try:
            text = cardfs.raw_text(path)
        except (OSError, ValueError):
            continue  # retroarch_writes warns about it below
        for key, value in data()["retroarch"].items():
            found = _pattern(key).search(text)
            old = found.group(0).split("=", 1)[1].strip().strip('"') if found else None
            result.append(applied.Entry(f"Saves/ra-configs/{os.path.basename(path)}", key, old, value, False))
    srv = server()
    config_warnings = []
    if srv is not None and not _no_wifi(card):
        config_warnings = _config_plan(card, base, srv)[2]
        result += _config_entries(base, srv)
    for warning in warnings + retroarch_writes(base)[2] + config_warnings:
        ui.warn(warning)
    return result


def run(card, layout_name, base, dry_run):
    """Set the Syncthing cores and RetroArch save settings on a spruce card. 0: a problem is a warning."""
    if layout_name != "spruce" or not enabled():
        return 0
    writes, lines, warnings = [], [], []
    srv = server()
    for part in (core_writes(base), retroarch_writes(base), _config_plan(card, base, srv)):
        writes += part[0]
        lines += part[1]
        warnings += part[2]
    for warning in warnings:
        ui.warn(warning)
    if not writes:
        return 0
    if dry_run:
        print(ui.dim("🧪 Dry run: would set for Syncthing:"))
        for line in lines:
            print(ui.dim(line))
        return 0
    for path, text in writes:
        cardfs.write_text(path, text)
    if any(path == os.path.join(base, *CONFIG) for path, _ in writes):
        for _, _, _, path in srv["folders"]:
            os.makedirs(os.path.join(base, path[len(CARD_ROOT):], ".stfolder"), exist_ok=True)
    print(ui.green(f"🔄 Syncthing: set {sum(1 for line in lines if not line.endswith(": new config"))} setting(s) so saves and states sync"))
    for line in lines:
        print(line)
    return 0
