"""Japanese and US/Western versions of the consoles and pads that visibly differ.

VARIANTS[icon id][region]["console" | "pad"] is a function returning a Sprite. A region that already exists in
nintendo_sega.py or others.py is referenced from there; the rest is drawn here. DEFAULT is the region the themes use.
"""
from importlib import import_module

from .sprite import Sprite


def ref(module, name):
    """A function that calls `name` from a sibling module when asked (those modules may import this one back)."""
    def draw():
        return getattr(import_module(f".{module}", __package__), name)()
    draw.__doc__ = f"{module}.{name}"
    return draw


def on(s, x, y, w, h, c):
    """Paint only over cells that already hold a color, so a stripe keeps the body's rounded corners."""
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < s.w and 0 <= yy < s.h and s.g[yy][xx] is not None:
                s.g[yy][xx] = c


# ---------------------------------------------------------------- NES (US)

def nes_console():
    """NES (Wikimedia, "NES-Console-Set"): light gray top with the black ridged cartridge band on the right, a
    darker gray front with the red brand bar, two buttons and the two pad ports."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "gray", 2)
    on(s, 0, 9, 26, 5, "dgray")             # darker front
    s.rect(3, 2, 14, 5, "white")            # flip door
    s.rect(19, 0, 5, 8, "dark")             # black cartridge band
    s.rect(20, 2, 3, 1, "dgray")            # its ridges
    s.rect(20, 4, 3, 1, "dgray")
    s.rect(3, 8, 6, 1, "maroon")            # brand bar
    s.rect(3, 10, 4, 2, "gray")             # power / reset
    s.rect(8, 10, 4, 2, "gray")
    s.rect(15, 10, 3, 2, "black")           # pad ports
    s.rect(20, 10, 3, 2, "black")
    return s


# ---------------------------------------------------------------- SNES (US) and Super Game Boy (US)

def snes_console():
    """US Super NES (Wikimedia, "SNES-Mod1-Console-Set"): boxy light gray, a pale top lid with the cartridge slot,
    purple power and reset slides either side of the gray eject, two pad ports below."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "gray", 2)
    s.rect(3, 1, 20, 4, "white")           # lid
    s.rect(5, 2, 16, 1, "gray")            # cartridge slot
    s.rect(4, 6, 6, 3, "purple")           # power
    s.rect(16, 6, 6, 3, "purple")          # reset
    s.rect(11, 6, 4, 3, "dgray")           # eject
    s.rect(4, 11, 6, 2, "dark")            # pad ports
    s.rect(16, 11, 6, 2, "dark")
    return s


def sgb_us_console():
    """US Super Game Boy (Wikimedia, "Super Game Boy US version"): the same cartridge with a white label carrying
    the blue logo and the red swoosh."""
    from .nintendo_sega import sgb_console
    s = sgb_console()
    s.rect(5, 13, 16, 5, "white")
    s.rect(7, 14, 12, 2, "blue")
    s.rect(7, 17, 12, 1, "red")
    return s


# ---------------------------------------------------------------- Genesis (US)

