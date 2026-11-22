import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import nextui_folders, store  # noqa: E402

FOLDERS = {
    "fbneo": "Arcade (FBN)", "neogeo": "Neo Geo (FBN)", "cps1": "CPS1 (FBN)", "cps2": "CPS2 (FBN)", "cps3": "CPS3 (FBN)",
    "atari2600": "Atari 2600 (A2600)", "atari5200": "Atari 5200 (A5200)", "atari7800": "Atari 7800 (A7800)",
    "atarilynx": "Atari Lynx (LYNX)", "colecovision": "Colecovision (COLECO)", "gb": "Game Boy (GB)",
    "gbc": "Game Boy Color (GBC)", "gba": "Game Boy Advance (GBA)", "sgb": "Super Game Boy (SGB)",
    "nes": "Nintendo Entertainment System (FC)", "fds": "Famicom Disk System (FDS)", "snes": "Super Nintendo Entertainment System (SFC)",
    "virtualboy": "Virtual Boy (VB)", "ngp": "Neo Geo Pocket (NGP)", "ngpc": "Neo Geo Pocket Color (NGPC)",
    "pokemini": "Pok\u00e9mon mini (PKM)", "sega32x": "Sega 32X (32X)", "segacd": "Sega CD (SEGACD)",
    "gamegear": "Sega Game Gear (GG)", "genesis": "Sega Genesis (MD)", "mastersystem": "Sega Master System (SMS)",
    "sg1000": "Sega SG-1000 (SG1000)", "tg16": "TurboGrafx-16 (PCE)", "tg-cd": "TurboGrafx-CD (PCE)",
    "psx": "Sony PlayStation (PS)", "pico8": "Pico-8 (P8)", "msx": "Microsoft MSX (MSX)", "msx2": "MSX2 (MSX)",
    "c64": "Commodore 64 (C64)", "doom": "Doom (PRBOOM)",
}
TAGS = set("FC GB GBC GBA MD SFC PS 32X A2600 A5200 A7800 C64 C128 COLECO CPC FBN FDS GG LYNX MGBA MSX NGP NGPC P8 PCE PET "
           "PKM PLUS4 PRBOOM PUAE SEGACD SG1000 SGB SMS SUPA VB VIC".split())


class NextUIDataTest(unittest.TestCase):
    def test_every_system_folder_is_null_or_has_a_known_tag(self):
        for s in store.repo_json("systems"):
            folder = s["folders"]["nextui"]
            if folder is not None:
                self.assertIn(store.folder_tag(folder), TAGS, s["bucket"])

    def test_the_non_null_folders_are_exactly_the_map(self):
        got = {s["bucket"]: s["folders"]["nextui"] for s in store.repo_json("systems") if s["folders"]["nextui"]}
        self.assertEqual(got, FOLDERS)

    def test_the_renamed_folders_are_the_current_ones(self):
        current = {s["folders"]["nextui"] for s in store.repo_json("systems")}
        for old, new in nextui_folders.RENAMES.items():
            self.assertIn(new, current)
            self.assertNotIn(old, current)
            self.assertEqual(store.folder_tag(old), store.folder_tag(new))

    def test_nextui_is_the_last_folder_key(self):
        for s in store.repo_json("systems"):
            self.assertEqual(list(s["folders"])[-1], "nextui", s["bucket"])

    def test_second_tag_bios(self):
        by_bucket = {s["bucket"]: s for s in store.repo_json("systems")}
        got = {b: s["nextui_bios_tags"] for b, s in by_bucket.items() if "nextui_bios_tags" in s}
        self.assertEqual(got, {"gba": ["MGBA"], "snes": ["SUPA"]})

    def test_the_sp_devices_default_to_nextui_then_knulli(self):
        devices = {d["id"]: d for d in store.repo_json("devices")}
        for id in ("anbernic-rg-sp", "anbernic-rg34xx-sp"):
            self.assertEqual(devices[id]["firmwares"][:2], ["nextui", "knulli"], id)

    def test_layout(self):
        layout = store.repo_json("layouts")["nextui"]
        for key, value in {"label": "NextUI", "roms_dir": "Roms", "bios_dir": "Bios", "bios_by_tag": True, "disc_folders": True,
                           "retroarch": {"dir": "", "saves": "Saves/{tag}", "states": ".userdata/shared/{tag}-{core}"}}.items():
            self.assertEqual(layout[key], value, key)
        self.assertIn("https://nextui.loveretro.games/getting-started/roms/", layout["note"])


if __name__ == "__main__":
    unittest.main()
