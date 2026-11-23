"""Arcade systems, engines, fantasy consoles and ports."""
from .sprite import Sprite


def _cab(body, marquee, trim, screen_art, rows=1, stick="red"):
    """Upright arcade cabinet, 20x23: marquee, screen, control panel with stick and buttons, coin door."""
    s = Sprite(20, 23)
    s.rrect(0, 0, 20, 5, marquee, 1)             # marquee
    s.rect(0, 5, 20, 8, body)                    # monitor hood
    s.rect(2, 6, 16, 6, "black")                 # screen
    s.art(3, 7, screen_art, {"X": "screen", "Y": "yellow", "R": "red", "C": "cyan"})
    s.rect(0, 13, 20, 3, trim)                   # control panel
    s.rect(2, 16, 16, 7, body)                   # lower cabinet
    s.rect(7, 18, 6, 4, "dark")                  # coin door
    s.rect(9, 19, 2, 1, "yellow")
    s.rect(9, 21, 2, 1, "gray")
    s.rect(4, 13, 2, 2, stick)                   # stick
    for r in range(rows):                        # buttons: a row of three per row
        for x in (9, 12, 15):
            s.rect(x, 13 + r * 2, 2, 1, "white")
    return s


INVADER = [
    "...X..X....X..",
    "....X..X..X...",
    "...XXXXXXXX...",
    "..XX.XXXX.XX..",
    "..XXXXXXXXXX..",
]
PAC = [
    "..............",
    "...YYYY.......",
    "..YYYY....Y.Y.",
    "..YYY.....Y.Y.",
    "..YYYY........",
]
VERSUS = [
    "RRRRRR..CCCCCC",
    "..............",
    "..XX......XX..",
    "..XX......XX..",
    ".XXXX....XXXX.",
]


def arcade_cab():
    return _cab("blue", "yellow", "dgray", INVADER)


def mame_cab():
    """A homebuilt MAME cabinet: wood body, teal marquee, six buttons."""
    return _cab("brown", "teal", "dark", PAC, rows=2, stick="yellow")


def cps1_cab():
    """Street Fighter II upright: black cabinet, purple marquee, two red-ball sticks with six buttons each (blue side, red side)."""
    s = _cab("dark", "purple", "dgray", VERSUS, rows=0)
    s.rect(2, 2, 16, 1, "orange")                # marquee art band
    s.rect(0, 13, 10, 3, "periwinkle")           # player 1 panel
    s.rect(10, 13, 10, 3, "maroon")              # player 2 panel
    for x0, c in ((0, "blue"), (10, "red")):
        s.rect(x0 + 1, 13, 2, 2, "red")          # stick
        for x in (x0 + 4, x0 + 6, x0 + 8):       # six buttons: two rows of three
            s.rect(x, 13, 1, 1, c)
            s.rect(x, 15, 1, 1, c)
    return s


def cps2_board():
    """CPS2: the A and B boards in their blue plastic cases (blue is the USA color) with a gold JAMMA edge."""
    s = Sprite(26, 22)
    s.rrect(0, 0, 26, 8, "blue", 2)              # B board case
    s.rect(3, 2, 8, 4, "sky")                    # battery bay
    for x in range(14, 24, 3):
        s.rect(x, 2, 1, 4, "indigo")             # vent slots
    s.rrect(0, 9, 26, 8, "blue", 2)              # A board case
    s.rect(3, 11, 20, 4, "indigo")
    s.rect(5, 12, 6, 2, "white")                 # label
    s.rect(3, 17, 20, 2, "green")                # PCB edge
    for x in range(4, 23, 2):
        s.rect(x, 19, 1, 3, "yellow")            # gold JAMMA fingers
    return s


def _cart(w, h, shell, label, stripe):
    """Cartridge standing up, connector edge at the bottom."""
    s = Sprite(w, h)
    s.rrect(0, 0, w, h - 3, shell, 2)
    s.rect(2, 3, w - 4, h - 10, label)
    s.rect(2, h - 6, w - 4, 2, stripe)
    return s


