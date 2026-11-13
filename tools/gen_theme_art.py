#!/usr/bin/env python3
"""Draw the Art Book Next collection art in src/sync_roms/data/themes/art-book-next/art/ (needs Pillow).

Each image is the theme's slanted colour band (452x1080) with a hand-drawn outline in the style of the theme's
artwork-outline set: off-white strokes about 6px wide with slightly rough edges, 250-300px across, low on the band.
Lines are steady and meet exactly: a line that stops at a shape is cut at its outline (Pen.inside), and a shape in
front of another hides it (opaque).

    python tools/gen_theme_art.py [id ...]     # all of them, or just the ids given
"""
import contextlib
import html
import json
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
    """Collects strokes: (points, closed, opaque, clip) in drawing units. An opaque shape hides what was drawn before
    it; clip is the shape the stroke is cut off at, if any."""

    def __init__(self):
        self.strokes = []
        self.clip = None

    def path(self, pts, closed=False, opaque=False):
        self.strokes.append((list(pts), closed, opaque, self.clip))

    @contextlib.contextmanager
    def inside(self, shape):
        """Strokes drawn in this block stop at shape's outline."""
        self.clip = list(shape)
        yield
        self.clip = None

    def l(self, pts, r=2.5):
        self.path(rounded(pts, r, closed=False))

    def pg(self, pts, r=2.5, opaque=False):
        self.path(rounded(pts, r), True, opaque)

    def c(self, pts):
        self.path(spline(pts))

    def cc(self, pts):
        self.path(spline(pts, closed=True), True)

    def o(self, cx, cy, rx, ry=None, rot=0, opaque=False):
        self.path(arc(cx, cy, rx, ry or rx, 0, 354, rot), True, opaque)

    def rr(self, x0, y0, x1, y1, r=3, rot=0, opaque=False):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.pg(turn(pts, rot, (x0 + x1) / 2, (y0 + y1) / 2) if rot else pts, r, opaque)

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

def action_classics(p):  # sword
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


def fighting(p):  # versus
    p.pg(star(0, 0, 48, 37, 12), 1)
    p.l([(-27, -15), (-15, 15), (-3, -15)], 1)
    p.path(arc(15, -7.5, 9.5, 7.5, 325, 90) + arc(15, 7.5, 9.5, 7.5, 270, 505)[1:])


def horror(p):  # ghost
    p.cc([(-31, 38), (-32, 0), (-27, -26), (-11, -44), (9, -46), (26, -32), (32, -4), (32, 38), (24, 31), (16, 39),
          (8, 31), (0, 39), (-8, 31), (-16, 39), (-24, 31)])
    p.o(-10, -15, 4.5, 7.5)
    p.o(10, -15, 4.5, 7.5)
    p.o(0, 6, 5.5, 7.5)


def platformers(p):  # platforms, a jump and a coin
    p.rr(-48, 26, -12, 38)
    p.rr(-4, -2, 34, 10)
    p.rr(-40, -36, -6, -24)
    p.dash([(-30, 18), (-26, -2), (-12, -15), (8, -10)])
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
    with p.inside(arc(0, 14, 32, 32, 0, 354)):
        p.c([(-36, 7), (-12, 1), (8, 10), (36, 3)])
    p.o(-10, 25, 4.5)
    p.o(10, 21, 3.2)
    p.o(4, 35, 3.2)


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


def strategy_tactics(p):  # rook
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


def backlog(p):  # pile of games
    for x, y in ((-3, -33), (4, -11), (-2, 11)):
        p.rr(x - 33, y, x + 33, y + 22, 3)
        p.rr(x - 20, y + 6, x + 8, y + 16, 2)


def benchmarks(p):  # gauge
    dial = arc(0, 14, 42, 42, 180, 360) + rounded([(42, 14), (42, 28), (-42, 28), (-42, 14)], 4, False)[1:-1]
    p.path(dial, True)
    with p.inside(dial):
        for a in range(210, 331, 30):
            p.l(turn([(34, 14), (50, 14)], a, 0, 14))
    p.l(turn([(0, 14), (28, 14)], 315, 0, 14))
    p.o(0, 14, 5, opaque=True)


