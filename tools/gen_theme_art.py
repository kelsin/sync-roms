#!/usr/bin/env python3
"""Draw the Art Book Next collection art in src/sync_roms/data/themes/art-book-next/art/ (needs Pillow).

Each image is the theme's slanted colour band (452x1080) with a hand-drawn outline in the style of the theme's
artwork-outline set: off-white strokes about 6px wide with slightly rough edges, 250-300px across, low on the band.

    python tools/gen_theme_art.py [id ...]     # all of them, or just the ids given
"""
import math
import os
import random
import sys
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), "..", "src", "sync_roms", "data", "themes", "art-book-next", "art")
W, H = 452, 1080
BAND = (112.424, 452.245, 0.10409)  # the theme's system-art mask: left and right edge at the top, and their slant
INK = (230, 230, 231)
SS = 4            # supersampling
STROKE = 5.8      # px, before the edge texture
CENTER = (243, 825)
UNIT = 3.3        # px per drawing unit; drawings are made in a box of about -50..50, y down


def spline(pts, closed=False, n=14):
    """Points along a Catmull-Rom spline through pts."""
    k = len(pts)
    out = []
    for i in range(k if closed else k - 1):
        p0 = pts[(i - 1) % k] if closed or i > 0 else pts[0]
        p1, p2 = pts[i], pts[(i + 1) % k]
        p3 = pts[(i + 2) % k] if closed or i + 2 < k else pts[-1]
        for j in range(n):
            t = j / n
            out.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                                    + (3 * b - a - 3 * c + d) * t ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    if not closed:
        out.append(pts[-1])
    return out


def rounded(pts, r, closed=True):
    """pts as a polyline with its corners rounded by r."""
    if r <= 0:
        return list(pts)
    k = len(pts)
    out = []
    for i in range(k):
        b = pts[i]
        if not closed and i in (0, k - 1):
            out.append(b)
            continue
        a, c = pts[i - 1], pts[(i + 1) % k]
        la, lc = math.dist(a, b), math.dist(b, c)
        ra, rc = min(r, la / 2), min(r, lc / 2)
        s = (b[0] + (a[0] - b[0]) * ra / la, b[1] + (a[1] - b[1]) * ra / la)
        e = (b[0] + (c[0] - b[0]) * rc / lc, b[1] + (c[1] - b[1]) * rc / lc)
        for j in range(7):
            t = j / 6
            out.append(((1 - t) ** 2 * s[0] + 2 * t * (1 - t) * b[0] + t * t * e[0],
                        (1 - t) ** 2 * s[1] + 2 * t * (1 - t) * b[1] + t * t * e[1]))
    return out


def arc(cx, cy, rx, ry, a0, a1, rot=0):
    """Points on an ellipse from angle a0 to a1 (degrees; 0 is right, 90 is down)."""
    n = max(4, int(abs(a1 - a0) / 6))
    cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * cr - y * sr, cy + x * sr + y * cr))
    return out


