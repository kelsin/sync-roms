"""Renames NextUI system folders an earlier sync-roms named differently from NextUI's own, so a sync doesn't copy
every ROM again. NextUI keys saves, states and BIOS by the folder's tag, which is unchanged, so only the folder moves."""
import os
import unicodedata

from . import downloads, ui

RENAMES = {  # old sync-roms name: NextUI's skeleton name (same tag)
    "ColecoVision (COLECO)": "Colecovision (COLECO)",
    "Game Gear (GG)": "Sega Game Gear (GG)",
    "MSX (MSX)": "Microsoft MSX (MSX)",
    "PICO-8 (P8)": "Pico-8 (P8)",
    "PlayStation (PS)": "Sony PlayStation (PS)",
    "Pokemon Mini (PKM)": "Pokémon mini (PKM)",
    "Super Nintendo (SFC)": "Super Nintendo Entertainment System (SFC)",
}


def migrate(roms_dir, dry_run):
    """Rename each old folder in roms_dir to its new name, unless a folder of the new name is there too (then both
    stay, with a warning). Returns the (old, new) pairs renamed, or that would be with dry_run."""
    try:
        names = os.listdir(roms_dir)
    except FileNotFoundError:
        return []
    on_disk = {unicodedata.normalize("NFC", n): n for n in names}
    done = []
    for old, new in RENAMES.items():
        if old not in on_disk:
            continue
        # the new folder is there already (or, on a case-sensitive card, spelled another way): leave both to the user
        if any(downloads.name_key(n) == downloads.name_key(new) for n in names if n != on_disk[old]):
            ui.warn(f"{os.path.join(roms_dir, on_disk[old])} and a folder named like {new} are both on the card; "
                    f"move its ROMs into {new} by hand")
            continue
        if not dry_run:
            downloads.rename_on_card(os.path.join(roms_dir, on_disk[old]), os.path.join(roms_dir, new))
        done.append((old, new))
    return done
