"""Other home consoles and computers."""
from .sprite import Sprite


def keys(s, x, y, cols, rows, c, kw=2, kh=1, gx=1, gy=1):
    """A grid of small keys."""
    for r in range(rows):
        for k in range(cols):
            s.rect(x + k * (kw + gx), y + r * (kh + gy), kw, kh, c)


def cross(s, x, y, c):
    """A d-pad whose top-left is (x, y): 6 wide, 6 tall."""
    s.rect(x, y + 2, 6, 2, c)
    s.rect(x + 2, y, 2, 6, c)


def keypad(s, x, y, c, cols=3, rows=4):
    keys(s, x, y, cols, rows, c, 2, 1, 1, 1)


# --- PC Engine family -------------------------------------------------------


def pce_console():
    """PC Engine (Japan): all white box, HuCard slit on top, round recess, green power switch."""
    s = Sprite(20, 16)
    s.rrect(0, 0, 20, 16, "white", 2)
    s.rect(3, 3, 14, 1, "black")
    s.ellipse(9.5, 8, 4, 2, "gray")
    s.rect(2, 11, 3, 3, "green")
    s.rect(14, 12, 4, 2, "dgray")
    return s


def pcecd_console():
    """CD-ROM2 unit: white drive with its round lid, the dark console docked on its right."""
    s = Sprite(26, 18)
    s.rrect(12, 0, 14, 14, "dgray", 2)
    s.rect(15, 3, 8, 1, "black")
    s.rrect(0, 2, 16, 14, "white", 2)
    s.ellipse(7.5, 8.5, 5, 4, "gray")
    s.ellipse(7.5, 8.5, 1.5, 1, "dark")
    s.rrect(0, 16, 26, 2, "gray", 1)
    return s


def sgfx_console():
    """SuperGrafx (Wikimedia, "SuperGrafx-Console-Set"): wide gray body, three raised rear blocks (green switch on
    the left, card slot in the middle), a raised centre plate and a column of round bumps on each side wing."""
    s = Sprite(26, 16)
    s.rrect(0, 3, 26, 13, "dgray", 2)
    s.rrect(0, 1, 6, 5, "dgray", 1)
    s.rrect(20, 1, 6, 5, "dgray", 1)
    s.rrect(8, 0, 10, 6, "dgray", 1)
    s.rect(2, 2, 3, 2, "green")
    s.rect(10, 1, 6, 1, "black")
    s.rect(9, 7, 8, 8, "dark")
    for y in (7, 10, 13):
        s.rrect(1, y, 6, 2, "dark", 1)
        s.rrect(19, y, 6, 2, "dark", 1)
    return s


def plus(s, x, y, c):
    """A d-pad whose top-left is (x, y): 8 wide, 8 tall, bars 2 thick, arms 3 long."""
    s.rect(x, y + 3, 8, 2, c)
    s.rect(x + 3, y, 2, 8, c)


def pce_pad():
    """PC Engine pad: white slab with the cord hump on top, d-pad, select and run, and buttons II and I."""
    s = Sprite(26, 16)
    s.rrect(7, 0, 12, 4, "white", 2)
    s.rrect(0, 2, 26, 14, "white", 2)
    plus(s, 2, 5, "dgray")
    s.rect(11, 10, 2, 1, "gray")
    s.rect(14, 10, 2, 1, "gray")
    s.rect(18, 8, 3, 3, "red")
    s.rect(22, 8, 3, 3, "red")
    return s



# --- Neo Geo ---------------------------------------------------------------