def turn(pts, deg, cx=0, cy=0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def mirror(pts):
    return [(-x, y) for x, y in pts]


def star(cx, cy, R, r, n=5, rot=-90):
    return [(cx + (R if i % 2 == 0 else r) * math.cos(math.radians(rot + i * 180 / n)),
             cy + (R if i % 2 == 0 else r) * math.sin(math.radians(rot + i * 180 / n))) for i in range(2 * n)]


class Pen:
    """Collects strokes: (points, closed) in drawing units."""

    def __init__(self):
        self.strokes = []

    def path(self, pts, closed=False):
        self.strokes.append((list(pts), closed))

    def l(self, pts, r=2.5):
        self.path(rounded(pts, r, closed=False))

    def pg(self, pts, r=2.5):
        self.path(rounded(pts, r), True)

    def c(self, pts):
        self.path(spline(pts))

    def cc(self, pts):
        self.path(spline(pts, closed=True), True)

    def o(self, cx, cy, rx, ry=None, rot=0):
        self.path(arc(cx, cy, rx, ry or rx, 0, 354, rot), True)

    def rr(self, x0, y0, x1, y1, r=3, rot=0):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.pg(turn(pts, rot, (x0 + x1) / 2, (y0 + y1) / 2) if rot else pts, r)

    def sparkle(self, cx, cy, r):
        self.pg(star(cx, cy, r, r * 0.3, 4), 0.8)

    def dash(self, pts, on=7, off=6):
        pts = spline(pts, n=24)
        run, dist, drawing = [pts[0]], 0, True
        for a, b in zip(pts, pts[1:]):
            dist += math.dist(a, b)
            if drawing:
                run.append(b)
            if dist >= (on if drawing else off):
                if drawing:
                    self.path(run)
                run, dist, drawing = [b], 0, not drawing
        if drawing and len(run) > 1:
            self.path(run)

    def runs(self, pts, keep):
        """The parts of pts where keep(x, y) holds, as separate strokes."""
        run = []
        for q in pts:
            if keep(*q):
                run.append(q)
            else:
                if len(run) > 1:
                    self.path(run)
                run = []
        if len(run) > 1:
            self.path(run)


# ---------------------------------------------------------------- drawings

def action(p):  # sword
    p.pg([(0, -50), (6.5, -40), (6.5, 18), (-6.5, 18), (-6.5, -40)], 1.5)
    p.l([(0, -36), (0, 12)])
    p.rr(-21, 18, 21, 26)
    p.rr(-4.5, 26, 4.5, 41, 1.5)
    p.o(0, 46.5, 5.5)


def adventure(p):  # compass
    p.o(0, 6, 39)
    p.o(0, 6, 31)
    p.o(0, -39.5, 6)
    p.pg(turn([(0, -20), (8, 6), (0, 32), (-8, 6)], 28, 0, 6), 1)
    p.l(turn([(-8, 6), (8, 6)], 28, 0, 6))
    for a in range(0, 360, 90):
        p.l(turn([(0, -24), (0, -19)], a, 0, 6))


def arcade(p):  # joystick
    p.rr(-40, 16, 40, 44, 7)
    p.o(-10, -32, 14)
    p.l([(-9, -18), (-4, 10)])
    p.l([(-2, -20), (5, 10)])
    p.path(arc(1, 12, 13, 4.5, 150, 390))
    p.o(24, 30, 5.5)
    p.o(-24, 30, 5.5)


def fighting(p):  # boxing glove
    p.cc([(-20, -40), (6, -46), (28, -34), (35, -8), (27, 16), (-18, 16), (-24, -4), (-27, -24)])
    p.c([(-25, -16), (-38, -17), (-42, -4), (-33, 6), (-23, 3)])
    p.rr(-20, 18, 28, 45, 3)
    p.l([(-20, 29), (28, 29)])
    p.c([(-4, -24), (9, -17), (22, -25)])


def horror(p):  # ghost
    p.cc([(-31, 38), (-32, 0), (-27, -26), (-11, -44), (9, -46), (26, -32), (32, -4), (32, 38), (24, 31), (16, 39),
          (8, 31), (0, 39), (-8, 31), (-16, 39), (-24, 31)])
    p.o(-10, -15, 4.5, 7.5)
    p.o(10, -15, 4.5, 7.5)
    p.o(0, 6, 5.5, 7.5)


def platformer(p):  # platforms, a jump and a coin
    p.rr(-48, 26, -12, 38)
    p.rr(-4, -2, 34, 10)
    p.rr(-40, -36, -6, -24)
    p.c([(-30, 20), (-25, 0), (-10, -14), (10, -8)])
    p.o(26, -30, 10)
    p.l([(26, -35), (26, -25)])


def puzzle(p):  # jigsaw piece
    p.path(rounded([(-36, -20), (-12, -20)], 0, False) + arc(-6, -30, 10, 10, 127, 413)
           + [(0, -20), (24, -20), (24, 4)] + arc(34, 10, 11.7, 11.7, 217, 503)
           + [(24, 16), (24, 40), (0, 40)] + arc(-6, 30, 10, 10, 53, -233)
           + [(-12, 40), (-36, 40), (-36, 16)] + arc(-26, 10, 11.7, 11.7, 149, -149) + [(-36, 4)], True)


def racing(p):  # chequered flag
    p.l([(-32, -44), (-22, 48)])
    p.o(-32.5, -47.5, 3.2)
    top = [(-31, -38), (-10, -45), (12, -35), (38, -42)]
    bottom = [(-27, 4), (-6, -3), (16, 7), (42, 0)]
    p.c(top)
    p.c(bottom)
    p.l([top[-1], bottom[-1]])
    mid = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(top, bottom)]
    p.c(mid)
    st, sb = spline(top), spline(bottom)
    for f in (1 / 3, 2 / 3):
        i = int(f * (len(st) - 1))
        p.l([st[i], sb[i]])


def rhythm(p):  # beamed notes
    p.o(-22, 34, 11.5, 8.5, -20)
    p.o(25, 24, 11.5, 8.5, -20)
    p.l([(-11.5, 31), (-11.5, -30)])
    p.l([(35.5, 21), (35.5, -40)])
    p.pg([(-11.5, -31), (35.5, -41), (35.5, -28), (-11.5, -18)], 1)


def rpg(p):  # potion
    p.rr(-10, -47, 10, -37, 3)
    p.path([(6.5, -37)] + arc(0, 14, 32, 32, 281.5, 618.5) + [(-6.5, -37)])
    p.c([(-30, 6), (-12, 1), (8, 10), (31, 4)])
    p.o(-10, 25, 4.5)
    p.o(10, 21, 3.2)
    p.o(4, 35, 3.2)


def shooter(p):  # rocket
    p.path(spline([(-13, 14), (-14, -14), (0, -50), (14, -14), (13, 14)]), True)
    p.o(0, -16, 6.5)
    p.l([(-13.5, -2), (-29, 24), (-13, 19)], 1.5)
    p.l([(13.5, -2), (29, 24), (13, 19)], 1.5)
    p.c([(-7, 20), (-5, 34), (0, 44), (5, 34), (7, 20)])
    p.l([(-24, -34), (-24, -44)])
    p.l([(24, -30), (24, -40)])


