"""The "Pixel Consoles" spruceOS themes: the SPRUCE theme with a black background and pixel-art consoles, in each palette."""
from .pixel.build import build_theme

STYLE = "Pixel Consoles"
BASE = "SPRUCE"


def build(base_dir, out_dir, palette):
    """Write <out_dir>/<theme name>/ (replacing it) in the palette and return that path."""
    from . import theme_name
    return build_theme(base_dir, out_dir, theme_name(STYLE, palette.name), "CONSOLES", palette)
