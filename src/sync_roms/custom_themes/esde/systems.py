"""Which sprite each ES-DE system (the `esde` folder in systems.json) is drawn with."""
import json
import os

from ... import store
from ..pixel import build, modern, variants

# ES-DE system name -> Pixel icon id (pixel/ids.py, or a drawing in pixel/extras.py)
ICONS = {
    "mame": "mame", "mame-advmame": "mame", "arcade": "arcade", "fbneo": "arcade",
    "atari2600": "atari", "atari5200": "5200", "atari7800": "7800", "atari800": "atari800", "atarilynx": "lynx",
    "atarist": "atarist", "atarijaguar": "jaguar", "atomiswave": "atomiswave", "colecovision": "col",
    "gba": "gba", "gbc": "gbc", "gb": "gb", "sgb": "sgb", "intellivision": "itv", "neogeo": "neogeo",
    "neogeocd": "neocd", "ngp": "ngp", "ngpc": "ngpc", "nes": "fc", "fds": "fds", "snes": "sfc", "n64": "n64",
    "nds": "nds", "n3ds": "3ds", "odyssey2": "ody", "pc98": "pc98", "sega32x": "32x", "segacd": "segacd",
    "dreamcast": "dc", "gamegear": "gg", "genesis": "md", "mastersystem": "ms", "saturn": "saturn",
    "sg-1000": "segasgone", "tg16": "pce", "tg-cd": "pcecd", "supergrafx": "sgfx", "vectrex": "vectrex",
    "virtualboy": "vb", "wonderswan": "ws", "wonderswancolor": "wsc", "arduboy": "arduboy", "chailove": "chai",
    "channelf": "fairchild", "cps1": "cps1", "cps2": "cps2", "cps3": "cps3", "doom": "doom", "easyrpg": "easyrpg",
    "megaduck": "megaduck", "naomi": "naomi", "naomi2": "naomi", "naomigd": "naomi", "openbor": "openbor",
    "pico8": "pico", "pokemini": "poke", "ports": "ports", "psx": "ps", "psp": "psp", "satellaview": "satella",
    "scummvm": "scummvm", "sufami": "sufami", "supervision": "supervision", "tic80": "tic", "quake": "quake",
    "msx": "msx", "msx2": "msx", "c64": "c64", "gamate": "gamate",
}
# ES-DE name -> {"CONSOLES": draw, "CONTROLLERS": draw} for drawings that aren't a Spruce icon id
EXTRA = {"mark3": {"CONSOLES": variants.mark3_console, "CONTROLLERS": variants.mark3_pad}}
EXTRA.update({name: {"CONSOLES": modern.CONSOLES[name], "CONTROLLERS": modern.CONTROLLERS[name]}
              for name in modern.CONSOLES})
# ES-DE names still waiting for a drawing
PENDING = {
    "pcfx", "daphne", "lowresnx", "lutro", "3do", "uzebox", "atarijaguarcd", "cdimono1", "model2", "model3", "ps2",
    "ps3", "ps4", "psvita", "stv", "triforce", "type-x", "xbox", "xbox360", "xboxone", "arcadia", "gamecom",
}


def esde_names():
    """The `esde` folders of systems.json in file order, each once."""
    with open(os.path.join(store.REPO_DATA, "systems.json"), encoding="utf-8") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else data.values()
    names = []
    for entry in entries:
        name = entry["folders"].get("esde")
        if name and name not in names:
            names.append(name)
    return names


def sprites(kind):
    """{ES-DE name: draw function} for every mapped system, `kind` being "CONSOLES" or "CONTROLLERS"."""
    drawn = build.systems(kind)
    out = {name: drawn[icon] for name, icon in ICONS.items()}
    out.update({name: draws[kind] for name, draws in EXTRA.items()})
    return out
