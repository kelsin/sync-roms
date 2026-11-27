"""Pixel sprites for more ES-DE systems missing from the Spruce set: CONSOLES and CONTROLLERS keyed by ES-DE name.

Not in build.BATCHES, so the Spruce themes don't change; esde/systems.py maps them through EXTRA.
"""
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


CONSOLES = {"3do": threedo_console, "cdimono1": cdi_console, "pcfx": pcfx_console,
            "atarijaguarcd": jaguarcd_console, "arcadia": arcadia_console, "gamecom": gamecom,
            "uzebox": uzebox_console}
# Jaguar CD: an add-on that sits on a Jaguar and uses its pad, so the existing Jaguar pad is the honest one
# Game.com: the handheld is its own controller, so both kinds draw it (as the PSP does)
# Uzebox: takes SNES pads in its two ports, so the existing Super Famicom pad is the honest one
CONTROLLERS = {"3do": threedo_pad, "cdimono1": cdi_pad, "pcfx": pcfx_pad, "atarijaguarcd": jaguar_pad,
               "arcadia": arcadia_pad, "gamecom": gamecom, "uzebox": sfc_pad}
