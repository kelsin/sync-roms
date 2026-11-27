"""Pixel sprites for more ES-DE systems missing from the Spruce set: CONSOLES and CONTROLLERS keyed by ES-DE name.

Not in build.BATCHES, so the Spruce themes don't change; esde/systems.py maps them through EXTRA.
"""
from .arcade import HEART, _panel
from .handhelds import face, plus
from .nintendo_sega import body_from_half, diamond, on, sfc_pad
from .others import jaguar_pad, keys
from .sprite import Sprite


# ---------------------------------------------------------------- 3DO

def threedo_console():
    """3DO, Panasonic FZ-1 (Wikimedia, Evan-Amos, "3DO-FZ-1-Console-FL"): the black console with the square lid on
    top, the round ribbed columns at its corners with the silver power and open / close buttons on the front ones,
    and the disc tray with the gold Panasonic name in the middle."""
    s = Sprite(26, 17)
    s.rrect(3, 0, 20, 7, "dgray", 2)            # lid
    s.rect(3, 5, 20, 10, "dark")
    s.rrect(0, 4, 6, 13, "dark", 2)             # front column
    s.rect(5, 6, 1, 9, "black")                 # its seam with the body
    s.rect(2, 6, 1, 9, "black")                 # rib
    s.rect(2, 9, 2, 1, "gray")                  # power / open-close
    s.rect(7, 8, 6, 3, "black")                 # disc tray
    s.mirror()
    s.rect(10, 9, 6, 1, "tan")                  # gold name
    return s


def threedo_pad():
    """3DO pad, Panasonic FZ-JP1X (Wikimedia, "Panasonic-3DO-Controller"): the black pad with a round lobe at each
    end, the gray d-pad in its black ring on the left lobe, the stop and play / pause keys, and the big gray A B C
    rising to the right."""
    tops = [2, 1, 0, 0, 0, 0, 0, 1, 2, 2, 2, 2, 2]
    bottoms = [13, 15, 16, 17, 17, 17, 17, 16, 16, 16, 16, 16, 16]
    s = body_from_half(tops, bottoms, "dark")
    s.ellipse(4.5, 8.5, 3.1, 3.1, "black")      # d-pad ring
    plus(s, 2, 6, 6, 2, "gray")
    s.rect(9, 4, 2, 1, "dgray")                 # stop
    s.rect(12, 4, 2, 1, "dgray")                # play / pause
    for x, y in ((11, 12), (16, 8), (21, 4)):   # A B C
        s.ellipse(x, y, 2.6, 2.6, "gray")
    return s


# ---------------------------------------------------------------- CD-i

