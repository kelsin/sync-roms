"""The "ToTK - James" spruceOS theme: the ToTK theme with a Tears of the Kingdom title picture, a sage card for each
main menu entry and no main menu title. It has no palette, so it is built once."""
import json
import os
import shutil

from .. import runtime  # noqa: F401  (keeps the package import order of the other styles)

STYLE = "ToTK - James"
BASE = "ToTK"
PALETTES = False
CHARACTERS = ("sidon", "riju", "mineru", "rauru")
COLLECTIONS = "rauru"  # the character whose cards are the main menu's Collections card
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "themes", "totk-james")


def build(base_dir, out_dir, palette=None):
    """Write <out_dir>/ToTK - James/ (replacing it): the base with the art laid over it. Returns that path."""
    dest = os.path.join(out_dir, STYLE)
    if os.path.lexists(dest):
        shutil.rmtree(dest)
    shutil.copytree(base_dir, dest)
    skin = os.path.join(dest, "skin")
    os.makedirs(skin, exist_ok=True)
    shutil.copyfile(os.path.join(DATA, "bg-title.png"), os.path.join(skin, "bg-title.png"))
    for character in CHARACTERS:
        for state in ("f", "n"):
            card = os.path.join(DATA, "cards", f"{character}-{state}.png")
            shutil.copyfile(card, os.path.join(skin, f"ic-collection-{character}-{state}.png"))
            if character == COLLECTIONS:
                shutil.copyfile(card, os.path.join(skin, f"ic-collection-{state}.png"))
    for name in sorted(os.listdir(dest)):
        path = os.path.join(dest, name)
        if name.startswith("config") and name.endswith(".json") and os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as f:
                config = json.load(f)
            config["name"] = STYLE
            config["mainMenuTitle"] = ""
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
    return dest
