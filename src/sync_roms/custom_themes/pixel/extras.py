"""Pixel icons for the base theme's extra systems (not in IDS): SHARED/CONSOLES/CONTROLLERS like the other batches."""
from .arcade import arcade_cab, arcade_stick, pico
from .handhelds import face, plus
from .others import cx40, joystick, keys
from .sprite import Sprite


# ---------------------------------------------------------------- handhelds and phones (same in both themes)

def _clam(body, bezel, screen_c, cam=None):
    """An open clamshell DS-style handheld, 22x23: two screens, hinge, d-pad, face buttons and start / select."""
    s = Sprite(22, 23)
    s.rrect(0, 0, 22, 11, body, 2)
    s.rect(2, 11, 18, 1, "gray")             # hinge
    s.rrect(0, 12, 22, 11, body, 2)
    for y, h in ((1, 9), (13, 9)):
        s.rect(4, y, 14, h, bezel)
        s.rect(5, y + 1, 12, h - 2, screen_c)
    s.rect(5, 2, 12, 7, "screen")
    face(s, 11, 3, 3)
    s.rect(1, 5, 1, 3, "gray")               # speakers
    s.rect(20, 5, 1, 3, "gray")
    plus(s, 1, 16, 3, 1, "gray")             # d-pad
    s.px(19, 15, "gray")                     # X Y A B diamond
    s.px(18, 16, "gray")
    s.px(20, 16, "gray")
    s.px(19, 17, "gray")
    s.rect(18, 19, 2, 1, "gray")             # start / select
    s.rect(18, 21, 2, 1, "gray")
    if cam:
        s.rect(10, 9, 2, 1, cam)
    return s


def dsi():
    """Nintendo DSi: a matte black DS with bigger screens and the camera lens between them."""
    return _clam("dark", "black", "sky", cam="cyan")


def n3ds():
    """Nintendo 3DS: aqua clamshell, wide top screen, circle pad and d-pad left of the bottom screen, buttons right."""
    s = Sprite(24, 23)
    s.rrect(0, 0, 24, 11, "cyan", 2)
    s.rect(2, 11, 20, 1, "gray")             # hinge
    s.rrect(0, 12, 24, 11, "cyan", 2)
    s.rect(3, 1, 18, 8, "black")             # top screen
    s.rect(4, 2, 16, 6, "screen")
    face(s, 12, 2, 3)
    s.rect(7, 13, 10, 9, "black")            # bottom screen
    s.rect(8, 14, 8, 7, "sky")
    s.ellipse(3.5, 15.5, 2, 2, "dgray")      # circle pad
    plus(s, 2, 19, 3, 1, "dgray")            # d-pad
    s.px(20, 14, "dgray")                    # X Y A B diamond
    s.px(19, 15, "dgray")
    s.px(21, 15, "dgray")
    s.px(20, 16, "dgray")
    s.rect(19, 19, 2, 1, "dgray")            # start / select
    s.rect(19, 21, 2, 1, "dgray")
    return s


def gamate():
    """Bit Corp Gamate: a landscape dark gray handheld, speaker grille top left, wide screen, d-pad left, two round
    buttons at the right (the real unit's start / select are two small keys above them)."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dgray", 3)
    s.rect(8, 1, 10, 9, "black")
    s.rect(9, 2, 8, 7, "screen")
    face(s, 13, 3, 3)
    keys(s, 2, 2, 2, 3, "dark", 1, 1, 1, 1)      # speaker grille
    plus(s, 1, 7, 6, 2, "dark")                  # d-pad
    s.rect(20, 2, 2, 1, "orange")                # select / start
    s.rect(23, 2, 2, 1, "orange")
    s.rrect(21, 5, 4, 4, "dark", 1)              # A
    s.rrect(19, 9, 4, 4, "dark", 1)              # B
    return s


def gw():
    """Game & Watch Ball: silver face with a red rim, the LCD in the middle, a round red LEFT / RIGHT button on each
    side of it and the three small game A / game B / time keys below."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "red", 2)
    s.rrect(1, 1, 24, 14, "gray", 1)
    s.rect(6, 2, 14, 9, "red")                   # LCD frame
    s.rect(7, 3, 12, 7, "screen")
    s.rect(12, 4, 2, 2, "dark")                  # juggler: head, body and arms
    s.rect(12, 6, 2, 3, "dark")
    s.line(9, 4, 11, 6, "dark")
    s.line(16, 6, 14, 4, "dark")
    s.rrect(2, 5, 4, 4, "red", 1)                # left
    s.rrect(20, 5, 4, 4, "red", 1)               # right
    for x in (9, 12, 15):                        # game A / game B / time
        s.rect(x, 12, 2, 2, "red")
    return s