def cps3_cart():
    """CPS3 security cartridge: a dark plastic cart, white sticker with the blue and yellow CP System pill."""
    s = Sprite(22, 23)
    s.rrect(0, 0, 22, 19, "dark", 2)
    s.rect(3, 3, 16, 10, "white")
    s.rrect(4, 5, 14, 6, "blue", 2)
    s.rrect(5, 6, 12, 4, "yellow", 1)
    s.rect(4, 14, 14, 2, "dgray")
    s.rect(3, 19, 16, 4, "dgray")                # connector
    for x in range(5, 18, 3):
        s.rect(x, 19, 2, 4, "yellow")
    return s


def atomiswave_cart():
    """Atomiswave: Sammy's squarish red cartridge, striped white label over a black band, a tab at the bottom."""
    s = Sprite(24, 22)
    s.rrect(0, 0, 24, 19, "red", 2)
    s.rect(2, 2, 20, 9, "white")
    for y in (4, 6, 8):
        s.rect(2, y, 20, 1, "gray")
    s.rect(2, 11, 20, 5, "black")
    s.rect(3, 12, 9, 2, "white")                 # serial strip
    s.rect(16, 12, 2, 3, "orange")               # logo
    s.rect(18, 12, 2, 3, "green")
    s.rect(7, 19, 10, 3, "red")                  # tab
    s.rect(7, 20, 1, 2, "black")
    s.rect(16, 20, 1, 2, "black")
    return s


def naomi_cart():
    """NAOMI: the navy plastic of the board with its vent ribs, and a red and yellow label like the GD-ROM discs."""
    s = Sprite(26, 20)
    s.rrect(0, 0, 26, 15, "navy", 2)
    for x in range(4, 22, 3):
        s.rect(x, 2, 1, 4, "dark")
    s.rect(4, 8, 18, 5, "red")
    s.rect(4, 8, 18, 1, "yellow")
    s.rect(6, 11, 14, 1, "yellow")
    s.rect(2, 15, 22, 5, "dark")
    for x in range(4, 22, 3):
        s.rect(x, 16, 2, 4, "tan")
    return s


BASE = [                                         # a clean 9x9 round stick base
    "..XXXXX..",
    ".XXXXXXX.",
    "XXXXXXXXX",
    "XXXXXXXXX",
    "XXXXXXXXX",
    "XXXXXXXXX",
    "XXXXXXXXX",
    ".XXXXXXX.",
    "..XXXXX..",
]
BALL = [".XXX.", "XXXXX", "XXXXX", "XXXXX", ".XXX."]


def _panel(rows, stick="red", body="dark", colors=("red", "yellow", "green", "white", "orange", "pink")):
    """Control panel, 26x17: a ball-top stick and 3x3 buttons, `rows` being the count in each row."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, body, 2)
    s.art(2, 4, BASE, {"X": "black"})
    s.art(4, 6, BALL, {"X": stick})
    s.px(5, 7, "white")
    n = 0
    for r, count in enumerate(rows):
        y = 3 + r * 6 if len(rows) == 2 else 7
        for i in range(count):
            s.rect(12 + i * 5, y, 3, 3, colors[n % 6])
            n += 1
    return s


def arcade_stick():
    return _panel([2], "red", "blue")


def mame_stick():
    return _panel([3, 3], "yellow", "brown")


def cps1_stick():
    return _panel([3, 3], "red", "dark")


def cps2_stick():
    return _panel([3, 3], "orange", "blue")


def cps3_stick():
    return _panel([3, 3], "blue", "dark")


def atomiswave_stick():
    return _panel([2, 2], "blue", "red", ("yellow", "white", "green", "orange"))


def naomi_stick():
    return _panel([3], "red", "navy")


def doom():
    """Doom's status-bar marine: bareheaded, buzz-cut brown hair, scowl, a cut, green armor below."""
    s = Sprite(20, 22)
    s.rect(2, 6, 16, 12, "tan")                  # face
    s.rrect(2, 0, 16, 7, "brown", 3)             # hair
    s.rect(4, 9, 5, 1, "brown")                  # brows
    s.rect(11, 9, 5, 1, "brown")
    s.rect(4, 10, 5, 2, "white")                 # eyes
    s.rect(6, 10, 2, 2, "blue")
    s.rect(11, 10, 5, 2, "white")
    s.rect(12, 10, 2, 2, "blue")
    s.rect(9, 12, 2, 3, "brown")                 # nose
    s.rect(6, 15, 8, 2, "dark")                  # gritted teeth
    s.rect(7, 15, 6, 1, "white")
    s.rect(14, 13, 2, 3, "red")                  # cut
    s.rrect(0, 18, 20, 4, "green", 1)            # armor
    return s


