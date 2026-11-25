"""The empty PICO-8 Splore launcher spruceOS ships in Roms/PICO8/, put back on a spruce card that lacks it."""
import os

from . import downloads, store, ui

FOLDER = os.path.join("Roms", "PICO8")
NAME = downloads.SPRUCE_FILES["pico8"][0]


def install(card, layout_name, base, dry_run):
    """Create the empty Splore launcher in a spruce card's Roms/PICO8/ when it's missing. The failure count."""
    if layout_name != "spruce" or not os.path.isdir(os.path.join(base, "Roms")):
        return 0
    folder = os.path.join(base, FOLDER)
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        names = []
    except OSError as e:
        ui.warn(f"Couldn't check {FOLDER.replace(os.sep, '/')}: {e}")
        return 1
    if downloads.name_key(NAME) in {downloads.name_key(n) for n in names}:
        return 0
    shown = f"{FOLDER.replace(os.sep, '/')}/{NAME}"
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would add the Splore launcher → {shown}"))
        return 0
    try:
        os.makedirs(folder, exist_ok=True)
        store.replace_file(os.path.join(folder, NAME), b"")
    except OSError as e:
        ui.warn(f"Couldn't write {shown}: {e}")
        return 1
    print(f"🌱 Adding the Splore launcher → {shown}")
    return 0
