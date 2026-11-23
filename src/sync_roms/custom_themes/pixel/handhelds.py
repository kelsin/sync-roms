"""Handhelds and other icons drawn the same in both themes."""
from .sprite import Sprite


def face(s, cx, y, k=3, c="dark"):
    """Smiling face centered on the line between columns cx-1 and cx (a mirrored pair): eyes at y..y+1, smile at y+4."""
    s.rect(cx - k, y, 1, 2, c)
    s.rect(cx + k - 1, y, 1, 2, c)
    s.px(cx - k, y + 3, c)
    s.px(cx + k - 1, y + 3, c)
    s.rect(cx - k + 1, y + 4, 2 * k - 2, 1, c)


def plus(s, x, y, n, t, c):
    """A cross n wide and tall with arms t thick."""
    o = (n - t) // 2
    s.rect(x, y + o, n, t, c)
    s.rect(x + o, y, t, n, c)


def gb():
    """Game Boy (DMG): gray portrait body, dark bezel, magenta A/B."""
    s = Sprite(14, 22)
    s.rrect(0, 0, 14, 22, "gray", 2)
    s.rrect(1, 1, 12, 10, "dgray", 1)
    s.rect(3, 3, 8, 6, "screen")
    face(s, 7, 3, 3)
    plus(s, 1, 13, 6, 2, "dark")
    s.rrect(11, 14, 2, 2, "magenta", 0)    # A
    s.rrect(8, 17, 2, 2, "magenta", 0)     # B
    s.rect(3, 20, 3, 1, "dgray")           # select / start
    s.rect(7, 20, 3, 1, "dgray")
    return s


def gbc():
    """Game Boy Color: teal body, black bezel, wider screen."""
    s = Sprite(14, 21)
    s.rrect(0, 0, 14, 21, "teal", 2)
    s.rrect(1, 1, 12, 10, "dark", 1)
    s.rect(3, 3, 8, 6, "screen")
    face(s, 7, 3, 3)
    plus(s, 1, 13, 6, 2, "dark")
    s.rrect(11, 14, 2, 2, "dgray", 0)
    s.rrect(8, 17, 2, 2, "dgray", 0)
    s.rect(3, 19, 3, 1, "dgray")
    s.rect(7, 19, 3, 1, "dgray")
    return s


def gba():
    """Game Boy Advance: indigo landscape, shoulder buttons, d-pad left, A/B right."""
    s = Sprite(26, 15)
    s.rect(2, 0, 4, 3, "indigo")           # shoulder buttons
    s.rect(20, 0, 4, 3, "indigo")
    s.rrect(0, 2, 26, 13, "indigo", 3)
    s.rect(6, 3, 14, 10, "dark")           # black bezel
    s.rect(7, 4, 12, 8, "screen")
    face(s, 13, 5, 3)
    plus(s, 1, 6, 4, 2, "gray")
    s.rrect(23, 5, 2, 2, "gray", 0)        # A
    s.rrect(21, 8, 2, 2, "gray", 0)        # B
    s.rect(21, 12, 2, 1, "dgray")          # start / select
    s.rect(3, 12, 2, 1, "dgray")
    return s


def nds():
    """Nintendo DS open: two screens, hinge, d-pad and buttons on the lower half."""
    s = Sprite(22, 23)
    s.rrect(0, 0, 22, 11, "white", 2)
    s.rect(2, 11, 18, 1, "gray")           # hinge
    s.rrect(0, 12, 22, 11, "white", 2)
    for y, h in ((1, 9), (13, 9)):
        s.rect(4, y, 14, h, "dgray")
        s.rect(5, y + 1, 12, h - 2, "sky")
    s.rect(5, 2, 12, 7, "screen")
    face(s, 11, 3, 3)
    s.rect(1, 5, 1, 3, "gray")             # speakers
    s.rect(20, 5, 1, 3, "gray")
    plus(s, 1, 16, 3, 1, "dgray")          # d-pad
    s.px(19, 15, "dgray")                  # X Y A B diamond
    s.px(18, 16, "dgray")
    s.px(20, 16, "dgray")
    s.px(19, 17, "dgray")
    s.rect(18, 19, 2, 1, "gray")           # start / select
    s.rect(18, 21, 2, 1, "gray")
    return s