def j2me():
    """Feature phone: dark candy bar, green screen, soft keys and a d-pad, a 3x4 keypad."""
    s = Sprite(14, 23)
    s.rrect(0, 0, 14, 23, "dgray", 3)
    s.rect(2, 2, 10, 7, "black")
    s.rect(3, 3, 8, 5, "screen")
    face(s, 7, 3, 2)
    s.rect(2, 10, 2, 1, "gray")              # soft keys
    s.rect(10, 10, 2, 1, "gray")
    plus(s, 5, 10, 4, 2, "gray")             # d-pad
    keys(s, 3, 15, 3, 4, "gray", 2, 1, 1, 1)
    return s


def loopy():
    """Casio Loopy: the lavender-gray console, cartridge slot along the back, round eject button and a yellow reset
    at the left, the round-windowed seal lid at the right and the black seal-out opening at the front."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "gray", 4)
    s.rect(4, 2, 14, 1, "dgray")             # cartridge slot
    s.ellipse(6.5, 7.5, 3, 3, "indigo")      # eject
    s.rect(12, 8, 2, 2, "yellow")            # reset
    s.rrect(16, 4, 8, 7, "periwinkle", 1)    # seal lid
    s.ellipse(19.5, 6.5, 2, 1.5, "dgray")    # its window
    s.rrect(13, 12, 11, 3, "black", 1)       # seal out
    return s


def loopy_pad():
    """Casio Loopy pad: lavender-gray, a round d-pad on the left, a yellow start and four indigo buttons in an arc."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "gray", 4)
    plus(s, 2, 4, 7, 3, "indigo")
    s.rect(11, 4, 2, 1, "yellow")            # start
    s.rect(21, 2, 3, 3, "indigo")         # D
    s.rect(17, 6, 3, 3, "indigo")         # C
    s.rect(13, 9, 3, 3, "indigo")         # B
    s.rect(9, 11, 3, 3, "indigo")         # A
    return s


def mkxp():
    """mkxp-z plays RPG Maker XP / VX / VX Ace games: the engine's classic front-facing hero, auburn hair, blue
    tunic, brown belt and boots."""
    s = Sprite(18, 21)
    s.art(0, 0, [
        "..OOOOOOO",
        ".OOOOOOOO",
        "OOOOOOOOO",
        "OOOOOOOOO",
        "OOsssssss",
        "OOsssssss",
        "OOsssssss",
        "..sssssss",
        "...ssssss",
        "......sss",
        ".IIBBBBBB",
        "IIIBBBBBB",
        "IIIBBBBBB",
        "IIIBBBBBB",
        "sssbbbbbb",
        "...BBBBBB",
        "...nnnnn.",
        "...nnnnn.",
        "...nnnnn.",
        "..bbbbbb.",
        "..bbbbbb.",
    ], {"O": "orange", "s": "tan", "I": "indigo", "B": "blue", "b": "brown", "n": "navy"})
    s.rect(4, 5, 1, 2, "dark")                     # eye
    s.rect(8, 8, 1, 1, "red")                      # mouth
    s.mirror()
    return s


