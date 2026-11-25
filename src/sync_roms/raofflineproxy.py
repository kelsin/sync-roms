"""RAOfflineProxy (the RetroAchievements offline proxy) from storage's os/<layout>/ folders, put on cards that have it on."""
import os
import re
import tempfile
import zipfile
from pathlib import PurePosixPath

from . import inventory, runtime, s3, store, ui

# layout: (storage prefix, file name pattern, folder in the zip holding the app (None: the file is copied as it is), where it goes on the card)
KINDS = {
    "onion": (runtime.ONION_PREFIX, r"RAOfflineProxy-Onion-v[^/]+\.zip", "App/RAOfflineProxy", "App/RAOfflineProxy"),
    "allium": (runtime.ALLIUM_PREFIX, r"RAOfflineProxy-Allium-v[^/]+\.zip", "Apps/RAOfflineProxy.pak", "Apps/RAOfflineProxy.pak"),
    "muos": (runtime.MUOS_PREFIX, r"RAOfflineProxy-muOS-v[^/]+\.muxapp", "RAOfflineProxy", "MUOS/application/RAOfflineProxy"),
    "knulli": (runtime.KNULLI_PREFIX, r"RAOfflineProxy-Knulli-v[^/]+-Install\.sh", None, "roms/tools/RAOfflineProxy Install.sh"),
    # not Tools (on internal storage, out of reach): Ports runs a .sh from the card
    "rocknix": (runtime.ROCKNIX_PREFIX, r"RAOfflineProxy-Rocknix-v[^/]+-Install\.sh", None, "roms/ports/RAOfflineProxy Install.sh"),
}
LAUNCH = "launch.sh"
ANDROID_PACKAGE = "com.raofflineproxy"
APK_NAME = re.compile(r"RAOfflineProxy.*\.apk")  # the Android build, in os/android/APKs/


def prefixes():
    return sorted({k[0] for k in KINDS.values()})


def _check(z, root):
    """Raise ValueError unless every member is a plain file or folder under root (or a folder leading to it) and launch.sh exists."""
    parts = PurePosixPath(root).parts
    names = set()
    for info in z.infolist():
        path = PurePosixPath(info.filename)
        ok = path.parts[:len(parts)] == parts or (info.is_dir() and path.parts == parts[:len(path.parts)])
        if path.is_absolute() or ".." in path.parts or not ok:
            raise ValueError(f"unexpected path {info.filename!r}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"{info.filename!r} is a symlink")
        names.add(info.filename)
    if f"{root}/{LAUNCH}" not in names:
        raise ValueError(f"{root}/{LAUNCH} is missing")


def _write(target, data, executable):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    store.replace_file(target, data)
    os.chmod(target, 0o755 if executable else 0o644)


def _extract(z, root, folder):
    """Overwrite the app's files in place: the app keeps its login and settings in its own folder."""
    for info in z.infolist():
        if info.is_dir():
            continue
        rel = PurePosixPath(info.filename).relative_to(root)
        executable = bool((info.external_attr >> 16) & 0o111) or rel.suffix == ".sh"
        _write(os.path.join(folder, *rel.parts), z.read(info), executable)


def install(card, layout_name, base, dry_run):
    """Put the newest RAOfflineProxy file on a card with the setting on, once per file name. The failure count."""
    if layout_name not in KINDS:
        return 0
    entry = store.saved_card(card)
    if not store.card_flag(entry, "raofflineproxy"):
        return 0
    prefix, pattern, root, dest = KINDS[layout_name]
    listing = inventory.files(prefix)
    key = inventory.newest(listing, prefix, pattern)
    if not key:
        return 0
    name = key[len(prefix):]
    target = os.path.join(base, *dest.split("/"))
    old = entry.get("raofflineproxy_app")
    if old == name and (root is None or os.path.isfile(os.path.join(target, LAUNCH))):
        return 0
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would install RAOfflineProxy {name} at {dest}"))
        return 0
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app")
            s3.download((key, path, listing[key]))
            if root is None:
                with open(path, "rb") as f:
                    _write(target, f.read(), True)
            else:
                with zipfile.ZipFile(path) as z:
                    _check(z, root)
                    _extract(z, root, target)
    except (OSError, zipfile.BadZipFile, ValueError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't install RAOfflineProxy {name} on the card: {e}")
        return 1
    store.update_card(card, raofflineproxy_app=name)
    print(f"🏆 RAOfflineProxy {ui.green(name)} → {dest}")
    return 0
