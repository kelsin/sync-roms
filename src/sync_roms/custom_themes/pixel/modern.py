"""Pixel sprites for the ES-DE systems newer than the Spruce set: CONSOLES and CONTROLLERS keyed by ES-DE name.

Not in build.BATCHES, so the Spruce themes don't change; esde/systems.py maps them through EXTRA.
"""
from .handhelds import face, plus
from .nintendo_sega import body_from_half, n64_pad, on
from .sprite import Sprite


def clear(s, x, y, w, h):
    """Empty a rectangle (a hole through the body, like a handle's)."""
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            s.px(xx, yy, None)


# ---------------------------------------------------------------- GameCube

def gc_console():
    """GameCube (Wikimedia, Evan-Amos, "GameCube-Set"): the indigo cube with its carry handle at the back, the round
    disc lid with the cube emblem in the middle, and the four pad ports along the front."""
    s = Sprite(24, 22)
    s.rrect(4, 0, 8, 5, "indigo", 1)            # handle (left half)
    clear(s, 6, 2, 6, 2)
    s.rrect(0, 4, 24, 18, "indigo", 3)
    s.ellipse(11.5, 11.5, 7, 6, "navy")         # disc lid groove
    s.ellipse(11.5, 11.5, 6, 5, "indigo")
    s.rect(3, 19, 3, 1, "black")                # pad ports
    s.rect(8, 19, 3, 1, "black")
    s.mirror()
    s.rect(10, 10, 4, 3, "gray")                # cube emblem
    return s


def gc_pad():
    """GameCube pad (Wikimedia, Evan-Amos, "GameCube-Set"): indigo body with drooping grips, gray stick top left and
    small d-pad below it, gray Start, the big green A with red B, gray kidney X and Y, and the yellow C-stick."""
    tops = [4, 3, 2, 2, 2, 2, 3, 3, 4, 4, 4, 4, 4]
    bottoms = [15, 17, 18, 18, 18, 17, 16, 15, 14, 12, 10, 10, 10]
    s = body_from_half(tops, bottoms, "indigo")
    s.ellipse(4.5, 6.5, 2.6, 2.6, "gray")       # stick
    s.ellipse(4.5, 6.5, 1, 1, "dgray")
    plus(s, 3, 11, 5, 1, "gray")                # d-pad
    s.rect(12, 7, 2, 1, "gray")                 # start
    s.ellipse(19.5, 7.5, 2.2, 2.2, "green")     # A
    s.rect(16, 9, 2, 2, "red")                  # B
    s.rect(23, 6, 1, 4, "gray")                 # X
    s.rect(18, 4, 4, 1, "gray")                 # Y
    s.ellipse(20.5, 13.5, 1.6, 1.6, "yellow")   # C-stick
    return s


# ---------------------------------------------------------------- Wii

def wii_console():
    """Wii (Wikimedia, Evan-Amos, "Wii-console"): the slim white console standing upright on its stand, the vertical
    disc slot with its blue light, and the SD card door low on the front."""
    s = Sprite(14, 23)
    s.rrect(0, 19, 14, 4, "dgray", 1)           # stand
    s.rrect(2, 0, 10, 20, "gray", 1)
    s.rect(3, 1, 8, 18, "white")                # front
    s.rect(6, 2, 2, 12, "black")                # disc slot
    s.rect(8, 2, 1, 12, "cyan")                 # its light
    s.rect(4, 2, 1, 2, "gray")                  # power / reset
    s.rect(4, 15, 6, 3, "gray")                 # SD card door
    return s


def wii_pad():
    """Wii Remote with the Nunchuk (Wikimedia, Evan-Amos, "Wii-console"): the white remote with its d-pad, A,
    minus / Home / plus, 1 and 2 and the blue player lights, the Nunchuk's stick beside it."""
    s = Sprite(16, 23)
    s.ellipse(3.5, 13.5, 3.5, 7, "gray")        # Nunchuk
    s.ellipse(3.5, 13.5, 2.5, 6, "white")
    s.ellipse(3.5, 10, 1.6, 1.6, "dgray")       # its stick
    s.rrect(9, 0, 7, 23, "gray", 2)             # remote
    s.rect(10, 1, 5, 21, "white")
    plus(s, 10, 2, 5, 1, "dark")                # d-pad
    s.rrect(11, 8, 3, 3, "dgray", 0)            # A
    s.px(10, 13, "dgray")                       # minus, Home, plus
    s.px(12, 13, "blue")
    s.px(14, 13, "dgray")
    s.rect(11, 16, 3, 2, "dgray")               # 1
    s.rect(11, 19, 3, 2, "dgray")               # 2
    s.rect(11, 21, 3, 1, "blue")                # player lights
    return s


# ---------------------------------------------------------------- Wii U