def wolf():
    """Wolfenstein 3D: B.J. Blazkowicz's face as the status bar shows it, auburn swept-back hair, blue eyes and a strong
    jaw on the bar's blue panel."""
    s = Sprite(18, 22)
    s.rrect(0, 0, 18, 22, "blue", 2)
    s.rect(2, 2, 7, 4, "orange")                   # hair
    s.rect(2, 6, 1, 4, "orange")                   # sideburn
    s.rect(3, 6, 6, 9, "tan")                      # face
    s.rect(4, 15, 5, 1, "tan")                     # jaw
    s.rect(5, 16, 4, 1, "tan")
    s.rect(6, 17, 3, 4, "tan")                     # neck
    s.rect(3, 7, 4, 1, "brown")                    # brow
    s.rect(4, 8, 2, 1, "sky")                      # eye
    s.rect(8, 10, 1, 3, "orange")                  # nose
    s.rect(6, 14, 3, 1, "maroon")                  # mouth
    s.mirror()
    return s


def ffplay():
    """FFplay video player: a screen with a big play triangle and a progress bar."""
    s = Sprite(24, 18)
    s.rrect(0, 0, 24, 18, "dgray", 2)
    s.rect(2, 2, 20, 11, "black")
    for n, w in enumerate((2, 4, 6, 8, 10, 10, 8, 6, 4, 2)):
        s.rect(7, 2 + n, w, 1, "red")
    s.rect(2, 15, 20, 1, "gray")
    s.rect(2, 15, 9, 1, "red")
    s.rect(11, 14, 2, 3, "white")
    return s


# ---------------------------------------------------------------- consoles and computers

def _disc(base):
    """A console or pad with a disc standing behind it: the disc rises 9 rows above (for the MSU enhancements)."""
    b = base()
    s = Sprite(b.w, b.h + 9)
    cx = b.w / 2 - 0.5
    s.ellipse(cx, 4.5, 5, 4.5, "cyan")
    s.ellipse(cx, 4.5, 2.5, 2.5, "white")
    s.ellipse(cx, 4.5, 1, 1, "dark")
    for y in range(b.h):
        for x in range(b.w):
            if b.g[y][x]:
                s.g[y + 9][x] = b.g[y][x]
    return s


def msu1_console():
    from .variants import snes_console
    return _disc(snes_console)


def msu1_pad():
    from .variants import snes_pad
    return _disc(snes_pad)


def msumd_console():
    from .variants import genesis_console
    return _disc(genesis_console)


def msumd_pad():
    from .variants import genesis_pad
    return _disc(genesis_pad)


def amiga_console():
    """Amiga 500: a wide cream keyboard computer, function row, main keys, numeric pad and the space bar."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "cream", 2)
    keys(s, 3, 2, 7, 1, "dgray", 2, 1, 1, 1)
    keys(s, 3, 4, 6, 3, "gray", 2, 1, 1, 1)
    keys(s, 20, 4, 2, 3, "gray", 2, 1, 1, 1)
    s.rect(6, 11, 8, 1, "gray")
    s.rect(21, 11, 2, 1, "red")              # drive light
    return s


def amiga_mouse():
    """Amiga mouse: the beige two-button mouse that shipped with the machine, its cord at the top."""
    s = Sprite(14, 21)
    s.rect(6, 0, 2, 3, "gray")
    s.rrect(0, 2, 14, 19, "cream", 3)
    s.rect(2, 4, 4, 6, "gray")
    s.rect(8, 4, 4, 6, "gray")
    return s


def coco_console():
    """TRS-80 Color Computer 2: a light gray wedge case with ribbed vents across the top and a black keyboard panel of
    white keys with the red BREAK key at the top right."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "cream", 3)
    for y in (2, 4):
        s.rect(4, y, 18, 1, "gray")
    s.rect(2, 7, 22, 9, "black")
    keys(s, 4, 8, 6, 3, "white", 2, 1, 1, 1)
    s.rect(8, 14, 10, 1, "white")            # space bar
    s.rect(22, 8, 2, 1, "red")               # BREAK
    return s


def coco_stick():
    """Color Computer joystick ("Black Beauty"): black base and ball, the one red fire button on the front."""
    return joystick("dark", "dgray", "black", [(3, "red")])