def cdi_console():
    """Philips CD-i 910 (Wikimedia, Evan-Amos, "CD-i-910-Console-Set"): the flat gray player, the vent grille at
    the back of the top, the disc tray on the left of the front, the black display and the previous / play / next
    keys on the right."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dgray", 1)
    on(s, 0, 0, 26, 5, "gray")                  # top
    keys(s, 14, 2, 5, 2, "dgray", 1, 1, 1, 0)   # vent grille
    s.rect(2, 6, 9, 3, "dark")                  # disc tray
    s.rect(4, 7, 2, 1, "gray")                  # its disc logo
    s.rect(12, 6, 6, 3, "black")                # display
    for x in (19, 21, 23):                      # previous / play / next
        s.rect(x, 7, 1, 1, "gray")
    s.rect(2, 10, 22, 1, "dark")                # lower front
    s.rect(3, 12, 2, 1, "dark")                 # on / off
    s.rect(21, 12, 2, 1, "dark")                # pause / stop
    return s


def cdi_pad():
    """CD-i gamepad (Wikimedia, Evan-Amos, "CD-i-Gamepad"): the gray dog-bone pad, the big black thumb disc with
    its gold centre on the left lobe, the gray 1/2 button and three black buttons in a diamond on the right."""
    tops = [5, 3, 2, 1, 1, 1, 2, 2, 3, 4, 4, 4, 4]
    bottoms = [11, 13, 14, 15, 15, 15, 14, 14, 14, 13, 12, 12, 12]
    s = body_from_half(tops, bottoms, "dgray")
    s.ellipse(5.5, 8.5, 4, 4, "black")          # thumb disc
    s.rect(5, 8, 2, 2, "tan")
    diamond(s, 16, 4, "black", "gray", "black", "black")
    return s


# ---------------------------------------------------------------- PC-FX

def pcfx_console():
    """NEC PC-FX (Wikimedia, Evan-Amos, "NEC-PC-FX-Front", "PC-FX-Console-Set"): the white upright tower, the vent
    slits in its top split by the lid latch, the narrow front panel with the PC-FX logo, the power and busy lights,
    the expansion door and the two pad ports at the bottom."""
    s = Sprite(18, 23)
    s.rrect(0, 0, 18, 23, "white", 1)
    for x in (2, 4, 6):                         # vent slits
        s.rect(x, 1, 1, 3, "gray")
    s.rect(1, 5, 7, 1, "gray")                  # lid seam
    s.rect(4, 6, 1, 16, "gray")                 # front panel edge
    s.mirror()
    s.rect(8, 3, 2, 3, "dark")                  # lid latch
    s.rect(7, 8, 2, 2, "yellow")                # logo
    s.rect(7, 10, 2, 2, "purple")
    s.rect(9, 8, 2, 4, "red")
    s.px(7, 13, "dgray")                        # power / busy
    s.px(10, 13, "dgray")
    s.rect(6, 15, 6, 1, "gray")                 # expansion door
    s.rect(7, 17, 4, 1, "dgray")                # pad ports
    s.rect(7, 19, 4, 1, "dgray")
    return s


def pcfx_pad():
    """PC-FX pad (Wikimedia, Evan-Amos, "PC-FX-Console-Set"): the white pad, the gray d-pad on its round base on the
    left, the two mode switches and select / run in the middle, and the six gray buttons I to VI in two rows."""
    tops = [4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
    bottoms = [12, 13, 14, 15, 15, 15, 14, 14, 14, 14, 14, 14, 14]
    s = body_from_half(tops, bottoms, "white")
    s.ellipse(4.5, 8.5, 3.1, 3.1, "gray")       # d-pad base
    plus(s, 2, 6, 6, 2, "dgray")
    s.rect(9, 5, 2, 1, "dgray")                 # mode switches
    s.rect(9, 7, 2, 1, "dgray")
    s.rect(9, 12, 2, 1, "gray")                 # select / run
    s.rect(12, 12, 2, 1, "gray")
    for y in (4, 8):                            # IV V VI over III II I
        for x in (12, 16, 20):
            s.rect(x, y, 3, 3, "gray")
    return s


# ---------------------------------------------------------------- Jaguar CD

def jaguarcd_console():
    """Atari Jaguar CD (Wikimedia, Evan-Amos, "Atari-Jaguar-CD-wController"): the black CD drive sitting on top of a
    Jaguar, its round lid with the oval window and the red Jaguar CD mark, over the Jaguar's ribbed sides and the
    red button on its front."""
    s = Sprite(26, 22)
    s.rrect(0, 9, 26, 13, "dark", 3)            # Jaguar
    for y in (13, 15, 17):                      # ribs
        s.rect(2, y, 2, 1, "dgray")
    s.rect(5, 17, 8, 3, "dgray")                # front strip
    s.rrect(2, 0, 22, 12, "dark", 3)            # CD drive
    s.rect(4, 11, 18, 1, "black")               # its base on the Jaguar
    s.mirror()
    s.ellipse(12.5, 5.5, 9, 4.5, "black")       # lid
    s.ellipse(12.5, 5.5, 8, 3.5, "dark")
    s.rect(7, 5, 4, 2, "dgray")                 # oval window
    for i in range(3):                          # Jaguar CD mark
        s.rect(13 + 2 * i, 7 - i, 2, 1, "red")
    s.rect(11, 17, 4, 2, "red")                 # button
    return s


# ---------------------------------------------------------------- Arcadia 2001

def arcadia_console():
    """Emerson Arcadia 2001 (Wikimedia, Evan-Amos, "Emerson-Arcadia-2001"): the dark console with its woodgrain
    base, a keypad controller stored in the bay at each side (gold keypad over a stick on a gold disc), the
    cartridge slot, the silver panel with the gold keys and the grille in the middle."""
    s = Sprite(26, 18)
    s.rrect(0, 1, 26, 17, "dark", 2)
    s.rrect(0, 13, 26, 5, "brown", 2)           # woodgrain base
    s.rect(2, 14, 22, 1, "tan")
    s.rrect(1, 0, 7, 13, "black", 1)            # stored controller
    s.rect(2, 2, 5, 5, "tan")                   # keypad
    s.ellipse(4, 10, 1.6, 1.6, "tan")           # stick on its disc
    s.mirror()
    s.px(4, 10, "black")
    s.px(21, 10, "black")
    s.rect(10, 3, 6, 1, "black")                # cartridge slot
    s.rect(9, 5, 8, 5, "gray")                  # panel
    s.px(10, 6, "red")                          # logo stripes
    s.px(11, 6, "green")
    s.px(12, 6, "blue")
    s.px(10, 8, "tan")                          # keys
    s.px(12, 8, "tan")
    s.rect(14, 8, 2, 1, "tan")                  # power
    s.rect(10, 11, 6, 1, "black")               # grille
    return s


def arcadia_pad():
    """Arcadia 2001 controller (Wikimedia, Evan-Amos, "Emerson-Arcadia-2001"): the black handset with the coloured
    stripes of the logo, the gold twelve-key pad and the stick on its gold disc at the bottom."""
    s = Sprite(15, 23)
    s.rrect(0, 0, 15, 23, "dark", 3)
    s.px(4, 2, "red")                           # logo stripes
    s.px(5, 2, "green")
    s.px(6, 2, "blue")
    s.rect(8, 2, 3, 1, "gray")
    s.rect(2, 4, 11, 9, "tan")                  # keypad
    for y in (5, 7, 9, 11):
        s.rect(3, y, 2, 1, "brown")
        s.rect(6, y, 3, 1, "brown")
        s.rect(10, y, 2, 1, "brown")
    s.ellipse(7, 17, 3.6, 3.6, "tan")           # stick on its disc
    s.ellipse(7, 17, 1.6, 1.6, "black")
    return s


# ---------------------------------------------------------------- Game.com

def gamecom():
    """Tiger Game.com (Wikimedia, Evan-Amos, "Tiger-Game-Com-FL"): the silver handheld with its dark lower band,
    the speaker holes and the black round d-pad on the left, the touch screen in the middle, the stylus in the band
    below it, the teal power button, A B C D and the three teal keys on the right. It is also its own
    controller."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "gray", 3)
    on(s, 0, 13, 26, 4, "dgray")                # lower band
    keys(s, 3, 3, 2, 2, "dgray", 1, 1, 1, 1)    # speaker
    s.ellipse(4, 9, 2.6, 2.6, "black")          # d-pad
    plus(s, 3, 8, 3, 1, "dgray")
    s.rect(8, 2, 10, 10, "dgray")               # screen bezel
    s.rect(8, 3, 10, 8, "screen")               # 5:4
    face(s, 13, 4, 3)
    s.rect(20, 2, 2, 2, "teal")                 # power
    for x in (19, 22):                          # A B / C D
        s.rect(x, 5, 2, 2, "dark")
        s.rect(x, 8, 2, 2, "dark")
    s.rect(4, 14, 9, 1, "black")                # stylus
    for x in (14, 17, 20):                      # menu / sound / pause
        s.rect(x, 14, 2, 1, "teal")
    return s