def genesis_console():
    """US Genesis (Wikimedia, "Sega-Genesis-Mod1-Set"): black slab, round lid with the silver ring and the red
    16-bit band, white reset button, vent grille."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    s.rect(2, 2, 5, 4, "dgray")            # vent grille
    s.rect(2, 3, 5, 1, "dark")
    s.rect(2, 5, 5, 1, "dark")
    s.ellipse(15.5, 6.5, 8, 5.5, "gray")   # silver ring
    s.ellipse(15.5, 6.5, 7, 4.5, "dgray")
    s.ellipse(15.5, 6.5, 5.5, 3.2, "black")
    s.rect(11, 2, 9, 1, "dgray")           # cartridge slot
    s.rect(12, 7, 7, 2, "red")             # red band
    s.rect(3, 9, 4, 2, "white")            # reset
    return s


def genesis32x_console():
    """Genesis 32X: the same black cap on a Genesis, whose lid has the silver ring and the red band."""
    from .nintendo_sega import x32_console
    s = x32_console()
    s.rect(7, 17, 12, 1, "gray")           # silver ring on the lid
    s.rect(9, 18, 8, 2, "red")
    return s


def sega_cd_console():
    """Sega CD (Wikimedia, "Sega-CD-Model1-Set"): the Genesis sits in the CD unit's tray, which rises at both sides."""
    s = Sprite(26, 21)
    s.rrect(2, 0, 22, 11, "dark", 2)       # Genesis
    s.ellipse(14.5, 5, 7, 4, "gray")       # silver ring
    s.ellipse(14.5, 5, 6, 3.3, "dgray")
    s.ellipse(14.5, 5, 4.8, 2.4, "black")
    s.rect(11, 5, 7, 1, "red")
    s.rect(4, 2, 4, 3, "dgray")            # vent
    s.rrect(0, 7, 26, 14, "dark", 2)       # the CD unit with its tray walls
    s.rect(2, 8, 1, 3, "dgray")
    s.rect(23, 8, 1, 3, "dgray")
    s.rect(2, 13, 15, 5, "dgray")          # disc lid
    s.rect(3, 14, 13, 1, "black")
    s.rect(19, 13, 5, 3, "dgray")          # ready / access
    s.rect(20, 14, 3, 1, "gray")
    return s


# ---------------------------------------------------------------- Master System (Mark III / Master System JP)

def mark3_console():
    """Sega Mark III (Wikimedia, "Sega-Sg-1000-MkIII-Console-FL"): long flat white case, vent grille on the left, black
    cartridge slot with a yellow tab on the right, the two joystick ports on the front."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "white", 2)
    s.rect(2, 1, 10, 1, "gray")            # vent grille
    s.rect(2, 3, 10, 1, "gray")
    s.rect(14, 1, 10, 3, "black")          # cartridge slot
    s.rect(14, 5, 3, 1, "yellow")          # label tab
    s.rect(18, 5, 6, 1, "gray")
    s.rect(1, 7, 24, 1, "dark")            # black front stripe
    s.rect(14, 9, 4, 2, "black")           # JOY 2 / JOY 1
    s.rect(20, 9, 4, 2, "black")
    return s


# ---------------------------------------------------------------- Saturn (US)

def saturn_us_console():
    """US Saturn (Wikimedia, "Sega-Saturn-Console-Set-Mk1"): the same shape in black, dark ring on the lid, flat
    front band with three dark buttons."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "dark", 3)
    s.rect(5, 1, 16, 2, "black")           # cartridge flap
    s.ellipse(12.5, 7.5, 8.5, 4.5, "dgray")  # CD lid
    s.ellipse(12.5, 7.5, 7.5, 3.5, "black")
    s.rect(11, 7, 3, 1, "dgray")           # logo
    s.rect(1, 11, 24, 4, "black")          # front band
    s.rect(3, 12, 4, 2, "dgray")
    s.rect(11, 12, 4, 2, "dgray")
    s.rect(19, 12, 4, 2, "dgray")
    return s


# ---------------------------------------------------------------- TurboGrafx-16 / PC Engine