def sports(p):  # football
    p.o(0, 0, 40)
    pent = star(0, 0, 14, 14 * math.cos(math.radians(36)), 5)[::2]
    p.pg(pent, 1)
    for i, (x, y) in enumerate(pent):
        a = -90 + i * 72
        j = (26 * math.cos(math.radians(a)), 26 * math.sin(math.radians(a)))
        p.l([(x, y), j])
        for d in (-21, 21):
            p.l([j, (40 * math.cos(math.radians(a + d)), 40 * math.sin(math.radians(a + d)))])


def strategy(p):  # rook
    p.pg([(-23, -46), (-13, -46), (-13, -38), (-5, -38), (-5, -46), (5, -46), (5, -38), (13, -38), (13, -46),
          (23, -46), (23, -24), (-23, -24)], 1.5)
    p.l([(-16, -24), (-20, 30)])
    p.l([(16, -24), (20, 30)])
    p.l([(-17, -12), (17, -12)])
    p.l([(-19.5, 18), (19.5, 18)])
    p.rr(-30, 30, 30, 45, 3)


def surprise(p):  # gift
    p.rr(-32, -2, 32, 45, 2.5)
    p.rr(-38, -17, 38, -2, 2.5)
    p.l([(-6, -17), (-6, 45)])
    p.l([(6, -17), (6, 45)])
    p.cc([(-2, -19), (-12, -36), (-30, -38), (-32, -27), (-18, -19)])
    p.cc([(2, -19), (12, -36), (30, -38), (32, -27), (18, -19)])
    p.l([(-16, -50), (-20, -58)])
    p.l([(0, -46), (0, -56)])
    p.l([(16, -50), (20, -58)])


def platformers_3d(p):  # cube
    p.pg([(0, -38), (35, -19), (35, 21), (0, 42), (-35, 21), (-35, -19)], 2)
    p.l([(-35, -19), (0, 1), (35, -19)], 1.5)
    p.l([(0, 1), (0, 42)])
    p.sparkle(34, -40, 9)
    p.sparkle(-36, -38, 5)


def action_classics(p):  # shuriken
    p.pg(star(0, 0, 46, 13, 4, -90), 1.5)
    p.o(0, 0, 5.5)


def arcade_brawlers(p):  # fist
    top = [q for x in (-22.5, -7.5, 7.5, 22.5) for q in arc(x, -12, 7.5, 11, 180, 360)]
    p.path(top + rounded([(30, -12), (30, 26), (-30, 26), (-30, -12)], 6, False)[1:-1], True)
    for x in (-15, 0, 15):
        p.l([(x, -12), (x, 4)])
    p.rr(-34, 6, 10, 21, 7)
    p.l([(-20, 26), (-22, 46)])
    p.l([(20, 26), (22, 46)])
    p.l([(-38, -34), (-44, -42)])
    p.l([(0, -36), (0, -46)])
    p.l([(38, -34), (44, -42)])


def arcade_classics(p):  # cabinet
    p.rr(-28, -47, 28, -33, 3)
    p.l([(-24, -33), (-24, -3)])
    p.l([(24, -33), (24, -3)])
    p.rr(-17, -27, 17, -8, 3)
    p.pg([(-24, -3), (24, -3), (31, 10), (-31, 10)], 2)
    p.o(-12, 3.5, 2.8)
    p.o(6, 3.5, 2.4)
    p.o(15, 3.5, 2.4)
    p.l([(-28, 10), (-28, 47), (28, 47), (28, 10)])
    p.rr(-8, 21, 8, 37, 2)


def best_of_16_bit(p):  # cartridge
    p.pg([(-34, -38), (34, -38), (34, 38), (23, 38), (23, 46), (-23, 46), (-23, 38), (-34, 38)], 3)
    p.rr(-25, -29, 25, 13, 3)
    p.pg(star(0, -7, 14, 6), 1)
    p.l([(-13, 24), (13, 24)])
    p.l([(-13, 32), (13, 32)])


def castlevania(p):  # bat
    half = (spline([(9, -10), (26, -20), (50, -22)]) + spline([(50, -22), (42, -8), (40, 10)])
            + spline([(40, 10), (30, 2), (23, 15)]) + spline([(23, 15), (14, 8), (7, 22)])
            + spline([(7, 22), (4, 29), (0, 31)]))
    head = [(0, -15), (3, -17), (9, -29), (9, -10)]
    right = head + half
    p.path(right + mirror(right)[::-1], True)
    p.o(-3.5, -4, 1.6)
    p.o(3.5, -4, 1.6)


def co_op(p):  # two players
    p.o(-15, -14, 13)
    p.path(spline([(-42, 42), (-40, 16), (-15, 6), (10, 16), (12, 42)]), True)
    p.o(22, -28, 12)
    p.c([(11, -8), (22, -12), (40, -4), (45, 24)])
    p.l([(45, 24), (45, 42), (18, 42)])


