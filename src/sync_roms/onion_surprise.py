"""The Surprise app zip from storage, installed under App/Surprise/ on Onion cards."""
import json
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
from pathlib import PurePosixPath

from . import downloads, inventory, runtime, s3, store, surprise, ui

LAYOUT = "onion"
PATTERN = r"Surprise-v\d+(\.\d+)*\.zip"
ROOT = "App/Surprise"
REQUIRED = (f"{ROOT}/config.json", f"{ROOT}/surprise")
EXECUTABLE = ("surprise", "launch.sh")
ICON = "Icons/Default/app/surprise.png"  # the app's icon, optional in the zip, written to the same path on the card
ICON_DIRS = ("Icons/", "Icons/Default/", "Icons/Default/app/")


def _check(z):
    """Raise ValueError unless every member is a plain file under App/Surprise/ (or the icon, or a directory leading to
    it) and the required ones exist."""
    names = set()
    for info in z.infolist():
        path = PurePosixPath(info.filename)
        extra = info.filename == ICON or (info.is_dir() and info.filename in ICON_DIRS)
        if path.is_absolute() or ".." in path.parts or (path.parts[:2] != ("App", "Surprise") and not extra):
            raise ValueError(f"unexpected path {info.filename!r}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"{info.filename!r} is a symlink")
        names.add(info.filename)
    for required in REQUIRED:
        if required not in names:
            raise ValueError(f"{required} is missing")


def _extract(z, folder):
    for info in z.infolist():
        if info.is_dir() or not info.filename.startswith(ROOT + "/"):
            continue
        rel = PurePosixPath(info.filename).relative_to(ROOT)
        target = os.path.join(folder, *rel.parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if len(rel.parts) == 1 and rel.name in EXECUTABLE:
            os.chmod(target, 0o755)


def install(card, layout_name, base, dry_run):
    """Install the newest Surprise app on an Onion card with Surprise and collections on, once per zip. The failure count."""
    if layout_name != LAYOUT:
        return 0
    entry = store.saved_card(card)
    if not surprise.enabled(entry) or not store.card_flag(entry, "custom_collections"):
        return 0
    listing = inventory.files(runtime.ONION_PREFIX)
    key = inventory.newest(listing, runtime.ONION_PREFIX, PATTERN)
    if not key:
        return 0
    name = key[len(runtime.ONION_PREFIX):]
    app = os.path.join(base, "App", "Surprise")
    old = entry.get("surprise_app")
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
                icon = z.read(ICON) if ICON in z.namelist() else None
        shutil.rmtree(app, ignore_errors=True)
        os.replace(new, app)
        if icon is not None:
            target = os.path.join(base, *ICON.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(icon)
    except (OSError, zipfile.BadZipFile, ValueError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't install the Surprise app {name} on the card: {e}")
        shutil.rmtree(new, ignore_errors=True)
        return 1
    store.update_card(card, surprise_app=name)
    print(f"🎁 Surprise app {ui.green(name)} → App/Surprise")
    return 0


SD = "/mnt/SDCARD"
BAD = re.compile(r'["\\:\x00-\x1f]')
MAX_VALUE = 256
MAX_LINE = 1024


def emu_folders(base):
    """{ROM folder under Roms/: (Emu folder, launch file)} from the card's Emu/*/config.json files.

    Several Emu folders for one ROM folder: the one named like it, else the first by name.
    """
    found = {}
    emu = os.path.join(base, "Emu")
    for name in sorted(os.listdir(emu)) if os.path.isdir(emu) else ():
        try:
            with open(os.path.join(emu, name, "config.json"), encoding="utf-8") as f:
                config = json.load(f)
            rompath, launch = config["rompath"], config["launch"]
            if not (isinstance(rompath, str) and isinstance(launch, str)):
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        parts = posixpath.normpath(f"Emu/{name}/{rompath}").split("/")
        if len(parts) == 2 and parts[0] == "Roms":
            if parts[1] not in found or name == parts[1]:
                found[parts[1]] = (name, launch)
    return found


def _label(title):
    return re.sub(r" {2,}", " ", BAD.sub("", title)).strip()


def lines(base, roms_dir, surprises, folder_of):
    """The surprise.json lines for the surprises whose ROM is on the card and has an Emu folder."""
    emus = emu_folders(base)
    out = []
    for item in surprises:
        folder = folder_of.get(item.get("system"))
        if folder not in emus:
            continue
        rel = downloads.rom_rel(item["bucket"])
        if not os.path.isfile(os.path.join(roms_dir, folder, *rel.split("/"))):
            continue
        emu, launch = emus[folder]
        root = f"{SD}/Emu/{emu}/../../Roms/{folder}"
        entry = {"label": _label(item.get("title", "")), "rompath": f"{root}/{rel}"}
        stem = os.path.splitext(rel)[0]
        if "/" not in rel and os.path.isfile(os.path.join(roms_dir, folder, "Imgs", stem + ".png")):
            entry["imgpath"] = f"{root}/Imgs/{stem}.png"
        entry["launch"] = f"{SD}/Emu/{emu}/{launch}"
        values = [v for k, v in entry.items() if k != "label"]
        if not entry["label"] or any(BAD.search(v) for v in values):
            continue
        if any(len(v.encode()) >= MAX_VALUE for v in (*values, entry["label"])):
            continue
        entry["type"] = 5
        line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
        if len(line.encode()) < MAX_LINE:
            out.append(line)
    return out


def write_list(card, layout_name, base, roms_dir, systems, dry_run):
    """Write Roms/surprise.json from the card's surprises, or remove it when there are none. Whether the card changed."""
    if layout_name != LAYOUT:
        return False
    entry = store.saved_card(card)
    wanted = []
    if surprise.enabled(entry) and store.card_flag(entry, "custom_collections"):
        folder_of = {s["bucket"]: s["folders"]["onion"] for s in systems if s["folders"].get("onion")}
        surprises = [x for x in entry.get("surprises") or () if isinstance(x, dict)
                     and isinstance(x.get("system"), str) and isinstance(x.get("bucket"), str)]
        wanted = lines(base, roms_dir, surprises, folder_of)
    path = os.path.join(roms_dir, "surprise.json")
    text = "".join(line + "\n" for line in wanted)
    try:
        with open(path, encoding="utf-8") as f:
            current = f.read()
    except OSError:
        current = None
    if (text or None) == current:
        return False
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would {'write' if text else 'remove'} Roms/surprise.json"
                     + (f" ({len(wanted)} game(s) on the card)" if text else "")))
        return False
    try:
        if text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            os.remove(path)
    except OSError as e:
        ui.warn(f"Couldn't update Roms/surprise.json on the card: {e}")
        return False
    return True