def vb():
    """Virtual Boy: red visor over a black band with two glowing red lenses on a black tripod stand."""
    s = Sprite(24, 19)
    s.rrect(0, 0, 24, 12, "red", 3)
    s.rrect(2, 3, 20, 6, "black", 1)
    s.ellipse(7.5, 5.5, 3, 2.5, "red")
    s.ellipse(16.5, 5.5, 3, 2.5, "red")
    s.rect(11, 12, 2, 3, "dark")           # neck
    s.line(11, 15, 5, 18, "dark")          # tripod legs
    s.line(12, 15, 18, 18, "dark")
    return s


def gg():
    """Game Gear: wide black landscape, big screen, d-pad and colored logo dots left, blue start and two buttons right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 3)
    s.rect(5, 1, 16, 12, "black")
    s.rect(7, 2, 12, 10, "screen")
    face(s, 13, 4, 3)
    plus(s, 1, 5, 3, 1, "gray")
    s.px(1, 2, "red")                      # the three colored dots of the logo
    s.px(2, 2, "green")
    s.px(3, 2, "blue")
    s.rrect(22, 2, 2, 2, "blue", 0)        # start
    s.rrect(22, 6, 2, 2, "dgray", 0)       # 1
    s.rrect(22, 9, 2, 2, "dgray", 0)       # 2
    return s


def lynx():
    """Atari Lynx: dark gray with chunky grips lower than the screen block."""
    s = Sprite(26, 13)
    s.rect(7, 0, 12, 11, "dgray")
    s.rrect(0, 0, 8, 13, "dgray", 3)
    s.rrect(18, 0, 8, 13, "dgray", 3)
    s.rect(7, 1, 12, 9, "black")
    s.rect(8, 2, 10, 7, "screen")
    face(s, 13, 2, 2)
    plus(s, 1, 4, 3, 1, "black")
    for y in (2, 8):                       # two black buttons high and two low
        s.rect(21, y, 2, 2, "black")
        s.rect(23, y, 2, 2, "black")
    return s


def ngp():
    """Neo Geo Pocket: dark rounded landscape, near-square screen, clicky stick left, two buttons right."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dgray", 4)
    s.rect(7, 2, 12, 12, "black")
    s.rect(8, 3, 10, 10, "screen")
    face(s, 13, 5, 3)
    s.rrect(1, 5, 5, 5, "gray", 2)         # stick ring
    s.rrect(2, 6, 3, 3, "dark", 1)         # stick
    s.rect(19, 8, 2, 2, "dark")            # A
    s.rect(22, 8, 2, 2, "dark")            # B
    return s


def ngpc():
    """Neo Geo Pocket Color: the same shape in platinum blue."""
    s = ngp()
    for row in s.g:
        for x, c in enumerate(row):
            if c == "dgray":
                row[x] = "periwinkle"
    return s