def completed(p):  # trophy
    p.o(-24, -26, 12, 11)
    p.o(24, -26, 12, 11)
    p.l([(-4, 0), (-4, 20)])
    p.l([(4, 0), (4, 20)])
    p.path(rounded([(-22, -20), (-22, -44), (22, -44), (22, -20)], 3, False) + arc(0, -20, 22, 26, 0, 180)[1:-1],
           True, opaque=True)
    p.pg(star(0, -22, 10, 4.3), 0.8)
    p.rr(-12, 20, 12, 28, 2.5)
    p.rr(-22, 28, 22, 42, 3)


def decades(p):  # calendar
    p.rr(-36, -34, 36, 42, 5)
    p.l([(-36, -15), (36, -15)])
    for x in (-18, 18):
        p.rr(x - 3.5, -44, x + 3.5, -26, 3.5, opaque=True)
    for y in (2, 24):
        for x in (-21, 0, 21):
            p.rr(x - 5, y - 5, x + 5, y + 5, 2)


def favorites(p):  # hearts
    lobe = math.degrees(math.atan2(-math.sqrt(21 ** 2 - 19 ** 2), 19)) + 360  # where the two lobes meet
    side = math.degrees(math.atan2(56, 19) + math.acos(21 / math.hypot(19, 56)))  # where a lobe turns to the point
    half = arc(-19, -12, 21, 21, lobe, side) + [(0, 44)]
    heart = half + mirror(half)[-2:0:-1]
    p.path([(x - 4, y + 4) for x, y in heart], True)
    p.path(turn([(40 + x * 0.3, -40 + y * 0.3) for x, y in heart], 14, 40, -40), True)


def hacks_homebrew(p):  # spanner
    handle, jaw = math.degrees(math.asin(8 / 18)), math.degrees(math.asin(6.5 / 18))
    right = arc(0, -28, 18, 18, 90 - handle, jaw - 90)
    top = right[-1][1]
    p.path(right + rounded([(6.5, top), (6.5, -31), (-6.5, -31), (-6.5, top)], 2.5, False)[1:-1] + mirror(right)[::-1]
           + arc(0, 39, 8, 8, 180, 0), True)
    p.o(0, 38, 2.6)


def hard_mode(p):  # skull
    skull = arc(0, -8, 32, 30, 150, 390) + rounded([(27.7, 7), (18, 20), (18, 40), (-18, 40), (-18, 20), (-27.7, 7)],
                                                   4, False)[1:-1]
    p.path(skull, True)
    p.o(-12, -6, 8, 9)
    p.o(12, -6, 8, 9)
    p.pg([(0, 7), (5, 17), (-5, 17)], 1.5)
    with p.inside(skull):
        p.l([(-40, 27), (40, 27)])
    for x in (-9, 0, 9):
        p.l([(x, 27), (x, 40)])


def holiday(p):  # snowflake
    for a in range(0, 360, 60):
        p.l(turn([(0, 0), (0, -44)], a))
        p.l(turn([(-9, -37), (0, -27), (9, -37)], a), 1)
        p.l(turn([(-5, -19), (0, -13), (5, -19)], a), 1)


def imports(p):  # globe on a stand
    cx, cy, tilt = -2, -8, 20
    p.path(arc(cx, cy, 38, 38, 290, 470))
    for a in (290, 110):
        p.l(turn([(cx, cy), (cx + 38, cy)], a, cx, cy))
    globe = arc(cx, cy, 30, 30, 0, 354)
    p.path(globe, True, opaque=True)
    with p.inside(globe):
        for y in (-16, 0, 16):
            p.l(turn([(cx - 40, cy + y), (cx + 40, cy + y)], tilt, cx, cy))
    p.o(cx, cy, 13, 30, tilt)
    p.l([(cx, cy + 38), (cx, cy + 46)])
    p.rr(cx - 18, cy + 46, cx + 18, cy + 54, 3)