def wiiu_console():
    """Wii U (Wikimedia, Takimata, "Wii U Console and Gamepad"): the black console lying flat, rounded at the
    sides, the disc slot along the front, the power button and the lower door over the SD slot and sync button."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "dgray", 3)
    s.rect(3, 3, 15, 1, "black")                # disc slot
    s.rect(20, 2, 3, 3, "gray")                 # power
    s.px(21, 3, "cyan")
    on(s, 0, 8, 26, 4, "dark")                  # lower door
    s.rect(18, 9, 2, 1, "gray")                 # sync
    return s


def wiiu_pad():
    """Wii U GamePad (Wikimedia, Takimata, "Wii U Console and Gamepad"): the black tablet with the screen in the
    middle, a stick at the top of each side, the d-pad below the left one and A B X Y below the right one."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dgray", 3)
    s.rect(6, 1, 14, 13, "black")               # screen
    s.rect(7, 2, 12, 11, "screen")
    face(s, 13, 4, 3)
    s.ellipse(2.5, 3.5, 1.5, 1.5, "gray")       # sticks
    s.ellipse(22.5, 3.5, 1.5, 1.5, "gray")
    plus(s, 1, 8, 3, 1, "dark")                 # d-pad
    s.px(23, 7, "gray")                         # X Y A B
    s.px(22, 8, "gray")
    s.px(24, 8, "gray")
    s.px(23, 9, "gray")
    return s


# ---------------------------------------------------------------- Switch

def switch_console():
    """Nintendo Switch (Wikimedia, Evan-Amos, "Nintendo-Switch-wJoyCons-BlRd-Standing-FL"): the tablet in handheld
    mode with the neon blue Joy-Con on the left and the neon red one on the right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 7, 14, "cyan", 3)             # left Joy-Con
    s.rrect(19, 0, 7, 14, "red", 3)             # right Joy-Con
    s.rect(5, 0, 16, 14, "dgray")
    s.rect(6, 1, 14, 12, "black")
    s.rect(7, 2, 12, 10, "screen")
    face(s, 13, 4, 3)
    s.rect(4, 1, 1, 1, "dark")                  # minus
    s.ellipse(2.5, 4, 1.5, 1.5, "dark")         # left stick
    s.px(2, 8, "dark")                          # arrow buttons
    s.px(1, 9, "dark")
    s.px(3, 9, "dark")
    s.px(2, 10, "dark")
    s.rect(21, 1, 1, 1, "dark")                 # plus
    s.px(23, 3, "dark")                         # X Y A B
    s.px(22, 4, "dark")
    s.px(24, 4, "dark")
    s.px(23, 5, "dark")
    s.ellipse(23.5, 9, 1.5, 1.5, "dark")        # right stick
    return s


def switch_pad():
    """Joy-Con pair (Wikimedia, Evan-Amos, "Nintendo-Switch-wJoyCons-BlRd-Standing-FL"): the neon blue left one with
    its stick above the four arrow buttons, the neon red right one with A B X Y above its stick."""
    s = Sprite(18, 22)
    s.rrect(0, 0, 8, 22, "cyan", 3)
    s.rect(5, 0, 3, 22, "cyan")                 # flat rail side
    s.rrect(10, 0, 8, 22, "red", 3)
    s.rect(10, 0, 3, 22, "red")
    s.rect(6, 2, 1, 1, "dark")                  # minus
    s.ellipse(3.5, 5.5, 2, 2, "dark")           # left stick
    s.rect(3, 10, 2, 2, "dark")                 # arrow buttons
    s.rect(1, 12, 2, 2, "dark")
    s.rect(5, 12, 2, 2, "dark")
    s.rect(3, 14, 2, 2, "dark")
    s.rect(11, 2, 1, 1, "dark")                 # plus
    s.rect(13, 4, 2, 2, "dark")                 # X Y A B
    s.rect(11, 6, 2, 2, "dark")
    s.rect(15, 6, 2, 2, "dark")
    s.rect(13, 8, 2, 2, "dark")
    s.ellipse(14.5, 13.5, 2, 2, "dark")         # right stick
    return s


# ---------------------------------------------------------------- 64DD

def n64dd_console():
    """64DD (Wikimedia, Evan-Amos, "64DD-Attached"): the charcoal drive under a Nintendo 64, the wide disk slot on
    its front and the eject button beside it."""
    s = Sprite(26, 23)
    s.rrect(8, 0, 10, 7, "gray", 1)             # cartridge
    s.rect(10, 2, 6, 3, "white")
    s.rrect(0, 5, 26, 9, "dgray", 3)            # Nintendo 64
    s.rect(7, 6, 12, 1, "black")                # cartridge slot
    for x in (1, 6, 16, 21):                    # pad ports
        s.rect(x, 9, 4, 3, "gray")
        s.rect(x + 1, 10, 2, 1, "black")
    s.rect(11, 9, 4, 3, "black")                # logo plate
    s.rrect(0, 13, 26, 10, "dgray", 2)          # 64DD
    s.rect(1, 13, 24, 1, "black")               # seam
    s.rrect(3, 16, 15, 4, "dark", 1)            # disk slot flap
    s.rect(5, 17, 11, 1, "black")
    s.rect(20, 17, 3, 2, "gray")                # eject
    return s


CONSOLES = {"gc": gc_console, "wii": wii_console, "wiiu": wiiu_console, "switch": switch_console,
            "n64dd": n64dd_console}
# 64DD: it used the standard Nintendo 64 pad, so the existing drawing is the honest one
CONTROLLERS = {"gc": gc_pad, "wii": wii_pad, "wiiu": wiiu_pad, "switch": switch_pad, "n64dd": n64_pad}