def neogeo_console():
    """AES: black wedge, a wide cartridge trench across the top, a round button and the front ports."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 2)
    s.rect(3, 2, 20, 4, "black")
    s.rect(3, 6, 20, 1, "dgray")
    s.ellipse(5.5, 10.5, 2, 2, "dgray")
    s.rect(10, 9, 4, 2, "black")
    s.rect(16, 9, 4, 2, "black")
    s.rect(10, 13, 10, 1, "dgray")
    return s


def neocd_console():
    """Neo Geo CD: black top-loader, round disc lid, ribbed right side and a red light."""
    s = Sprite(26, 18)
    s.rrect(0, 0, 26, 18, "dark", 2)
    s.rrect(2, 2, 19, 11, "black", 2)
    s.ellipse(11.5, 7.5, 6, 4.5, "dgray")
    s.ellipse(11.5, 7.5, 2, 1.5, "black")
    for y in range(3, 13, 2):
        s.rect(22, y, 3, 1, "dgray")
    s.rect(4, 14, 3, 2, "red")
    s.rect(11, 15, 12, 1, "dgray")
    return s


def neogeo_stick():
    """AES arcade stick (Wikimedia, "Neo-Geo-AES-Console-Set"): all-black slab, a black ball on a round dish at the left,
    small select and start above, four black buttons in a rising arc (A lowest, D highest)."""
    s = Sprite(26, 23)
    s.rrect(0, 4, 26, 19, "dark", 3)
    s.ellipse(6, 15, 4.5, 4.5, "black")
    s.rect(5, 8, 2, 6, "black")
    s.ellipse(5.5, 6.5, 3, 3, "dgray")
    s.rect(14, 7, 3, 1, "gray")
    s.rect(19, 7, 3, 1, "gray")
    for x, y in ((11, 15), (15, 12), (19, 10), (23, 9)):
        s.rect(x, y, 3, 3, "dgray")
    return s


def neocd_pad():
    """Neo Geo CD pad: black pad, round stick ring on the left, A B C D in two offset rows, select and start."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 5)
    s.ellipse(7.5, 7.5, 4.5, 4.5, "dgray")
    s.ellipse(7.5, 7.5, 3, 3, "black")
    s.rect(5, 5, 2, 1, "dgray")
    s.rect(17, 3, 3, 3, "green")
    s.rect(21, 3, 3, 3, "blue")
    s.rect(15, 7, 3, 3, "red")
    s.rect(19, 7, 3, 3, "yellow")
    s.rect(13, 12, 3, 1, "gray")
    s.rect(17, 12, 3, 1, "gray")
    return s



# --- PlayStation -------------------------------------------------------------

def ps_console():
    """PlayStation: gray body, big round lid, the round power, open and reset buttons and the front ports."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "gray", 2)
    s.ellipse(12.5, 5.5, 6.5, 4, "dgray")
    s.ellipse(12.5, 5.5, 3, 2, "gray")
    s.rect(2, 2, 2, 2, "dgray")
    s.rect(21, 2, 3, 1, "dgray")
    s.rect(21, 4, 3, 1, "dgray")
    s.rect(3, 11, 6, 2, "black")
    s.rect(17, 11, 6, 2, "black")
    s.rect(11, 11, 4, 2, "dgray")
    return s


def ps_pad():
    """DualShock: gray pad, two grips, shoulders as the raised top corners, d-pad, four shape buttons, sticks."""
    s = Sprite(26, 20)
    s.rrect(0, 0, 9, 20, "gray", 3)
    s.rect(7, 2, 6, 12, "gray")
    s.rrect(8, 9, 4, 4, "dgray", 1)
    s.rect(10, 7, 2, 1, "dark")
    s.mirror()
    plus(s, 1, 3, "dark")
    s.rect(20, 3, 2, 2, "green")
    s.rect(20, 9, 2, 2, "blue")
    s.rect(17, 6, 2, 2, "pink")
    s.rect(23, 6, 2, 2, "red")
    return s



# --- Atari ----------------------------------------------------------------

def atari_console():
    """2600 heavy sixer: black ridged top, cartridge slot, four switches and a woodgrain front strip."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 2)
    s.rrect(0, 11, 26, 5, "brown", 2)
    s.rect(2, 12, 22, 1, "tan")
    for i in range(4):
        s.rect(13 + i * 3, 1, 2, 2, "gray")
    s.rect(2, 4, 22, 1, "dgray")
    s.rect(2, 8, 22, 1, "dgray")
    s.rect(8, 5, 10, 3, "black")
    return s


