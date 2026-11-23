"""Pixel replacements for base-theme icons: ICONS = {path inside the theme: draw fn returning a Sprite}."""
from math import hypot

from .sprite import Sprite


def half(rows, legend):
    """A sprite from its left half (ASCII rows), mirrored."""
    s = Sprite(len(rows[0]) * 2, len(rows))
    s.art(0, 0, rows, legend)
    s.mirror()
    return s


def ring(s, cx, cy, ro, ri, c, keep=lambda x, y: True):
    """Filled ring (or arc, with keep) between radii ri and ro around (cx, cy), in pixel-center coordinates."""
    for y in range(s.h):
        for x in range(s.w):
            if ri < hypot(x - cx, y - cy) <= ro and keep(x, y):
                s.px(x, y, c)


def over(s, x, y, w, h, c):
    """Paint c only on pixels the sprite already has."""
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < s.w and 0 <= yy < s.h and s.g[yy][xx]:
                s.g[yy][xx] = c


def fixit():
    s = Sprite(18, 18)
    for dx in (0, 1, 2):                     # handle: three pixels wide along a 1:1 diagonal
        s.line(dx, 17, 9 + dx, 8, "gray")
    s.ellipse(11.5, 6.5, 5.2, 5.2, "gray")
    for y in range(s.h):                     # the jaw's notch, a 3-wide channel toward the top-right corner
        for x in range(s.w):
            if x >= 11 and y <= 6 and 17 <= x + y <= 19:
                s.g[y][x] = None
    return s


def brightness():
    s = Sprite(18, 18)
    s.ellipse(8.5, 8.5, 4.3, 4.3, "yellow")
    for x, y, w, h in ((8, 0, 2, 3), (8, 15, 2, 3), (0, 8, 3, 2), (15, 8, 3, 2)):
        s.rect(x, y, w, h, "orange")
    for x, y in ((2, 2), (14, 2), (2, 14), (14, 14)):
        s.rect(x, y, 2, 2, "orange")
    return s


def device_info():
    s = Sprite(18, 18)
    s.ellipse(8.5, 8.5, 8.6, 8.6, "blue")
    s.rect(8, 3, 2, 2, "white")
    s.rect(8, 7, 2, 7, "white")
    s.rect(6, 7, 3, 2, "white")
    s.rect(6, 13, 6, 2, "white")
    return s


def factory_reset():
    s = Sprite(18, 18)
    ring(s, 8.5, 10.5, 7.5, 4.5, "orange", lambda x, y: not (9 <= x <= 13 and y <= 9))
    s.art(8, 1, [
        "X......",
        "XXX....",
        "XXXXX..",
        "XXXXXXX",
        "XXXXX..",
        "XXX....",
        "X......",
    ], {"X": "orange"})
    return s


def key_setting():
    s = Sprite(18, 18)
    s.rrect(0, 3, 18, 12, "indigo", 2)
    s.rect(5, 12, 8, 3, None)
    s.rect(2, 7, 5, 1, "white")
    s.rect(4, 5, 1, 5, "white")
    s.rect(12, 6, 2, 2, "white")
    s.rect(14, 9, 2, 2, "white")
    return s


def language():
    s = Sprite(18, 18)
    s.ellipse(8.5, 8.5, 8.6, 8.6, "blue")
    over(s, 0, 8, 18, 2, "sky")
    over(s, 8, 0, 2, 18, "sky")
    over(s, 0, 4, 18, 1, "sky")
    over(s, 0, 13, 18, 1, "sky")
    return s


def wifi():
    return half([
        "...XXXXXX",
        ".XXXXXXXX",
        "XXXX.....",
        "XXX......",
        "....XXXXX",
        "..XXXXXXX",
        "..XXX....",
        ".........",
        ".......XX",
        "......XXX",
        "......XXX",
        ".......XX",
    ], {"X": "green"})


def shutdown():
    s = Sprite(18, 18)
    ring(s, 8.5, 9.5, 8.6, 5.6, "red", lambda x, y: not (5.5 <= x <= 11.5 and y <= 7))
    s.rect(8, 0, 2, 10, "red")
    return s


def bluetooth():
    s = Sprite(14, 17)
    for dx in (0, 1, 2):
        s.line(5 + dx, 0, 9 + dx, 4, "blue")
        s.line(9 + dx, 4, 1 + dx, 12, "blue")
        s.line(5 + dx, 16, 9 + dx, 12, "blue")
        s.line(9 + dx, 12, 1 + dx, 4, "blue")
    s.rect(5, 0, 3, 17, "blue")
    return s