# ---------------------------------------------------------------- Uzebox

def uzebox_console():
    """Uzebox (Wikimedia, "Uze open console 01", "Uzebox"): the bare green board, its big black microcontroller,
    the pink headers, the yellow and white video and audio jacks at the back and the two gray SNES pad ports at
    the front."""
    s = Sprite(26, 18)
    s.rrect(15, 0, 4, 4, "yellow", 1)           # video / audio jacks, behind the board's edge
    s.rrect(20, 0, 4, 4, "white", 1)
    s.rrect(0, 2, 26, 14, "forest", 1)          # board
    s.rect(3, 4, 11, 3, "black")                # microcontroller
    s.rect(16, 6, 7, 2, "pink")                 # headers
    s.rect(3, 9, 3, 2, "black")                 # small chips
    s.rect(8, 9, 3, 2, "black")
    for x in (3, 15):                           # SNES pad ports
        s.rrect(x, 12, 8, 6, "gray", 1)
        s.rect(x + 1, 14, 6, 1, "dark")
    return s


# ---------------------------------------------------------------- Sega Model 2

def model2_board():
    """Sega Model 2 (KLOV, Virtua Fighter 2 "PCB Game Circuit Board"): the green board stack sitting in its open
    galvanised steel cage, the rows of black RAM chips across the back and the big custom chips in front."""
    s = Sprite(26, 20)
    s.rrect(0, 0, 26, 20, "gray", 1)            # cage
    s.rect(2, 2, 22, 16, "dgray")               # its floor in shadow
    s.rect(3, 3, 20, 14, "forest")              # board
    for x in (12, 15, 18, 21):                  # RAM rows
        s.rect(x - 1, 4, 2, 4, "black")
    s.rect(4, 4, 5, 3, "black")                 # custom chips
    s.rect(4, 10, 4, 4, "black")
    s.rect(10, 10, 4, 4, "black")
    s.rect(16, 10, 6, 2, "black")
    s.rect(16, 14, 6, 1, "white")               # connector
    return s


