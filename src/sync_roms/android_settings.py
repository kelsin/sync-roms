"""The retroarch.cfg and ES-DE gamelist edits `config apply` makes on an Android device, as text in, text out, and `apply`, which reads and writes them over adb."""
import os
import posixpath
import re
import shutil
import tempfile
from xml.sax.saxutils import escape, unescape

from . import adb, android, applied, spruce_syncthing, store, ui, usersettings

CFG = "retroarch.cfg"
SECRETS = ("cheevos_password", "webdav_password", "cheevos_token")
CLOUD_SYNC = {"cloud_sync_enable": "false", "webdav_url": "", "webdav_username": "", "webdav_password": ""}
RA_MODES = {"Disabled": {"cheevos_enable": "false"},
            "Casual": {"cheevos_enable": "true", "cheevos_hardcore_mode_enable": "false"},
            "Softcore": {"cheevos_enable": "true", "cheevos_hardcore_mode_enable": "false"},
            "Hardcore": {"cheevos_enable": "true", "cheevos_hardcore_mode_enable": "true"}}
XML_DECLARATION = '<?xml version="1.0"?>\n'
BLOCK = re.compile(r"<alternativeEmulator>\s*<label>(.*?)</label>\s*</alternativeEmulator>[ \t]*\r?\n?", re.S)


def cfg_wanted():
    """{key: value} for retroarch.cfg: the Syncthing save settings (when on), RetroAchievements, then Cloud Sync cleared."""
    wanted = {}
    if spruce_syncthing.enabled():
        wanted.update(spruce_syncthing.data()["retroarch"])
        wanted["savefile_directory"] = android.DEFAULT_SAVES
        wanted["savestate_directory"] = android.DEFAULT_STATES
    settings = usersettings.load_settings()
    wanted.update(RA_MODES.get(settings.get("spruce_ra_mode"), {}))
    for setting, key in (("spruce_ra_username", "cheevos_username"), ("spruce_ra_password", "cheevos_password")):
        if settings.get(setting):
            wanted[key] = settings[setting]
    wanted.update(CLOUD_SYNC)
    return wanted


def cfg_entries(text, wanted):
    """[Entry] for each wanted key; a changed username also clears a stored cheevos_token."""
    current = android.parse_config(text)
    result = [applied.Entry(CFG, key, current.get(key), value, key in SECRETS) for key, value in wanted.items()]
    if current.get("cheevos_token") and any(e.key == "cheevos_username" and applied.changed(e) for e in result):
        result.append(applied.Entry(CFG, "cheevos_token", current["cheevos_token"], "", True))
    return result


def cfg_apply(text, entries):
    """text with each changed entry's line(s) set to KEY = "VALUE" and missing keys appended, line ends kept."""
    eol = "\r\n" if "\r\n" in text else "\n"
    for entry in entries:
        if not applied.changed(entry):
            continue
        line = f'{entry.key} = "{entry.new}"'
        pattern = spruce_syncthing._pattern(entry.key)
        if pattern.search(text):
            text = pattern.sub(lambda m: line, text)
        else:
            text += ("" if not text or text.endswith("\n") else eol) + line + eol
    return text


def gamelist_entry(system_folder, text, label):
    found = BLOCK.search(text) if text else None
    old = unescape(found.group(1).strip()) if found else None
    return applied.Entry(f"ES-DE/gamelists/{system_folder}/gamelist.xml", "alternativeEmulator", old, label, False)


def gamelist_apply(text, label):
    """The gamelist with its alternativeEmulator block set to label; a missing file is made."""
    if text is None or not text.strip():
        text = XML_DECLARATION + "<gameList />\n"
    eol = "\r\n" if "\r\n" in text else "\n"
    block = f"<alternativeEmulator>{eol}\t<label>{escape(label)}</label>{eol}</alternativeEmulator>{eol}"
    if BLOCK.search(text):
        return BLOCK.sub(lambda m: block, text, count=1)
    at = text.find("<gameList")
    if at < 0:
        declaration = re.match(r"<\?xml[^>]*\?>[ \t]*\r?\n?", text)
        at = declaration.end() if declaration else 0
    return text[:at] + block + text[at:]