def atari5200_console():
    """5200: black body, cartridge slot in the dark top, a silver band, front vents and four controller ports."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 2)
    s.rect(6, 1, 14, 2, "black")
    s.rect(0, 4, 26, 5, "gray")
    s.rect(2, 10, 22, 1, "dgray")
    for i in range(4):
        s.rect(3 + i * 6, 12, 4, 2, "black")
    return s


def atari7800_console():
    """7800 ProSystem: black body, a slot in the top, a silver band with a red stripe and small switches."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dark", 3)
    s.rect(5, 2, 16, 2, "black")
    s.rect(0, 5, 26, 4, "gray")
    s.rect(0, 7, 26, 1, "red")
    s.rect(4, 11, 3, 1, "dgray")
    s.rect(19, 11, 3, 1, "dgray")
    return s


def joystick(base, stick, ball, buttons):
    """A side-on joystick: round ball on a shaft over a flat base; buttons is [(x, color)] on the base."""
    s = Sprite(26, 23)
    s.rect(12, 9, 2, 6, stick)
    s.ellipse(12.5, 5.5, 4.5, 4.5, ball)
    s.rrect(0, 13, 26, 10, base, 3)
    for x, c in buttons:
        s.rrect(x, 16, 4, 4, c, 1)
    return s


def cx40():
    """CX40 (Wikimedia, "Atari-2600-Joystick"): square black base, a tall tapering stick in a rubber boot, the red fire
    button at the back left corner."""
    s = Sprite(26, 23)
    s.rect(11, 0, 4, 9, "black")
    s.rrect(10, 8, 6, 4, "black", 1)
    s.rrect(0, 11, 26, 12, "dark", 3)
    s.ellipse(12.5, 12.5, 5.5, 2.5, "dgray")
    s.rrect(2, 14, 6, 4, "red", 1)
    return s


def prolin_stick():
    """7800 ProLine stick (Wikimedia, "Atari-7800-Console-Set"): black base with a silver plate, a black stick with a
    broad round cap, an orange fire button at each end."""
    s = Sprite(26, 23)
    s.rect(12, 8, 2, 6, "dgray")
    s.rrect(8, 1, 10, 8, "black", 2)
    s.rrect(0, 13, 26, 10, "dark", 3)
    s.rect(9, 17, 8, 4, "gray")
    s.rect(1, 15, 3, 5, "orange")
    s.rect(22, 15, 3, 5, "orange")
    return s


def atari5200_pad():
    """5200 pad: black slab, start, pause and reset keys, a big stick, a red fire button on each side, a keypad."""
    s = Sprite(15, 23)
    s.rrect(0, 0, 15, 23, "dark", 3)
    for x, c in ((2, "red"), (6, "yellow"), (10, "blue")):
        s.rect(x, 2, 3, 1, c)
    s.ellipse(7, 7, 4.5, 4.5, "dgray")
    s.ellipse(7, 7, 2.5, 2.5, "black")
    s.rect(0, 5, 2, 4, "red")
    s.rect(13, 5, 2, 4, "red")
    for r in range(4):
        for k in range(3):
            s.rect(2 + k * 4, 13 + r * 2, 3, 1, "gray")
    return s


def atari800_console():
    """Atari 800: cream case, ribbed top, black keys and the column of yellow console keys."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 17, "cream", 3)
    s.rect(3, 1, 20, 1, "tan")
    s.rect(3, 2, 20, 1, "gray")
    s.rect(3, 3, 20, 1, "tan")
    keys(s, 3, 6, 5, 4, "dark", 2, 1, 1, 1)
    for i in range(4):
        s.rect(20, 6 + i * 2, 3, 1, "yellow")
    s.rect(6, 14, 9, 1, "dark")
    return s


def atarist_console():
    """Atari ST: light-gray keyboard computer, a row of function keys over the key block and number pad."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "gray", 2)
    keys(s, 2, 2, 8, 1, "dgray", 2, 1, 1, 1)
    keys(s, 2, 5, 6, 3, "dgray", 2, 1, 1, 1)
    keys(s, 20, 5, 2, 3, "dgray", 2, 1, 1, 1)
    s.rect(6, 11, 10, 1, "dgray")
    return s


def atarist_mouse():
    """ST mouse: gray body, two buttons and its cable."""
    s = Sprite(16, 23)
    s.rect(7, 0, 2, 3, "dgray")
    s.rrect(0, 2, 16, 21, "gray", 4)
    for y in range(2, 12):
        for x in range(16):
            if s.g[y][x]:
                s.px(x, y, "white")
    s.rect(7, 2, 2, 10, "dgray")
    s.rect(0, 12, 16, 1, "dgray")
    return s