def joystick():
    s = Sprite(18, 18)
    s.ellipse(8.5, 4.5, 4.4, 4.4, "red")
    s.rect(8, 8, 2, 5, "gray")
    s.rrect(0, 12, 18, 6, "dgray", 1)
    return s


def headphone():
    s = Sprite(18, 18)
    s.ellipse(8.5, 8.5, 8.6, 8.6, "gray")
    s.ellipse(8.5, 8.5, 5.6, 5.6, None)
    s.rect(0, 9, 18, 9, None)
    s.rrect(0, 8, 5, 10, "blue", 1)
    s.mirror()
    return s


def hotspot():
    return half([
        "...XX....",
        "..XX.....",
        ".XX..XX..",
        ".XX.XX...",
        "XX..XX...",
        "XX..XX...",
        "XX..XX...",
        "XX..XX..X",
        "XX..XX.XX",
        "XX..XX.XX",
        "XX..XX..X",
        "XX..XX...",
        "XX..XX...",
        ".XX.XX...",
        ".XX..XX..",
        "..XX.....",
        "...XX....",
    ], {"X": "cyan"})


def joystick_calibrate():
    s = Sprite(18, 18)
    s.ellipse(8.5, 8.5, 3.3, 3.3, "red")
    arrow = ["..XX..", ".XXXX.", "XXXXXX"]
    s.art(6, 0, arrow, {"X": "green"})
    s.art(6, 15, arrow[::-1], {"X": "green"})
    for y in range(6):
        for x in range(3):
            if arrow[x][y] == "X":
                s.px(x, 6 + y, "green")
                s.px(17 - x, 6 + y, "green")
    return s


def vibrate():
    s = Sprite(18, 18)
    s.rrect(5, 0, 8, 18, "green", 2)
    s.rect(6, 2, 6, 12, "dark")
    s.rect(8, 15, 2, 1, "dark")
    for i, y in enumerate(range(3, 15)):
        x = (0, 1, 2, 1)[i % 4]
        s.rect(x, y, 2, 1, "cyan")
        s.rect(16 - x, y, 2, 1, "cyan")
    return s


def usb():
    s = Sprite(14, 18)
    s.rect(3, 0, 8, 6, "gray")
    s.rect(4, 2, 2, 2, "dark")
    s.rect(8, 2, 2, 2, "dark")
    s.rrect(1, 6, 12, 8, "blue", 1)
    s.rect(6, 14, 2, 4, "blue")
    return s


def remove_sdcard():
    s = Sprite(18, 18)
    s.rrect(3, 0, 12, 18, "blue", 1)
    for k in range(3):
        s.rect(11 + k, k * 0, 1, 1, None)
    s.rect(12, 0, 3, 1, None)
    s.rect(13, 1, 2, 1, None)
    s.rect(14, 2, 1, 1, None)
    for x in (5, 7, 9):
        s.rect(x, 1, 1, 3, "yellow")
    s.art(6, 8, ["..XX..", ".XXXX.", "XXXXXX"], {"X": "white"})
    s.rect(6, 12, 6, 2, "white")
    return s


def tf():
    s = Sprite(8, 10)
    s.rrect(0, 0, 8, 10, "blue", 1)
    s.rect(6, 0, 2, 1, None)
    s.rect(7, 1, 1, 1, None)
    for x in (1, 3, 5):
        s.rect(x, 1, 1, 2, "yellow")
    return s


def trigger():
    s = Sprite(18, 18)
    ring(s, 8.5, 8.5, 8.5, 5.5, "green", lambda x, y: abs(y - 8.5) > 1.6)
    head = ["XXXXX", ".XXX.", "..X.."]
    for j, row in enumerate(head):
        for i, ch in enumerate(row):
            if ch == "X":
                s.px(13 + i, 6 + j, "green")
                s.px(17 - 13 - i, 17 - 6 - j, "green")
    return s


def folder():
    s = Sprite(22, 18)
    s.rect(0, 0, 9, 3, "orange")
    s.rrect(0, 2, 22, 16, "orange", 1)
    return s


STAR = [
    "........X",
    "........X",
    ".......XX",
    ".......XX",
    "......XXX",
    "XXXXXXXXX",
    ".XXXXXXXX",
    "..XXXXXXX",
    "...XXXXXX",
    "....XXXXX",
    "...XXXXXX",
    "...XXXXXX",
    "..XXXXXX.",
    "..XXXXX..",
    ".XXXXX...",
    ".XXXX....",
]


def favorite():
    return half(STAR, {"X": "yellow"})