def model2_stick():
    """Virtua Fighter 2 panel (KLOV): the blue panel of the Sega upright, a red ball-top stick and the three
    buttons guard, punch and kick."""
    return _panel([3], "red", "blue", ("yellow", "yellow", "yellow"))


# ---------------------------------------------------------------- Sega Model 3

def model3_cab():
    """Virtua Fighter 3 in a Sega Blast City (KLOV, Virtua Fighter 3 "Cabinet"): the white cabinet, the teal VF3
    marquee over the red Blast City strip, the wide screen, the dark panel with red-ball sticks and yellow buttons,
    and the coin door."""
    s = Sprite(20, 23)
    s.rrect(1, 0, 18, 5, "teal", 1)             # marquee
    s.rect(1, 5, 18, 1, "red")                  # Blast City strip
    s.rect(0, 6, 20, 8, "white")                # hood
    s.rect(2, 7, 16, 6, "black")                # screen
    s.rect(3, 8, 14, 3, "sky")                  # VF3's beach
    s.rect(3, 11, 14, 1, "tan")
    s.rect(0, 14, 20, 4, "dgray")               # panel
    s.rect(2, 18, 16, 5, "white")               # lower cabinet
    s.rect(7, 19, 6, 3, "gray")                 # coin door
    s.rect(9, 20, 2, 1, "dark")
    s.rect(2, 15, 2, 2, "red")                  # sticks
    s.px(5, 16, "yellow")                       # buttons
    s.px(7, 16, "yellow")
    s.mirror()
    s.rect(7, 2, 6, 1, "red")                   # marquee title
    return s


def model3_stick():
    """Virtua Fighter 3 panel (KLOV, Blast City): the dark panel, a red ball-top stick and the four buttons guard,
    punch, kick and escape."""
    return _panel([2, 2], "red", "dark", ("yellow", "yellow", "yellow", "red"))


# ---------------------------------------------------------------- Sega ST-V

def stv_board():
    """Sega ST-V (Wikimedia, "Sega ST-V Dynamite Deka PCB 20100324"): the gray game cartridge, a big Saturn-like
    cart with a white label, the blue ST-V mark and the blue SEGA logo, standing in the green board with its white
    connector strips and black chips."""
    s = Sprite(26, 22)
    s.rrect(4, 0, 18, 12, "gray", 2)            # cartridge
    s.rect(6, 2, 14, 6, "white")                # label
    s.rect(7, 3, 4, 2, "blue")                  # ST-V mark
    s.rect(13, 3, 6, 2, "blue")                 # SEGA logo
    s.rect(7, 6, 12, 1, "dgray")                # game title
    s.rrect(0, 10, 26, 12, "forest", 1)         # board
    s.rect(2, 11, 9, 1, "white")                # connector strips
    s.rect(15, 11, 9, 1, "white")
    s.rect(3, 13, 4, 3, "black")                # chips
    s.rect(9, 13, 4, 3, "black")
    s.rect(15, 13, 4, 3, "black")
    s.rect(21, 13, 3, 3, "black")
    s.rect(2, 18, 9, 1, "white")
    s.rect(15, 18, 9, 1, "white")
    return s


