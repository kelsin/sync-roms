"""The "ToTK - Kelsin" spruceOS theme: "ToTK - James" with "Kelsin" in its title picture."""
from . import totk_james

STYLE = "ToTK - Kelsin"
BASE = totk_james.BASE
PALETTES = False


def build(base_dir, out_dir, palette=None):
    """Write <out_dir>/ToTK - Kelsin/ (replacing it). Returns that path."""
    return totk_james.build_named(base_dir, out_dir, STYLE, "bg-title-kelsin.png")
