"""Nintendo and Sega consoles and their pads (SHARED: drawn the same in both themes)."""
from .sprite import Sprite



def on(s, x, y, w, h, c):
    """Paint only over cells that already hold a color, so a stripe keeps the body's rounded corners."""
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < s.w and 0 <= yy < s.h and s.g[yy][xx] is not None:
                s.g[yy][xx] = c


# ---------------------------------------------------------------- Famicom

def fc_console():
    """Famicom (Wikimedia, Evan-Amos): cream body, red front stripe, red eject lever and buttons, and the red
    controller II dock with its tan face on the right side."""
    s = Sprite(26, 15)
    s.rrect(3, 0, 16, 6, "cream", 1)        # raised rear (cartridge bay)
    s.rrect(0, 4, 22, 11, "cream", 2)
    on(s, 0, 10, 22, 2, "maroon")           # red stripe along the front
    s.rect(9, 2, 4, 4, "red")               # cartridge eject lever
    s.rect(3, 6, 3, 2, "red")               # power / reset
    s.rect(16, 6, 3, 2, "red")
    s.rrect(21, 1, 5, 14, "maroon", 1)      # controller II dock
    s.rect(22, 4, 3, 9, "tan")
    s.rect(22, 8, 3, 1, "black")            # its d-pad
    s.rect(23, 7, 1, 3, "black")
    return s


def fds_console():
    """Famicom Disk System (Wikimedia, Evan-Amos): a red drive under the cream Famicom, with its black RAM adapter."""
    s = Sprite(26, 23)
    s.rrect(5, 0, 16, 5, "dark", 1)         # RAM adapter at the back
    s.rrect(1, 3, 24, 8, "cream", 2)        # the Famicom
    on(s, 1, 8, 24, 2, "maroon")
    s.rect(11, 4, 4, 2, "red")
    s.rrect(0, 11, 26, 12, "maroon", 2)     # the disk drive
    s.rect(2, 14, 22, 7, "dark")            # front panel
    s.rect(4, 16, 14, 2, "black")           # disk slot
    s.rect(20, 16, 3, 2, "yellow")          # eject
    return s


# ---------------------------------------------------------------- Super Famicom family