def stv_stick():
    """ST-V panel: the gray Sega Astro City panel the ST-V games ran in, a red ball-top stick and three buttons
    (Die Hard Arcade, Virtua Fighter Remix and Cotton 2 use three)."""
    return _panel([3], "red", "gray", ("blue", "green", "red"))


# ---------------------------------------------------------------- Triforce

def triforce_box():
    """Triforce (Wikimedia, "Triforce hardware"): the blue box, its lid rounded off at the back right, the white
    label with the triangle of the Triforce logo, and the black front with its connectors."""
    s = Sprite(26, 20)
    s.rect(0, 0, 26, 12, "indigo")              # lid
    for y, cut in enumerate((6, 4, 2, 1)):      # its rounded back right corner, 2:1 then 1:1
        s.rect(26 - cut, y, cut, 1, None)
    s.rect(0, 12, 26, 8, "dark")                # front
    s.rrect(7, 2, 11, 5, "white", 1)            # label
    s.line(12, 3, 10, 5, "indigo")              # triangle
    s.line(12, 3, 14, 5, "indigo")
    s.rect(10, 5, 5, 1, "indigo")
    s.rect(2, 14, 4, 2, "gray")                 # connectors
    s.rect(8, 14, 6, 2, "gray")
    s.rect(16, 14, 2, 4, "white")
    s.rect(20, 14, 4, 4, "black")               # vent
    return s


def triforce_stick():
    """Triforce panel: a stick with three buttons, as Virtua Striker 4's short pass, long pass and shoot, on the
    board's blue."""
    return _panel([3], "yellow", "indigo", ("red", "blue", "green"))


# ---------------------------------------------------------------- Taito Type X

def typex_box():
    """Taito Type X (Emulation General wiki, "Type-x.jpg"): the gray steel PC case, its lid with the white label,
    the power supply grille, the coloured PC ports on the back and the yellow warning label."""
    s = Sprite(26, 19)
    s.rrect(0, 0, 26, 7, "gray", 1)             # lid
    s.rect(4, 2, 7, 3, "white")                 # label
    s.rect(0, 6, 26, 13, "dgray")               # back
    s.rect(1, 7, 24, 11, "gray")
    for y in (8, 10, 12, 14, 16):               # power supply grille
        s.rect(2, y, 5, 1, "dgray")
    s.rect(9, 8, 2, 2, "green")                 # PS/2
    s.rect(9, 11, 2, 2, "purple")
    s.rect(13, 8, 6, 2, "purple")               # parallel
    s.rect(13, 11, 3, 2, "blue")                # VGA
    s.rect(17, 11, 2, 2, "dark")                # USB
    s.rect(9, 15, 10, 1, "dark")                # card slots
    s.rect(21, 8, 3, 3, "yellow")               # warning label
    s.rect(21, 13, 3, 4, "dark")                # expansion card
    return s


def typex_stick():
    """Type X panel: Taito's Vewlix panel, a red ball-top stick and six buttons, as Raiden III and the fighters
    on Type X use."""
    return _panel([3, 3], "red", "dark", ("white", "white", "white", "white", "white", "white"))


# ---------------------------------------------------------------- Daphne

def daphne_cab():
    """Daphne, the laserdisc arcade emulator, as the Dragon's Lair cabinet (KLOV, Dragon's Lair "Cabinet",
    "Marquee", "Control Panel"): the black cabinet, the orange marquee with its gold title, Dirk's sword on the
    screen, the panel
    blue on the left and pink on the right with the red-ball stick in the middle and a red sword button each side,
    and the drawer below that holds the laserdisc player."""
    s = Sprite(20, 23)
    s.rrect(0, 0, 20, 5, "orange", 1)           # marquee
    s.rect(3, 2, 14, 1, "yellow")               # title
    s.rect(0, 5, 20, 9, "dark")                 # hood
    s.rect(2, 6, 16, 7, "black")                # screen
    s.rect(9, 7, 2, 3, "gray")                  # Dirk's sword
    s.rect(7, 10, 6, 1, "tan")
    s.rect(9, 11, 2, 1, "brown")
    s.rect(0, 14, 10, 4, "blue")                # panel
    s.rect(10, 14, 10, 4, "pink")
    s.rect(9, 15, 2, 2, "red")                  # stick
    s.px(5, 16, "red")                          # sword buttons
    s.px(14, 16, "red")
    s.rect(2, 18, 16, 5, "dark")                # lower cabinet
    s.rect(4, 19, 12, 3, "black")               # laserdisc drawer
    s.rect(6, 20, 8, 1, "gray")
    return s