def quake():
    """A rocket, Quake's signature weapon, in the game's brown and steel."""
    s = Sprite(14, 23)
    for y, x in enumerate((5, 4, 3, 2, 2, 1, 1)):    # nose, 2:1 curve
        s.rect(x, y, 7 - x, 1, "dgray")
    s.rect(0, 7, 7, 9, "tan")
    s.rect(0, 9, 7, 1, "brown")
    s.rect(0, 12, 7, 1, "brown")
    s.rect(0, 15, 7, 1, "yellow")
    s.rect(0, 16, 7, 1, "brown")
    s.rect(3, 17, 4, 6, "orange")                # flame
    s.rect(5, 19, 2, 4, "yellow")
    s.mirror()
    return s


def scummvm():
    """A magnifying glass in ScummVM's slime green and steel gray: the adventure-game hunt for clues."""
    s = Sprite(24, 22)
    s.art(0, 0, [
        "....XXXXXXXX....",
        "..XXXXXXXXXXXX..",
        ".XXXXXXXXXXXXXX.",
        ".XXXXXXXXXXXXXX.",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXX",
        ".XXXXXXXXXXXXXX.",
        ".XXXXXXXXXXXXXX.",
        "..XXXXXXXXXXXX..",
        "....XXXXXXXX....",
    ], {"X": "lime"})
    s.art(2, 2, [
        "..XXXXXXXX..",
        ".XXXXXXXXXX.",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        ".XXXXXXXXXX.",
        "..XXXXXXXX..",
    ], {"X": "sky"})
    s.rect(4, 4, 3, 1, "white")                  # glint
    s.rect(4, 5, 1, 2, "white")
    for i in range(7):                           # handle, 1:1 diagonal
        s.rect(14 + i, 14 + i, 3, 3, "dgray")
    s.rect(20, 20, 3, 2, "dgray")
    return s


def easyrpg():
    """EasyRPG's emblem: a pale green disc with a dark green swirl."""
    s = Sprite(22, 22)
    s.ellipse(10.5, 10.5, 10.5, 10.5, "lime")
    s.ellipse(10.5, 10.5, 8.5, 8.5, "cream")
    ring = [".XXXX.", "XXXXXX", "XX..XX", "XX..XX", "XXXXXX", ".XXXX."]
    for x, y in ((8, 3), (3, 11), (13, 11)):     # three curls round a hub
        s.art(x, y, ring, {"X": "forest"})
    s.rect(9, 8, 4, 4, "forest")
    return s


def openbor():
    """A clenched fist from the front: four knuckles, the thumb across, a red wristband."""
    s = Sprite(20, 23)
    for i in range(4):
        s.rrect(2 + i * 4, 1, 4, 10, "tan", 1)   # fingers
    for x in (5, 9, 13):
        s.rect(x, 3, 1, 7, "brown")
    s.rrect(2, 10, 14, 6, "tan", 2)              # thumb across
    s.rect(3, 10, 12, 1, "brown")
    s.rect(15, 11, 1, 4, "brown")
    s.rect(4, 16, 12, 3, "tan")                  # wrist
    s.rrect(3, 19, 14, 4, "red", 1)              # wristband
    return s


