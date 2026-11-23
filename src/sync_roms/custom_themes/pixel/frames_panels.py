"""The bars, screens, panels, loading bar and dividers.

Full-screen backgrounds are opaque black over their whole footprint with palette-colored dotted rules at the edges
where a bar meets the screen (the title's bottom, the hints' top, ...). Panels are a bevelled ring (ink outline, bar-
colored ring) around a dark fill; the loading frame is the same ring left hollow for the progress pieces, which tile
left + mid + ... + mid + right as one segmented bar.
"""
from .frames import _mix, register

BLACK = (0, 0, 0)
ALL = ("left", "right", "top", "bottom")


def dotted(length, on=2, off=1):
    """Which cells of a dotted line of `length` are on: the on/off pattern phased so the line is its own mirror (a
    period of 3 can always be; the ends land wherever that puts them, the same at both ends)."""
    period = on + off
    phase = next(p for p in range(period) if all(((i + p) % period < on) == ((length - 1 - i + p) % period < on)
                                                   for i in range(length)))
    return [(i + phase) % period < on for i in range(length)]


def hdots(canvas, cx, cy, length, rgb):
    for i, on in enumerate(dotted(length)):
        if on:
            canvas.px(cx + i, cy, rgb)


def vdots(canvas, cx, cy, length, rgb):
    for i, on in enumerate(dotted(length)):
        if on:
            canvas.px(cx, cy + i, rgb)


def rule(s):
    return s.hi


def _inset(length):
    """The cells (0 to 2) left clear at both ends of a full-length rule so it starts and ends with a whole dash."""
    return next(i for i in range(3) if dotted(length - 2 * i)[:2] == [True, True])


def hrule(canvas, cy, rgb):
    inset = _inset(canvas.cols)
    hdots(canvas, inset, cy, canvas.cols - 2 * inset, rgb)


def vrule(canvas, cx, rgb):
    inset = _inset(canvas.rows)
    vdots(canvas, cx, inset, canvas.rows - 2 * inset, rgb)


# full-screen backgrounds (black, see register below)

def top_rule(canvas, s):
    hrule(canvas, 0, rule(s))


def bottom_rule(canvas, s):
    hrule(canvas, canvas.rows - 1, rule(s))