def sfc_console():
    """Super Famicom (Wikimedia, Evan-Amos): light body, darker top panel with the slot, power, eject and reset,
    the four-colour dot, two pad ports on the front."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "gray", 2)
    s.rrect(3, 1, 20, 8, "dgray", 1)
    s.rect(5, 2, 12, 1, "black")           # cartridge slot
    s.px(21, 2, "blue")                    # the four-colour dot
    s.px(20, 3, "green")
    s.px(22, 3, "red")
    s.px(21, 4, "yellow")
    s.rect(5, 5, 4, 3, "dark")             # power
    s.rect(10, 5, 6, 3, "gray")            # eject
    s.rect(17, 5, 4, 3, "dark")            # reset
    s.rect(4, 11, 5, 2, "black")           # pad ports
    s.rect(17, 11, 5, 2, "black")
    return s


def sufami_console():
    """Sufami Turbo adapter: a gray SNES-style cartridge with two mini cartridges plugged into its top."""
    s = Sprite(26, 20)
    s.rrect(3, 0, 8, 11, "orange", 1)
    s.rect(4, 2, 6, 4, "white")
    s.rrect(15, 0, 8, 11, "teal", 1)
    s.rect(16, 2, 6, 4, "white")
    s.rrect(0, 9, 26, 11, "gray", 2)
    s.rect(3, 10, 8, 1, "black")           # slots
    s.rect(15, 10, 8, 1, "black")
    s.rect(7, 14, 12, 3, "white")          # label
    return s


def satella_console():
    """Satellaview (Wikimedia, "Satellaview with Super Famicom"): the BS-X memory pack on top of a Super Famicom,
    which sits on the Satellaview box with its power light."""
    s = Sprite(26, 23)
    s.rrect(0, 5, 26, 10, "gray", 2)        # Super Famicom
    s.rect(3, 7, 20, 2, "dgray")
    s.rect(4, 11, 5, 2, "black")            # its pad ports
    s.rect(17, 11, 5, 2, "black")
    s.rrect(7, 0, 12, 9, "dgray", 1)        # BS-X memory pack
    s.rect(9, 2, 8, 4, "yellow")            # its label
    s.rrect(1, 15, 24, 8, "gray", 2)        # Satellaview box
    s.rect(2, 15, 22, 1, "dgray")           # seam
    s.rect(15, 18, 2, 2, "dark")            # access
    s.rect(19, 18, 2, 2, "red")             # power
    return s


def sgb_console():
    """Super Game Boy (Wikimedia, Evan-Amos): a light gray SNES-style cartridge with a Game Boy cartridge in the top recess."""
    s = Sprite(26, 23)
    s.rrect(7, 0, 12, 11, "dgray", 1)       # Game Boy cartridge
    s.rect(9, 2, 8, 4, "cream")
    s.rrect(1, 7, 24, 14, "gray", 2)
    s.rect(6, 9, 14, 2, "black")           # Game Boy slot
    s.rect(5, 13, 16, 5, "white")          # label
    s.rect(5, 21, 16, 2, "dgray")          # cartridge edge
    return s


# ---------------------------------------------------------------- Nintendo 64

def n64_console():
    """Nintendo 64 (Wikimedia, Evan-Amos): charcoal body, gray cartridge in the top slot, four pad ports with
    light rings and the four-colour N plate between them."""
    s = Sprite(26, 20)
    s.rrect(8, 0, 10, 9, "gray", 1)        # cartridge
    s.rect(10, 2, 6, 3, "white")
    s.rrect(0, 7, 26, 13, "dgray", 3)
    s.rect(7, 8, 12, 2, "black")           # cartridge slot
    for x in (1, 6, 16, 21):               # pad ports
        s.rect(x, 13, 4, 3, "gray")
        s.rect(x + 1, 14, 2, 1, "black")
    s.rect(11, 12, 4, 4, "black")          # logo plate
    s.px(12, 13, "red")
    s.px(13, 13, "yellow")
    s.px(12, 14, "green")
    s.px(13, 14, "blue")
    return s


# ---------------------------------------------------------------- Sega Genesis / Mega Drive family

def md_console():
    """Genesis / Mega Drive (Wikimedia, Evan-Amos): black slab, big round cartridge lid with its magenta band,
    a vent grille and the power slider and reset."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    s.rect(2, 2, 5, 4, "dgray")            # vent grille
    s.rect(2, 3, 5, 1, "dark")
    s.rect(2, 5, 5, 1, "dark")
    s.ellipse(15.5, 6.5, 8, 5.5, "dgray")  # round lid
    s.ellipse(15.5, 6.5, 6.5, 4, "black")
    s.rect(11, 2, 9, 1, "dgray")           # cartridge slot
    s.rect(12, 7, 7, 2, "maroon")          # magenta band
    s.rect(3, 9, 4, 2, "gray")             # reset
    return s


def x32_console():
    """32X (Wikimedia, Evan-Amos): a black mushroom-shaped add-on with a cartridge cradle in the top, plugged into
    the Genesis cartridge slot (round lid band showing)."""
    s = Sprite(26, 23)
    s.rrect(7, 0, 12, 3, "dgray", 1)       # cartridge cradle
    s.rect(9, 1, 8, 1, "black")
    s.rrect(1, 2, 24, 9, "dark", 4)        # the 32X cap
    s.rect(8, 5, 10, 3, "black")           # badge
    s.rect(9, 11, 8, 3, "dgray")           # neck into the Genesis
    s.rrect(0, 13, 26, 10, "dark", 2)      # the Genesis below
    s.rect(2, 15, 22, 1, "dgray")
    s.rect(9, 18, 8, 2, "maroon")          # lid band
    s.rect(3, 20, 4, 2, "black")           # pad ports
    s.rect(19, 20, 4, 2, "black")
    return s


def segacd_console():
    """Sega CD (Wikimedia, "Sega-CD-Model1-Set"): the Genesis sitting on the wider black disc unit with its disc
    lid and ready/access panel."""
    s = Sprite(26, 21)
    s.rrect(2, 0, 22, 11, "dark", 2)       # Genesis on top
    s.ellipse(14.5, 5, 7, 4, "dgray")
    s.ellipse(14.5, 5, 5.5, 2.8, "black")
    s.rect(11, 5, 7, 1, "maroon")
    s.rect(4, 2, 4, 3, "dgray")            # vent
    s.rrect(0, 10, 26, 11, "dark", 2)      # the CD unit
    s.rect(2, 13, 15, 5, "dgray")          # disc lid
    s.rect(3, 14, 13, 1, "black")
    s.rect(19, 13, 5, 3, "dgray")          # ready / access
    s.rect(20, 14, 3, 1, "gray")
    return s