HEART = [
    "..XXXX..XXXX..",
    ".XXXXXXXXXXXX.",
    "XXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXX",
    ".XXXXXXXXXXXX.",
    "..XXXXXXXXXX..",
    "...XXXXXXXX...",
    "....XXXXXX....",
    ".....XXXX.....",
    "......XX......",
]


def chai():
    """ChaiLove's emblem: a blue swirl disc, dark on its right rim, round a white heart (LOVE's heart)."""
    s = Sprite(22, 22)
    s.ellipse(10.5, 10.5, 10.5, 10.5, "navy")
    for y in range(22):                          # the disc minus a shifted copy leaves the dark rim on the right
        for x in range(22):
            if ((x - 9) / 10.5) ** 2 + ((y - 10.5) / 10.5) ** 2 <= 1.0 and s.g[y][x]:
                s.px(x, y, "blue")
    s.ellipse(10.5, 10.5, 8.5, 8.5, "sky")
    s.art(4, 5, HEART, {"X": "white"})
    return s


def tic():
    """TIC-80: a little retro computer whose screen shows the SWEETIE-16 palette it starts with."""
    s = Sprite(24, 22)
    s.rrect(0, 0, 24, 15, "navy", 2)             # monitor
    s.rect(2, 2, 20, 10, "black")
    pal = ["dark", "purple", "red", "orange", "yellow", "lime", "green", "teal",
           "navy", "blue", "sky", "cyan", "white", "gray", "dgray", "indigo"]
    for i, c in enumerate(pal):
        s.rect(4 + (i % 8) * 2, 4 + (i // 8) * 2, 2, 2, c)
    s.rect(4, 9, 8, 1, "cyan")                   # a line of code
    s.rect(10, 13, 4, 1, "dgray")
    s.rect(6, 15, 12, 2, "gray")                 # neck
    s.rrect(0, 17, 24, 5, "gray", 1)             # base / keys
    for x in range(2, 22, 3):
        s.rect(x, 19, 2, 1, "dgray")
    return s


def pico():
    """PICO-8: its cartridge, a dark gray case with a game picture and the pink strip."""
    s = Sprite(18, 23)
    s.rrect(0, 0, 18, 23, "dgray", 2)
    s.rect(2, 2, 14, 13, "sky")
    s.rect(2, 11, 14, 4, "green")
    s.rect(11, 4, 2, 2, "yellow")                # sun
    s.rect(5, 7, 2, 1, "tan")                    # little hero
    s.rect(5, 8, 2, 3, "pink")
    s.rect(2, 16, 14, 2, "pink")
    s.rect(3, 20, 12, 3, "dark")                 # edge connector
    for x in range(4, 15, 2):
        s.rect(x, 21, 1, 2, "yellow")
    return s


def ports():
    """A plug with a face, the cable below."""
    s = Sprite(14, 23)
    s.rect(2, 0, 2, 6, "gray")                   # prongs
    s.rect(8, 0, 2, 6, "gray")
    s.rect(2, 0, 2, 1, "white")
    s.rect(8, 0, 2, 1, "white")
    s.rrect(0, 6, 12, 10, "orange", 2)
    s.rect(3, 9, 2, 2, "black")
    s.rect(7, 9, 2, 2, "black")
    s.rect(4, 12, 4, 1, "dark")
    s.rect(3, 16, 6, 2, "dgray")
    s.rect(4, 18, 4, 5, "dgray")
    return s


SHARED = {"doom": doom, "quake": quake, "scummvm": scummvm, "easyrpg": easyrpg, "openbor": openbor,
          "chai": chai, "tic": tic, "pico": pico, "ports": ports}
CONSOLES = {"arcade": arcade_cab, "mame": mame_cab, "cps1": cps1_cab, "cps2": cps2_board, "cps3": cps3_cart,
            "atomiswave": atomiswave_cart, "naomi": naomi_cart}
CONTROLLERS = {"arcade": arcade_stick, "mame": mame_stick, "cps1": cps1_stick, "cps2": cps2_stick,
               "cps3": cps3_stick, "atomiswave": atomiswave_stick, "naomi": naomi_stick}