def cpc_console():
    """Amstrad CPC 464: a long black keyboard with the green and blue colored keys, a numeric block and the built-in
    cassette deck at the right with its red REC key."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "dark", 2)
    keys(s, 2, 2, 4, 3, "dgray", 2, 1, 1, 1)
    s.rect(2, 2, 2, 1, "green")              # colored keys
    s.rect(2, 4, 2, 1, "green")
    s.rect(6, 8, 6, 1, "dgray")              # space bar
    keys(s, 14, 2, 2, 3, "dgray", 2, 1, 1, 1)
    s.rect(14, 6, 2, 2, "blue")              # ENTER
    s.rect(20, 2, 5, 4, "black")             # cassette deck
    s.rect(21, 3, 3, 2, "gray")
    s.rect(20, 8, 2, 1, "red")               # REC
    s.rect(23, 8, 2, 1, "dgray")
    return s


def cpc_stick():
    """Amstrad joystick: red case, black stick with its fire button on top and a black fire button on the base."""
    return joystick("red", "black", "black", [(3, "dark")])


def dos_console():
    """IBM PC 5150: a beige monochrome monitor over the desktop case, vent slits on the left and the two 5.25" floppy
    drives on the right."""
    s = Sprite(26, 22)
    s.rrect(3, 0, 20, 13, "cream", 2)
    s.rect(5, 2, 16, 8, "black")
    s.rect(6, 3, 3, 1, "screen")             # C:\> prompt
    s.rect(6, 5, 1, 1, "screen")
    s.rect(7, 5, 2, 1, "dgray")
    s.rrect(0, 14, 26, 8, "cream", 2)
    for x in (3, 5, 7):                      # vents
        s.rect(x, 16, 1, 4, "gray")
    for x in (11, 19):                       # drives
        s.rect(x, 16, 6, 4, "dark")
        s.rect(x + 1, 17, 4, 1, "black")
    return s


def dos_keyboard():
    """PC keyboard: cream slab, the main block, a numeric pad and the space bar."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "cream", 2)
    keys(s, 2, 3, 6, 3, "gray", 2, 1, 1, 1)
    keys(s, 20, 3, 2, 3, "dgray", 2, 1, 1, 1)
    s.rect(5, 10, 10, 2, "gray")
    return s


def gametank_console():
    """GameTank: a blue box with ribbed vents down both sides, a cartridge standing in the top slot and a red and an
    orange button on the front."""
    s = Sprite(26, 18)
    s.rect(0, 4, 26, 14, "blue")
    for y in range(5, 17, 2):                # ribbed side vents
        s.rect(1, y, 3, 1, "indigo")
        s.rect(22, y, 3, 1, "indigo")
    s.rect(8, 4, 10, 2, "dark")              # slot
    s.rect(9, 0, 8, 5, "gray")               # cartridge
    s.rect(10, 1, 6, 2, "red")               # label
    s.rect(8, 12, 4, 3, "red")
    s.rect(14, 12, 4, 3, "orange")
    return s


def gametank_pad():
    """GameTank controller: a small blue oblong pad with a d-pad on the left, a small start and the A, B and C buttons
    at the right."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "blue", 4)
    plus(s, 3, 3, 6, 2, "dark")
    s.rect(12, 3, 2, 1, "dark")              # start
    s.rect(17, 3, 3, 3, "dark")             # C
    s.rect(21, 5, 3, 3, "dark")             # B
    s.rect(17, 7, 3, 3, "dark")             # A
    return s


def vdp_console():
    """Sega SC-3000: a black keyboard computer with gray keys, the orange RESET key at the right end and the cartridge
    slot beside it."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 3)
    s.rect(4, 2, 14, 1, "dgray")             # vents
    keys(s, 3, 5, 6, 4, "dgray", 2, 1, 1, 1)
    s.rect(7, 13, 9, 1, "dgray")             # space bar
    s.rect(21, 3, 3, 1, "orange")            # RESET
    s.rect(21, 7, 3, 6, "black")             # cartridge slot
    return s


