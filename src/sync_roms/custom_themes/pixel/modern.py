"""Pixel sprites for the ES-DE systems newer than the Spruce set: CONSOLES and CONTROLLERS keyed by ES-DE name.

Not in build.BATCHES, so the Spruce themes don't change; esde/systems.py maps them through EXTRA.
"""
from .handhelds import face, plus
from .nintendo_sega import body_from_half, n64_pad, on
from .others import plus as dpad
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
    s.ellipse(19, 9, 2.6, 2.6, "green")         # A
    s.rect(14, 8, 2, 2, "red")                  # B
    s.rect(23, 7, 1, 4, "gray")                 # X
    s.rect(18, 5, 4, 1, "gray")                 # Y
    s.ellipse(20.5, 14.5, 1.6, 1.6, "yellow")   # C-stick
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
    s = Sprite(26, 13)
    s.rrect(0, 0, 26, 13, "dgray", 3)
    s.rect(5, 1, 16, 11, "black")               # wide screen
    s.rect(6, 2, 14, 9, "screen")
    face(s, 13, 4, 3)
    s.ellipse(2.5, 3.5, 1.9, 1.9, "gray")       # sticks
    s.ellipse(22.5, 3.5, 1.9, 1.9, "gray")
    plus(s, 1, 7, 3, 1, "dark")                 # d-pad
    s.px(23, 7, "dark")                         # X Y A B
    s.px(22, 8, "dark")
    s.px(24, 8, "dark")
    s.px(23, 9, "dark")
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


# ---------------------------------------------------------------- PlayStation 2

def ps2_console():
    """PlayStation 2 (Wikimedia, Evan-Amos, "Sony-PlayStation-2-30001-wController-L"): the black console lying flat,
    the ribbed top, the disc tray along the front with the blue eject and green reset lights beside it, and the pad
    and card ports below."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    for y in (2, 4, 6):                         # ribbed top
        s.rect(2, y, 22, 1, "dgray")
    s.rect(1, 8, 24, 1, "black")                # front edge
    s.rect(3, 10, 13, 1, "black")               # disc tray
    s.rect(18, 10, 2, 1, "green")               # reset
    s.rect(22, 10, 2, 1, "blue")                # eject
    s.rect(3, 12, 3, 1, "dgray")                # pad and memory card ports
    s.rect(8, 12, 3, 1, "dgray")
    return s


def ds_pad(body="dark", detail="dgray"):
    """DualShock 2 / 3 (Wikimedia, Evan-Amos, "Sony-PlayStation-2-30001-wController-L", "PS3-Fat-Console-Set"): the
    DualShock's shape (see others.ps_pad) in black, with the d-pad, select and start in the body's lighter gray."""
    s = Sprite(26, 20)
    s.rrect(0, 0, 9, 20, body, 3)
    s.rect(7, 2, 6, 12, body)
    s.rrect(8, 9, 4, 4, detail, 1)              # sticks
    s.rect(10, 7, 2, 1, detail)                 # select / start
    s.mirror()
    dpad(s, 1, 3, detail)
    s.rect(20, 3, 2, 2, "green")
    s.rect(20, 9, 2, 2, "blue")
    s.rect(17, 6, 2, 2, "pink")
    s.rect(23, 6, 2, 2, "red")
    return s


def ps2_pad():
    """DualShock 2: the black DualShock."""
    return ds_pad()


# ---------------------------------------------------------------- PlayStation 3

def ps3_console():
    """PlayStation 3, the launch model (Wikimedia, Evan-Amos, "PS3-Fat-Console-Set"): the glossy black body with its
    curved top, the silver front strip, the disc slot and the power and eject touch buttons."""
    tops = [5, 4, 3, 2, 2, 1, 1, 1, 1, 0, 0, 0, 0]
    s = body_from_half(tops, [13] * 13, "dark")
    for x in range(2, 13):                      # gloss along the curve
        s.px(x, tops[x] + 2, "dgray")
    s.mirror()
    on(s, 0, 9, 26, 5, "gray")                  # silver front
    s.rect(3, 11, 15, 1, "black")               # disc slot
    s.rect(20, 11, 1, 1, "dark")                # power / eject
    s.rect(22, 11, 1, 1, "dark")
    return s


def ps3_pad():
    """DualShock 3 (Wikimedia, Evan-Amos, "PS3-Fat-Console-Set"): the black DualShock with the round PS button in
    the middle and the four red player lights along the top."""
    s = ds_pad()
    s.rect(10, 7, 2, 1, "dark")                 # select / start move up for the PS button
    s.rect(14, 7, 2, 1, "dark")
    s.rect(9, 5, 2, 1, "dgray")
    s.rect(15, 5, 2, 1, "dgray")
    s.rrect(11, 6, 4, 3, "gray", 1)             # PS button
    for x in (9, 11, 14, 16):                   # player lights
        s.px(x, 3, "red")
    return s


# ---------------------------------------------------------------- PlayStation 4

def ps4_console():
    """PlayStation 4 (Wikimedia, Evan-Amos, "PS4-Console-wDS4"): the slanted black slab seen from the front, the
    glossy upper half and matte lower half split by the groove with the blue light bar."""
    s = Sprite(26, 12)
    for y in range(12):
        x0 = (11 - y) // 2
        s.rect(x0, y, 20, 1, "dgray" if y < 5 else "dark")
    for y in (5, 6):                            # the groove
        x0 = (11 - y) // 2
        s.rect(x0, y, 20, 1, "black")
    s.rect(4, 6, 6, 1, "blue")                  # light bar
    return s


def ps4_pad():
    """DualShock 4 (Wikimedia, Evan-Amos, "PS4-Console-wDS4"): black, the touchpad in the middle with the blue light
    bar along its top edge, the sticks side by side below it, the PS button between them and the long grips."""
    tops = [3, 2, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2]
    bottoms = [15, 17, 18, 18, 17, 16, 16, 15, 15, 15, 15, 15, 15]
    s = body_from_half(tops, bottoms, "dark")
    s.rect(10, 1, 3, 1, "blue")                 # light bar
    s.rect(10, 2, 3, 5, "dgray")                # touchpad
    s.rect(7, 3, 1, 2, "dgray")                 # share / options
    s.ellipse(9, 12, 2.6, 2.6, "dgray")         # sticks
    s.mirror()
    dpad(s, 1, 4, "dgray")
    s.rect(12, 8, 2, 2, "gray")                 # PS button
    s.rect(20, 4, 2, 2, "green")
    s.rect(20, 10, 2, 2, "blue")
    s.rect(17, 7, 2, 2, "pink")
    s.rect(23, 7, 2, 2, "red")
    return s


# ---------------------------------------------------------------- PS Vita

def psvita():
    """PS Vita 1000 (Wikimedia, Evan-Amos, "PlayStation-Vita-1101-FL"): the black oval handheld with the wide OLED
    screen, the d-pad above the left stick, the four face buttons above the right stick, the PS button below the
    left stick and start below the right one. It is also its own controller, like the PSP."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 4)
    s.rrect(2, 7, 3, 3, "dgray", 1)             # sticks (nubs, as on the PSP)
    s.px(3, 11, "dgray")                        # PS button / start
    s.mirror()
    s.rect(6, 2, 14, 8, "sky")                  # 16:9, under the one black glass front
    face(s, 13, 3, 3)
    plus(s, 2, 3, 3, 1, "gray")
    s.px(22, 3, "green")                        # triangle
    s.px(21, 4, "pink")                         # square
    s.px(23, 4, "red")                          # circle
    s.px(22, 5, "blue")                         # cross
    return s