def tg16_console():
    """TurboGrafx-16 (Wikimedia, "TurboGrafx16-Console-Set"): wide black box, ridged rear panels, the HuCard
    recess in the front with the orange logo bar, controller port at the right."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    s.rect(2, 2, 7, 1, "dgray")            # ridges
    s.rect(2, 4, 7, 1, "dgray")
    s.rect(17, 2, 7, 1, "dgray")
    s.rect(17, 4, 7, 1, "dgray")
    s.rect(10, 5, 6, 8, "black")           # card recess
    s.rect(11, 6, 4, 2, "dgray")
    s.rect(2, 10, 5, 1, "orange")          # logo bar
    s.rect(20, 9, 4, 3, "black")           # controller port
    return s


def pcecd_console():
    """PC Engine CD-ROM2 (Wikimedia, "NEC PC Engine CDROM2"): the white CD drive with its disc lid beside the white
    PC Engine with the green interface block, on the gray base with its round bays."""
    s = Sprite(26, 22)
    s.rrect(0, 1, 13, 11, "white", 2)      # CD drive
    s.ellipse(6, 6, 4.5, 3.5, "gray")
    s.ellipse(6, 6, 2.5, 1.8, "white")
    s.rrect(14, 0, 12, 9, "white", 2)      # PC Engine
    s.rect(16, 1, 8, 1, "black")
    s.rect(15, 5, 3, 3, "green")
    s.rrect(0, 11, 26, 11, "gray", 2)      # base
    for cx in (4.5, 10.5, 16.5, 22.5):
        s.ellipse(cx, 16.5, 2, 2, "dgray")
    return s


def tgcd_console():
    """TurboGrafx-CD (Wikimedia, "NEC-TurboGrafx-16-CD-FL"): the small black disc drive on the interface unit behind
    the black TurboGrafx-16."""
    s = Sprite(26, 22)
    s.rrect(6, 0, 17, 11, "dark", 2)       # CD drive
    s.ellipse(14.5, 4.5, 6, 3.5, "dgray")
    s.ellipse(14.5, 4.5, 4.5, 2.3, "black")
    s.rrect(0, 8, 26, 14, "dark", 2)       # TurboGrafx-16
    s.rect(1, 9, 24, 1, "dgray")
    s.rect(10, 12, 6, 8, "black")          # card recess
    s.rect(11, 13, 4, 2, "dgray")
    s.rect(2, 18, 5, 1, "orange")
    s.rect(20, 14, 4, 3, "black")
    return s


# ---------------------------------------------------------------- pads (see nintendo_sega.py for the helpers)

def nes_pad():
    """NES pad (Wikimedia, Evan-Amos, "Nintendo-Entertainment-System-NES-Controller-FL"): light gray rim around a black
    face, d-pad, a gray plate with the select / start pills, two red round buttons B and A."""
    from .nintendo_sega import btn, plus
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "gray", 1)
    s.rect(1, 1, 24, 10, "dark")
    plus(s, 2, 2, "black")
    s.rect(10, 3, 7, 6, "gray")             # select / start plate
    s.rect(11, 6, 2, 1, "dark")
    s.rect(14, 6, 2, 1, "dark")
    btn(s, 18, 4, "red")                    # B and A
    btn(s, 22, 4, "red")
    return s


def snes_pad():
    """US Super NES pad (Wikimedia, Evan-Amos, "Nintendo-Super-NES-Controller"): the same dog-bone body, d-pad,
    select / start slants, lilac X and Y and purple A and B."""
    from .nintendo_sega import _snes_pad
    return _snes_pad("periwinkle", "periwinkle", "purple", "purple", plate=False)


def genesis_pad():
    """US Genesis 3-button pad (Wikimedia, Evan-Amos, "Sega-Genesis-Mod1-Set"): boomerang body, d-pad, Start above
    the buttons, A B C in a shallow arc."""
    from .nintendo_sega import _md_body, btn, plus
    s = _md_body(14)
    plus(s, 2, 3, "gray")
    s.rect(10, 3, 3, 1, "gray")
    for x, y in ((14, 5), (18, 4), (22, 5)):
        btn(s, x, y, "gray")
    return s


def genesis6_pad():
    """US Genesis 6-button pad (Wikimedia, Evan-Amos, "Sega-Genesis-6But-Cont"): X Y Z above A B C on the boomerang."""
    from .nintendo_sega import x32_pad
    return x32_pad()


def mark3_pad():
    """Japanese Master System pad: white slab with a dark d-pad and two dark buttons (shape from the
    console's white styling; no photo of this pad was found)."""
    from .nintendo_sega import _sms_pad
    return _sms_pad("white", "dark", "red")


def saturn_us_pad():
    """US Saturn pad (Wikimedia, Evan-Amos, "Sega-Saturn-Controller-Mk-I-NA-FL"): the same wide body in black, with the
    chin lower in the middle, d-pad, Start, X Y Z over A B C."""
    from .nintendo_sega import btn, plus, saturn_body
    s = saturn_body("dark", chin=14)
    plus(s, 2, 4, "gray")
    s.rect(10, 9, 3, 1, "gray")
    for x in (14, 18, 22):
        btn(s, x, 4, "gray")               # X Y Z
        btn(s, x, 8, "gray")               # A B C
    return s


def tg16_pad():
    """TurboPad (Wikimedia, Evan-Amos, "NEC-TurboGrafx-16-Controller-FL"): wide black pad with the cord hump in the
    top edge, d-pad, select / run pills, the two turbo switches over the round II and I buttons."""
    from .nintendo_sega import body_from_half, btn, on, plus
    tops = [3, 2, 2, 2, 2, 2, 2, 2, 1, 0, 0, 0, 0]
    bottoms = [10, 11, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12]
    s = body_from_half(tops, bottoms, "dark")
    on(s, 9, 0, 8, 2, "dgray")             # cord hump
    plus(s, 2, 4, "gray")
    s.rect(10, 10, 2, 1, "gray")           # select / run
    s.rect(13, 10, 2, 1, "gray")
    s.rect(19, 3, 2, 2, "dgray")           # turbo switches
    s.rect(23, 3, 2, 2, "dgray")
    btn(s, 18, 6, "gray")                  # II and I
    btn(s, 22, 6, "gray")
    return s


# ---------------------------------------------------------------- registry

def both(jp_console, jp_pad, us_console, us_pad):
    return {"jp": {"console": jp_console, "pad": jp_pad}, "us": {"console": us_console, "pad": us_pad}}


_sfc_pad = ref("nintendo_sega", "sfc_pad")

VARIANTS = {
    "fc": both(ref("nintendo_sega", "fc_console"), ref("nintendo_sega", "fc_pad"), nes_console, nes_pad),
    "sfc": both(ref("nintendo_sega", "sfc_console"), _sfc_pad, snes_console, snes_pad),
    "sgb": both(ref("nintendo_sega", "sgb_console"), _sfc_pad, sgb_us_console, snes_pad),
    "md": both(ref("nintendo_sega", "md_console"), ref("nintendo_sega", "md_pad"), genesis_console, genesis_pad),
    "segacd": both(ref("nintendo_sega", "segacd_console"), ref("nintendo_sega", "md_pad"), sega_cd_console, genesis_pad),
    "32x": both(ref("nintendo_sega", "x32_console"), ref("nintendo_sega", "x32_pad"), genesis32x_console, genesis6_pad),
    "ms": both(mark3_console, mark3_pad, ref("nintendo_sega", "ms_console"), ref("nintendo_sega", "ms_pad")),
    "saturn": both(ref("nintendo_sega", "saturn_console"), ref("nintendo_sega", "saturn_pad"),
                   saturn_us_console, saturn_us_pad),
    "pce": both(ref("others", "pce_console"), ref("others", "pce_pad"), tg16_console, tg16_pad),
    "pcecd": both(pcecd_console, ref("others", "pce_pad"), tgcd_console, tg16_pad),
}

DEFAULT = {"fc": "jp", "sfc": "jp", "sgb": "jp", "md": "jp", "segacd": "jp", "32x": "jp", "ms": "us",
           "saturn": "jp", "pce": "jp", "pcecd": "jp"}

# The region used by the themes (the user's choice): the US/Western console and pad everywhere they differ.
REGION = {icon: "us" for icon in VARIANTS}
