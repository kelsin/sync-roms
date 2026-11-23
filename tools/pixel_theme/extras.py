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
    """Bit Corp Gamate: gray portrait handheld, wide screen, d-pad and two buttons below, speaker grille."""
    s = Sprite(18, 23)
    s.rrect(0, 0, 18, 23, "gray", 3)
    s.rrect(1, 1, 16, 12, "dgray", 2)
    s.rect(3, 3, 12, 8, "screen")
    face(s, 9, 4, 3)
    plus(s, 2, 15, 6, 2, "dark")
    s.rrect(13, 16, 3, 3, "dark", 1)         # A
    s.rrect(9, 18, 3, 3, "dark", 1)          # B
    s.rect(2, 21, 3, 1, "dgray")             # start / select
    return s


def gw():
    """Game & Watch: wide silver case, LCD in a black frame, d-pad on the left, a button on the right, small keys below."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "gray", 2)
    s.rect(6, 2, 14, 9, "black")
    s.rect(7, 3, 12, 7, "screen")
    face(s, 13, 4, 3)
    plus(s, 1, 5, 3, 1, "dark")
    s.rrect(22, 5, 3, 3, "red", 1)           # jump
    s.rect(8, 13, 3, 1, "dgray")             # game A / game B / time
    s.rect(15, 13, 3, 1, "dgray")
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
    """Casio Loopy: a white rounded console with its pad built in, a pink cartridge in the top slot, two pink buttons."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "white", 4)
    s.rect(5, 2, 16, 4, "pink")              # cartridge in the slot
    s.rect(7, 3, 12, 1, "white")             # label
    plus(s, 3, 8, 6, 2, "gray")              # d-pad
    s.rrect(14, 9, 3, 3, "pink", 1)
    s.rrect(19, 9, 3, 3, "pink", 1)
    return s


def mkxp():
    """mkxp-z runs RPG Maker (RGSS, built on Ruby): a faceted ruby."""
    s = Sprite(24, 17)
    for y in range(5):                             # crown, widening 1:1
        s.rect(4 - y, y, 16 + 2 * y, 1, "red")
    s.rect(0, 5, 24, 1, "maroon")                  # girdle
    for y in range(6, 17):                         # pavilion, narrowing 1:1
        s.rect(y - 5, y, 24 - 2 * (y - 5), 1, "red")
    s.rect(7, 1, 10, 2, "pink")                    # table highlight
    return s


def wolf():
    """Wolfenstein 3D: B.J. Blazkowicz's face from the status bar, brown hair, blue eyes, in a green tunic."""
    s = Sprite(18, 22)
    s.rrect(0, 0, 18, 18, "tan", 3)
    for y in range(7):
        for x in range(18):
            if s.g[y][x]:
                s.g[y][x] = "brown"
    for y in range(7, 10):                         # sideburns
        for x in (0, 1, 16, 17):
            if s.g[y][x]:
                s.g[y][x] = "brown"
    s.rect(4, 10, 2, 2, "blue")
    s.rect(12, 10, 2, 2, "blue")
    s.rect(3, 9, 4, 1, "brown")                    # brows
    s.rect(11, 9, 4, 1, "brown")
    s.rect(8, 12, 2, 2, "orange")                  # nose
    s.rect(6, 15, 6, 1, "dark")
    s.rect(6, 18, 6, 1, "tan")                     # neck
    s.rrect(1, 19, 16, 3, "forest", 1)
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


def amiga_stick():
    """Amiga joystick: the one-button digital stick of the era, a gray base with the red fire button."""
    return joystick("gray", "dark", "black", [(3, "red")])


def coco_console():
    """TRS-80 Color Computer: a gray case with ribbed top vents and a black keyboard of light keys."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "gray", 3)
    for y in (2, 4):
        s.rect(4, y, 18, 1, "dgray")
    s.rect(2, 7, 22, 7, "black")
    keys(s, 4, 8, 6, 3, "white", 2, 1, 1, 1)
    return s


def coco_stick():
    """Color Computer joystick: black base, black ball, one gray fire button."""
    return joystick("dark", "dgray", "black", [(3, "gray")])


def cpc_console():
    """Amstrad CPC 464: dark keyboard with the cassette deck at the top right and four colored keys."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dgray", 3)
    s.rect(14, 2, 9, 5, "black")             # cassette deck
    s.rect(15, 3, 7, 3, "gray")
    s.rect(16, 4, 1, 1, "dark")
    s.rect(20, 4, 1, 1, "dark")
    keys(s, 3, 9, 6, 2, "gray", 2, 1, 1, 1)
    s.rect(19, 9, 2, 1, "red")               # color keys
    s.rect(22, 9, 1, 1, "green")
    s.rect(19, 11, 2, 1, "blue")
    s.rect(22, 11, 1, 1, "yellow")
    return s


def cpc_stick():
    """Amstrad joystick: dark base, blue ball and a red fire button."""
    return joystick("dark", "dgray", "blue", [(19, "red")])


