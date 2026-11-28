"""Palette recipes: a frame color kept as how it derives from the palette's roles, so one drawing serves every palette."""
from dataclasses import dataclass

from . import frames
from .sprite import INK, _rgb

ROLES = ("text", "list", "selected", "accent", "dim", "bar")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)


@dataclass(frozen=True)
class Recipe:
    """`src` (a role id, another Recipe or a fixed rgb) mixed `t` of the way to `target` (None: `src` as it is)."""
    src: "str | Recipe | tuple"
    target: "None | tuple" = None
    t: float = 0.0


def shades():
    """frames.Shades whose colors are recipes, the same derivations as frames.shades."""
    return frames.Shades(**{role: Recipe(role) for role in ROLES}, hi=Recipe("bar", WHITE, .35),
                         sh=Recipe("bar", BLACK, .4), mid=Recipe("bar", BLACK, .45), dark=Recipe("bar", BLACK, .7),
                         ink=Recipe(_rgb(INK)))


def resolve(r, palette):
    """The rgb of `r` (a Recipe or an rgb) in `palette`, with frames._mix's arithmetic."""
    if not isinstance(r, Recipe):
        return tuple(r)
    src = getattr(palette, r.src) if isinstance(r.src, str) else r.src
    src = _rgb(src) if isinstance(src, str) else resolve(src, palette)
    if r.target is None:
        return src
    return frames._mix(src, r.target, r.t)
