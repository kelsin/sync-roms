"""Pixel replacements for the status-bar and button-glyph icons in skin/: ICONS = {path in the theme: draw fn}."""
from .sprite import Sprite

ICONS = {}

# 3x5 pixel font
FONT = {
    "A": (".X.", "X.X", "XXX", "X.X", "X.X"),
    "B": ("XX.", "X.X", "XX.", "X.X", "XX."),
    "E": ("XXX", "X..", "XX.", "X..", "XXX"),
    "K": ("X.X", "X.X", "XX.", "X.X", "X.X"),
    "L": ("X..", "X..", "X..", "X..", "XXX"),
    "M": ("X.X", "XXX", "XXX", "X.X", "X.X"),
    "N": ("XX.", "X.X", "X.X", "X.X", "X.X"),
    "O": ("XXX", "X.X", "X.X", "X.X", "XXX"),
    "R": ("XX.", "X.X", "XX.", "X.X", "X.X"),
    "S": ("XXX", "X..", "XXX", "..X", "XXX"),
    "T": ("XXX", ".X.", ".X.", ".X.", ".X."),
    "U": ("X.X", "X.X", "X.X", "X.X", "XXX"),
    "X": ("X.X", "X.X", ".X.", "X.X", "X.X"),
    "Y": ("X.X", "X.X", ".X.", ".X.", ".X."),
    "C": ("XXX", "X..", "X..", "X..", "XXX"),
    "2": ("XXX", "..X", "XXX", "X..", "XXX"),
}


def text(s, word, x, y, color):
    """Stamp `word` (3x5 letters, 1 gap) with its top-left at (x, y)."""
    for i, ch in enumerate(word):
        for j, row in enumerate(FONT[ch]):
            for k, c in enumerate(row):
                if c == "X":
                    s.px(x + i * 4 + k, y + j, color)


def text_width(word):
    return len(word) * 4 - 1


def add(name, fn):
    ICONS[f"skin/{name}.png"] = fn


# ---- battery: 12x16, terminal on top, 4 bars of 2 rows inside ----
def battery(bars, color, bolt=False):
    def draw():
        s = Sprite(12, 16)
        s.rect(4, 0, 4, 1, color)
        s.rrect(0, 1, 12, 15, color, 1)
        s.rect(1, 2, 10, 13, "black")
        for k in range(bars):
            s.rect(2, 12 - 3 * k, 8, 2, color)
        if bolt:
            s.art(3, 3, [
                "...XXX",
                "..XXX.",
                ".XXX..",
                "XXXXXX",
                "..XXX.",
                ".XXX..",
                "XXX...",
            ], {"X": "yellow"})
        return s
    return draw


for name, bars, color in (("0", 0, "red"), ("20", 1, "orange"), ("50", 2, "yellow"), ("80", 3, "green"), ("full", 4, "green")):
    add(f"power-{name}%-icon" if name != "full" else "power-full-icon", battery(bars, color))
for name, color in (("0", "red"), ("25", "orange"), ("50", "yellow"), ("75", "yellow"), ("100", "green")):
    add(f"ic-power-charge-{name}%", battery(0, color, True))


# ---- speaker (7 wide, 14 tall) with sound arcs: 2-thick bands, steps of 1:1, straight in the middle ----
def speaker(s, color):
    s.rect(0, 4, 3, 6, color)
    for c in range(3, 7):
        s.rect(c, 4 - (c - 2), 1, 6 + 2 * (c - 2), color)


ARC_X = (8, 12, 17)  # left edges of the three arcs; arc k has k + 1 diagonal steps


def arc(s, k, color):
    steps = k + 1
    x0 = ARC_X[k]
    top = 7 - steps - 2
    for i in range(steps):
        s.rect(x0 + i, top + i, 2, 1, color)
        s.rect(x0 + i, top + 2 * steps + 3 - i, 2, 1, color)
    s.rect(x0 + steps, top + steps, 2, 4, color)


def cross(s, x, y, color):
    for i in range(5):
        s.rect(x + i, y + i, 2, 2, color)
        s.rect(x + 4 - i, y + i, 2, 2, color)


def volume(level):
    def draw():
        s = Sprite(22, 18)
        speaker(s, "green" if level else "gray")
        if level == 0:
            cross(s, 10, 4, "red")
        else:
            lit = 1 + (level >= 7) + (level >= 14)
            for k in range(3):
                arc(s, k, "green" if k < lit else "dgray")
        for i in range(20):
            s.rect(1 + i, 15, 1, 3, "green" if i < level else "dgray")
        return s
    return draw


for n in range(21):
    add(f"icon-volume-{n:02d}", volume(n))


def sound(muted):
    def draw():
        s = Sprite(16, 14)
        speaker(s, "gray" if muted else "green")
        if muted:
            cross(s, 9, 4, "red")
        else:
            arc(s, 0, "green")
            arc(s, 1, "green")
        return s
    return draw


add("sound-icon", sound(False))
add("sound-mute-icon", sound(True))