def dungeon_crawlers(p):  # key
    p.o(0, -30, 17)
    p.o(0, -30, 7)
    p.l([(-3.5, -13), (-3.5, 46), (3.5, 46), (3.5, -13)], 1.5)
    p.l([(3.5, 20), (16, 20), (16, 28), (3.5, 28)], 1.5)
    p.l([(3.5, 35), (12, 35), (12, 43), (3.5, 43)], 1.5)


def fan_translations(p):  # speech bubbles
    p.pg([(-45, -38), (12, -38), (12, 6), (-18, 6), (-32, 21), (-30, 6), (-45, 6)], 5)
    p.l([(-28, -4), (-16.5, -29), (-5, -4)], 1)
    p.l([(-23.5, -13), (-9.5, -13)])
    p.l([(19, -12), (46, -12), (46, 30), (36, 30), (38, 45), (23, 30), (-8, 30), (-8, 14)], 5)
    p.l([(24, 0), (36, 0)])
    p.l([(2, 20), (36, 20)])
    p.l([(22, 10), (36, 10)])


def final_fantasy(p):  # crystal
    p.pg([(4, -50), (24, -24), (24, 22), (4, 48), (-16, 22), (-16, -24)], 1.5)
    p.l([(-16, -24), (0, -16), (24, -24)], 1)
    p.l([(-16, 22), (0, 28), (24, 22)], 1)
    p.l([(4, -50), (0, -16), (0, 28), (4, 48)], 1)
    p.pg([(-32, 8), (-24, 20), (-24, 38), (-32, 48), (-40, 38), (-40, 20)], 1.5)
    p.l([(-40, 20), (-33, 23), (-24, 20)], 1)
    p.l([(-33, 23), (-32, 48)])
    p.sparkle(-34, -30, 8)


def fps(p):  # crosshair
    p.o(0, 0, 33)
    p.o(0, 0, 4)
    for a in range(0, 360, 90):
        p.l(turn([(0, -47), (0, -19)], a))


def handheld_greatest_hits(p):  # handheld
    p.rr(-27, -47, 27, 47, 8)
    p.rr(-19, -39, 19, -7, 3)
    p.pg(star(0, -23, 10, 4.3), 0.8)
    p.pg([(-15, 6), (-9, 6), (-9, 12), (-3, 12), (-3, 18), (-9, 18), (-9, 24), (-15, 24), (-15, 18), (-21, 18),
          (-21, 12), (-15, 12)], 1)
    p.o(17, 10, 4.5)
    p.o(8, 19, 4.5)
    p.l([(6, 36), (12, 32)])
    p.l([(13, 38), (19, 34)])


def hidden_gems(p):  # gem
    p.pg([(-22, -26), (22, -26), (41, -6), (0, 44), (-41, -6)], 1.5)
    p.l([(-41, -6), (41, -6)])
    p.l([(-22, -26), (-13, -6), (0, -26), (13, -6), (22, -26)], 1)
    p.l([(-13, -6), (0, 44), (13, -6)], 1)
    p.sparkle(36, -40, 9)
    p.sparkle(-38, -36, 5.5)


def jrpg_essentials(p):  # treasure chest
    p.rr(-38, -2, 38, 41, 3)
    p.path([(-38, -2)] + spline([(-38, -18), (-33, -32), (-19, -38), (19, -38), (33, -32), (38, -18)]) + [(38, -2)])
    p.l([(-21, -37), (-21, -2)])
    p.l([(21, -37), (21, -2)])
    p.l([(-21, -2), (-21, 41)])
    p.l([(21, -2), (21, 41)])
    p.rr(-7, -9, 7, 9, 2.5)
    p.l([(0, -2), (0, 3)], 0)


def kart_racers(p):  # helmet
    p.cc([(-37, 22), (-40, -8), (-24, -36), (6, -42), (30, -30), (39, -6), (37, 20), (0, 26)])
    p.pg([(2, -18), (32, -18), (39, 2), (8, 2)], 5)
    p.c([(-38, -4), (-18, -8), (2, -18)])
    p.c([(-36, 10), (-14, 8), (8, 2)])
    p.o(-18, 14, 3)


def kirby(p):  # shooting star
    p.pg(turn(star(8, -6, 36, 17), 14, 8, -6), 4)
    p.c([(-46, 20), (-36, 22), (-24, 18)])
    p.c([(-40, 36), (-26, 38), (-10, 30)])
    p.c([(-22, 48), (-10, 48), (2, 42)])
    p.sparkle(-34, -34, 7)


def licensed_classics(p):  # clapperboard
    p.rr(-38, -8, 38, 42, 3)
    p.l([(-38, 6), (38, 6)])
    for x in (-22, -3, 16, 35):
        p.l([(x, -8), (x - 8, 6)])
    bar = lambda pts: turn(pts, -13, -38, -10)
    p.pg(bar([(-38, -24), (38, -24), (38, -10), (-38, -10)]), 2)
    for x in (-24, -5, 14, 33):
        p.l(bar([(x - 8, -24), (x, -10)]))
    p.l([(-27, 19), (2, 19)])
    p.l([(-27, 30), (16, 30)])