# ---------------------------------------------------------------- Xbox

def xbox_console():
    """Xbox (Wikimedia, Evan-Amos, "Xbox-console"): the big black box with the green jewel and its X on top, the
    disc tray across the front, and the four pad ports under it."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 2)
    s.ellipse(12.5, 5, 5, 4, "forest")          # jewel
    s.ellipse(12.5, 5, 4, 3, "green")
    s.line(10, 3, 12, 5, "forest")              # its X
    s.line(10, 7, 12, 5, "forest")
    on(s, 0, 10, 13, 6, "black")                # front
    s.rect(3, 11, 10, 1, "dgray")               # disc tray
    for x in (2, 7):                            # pad ports
        s.rect(x, 13, 3, 1, "dgray")
    s.mirror()
    s.rect(18, 11, 2, 1, "green")               # power / eject
    s.rect(21, 11, 2, 1, "gray")
    return s


PAD_TOPS = [4, 3, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3]
PAD_BOTTOMS = [15, 17, 18, 18, 18, 17, 16, 15, 15, 15, 15, 14, 14]


def xbox_pad():
    """Xbox Controller S (Wikimedia, Evan-Amos, "Xbox-s-controller"): black, the left stick high and the d-pad low,
    the right stick low, the green jewel between them, the green A, red B, blue X and yellow Y, with the white button
    below them."""
    s = body_from_half(PAD_TOPS, PAD_BOTTOMS, "dgray")
    s.ellipse(4, 6, 2.6, 2.6, "black")              # left stick
    plus(s, 7, 9, 5, 1, "black")               # d-pad
    s.ellipse(16, 11, 2.6, 2.6, "black")            # right stick
    s.rect(20, 4, 2, 2, "yellow")               # Y
    s.rect(17, 6, 2, 2, "blue")                 # X
    s.rect(23, 6, 2, 2, "red")                  # B
    s.rect(20, 8, 2, 2, "green")                # A
    s.px(22, 11, "white")                       # white button
    s.rrect(11, 4, 4, 4, "forest", 1)           # jewel
    s.rect(12, 5, 2, 2, "green")
    return s


# ---------------------------------------------------------------- Xbox 360

def xbox360_console():
    """Xbox 360 (Wikimedia, Evan-Amos, "Xbox-360-Pro-wController"): the white console lying flat, the silver disc
    tray, the ring of light around the power button with its green quarters, and the vents at both ends."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "gray", 2)
    s.rect(1, 1, 24, 12, "white")
    for y in (3, 5, 7, 9):                      # vents
        s.rect(1, y, 2, 1, "gray")
    s.mirror()
    s.rect(4, 3, 13, 2, "gray")                 # disc tray
    s.rect(5, 4, 11, 1, "dgray")
    s.ellipse(19.5, 8.5, 2.6, 2.6, "green")     # ring of light
    s.ellipse(19.5, 8.5, 1.5, 1.5, "gray")
    s.rect(19, 3, 2, 1, "gray")                 # eject
    return s


