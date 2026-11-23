"""Pixel replacements for base-theme icons: ICONS = {path inside the theme: draw fn returning a Sprite}.

The Apps menu icons (`icons/app/<name>.png`, 70x70 in the base theme): sprites of at most 20x20 cells. An app's icon
is the `icon` in its spruceOS `App/<app>/config.json`; one the base theme lacks is drawn at APP_SIZE."""
from .sprite import Sprite

APP_SIZE = (70, 70)


def _rot180(s):
    """Overlay a half-turned copy of the sprite on itself."""
    old = [row[:] for row in s.g]
    for y in range(s.h):
        for x in range(s.w):
            if old[y][x]:
                s.g[s.h - 1 - y][s.w - 1 - x] = old[y][x]


def _triangle(s, cx, y, widths, c):
    """Rows of the given (even) widths centered on column pair cx-1/cx."""
    for i, w in enumerate(widths):
        s.rect(cx - w // 2, y + i, w, 1, c)


def _hill(s, peak_x, peak_y, bottom_y, c, x0, x1):
    for y in range(peak_y, bottom_y + 1):
        half = y - peak_y
        for x in range(peak_x - half, peak_x + half + 1):
            if x0 <= x <= x1:
                s.px(x, y, c)


def _loop(color):
    """Two arrows chasing each other round a square (a refresh symbol); the middle is left for the caller."""
    s = Sprite(20, 20)
    s.rect(2, 2, 12, 3, color)
    s.rect(2, 2, 3, 8, color)
    for x, (a, b) in zip(range(14, 18), ((0, 6), (1, 5), (2, 4), (3, 3))):
        s.rect(x, a, 1, b - a + 1, color)
    _rot180(s)
    return s


def _disc(s, cy, c, top):
    s.ellipse(9.5, cy + 4, 9.5, 2.6, c)
    s.rect(0, cy, 20, 4, c)
    s.ellipse(9.5, cy, 9.5, 2.6, top)


def ssh():
    s = Sprite(20, 18)
    s.rrect(0, 0, 20, 18, "dark", 2)
    s.rrect(0, 0, 20, 5, "blue", 2)
    for x in (3, 5, 7):
        s.px(x, 2, "white")
    s.art(3, 7, ["XX..", ".XX.", "..XX", ".XX.", "XX.."], {"X": "green"})
    s.rect(9, 11, 6, 2, "green")
    return s


def backup():
    s = Sprite(20, 20)
    s.rrect(0, 0, 20, 20, "blue", 2)
    s.rect(5, 0, 10, 7, "gray")
    s.rect(11, 1, 2, 4, "dark")
    s.rect(3, 11, 14, 9, "white")
    s.rect(5, 13, 10, 1, "gray")
    s.rect(5, 16, 10, 1, "gray")
    return s


def bootlogo():
    s = Sprite(20, 20)
    s.rrect(0, 0, 20, 15, "gray", 2)
    s.rect(2, 2, 16, 11, "dark")
    s.ellipse(9.5, 7.5, 3.6, 3.6, "green")
    s.ellipse(9.5, 7.5, 1.8, 1.8, "dark")
    s.rect(8, 4, 4, 2, "dark")
    s.rect(9, 3, 2, 5, "green")
    s.rect(8, 15, 4, 2, "gray")
    s.rrect(5, 17, 10, 3, "gray", 1)
    return s


def cheevos():
    s = Sprite(20, 16)
    s.art(0, 0, [
        "..XXXXXXXX",
        "XXXXXXXXXX",
        "X.XXXXXXXX",
        "X.XXXXXXXX",
        "XXXXXXXXXX",
        "..XXXXXXXX",
        "...XXXXXXX",
        "....XXXXXX",
        ".....XXXXX",
        "......XXXX",
        ".......XXX",
        ".......XXX",
        ".......XXX",
    ], {"X": "yellow"})
    s.art(0, 13, ["....XXXXXX", "...XXXXXXX", "...XXXXXXX"], {"X": "orange"})
    s.mirror()
    s.rect(4, 2, 2, 3, "white")
    return s


def emufresh():
    s = _loop("green")
    s.rrect(6, 7, 8, 6, "gray", 1)
    s.rect(7, 10, 3, 1, "white")
    s.rect(8, 9, 1, 3, "white")
    s.px(11, 9, "red")
    s.px(12, 11, "cyan")
    return s


def ereader():
    s = Sprite(20, 20)
    s.rrect(0, 2, 20, 17, "blue", 2)
    s.rect(2, 4, 7, 13, "cream")
    for y in (6, 8, 10, 12):
        s.rect(3, y, 5, 1, "gray")
    s.mirror()
    s.rect(9, 16, 2, 4, "red")
    return s


def expertappswitch():
    s = Sprite(20, 16)
    s.art(0, 0, [
        "...XXXXXXX",
        "..XXXXXXXX",
        ".XXXXXXXXX",
        "XXXXXXXXXX",
        "XXXXXXXXXX",
        ".XXXXXXXXX",
        "..XXXXXXXX",
        "...XXXXXXX",
        "....XXXXXX",
        ".....XXXXX",
        "......XXXX",
        ".......XXX",
        "........XX",
        ".........X",
    ], {"X": "blue"})
    s.art(0, 0, ["...XXXXXXX", "..XXXXXXXX", ".XXXXXXXXX", "XXXXXXXXXX"], {"X": "cyan"})
    s.mirror()
    s.rect(4, 1, 2, 1, "white")
    return s


def file():
    s = Sprite(20, 20)
    s.rect(0, 2, 8, 3, "orange")
    s.rrect(0, 4, 20, 15, "orange", 1)
    for k in (0, 1):
        s.line(14 + k, 14, 18 + k, 18, "dark")
    s.ellipse(10.5, 10.5, 5.6, 5.6, "white")
    s.ellipse(10.5, 10.5, 3.4, 3.4, "sky")
    return s


def firmwareupdate():
    s = Sprite(20, 20)
    _triangle(s, 10, 0, (2, 4, 6, 8), "yellow")
    s.rect(8, 4, 4, 3, "yellow")
    s.rect(1, 10, 3, 2, "gray")
    s.rect(1, 15, 3, 2, "gray")
    s.rrect(4, 8, 12, 12, "teal", 2)
    s.rect(7, 11, 6, 6, "dark")
    s.mirror()
    return s


def fnkey():
    s = Sprite(20, 20)
    s.rrect(0, 0, 20, 20, "dgray", 3)
    s.rrect(2, 1, 16, 15, "gray", 2)
    s.rect(4, 5, 9, 2, "orange")
    for x, (a, b) in zip(range(13, 16), ((3, 8), (4, 7), (5, 6))):
        s.rect(x, a, 1, b - a + 1, "orange")
    s.rect(7, 10, 9, 2, "white")
    for x, (a, b) in zip(range(6, 3, -1), ((8, 13), (9, 12), (10, 11))):
        s.rect(x, a, 1, b - a + 1, "white")
    return s


def gallery():
    s = Sprite(20, 18)
    s.rrect(0, 0, 20, 18, "white", 2)
    s.rect(2, 2, 16, 14, "sky")
    s.ellipse(13.5, 6.5, 2.4, 2.4, "yellow")
    _hill(s, 6, 7, 15, "forest", 2, 17)
    _hill(s, 13, 10, 15, "green", 2, 17)
    return s


def gamelist():
    s = Sprite(20, 20)
    s.rrect(0, 0, 15, 20, "white", 2)
    for y in (3, 8, 13):
        s.rect(2, y, 2, 2, "orange")
        s.rect(5, y, 4, 2, "dgray")
    for t in range(11):
        cx, cy = 17 - t, 2 + t
        if t < 8:
            c = "pink" if t < 2 else "yellow"
            for x in (cx - 1, cx, cx + 1):
                s.px(x, cy, c)
        elif t < 10:
            for x in ((cx - 1, cx, cx + 1) if t == 8 else (cx,)):
                s.px(x, cy, "tan")
        else:
            s.px(cx, cy, "dark")
    return s


def iconfresh():
    s = _loop("orange")
    for (x, y), c in zip(((6, 7), (11, 7), (6, 10), (11, 10)), ("pink", "cyan", "green", "yellow")):
        s.rect(x, y, 3, 2, c)
    return s


def led():
    s = Sprite(20, 20)
    s.rect(6, 14, 8, 2, "yellow")
    s.ellipse(9.5, 8.5, 6.6, 6.6, "yellow")
    s.rect(6, 16, 8, 2, "gray")
    s.rect(7, 18, 6, 2, "dgray")
    s.rect(0, 8, 2, 2, "orange")
    s.px(2, 1, "orange")
    s.px(3, 2, "orange")
    s.rect(5, 5, 2, 3, "white")
    s.mirror()
    return s


def menuswitch():
    s = Sprite(20, 20)
    for y in (0, 4, 8):
        s.rect(0, y, 2, 2, "orange")
        s.rect(4, y, 14, 2, "white")
    s.rrect(0, 12, 20, 8, "green", 4)
    s.ellipse(15.5, 15.5, 3.4, 3.4, "white")
    return s


def moonlight():
    s = Sprite(20, 20)
    s.ellipse(8.5, 10.5, 8.5, 8.5, "yellow")
    s.ellipse(12.5, 8.5, 7, 7, None)
    s.rect(15, 4, 3, 1, "white")
    s.rect(16, 3, 1, 3, "white")
    s.rect(17, 13, 2, 2, "white")
    return s


def pico8():
    s = Sprite(19, 19)
    names = ("dark", "navy", "magenta", "forest", "brown", "dgray", "gray", "white",
             "red", "orange", "yellow", "green", "blue", "periwinkle", "pink", "tan")
    for i, c in enumerate(names):
        s.rrect((i % 4) * 5, (i // 4) * 5, 4, 4, c, 1)
    return s


def portmaster():
    s = Sprite(20, 20)
    s.rect(13, 1, 2, 3, "red")
    s.rect(11, 4, 6, 7, "white")
    s.rect(13, 6, 2, 2, "sky")
    s.rect(1, 7, 4, 4, "cyan")
    s.rect(5, 7, 4, 4, "orange")
    s.rect(3, 3, 4, 4, "yellow")
    s.art(0, 11, [
        "XXXXXXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXXXXXX",
        ".XXXXXXXXXXXXXXXXXX.",
        "..XXXXXXXXXXXXXXXX..",
        "...XXXXXXXXXXXXXX...",
    ], {"X": "red"})
    for x in (0, 8, 16):
        s.rect(x, 17, 4, 1, "cyan")
    for x in (4, 12):
        s.rect(x, 18, 4, 1, "cyan")
    return s


def ppsspp():
    s = Sprite(20, 12)
    s.rrect(0, 0, 20, 12, "dgray", 2)
    s.rect(6, 1, 8, 10, "screen")
    s.rect(3, 3, 2, 6, "white")
    s.rect(2, 5, 4, 2, "white")
    s.mirror()
    s.rect(14, 3, 5, 6, "dgray")
    s.px(16, 4, "green")
    s.px(14, 6, "blue")
    s.px(18, 6, "red")
    s.px(16, 8, "pink")
    return s


def random():
    s = Sprite(20, 20)
    s.rrect(0, 0, 20, 20, "red", 3)
    for x, y in ((3, 3), (3, 13)):
        s.rrect(x, y, 4, 4, "white", 1)
    s.rrect(8, 8, 4, 4, "white", 1)
    s.mirror()
    return s


def recents():
    s = Sprite(20, 18)
    s.rrect(0, 0, 20, 18, "indigo", 2)
    for x0 in (2, 11):
        for y in range(12):
            left = x0 + 5 - min(y, 11 - y)
            s.rect(left, 3 + y, x0 + 8 - left, 1, "white")
    return s


def restore():
    s = Sprite(20, 20)
    _triangle(s, 10, 0, (2, 4, 6, 8), "lime")
    s.rect(8, 4, 4, 4, "lime")
    _disc(s, 15, "teal", "cyan")
    _disc(s, 10, "teal", "cyan")
    return s


def retroarch():
    s = Sprite(20, 20)
    s.rect(9, 9, 2, 6, "gray")
    s.ellipse(9.5, 4.5, 4.6, 4.6, "red")
    s.rect(6, 2, 2, 2, "white")
    s.rrect(1, 14, 18, 6, "dgray", 1)
    s.rect(4, 16, 2, 2, "yellow")
    s.rect(14, 16, 2, 2, "green")
    return s


def retroexpert():
    s = Sprite(18, 10)
    s.art(0, 0, [
        "..X......",
        "...X.....",
        "..XXXXXXX",
        ".XXXXXXXX",
        "XXX..XXXX",
        "XXX..XXXX",
        "XXXXXXXXX",
        "X.XXXXXXX",
        "X.X......",
        "...XX....",
    ], {"X": "green"})
    s.mirror()
    return s


def rtc():
    s = Sprite(20, 20)
    s.ellipse(3.5, 3.5, 3.2, 3.2, "yellow")
    s.ellipse(9.5, 11, 8.6, 8.6, "red")
    s.ellipse(9.5, 11, 6.4, 6.4, "cream")
    s.mirror()
    s.rect(9, 6, 2, 6, "dark")
    s.rect(9, 10, 5, 2, "dark")
    return s


def scraper():
    s = Sprite(20, 18)
    s.ellipse(5, 11.5, 4.6, 4.6, "white")
    s.ellipse(9.5, 7.5, 6.6, 6.6, "white")
    s.rect(2, 11, 16, 6, "white")
    s.mirror()
    s.rect(8, 4, 4, 5, "blue")
    _triangle(s, 10, 9, (10, 8, 6, 4, 2), "blue")
    return s


def songo():
    """Songo#5, the music player: two beamed eighth notes."""
    s = Sprite(20, 20)
    s.rect(6, 1, 13, 3, "pink")
    s.rect(6, 1, 2, 15, "pink")
    s.rect(17, 1, 2, 13, "pink")
    s.ellipse(4.5, 16.5, 3.5, 2.6, "pink")
    s.ellipse(15.5, 14.5, 3.5, 2.6, "pink")
    return s


def sftpgo():
    s = Sprite(20, 20)
    for y, c in ((0, "periwinkle"), (7, "periwinkle"), (14, "periwinkle")):
        s.rrect(0, y, 20, 6, c, 1)
        s.rect(2, y + 2, 2, 2, "green")
        s.rect(5, y + 2, 2, 2, "orange")
        s.rect(10, y + 2, 8, 2, "dgray")
    return s


def syncthing():
    s = Sprite(20, 20)
    for y in range(5, 15):
        s.rect(8 - (y - 4) // 2, y, 2, 1, "blue")
    s.rect(3, 14, 14, 2, "blue")
    s.ellipse(9.5, 3.5, 3.4, 3.4, "cyan")
    s.ellipse(3.5, 15.5, 3.4, 3.4, "cyan")
    s.mirror()
    return s


def themegallery():
    s = Sprite(20, 18)
    s.ellipse(9.5, 8.5, 9.6, 8.6, "tan")
    s.ellipse(12.5, 13.5, 2.6, 2.6, None)
    for (x, y), c in (((3, 7), "red"), ((6, 3), "yellow"), ((12, 3), "green"), ((15, 7), "blue")):
        s.rrect(x, y, 3, 3, c, 1)
    return s


def updater():
    s = Sprite(20, 20)
    s.ellipse(9.5, 9.5, 9.6, 9.6, "green")
    _triangle(s, 10, 3, (2, 4, 6, 8, 10), "white")
    s.rect(8, 8, 4, 8, "white")
    return s


def usb():
    s = Sprite(20, 20)
    s.rect(5, 0, 10, 6, "gray")
    s.rect(7, 2, 2, 2, "dark")
    s.rrect(3, 6, 14, 14, "blue", 1)
    s.rect(5, 10, 10, 2, "white")
    s.rect(9, 15, 2, 2, "green")
    s.mirror()
    return s


def zitch():
    s = Sprite(20, 18)
    s.rrect(0, 0, 20, 10, "indigo", 3)
    s.rrect(0, 6, 7, 12, "indigo", 2)
    s.rect(3, 6, 6, 2, "white")
    s.rect(5, 4, 2, 6, "white")
    s.mirror()
    s.rect(11, 3, 6, 8, "indigo")
    for x, y, c in ((13, 4, "green"), (13, 8, "yellow"), (11, 6, "blue"), (15, 6, "red")):
        s.rect(x, y, 2, 2, c)
    return s


ICONS = {f"icons/app/{fn.__name__.upper() if fn is ssh else fn.__name__}.png": fn for fn in (
    ssh, backup, bootlogo, cheevos, emufresh, ereader, expertappswitch, file, firmwareupdate, fnkey, gallery,
    gamelist, iconfresh, led, menuswitch, moonlight, pico8, portmaster, ppsspp, random, recents, restore,
    retroarch, retroexpert, rtc, scraper, songo, sftpgo, syncthing, themegallery, updater, usb, zitch)}