def life_sim(p):  # seedling
    p.rr(-26, 4, 26, 14, 2.5)
    p.l([(-21, 14), (-16, 45), (16, 45), (21, 14)])
    p.c([(0, 4), (-2, -12), (2, -26)])
    p.path(spline([(2, -26), (-6, -42), (-28, -46), (-22, -30), (2, -26)]), True)
    p.path(spline([(1, -12), (12, -32), (36, -36), (26, -16), (1, -12)]), True)
    p.c([(-2, -28), (-12, -36), (-20, -39)])
    p.c([(6, -15), (18, -24), (28, -30)])


def light_gun(p):  # light gun
    p.pg([(-46, -24), (26, -24), (37, -14), (33, 4), (31, 38), (10, 38), (12, -3), (-46, -3)], 3.5)
    p.l([(-36, -24), (-36, -3)])
    p.l([(-42, -24), (-42, -31), (-35, -31)], 1.5)
    p.c([(-12, -3), (-11, 10), (0, 14), (11, 9)])
    p.c([(3, -3), (0, 3), (1, 8)])
    p.c([(20, 38), (16, 48), (28, 52), (44, 44)])


def mario(p):  # mushroom
    p.path(spline([(-41, 4), (-39, -24), (-17, -45), (17, -45), (39, -24), (41, 4)])
           + spline([(41, 4), (21, 10), (0, 11), (-21, 10), (-41, 4)])[1:], True)
    p.c([(-18, 10), (-23, 32), (-13, 45), (13, 45), (23, 32), (18, 10)])
    p.o(0, -22, 11.5)
    p.c([(-38, -16), (-27, -15), (-24, -3), (-31, 5)])
    p.c([(38, -16), (27, -15), (24, -3), (31, 5)])


def mega_man(p):  # gear
    pts = []
    for i in range(8):
        for d, r in ((-15, 31), (-9, 43), (9, 43), (15, 31)):
            a = math.radians(i * 45 + d)
            pts.append((r * math.cos(a), r * math.sin(a)))
    p.pg(pts, 2)
    p.o(0, 0, 14)


def metroid(p):  # ringed planet
    p.o(0, 2, 27)
    ring = turn(arc(0, 2, 47, 13, 0, 360), -20, 0, 2)
    p.runs(ring, lambda x, y: math.hypot(x, y - 2) > 27 or (y - 2) > -0.36 * x)
    p.c([(-22, -10), (-6, -16), (10, -22)])
    p.sparkle(34, -38, 8)
    p.sparkle(-36, -32, 5)
    p.sparkle(-30, 40, 5)


def metroidvanias(p):  # map
    p.pg([(-42, -30), (-14, -38), (14, -30), (42, -38), (42, 30), (14, 38), (-14, 30), (-42, 38)], 2)
    p.l([(-14, -38), (-14, 30)])
    p.l([(14, -30), (14, 38)])
    p.o(-30, 20, 3.5)
    p.dash([(-24, 16), (-14, 2), (0, 8), (12, 2), (22, -8)])
    p.l([(23, -22), (35, -10)])
    p.l([(35, -22), (23, -10)])


def pinball(p):  # flippers, bumpers and a ball
    def flipper(flip):
        a = math.degrees(math.atan2(20, 28))
        pts = arc(-38, 18, 8, 8, a + 90, a + 270) + arc(-10, 38, 3.5, 3.5, a - 90, a + 90)
        p.path(mirror(pts) if flip else pts, True)
        p.o(38 if flip else -38, 18, 2)
    flipper(False)
    flipper(True)
    p.o(-20, -28, 14)
    p.o(-20, -28, 6.5)
    p.o(24, -34, 11)
    p.o(24, -34, 4.5)
    p.o(8, 4, 8.5)


def platformers(p):  # spring
    p.o(2, -38, 9.5)
    p.l([(-16, -44), (-22, -50)])
    p.l([(-18, -34), (-26, -34)])
    p.rr(-25, -22, 25, -14, 2.5)
    p.l([(-18, -14), (18, -5), (-18, 5), (18, 15), (-18, 25), (18, 35)], 4)
    p.rr(-29, 37, 29, 46, 2.5)


def pokemon(p):  # lightning bolt
    p.pg([(10, -50), (-24, 4), (-4, 4), (-16, 48), (26, -10), (5, -10), (22, -50)], 2)
    p.l([(-36, -30), (-28, -24)])
    p.l([(-40, -8), (-32, -8)])
    p.l([(34, 14), (42, 14)])
    p.l([(30, 30), (38, 36)])


def resident_evil(p):  # umbrella
    scallops = []
    for x in (44, 22, 0, -22):
        scallops += spline([(x, -2), (x - 11, -9), (x - 22, -2)])[1:]
    p.path(spline([(-44, -2), (-36, -28), (0, -44), (36, -28), (44, -2)]) + scallops, True)
    p.c([(0, -44), (-15, -28), (-22, -2)])
    p.c([(0, -44), (15, -28), (22, -2)])
    p.l([(0, -44), (0, -51)])
    p.path([(0, -9), (0, 34)] + arc(-6, 36, 6, 8, 0, 180))