def inset(s, body, inner):
    """Recolor the body's cells that aren't on its edge, leaving a one-pixel rim."""
    filled = [[c is not None for c in row] for row in s.g]
    for y in range(1, s.h - 1):
        for x in range(1, s.w - 1):
            if s.g[y][x] == body and filled[y - 1][x] and filled[y + 1][x] and filled[y][x - 1] and filled[y][x + 1]:
                s.g[y][x] = inner


def xbox360_pad():
    """Xbox 360 controller (Wikimedia, Evan-Amos, "Xbox-360-Pro-wController"): white, the silver Guide button with
    its green X in the middle, the left stick high and the d-pad low, the right stick low and A B X Y high."""
    s = body_from_half(PAD_TOPS, PAD_BOTTOMS, "gray")
    inset(s, "gray", "white")
    s.ellipse(4, 6, 2.6, 2.6, "dgray")              # left stick
    plus(s, 7, 9, 5, 1, "dgray")               # d-pad
    s.ellipse(16, 11, 2.6, 2.6, "dgray")            # right stick
    s.rrect(11, 4, 4, 4, "gray", 1)             # Guide
    s.rect(12, 5, 2, 2, "green")
    s.rect(20, 4, 2, 2, "yellow")
    s.rect(17, 6, 2, 2, "blue")
    s.rect(23, 6, 2, 2, "red")
    s.rect(20, 8, 2, 2, "green")
    return s


# ---------------------------------------------------------------- Xbox One

def xboxone_console():
    """Xbox One (Wikimedia, Evan-Amos, "Microsoft-Xbox-One-Console-Set-wKinect"): the wide black box, the glossy top
    left and the vented matte top right, the disc slot on the front and the glowing white Xbox button."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 1)
    on(s, 0, 0, 9, 7, "dgray")                  # glossy part
    for y in (1, 3, 5):                         # vents
        s.rect(10, y, 15, 1, "black")
    on(s, 0, 7, 26, 7, "black")                 # front
    s.rect(2, 9, 12, 1, "dgray")                # disc slot
    s.ellipse(21, 10, 2.6, 2.6, "white")        # Xbox button
    return s


def xboxone_pad():
    """Xbox One controller (Wikimedia, Evan-Amos, "Microsoft-Xbox-One-Console-Set-wKinect"): black, the glowing white
    Xbox button at the top, the view and menu buttons, the left stick high and the d-pad low, the right stick low and
    A B X Y high."""
    s = body_from_half(PAD_TOPS, PAD_BOTTOMS, "dark")
    s.ellipse(4, 6, 2.6, 2.6, "dgray")
    plus(s, 7, 9, 5, 1, "dgray")
    s.ellipse(16, 11, 2.6, 2.6, "dgray")
    s.rect(12, 4, 2, 2, "white")                # Xbox button
    s.px(10, 7, "dgray")                        # view / menu
    s.px(15, 7, "dgray")
    s.rect(20, 4, 2, 2, "yellow")
    s.rect(17, 6, 2, 2, "blue")
    s.rect(23, 6, 2, 2, "red")
    s.rect(20, 8, 2, 2, "green")
    return s


CONSOLES = {"gc": gc_console, "wii": wii_console, "wiiu": wiiu_console, "switch": switch_console,
            "n64dd": n64dd_console, "ps2": ps2_console, "ps3": ps3_console, "ps4": ps4_console, "psvita": psvita,
            "xbox": xbox_console, "xbox360": xbox360_console, "xboxone": xboxone_console}
# 64DD: it used the standard Nintendo 64 pad, so the existing drawing is the honest one
# PS Vita: the handheld is its own controller, so both kinds draw it (as the PSP does)
CONTROLLERS = {"gc": gc_pad, "wii": wii_pad, "wiiu": wiiu_pad, "switch": switch_pad, "n64dd": n64_pad,
               "ps2": ps2_pad, "ps3": ps3_pad, "ps4": ps4_pad, "psvita": psvita, "xbox": xbox_pad,
               "xbox360": xbox360_pad, "xboxone": xboxone_pad}