def kids(p):  # teddy bear
    p.o(-25, -22, 11)
    p.o(25, -22, 11)
    p.o(0, 6, 32, 28, opaque=True)
    for x in (-12, 12):
        p.o(x, -4, 2.2)
        p.o(x, -4, 0.8)
    p.o(0, 16, 14, 11)
    p.o(0, 12, 2.2)
    p.o(0, 12, 0.8)
    p.l([(0, 14.2), (0, 19)])
    p.c([(-5, 18), (-2.5, 21), (0, 19), (2.5, 21), (5, 18)])


def late_night(p):  # crescent moon and stars
    a, b = math.degrees(math.acos(20 / 36)), math.degrees(math.acos(2 / 30))  # where the two circles cross
    moon = turn(arc(0, 0, 36, 36, a, 360 - a) + arc(18, 0, 30, 30, 360 - b, b)[1:-1], -32)
    p.path([(x - 6, y + 4) for x, y in moon], True)
    p.sparkle(10, -4, 9)
    p.sparkle(30, -8, 5)
    p.sparkle(16, -30, 4.5)


def now_playing(p):  # gamepad
    p.pg([(-24, -24), (24, -24), (38, -17), (45, 18), (37, 32), (26, 28), (16, 10), (-16, 10), (-26, 28), (-37, 32),
          (-45, 18), (-38, -17)], 7)
    p.pg([(-25, -15), (-19, -15), (-19, -9), (-13, -9), (-13, -3), (-19, -3), (-19, 3), (-25, 3), (-25, -3),
          (-31, -3), (-31, -9), (-25, -9)], 1)
    p.o(15, 0, 4.5)
    p.o(26, -9, 4.5)
    p.l([(-6, -6), (-2, -6)])
    p.l([(2, -6), (6, -6)])


def soundtracks(p):  # headphones
    p.path(arc(0, 0, 37, 40, 180, 360))
    p.path(arc(0, 0, 31, 34, 180, 360))
    for x in (-1, 1):
        p.rr(x * 18, 2, x * 28, 26, 3)
        p.rr(x * 26, -4, x * 42, 32, 5, opaque=True)


def platformers_3d(p):  # cube
    p.pg([(0, -38), (35, -19), (35, 21), (0, 42), (-35, 21), (-35, -19)], 2)
    p.l([(-35, -19), (0, 1), (35, -19)], 1.5)
    p.l([(0, 1), (0, 42)])
    p.sparkle(34, -40, 9)
    p.sparkle(-36, -38, 5)


def arcade_brawlers(p):  # fist
    tops = [q for x in (-22.5, -7.5, 7.5, 22.5) for q in arc(x, -15, 7.5, 9, 180, 360)]
    p.path(tops + rounded([(30, -15), (30, 27), (-30, 27), (-30, -15)], 10, False)[1:-1], True)
    for x in (-15, 0, 15):
        p.l([(x, -15), (x, 5)])
    p.l([(0, 5), (30, 5)])
    p.rr(-36, 5, 8, 20, 7.5, opaque=True)
    p.l([(-16, 27), (-16, 35)])
    p.l([(16, 27), (16, 35)])
    p.rr(-22, 35, 22, 47)
    p.l([(0, -32), (0, -42)])
    p.l([(-19, -31), (-26, -39)])
    p.l([(19, -31), (26, -39)])


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
    p.o(20, -30, 12)
    p.path(arc(20, 16, 24, 24, 180, 360) + [(44, 44), (-4, 44)], True)
    p.o(-14, -14, 13)
    p.path(arc(-14, 32, 27, 24, 180, 360) + [(13, 44), (-41, 44)], True, opaque=True)


def dungeon_crawlers(p):  # key
    p.o(0, -30, 17)
    p.o(0, -30, 7)
    p.l([(-3.5, -13), (-3.5, 46), (3.5, 46), (3.5, -13)], 1.5)
    p.l([(3.5, 20), (16, 20), (16, 28), (3.5, 28)], 1.5)
    p.l([(3.5, 35), (12, 35), (12, 43), (3.5, 43)], 1.5)