# ---------------------------------------------------------------- Saturn, Dreamcast

def saturn_console():
    """Saturn, Japanese gray model (Wikimedia, Evan-Amos JP Mk1): gray body, black cartridge flap, round lid
    and a black front band with three blue buttons."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "gray", 3)
    s.rect(5, 1, 16, 2, "black")           # cartridge flap
    s.ellipse(12.5, 7.5, 8.5, 4.5, "dgray")  # CD lid
    s.ellipse(12.5, 7.5, 7.5, 3.5, "gray")
    s.rect(8, 8, 9, 1, "black")            # disc slot
    s.rect(1, 11, 24, 4, "black")          # front band
    s.rect(3, 12, 4, 2, "blue")            # power / open / access
    s.rect(11, 12, 4, 2, "blue")
    s.rect(19, 12, 4, 2, "blue")
    return s


def dc_console():
    """Dreamcast: white box with the round disc lid, two corner buttons and four pad ports."""
    s = Sprite(26, 20)
    s.rrect(0, 0, 26, 15, "white", 3)
    s.ellipse(12.5, 7, 10.5, 6.5, "gray")  # disc lid
    s.ellipse(12.5, 7, 2.5, 1.5, "white")
    s.rect(2, 11, 3, 2, "gray")            # open / power buttons
    s.rect(21, 11, 3, 2, "gray")
    s.rrect(0, 15, 26, 5, "gray", 2)
    for x in (2, 8, 14, 20):
        s.rect(x, 16, 4, 3, "dark")        # four pad ports
    return s


# ---------------------------------------------------------------- SG-1000 / Master System

def sg1000_console():
    """SG-1000: white slab, grey vents either side of the cartridge slot, blue and red stripes, red power button."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "white", 2)
    s.rect(9, 1, 8, 4, "dgray")            # cartridge slot
    s.rect(2, 2, 5, 3, "gray")             # vents
    s.rect(19, 2, 5, 3, "gray")
    s.rect(0, 7, 26, 2, "blue")
    s.rect(0, 9, 26, 1, "red")
    s.rect(19, 11, 4, 2, "red")            # power button
    return s


def ms_console():
    """Master System (Wikimedia, Evan-Amos): black body, red panel with the cartridge slot above it, red power tab,
    thin red line and two pad ports on the front."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    s.rect(12, 1, 12, 2, "black")          # cartridge slot
    s.rect(12, 3, 12, 6, "red")            # red panel
    s.rect(12, 4, 12, 1, "black")          # reset / pause bar
    s.rect(2, 10, 5, 2, "red")             # power
    s.rect(9, 10, 4, 2, "black")           # pad ports
    s.rect(14, 10, 4, 2, "black")
    on(s, 0, 12, 26, 1, "maroon")          # red line
    return s


def fc_pad():
    """Famicom pad (Wikimedia, Evan-Amos, "Nintendo-Famicom-Controller-I-FL"): red shell, cream face with the black
    d-pad, the red select / start pills and the two black round buttons B and A on the lower right band."""
    s = Sprite(26, 13)
    s.rrect(0, 0, 26, 13, "red", 2)
    s.rect(1, 1, 13, 11, "cream")
    s.rect(14, 5, 11, 7, "cream")
    plus(s, 2, 3, "black")
    s.rect(10, 8, 2, 1, "maroon")           # select / start
    s.rect(13, 8, 2, 1, "maroon")
    btn(s, 16, 6, "black")                  # B and A
    btn(s, 20, 6, "black")
    return s


# ---------------------------------------------------------------- controllers (pads)
# Every pad is one body: the shoulder buttons are the raised top corners of its outline, never separate pieces.
# Symmetric bodies come from the left half's first and last row in each column.

def plus(s, x, y, c):
    """D-pad: a plus 7 wide and 7 tall (3-wide arms), top-left at (x, y)."""
    s.rect(x, y + 2, 7, 3, c)
    s.rect(x + 2, y, 3, 7, c)


def btn(s, x, y, c):
    """3x3 face button, top-left at (x, y)."""
    s.rect(x, y, 3, 3, c)


def diamond(s, x, y, top, left, right, bottom):
    """Four 2x2 buttons in a diamond with a 1-cell gap between neighbours; the 8x8 box has its top-left at (x, y)."""
    s.rect(x + 3, y, 2, 2, top)
    s.rect(x, y + 3, 2, 2, left)
    s.rect(x + 6, y + 3, 2, 2, right)
    s.rect(x + 3, y + 6, 2, 2, bottom)


def body_from_half(tops, bottoms, body):
    """A symmetric body from the left half's first and last row in each column. A column whose top is above the
    middle columns' is a raised corner: the shoulder button, one piece with the body."""
    s = Sprite(len(tops) * 2, max(bottoms) + 1)
    for x, (t, b) in enumerate(zip(tops, bottoms)):
        for y in range(t, b + 1):
            s.px(x, y, body)
    s.mirror()
    return s