def vdp_stick():
    """SG-1000 / SC-3000 joystick: a gray slab, a black stick near the left and a red fire button at each end."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "gray", 3)
    for y in range(12):
        for x in (0, 1, 2, 23, 24, 25):
            if s.g[y][x]:
                s.g[y][x] = "red"
    s.ellipse(8.5, 5.5, 4, 4, "dgray")
    s.ellipse(8.5, 5.5, 2.5, 2.5, "black")
    return s


def vic20_console():
    """Commodore VIC-20: a cream case with brown keys and the column of four tan function keys at the right."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "cream", 3)
    keys(s, 3, 3, 6, 4, "brown", 2, 1, 1, 1)
    for i in range(4):
        s.rect(21, 3 + i * 2, 2, 1, "tan")
    s.rect(6, 12, 10, 1, "brown")
    return s


def x68000_console():
    """Sharp X68000: the two black towers side by side: the narrow drive tower with two floppy slots and their
    beige eject tabs, the wide computer tower with its activity lamps, on a dark base."""
    s = Sprite(26, 23)
    s.rect(0, 21, 26, 2, "dark")
    s.rrect(0, 0, 10, 21, "dgray", 2)
    s.rect(3, 3, 1, 11, "black")
    s.rect(6, 3, 1, 11, "black")
    s.rect(2, 14, 3, 2, "tan")
    s.rect(5, 14, 3, 2, "tan")
    s.rrect(10, 0, 16, 21, "dark", 2)
    for y in (3, 6, 9, 12):
        s.rect(12, y, 3, 1, "gray")
    return s


def x68000_pad():
    """X68000 Cyber Stick: a wide black slab with a stick at each end, red tips, and the three round A, B and C
    buttons between them."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 3)
    for cx in (4.5, 20.5):
        s.ellipse(cx, 7.5, 3, 3, "dgray")
        s.ellipse(cx, 7.5, 1.5, 1.5, "red")
    for x in (8, 12, 16):
        s.rect(x, 5, 2, 2, "gray")
    return s


def zxs_console():
    """ZX Spectrum: a black case of gray rubber keys with the rainbow stripes across the bottom right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    keys(s, 3, 2, 7, 4, "dgray", 2, 1, 1, 1)
    for i, c in enumerate(("red", "yellow", "green", "cyan")):
        for k in range(5):
            x, y = 17 + i + k, 13 - k
            if 0 <= x < 26 and s.g[y][x]:
                s.px(x, y, c)
    return s


def zxs_stick():
    """Spectrum joystick (Quickshot II): a black pistol grip with the red trigger on top and a red fire button on the
    base."""
    s = Sprite(26, 23)
    s.rrect(0, 13, 26, 10, "dark", 3)
    s.rect(11, 3, 4, 11, "black")
    s.rect(10, 0, 6, 4, "red")
    s.rrect(3, 16, 4, 4, "red", 1)
    return s


SHARED = {
    "3ds": n3ds, "dsi": dsi, "fake08": pico, "ffplay": ffplay, "gamate": gamate, "gw": gw, "j2me": j2me,
    "mkxp-z": mkxp, "wolf": wolf,
}
CONSOLES = {
    "amiga": amiga_console, "coco": coco_console, "cpc": cpc_console, "dos": dos_console, "fbneo": arcade_cab,
    "gametank": gametank_console, "loopy": loopy, "msu1": msu1_console, "msumd": msumd_console, "vdp": vdp_console,
    "vic20": vic20_console, "x68000": x68000_console, "zxs": zxs_console,
}
CONTROLLERS = {
    "amiga": amiga_mouse, "coco": coco_stick, "cpc": cpc_stick, "dos": dos_keyboard, "fbneo": arcade_stick,
    "gametank": gametank_pad, "loopy": loopy_pad, "msu1": msu1_pad, "msumd": msumd_pad, "vdp": vdp_stick, "vic20": cx40,
    "x68000": x68000_pad, "zxs": zxs_stick,
}