def jaguar_console():
    """Jaguar (Wikimedia, "Atari-Jaguar-Console-Set"): black body, a round dish under a cartridge slot, ribs at both
    sides and the red button on the front strip."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dark", 3)
    s.rect(9, 1, 8, 2, "black")
    s.ellipse(12.5, 7, 7.5, 3.5, "black")
    for y in (3, 5, 7, 9):
        s.rect(1, y, 3, 1, "dgray")
        s.rect(22, y, 3, 1, "dgray")
    s.rect(5, 11, 16, 3, "dgray")
    s.rect(11, 11, 4, 2, "red")
    return s


def jaguar_pad():
    """Jaguar pad: black, cord hump, d-pad, pause and option, A B C on an arc and the twelve-key pad below."""
    s = Sprite(26, 22)
    s.rrect(9, 0, 8, 3, "dark", 1)
    for y, left in enumerate((4, 3, 2, 1, 0, 0, 0, 0, 1, 2, 3, 4, 5, 5, 5, 5, 5, 5, 6, 7), start=2):
        s.rect(left, y, 26 - 2 * left, 1, "dark")
    plus(s, 3, 5, "gray")
    s.rect(12, 5, 2, 1, "dgray")
    s.rect(12, 7, 2, 1, "dgray")
    s.rect(22, 5, 3, 3, "orange")
    s.rect(18, 7, 3, 3, "orange")
    s.rect(14, 9, 3, 3, "orange")
    for r in range(4):
        for k in range(3):
            s.rect(8 + k * 4, 13 + r * 2, 3, 1, "gray")
    return s



# --- Coleco / Mattel / Magnavox / GCE / Fairchild ---------------------------------

def col_console():
    """ColecoVision: black wide body, open bay on the left, vents on the right and a silver front strip."""
    s = Sprite(26, 14)
    s.rrect(0, 0, 26, 14, "dark", 2)
    s.rect(2, 2, 10, 5, "black")
    for y in (2, 4, 6):
        s.rect(15, y, 9, 1, "dgray")
    s.rect(2, 9, 22, 2, "gray")
    return s


def col_pad():
    """ColecoVision controller: black handset, round silver knob on top, gray side buttons and a twelve-key pad."""
    s = Sprite(15, 23)
    s.rrect(0, 0, 15, 23, "dark", 3)
    s.ellipse(7, 5, 4.5, 4.5, "gray")
    s.ellipse(7, 5, 2.5, 2.5, "white")
    s.rect(0, 8, 2, 3, "gray")
    s.rect(13, 8, 2, 3, "gray")
    for r in range(4):
        for k in range(3):
            s.rect(2 + k * 4, 12 + r * 3, 3, 2, "white")
    return s


def itv_console():
    """Intellivision: dark brown body, two tan stripes, slot, keypad and disc on top, woodgrain front."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dark", 2)
    s.rrect(0, 9, 26, 6, "brown", 2)
    s.rect(2, 1, 22, 2, "tan")
    s.rect(3, 4, 8, 3, "black")
    keys(s, 13, 4, 3, 2, "gray", 2, 1, 1, 1)
    s.ellipse(23, 5, 1.5, 1.5, "tan")
    s.rect(2, 10, 22, 1, "tan")
    return s


def itv_pad():
    """Intellivision pad: dark body, four side buttons, a tan panel with the twelve keys, the round disc below."""
    s = Sprite(16, 23)
    s.rrect(0, 0, 16, 23, "dark", 3)
    s.rect(0, 2, 2, 3, "gray")
    s.rect(14, 2, 2, 3, "gray")
    s.rect(0, 8, 2, 3, "gray")
    s.rect(14, 8, 2, 3, "gray")
    s.rect(3, 1, 10, 13, "tan")
    for r in range(4):
        for k in range(3):
            s.rect(4 + k * 3, 2 + r * 3, 2, 2, "dark")
    s.ellipse(7.5, 18, 4.5, 3.5, "tan")
    s.ellipse(7.5, 18, 2, 1.5, "brown")
    return s