def daphne_stick():
    """Dragon's Lair panel (KLOV, "Control Panel"): blue on the left, pink on the right, the red-ball stick in the
    middle, a red sword button on each side and the two white start buttons."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "blue", 2)
    for y in range(17):                         # pink right half
        for x in range(13, 26):
            if s.g[y][x]:
                s.g[y][x] = "pink"
    s.ellipse(12.5, 7.5, 4.8, 4.8, "black")     # stick base, centred on the split
    s.rrect(10, 5, 6, 6, "red", 1)              # its ball
    s.px(11, 6, "white")
    s.rect(3, 6, 3, 3, "red")                   # sword buttons
    s.rect(20, 6, 3, 3, "red")
    s.rect(3, 2, 2, 2, "white")                 # start buttons
    s.rect(3, 11, 2, 2, "white")
    return s


# ---------------------------------------------------------------- LowRes NX

NX = [
    "XX...XX.XX...XX",
    "XXX..XX..XX.XX.",
    "XXXX.XX...XXX..",
    "XX.XXXX...XXX..",
    "XX..XXX..XX.XX.",
    "XX...XX.XX...XX",
]


def lowresnx():
    """LowRes NX (its site, lowresnx.inutilis.com, "lowres_nx_logo_dark"): the logo's orange block with the
    blocky dark NX, over the dark bar with the white letters of LOWRES."""
    s = Sprite(21, 18)
    s.rrect(0, 0, 21, 13, "orange", 2)
    s.art(3, 3, NX, {"X": "dark"})
    s.rrect(2, 12, 17, 6, "dark", 1)            # LOWRES bar
    s.rect(2, 12, 17, 1, "dark")
    for x in range(5, 16, 2):                   # its six letters
        s.rect(x, 14, 1, 2, "white")
    return s


# ---------------------------------------------------------------- Lutro

def lutro():
    """Lutro (its site, lutro.libretro.com, "assets/logo.png"): the disc split on the diagonal, purple above and
    green below, round a white heart."""
    s = Sprite(22, 22)
    s.ellipse(10.5, 10.5, 10.5, 10.5, "purple")
    for y in range(22):
        for x in range(22):
            if s.g[y][x] and x + y >= 23:       # green below the 1:1 diagonal
                s.g[y][x] = "green"
    s.art(4, 5, HEART, {"X": "white"})
    return s


CONSOLES = {"3do": threedo_console, "cdimono1": cdi_console, "pcfx": pcfx_console,
            "atarijaguarcd": jaguarcd_console, "arcadia": arcadia_console, "gamecom": gamecom,
            "uzebox": uzebox_console, "model2": model2_board, "model3": model3_cab, "stv": stv_board,
            "triforce": triforce_box, "type-x": typex_box, "daphne": daphne_cab, "lowresnx": lowresnx, "lutro": lutro}
# Jaguar CD: an add-on that sits on a Jaguar and uses its pad, so the existing Jaguar pad is the honest one
# Game.com: the handheld is its own controller, so both kinds draw it (as the PSP does)
# Uzebox: takes SNES pads in its two ports, so the existing Super Famicom pad is the honest one
CONTROLLERS = {"3do": threedo_pad, "cdimono1": cdi_pad, "pcfx": pcfx_pad, "atarijaguarcd": jaguar_pad,
               "arcadia": arcadia_pad, "gamecom": gamecom, "uzebox": sfc_pad, "model2": model2_stick,
               "model3": model3_stick, "stv": stv_stick, "triforce": triforce_stick, "type-x": typex_stick,
               "daphne": daphne_stick, "lowresnx": lowresnx, "lutro": lutro}