def cheevos():
    return half([
        "..XXXXXXX",
        "..XXXXXXX",
        "XXXXXXXXX",
        "X.XXXXXXX",
        "X.XXXXXXX",
        "XXXXXXXXX",
        "..XXXXXXX",
        "...XXXXXX",
        "....XXXXX",
        ".......XX",
        ".......XX",
        "......XXX",
        "....XXXXX",
        "...XXXXXX",
    ], {"X": "yellow"})


def collection_green():
    s = Sprite(22, 28)           # the folder sits where the menu icons do, high on the 100x140 canvas
    s.rect(0, 0, 9, 3, "green")
    s.rrect(0, 2, 22, 16, "green", 1)
    s.art(7, 5, [
        "....XX....",
        "....XX....",
        "XXXXXXXXXX",
        ".XXXXXXXX.",
        "..XXXXXX..",
        "..XXXXXX..",
        ".XXX..XXX.",
        ".XX....XX.",
    ], {"X": "yellow"})
    return s


def empty():
    s = Sprite(22, 20)
    s.rect(0, 0, 22, 6, "cream")
    s.rect(2, 1, 18, 3, "dark")
    s.rrect(1, 6, 20, 14, "tan", 1)
    s.rect(5, 10, 2, 3, "dark")
    s.rect(15, 10, 2, 3, "dark")
    s.rect(5, 13, 1, 2, "cyan")
    s.rect(9, 15, 4, 1, "dark")
    s.rect(8, 16, 1, 1, "dark")
    s.rect(13, 16, 1, 1, "dark")
    s.rect(2, 14, 2, 1, "pink")
    s.rect(18, 14, 2, 1, "pink")
    return s


def missing_image():
    s = Sprite(40, 32)
    s.rrect(0, 0, 40, 32, "gray", 2)
    s.rect(3, 3, 34, 26, "sky")
    s.ellipse(29.5, 9.5, 3.6, 3.6, "yellow")
    for k in range(13):                      # mountains: 1:1 slopes
        s.rect(13 - k, 15 + k, 2 * k + 2, 1, "forest")
    for k in range(10):
        s.rect(27 - k, 19 + k, 2 * k + 2, 1, "green")
    for y in range(29, 32):
        s.rect(0, y, 40, 1, "gray")
    return s


def menu():
    s = Sprite(18, 16)
    for k in range(8):
        s.rect(8 - k, k, 2 * k + 2, 1, "red")
    s.rect(2, 8, 14, 8, "cream")
    s.rect(7, 11, 4, 5, "brown")
    return s


def menu_a():
    s = Sprite(50, 18)
    for k in range(8):
        s.rect(7 - k, 1 + k, 2 * k + 2, 1, "red")
    s.rect(1, 9, 14, 8, "cream")
    s.rect(6, 12, 4, 5, "brown")
    s.rect(23, 5, 2, 8, "white")
    s.rect(20, 8, 8, 2, "white")
    s.ellipse(40.5, 8.5, 8.6, 8.6, "gray")
    s.ellipse(40.5, 8.5, 6.2, 6.2, "white")
    s.art(38, 6, [
        ".XX.",
        ".XX.",
        "X..X",
        "XXXX",
        "X..X",
        "X..X",
    ], {"X": "dark"})
    return s


ICONS = {
    "skin/fixit.png": fixit,
    "skin/icon-brightness-48.png": brightness,
    "skin/icon-device-info-48.png": device_info,
    "skin/icon-factory-reset-48.png": factory_reset,
    "skin/icon-key-setting-48.png": key_setting,
    "skin/icon-language-48.png": language,
    "skin/icon-setting-wifi.png": wifi,
    "skin/icon-Shutdown.png": shutdown,
    "skin/icon-bluetooth-default.png": bluetooth,
    "skin/icon-bluetooth-gamepad.png": joystick,
    "skin/icon-bluetooth-headphone.png": headphone,
    "skin/icon-hotspot-wifi.png": hotspot,
    "skin/icon-joystick-calibrate.png": joystick_calibrate,
    "skin/icon-vibrate-48.png": vibrate,
    "skin/icon-usb-storage.png": usb,
    "skin/icon-remove-sdcard.png": remove_sdcard,
    "skin/icon-TF.png": tf,
    "skin/icon-trigger.png": trigger,
    "skin/icon-folder.png": folder,
    "skin/icon-folder-40.png": folder,
    "skin/ic-favorite-mark.png": favorite,
    "skin/ic-cheevos-mark.png": cheevos,
    "skin/ic-collection-f-GREEN.png": collection_green,
    "skin/Empty.png": empty,
    "skin/missing_image.png": missing_image,
    "skin/ic-MENU.png": menu,
    "skin/ic-MENU+A.png": menu_a,
}