def ody_console():
    """Odyssey 2 (Wikimedia, "Magnavox-Odyssey2-Console-BR"): silver top with the black cartridge bay and its red tab,
    a flat black keyboard panel with its rows of keys, a black lower body."""
    s = Sprite(26, 17)
    s.rrect(0, 0, 26, 6, "gray", 3)
    s.rect(0, 3, 26, 10, "gray")
    s.rrect(0, 11, 26, 6, "dark", 3)
    s.rect(0, 11, 26, 2, "dark")
    s.rect(3, 1, 20, 3, "black")
    s.rect(18, 2, 3, 1, "red")
    s.rect(2, 5, 22, 7, "black")
    keys(s, 3, 6, 7, 3, "dgray", 2, 1, 1, 1)
    return s


def ody_stick():
    """Odyssey 2 stick (Wikimedia, "Magnavox-Odyssey2-Console-BR"): a black box with a short black stick in a round
    collar and a red tab at the back corner."""
    s = Sprite(26, 23)
    s.rect(12, 1, 2, 10, "black")
    s.rect(11, 0, 4, 2, "black")
    s.rrect(0, 9, 26, 14, "dark", 3)
    s.ellipse(12.5, 13, 5.5, 3, "dgray")
    s.rect(2, 11, 5, 3, "red")
    return s


def vectrex_console():
    """Vectrex (Wikimedia, "Vectrex-Console-Set"): tall black cabinet, a hood over the pale gray screen glass and
    the recessed control deck with its vents."""
    s = Sprite(20, 23)
    s.rrect(0, 0, 20, 5, "dark", 1)
    s.rrect(1, 4, 18, 19, "dark", 3)
    s.rrect(3, 5, 14, 11, "gray", 3)
    s.rect(3, 18, 14, 1, "dgray")
    s.rect(4, 20, 4, 2, "dgray")
    s.rect(10, 20, 6, 2, "dgray")
    return s


def vectrex_pad():
    """Vectrex controller (Wikimedia, "Vectrex-Console-Set"): black slab, a small stick with a cream tip on a round
    collar at the left, a pale stripe and four round buttons in a row."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 3)
    s.ellipse(5.5, 7.5, 3.5, 3.5, "black")
    s.rect(5, 7, 2, 2, "cream")
    s.rect(1, 12, 24, 1, "dgray")
    for x in (10, 14, 18, 22):
        s.rect(x, 4, 3, 3, "dgray")
    return s


def fairchild_console():
    """Channel F (Wikimedia, "Fairchild-Channel-F"): a dark sloping top over a front strip with the yellow reset and four
    cream buttons at the left and the cartridge slot at the right, woodgrain base."""
    s = Sprite(26, 15)
    s.rrect(0, 0, 26, 15, "dark", 2)
    s.rrect(0, 11, 26, 4, "brown", 2)
    s.rect(2, 8, 2, 2, "yellow")
    for i in range(4):
        s.rect(5 + i * 3, 8, 2, 2, "cream")
    s.rect(15, 6, 9, 4, "black")
    s.rect(16, 7, 7, 1, "dgray")
    s.rect(2, 2, 22, 1, "dgray")
    return s


def fairchild_stick():
    """Channel F controller (Wikimedia, "Fairchild-Channel-F"): a ridged black barrel with a disc-shaped knob on its end."""
    s = Sprite(26, 16)
    s.rrect(0, 3, 21, 10, "dark", 2)
    for x in range(3, 18, 2):
        s.rect(x, 5, 1, 6, "dgray")
    s.rect(21, 7, 2, 2, "dgray")
    s.rrect(22, 1, 4, 14, "black", 1)
    return s



# --- Computers ---------------------------------------------------------------

def msx_console():
    """MSX (Wikimedia, Sony HB-10P): black keyboard computer, a cartridge slot on top, light keys, red STOP key and the cursor keys."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "dark", 3)
    s.rect(3, 2, 20, 2, "black")
    keys(s, 3, 6, 5, 2, "gray", 2, 1, 1, 1)
    s.rect(19, 6, 2, 1, "red")
    s.rect(21, 8, 2, 1, "gray")
    s.rect(19, 8, 2, 1, "gray")
    s.rect(6, 11, 12, 2, "gray")
    return s