# SNES / Super Famicom: a dog bone, wide lobes with the shoulder buttons as their raised top corners
SNES_TOPS = [2, 1, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3]
SNES_BOTTOMS = [11, 12, 13, 13, 13, 13, 13, 12, 11, 10, 10, 10, 10]


def _snes_pad(top, left, right, bottom, plate=True, body="gray", pad="dark"):
    s = body_from_half(SNES_TOPS, SNES_BOTTOMS, body)
    plus(s, 2, 4, pad)                       # d-pad
    s.rect(10, 9, 2, 1, "dark")              # select / start
    s.rect(14, 9, 2, 1, "dark")
    if plate:
        s.ellipse(20.5, 7.5, 4.5, 4.5, "dgray")  # the Super Famicom's dark button plate
    diamond(s, 17, 4, top, left, right, bottom)
    return s


def sfc_pad():
    """Super Famicom pad (Wikimedia, Evan-Amos, "Super-Famicom-Controller"): dog-bone body with the shoulder buttons
    as the raised lobe tops, d-pad, select / start, dark plate with X blue, Y green, A red, B yellow."""
    return _snes_pad("blue", "green", "red", "yellow")


def sgb_pad():
    """SNES (US) pad: light X and Y, purple A and B."""
    return _snes_pad("white", "white", "purple", "purple", plate=False)


def n64_pad():
    """N64 pad (Wikimedia, Evan-Amos, "Nintendo-64-wController-L"): trident with the L and R shoulders as the raised
    top corners, d-pad on the left prong, red Start, yellow C diamond, blue A and green B, stick and Z trigger on
    the centre prong."""
    tops = [2, 1, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3]
    bottoms = [20, 21, 22, 22, 22, 22, 21, 13, 13, 20, 21, 21, 21]
    s = body_from_half(tops, bottoms, "gray")
    plus(s, 2, 5, "dark")                  # d-pad
    s.rect(10, 4, 2, 2, "red")             # start
    s.ellipse(12.5, 15, 3.1, 3.1, "dgray")  # stick
    s.ellipse(12.5, 15, 1.6, 1.6, "dark")
    diamond(s, 17, 3, "yellow", "yellow", "yellow", "yellow")   # C buttons
    btn(s, 13, 4, "green")                 # B
    btn(s, 13, 8, "blue")                  # A
    return s


# Genesis / Mega Drive: a smooth boomerang, lobes at both ends, a concave underside
def _md_body(h, color="dark"):
    tops = [3, 2, 1] + [0] * 10
    bottoms = [h - 3, h - 2, h - 1, h - 1, h - 1, h - 2, h - 2, h - 3, h - 3, h - 4, h - 4, h - 5, h - 5]
    return body_from_half(tops, bottoms, color)


def md_pad():
    """Genesis 3-button pad (Wikimedia, Evan-Amos, "Sega-Mega-Drive-controllers"): boomerang body, d-pad on the left,
    Start beside the buttons, A B C rising on the diagonal."""
    s = _md_body(14)
    plus(s, 2, 3, "gray")
    s.rect(10, 6, 3, 1, "gray")
    for n, x in enumerate((14, 18, 22)):
        btn(s, x, 5 - n, "gray")
    return s


def x32_pad():
    """Genesis 6-button pad (Wikimedia, Evan-Amos, "Sega-Genesis-6But-Cont"): X Y Z above A B C, Start beside them."""
    s = _md_body(16)
    plus(s, 2, 4, "gray")
    s.rect(10, 7, 3, 1, "gray")
    for x in (14, 18, 22):
        s.rect(x, 3, 3, 2, "gray")         # X Y Z
        btn(s, x, 6, "gray")               # A B C
    return s


