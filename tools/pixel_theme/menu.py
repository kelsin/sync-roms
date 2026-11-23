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
    s = Sprite(20, 20)
    for x, y in ((8, 0), (8, 16), (0, 8), (16, 8)):      # N, S, W, E teeth
        s.rect(x, y, 4, 4, "gray")
    for x, y in ((2, 2), (14, 2), (2, 14), (14, 14)):    # diagonal teeth
        s.rect(x, y, 4, 4, "gray")
    s.ellipse(9.5, 9.5, 7.3, 7.3, "gray")
    s.ellipse(9.5, 9.5, 3.2, 3.2, None)
    return s


def apps():
    s = Sprite(20, 20)
    for (x, y), c in zip(((0, 0), (11, 0), (0, 11), (11, 11)), ("orange", "green", "blue", "pink")):
        s.rrect(x, y, 9, 9, c, 2)
    return s


def collection():
    s = Sprite(22, 18)
    s.rect(0, 0, 9, 3, "orange")
    s.rrect(0, 2, 22, 16, "orange", 1)
    s.art(7, 5, [
        "....XX....",
        "....XX....",
        "XXXXXXXXXX",
        ".XXXXXXXX.",
        "..XXXXXX..",
        "..XXXXXX..",
        ".XXX..XXX.",
        ".XX....XX.",
    ], {"X": "yellow"})
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
    """Portrait Game Boy, the 'games' icon of the console theme."""
    s = Sprite(18, 24)
    s.rrect(0, 0, 18, 24, "gray", 2)
    s.rect(2, 2, 14, 10, "dgray")
    s.rect(3, 3, 12, 8, "screen")
    s.rect(5, 5, 2, 2, "dark")
    s.rect(11, 5, 2, 2, "dark")
    s.rect(7, 8, 4, 1, "dark")
    s.rect(6, 7, 1, 1, "dark")
    s.rect(11, 7, 1, 1, "dark")
    s.rect(2, 15, 5, 1, "dark")      # d-pad
    s.rect(4, 13, 1, 5, "dark")
    s.rect(11, 14, 2, 2, "red")      # B
    s.rect(14, 12, 2, 2, "red")      # A
    s.line(9, 20, 12, 17, "dgray")   # speaker
    s.line(11, 21, 14, 18, "dgray")
    return s


def controller():
    """Classic pad, the 'games' icon of the controller theme."""
    s = Sprite(24, 14)
    s.rrect(0, 0, 24, 14, "gray", 3)
    s.rect(3, 6, 6, 2, "dark")
    s.rect(5, 4, 2, 6, "dark")
    s.rect(15, 7, 3, 3, "red")
    s.rect(19, 4, 3, 3, "red")
    s.rect(10, 9, 2, 1, "dgray")
    s.rect(13, 9, 2, 1, "dgray")
    return s


SPRITES = {
    "favorite": heart, "recent": clock, "setting": gear, "app": apps,
    "collection": collection, "retroarch": ghost,
}
