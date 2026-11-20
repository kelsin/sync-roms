"""RAOfflineProxy (the RetroAchievements offline proxy) from storage's os/<layout>/ folders, put on cards that have it on."""
import os
import re
import tempfile
import zipfile
from pathlib import PurePosixPath

from . import inventory, onion_surprise, runtime, s3, store, ui

# layout: (storage prefix, file name pattern, folder in the zip holding the app (None: the file is copied as it is), where it goes on the card)
KINDS = {
    "onion": (runtime.ONION_PREFIX, r"RAOfflineProxy-Onion-v[^/]+\.zip", "App/RAOfflineProxy", "App/RAOfflineProxy"),
    "allium": (runtime.ALLIUM_PREFIX, r"RAOfflineProxy-Allium-v[^/]+\.zip", "Apps/RAOfflineProxy.pak", "Apps/RAOfflineProxy.pak"),
    "muos": (runtime.MUOS_PREFIX, r"RAOfflineProxy-muOS-v[^/]+\.muxapp", "RAOfflineProxy", "MUOS/application/RAOfflineProxy"),
    "knulli": (runtime.KNULLI_PREFIX, r"RAOfflineProxy-Knulli-v[^/]+-Install\.sh", None, "roms/tools/RAOfflineProxy Install.sh"),
}
LAUNCH = "launch.sh"


def prefixes():
    return sorted({k[0] for k in KINDS.values()})


def newest(layout, listing):
    """The storage key of the newest RAOfflineProxy file for the layout in the listing (digit runs compared as numbers), or None."""
    prefix, pattern = KINDS[layout][:2]
    keys = [k for k in listing if re.fullmatch(pattern, k[len(prefix):]) and k.startswith(prefix)]
    return max(keys, key=lambda k: onion_surprise._natural(k[len(prefix):]), default=None)


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
    entry = store.load_cards().get(card)
    if not store.card_flag(entry, "raofflineproxy"):
        return 0
    prefix, _, root, dest = KINDS[layout_name]
    listing = inventory.files(prefix)
    key = newest(layout_name, listing)
    if not key:
        return 0
    name = key[len(prefix):]
    target = os.path.join(base, *dest.split("/"))
    old = entry.get("raofflineproxy_app") if isinstance(entry, dict) else None
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