def msx_stick():
    """MSX stick: a plain two-button joystick (no single canonical model)."""
    return joystick("gray", "dgray", "dark", [(2, "red"), (20, "red")])


def c64_console():
    """Commodore 64: beige-brown 'breadbin' with brown keys, the function key column and a long space bar."""
    s = Sprite(26, 16)
    s.rrect(0, 0, 26, 16, "tan", 3)
    s.rect(3, 2, 20, 1, "cream")
    keys(s, 3, 5, 6, 3, "brown", 2, 1, 1, 1)
    for i in range(3):
        s.rect(21, 5 + i * 2, 2, 1, "brown")
    s.rect(6, 12, 12, 1, "brown")
    s.rect(3, 14, 2, 1, "red")
    return s


def competition_pro():
    """Competition Pro (icomp.de photo "Compproretro420"): black base, red stick with a red ball, a big round red fire
    button at the left and two small red buttons at the right."""
    s = Sprite(26, 23)
    s.rect(12, 8, 2, 6, "red")
    s.ellipse(12.5, 5.5, 4.5, 4.5, "red")
    s.rrect(0, 13, 26, 10, "dark", 3)
    s.rrect(2, 15, 6, 6, "red", 2)
    s.rect(21, 15, 3, 3, "red")
    s.rect(21, 19, 3, 3, "red")
    return s


def pc98_console():
    """PC-9801 (Wikimedia, "PC-9801 computer set" and "NEC PC-9801VM Front"): a beige CRT on the wide main unit, a vent
    grille at the left and two floppy slots stacked at the right."""
    s = Sprite(26, 22)
    s.rrect(3, 0, 20, 11, "cream", 2)
    s.rrect(5, 2, 16, 7, "black", 1)
    s.rrect(0, 12, 26, 10, "cream", 2)
    for y in (14, 16, 18, 20):
        s.rect(2, y, 10, 1, "tan")
    s.rect(15, 14, 9, 1, "black")
    s.rect(15, 18, 9, 1, "black")
    return s


def pc98_keyboard():
    """PC-9800 keyboard (Wikimedia, "NEC PC-9800 series keyboard"): a long pale slab, a row of function keys, the main
    block, a darker cursor and number block and a space bar."""
    s = Sprite(26, 12)
    s.rrect(0, 0, 26, 12, "white", 2)
    keys(s, 2, 2, 8, 1, "gray", 2, 1, 1, 1)
    keys(s, 2, 4, 5, 3, "gray", 2, 1, 1, 1)
    keys(s, 17, 4, 2, 3, "dgray", 2, 1, 1, 1)
    keys(s, 21, 4, 1, 3, "dgray", 2, 1, 1, 1)
    s.rect(5, 10, 10, 1, "gray")
    return s



SHARED = {}
CONSOLES = {
    "pce": pce_console, "pcecd": pcecd_console, "sgfx": sgfx_console,
    "neogeo": neogeo_console, "neocd": neocd_console, "ps": ps_console,
    "atari": atari_console, "5200": atari5200_console, "7800": atari7800_console,
    "atari800": atari800_console, "atarist": atarist_console, "jaguar": jaguar_console,
    "col": col_console, "itv": itv_console, "ody": ody_console, "vectrex": vectrex_console,
    "fairchild": fairchild_console, "msx": msx_console, "c64": c64_console, "pc98": pc98_console,
}
CONTROLLERS = {
    "pce": pce_pad, "pcecd": pce_pad, "sgfx": pce_pad,
    "neogeo": neogeo_stick, "neocd": neocd_pad, "ps": ps_pad,
    "atari": cx40, "5200": atari5200_pad, "7800": prolin_stick,
    "atari800": cx40, "atarist": atarist_mouse, "jaguar": jaguar_pad,
    "col": col_pad, "itv": itv_pad, "ody": ody_stick, "vectrex": vectrex_pad,
    "fairchild": fairchild_stick, "msx": msx_stick, "c64": competition_pro, "pc98": pc98_keyboard,
}
