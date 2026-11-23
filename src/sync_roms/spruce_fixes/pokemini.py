"""Art Book themes name Pokémon Mini's pictures `pokemini` where Spruce's folder is `POKE`, so the system shows no
logo. Copies `pokemini.png` to `poke.png` wherever the theme lacks it, PyUI's resized copies included (each copies its
own, already resized, `pokemini.png`)."""
import os

from . import pyui
from .. import cardfs

ID = "pokemini"
THEMES = ("ART_BOOK_OUTLINE", "ART_BOOK_NEXT")
FOLDERS = (("bg", ""), ("icons", ""), ("icons", "sel"), ("icons", "overlay"))


def plan(base):
    if not any(cardfs.is_dir(os.path.join(base, "Themes", theme)) for theme in THEMES):
        return [], None
    writes, has_poke = [], False
    for theme in THEMES:
        root = os.path.join(base, "Themes", theme)
        for top in [os.path.join(root, name, sub) for base_name, sub in FOLDERS
                    for name, _ in pyui.folders(root, base_name)]:
            source, target = os.path.join(top, "pokemini.png"), os.path.join(top, "poke.png")
            if cardfs.exists(target):
                has_poke = True
            elif cardfs.exists(source):
                writes.append((target, cardfs.read(source)))
    return writes, "the theme already has poke.png" if has_poke else "the theme has no pokemini.png to copy"


def keeps(path):
    return False
