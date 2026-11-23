"""The "Pixel Consoles" spruceOS theme: the SPRUCE theme with a black background and pixel-art consoles."""
from .pixel.build import build_theme

NAME = "Pixel Consoles"
BASE = "SPRUCE"


def build(base_dir, out_dir):
    """Write <out_dir>/<NAME>/ (replacing it) and return that path."""
    return build_theme(base_dir, out_dir, NAME, "CONSOLES")
