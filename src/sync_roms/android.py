"""An Android device over adb: its SD card, RetroArch and RetroArch's save folders."""
from collections import namedtuple

from . import adb, ui

Folders = namedtuple("Folders", "saves states sort_saves sort_states")

DEFAULT_SAVES = "/storage/emulated/0/RetroArch/saves"
DEFAULT_STATES = "/storage/emulated/0/RetroArch/states"
NOT_SUPPORTED = (
    ("savefiles_in_content_dir", "Save files in the content folder"),
    ("savestates_in_content_dir", "Save states in the content folder"),
    ("sort_savefiles_by_content_enable", "Sort save files into folders by content directory"),
    ("sort_savestates_by_content_enable", "Sort save states into folders by content directory"),
)


def is_android(entry):
    return entry.get("layout") == "esde" and entry.get("device") != "windows-pc"


def card_volumes(serial, roms_dir):
    """The ids of the SD cards and USB drives that hold the ROM folder."""
    ids = [i for i in adb.shell(serial, "ls", "/storage").split() if i not in ("emulated", "self")]
    return [i for i in ids if adb.shell_ok(serial, "test", "-d", f"/storage/{i}/{roms_dir}")]


def retroarch_package(serial):
    from . import picker
    out = adb.shell(serial, "pm", "list", "packages")
    pkgs = [line[8:].strip() for line in out.splitlines() if line.startswith("package:com.retroarch")]
    if not pkgs:
        model = next((d.model for d in adb.devices() if d.serial == serial and d.model), serial)
        ui.fail(f"No RetroArch installed on {model}", 2)
    if len(pkgs) == 1:
        return pkgs[0]
    pick = picker.filter_list("🕹️  Which RetroArch?", pkgs)
    if pick is None:
        raise SystemExit(0)
    return pkgs[pick]


def parse_config(text):
    out = {}
    for line in text.splitlines():
        key, eq, value = line.partition("=")
        if eq:
            out[key.strip()] = value.strip().strip('"')
    return out


def ra_folders(cfg):
    for key, label in NOT_SUPPORTED:
        if cfg.get(key) == "true":
            ui.fail(f"RetroArch's \"{label}\" ({key}) is on: turn it off in RetroArch's settings", 2)

    def folder(key, default):
        value = cfg.get(key, "")
        return default if value in ("", "default") else value.rstrip("/")
    return Folders(folder("savefile_directory", DEFAULT_SAVES), folder("savestate_directory", DEFAULT_STATES),
                   cfg.get("sort_savefiles_enable") == "true", cfg.get("sort_savestates_enable") == "true")


def read_folders(serial, pkg):
    path = f"/storage/emulated/0/Android/data/{pkg}/files/retroarch.cfg"
    try:
        text = adb.shell(serial, "cat", path)
    except adb.AdbError as e:
        ui.fail(f"Can't read RetroArch's settings at {path}: {e}", 2)
    return ra_folders(parse_config(text))


def running(serial, pkg):
    return adb.shell_ok(serial, "pidof", pkg)


def wait_closed(serial, pkg):
    while running(serial, pkg):
        print("RetroArch is open on the device: save in-game, then close RetroArch on the device.")
        if not ui.confirm("Closed it? (Enter checks again)", default=True):
            print(ui.yellow("↩️  Stopped: RetroArch is still open"))
            raise SystemExit(0)
