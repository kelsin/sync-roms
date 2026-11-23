"""The keyboard keys and counters, the keyboard's glyphs, the favorite and file glyphs, the button hints, the progress
dot and the loading and charging animations.

Keys are bevelled tiles filling their footprint; a selected key and its unselected twin share every cell and differ
only in color. Glyphs are drawn to fill their footprint (the base glyph's own box) or centered in it, each part sized to
the grid's parity so it centers exactly: a 3-cell letter on an odd grid, its 4-cell form (middle column doubled) on an
even one; likewise a 5-row letter or its 6-row form. Round buttons are regular octagons (1:1 corners).
"""
from .frames import _mix, register
from .ui_status import FONT

ALL = ("left", "right", "top", "bottom")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)


def edge(mask):
    """The cells of `mask` with a side neighbor outside it: a 1-cell outline whose 1:1 steps touch at corners."""
    return {(x, y) for x, y in mask if any((x + dx, y + dy) not in mask for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}


def stamp(canvas, cells, rgb, dx=0, dy=0):
    for x, y in cells:
        canvas.px(dx + x, dy + y, rgb)


def round_cut(size):
    """The corner cut that makes a regular octagon (straight sides as long as the 1:1 ones) of `size` cells."""
    return max(1, round(size * 0.293))


# keys and counters

def key(selected):
    """A bevelled key; the unselected one is the same tile in the dark shades."""
    def draw(canvas, s):
        if selected:
            canvas.panel(0, 0, canvas.cols, canvas.rows, s.bar, s.hi, s.sh, s.ink)
        else:
            canvas.panel(0, 0, canvas.cols, canvas.rows, s.dark, s.mid, _mix(s.dark, BLACK, .5), s.sh)
    return draw


# the keyboard's glyphs

def ring(canvas, rgb):
    """A 1-cell outline round the whole grid, its corners cut one cell."""
    c, r = canvas.cols, canvas.rows
    mask = {(x, y) for y in range(r) for x in range(c)} - {(0, 0), (c - 1, 0), (0, r - 1), (c - 1, r - 1)}
    stamp(canvas, edge(mask), rgb)


def delete(canvas, s):
    """Backspace: a key outline with a left arrow, one cell of padding round the arrow inside it."""
    ring(canvas, s.text)
    w, h = canvas.cols - 2, canvas.rows - 2
    t = 2 - h % 2  # shaft rows: the arrow's height has the inner height's parity, so it centers exactly
    k = max(1, (h - t) // 2 - 1)
    y0 = 1 + (h - t) // 2
    x0 = 2
    canvas.rect(x0, y0, w - 2, t, s.text)
    for i in range(1, k + 1):
        canvas.px(x0 + i, y0 - i, s.text)
        canvas.px(x0 + i, y0 + t - 1 + i, s.text)


def shift(canvas, s):
    """Shift: a key outline with an up arrow centered in it, one cell of padding above and below the arrow."""
    ring(canvas, s.text)
    w, h = canvas.cols - 2, canvas.rows - 2
    t = 2 - w % 2
    tall = max(3, h - 2)
    k = max(1, min((w - t) // 2 - 1, tall - 2))
    x0, y0 = 1 + (w - t) // 2, 1 + (h - tall) // 2
    canvas.rect(x0, y0, t, tall, s.text)
    for i in range(1, k + 1):
        canvas.px(x0 - i, y0 + i, s.text)
        canvas.px(x0 + t - 1 + i, y0 + i, s.text)


def space(canvas, s):
    """Space: two full-height bars and a two-headed arrow from one to the other."""
    c, r = canvas.cols, canvas.rows
    canvas.rect(0, 0, 1, r, s.text)
    canvas.rect(c - 1, 0, 1, r, s.text)
    t = 2 - r % 2
    k = max(1, min((r - t) // 2 - 2, (c - 3) // 4))
    y0 = (r - t) // 2
    canvas.rect(1, y0, c - 2, t, s.text)
    for i in range(1, k + 1):
        for x in (1 + i, c - 2 - i):
            canvas.px(x, y0 - i, s.text)
            canvas.px(x, y0 + t - 1 + i, s.text)


def _trash_body(cols):
    """(overhang, lines, gap): the body inset `overhang` cells under the lid, its `lines` 1-cell lines spaced `gap`
    cells apart and from the sides (equal everywhere, so the body is exactly mirrored)."""
    for overhang in (1, 2, 3):
        for lines in (3, 2):
            inner = cols - 2 * overhang - 2 - lines
            if inner > 0 and inner % (lines + 1) == 0:
                return overhang, lines, inner // (lines + 1)
    raise ValueError(f"no trash can fits {cols} cells")


def trash(canvas, s):
    """Delete all: a can with a handle, a full-width lid and an outlined body with evenly spaced lines."""
    c, r = canvas.cols, canvas.rows
    handle = c // 3 + (c - c // 3) % 2
    hx = (c - handle) // 2
    canvas.rect(hx, 0, handle, 1, s.text)
    canvas.px(hx, 1, s.text)
    canvas.px(hx + handle - 1, 1, s.text)
    canvas.rect(0, 2, c, 1, s.text)
    overhang, lines, gap = _trash_body(c)
    left, right = overhang, c - 1 - overhang
    canvas.rect(left, 3, 1, r - 4, s.text)
    canvas.rect(right, 3, 1, r - 4, s.text)
    canvas.rect(left + 1, r - 1, right - left - 1, 1, s.text)
    for i in range(lines):
        canvas.rect(left + 1 + gap + i * (gap + 1), 4, 1, r - 7, s.text)


# favorite and file glyphs

def star_mask(cols, rows):
    """A five-pointed star of 1:1 edges as wide as the grid allows with even side margins: a spike, two arms, the
    underside stepping in to the waist and two legs stepping out. Returns (cells, width, height)."""
    peak = 2 - cols % 2
    arm = (cols - peak) // 2
    while arm >= 3:
        spike, waist = max(2, arm // 2), round(arm * 3 / 8)
        legs, thick = arm - waist, 2 if arm >= 6 else 1
        height = spike + 1 + (arm - waist) + legs
        if (rows - height) % 2:
            spike += 1 if height + 1 <= rows else -1
            height = spike + 1 + (arm - waist) + legs
        if height <= rows and spike >= 2:
            break
        arm -= 1
    rows_ = [[(-r, r)] for r in range(spike)] + [[(-arm, arm)]]
    rows_ += [[(-(arm - i), arm - i)] for i in range(1, arm - waist + 1)]
    rows_ += [[(-(waist + j), -(waist - thick + j)), (waist - thick + j, waist + j)] for j in range(1, legs + 1)]
    cells = set()
    for y, segments in enumerate(rows_):
        for a, b in segments:
            lo = arm + a if a <= 0 else arm + peak - 1 + a
            hi = arm + peak - 1 + b if b >= 0 else arm + b
            cells.update((x, y) for x in range(lo, hi + 1))
    return cells, 2 * arm + peak, len(rows_)


def star(selected):
    def draw(canvas, s):
        cells, width, height = star_mask(canvas.cols, canvas.rows)
        stamp(canvas, cells, s.accent if selected else s.dim,
              (canvas.cols - width) // 2, (canvas.rows - height) // 2)
    return draw


def folder(selected):
    """A folder outline filling the grid: the tab at the left with a 1:1 slanted side, the body below it."""
    def draw(canvas, s):
        c, r = canvas.cols, canvas.rows
        tab_rows, tab = max(2, round(r / 7)), round(c * .4)
        mask = {(x, y) for y in range(tab_rows) for x in range(tab + y)}
        mask |= {(x, y) for y in range(tab_rows, r) for x in range(c)}
        mask -= {(0, 0), (c - 1, tab_rows), (0, r - 1), (c - 1, r - 1)}
        stamp(canvas, edge(mask), s.accent if selected else s.dim)
    return draw


def dot(canvas, s):
    canvas.panel(0, 0, canvas.cols, canvas.rows, s.text, s.text, s.text, s.text, cut=round_cut(canvas.rows))


# button hints

HINT_FONT = dict(FONT, M=("X...X", "XX.XX", "X.X.X", "X...X", "X...X"))  # the 3-wide M reads as an H


def letter(ch, wide, tall):
    """A letter of the 3x5 font (M 5 wide), one column wider with its second column doubled, 6 tall with a row
    doubled (X its middle, the others the one under it)."""
    rows = list(HINT_FONT[ch])
    if tall:
        dup = 2 if ch == "X" else 3
        rows = rows[:dup + 1] + rows[dup:]
    if wide:
        rows = [row[0] + row[1] + row[1:] for row in rows]
    return rows


def word(canvas, text, rgb):
    """`text` centered in the grid: the letter nearest the middle widened when the word's width and the grid differ
    in parity, every letter made 6 tall when the 5-row form can't center vertically."""
    tall = (canvas.rows - 5) % 2 == 1
    width = sum(len(HINT_FONT[ch][0]) for ch in text) + len(text) - 1
    middle = sorted((i for i, ch in enumerate(text) if ch != "M" or len(text) == 1), key=lambda i: abs(2 * i - len(text) + 1))
    wide = middle[0] if (canvas.cols - width) % 2 else None
    glyphs = [letter(ch, i == wide, tall) for i, ch in enumerate(text)]
    width = sum(len(g[0]) for g in glyphs) + len(glyphs) - 1
    x, y = (canvas.cols - width) // 2, (canvas.rows - len(glyphs[0])) // 2
    for g in glyphs:
        for j, row in enumerate(g):
            for i, on in enumerate(row):
                if on == "X":
                    canvas.px(x + i, y + j, rgb)
        x += len(g[0]) + 1


def hint(text):
    """A button hint: an accent octagon (or pill with octagon ends), bevelled, with its letters in ink."""
    def draw(canvas, s):
        canvas.panel(0, 0, canvas.cols, canvas.rows, s.accent, _mix(s.accent, WHITE, .35), _mix(s.accent, BLACK, .4),
                     s.ink, cut=round_cut(canvas.rows))
        word(canvas, text, s.ink)
    return draw


# loading and charging: a spruce tree lit from the trunk up, one part per frame

def tree_rows(cols, rows):
    """The tree's rows as (width, part) from the top, part 0 the top tier to 2 the bottom tier, 3 the trunk, None the
    gap above the trunk: three equal 1:1 tiers, each overlapping the one above by a row, one cell of margin at the
    sides and equal margins above and below."""
    width = cols - 2
    peak = 2 - width % 2
    tier = [peak + 2 * i for i in range((width - peak) // 2 + 1)]
    trunk_width = peak if peak == 2 else 3
    for step in range(len(tier) - 1, 0, -1):
        for trunk in range(len(tier), 1, -1):
            height = len(tier) + 2 * step + 1 + trunk
            if height <= rows - 2 and (rows - height) % 2 == 0:
                out = [None] * (len(tier) + 2 * step)
                for part in range(3):
                    for i, w in enumerate(tier):
                        out[part * step + i] = (w, part)
                return out + [None] + [(trunk_width, 3)] * trunk
    raise ValueError(f"no tree fits {cols}x{rows} cells")


def tree(lit):
    """Frame `lit` (0 to 4): the trunk, then the bottom, middle and top tiers lit in turn."""
    def draw(canvas, s):
        layout = tree_rows(canvas.cols, canvas.rows)
        top = (canvas.rows - len(layout)) // 2
        for y, row in enumerate(layout):
            if row is None:
                continue
            w, part = row
            on = lit >= (1 if part == 3 else 4 - part)
            canvas.rect((canvas.cols - w) // 2, top + y, w, 1, s.accent if on else s.bar)
    return draw


for _state, _selected in (("f", True), ("n", False)):
    for _name in ("bg-btn-01", "value-frame"):
        register(f"skin/{_name}-{_state}.png", key(_selected), symmetric=True, flush=ALL)
    register(f"skin/bg-btn-02-{_state}.png", key(_selected), symmetric=True, flush=ALL, small=True)  # like bg-btn-01
    register(f"skin/nav-favorite-{_state}.png", star(_selected), symmetric=True)
    register(f"skin/nav-file-{_state}.png", folder(_selected), flush=ALL)  # the tab sits at the left
register("skin/bg-btn-sel.png", key(True), symmetric=True, flush=ALL)
register("skin/bg-btn-shift-active.png", key(True), symmetric=True, flush=ALL)
register("skin/bg-btn-nor.png", key(False), symmetric=True, flush=ALL)
register("skin/num-bg.png", key(False), symmetric=True, flush=ALL)
register("skin/btn-delete.png", delete, flush=ALL)
register("skin/btn-shift.png", shift, symmetric=True, flush=ALL)
register("skin/btn-space.png", space, symmetric=True, flush=ALL)
register("skin/btn-empty.png", trash, symmetric=True, flush=ALL)
register("skin/progress-dot.png", dot, symmetric=True, flush=ALL)
for _letter in "ABXY":
    register(f"skin/context-{_letter.lower()}.png", hint(_letter), flush=ALL, small=True)
for _word in ("MENU", "SELECT", "START"):
    register(f"skin/context-{_word.lower()}.png", hint(_word), flush=ALL, small=True)  # the word needs small cells
for _kind in ("app_loading_0", "charging-0"):
    _group = tuple(f"{_kind}{i}.png" for i in range(1, 6))
    for _i in range(1, 6):
        register(f"skin/{_kind}{_i}.png", tree(_i - 1), symmetric=True, group=_group)