def dos_console():
    """DOS PC: a cream CRT with a prompt on the desktop case, a big and a small floppy drive."""
    s = Sprite(26, 22)
    s.rrect(3, 0, 20, 13, "cream", 2)
    s.rect(5, 2, 16, 8, "black")
    s.rect(6, 3, 3, 1, "screen")             # C:\> prompt
    s.rect(6, 5, 1, 1, "screen")
    s.rect(7, 5, 2, 1, "dgray")
    s.rrect(0, 14, 26, 8, "cream", 2)
    s.rect(3, 17, 9, 1, "dark")              # 5.25" drive
    s.rect(15, 17, 5, 1, "dark")             # 3.5" drive
    s.rect(22, 17, 1, 1, "green")
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
    """GameTank: a black box with a cartridge on top (white label), vent slots and two pad ports."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "dark", 3)
    s.rect(5, 2, 16, 6, "dgray")             # cartridge
    s.rect(7, 3, 6, 3, "white")
    for x in (15, 17, 19):
        s.rect(x, 3, 1, 4, "dark")
    s.rect(4, 11, 6, 2, "black")             # pad ports
    s.rect(16, 11, 6, 2, "black")
    s.rect(12, 14, 2, 1, "red")              # power light
    return s


def gametank_pad():
    """GameTank controller: a black pad with a d-pad on the left and a row of red buttons."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "dark", 4)
    plus(s, 3, 3, 6, 2, "gray")
    s.rrect(13, 4, 3, 3, "red", 1)
    s.rrect(17, 4, 3, 3, "red", 1)
    s.rrect(21, 4, 3, 3, "red", 1)
    return s


def vdp_console():
    """Sega SC-3000: a white keyboard computer with the cartridge slot on top and black keys."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "white", 3)
    s.rect(3, 2, 20, 2, "dark")              # cartridge slot
    s.rect(11, 2, 4, 1, "red")
    keys(s, 3, 6, 6, 3, "dgray", 2, 1, 1, 1)
    keys(s, 21, 6, 1, 3, "dgray", 2, 1, 1, 1)
    s.rect(7, 13, 10, 1, "dgray")
    return s


def vdp_stick():
    """SC-3000 joystick: white base, red ball, two red fire buttons."""
    return joystick("white", "dgray", "red", [(2, "red"), (20, "red")])


def vic20_console():
    """Commodore VIC-20: a cream case, brown keys, the function key column and a space bar."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "cream", 3)
    s.rect(3, 2, 20, 2, "brown")             # stripe
    keys(s, 3, 6, 6, 3, "brown", 2, 1, 1, 1)
    for i in range(3):
        s.rect(21, 6 + i * 2, 2, 1, "brown")
    s.rect(6, 12, 12, 1, "brown")
    return s


def x68000_console():
    """Sharp X68000: the dark twin towers around a CRT, floppy drives under it."""
    s = Sprite(26, 23)
    s.rrect(0, 0, 7, 23, "dgray", 2)         # left tower
    for y in (3, 5, 7):
        s.rect(2, y, 3, 1, "dark")
    s.rect(2, 19, 3, 1, "red")
    s.rect(7, 2, 12, 12, "dark")             # CRT
    s.rect(9, 4, 8, 8, "black")
    s.rect(7, 14, 12, 8, "dgray")
    s.rect(9, 16, 4, 1, "black")
    s.rect(14, 16, 4, 1, "black")
    s.rect(9, 19, 8, 1, "black")
    for y in range(23):
        for x in range(7):
            if s.g[y][x]:
                s.g[y][25 - x] = s.g[y][x]
    return s


def x68000_pad():
    """X68000 pad: a black pad with a d-pad, start / select pills and two round buttons."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "dark", 3)
    plus(s, 3, 3, 6, 2, "gray")
    s.rect(11, 8, 2, 1, "gray")
    s.rect(14, 8, 2, 1, "gray")
    s.rrect(17, 4, 3, 3, "gray", 1)
    s.rrect(21, 4, 3, 3, "gray", 1)
    return s


def zxs_console():
    """ZX Spectrum: a black case of rubber keys with the rainbow stripes across the bottom right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    keys(s, 3, 2, 7, 4, "gray", 2, 1, 1, 1)
    for i, c in enumerate(("red", "yellow", "green", "cyan")):
        for k in range(5):
            x, y = 17 + i + k, 13 - k
            if 0 <= x < 26 and s.g[y][x]:
                s.px(x, y, c)
    return s


def zxs_stick():
    """Spectrum joystick (Quickshot style): dark base, red ball, a yellow fire button."""
    return joystick("dark", "gray", "red", [(3, "yellow"), (19, "yellow")])


SHARED = {
    "3ds": n3ds, "dsi": dsi, "fake08": pico, "ffplay": ffplay, "gamate": gamate, "gw": gw, "j2me": j2me,
    "loopy": loopy, "mkxp-z": mkxp, "wolf": wolf,
}
CONSOLES = {
    "amiga": amiga_console, "coco": coco_console, "cpc": cpc_console, "dos": dos_console, "fbneo": arcade_cab,
    "gametank": gametank_console, "msu1": msu1_console, "msumd": msumd_console, "vdp": vdp_console,
    "vic20": vic20_console, "x68000": x68000_console, "zxs": zxs_console,
}
CONTROLLERS = {
    "amiga": amiga_stick, "coco": coco_stick, "cpc": cpc_stick, "dos": dos_keyboard, "fbneo": arcade_stick,
    "gametank": gametank_pad, "msu1": msu1_pad, "msumd": msumd_pad, "vdp": vdp_stick, "vic20": cx40,
    "x68000": x68000_pad, "zxs": zxs_stick,
}
