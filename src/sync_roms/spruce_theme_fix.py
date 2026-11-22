"""Temporary fix for spruceOS's Art Book themes, which name Pokémon Mini's pictures `pokemini` where Spruce's folder is
`POKE`, so the system shows no logo (https://github.com/spruceUI/PyUI-Themes/pull/15). Copies `pokemini.png` to
`poke.png` wherever the theme lacks it. Once the card's theme has every `poke.png` there is nothing to copy, and the
step does nothing; delete this module and its step in cli.py when spruceOS ships the fixed themes."""
import os

from . import cardfs

THEMES = ("ART_BOOK_OUTLINE", "ART_BOOK_NEXT")
FOLDERS = ("bg", "icons", os.path.join("icons", "sel"), os.path.join("icons", "overlay"))


def plan(base):
    """[(source, target)] of the `pokemini.png` files to copy to `poke.png` in the card's Art Book themes."""
    result = []
    for theme in THEMES:
        for folder in FOLDERS:
            top = os.path.join(base, "Themes", theme, folder)
            source, target = os.path.join(top, "pokemini.png"), os.path.join(top, "poke.png")
            if cardfs.exists(source) and not cardfs.exists(target):
                result.append((source, target))
    return result


def describe(copies):
    for _, target in copies:
        print(f"🎨 would add {'/'.join(target.replace(os.sep, '/').split('/')[-4:])} (Pokémon Mini logo)")


def apply(copies):
    """Copy each source to its target; the number copied."""
    for source, target in copies:
        cardfs.write_bytes(target, cardfs.read(source))
    return len(copies)
