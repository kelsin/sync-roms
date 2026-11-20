#!/usr/bin/env python3
"""Add the NextUI folder to every system in src/sync_roms/data/systems.json (null for systems NextUI has no tag for),
and the extra BIOS tags a system's emulators use. Keeps key order and formatting; running it again changes nothing.

    tools/add_nextui_folders.py
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "systems.json")
FOLDERS = {
    "fbneo": "Arcade (FBN)", "neogeo": "Neo Geo (FBN)", "cps1": "CPS1 (FBN)", "cps2": "CPS2 (FBN)", "cps3": "CPS3 (FBN)",
    "atari2600": "Atari 2600 (A2600)", "atari5200": "Atari 5200 (A5200)", "atari7800": "Atari 7800 (A7800)",
    "atarilynx": "Atari Lynx (LYNX)", "colecovision": "ColecoVision (COLECO)", "gb": "Game Boy (GB)",
    "gbc": "Game Boy Color (GBC)", "gba": "Game Boy Advance (GBA)", "sgb": "Super Game Boy (SGB)",
    "nes": "Nintendo Entertainment System (FC)", "fds": "Famicom Disk System (FDS)", "snes": "Super Nintendo (SFC)",
    "virtualboy": "Virtual Boy (VB)", "ngp": "Neo Geo Pocket (NGP)", "ngpc": "Neo Geo Pocket Color (NGPC)",
    "pokemini": "Pokemon Mini (PKM)", "sega32x": "Sega 32X (32X)", "segacd": "Sega CD (SEGACD)",
    "gamegear": "Game Gear (GG)", "genesis": "Sega Genesis (MD)", "mastersystem": "Sega Master System (SMS)",
    "sg1000": "Sega SG-1000 (SG1000)", "tg16": "TurboGrafx-16 (PCE)", "tg-cd": "TurboGrafx-CD (PCE)",
    "psx": "PlayStation (PS)", "pico8": "PICO-8 (P8)", "msx": "MSX (MSX)", "msx2": "MSX2 (MSX)",
    "c64": "Commodore 64 (C64)", "doom": "Doom (PRBOOM)",
}
# systems whose BIOS files are also read from a second tag's directory
BIOS_TAGS = {"gba": ["MGBA"]}


def main():
    with open(PATH, encoding="utf-8") as f:
        systems = json.load(f)
    for s in systems:
        s["folders"]["nextui"] = FOLDERS.get(s["bucket"])
        if s["bucket"] in BIOS_TAGS:
            rebuilt = {}
            for key, value in s.items():
                rebuilt[key] = value
                if key == "folders":
                    rebuilt["nextui_bios_tags"] = BIOS_TAGS[s["bucket"]]
            s.clear()
            s.update(rebuilt)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(systems, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