def fan_translations(p):  # speech bubbles
    p.pg([(-8, -12), (46, -12), (46, 30), (36, 30), (38, 45), (23, 30), (-8, 30)], 5)
    p.l([(20, 1), (38, 1)])
    p.l([(0, 10), (38, 10)])
    p.l([(0, 19), (28, 19)])
    p.pg([(-45, -38), (12, -38), (12, 6), (-18, 6), (-32, 21), (-30, 6), (-45, 6)], 5, opaque=True)
    p.l([(-28, -4), (-16.5, -29), (-5, -4)], 1)
    p.l([(-23.5, -13), (-9.5, -13)])


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
    shell = arc(0, -2, 40, 38, 160, 380) + rounded([(37.6, 11), (33, 27), (-31, 27), (-37.6, 11)], 7, False)[1:-1]
    p.path(shell, True)
    with p.inside(shell):
        p.rr(4, -18, 60, 5, 7)
        p.l([(-60, -6.5), (4, -6.5)])
    p.rr(13, 13, 28, 18.5, 2.7)


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


def life_sim(p):  # house and tree
    p.l([(-46, 40), (52, 40)])
    p.pg([(-42, -4), (-8, -36), (26, -4)], 2)
    p.l([(-34, -4), (-34, 40)])
    p.l([(18, -4), (18, 40)])
    p.l([(8, -20.9), (8, -34), (16, -34), (16, -13.4)], 1.5)
    p.path([(x * 1.3 - 8, y * 1.3 - 15) for x, y in
            arc(-2.6, -2, 2.6, 2.6, 180, 360) + arc(2.6, -2, 2.6, 2.6, 180, 360) + [(0, 5.5)]], True)
    p.l([(-27, 40), (-27, 17), (-15, 17), (-15, 40)], 2)
    p.rr(-4, 12, 10, 26, 1.5)
    p.l([(3, 12), (3, 26)])
    p.l([(-4, 19), (10, 19)])
    p.o(35, 8, 13)
    p.l([(32.5, 20.76), (32.5, 40)])
    p.l([(37.5, 20.76), (37.5, 40)])


def light_gun(p):  # light gun
    p.rr(-50, -20, 0, -9, 2)
    p.rr(-50, -22.5, -41, -6.5, 2.5, opaque=True)
    grip = rounded([(10, -4), (34, -4), (42, 38), (22, 38)], 4)
    p.path(grip, True)
    with p.inside(grip):
        for y in (22, 29):
            p.l([(0, y), (60, y)])
    p.pg([(-6, -24), (28, -24), (39, -13), (39, 0), (-6, 0)], 3, opaque=True)
    p.l([(16, -24), (16, -28), (23, -28), (23, -24)], 1)
    p.l([(2, -12), (18, -12)])
    p.o(28, -12, 2.6)
    p.c([(-2, 0), (-3, 10), (5, 16), (15.1, 14)])
    p.c([(6, 0), (4, 5), (7, 10)])
    p.c([(32, 38), (32, 47), (40, 53), (52, 50), (66, 54)])


def mario(p):  # mushroom
    cap = (spline([(-41, 4), (-39, -24), (-17, -45), (17, -45), (39, -24), (41, 4)])
           + spline([(41, 4), (21, 10), (0, 11), (-21, 10), (-41, 4)])[1:])
    p.path(cap, True)
    p.c([(-18, 10), (-23, 32), (-13, 45), (13, 45), (23, 32), (18, 10)])
    p.o(0, -22, 11.5)
    with p.inside(cap):
        p.o(-41, -8, 13)
        p.o(41, -8, 13)


def mega_man(p):  # gear
    pts = []
    for i in range(8):
        for d, r in ((-15, 31), (-9, 43), (9, 43), (15, 31)):
            a = math.radians(i * 45 + d)
            pts.append((r * math.cos(a), r * math.sin(a)))
    p.pg(pts, 2)
    p.o(0, 0, 14)