def ws():
    """WonderSwan: pearl white landscape, silver screen panel, two four-button clusters left, A/B right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "white", 3)
    s.rect(7, 1, 12, 12, "gray")
    s.rect(8, 2, 10, 8, "screen")
    face(s, 13, 3, 3)
    s.rect(9, 11, 2, 1, "dgray")           # sound / start
    s.rect(12, 11, 2, 1, "dgray")
    for y in (2, 8):                       # X and Y clusters: four buttons each
        s.rect(3, y, 2, 1, "dgray")
        s.rect(2, y + 1, 1, 2, "dgray")
        s.rect(5, y + 1, 1, 2, "dgray")
        s.rect(3, y + 3, 2, 1, "dgray")
    s.rrect(21, 8, 3, 3, "dgray", 1)
    s.rrect(21, 3, 3, 3, "dgray", 1)
    return s


def wsc():
    """WonderSwan Color: crystal orange."""
    s = ws()
    for row in s.g:
        for x, c in enumerate(row):
            if c == "white":
                row[x] = "orange"
    return s


def megaduck():
    """Mega Duck: off-white portrait body, dark bezel, teal d-pad, round A/B side by side, select/start pills."""
    s = Sprite(16, 22)
    s.rrect(0, 0, 16, 22, "white", 3)
    s.rrect(1, 1, 14, 12, "dgray", 1)
    s.rect(3, 3, 10, 8, "screen")
    face(s, 8, 4, 3)
    plus(s, 1, 15, 6, 2, "teal")
    s.rrect(8, 15, 3, 3, "teal", 1)        # B
    s.rrect(12, 15, 3, 3, "teal", 1)       # A
    s.rect(8, 19, 3, 1, "dgray")           # select / start
    s.rect(12, 19, 3, 1, "dgray")
    return s


def supervision():
    """Watara Supervision: gray controller half, ribbed hinge, screen half with teal A/B."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 12, 12, "gray", 4)
    s.rect(12, 3, 2, 6, "dark")            # hinge
    s.rect(12, 4, 2, 1, "dgray")
    s.rect(12, 6, 2, 1, "dgray")
    s.rrect(14, 0, 12, 12, "gray", 1)
    s.rect(15, 1, 10, 8, "dark")
    s.rect(16, 2, 8, 6, "screen")
    face(s, 20, 2, 2)
    plus(s, 1, 2, 6, 2, "dark")
    s.rrect(8, 3, 3, 3, "teal", 1)
    s.rrect(5, 8, 3, 3, "teal", 1)
    return s


def poke():
    """Pokemon Mini: small portrait body in clear blue, round black screen bezel, blue d-pad, A/B and a shock sensor."""
    s = Sprite(18, 22)
    s.rrect(0, 0, 18, 22, "sky", 4)
    s.ellipse(8.5, 7, 8, 6.5, "black")
    s.rect(4, 4, 10, 7, "screen")
    face(s, 9, 5, 3)
    plus(s, 2, 14, 6, 2, "blue")
    s.rect(9, 14, 2, 2, "dgray")           # shock sensor
    s.rrect(13, 14, 3, 3, "blue", 1)       # A
    s.rrect(9, 18, 3, 3, "blue", 1)        # B
    return s


def psp():
    """Sony PSP: long black slab with a silver lip, wide screen, d-pad and nub left, four face buttons right."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "dark", 3)
    s.rect(3, 11, 20, 1, "gray")           # silver lip
    s.rect(6, 1, 14, 9, "black")
    s.rect(7, 2, 12, 7, "sky")
    face(s, 13, 3, 3)
    plus(s, 1, 2, 3, 1, "gray")
    s.rrect(1, 6, 3, 3, "dgray", 1)
    s.px(22, 3, "green")                   # triangle
    s.px(21, 4, "pink")                    # square
    s.px(23, 4, "red")                     # circle
    s.px(22, 5, "blue")                    # cross
    return s


def arduboy():
    """Arduboy: credit-card sized clear board in portrait, a wide OLED above a big black d-pad and two red buttons."""
    s = Sprite(14, 20)
    s.rrect(0, 0, 14, 20, "gray", 2)
    s.rect(1, 1, 12, 7, "black")
    face(s, 7, 2, 3, "white")
    plus(s, 1, 10, 6, 2, "black")
    s.rect(11, 11, 2, 2, "red")            # B
    s.rect(8, 14, 2, 2, "red")             # A
    s.rect(5, 18, 4, 1, "dgray")           # USB
    return s


SHARED = {
    "gb": gb, "gbc": gbc, "gba": gba, "nds": nds, "vb": vb, "gg": gg, "lynx": lynx, "ngp": ngp, "ngpc": ngpc,
    "ws": ws, "wsc": wsc, "megaduck": megaduck, "supervision": supervision, "poke": poke, "psp": psp,
    "arduboy": arduboy,
}
CONSOLES = {}
CONTROLLERS = {}