def esde_wanted(folders):
    """[(ES-DE ROM folder, emulator label)] for the Syncthing cores on the folders the card has; [] when Syncthing is off."""
    if not spruce_syncthing.enabled():
        return []
    have = set(folders)
    data = spruce_syncthing.data()
    systems = {s["bucket"]: s for s in store.repo_json("systems")}
    result = []
    for system, core in data["cores"].items():
        folder = systems.get(system, {}).get("folders", {}).get("esde")
        if folder in have:
            result.append((folder, data["esde_labels"][core]))
    return result


ESDE_PACKAGE = "org.es_de.frontend"


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _push(serial, local, remote, failed):
    try:
        adb.push(serial, local, remote)
    except adb.AdbError as e:
        failed.append(remote)
        ui.warn(f"Couldn't write {remote}: {e}")


def _pull_cfg(serial, remote, tmp):
    local = os.path.join(tmp, CFG)
    adb.pull(serial, remote, local)
    return _read(local)


def _retroarch_part(serial, pkg, tmp):
    """(entries, remote path) for retroarch.cfg; ([], path) with a warning when it can't be read."""
    remote = f"/storage/emulated/0/Android/data/{pkg}/files/{CFG}"
    if not adb.is_file(serial, remote):
        ui.warn(f"Can't read RetroArch's settings at {remote}: skipping them")
        return [], remote
    return cfg_entries(_pull_cfg(serial, remote, tmp), cfg_wanted()), remote


def _esde_part(serial, volume, roms_dir, systems, tmp):
    """[(Entry, folder, gamelist text or None, label)] for the wanted ES-DE folders the device has."""
    folders = {s["folders"]["esde"] for s in systems if s.get("folders", {}).get("esde")}
    result = []
    for folder, label in esde_wanted(folders):
        if not adb.is_dir(serial, f"/storage/{volume}/{roms_dir}/{folder}"):
            continue
        remote = f"/storage/{volume}/ES-DE/gamelists/{folder}/gamelist.xml"
        text = None
        if adb.is_file(serial, remote):
            local = os.path.join(tmp, "gamelists", folder, "gamelist.xml")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            adb.pull(serial, remote, local)
            text = _read(local)
        result.append((gamelist_entry(folder, text, label), folder, text, label))
    return result


def _write_retroarch(serial, pkg, remote, tmp, failed):
    """Wait for RetroArch to close (it rewrites its cfg on quit), then set what is still wrong in the fresh cfg."""
    android.wait_closed(serial, pkg)
    text = _pull_cfg(serial, remote, tmp)
    entries = cfg_entries(text, cfg_wanted())
    if not any(applied.changed(e) for e in entries):
        return
    local = os.path.join(tmp, "new-" + CFG)
    _write(local, cfg_apply(text, entries))
    _push(serial, local, remote, failed)


def _write_esde(serial, volume, gamelists, tmp, failed):
    if not ui.confirm("ES-DE must restart to see the new emulators. Close it now?", default=True):
        print(ui.dim("↩️  Left ES-DE's gamelists as they are"))
        return
    adb.shell(serial, "am", "force-stop", ESDE_PACKAGE)
    for entry, folder, text, label in gamelists:
        if not applied.changed(entry):
            continue
        local = os.path.join(tmp, "new-gamelists", folder, "gamelist.xml")
        _write(local, gamelist_apply(text, label))
        remote = f"/storage/{volume}/ES-DE/gamelists/{folder}/gamelist.xml"
        adb.shell(serial, "mkdir", "-p", posixpath.dirname(remote))
        _push(serial, local, remote, failed)
    adb.shell(serial, "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")


def apply(target, layout, systems, dry_run):
    """Set the wanted RetroArch and ES-DE settings on the device; 0, or 1 when a write failed. adb errors propagate."""
    serial = target.serial
    pkg = android.retroarch_package(serial)
    tmp = tempfile.mkdtemp(prefix="sync-roms-apply-")
    failed = []
    try:
        ra_entries, cfg_remote = _retroarch_part(serial, pkg, tmp)
        gamelists = _esde_part(serial, target.volume, layout["roms_dir"], systems, tmp)
        esde_entries = [g[0] for g in gamelists]
        applied.show(ra_entries + esde_entries, dry_run)
        if dry_run:
            return 0
        if any(applied.changed(e) for e in ra_entries):
            _write_retroarch(serial, pkg, cfg_remote, tmp, failed)
        if any(applied.changed(e) for e in esde_entries):
            _write_esde(serial, target.volume, gamelists, tmp, failed)
        return 1 if failed else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
