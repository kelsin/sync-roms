"""`config apply` for an `emudeck` card, run on the Steam Deck or Steam Machine itself: RetroArch's settings in EmuDeck's
Flatpak RetroArch, ES-DE's emulator per system, and Syncthing for RetroArch's save and state folders."""
import os
import subprocess

from . import android, android_settings, applied, frontend, steamos_syncthing, store, ui

RA_DIR = "~/.var/app/org.libretro.RetroArch/config/retroarch"
RA_PROCESS = "org.libretro.RetroArch"
ESDE_PROCESS = "es-de"
# EmuDeck's settings: functions/all.sh sources ~/.config/EmuDeck/settings.sh ($emudeckFolder, vars.sh) when it is a file
# and not a symlink, else ~/emudeck/settings.sh. Its Cloud Saves are on with cloud_sync_status=true (setSetting in
# functions/ToolScripts/emuDeckCloudSync.sh; helperFunctions.sh syncs only when "$cloud_sync_status" == "true").
# github.com/dragoonDorise/EmuDeck, main at d181675e.
EMUDECK_SETTINGS = ("~/.config/EmuDeck/settings.sh", "~/emudeck/settings.sh")
SAVE_KEYS = ("savefile_directory", "savestate_directory")


def folders(cfg_text, ra_dir):
    """{"saves", "states"}: RetroArch's save and state folders, as real paths (Syncthing doesn't follow symlinks)."""
    cfg = android.parse_config(cfg_text)
    result = {}
    for name, key in (("saves", "savefile_directory"), ("states", "savestate_directory")):
        value = cfg.get(key, "")
        if not value or value == "default":
            value = os.path.join(ra_dir, name)
        elif value.startswith(":"):  # RetroArch's own folder
            value = os.path.join(ra_dir, value[1:].lstrip("/"))
        result[name] = os.path.realpath(os.path.expanduser(value))
    return result


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _emudeck_settings():
    """The text of EmuDeck's settings.sh, the one EmuDeck itself reads, or None."""
    for i, path in enumerate(os.path.expanduser(p) for p in EMUDECK_SETTINGS):
        if os.path.isfile(path) and (i or not os.path.islink(path)):
            try:
                return _read(path)
            except (OSError, UnicodeDecodeError):
                return None
    return None


def warnings(ra_dir, emudeck_settings):
    """What else writes or moves RetroArch's saves: EmuDeck's Cloud Saves, per-core overrides of the save folders."""
    result = []
    if emudeck_settings and android.parse_config(emudeck_settings).get("cloud_sync_status") == "true":
        result.append("EmuDeck's Cloud Saves are on: they sync the same save folders as Syncthing; turn them off in EmuDeck")
    config = os.path.join(ra_dir, "config")
    try:
        cores = sorted(e.path for e in os.scandir(config) if e.is_dir())
    except OSError:
        cores = []
    for core in cores:
        for path in sorted(e.path for e in os.scandir(core) if e.is_file() and e.name.endswith(".cfg")):
            try:
                cfg = android.parse_config(_read(path))
            except (OSError, UnicodeDecodeError):
                continue
            for key in SAVE_KEYS:
                if key in cfg:
                    result.append(f"{path} sets {key}: remove that line, or this core's saves stay out of the shared folders")
    return result


def _running(pattern):
    """Whether a process whose command line matches pattern runs; no pgrep counts as not running."""
    try:
        return subprocess.run(["pgrep", "-f", pattern], capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def _wait_closed():
    """Wait for RetroArch to close (it rewrites its cfg on quit); without a terminal, fail."""
    while _running(RA_PROCESS):
        if ui.ASSUME_YES or not ui.has_terminal():
            ui.fail("RetroArch is open: save in-game, close it, then run again", 1)
        print("RetroArch is open: save in-game, then close RetroArch.")
        if not ui.confirm("Closed it? (Enter checks again)", default=True):
            print(ui.yellow("↩️  Stopped: RetroArch is still open"))
            raise SystemExit(0)


def _write(path, text, failed):
    """True when the file was written."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.replace_file(path, text, newline="")
    except OSError as e:
        failed.append(path)
        ui.warn(f"Couldn't write {path}: {e}")
        return False
    return True


def _esde_part(base, layout, systems):
    """[(Entry, gamelist path, text or None, label)] for the wanted ES-DE folders the card has; [] with a warning when this
    computer's ES-DE doesn't serve the card."""
    roms = os.path.join(base, layout["roms_dir"])
    have = {s["folders"]["esde"] for s in systems if s.get("folders", {}).get("esde")}
    wanted = [(f, label) for f, label in android_settings.esde_wanted(have) if os.path.isdir(os.path.join(roms, f))]
    if not wanted:
        return []
    problem = frontend.emudeck_problem(base, roms)
    if problem:
        ui.warn(f"{problem}: skipping ES-DE's emulators")
        return []
    gamelists = os.path.join(frontend.esde_dir("emudeck", base), "gamelists")
    result = []
    for folder, label in wanted:
        path = os.path.join(gamelists, folder, "gamelist.xml")
        try:
            text = _read(path) if os.path.isfile(path) else None
        except (OSError, UnicodeDecodeError) as e:
            ui.warn(f"Can't read {path}: {e}; skipping it")
            continue
        if text and text.strip() and "<gameList" not in text:
            ui.warn(f"Can't read {path} as a gamelist: skipping it")
            continue
        result.append((android_settings.gamelist_entry(folder, text, label), path, text, label))
    return result


def _write_esde(gamelists, failed):
    if _running(ESDE_PROCESS) and not ui.confirm(
            "ES-DE is open and rewrites its gamelists when it quits: quit it first. Write the gamelists now?", default=False):
        print(ui.dim("↩️  Left ES-DE's gamelists as they are"))
        return
    for entry, path, text, label in gamelists:
        if applied.changed(entry) and _write(path, android_settings.gamelist_apply(text, label), failed):
            applied.show([entry], False)


def apply(base, layout, systems, dry_run):
    """Set the wanted RetroArch, ES-DE and Syncthing settings on this computer for the card at base; 0, or 1 when a write failed."""
    ra_dir = os.path.expanduser(RA_DIR)
    cfg = os.path.join(ra_dir, android_settings.CFG)
    wanted = android_settings.cfg_wanted(platform="steamos")
    failed = []
    try:
        text = _read(cfg)
    except (OSError, UnicodeDecodeError):
        text = None
        ui.warn(f"Can't read RetroArch's settings at {cfg}: skipping them and Syncthing (open RetroArch once, then run again)")
    ra_entries = android_settings.cfg_entries(text, wanted) if text is not None else []
    gamelists = _esde_part(base, layout, systems)
    if dry_run:
        applied.show(ra_entries + [g[0] for g in gamelists], True)
    else:
        if any(applied.changed(e) for e in ra_entries):
            _wait_closed()
            text = _read(cfg)
            ra_entries = android_settings.cfg_entries(text, wanted)
            if any(applied.changed(e) for e in ra_entries) and _write(cfg, android_settings.cfg_apply(text, ra_entries), failed):
                applied.show(ra_entries, False)
        if any(applied.changed(g[0]) for g in gamelists):
            _write_esde(gamelists, failed)
    for warning in warnings(ra_dir, _emudeck_settings()):
        ui.warn(warning)
    if text is not None:
        steamos_syncthing.apply(folders(text, ra_dir), dry_run, failed)
    return 1 if failed else 0
