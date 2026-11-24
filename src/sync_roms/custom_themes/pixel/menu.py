"""Main-menu sprites (ic-<name>-f/n.png, 100x140 canvas)."""
from .sprite import Sprite


def heart():
    s = Sprite(20, 17)
    s.art(0, 0, [
        "..XXXX....",
        ".XXXXXX...",
        "XXXXXXXX..",
        "XXXXXXXXX.",
        "XXXXXXXXXX",
        "XXXXXXXXXX",
        "XXXXXXXXXX",
        "XXXXXXXXXX",
        ".XXXXXXXXX",
        "..XXXXXXXX",
        "...XXXXXXX",
        "....XXXXXX",
        ".....XXXXX",
        "......XXXX",
        ".......XXX",
        "........XX",
        ".........X",
    ], {"X": "red"})
    s.art(2, 2, ["WW", "W."], {"W": "white"})
    s.mirror()
    # the shine is only on the left lobe: undo its mirror
    for (x, y) in ((17, 2), (18, 2), (17, 3)):
        s.px(x, y, "red")
    return s


def clock():
    s = Sprite(20, 20)
    s.ellipse(9.5, 9.5, 9.6, 9.6, "teal")
    s.ellipse(9.5, 9.5, 7.4, 7.4, "cream")
    s.rect(9, 4, 2, 6, "dark")      # minute hand
    s.rect(9, 9, 5, 2, "dark")      # hour hand
    for x, y in ((9, 2), (10, 2), (9, 17), (10, 17)):
        s.px(x, y, "dark")
    for x, y in ((3, 9), (3, 10), (16, 9), (16, 10)):
        s.px(x, y, "dark")
    return s


def gear():
    """Three sliders: the settings icon."""
    s = Sprite(22, 17)
    for (y, x, c) in ((2, 3, "orange"), (8, 13, "teal"), (14, 7, "pink")):
        s.rect(0, y - 1, 22, 3, "gray")
        s.rrect(x, y - 2, 6, 5, c, 2)
    return s

def apps():
    """An app window with a play button."""
    s = Sprite(22, 18)
    s.rrect(0, 0, 22, 18, "indigo", 2)
    for x, c in ((3, "red"), (6, "yellow"), (9, "green")):
        s.rect(x, 1, 2, 2, c)
    s.rect(2, 5, 18, 11, "cream")
    s.art(9, 7, ["X...", "XX..", "XXX.", "XXXX", "XXX.", "XX..", "X..."], {"X": "green"})
    return s

def collection():
    """A shelf of three game cartridges."""
    s = Sprite(22, 18)
    for x, w, top, c in ((0, 6, 2, "red"), (7, 8, 0, "blue"), (16, 6, 2, "green")):
        s.rrect(x, top, w, 18 - top, c, 1)
        s.rect(x + 1, top + 2, w - 2, 6, "cream")
        s.rect(x + 1, 16, w - 2, 2, "dark")
    return s

def ghost():
    s = Sprite(18, 17)
    s.art(0, 0, [
        "...XXXXXX",
        ".XXXXXXXX",
        ".XXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXX..XXXX",
        "XX....XXX",
    ], {"X": "purple"})
    s.rect(3, 5, 3, 4, "white")
    s.rect(4, 7, 2, 2, "dark")
    s.rect(1, 10, 2, 1, "pink")
    s.mirror()
    return s


def handheld():
    """Retro home console with a cartridge in the slot, the 'games' icon of the console theme."""
    s = Sprite(22, 18)
    s.rrect(6, 0, 10, 7, "red", 1)
    s.rect(8, 2, 6, 3, "cream")
    s.rrect(0, 6, 22, 12, "gray", 2)
    s.rect(3, 8, 16, 2, "dark")      # cartridge slot
    s.rect(3, 13, 4, 2, "dgray")     # controller ports
    s.rect(15, 13, 4, 2, "dgray")
    s.rect(9, 13, 2, 2, "red")       # power
    s.rect(12, 13, 2, 2, "green")    # reset
    return s

def controller():
    """Modern gamepad with sticks and face buttons, the 'games' icon of the controller theme."""
    s = Sprite(22, 18)
    s.rrect(0, 1, 22, 12, "gray", 3)
    s.rrect(0, 8, 7, 10, "gray", 2)
    s.rrect(15, 8, 7, 10, "gray", 2)
    s.rect(2, 5, 5, 1, "dark")       # d-pad
    s.rect(4, 3, 1, 5, "dark")
    s.rect(16, 3, 2, 2, "red")       # face buttons
    s.rect(16, 7, 2, 2, "blue")
    s.rect(14, 5, 2, 2, "green")
    s.rect(18, 5, 2, 2, "yellow")
    s.ellipse(8.5, 10.5, 1.8, 1.8, "dgray")  # sticks
    s.ellipse(13.5, 10.5, 1.8, 1.8, "dgray")
    return s

SPRITES = {
    "favorite": heart, "recent": clock, "setting": gear, "app": apps,
    "collection": collection, "retroarch": ghost,
}
