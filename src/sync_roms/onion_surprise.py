"""The Surprise app zip from storage, installed under App/Surprise/ on Onion cards."""
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import PurePosixPath

from . import inventory, runtime, s3, store, surprise, ui

LAYOUT = "onion"
ROOT = "App/Surprise"
REQUIRED = (f"{ROOT}/config.json", f"{ROOT}/surprise")
EXECUTABLE = ("surprise", "launch.sh")


def _natural(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def _newest(listing):
    keys = [k for k in listing if re.fullmatch(r"Surprise-v\d+(\.\d+)*\.zip", k[len(runtime.ONION_PREFIX):])]
    return max(keys, key=lambda k: _natural(k[len(runtime.ONION_PREFIX):]), default=None)


def newest_zip():
    """The storage key of the newest Surprise-v<version>.zip in os/onion/ (digit runs compared as numbers), or None."""
    return _newest(inventory.files(runtime.ONION_PREFIX, sizes=False))


def _check(z):
    """Raise ValueError unless every member is a plain file under App/Surprise/ and the required ones exist."""
    names = set()
    for info in z.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("App", "Surprise"):
            raise ValueError(f"unexpected path {info.filename!r}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"{info.filename!r} is a symlink")
        names.add(info.filename)
    for required in REQUIRED:
        if required not in names:
            raise ValueError(f"{required} is missing")


def _extract(z, folder):
    for info in z.infolist():
        if info.is_dir():
            continue
        rel = PurePosixPath(info.filename).relative_to(ROOT)
        target = os.path.join(folder, *rel.parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if rel.name in EXECUTABLE:
            os.chmod(target, 0o755)


def install(card, layout_name, base, dry_run):
    """Install the newest Surprise app on an Onion card with Surprise on, once per zip. The failure count."""
    if layout_name != LAYOUT:
        return 0
    entry = store.load_cards().get(card)
    if not surprise.enabled(entry):
        return 0
    listing = inventory.files(runtime.ONION_PREFIX)
    key = _newest(listing)
    if not key:
        return 0
    name = key[len(runtime.ONION_PREFIX):]
    app = os.path.join(base, "App", "Surprise")
    old = entry.get("surprise_app") if isinstance(entry, dict) else None
    present = all(os.path.isfile(os.path.join(app, f)) for f in ("config.json", "surprise"))
    if old == name and present:
        return 0
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would install Surprise app {name} at App/Surprise"))
        return 0
    new = os.path.join(base, "App", ".Surprise.new")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "surprise.zip")
            s3.download((key, path, listing[key]))
            with zipfile.ZipFile(path) as z:
                _check(z)
                shutil.rmtree(new, ignore_errors=True)
                _extract(z, new)
        shutil.rmtree(app, ignore_errors=True)
        os.replace(new, app)
    except (OSError, zipfile.BadZipFile, ValueError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't install the Surprise app {name} on the card: {e}")
        shutil.rmtree(new, ignore_errors=True)
        return 1
    store.update_card(card, surprise_app=name)
    print(f"🎁 Surprise app {ui.green(name)} → App/Surprise")
    return 0