def metroid(p):  # ringed planet
    planet = arc(0, 2, 27, 27, 0, 354)
    p.path(planet, True)
    ring = turn(arc(0, 2, 47, 13, 0, 360), -20, 0, 2)
    p.runs(ring, lambda x, y: math.hypot(x, y - 2) > 27 or (y - 2) > -0.36 * x)
    with p.inside(planet):
        p.c([(-34, -6), (-6, -16), (22, -28)])
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


def pokemon(p):  # pikachu
    p.pg([(52, -6), (34, 20), (40, 28), (16, 44), (49, 36), (43, 29), (65, 4)], 1.5)
    p.o(-21, 19, 4.5, 7, 33, opaque=True)
    p.o(21, 19, 4.5, 7, -33, opaque=True)
    p.pg([(-17, 0), (17, 0), (24, 32), (18, 46), (-18, 46), (-24, 32)], 8, opaque=True)
    ear = spline([(-20, -14), (-31, -32), (-36, -50)]) + spline([(-36, -50), (-24, -36), (-11, -22)])[1:]
    for flip in (False, True):
        side = mirror if flip else list
        p.path(side(ear), True)
        with p.inside(side(ear)):
            p.l(side([(-36.3, -32.4), (-19.7, -43.5)]))
        p.path(side(arc(-13, 47, 8, 3.5, 0, 354)), True, opaque=True)
    p.path(spline([(0, -26), (14, -24), (24, -16), (27, -6), (21, 6), (0, 10), (-21, 6), (-27, -6), (-24, -16),
                   (-14, -24)], closed=True), True, opaque=True)
    for x in (-1, 1):
        p.o(12 * x, -10, 2.2)
        p.o(12 * x, -10, 0.8)
        p.o(18 * x, -1, 4.5)
    p.l([(-0.6, -5.5), (0.6, -5.5)])
    p.c([(-5, -2.5), (-2.5, 0.5), (0, -2), (2.5, 0.5), (5, -2.5)])


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
    body = arc(0, 16, 25, 29, 0, 354)
    p.path(body, True)
    with p.inside(body):
        p.c([(-30, 3), (0, 8), (30, 3)])
        p.c([(-30, 24), (0, 29), (30, 24)])
        p.c([(-8, -16), (-10, 16), (-8, 48)])
        p.c([(8, -16), (10, 16), (8, 48)])
    p.rr(-10, -27, 10, -11, 2.5, opaque=True)
    p.path(spline([(10, -23), (26, -21), (35, -8), (37, 8)]) + spline([(31.5, 8), (30, -6), (23, -15), (10, -17)]),
           True)
    p.o(-21, -19, 8)
    p.l([(-13, -19), (-10, -19)])


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
    with p.inside(side + mirror(side)[::-1]):
        p.c([(-26, -24), (0, -19), (26, -24)])
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
    "adventure": (adventure, (44, 146, 118), -6, 1.0, (0, 0)),
    "fighting": (fighting, (232, 112, 42), -8, 0.92, (-22, 0)),
    "horror": (horror, (72, 52, 96), 4, 1.0, (0, 0)),
    "puzzle": (puzzle, (228, 186, 42), -6, 1.0, (0, 0)),
    "racing": (racing, (96, 104, 116), -4, 1.0, (0, 0)),
    "rhythm": (rhythm, (236, 118, 108), -4, 1.0, (0, 0)),
    "rpg": (rpg, (122, 84, 184), 8, 1.0, (0, 0)),
    "sports": (sports, (72, 160, 74), 10, 1.0, (0, 0)),
    "surprise": (surprise, (201, 62, 110), -6, 1.0, (0, 10)),
    "backlog": (backlog, (100, 116, 160), -6, 1.0, (6, 0)),
    "benchmarks": (benchmarks, (104, 64, 214), -6, 0.95, (-10, 0)),
    "completed": (completed, (212, 160, 40), 6, 1.0, (-6, 0)),
    "decades": (decades, (164, 84, 116), -7, 1.0, (-6, 0)),
    "favorites": (favorites, (228, 70, 100), -8, 1.0, (-4, 0)),
    "hacks-homebrew": (hacks_homebrew, (170, 150, 44), 38, 1.0, (0, 0)),
    "hard-mode": (hard_mode, (44, 40, 52), -6, 1.0, (0, 0)),
    "holiday": (holiday, (100, 168, 222), 10, 1.0, (0, 0)),
    "imports": (imports, (24, 116, 150), 0, 1.0, (-4, 0)),
    "kids": (kids, (104, 196, 188), -6, 1.0, (0, 0)),
    "late-night": (late_night, (58, 48, 120), 0, 1.0, (0, 0)),
    "now-playing": (now_playing, (76, 100, 236), -8, 0.95, (-12, 0)),
    "soundtracks": (soundtracks, (230, 70, 160), -8, 1.0, (-22, 0)),
    "3d-platformers": (platformers_3d, (240, 150, 40), -4, 1.0, (0, 0)),
    "action-classics": (action_classics, (198, 66, 58), 32, 1.0, (0, 0)),
    "arcade-brawlers": (arcade_brawlers, (206, 84, 44), -8, 1.0, (0, 0)),
    "arcade-classics": (arcade_classics, (70, 78, 170), 6, 1.0, (0, 0)),
    "best-of-16-bit": (best_of_16_bit, (112, 96, 176), -8, 1.0, (6, 0)),
    "castlevania": (castlevania, (120, 36, 60), -6, 0.88, (-12, 0)),
    "co-op": (co_op, (36, 150, 160), -4, 1.0, (-24, 0)),
    "dungeon-crawlers": (dungeon_crawlers, (104, 92, 80), 28, 1.0, (0, 0)),
    "fan-translations": (fan_translations, (214, 92, 124), -5, 1.0, (-26, 0)),
    "final-fantasy": (final_fantasy, (64, 132, 206), 10, 1.0, (0, 0)),
    "fps": (fps, (156, 60, 48), 8, 1.0, (0, 0)),
    "handheld-greatest-hits": (handheld_greatest_hits, (120, 170, 60), -8, 1.0, (0, 0)),
    "hidden-gems": (hidden_gems, (40, 160, 150), -6, 1.0, (0, 0)),
    "jrpg-essentials": (jrpg_essentials, (176, 124, 44), -6, 1.0, (0, 0)),
    "kart-racers": (kart_racers, (224, 76, 64), -8, 1.0, (-14, 0)),
    "kirby": (kirby, (238, 132, 166), 0, 1.0, (-10, 0)),
    "licensed-classics": (licensed_classics, (60, 68, 84), -6, 1.0, (-6, 0)),
    "life-sim": (life_sim, (104, 172, 84), -5, 0.92, (-34, 0)),
    "light-gun": (light_gun, (228, 120, 52), -10, 0.95, (-36, 0)),
    "mario": (mario, (216, 56, 56), -6, 1.0, (0, 0)),
    "mega-man": (mega_man, (48, 136, 216), 10, 1.0, (-8, 0)),
    "metroid": (metroid, (224, 104, 36), 0, 1.0, (-6, 0)),
    "metroidvanias": (metroidvanias, (84, 76, 150), -6, 1.0, (0, 0)),
    "pinball": (pinball, (170, 70, 170), -6, 1.0, (-14, 0)),
    "platformers": (platformers, (68, 148, 220), -5, 1.0, (0, 0)),
    "pokemon": (pokemon, (236, 180, 30), -4, 0.86, (-74, 0)),
    "resident-evil": (resident_evil, (140, 40, 44), 16, 1.0, (0, 0)),
    "retro-oddities": (retro_oddities, (176, 112, 52), -6, 1.0, (6, 0)),
    "rpg-series": (rpg_series, (132, 72, 148), -10, 1.0, (0, 0)),
    "run-and-gun": (run_and_gun, (96, 124, 68), 12, 1.0, (0, 0)),
    "shmups": (shmups, (44, 60, 120), 16, 1.0, (0, 0)),
    "short-sessions": (short_sessions, (60, 150, 190), 8, 1.0, (0, 0)),
    "sonic": (sonic, (36, 96, 200), 8, 1.0, (-12, 0)),
    "star-wars": (star_wars, (40, 44, 60), -32, 1.0, (0, 0)),
    "stealth": (stealth, (86, 110, 100), -5, 1.0, (0, 6)),
    "strategy-tactics": (strategy_tactics, (150, 102, 62), 5, 1.0, (0, 0)),
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
    """The strokes (in px) as an L mask at SS scale."""
    size = (W * SS, H * SS)
    img = Image.new("L", size, 0)
    r = STROKE / 2 * SS
    for pts, closed, opaque, clip in strokes:
        if opaque:
            ImageDraw.Draw(img).polygon([(x * SS, y * SS) for x, y in pts], fill=0)
        layer = Image.new("L", size, 0) if clip else img
        draw = ImageDraw.Draw(layer)
        for x, y in _resample(pts, closed, 0.5):
            draw.ellipse((x * SS - r, y * SS - r, x * SS + r, y * SS + r), fill=255)
        if clip:
            mask = Image.new("L", size, 0)
            ImageDraw.Draw(mask).polygon([(x * SS, y * SS) for x, y in clip], fill=255)
            img.paste(255, mask=ImageChops.multiply(layer, mask))
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

    def place(pts):
        return [(CENTER[0] + dx + x * UNIT * scale, CENTER[1] + dy + y * UNIT * scale) for x, y in turn(pts, rot)]

    strokes = [(place(pts), closed, opaque, clip and place(clip)) for pts, closed, opaque, clip in pen.strokes]
    band = Image.new("L", (W, H), 0)
    for y in range(H):
        left, right = (edge - BAND[2] * (y + 0.5) for edge in BAND[:2])
        for x in range(int(left), min(W, int(right) + 1)):
            band.putpixel((x, y), round(255 * (min(x + 1, right) - max(x, left))))
    img = Image.new("RGB", (W, H), colour)
    img.paste(Image.new("RGB", (W, H), INK), mask=_ink(strokes, rng))
    img.putalpha(band)
    return img