def headphone():
    s = Sprite(12, 12)
    s.art(0, 0, [
        "..XXXX",
        ".XXXXX",
        "XX....",
        "XX....",
        "XX....",
        "XX....",
    ], {"X": "gray"})
    s.rrect(0, 6, 3, 6, "green", 1)
    s.mirror()
    return s


add("headphone-icon", headphone)


# ---- wifi: dot and arcs around the bottom middle, cut to a 45 degree wedge ----
def wifi(count, color, w=18, h=16, r0=5.2, arcs=3):
    """Dot plus the first `count` of `arcs` arcs."""
    def draw():
        s = Sprite(w, h)
        cx, cy = w / 2 - 0.5, h - 1.5
        s.rect(w // 2 - 1, h - 2, 2, 2, color)
        for k in range(min(count, arcs)):
            r = r0 + 4 * k
            for y in range(h):
                for x in range(w):
                    dx, dy = x - cx, y - cy
                    if r - 2.2 < (dx * dx + dy * dy) ** 0.5 <= r and -dy >= abs(dx):
                        s.px(x, y, color)
        return s
    return draw


for n, (arcs, color) in enumerate(((1, "orange"), (2, "yellow"), (3, "lime"), (3, "green"))):
    add(f"icon-wifi-signal-0{n + 1}", wifi(arcs, color))


def wifi_connected():
    s = Sprite(12, 12)
    s.ellipse(5.5, 5.5, 5.8, 5.8, "green")
    for i in range(3):
        for dx in (0, 1):
            s.px(2 + i + dx, 5 + i, "white")
    for i in range(5):
        for dx in (0, 1):
            s.px(4 + i + dx, 7 - i, "white")
    return s


add("icon-wifi-connected", wifi_connected)
def wifi_locked():
    """Padlock: gray shackle, yellow body with a keyhole."""
    s = Sprite(12, 12)
    s.rect(3, 0, 3, 1, "gray")
    s.rect(2, 1, 2, 5, "gray")
    s.rrect(0, 5, 12, 7, "yellow", 1)
    s.rect(5, 7, 2, 3, "dark")
    s.mirror()
    return s


add("icon-wifi-locked", wifi_locked)


# ---- face buttons and text pills ----
BUTTONS = {"A": ("red", "white"), "B": ("yellow", "dark"), "X": ("blue", "white"), "Y": ("green", "white")}


def face(letter):
    def draw():
        body, ink = BUTTONS[letter]
        s = Sprite(11, 11)
        s.ellipse(5, 5, 5.6, 5.6, body)
        text(s, letter, 4, 3, ink)
        return s
    return draw


for letter in "ABXY":
    add(f"context-{letter.lower()}", face(letter))
for letter in "XY":
    add(f"icon-{letter.lower()}", face(letter))


def pill(word, w, h=9, body="yellow", ink="dark"):
    def draw():
        s = Sprite(w, h)
        s.rrect(0, 0, w, h, body, 2)
        text(s, word, (w - text_width(word)) // 2, (h - 5) // 2, ink)
        return s
    return draw


add("icon-L2", pill("L2", 11))
add("icon-R2", pill("R2", 11))
add("icon-OK", pill("OK", 11, body="green", ink="white"))
add("icon-START", pill("START", 21))
add("context-start", pill("START", 29))
add("context-select", pill("SELECT", 29))
add("context-menu", pill("MENU", 29))


# ---- keyboard keys and arrows ----
def key(active):
    def draw():
        s = Sprite(12, 10)
        s.rrect(0, 0, 12, 10, "green", 2)
        if not active:
            s.rrect(1, 1, 10, 8, "black", 1)
        s.art(3, 2, [
            "..XX..",
            ".XXXX.",
            "XXXXXX",
            "..XX..",
            "..XX..",
            "..XX..",
        ], {"X": "green" if not active else "white"})
        return s
    return draw


add("icon-shift", key(False))
add("icon-shift-active", key(True))


def delete():
    s = Sprite(12, 10)
    s.rrect(0, 0, 12, 10, "green", 2)
    s.rrect(1, 1, 10, 8, "black", 1)
    s.art(3, 2, [
        "..X....",
        ".XX....",
        "XXXXXXX",
        ".XX....",
        "..X....",
    ], {"X": "green"})
    return s


add("icon-delete", delete)


def space():
    s = Sprite(13, 7)
    s.art(0, 0, [
        "X...........X",
        "X...X...X...X",
        "X..XX...XX..X",
        "X.XXXXXXXXX.X",
        "X..XX...XX..X",
        "X...X...X...X",
        "X...........X",
    ], {"X": "green"})
    return s


add("icon-space", space)


def chevron(right):
    def draw():
        s = Sprite(7, 11)
        for i in range(6):
            for dx in (0, 1):
                s.px(i + dx, i, "yellow")
                s.px(i + dx, 10 - i, "yellow")
        if not right:
            s.g = [row[::-1] for row in s.g]
        return s
    return draw


for name in ("icon-left-arrow-24", "icon-menu-left-arrow-24"):
    add(name, chevron(False))
for name in ("icon-right-arrow-24", "icon-menu-right-arrow-24"):
    add(name, chevron(True))