def retro_oddities(p):  # television
    p.rr(-41, -22, 41, 38, 7)
    p.rr(-33, -14, 14, 30, 8)
    p.o(28, -5, 5)
    p.o(28, 10, 5)
    p.l([(22, 22), (33, 22)])
    p.l([(22, 28), (33, 28)])
    p.l([(-5, -22), (-22, -47)])
    p.l([(5, -22), (24, -45)])
    p.l([(-26, 38), (-30, 46)])
    p.l([(26, 38), (30, 46)])


def rpg_series(p):  # spellbook
    p.rr(-29, -42, 30, 40, 3.5)
    p.l([(-19, -42), (-19, 40)])
    p.pg(star(6, -6, 14, 6), 1)
    p.l([(-4, 20), (16, 20)])
    p.l([(12, 40), (12, 51), (17, 46), (22, 51), (22, 40)], 1)


def run_and_gun(p):  # grenade
    p.o(-2, 14, 26, 31)
    p.c([(-27, 2), (-2, 7), (23, 2)])
    p.c([(-26, 26), (-2, 31), (22, 26)])
    p.c([(-11, -16), (-13, 14), (-11, 44)])
    p.c([(7, -16), (9, 14), (7, 44)])
    p.rr(-12, -30, 8, -17, 2.5)
    p.c([(8, -27), (24, -30), (34, -14), (35, 6)])
    p.o(-22, -34, 8.5)


def shmups(p):  # fighter, seen from above
    p.pg([(0, -46), (7, -24), (10, -4), (41, 18), (41, 28), (12, 24), (8, 36), (-8, 36), (-12, 24), (-41, 28),
          (-41, 18), (-10, -4), (-7, -24)], 2)
    p.o(0, -14, 4, 8.5)
    p.c([(-5, 40), (0, 49), (5, 40)])
    p.l([(-26, -22), (-26, -34)])
    p.l([(26, -22), (26, -34)])
    p.l([(-26, 0), (-26, -8)])
    p.l([(26, 0), (26, -8)])


def short_sessions(p):  # hourglass
    p.rr(-27, -47, 27, -38, 2.5)
    p.rr(-27, 38, 27, 47, 2.5)
    side = spline([(-20, -38), (-19, -22), (-4, -3), (-4, 3), (-19, 22), (-20, 38)])
    p.path(side)
    p.path(mirror(side))
    p.c([(-15, -22), (0, -19), (15, -22)])
    p.l([(0, -2), (0, 22)])
    p.c([(-14, 38), (-7, 30), (0, 26), (7, 30), (14, 38)])


def sonic(p):  # ring
    p.o(-2, 4, 33, 40)
    p.o(-6, 4, 22, 30)
    p.sparkle(36, -36, 10)
    p.sparkle(42, 34, 5.5)
    p.sparkle(-40, -40, 5)


def star_wars(p):  # laser sword
    p.l([(-5.5, 8), (-5.5, -50), (5.5, -50), (5.5, 8)], 5.5)
    p.rr(-7.5, 8, 7.5, 15, 1.5)
    p.rr(-5.5, 15, 5.5, 47, 2)
    p.l([(-5.5, 23), (5.5, 23)])
    p.l([(-5.5, 39), (5.5, 39)])
    p.o(0, 31, 2.2)
    p.l([(-14, -38), (-21, -42)])
    p.l([(-15, -20), (-23, -20)])
    p.l([(14, -30), (21, -34)])
    p.l([(15, -10), (23, -10)])


def stealth(p):  # cardboard box and an alert
    p.rr(-34, -2, 34, 42, 2.5)
    p.l([(-34, -2), (-45, -15), (-11, -15), (0, -2)], 1.5)
    p.l([(34, -2), (45, -15), (11, -15), (0, -2)], 1.5)
    p.l([(0, -2), (0, 10)])
    p.rr(-13, 16, 13, 25, 4.5)
    p.pg([(-4.5, -52), (4.5, -52), (2.5, -32), (-2.5, -32)], 1.5)
    p.o(0, -24, 2.8)


def strategy_tactics(p):  # pawn and pennant
    p.o(-10, -30, 11.5)
    p.l([(-21, -17), (1, -17)])
    p.c([(-17, -17), (-18, 2), (-27, 28)])
    p.c([(-3, -17), (-2, 2), (7, 28)])
    p.rr(-33, 28, 13, 44, 3)
    p.l([(30, 44), (30, -24)])
    p.pg([(30, -24), (48, -14), (30, -4)], 1.5)


def street_fighter(p):  # fireball
    p.o(-14, 8, 22)
    p.o(-14, 8, 10)
    p.path(spline([(-19.7, -13.3), (2, -22), (22, -36), (46, -34)]) + spline([(46, -34), (33, -24), (29, -13)])[1:]
           + spline([(29, -13), (39, -11), (48, -3)])[1:] + spline([(48, -3), (34, 3), (28, 12)])[1:]
           + spline([(28, 12), (36, 16), (42, 24)])[1:] + spline([(42, 24), (14, 34), (-10.2, 29.7)])[1:])


