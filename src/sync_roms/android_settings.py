"""The retroarch.cfg and ES-DE gamelist edits `config apply` makes on an Android device, as text in, text out (no adb)."""
import re
from xml.sax.saxutils import escape, unescape

from . import android, applied, spruce_syncthing, store, usersettings

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