def title(canvas, s):
    """The title bar: a dotted bottom rule and a small spruce tree centered in a square slot at the left (the slot is
    the bar's height above the rule: the tree's left, top and bottom margins are equal)."""
    bottom_rule(canvas, s)
    content = canvas.rows - 1
    tall = content % 2  # an odd slot gets a one-row-longer trunk, so the top and bottom margins stay equal
    widths = [2, 4, 6, 4, 6, 8, 6, 8] + [2] * (2 + tall)  # three tiers with 1:1 sides, then the trunk
    margin = (content - len(widths)) // 2
    for row, width in enumerate(widths):
        color = s.hi if row >= 8 else s.accent
        canvas.rect(margin + (8 - width) // 2, margin + row, width, 1, color)


def rails(canvas, s):
    """The game list between the title and hint bars: dotted rails down both screen edges."""
    vrule(canvas, 0, rule(s))
    vrule(canvas, canvas.cols - 1, rule(s))


def _arm(length):
    """The bracket arm (3 to 5 cells) that lets the dots between a side's two brackets, a cell's gap from each, start
    and end with a whole dash: the dash rhythm then runs unbroken from corner to corner."""
    return next(arm for arm in (3, 4, 5) if dotted(length - 2 * (arm + 1))[:2] == [True, True])


def border(canvas, s):
    """A dotted border one cell in from every edge, with solid L brackets at the four (identical) corners."""
    x0, y0, x1, y1 = 1, 1, canvas.cols - 2, canvas.rows - 2
    across, down = x1 - x0 + 1, y1 - y0 + 1
    arm_x, arm_y = _arm(across), _arm(down)
    hdots(canvas, x0 + arm_x + 1, y0, across - 2 * (arm_x + 1), rule(s))
    hdots(canvas, x0 + arm_x + 1, y1, across - 2 * (arm_x + 1), rule(s))
    vdots(canvas, x0, y0 + arm_y + 1, down - 2 * (arm_y + 1), rule(s))
    vdots(canvas, x1, y0 + arm_y + 1, down - 2 * (arm_y + 1), rule(s))
    for x, dx in ((x0, 1), (x1, -1)):
        for y, dy in ((y0, 1), (y1, -1)):
            for i in range(arm_x):
                canvas.px(x + dx * i, y, s.accent)
            for i in range(arm_y):
                canvas.px(x, y + dy * i, s.accent)


# panels

def ring(canvas, cx, cy, cw, ch, s, fill=None):
    """A bevelled panel whose bar-colored ring (light top, dark bottom) surrounds `fill`; hollow when fill is None."""
    canvas.panel(cx, cy, cw, ch, s.bar, s.hi, s.sh, s.ink)
    for y in range(cy + 2, cy + ch - 2):
        for x in range(cx + 2, cx + cw - 2):
            if fill is None:
                canvas.cells.pop((x, y), None)
            else:
                canvas.px(x, y, fill)


def dark_panel(canvas, s):
    ring(canvas, 0, 0, canvas.cols, canvas.rows, s, s.dark)


def loading_frame(canvas, s):
    ring(canvas, 0, 0, canvas.cols, canvas.rows, s)


def name_frame(canvas, s):
    canvas.panel(0, 0, canvas.cols, canvas.rows, s.bar, s.hi, s.sh, s.ink)


def thumb(canvas, s):
    """A placeholder picture: the dark panel with a mountain peak centered in it (1:1 sides, a light snow cap, its peak one cell wide on
    an odd grid and two on an even one, so it centers exactly)."""
    dark_panel(canvas, s)
    peak = 2 - canvas.cols % 2
    height = max(2, min(canvas.cols, canvas.rows) // 6)
    width = peak + 2 * (height - 1)
    x, y = (canvas.cols - width) // 2, (canvas.rows - height) // 2
    for row in range(height):
        canvas.rect(x + height - 1 - row, y + row, peak + 2 * row, 1, s.text if row < 2 else s.hi)


def divider(canvas, s):
    for x in range(canvas.cols):
        vrule(canvas, x, rule(s))


# the loading bar's pieces: 2 cells wide each, tiling left + mid... + right with no seam

def _bar_colors(s):
    return {"top": _mix(s.accent, (255, 255, 255), .35), "fill": s.accent, "bottom": _mix(s.accent, (0, 0, 0), .4),
            "divider": _mix(s.accent, (0, 0, 0), .45)}


def _column(canvas, cx, s, kind):
    """One cell column of the segmented bar: `cap` (the stepped end), `body` (a segment), `divider` or `head` (the
    light leading edge)."""
    c, last = _bar_colors(s), canvas.rows - 1
    for y in range(canvas.rows):
        if kind == "cap":
            color = s.ink if 0 < y < last else None
        elif y in (0, last):
            color = s.ink
        elif kind == "body":
            color = c["top"] if y == 1 else c["bottom"] if y == last - 1 else c["fill"]
        else:
            color = c["divider"] if kind == "divider" else c["top"]
        if color is not None:
            canvas.px(cx, y, color)


def progress(kinds):
    def draw(canvas, s):
        for cx, kind in enumerate(kinds):
            _column(canvas, cx, s, kind)
    return draw


for _name, _draw in (("tips-bar-bg", top_rule), ("navbg", top_rule), ("statbg", bottom_rule),
                     ("bg-gamelist", rails), ("menu-5line-bg", border), ("menu-6line-bg", border),
                     ("app_loading_bg", border)):
    register(f"skin/{_name}.png", _draw, symmetric=True, flush=ALL, background=BLACK)
register("skin/bg-title.png", title, flush=ALL, background=BLACK)
for _name in ("bg-pop-menu-4", "menu-sub-bg", "preview-bg"):
    register(f"skin/{_name}.png", dark_panel, symmetric=True, flush=ALL)
register("skin/loading-bg.png", loading_frame, symmetric=True, flush=ALL)
register("skin/preview-nameFrame.png", name_frame, symmetric=True, flush=ALL)
register("skin/thumb-default.png", thumb, symmetric=True, flush=ALL)
register("skin/div-line-v-02.png", divider, symmetric=True, flush=("left", "right"))
register("skin/loading-progress-left.png", progress(("cap", "body")), flush=ALL)
register("skin/loading-progress-mid.png", progress(("divider", "body")), flush=ALL)
register("skin/loading-progress-right.png", progress(("head", "cap")), flush=ALL)