def write_readme():
    """Write art/README.md, a gallery of every picture so they can be browsed on GitHub. Sync never copies it."""
    data = os.path.join(OUT, "..", "..", "..")
    with open(os.path.join(OUT, "..", "art.json")) as f:
        names = {"surprise": "Surprise", **json.load(f)}
    for file in os.listdir(os.path.join(data, "sets")):
        if file.endswith(".json"):
            with open(os.path.join(data, "sets", file)) as f:
                names.setdefault(file[:-5], json.load(f)["name"])
    ids = sorted(f[:-4] for f in os.listdir(OUT) if f.endswith(".png"))
    cell = '<td align="center" valign="top"><img src="{0}.png" width="120" alt="{1}"><br><sub>{1}<br><code>{0}</code></sub></td>'
    rows = ["<tr>" + "".join(cell.format(i, html.escape(names.get(i, i))) for i in ids[n:n + 6]) + "</tr>" for n in range(0, len(ids), 6)]
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("# Art Book Next collection art\n\n"
                "Collection art for the [Art Book Next](https://github.com/anthonycaccese/art-book-next-es-de) theme by "
                "Anthony Caccese. These pictures are not part of that theme: they are LLM-generated, for my own personal use.\n\n"
                "Generated by `tools/gen_theme_art.py`; don't edit by hand.\n\n"
                "<table>\n" + "\n".join(rows) + "\n</table>\n")


def main(ids):
    for art_id in ids or ART:
        render(art_id).save(os.path.join(OUT, f"{art_id}.png"), optimize=True)
        print(art_id)
    write_readme()


if __name__ == "__main__":
    main(sys.argv[1:])
