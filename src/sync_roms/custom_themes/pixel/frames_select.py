"""The selection frames: list bars, the outlined short-list box and the grid tiles."""
from .frames import register


def bar(canvas, s):
    """A full-width selection bar, inset one cell at the top and bottom."""
    canvas.panel(0, 1, canvas.cols, canvas.rows - 2, s.bar, s.hi, s.sh, s.ink)


def outlined_box(canvas, s):
    """A dark box with an accent ring inside the ink outline, the bar's footprint."""
    canvas.panel(0, 1, canvas.cols, canvas.rows - 2, s.accent, s.accent, s.accent, s.ink)
    canvas.panel(1, 2, canvas.cols - 2, canvas.rows - 4, s.dark, s.dark, s.dark, s.accent, cut=1)


def tile(canvas, s):
    """A grid tile filling its footprint."""
    canvas.panel(0, 0, canvas.cols, canvas.rows, s.bar, s.hi, s.sh, s.ink)


for _name in ("bg-list-l", "bg-list-s", "bg-list-s2", "menu-sub-title-bg"):
    register(f"skin/{_name}.png", bar, symmetric=True, flush=("left", "right"))
register("skin/list-item-select-bg-short.png", outlined_box, symmetric=True, flush=("left", "right"))
for _name in ("grid-game-selected", "bg-game-item-f", "bg-grid-s"):
    register(f"skin/{_name}.png", tile, symmetric=True, flush=("left", "right", "top", "bottom"))