def survival_horror(p):  # torch
    p.rr(-46, -8, -4, 8, 3)
    p.pg([(-4, -8), (9, -19), (17, -19), (17, 19), (9, 19), (-4, 8)], 2)
    p.rr(-30, -3.5, -18, 3.5, 3)
    p.l([(24, -14), (46, -30)])
    p.l([(26, 0), (49, 0)])
    p.l([(24, 14), (46, 30)])


def system_essentials(p):  # checklist
    p.rr(-30, -39, 30, 47, 4)
    p.rr(-12, -47, 12, -32, 3)
    for y in (-13, 7, 27):
        p.l([(-22, y), (-17.5, y + 5), (-10, y - 6)], 1)
        p.l([(-1, y), (20, y)])


def zelda(p):  # shield
    p.path(spline([(-34, -38), (-17, -34), (0, -43), (17, -34), (34, -38)])
           + spline([(34, -38), (35, -2), (23, 26), (0, 47)])[1:]
           + spline([(0, 47), (-23, 26), (-35, -2), (-34, -38)])[1:-1], True)
    p.pg([(0, -24), (13, -5), (0, 14), (-13, -5)], 1.5)
    p.c([(-17, 14), (0, 30), (17, 14)])


# id: (drawing, band colour, rotation in degrees, scale, offset in px)
ART = {
    "action": (action, (198, 66, 58), 32, 1.0, (0, 0)),
    "adventure": (adventure, (44, 146, 118), -6, 1.0, (0, 0)),
    "arcade": (arcade, (92, 92, 204), -7, 1.0, (0, 0)),
    "fighting": (fighting, (232, 112, 42), -8, 1.0, (0, 0)),
    "horror": (horror, (72, 52, 96), 4, 1.0, (0, 0)),
    "platformer": (platformer, (68, 148, 220), -5, 1.0, (0, 0)),
    "puzzle": (puzzle, (228, 186, 42), -6, 1.0, (0, 0)),
    "racing": (racing, (96, 104, 116), -4, 1.0, (0, 0)),
    "rhythm": (rhythm, (236, 118, 108), -4, 1.0, (0, 0)),
    "rpg": (rpg, (122, 84, 184), 8, 1.0, (0, 0)),
    "shooter": (shooter, (52, 72, 140), 18, 1.0, (0, 0)),
    "sports": (sports, (72, 160, 74), 10, 1.0, (0, 0)),
    "strategy": (strategy, (150, 102, 62), 5, 1.0, (0, 0)),
    "surprise": (surprise, (201, 62, 110), -6, 1.0, (0, 10)),
    "3d-platformers": (platformers_3d, (240, 150, 40), -4, 1.0, (0, 0)),
    "action-classics": (action_classics, (150, 44, 52), 18, 1.0, (0, 0)),
    "arcade-brawlers": (arcade_brawlers, (206, 84, 44), -8, 1.0, (0, 0)),
    "arcade-classics": (arcade_classics, (70, 78, 170), 6, 1.0, (0, 0)),
    "best-of-16-bit": (best_of_16_bit, (112, 96, 176), -8, 1.0, (6, 0)),
    "castlevania": (castlevania, (120, 36, 60), -6, 1.0, (0, 0)),
    "co-op": (co_op, (36, 150, 160), -4, 1.0, (-18, 0)),
    "dungeon-crawlers": (dungeon_crawlers, (104, 92, 80), 28, 1.0, (0, 0)),
    "fan-translations": (fan_translations, (214, 92, 124), -5, 1.0, (-10, 0)),
    "final-fantasy": (final_fantasy, (64, 132, 206), 10, 1.0, (0, 0)),
    "fps": (fps, (156, 60, 48), 8, 1.0, (0, 0)),
    "handheld-greatest-hits": (handheld_greatest_hits, (120, 170, 60), -8, 1.0, (0, 0)),
    "hidden-gems": (hidden_gems, (40, 160, 150), -6, 1.0, (0, 0)),
    "jrpg-essentials": (jrpg_essentials, (176, 124, 44), -6, 1.0, (0, 0)),
    "kart-racers": (kart_racers, (224, 76, 64), -8, 1.0, (0, 0)),
    "kirby": (kirby, (238, 132, 166), 0, 1.0, (-10, 0)),
    "licensed-classics": (licensed_classics, (60, 68, 84), -6, 1.0, (-6, 0)),
    "life-sim": (life_sim, (104, 172, 84), -5, 1.0, (0, 0)),
    "light-gun": (light_gun, (228, 120, 52), -10, 1.0, (-10, 0)),
    "mario": (mario, (216, 56, 56), -6, 1.0, (0, 0)),
    "mega-man": (mega_man, (48, 136, 216), 10, 1.0, (-8, 0)),
    "metroid": (metroid, (224, 104, 36), 0, 1.0, (-6, 0)),
    "metroidvanias": (metroidvanias, (84, 76, 150), -6, 1.0, (0, 0)),
    "pinball": (pinball, (170, 70, 170), -6, 1.0, (-14, 0)),
    "platformers": (platformers, (56, 164, 200), -6, 1.0, (0, 0)),
    "pokemon": (pokemon, (236, 180, 30), 6, 1.0, (-8, 0)),
    "resident-evil": (resident_evil, (140, 40, 44), 16, 1.0, (0, 0)),
    "retro-oddities": (retro_oddities, (176, 112, 52), -6, 1.0, (6, 0)),
    "rpg-series": (rpg_series, (132, 72, 148), -10, 1.0, (0, 0)),
    "run-and-gun": (run_and_gun, (96, 124, 68), 12, 1.0, (0, 0)),
    "shmups": (shmups, (44, 60, 120), 16, 1.0, (0, 0)),
    "short-sessions": (short_sessions, (60, 150, 190), 8, 1.0, (0, 0)),
    "sonic": (sonic, (36, 96, 200), 8, 1.0, (-12, 0)),
    "star-wars": (star_wars, (40, 44, 60), -32, 1.0, (0, 0)),
    "stealth": (stealth, (86, 110, 100), -5, 1.0, (0, 6)),
    "strategy-tactics": (strategy_tactics, (128, 100, 64), -5, 1.0, (-18, 0)),
    "street-fighter": (street_fighter, (226, 88, 40), -14, 1.0, (-22, 0)),
    "survival-horror": (survival_horror, (58, 62, 70), -24, 1.0, (-24, 0)),
    "system-essentials": (system_essentials, (72, 128, 180), -7, 1.0, (0, 0)),
    "zelda": (zelda, (52, 140, 84), -6, 1.0, (0, 0)),
}


