"""The official PICO-8 zip from storage, put where each frontend installs it from."""
import os
import re
import tempfile
import zipfile

from . import inventory, runtime, s3, store, ui

TARGETS = {
    "esde": ("zip", "PICO-8/{name}"),
    "knulli": ("zip", "roms/pico8/{name}"),
    "onion": ("extract", "RApp/PICO-8/bin"),
    "allium": ("extract", "Apps/pico.pak/bin"),
    "spruce": ("extract", "BIOS"),
    "rocknix": ("extract", "roms/pico-8"),
    "muos": ("extract", "MUOS/bios/pico8"),
}
EXTRACT = ("pico-8/pico8_dyn", "pico-8/pico8.dat")
EXTRACT_MORE = {"spruce": ("pico-8/pico8_64",),  # spruce also wants the 64-bit binary, for its Miyoo Flip
                "rocknix": ("pico-8/pico8_64",)}  # and so does ROCKNIX (aarch64)
ONLY = {"muos": ("pico-8/pico8_64", "pico-8/pico8.dat")}  # muOS's launcher runs pico8_64 alone


def members(layout_name):
    return ONLY.get(layout_name) or EXTRACT + EXTRACT_MORE.get(layout_name, ())


def _natural(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def _newest(listing):
    keys = [k for k in listing if re.fullmatch(r"pico-8_.*_raspi\.zip", k[len(runtime.PICO8_PREFIX):])]
    return max(keys, key=lambda k: _natural(k[len(runtime.PICO8_PREFIX):]), default=None)


def newest_zip():
    """The storage key of the newest pico-8_*_raspi.zip in os/pico8/ (digit runs compared as numbers), or None."""
    return _newest(inventory.files(runtime.PICO8_PREFIX, sizes=False))


def _path(base, layout_name, name):
    kind, template = TARGETS[layout_name]
    return kind, os.path.join(base, *template.format(name=name).split("/"))


def _extract(key, size, folder, layout_name):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "pico8.zip")
        s3.download((key, path, size))
        os.makedirs(folder, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for member in members(layout_name):
                target = os.path.join(folder, os.path.basename(member))
                store.replace_file(target, z.read(member))
                if member.endswith(("pico8_dyn", "pico8_64")):
                    os.chmod(target, 0o755)


def run(card, layout_name, base, dry_run, wrote=None):
    """Put the newest PICO-8 zip on the card the way its layout installs it, once per zip (again when it is missing
    from the card). The failure count.
    wrote, a list, gets the card path of what was put there."""
    if layout_name not in TARGETS:
        return 0
    listing = inventory.files(runtime.PICO8_PREFIX)
    key = _newest(listing)
    if not key:
        return 0
    name = key[len(runtime.PICO8_PREFIX):]
    kind, target = _path(base, layout_name, name)
    entry = store.load_cards().get(card)
    old = entry.get("pico8") if isinstance(entry, dict) else None
    old = old if isinstance(old, str) else None
    if kind == "extract":
        missing = any(not os.path.isfile(os.path.join(target, os.path.basename(m))) for m in members(layout_name))
    else:
        missing = not os.path.isfile(target)
    if old == name and not missing:
        return 0
    old_path = _path(base, layout_name, old)[1] if old and old != name and kind == "zip" else None
    old_path = old_path if old_path and os.path.isfile(old_path) else None
    shown = os.path.relpath(target, base)
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would put PICO-8 {name} at {shown}" + (f" and delete {os.path.relpath(old_path, base)}" if old_path else "")))
        return 0
    try:
        if kind == "zip":
            s3.download((key, target, listing[key]))
        else:
            _extract(key, listing[key], target, layout_name)
    except (OSError, zipfile.BadZipFile, KeyError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't put PICO-8 {name} on the card: {e}")
        return 1
    if old_path:
        os.remove(old_path)
    if wrote is not None:
        wrote.append(target)
    store.update_card(card, pico8=name)
    print(f"🕹️  PICO-8 {ui.green(name)} → {shown}")
    return 0


def keep_in(dest, card, layout_name=None):
    """Names in a pico8 ROM folder that the extras check must keep: the card's recorded zip, the Splore files, and the
    extracted runtime when the layout installs it into this folder (ROCKNIX)."""
    entry = store.load_cards().get(card)
    recorded = entry.get("pico8") if isinstance(entry, dict) else None
    keep = {recorded} if isinstance(recorded, str) else set()
    if layout_name == "rocknix":
        keep |= {os.path.basename(m) for m in members(layout_name)}
    if os.path.isdir(dest):
        keep |= {n for n in os.listdir(dest) if n.lower().startswith("splore") or "with splore" in n.lower()}
    return keep