def saturn_body(body, chin=13):
    """Saturn pad body: wide, the shoulders its raised top corners, a grip down each side."""
    tops = [2, 1, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3]
    bottoms = [14, 16, 17, 17, 17, 16, 16, 15, 15, 14, 14, chin, chin]
    return body_from_half(tops, bottoms, body)


def saturn_pad():
    """Saturn pad, Japanese gray (Wikimedia, Evan-Amos, "Sega-Saturn-JP-Mk2-Controller"): wide shell with the L / R
    shoulders as raised corners, d-pad, Start, X Y Z over green A, yellow B and blue C."""
    s = saturn_body("gray")
    plus(s, 2, 4, "dgray")
    s.rect(10, 9, 3, 1, "magenta")         # start
    for x in (14, 18, 22):
        btn(s, x, 4, "white")           # X Y Z
    for x, c in ((14, "green"), (18, "yellow"), (22, "blue")):
        btn(s, x, 8, c)                 # A B C
    return s


def dc_pad():
    """Dreamcast pad (Wikimedia, Evan-Amos, "Sega-Dreamcast-Controller-FL"): white body with the triggers as raised
    top corners, stick over d-pad on the left, the VMU bay in the middle with the Start triangle under it, the
    four colored buttons on the right, two tapering grips."""
    tops = [2, 1, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3]
    bottoms = [20, 21, 22, 22, 22, 22, 22, 21, 20, 19, 18, 17, 16]
    s = body_from_half(tops, bottoms, "white")
    s.ellipse(4, 5, 3.4, 3.4, "gray")      # stick dish
    s.ellipse(4, 5, 2.0, 2.0, "dgray")
    plus(s, 1, 11, "gray")                 # d-pad
    s.rect(10, 4, 6, 8, "gray")            # VMU bay
    s.rect(11, 5, 4, 4, "screen")
    s.rect(11, 9, 4, 2, "dgray")
    s.rect(11, 14, 4, 1, "gray")           # start triangle
    s.rect(12, 15, 2, 1, "gray")
    diamond(s, 17, 7, "green", "yellow", "blue", "red")
    return s


def sg1000_pad():
    """SG-1000 joystick: gray case seen from the front, black stick with a ball, two red buttons."""
    s = Sprite(26, 17)
    s.rrect(0, 7, 26, 10, "gray", 2)
    s.rect(11, 3, 3, 6, "black")           # stick
    s.ellipse(12.5, 3.5, 3, 3, "red")
    s.rect(1, 9, 8, 1, "dgray")
    s.rect(1, 12, 8, 1, "dgray")
    btn(s, 16, 10, "red")               # buttons
    btn(s, 21, 10, "red")
    return s


def _sms_pad(body, face, label):
    s = Sprite(26, 13)
    s.rrect(0, 0, 26, 13, body, 2)
    plus(s, 2, 3, face)
    s.rect(10, 6, 4, 1, face)              # logo plate
    s.rect(15, 2, 3, 1, label)             # labels
    s.rect(20, 2, 3, 1, label)
    btn(s, 15, 5, face)                    # buttons 1 and 2
    btn(s, 20, 5, face)
    return s


def ms_pad():
    """Master System pad (Wikimedia, Evan-Amos, "Sega-Master-System-Controllers"): black slab, d-pad on the left,
    the SEGA plate, buttons 1 and 2 with red labels."""
    return _sms_pad("dark", "gray", "red")


SHARED = {}
CONSOLES = {
    "fc": fc_console, "fds": fds_console, "sfc": sfc_console, "sufami": sufami_console,
    "satella": satella_console, "sgb": sgb_console, "n64": n64_console, "md": md_console,
    "32x": x32_console, "segacd": segacd_console, "saturn": saturn_console, "dc": dc_console,
    "segasgone": sg1000_console, "ms": ms_console,
}
CONTROLLERS = {
    "fc": fc_pad, "fds": fc_pad, "sfc": sfc_pad, "sufami": sfc_pad, "satella": sfc_pad,
    "sgb": sgb_pad, "n64": n64_pad, "md": md_pad, "32x": x32_pad, "segacd": md_pad,
    "saturn": saturn_pad, "dc": dc_pad, "segasgone": sg1000_pad, "ms": ms_pad,
}