# ---------------------------------------------------------------- rendering

def _resample(pts, closed, step):
    if closed:
        pts = pts + [pts[0]]
    out, carry = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        t = step - carry
        while t <= d:
            out.append((a[0] + (b[0] - a[0]) * t / d, a[1] + (b[1] - a[1]) * t / d))
            t += step
        carry = (carry + d) % step
    return out


def _ink(strokes, rng):
    """The strokes (in px) as an L mask at SS scale, drawn with an unsteady hand."""
    img = Image.new("L", (W * SS, H * SS), 0)
    draw = ImageDraw.Draw(img)
    for pts, closed in strokes:
        pts = _resample(pts, closed, 0.5)
        n = len(pts)
        if n < 2:
            continue
        length = n * 0.5
        waves = [(amp, max(1, round(length / wl)) if closed else length / wl, rng.uniform(0, math.tau))
                 for amp, wl in ((0.7, 190), (0.3, 80))]  # sideways drift
        thick = (0.07, max(1, round(length / 120)) if closed else length / 120, rng.uniform(0, math.tau))
        for i, (x, y) in enumerate(pts):
            ax, ay = pts[i - 1] if i else pts[0]
            bx, by = pts[i + 1] if i + 1 < n else pts[-1]
            d = math.hypot(bx - ax, by - ay) or 1
            f = i / n
            off = sum(a * math.sin(math.tau * k * f + ph) for a, k, ph in waves)
            if not closed:
                off *= min(1, i / 12, (n - 1 - i) / 12)  # ends stay where they were put, so strokes still meet
            x, y = x - (by - ay) / d * off, y + (bx - ax) / d * off
            r = STROKE / 2 * (1 + thick[0] * math.sin(math.tau * thick[1] * f + thick[2])) * SS
            draw.ellipse((x * SS - r, y * SS - r, x * SS + r, y * SS + r), fill=255)
    # rough edges, like the theme's brush
    noise = Image.frombytes("L", img.size, rng.randbytes(img.width * img.height))
    noise = noise.filter(ImageFilter.GaussianBlur(SS * 0.45))
    soft = img.filter(ImageFilter.GaussianBlur(SS * 0.55))
    rough = ImageChops.add(soft, noise, 1, -128).point(lambda v: 255 if v > 127 else 0)
    return rough.resize((W, H), Image.LANCZOS)


def render(art_id):
    draw, colour, rot, scale, (dx, dy) = ART[art_id]
    pen = Pen()
    draw(pen)
    rng = random.Random(zlib.crc32(art_id.encode()))
    strokes = [([(CENTER[0] + dx + x * UNIT * scale, CENTER[1] + dy + y * UNIT * scale) for x, y in turn(pts, rot)],
                closed) for pts, closed in pen.strokes]
    band = Image.new("L", (W, H), 0)
    for y in range(H):
        left, right = (edge - BAND[2] * (y + 0.5) for edge in BAND[:2])
        for x in range(int(left), min(W, int(right) + 1)):
            band.putpixel((x, y), round(255 * (min(x + 1, right) - max(x, left))))
    img = Image.new("RGB", (W, H), colour)
    img.paste(Image.new("RGB", (W, H), INK), mask=_ink(strokes, rng))
    img.putalpha(band)
    return img


def main(ids):
    for art_id in ids or ART:
        render(art_id).save(os.path.join(OUT, f"{art_id}.png"), optimize=True)
        print(art_id)


if __name__ == "__main__":
    main(sys.argv[1:])
