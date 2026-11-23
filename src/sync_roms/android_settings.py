"""The retroarch.cfg and ES-DE gamelist edits `config apply` makes on an Android device, as text in, text out, and `apply`, which reads and writes them over adb."""
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
from xml.sax.saxutils import escape, unescape

from . import adb, android, apk, applied, inventory, raofflineproxy, runtime, s3, spruce_syncthing, store, ui, usersettings

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


def apk_rules(card_name):
    """A function of an APK's file name: None to install it, else why this card's device skips it."""
    card = store.saved_card(card_name)
    device_id = card.get("device", "full")
    data = store.repo_json("device-systems")
    tiers = [t["id"] for t in data["tiers"]]
    device = next((d for d in store.load_catalog()["devices"] if d["id"] == device_id), None)  # None: `full`, which has everything
    tier = data["devices"].get(device_id, {}).get("tier") if device else None
    rules = store.repo_json("android-apks")["apks"]
    proxy_on = store.card_flag(card, "raofflineproxy")

    def reason(name):
        if raofflineproxy.APK_NAME.fullmatch(name) and not proxy_on:
            return "RAOfflineProxy is off for this card"
        for rule in rules:
            if not name.lower().startswith(rule["prefix"].lower()):
                continue
            if rule.get("never"):
                return "not needed"
            if device is None:
                continue
            if "tier" in rule and (tier not in tiers or tiers.index(tier) < tiers.index(rule["tier"])):
                return "device is below the Nova's tier"
            if "systems" in rule and not set(rule["systems"]) & set(device["systems"]):
                return "device doesn't play Switch"
            if rule.get("dualscreen") and not device.get("screen2"):
                return "not a dual-screen device"
        return None
    return reason


def _card_copy(serial, volume, name, size):
    """The card's copy of the APK when it is there at storage's size, else None."""
    path = f"/storage/{volume}/APKs/{name}"
    if not adb.is_file(serial, path):
        return None
    try:
        return path if int(adb.shell(serial, "stat", "-c", "%s", path).strip()) == size else None
    except ValueError:
        return None


def _fetch(key, size, tmp):
    """The storage APK as a local file: in place for folder storage, else downloaded once into tmp (see _forget)."""
    if s3.read_root():
        return s3.safe_join(s3.read_root(), key)
    local = os.path.join(tmp, "apks", posixpath.basename(key))
    s3.download((key, local, size))
    return local


def _read_manifest(serial, card_path, key, size, tmp):
    """(package, versionCode, local copy or None): from the card's copy when it has one, else from storage's, fetched."""
    if card_path:
        try:
            return (*apk.manifest(adb.exec_out(serial, "/system/bin/unzip", "-p", card_path, "AndroidManifest.xml")), None)
        except (adb.AdbError, ValueError):
            pass
    local = _fetch(key, size, tmp)
    with zipfile.ZipFile(local) as z:
        return (*apk.manifest(z.read("AndroidManifest.xml")), local)


def _forget(tmp, name):
    """Remove the downloaded copy of the APK, when there is one."""
    try:
        os.remove(os.path.join(tmp, "apks", name))
    except OSError:
        pass


def apk_entries(serial, volume, card_name, listing, tmp):
    """Generator of (file name, key, size, state, package, new version, old version, card path, local copy) for each APK in the
    listing {key: size}. state: install, upgrade, current, newer, or the skip reason in parentheses; unreadable ones are
    warned about and left out. A downloaded copy stays in tmp until the caller is done with the entry (_forget)."""
    if not any(not k.endswith("/") and k.lower().endswith(".apk") for k in listing):
        return
    reason = apk_rules(card_name)
    installed = {line[8:].strip() for line in adb.shell(serial, "pm", "list", "packages").splitlines() if line.startswith("package:")}
    for key, size in sorted(listing.items()):
        name = posixpath.basename(key)
        if key.endswith("/") or not name.lower().endswith(".apk"):
            continue
        skip = reason(name)
        if skip:
            yield (name, key, size, f"skipped ({skip})", None, None, None, None, None)
            continue
        card_path = _card_copy(serial, volume, name, size)
        try:
            pkg, new, local = _read_manifest(serial, card_path, key, size, tmp)
        except (ValueError, KeyError, zipfile.BadZipFile, *s3.ERRORS) as e:
            ui.warn(f"Can't read {name}: {e}; skipping it")
            _forget(tmp, name)
            continue
        old = adb.installed_version(serial, pkg) if pkg in installed else None
        if pkg not in installed:
            state = "install"
        elif old is None:
            ui.warn(f"Can't read the installed version of {pkg}: skipping {name}")
            _forget(tmp, name)
            continue
        else:
            state = "upgrade" if new > old else "current" if new == old else "newer"
        yield (name, key, size, state, pkg, new, old, card_path, local)


def _show_apks(entries):
    print(ui.dim("🧪 Dry run: APKs"))
    for name, _, _, state, _, new, old, _, _ in entries:
        what = {"install": "would install", "upgrade": f"would upgrade {old} → {new}", "current": "up to date",
                "newer": f"left alone (installed {old} is newer than {new})"}.get(state, state)
        print(f"   {name}: {what}")


def _install(serial, entry, tmp):
    """Install or upgrade one APK, from the card's copy when it has one, else from storage's; an error message, or None."""
    name, key, size, state, pkg, new, old, card_path, local = entry
    replace = state == "upgrade"
    if card_path:
        out = adb.shell(serial, "pm", "install", *(["-r"] if replace else []), card_path, check=False)
        if "Success" in out:
            return None
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
            return out.strip()
    try:
        adb.install(serial, local or _fetch(key, size, tmp), replace)
    except (adb.AdbError, *s3.ERRORS) as e:
        return str(e)
    return None


def _install_apks(serial, entries, tmp, failed):
    """Install each entry as it is read, removing its download when done."""
    for entry in entries:
        name, _, _, state, pkg, new, old, _, _ = entry
        if state not in ("install", "upgrade"):
            _forget(tmp, name)
            continue
        print(f"📦 Installing {name}" if state == "install" else f"⬆️ Upgrading {name} ({old} → {new})")
        error = _install(serial, entry, tmp)
        _forget(tmp, name)
        if error is None:
            continue
        failed.append(name)
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in error:
            ui.warn(f"Couldn't upgrade {name}: it is signed differently from the installed {pkg}; uninstall that app by hand first")
        else:
            ui.warn(f"Couldn't install {name}: {error}")


def _apk_part(serial, target, tmp, dry_run, failed):
    """List (dry run) or install the APKs; a storage error warns and counts as a failure, an adb one propagates."""
    try:
        entries = apk_entries(serial, target.volume, target.card, inventory.files(runtime.APKS_PREFIX, sizes=True), tmp)
        if dry_run:
            shown = []
            for entry in entries:
                shown.append(entry)
                _forget(tmp, entry[0])
            if shown:
                _show_apks(shown)
        else:
            _install_apks(serial, entries, tmp, failed)
    except s3.ERRORS as e:
        ui.warn(f"Couldn't read the APKs from storage: {e}")
        failed.append("APKs")


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
            _apk_part(serial, target, tmp, True, failed)
            return 1 if failed else 0
        if any(applied.changed(e) for e in ra_entries):
            _write_retroarch(serial, pkg, cfg_remote, tmp, failed)
        if any(applied.changed(e) for e in esde_entries):
            _write_esde(serial, target.volume, gamelists, tmp, failed)
        _apk_part(serial, target, tmp, False, failed)
        return 1 if failed else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
