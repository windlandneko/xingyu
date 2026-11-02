'''Xingyu (兴语): a variable font for the alien script of Message From Aliens.

Every stroke segment is a capsule, so the wght axis (100-900) only changes the stroke width. ss01 turns ASCII
numbers into base-7 numerals (the game's own formatting, plus two base-7 decimal places); ss02 turns the script's
English words into glyphs.

Code points: F7000 numerals (8 per exponent), F7080 tokens, F7100 words by the game's dictionary categories,
F7A00 overflow. A character keeps its code point while it is in the game.

Inputs (source/): words.csv and glyphs.json from prepare.py; units.json, registry.csv and blocks.csv are kept by hand
or by this script.
Outputs (data/): Xingyu-VF.ttf, Xingyu-VF.woff2 and xingyu.json.

  python3 build_font.py'''
import csv
import heapq
import itertools
import json
import math
import re
from pathlib import Path

from fontTools import varLib
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import flagOverlapSimple

from optimize_font import save_font

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'source'
DATA = HERE / 'data'
REGISTRY, BLOCKS = SOURCE / 'registry.csv', SOURCE / 'blocks.csv'
UPM = 1000
ASCENT, DESCENT = 1160, -288                         # CJK line box, as in Source Han Sans
VERSION = 1.0                                          # first built from the released game
AUTHOR = 'windlandneko'

# vertical design: alien glyphs sit in the CJK ideographic box (ink of 国 in Source Han Sans / HarmonyOS
# runs about -80..795, centre ~358); Latin x-height / cap height near theirs (540 / 733)
ALIEN_ADV, ALIEN_CY, ALIEN_SPAN = 1000, 358, 800     # the game: 1-unit cell, 0.8 box (centre lines)
VORIGIN = ALIEN_CY + ALIEN_ADV // 2                  # top of the vertical cell, so glyphs sit centred in it
LAT_NARROW = 0.9                                     # letters are drawn on a square grid, then narrowed
LAT_U = 53.0                                         # Latin grid unit: x-height 10u, caps 14u

# weight axis: stroke width in font units at each master
MASTERS = {100: 16, 400: 34, 700: 58, 900: 80}   # Regular matches the game's sprites (~34, 4.2% of the box)
REGULAR = MASTERS[400]
KEEP = 0.2        # above Regular a dense glyph keeps this share of its Regular gap between strokes,
FLOOR = 0.5       # but always gains at least this share of the axis' growth, so heavy weights stay even
INSTANCES = {'Thin': 100, 'Light': 300, 'Regular': 400, 'Medium': 500, 'Bold': 700, 'Black': 900}

PUA0 = 0xF7000       # clear of UCSUR (up to F2FFF) and Nerd Fonts (F0001-F1AF0)
TOKEN0, WORD0, OVERFLOW0 = PUA0 + 0x80, PUA0 + 0x100, PUA0 + 0xA00

# ---------- geometry: centre lines -> capsules ----------

QK = 1 / math.cos(math.radians(22.5))


def capsule(pen, p0, p1, r):
    '''One stroke segment as a closed clockwise contour: left side, round end, right side, round start. Every
    master gets the same points: arcs end exactly on the side lines' end points.'''
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    a = math.atan2(ux, -uy)         # angle of the left normal (-uy, ux)
    side = lambda x, y, s: (round(x - s * uy * r), round(y + s * ux * r))

    def arc(cx, cy, a0, end):       # half turn clockwise from angle a0, four 45 degree quadratics
        for i in range(4):
            am, a1 = a0 - math.radians(45 * i + 22.5), a0 - math.radians(45 * (i + 1))
            on = end if i == 3 else (round(cx + r * math.cos(a1)), round(cy + r * math.sin(a1)))
            pen.qCurveTo((round(cx + r * QK * math.cos(am)), round(cy + r * QK * math.sin(am))), on)
    start = side(x0, y0, 1)
    pen.moveTo(start)
    pen.lineTo(side(x1, y1, 1))
    arc(x1, y1, a, side(x1, y1, -1))
    pen.lineTo(side(x0, y0, -1))
    arc(x0, y0, a + math.pi, start)
    pen.closePath()


def dot(pen, c, r):
    cx, cy = c
    pen.moveTo((round(cx + r), round(cy)))
    for i in range(8):
        am, a1 = -math.radians(45 * i + 22.5), -math.radians(45 * (i + 1))
        pen.qCurveTo((round(cx + r * QK * math.cos(am)), round(cy + r * QK * math.sin(am))),
                     (round(cx + r * math.cos(a1)), round(cy + r * math.sin(a1))))
    pen.closePath()


def draw(polylines, dots, width):
    '''Polylines (and lone dots) in font units -> a TrueType glyph at this stroke width.'''
    pen = TTGlyphPen(None)
    r = width / 2
    for pl in polylines:
        for p0, p1 in itertools.pairwise(pl):
            if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-6:
                capsule(pen, p0, p1, r)
    for c in dots:
        dot(pen, c, max(r * 1.25, 18))
    g = pen.glyph()
    if g.numberOfContours > 0:
        g.flags[0] |= flagOverlapSimple
    return g


def segment_gap(a, b, c, d):
    '''Distance between segments ab and cd; 0 when they cross.'''
    side = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
        return 0

    def point(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
    return min(point(a, c, d), point(b, c, d), point(c, a, b), point(d, a, b))


def clearance(polylines):
    '''The smallest gap still open at Regular (the game's own weight): how much room the glyph has to get bold.
    Narrower gaps are already closed at Regular, and they stay closed.'''
    segs = [s for pl in polylines for s in itertools.pairwise(pl) if math.dist(*s) > 1e-6]
    gaps = (segment_gap(*s, *t) for s, t in itertools.combinations(segs, 2))
    return min((g for g in gaps if g > REGULAR), default=None)


def fitted(width, clear):
    '''Stroke width for one glyph: every glyph follows the axis up to Regular; above it the stroke approaches
    (smoothly) the width that leaves KEEP of the glyph's Regular gap, so dense glyphs stay open, but never grows
    by less than FLOOR of the axis.'''
    if clear is None or width <= REGULAR:
        return width
    room, d = max((1 - KEEP) * (clear - REGULAR), REGULAR / 4), width - REGULAR
    return REGULAR + max(d / (1 + (d / room) ** 4) ** 0.25, FLOOR * d)


def alien_lines(strokes):
    '''Game coordinates -> font units, the way the game fits a glyph into its 0.8-wide box: centred on the origin,
    shrunk (never enlarged) so the largest |coordinate| reaches the box edge.'''
    sc = ALIEN_SPAN / 2 / max([0.4] + [abs(c) for s in strokes for p in s for c in p])
    return [[(ALIEN_ADV / 2 + x * sc, ALIEN_CY + y * sc) for x, y in s] for s in strokes], []


def string_to_pos(s):
    out = []
    for part in s.split(';'):
        v = [float(x) for x in re.findall(r'[+-]?\d+(?:\.\d+)?', part)]
        out.append([[v[i], v[i + 1]] for i in range(0, len(v) - 1, 2)])
    xs = [p[0] for s_ in out for p in s_]
    ys = [p[1] for s_ in out for p in s_]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[[x - cx, y - cy] for x, y in s_] for s_ in out]


def numeral_strokes(digit_src, e):
    '''The game's "{d}e{e}": the digit with |e| bars above (e > 0) or below, recentred.'''
    s = 1 if e > 0 else -1
    bars = [[[-3, s * (3 + k)], [3, s * (3 + k)]] for k in range(abs(e))]
    dy = -(e - s) / 2 if e else 0
    return [[[x, y + dy] for x, y in st] for st in string_to_pos(digit_src) + bars]


# ---------- Latin: a small monoline geometric alphabet on a 10u x-height grid ----------
# ('L', [x, y, ...]) polyline; ('A', cx, cy, r, a0, a1) arc in degrees, a1 < a0 runs clockwise; ('E', cx, cy, rx, ry,
# a0, a1) the same on an ellipse; ('T', px, py, cx, cy, rx, ry, turn[, a1]) a line running into an ellipse; ('D', x, y)
LATIN = {
    'a': [('A', 5, 5, 5, 0, 360), ('L', [10, 10, 10, 0])],
    'b': [('L', [0, 14, 0, 0]), ('A', 5, 5, 5, 0, 360)],
    'c': [('A', 5, 5, 5, 40, 320)],
    'd': [('L', [10, 14, 10, 0]), ('A', 5, 5, 5, 0, 360)],
    'e': [('L', [0, 5, 10, 5]), ('A', 5, 5, 5, 0, 320)],
    'f': [('L', [2.6, 0, 2.6, 11]), ('A', 5.6, 11, 3, 180, 50), ('L', [0, 10, 6.2, 10])],
    'g': [('A', 5, 5, 5, 0, 360), ('L', [10, 10, 10, 0]), ('A', 5, 0, 5, 0, -160)],
    'h': [('L', [0, 14, 0, 0]), ('A', 5, 5, 5, 180, 0), ('L', [10, 5, 10, 0])],
    'i': [('L', [0, 0, 0, 10]), ('D', 0, 13.5)],
    'j': [('L', [3, 10, 3, -2]), ('A', 0, -2, 3, 0, -150), ('D', 3, 13.5)],
    'k': [('L', [0, 14, 0, 0]), ('L', [9, 10, 0, 3.5]), ('L', [3.2, 6, 9, 0])],
    'l': [('L', [0, 14, 0, 0])],
    'm': [('L', [0, 10, 0, 0]), ('A', 3, 7, 3, 180, 0), ('L', [6, 7, 6, 0]), ('A', 9, 7, 3, 180, 0),
          ('L', [12, 7, 12, 0])],
    'n': [('L', [0, 10, 0, 0]), ('A', 5, 5, 5, 180, 0), ('L', [10, 5, 10, 0])],
    'o': [('A', 5, 5, 5, 0, 360)],
    'p': [('L', [0, 10, 0, -5]), ('A', 5, 5, 5, 0, 360)],
    'q': [('L', [10, 10, 10, -5]), ('A', 5, 5, 5, 0, 360)],
    'r': [('L', [0, 10, 0, 0]), ('A', 5, 5, 5, 180, 80)],
    's': [('E', 4, 7.55, 3.5, 2.45, 30, 270), ('E', 4, 2.55, 4, 2.55, 90, -150)],
    't': [('L', [2.6, 12.6, 2.6, 2.8]), ('A', 5.4, 2.8, 2.8, 180, 275), ('L', [0, 10, 6.2, 10])],
    'u': [('L', [0, 10, 0, 5]), ('A', 5, 5, 5, 180, 360), ('L', [10, 10, 10, 0])],
    'v': [('L', [0, 10, 5, 0, 10, 10])],
    'w': [('L', [0, 10, 3, 0, 6.5, 9, 10, 0, 13, 10])],
    'x': [('L', [0, 10, 10, 0]), ('L', [0, 0, 10, 10])],
    'y': [('L', [0, 10, 5, 0]), ('L', [10, 10, 2.5, -5])],
    'z': [('L', [0, 10, 10, 10, 0, 0, 10, 0])],
    'A': [('L', [0, 0, 6, 14, 12, 0]), ('L', [2.6, 6, 9.4, 6])],
    'B': [('L', [5.5, 7, 0, 7, 0, 14, 5.5, 14]), ('A', 5.5, 10.5, 3.5, 90, -90), ('L', [0, 7, 0, 0, 6, 0]),
          ('A', 6, 3.5, 3.5, -90, 90)],
    'C': [('A', 7, 7, 7, 45, 315)],
    'D': [('L', [4, 14, 0, 14, 0, 0, 4, 0]), ('A', 4, 7, 7, -90, 90)],
    'E': [('L', [10, 14, 0, 14, 0, 0, 10, 0]), ('L', [0, 7, 8, 7])],
    'F': [('L', [10, 14, 0, 14, 0, 0]), ('L', [0, 7, 8, 7])],
    'G': [('A', 7, 7, 7, 45, 360), ('L', [14, 7, 8, 7])],
    'H': [('L', [0, 0, 0, 14]), ('L', [11, 0, 11, 14]), ('L', [0, 7, 11, 7])],
    'I': [('L', [0, 0, 0, 14])],
    'J': [('L', [8, 14, 8, 4]), ('A', 4, 4, 4, 0, -180)],
    'K': [('L', [0, 0, 0, 14]), ('L', [10, 14, 0, 4]), ('L', [3.5, 7.5, 10, 0])],
    'L': [('L', [0, 14, 0, 0, 9, 0])],
    'M': [('L', [0, 0, 0, 14, 7, 2, 14, 14, 14, 0])],
    'N': [('L', [0, 0, 0, 14, 11, 0, 11, 14])],
    'O': [('A', 7, 7, 7, 0, 360)],
    'P': [('L', [0, 0, 0, 14, 5.5, 14]), ('A', 5.5, 10, 4, 90, -90), ('L', [5.5, 6, 0, 6])],
    'Q': [('A', 7, 7, 7, 0, 360), ('L', [9, 4, 14, -1])],
    'R': [('L', [0, 0, 0, 14, 5.5, 14]), ('A', 5.5, 10, 4, 90, -90), ('L', [5.5, 6, 0, 6]), ('L', [5, 6, 10.5, 0])],
    'S': [('E', 4.7, 10.6, 4.0, 3.4, 35, 270), ('E', 4.7, 3.6, 4.6, 3.6, 90, -145)],
    'T': [('L', [0, 14, 12, 14]), ('L', [6, 14, 6, 0])],
    'U': [('L', [0, 14, 0, 5.5]), ('A', 5.5, 5.5, 5.5, 180, 360), ('L', [11, 5.5, 11, 14])],
    'V': [('L', [0, 14, 6, 0, 12, 14])],
    'W': [('L', [0, 14, 4, 0, 8, 12, 12, 0, 16, 14])],
    'X': [('L', [0, 14, 11, 0]), ('L', [0, 0, 11, 14])],
    'Y': [('L', [0, 14, 6, 7, 12, 14]), ('L', [6, 7, 6, 0])],
    'Z': [('L', [0, 14, 11, 14, 0, 0, 11, 0])],
    'zero': [('E', 4.4, 7, 4.4, 7, 0, 360)],
    'one': [('L', [1.2, 11.4, 4.6, 14, 4.6, 0])],
    'two': [('T', 0.2, 0, 4.4, 9.8, 4.2, 4.2, 1, 165), ('L', [0.2, 0, 8.8, 0])],
    'three': [('E', 4.4, 10.6, 3.6, 3.4, 155, -90), ('E', 4.4, 3.6, 4.3, 3.6, 90, -155)],
    'four': [('L', [6.8, 0, 6.8, 14, 0, 4.2, 9.2, 4.2])],
    'five': [('L', [8.4, 14, 1.4, 14, 0.98, 7.17]), ('E', 4.4, 4.4, 4.4, 4.4, 141, -145)],
    'six': [('T', 6.0, 14, 4.4, 4.3, 4.4, 4.3, 1)],
    'seven': [('L', [0, 14, 8.8, 14, 3, 0])],
    'eight': [('E', 4.4, 10.7, 3.5, 3.3, 0, 360), ('E', 4.4, 3.7, 4.2, 3.7, 0, 360)],
    'nine': [('T', 2.8, 0, 4.4, 9.7, 4.4, 4.3, 1)],
    'period': [('D', 0, 0)],
    'comma': [('L', [0.6, 0.6, -0.6, -2])],
    'colon': [('D', 0, 0), ('D', 0, 9)],
    'semicolon': [('L', [0.6, 0.6, -0.6, -2]), ('D', 0.6, 9)],
    'exclam': [('L', [0, 14, 0, 4]), ('D', 0, 0)],
    'question': [('A', 4.5, 10, 4.5, 160, -60), ('L', [6.75, 6.1, 4.5, 4]), ('D', 4.5, 0)],
    'quotesingle': [('L', [0, 14, 0, 10])],
    'quotedbl': [('L', [0, 14, 0, 10]), ('L', [3, 14, 3, 10])],
    'hyphen': [('L', [0, 5, 6, 5])],
    'underscore': [('L', [0, -2, 10, -2])],
    'parenleft': [('A', 9, 5.5, 9, 130, 230)],
    'parenright': [('A', -4, 5.5, 9, 50, -50)],
    'bracketleft': [('L', [3, 14, 0, 14, 0, -2, 3, -2])],
    'bracketright': [('L', [0, 14, 3, 14, 3, -2, 0, -2])],
    'slash': [('L', [0, -2, 8, 14])],
    'plus': [('L', [0, 5, 10, 5]), ('L', [5, 0, 5, 10])],
    'equal': [('L', [0, 3.5, 10, 3.5]), ('L', [0, 7.5, 10, 7.5])],
    'percent': [('A', 2.5, 11.5, 2.5, 0, 360), ('A', 9.5, 2.5, 2.5, 0, 360), ('L', [1, 0, 11, 14])],
    'asterisk': [('L', [3, 14, 3, 8]), ('L', [0, 12.5, 6, 9.5]), ('L', [0, 9.5, 6, 12.5])],
    'numbersign': [('L', [3, 0, 4.5, 14]), ('L', [7, 0, 8.5, 14]), ('L', [0, 4.5, 11, 4.5]), ('L', [0, 9.5, 11, 9.5])],
}
# ink side bearings (font units, the same at every weight), after Source Han Sans scaled to this x-height
SIDEBEARINGS = {'a': (60, 80), 'b': (90, 50), 'c': (50, 25), 'd': (50, 90), 'e': (50, 40), 'f': (30, 10),
                'g': (50, 90), 'h': (90, 80), 'i': (75, 75), 'j': (-45, 75), 'k': (90, 10), 'l': (90, 40),
                'm': (90, 85), 'n': (90, 80), 'o': (50, 50), 'p': (90, 50), 'q': (50, 90), 'r': (90, 35),
                's': (30, 35), 't': (30, 30), 'u': (80, 90), 'v': (15, 15), 'w': (25, 25), 'x': (15, 15),
                'y': (15, 15), 'z': (40, 40), 'A': (5, 5), 'B': (100, 45), 'C': (55, 35), 'D': (100, 60),
                'E': (100, 55), 'F': (100, 30), 'G': (55, 70), 'H': (100, 100), 'I': (100, 100), 'J': (35, 95),
                'K': (100, 5), 'L': (100, 30), 'M': (100, 100), 'N': (100, 100), 'O': (55, 55), 'P': (100, 50),
                'Q': (55, 40), 'R': (100, 25), 'S': (45, 40), 'T': (30, 30), 'U': (95, 95), 'V': (0, 0),
                'W': (25, 25), 'X': (15, 15), 'Y': (0, 0), 'Z': (50, 45), 'zero': (50, 50), 'one': (85, 65),
                'two': (40, 50), 'three': (30, 55), 'four': (20, 30), 'five': (25, 50), 'six': (55, 40),
                'seven': (50, 45), 'eight': (45, 45), 'nine': (45, 55), 'period': (70, 70), 'comma': (50, 55),
                'colon': (70, 70), 'semicolon': (50, 55), 'exclam': (95, 95), 'question': (40, 50),
                'quotesingle': (90, 90), 'quotedbl': (90, 90), 'hyphen': (45, 45), 'underscore': (15, 15),
                'parenleft': (90, 40), 'parenright': (40, 90), 'bracketleft': (105, 35), 'bracketright': (35, 100),
                'slash': (10, 15), 'plus': (35, 35), 'equal': (35, 35), 'percent': (40, 40), 'asterisk': (65, 65),
                'numbersign': (40, 30)}

LAT = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
LATIN_CHARS = {**{c: c for c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'},
               **dict(zip('0123456789', LAT)),
               '.': 'period', ',': 'comma', ':': 'colon', ';': 'semicolon', '!': 'exclam', '?': 'question',
               "'": 'quotesingle', '"': 'quotedbl', '-': 'hyphen', '_': 'underscore', '(': 'parenleft',
               ')': 'parenright', '[': 'bracketleft', ']': 'bracketright', '/': 'slash', '+': 'plus', '=': 'equal',
               '%': 'percent', '*': 'asterisk', '#': 'numbersign'}


def ellipse_arc(cx, cy, rx, ry, a0, a1):
    n = max(2, math.ceil(abs(a1 - a0) / 10))
    angles = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
    return [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in angles]


def tangent_in(px, py, cx, cy, rx, ry, turn, a1=None):
    '''A straight stroke from (px, py) that runs smoothly into the ellipse, then follows it (turn +1: counter-
    clockwise, -1: clockwise) to angle a1, or all the way round when a1 is None.'''
    def miss(a):
        t = math.radians(a)
        qx, qy = cx + rx * math.cos(t), cy + ry * math.sin(t)
        tx, ty = -turn * rx * math.sin(t), turn * ry * math.cos(t)
        dx, dy = qx - px, qy - py
        if dx * tx + dy * ty <= 0:
            return 9e9
        return abs(dx * ty - dy * tx) / math.hypot(dx, dy) / math.hypot(tx, ty)
    a0 = min((i / 10 for i in range(3600)), key=miss)
    if a1 is None:
        a1 = a0 + 360 * turn
    while (a1 - a0) * turn < 0:
        a1 += 360 * turn
    return [(px, py)] + ellipse_arc(cx, cy, rx, ry, a0, a1)


def latin_lines(name):
    '''Commands on the grid -> font units, centre lines starting at x = 0; also returns their width.'''
    lines, dots = [], []
    for cmd in LATIN[name]:
        if cmd[0] == 'L':
            v = cmd[1]
            lines.append([(v[i], v[i + 1]) for i in range(0, len(v), 2)])
        elif cmd[0] == 'A':
            _, cx, cy, r, a0, a1 = cmd
            lines.append(ellipse_arc(cx, cy, r, r, a0, a1))
        elif cmd[0] == 'E':
            lines.append(ellipse_arc(*cmd[1:]))
        elif cmd[0] == 'T':
            lines.append(tangent_in(*cmd[1:]))
        else:
            dots.append((cmd[1], cmd[2]))
    xs = [p[0] for l in lines for p in l] + [d[0] for d in dots]
    x0 = min(xs)
    k = LAT_U * (LAT_NARROW if name.isalpha() and len(name) == 1 else 1)
    f = lambda p: ((p[0] - x0) * k, p[1] * LAT_U)
    return [[f(p) for p in l] for l in lines], [f(d) for d in dots], (max(xs) - x0) * k


# ---------- glyph names ----------

A = lambda d, c: f'acc.a{d}c{c}'
B = lambda d, c: f'acc.b{d}c{c}'
D = lambda d: f'b7.{d}'
DC = 'b7.carry'
L = lambda d, k: f'lead.{d}k{k}'
EXP = lambda k: f'exp.{k}'
G = lambda d, e: f'num.{d}e{e}'.replace('-', 'm')
FRA = lambda f, c: f'fr.a{f}c{c}'
FRB = lambda f, c: f'fr.b{f}c{c}'
SL = lambda i, d: f'slot{i}.{d}'
SLC = lambda i: f'slot{i}.carry'
POINT, POINTBIG, POINTZ = 'pt', 'pt.big', 'pt.zero'
EMPTY, TAIL, BIGE = 'nul.lz', 'nul.sci', 'nul.big'
NUMBER_WORDS = ('negative', 'exp7')   # ss01 writes these; a space next to them is kept
SPACE_ADV = 300
JOINRUN = 8                           # longest run of spaces that still loses one
G_EXPS = range(-9, 10)
NUMERALS = [(d, e) for d in range(7) for e in G_EXPS if d or e == 0]
MAXDIG, PAD, KMAX = 20, 5, 24
FRACS = 3                 # base-7 fractional digits extracted: two shown, one to round on
WORDC = lambda w: 'w.' + w.replace('-', '_')         # glyph names cannot hold a hyphen


carry = lambda v: (v % 7, v // 7)
cls = lambda xs: '[' + ' '.join(xs) + ']'


# ---------- features ----------

def feature_code(words, joined):
    f = []
    w = f.append
    lookup = lambda name, rules: w(f'lookup {name} {{\n' + ''.join(f'  {r};\n' for r in rules) + f'}} {name};\n')
    single = lambda name, rule: w(f'lookup {name} {{ {rule}; }} {name};\n')
    subs = lambda pairs: [f'sub {a} by {b}' for a, b in pairs]
    Dall = [D(d) for d in range(7)]
    Dx = Dall + [DC]
    w('languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n')
    w(f'@LAT = {cls(LAT)};\n@D = {cls(Dall)};\n@DX = {cls(Dx)};\n')

    # ===== ss02: words =====
    wc = [LATIN_CHARS[c] for c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789']
    var = lambda g, v: f'{g}.{v}'
    variants = [var(g, v) for g in wc for v in ('init', 'fina', 'isol')]
    w(f'@WC = {cls(wc)};\n@WCANY = {cls(wc + variants)};\n')
    for v in ('init', 'fina', 'isol'):
        lookup(f'TO_{v}', subs((g, var(g, v)) for g in wc))
    # word starts (a word char after a non-word char), then word ends
    lookup('WSTART', ["ignore sub @WCANY @WC'", "sub @WC' lookup TO_init @WC", "sub @WC' lookup TO_isol"])
    lookup('WEND', ["ignore sub @WC' @WCANY", "sub @WCANY @WC' lookup TO_fina"])
    # whole words; the game's own numeral tokens "3e2", "3e-1"
    lig = []
    for word in sorted(words, key=lambda s: -len(s)):
        gs = [LATIN_CHARS[c] for c in word]
        seq = [var(gs[0], 'isol')] if len(gs) == 1 else [var(gs[0], 'init')] + gs[1:-1] + [var(gs[-1], 'fina')]
        lig.append((' '.join(seq), WORDC(word)))
    for d, e in NUMERALS:
        if e > 0:
            lig.append((f"{var(LAT[d], 'init')} e {var(LAT[e], 'fina')}", G(d, e)))
        elif e < 0:
            lig.append((f"{var(LAT[d], 'init')} {var('e', 'fina')} hyphen {var(LAT[-e], 'isol')}", G(d, e)))
    lookup('WORDS', subs(lig))
    lookup('WREVERT', subs((v, v.rsplit('.', 1)[0]) for v in variants))

    # ===== ss01: numbers =====
    # past MAXDIG integer digits the arithmetic cannot hold the number: its digits hide as .isol until the end
    KEEP = cls(var(g, 'isol') for g in LAT)
    lookup('LONG', ["ignore sub @LAT @LAT'", "ignore sub @LAT period @LAT'", f"sub {KEEP} period @LAT' lookup TO_isol",
                    f"sub {KEEP} @LAT' lookup TO_isol", "sub @LAT' lookup TO_isol" + ' @LAT' * MAXDIG])
    single('TONEG', f'sub hyphen by {WORDC("negative")}')
    # a hyphen right after a digit joins (2017-11-02), it does not negate
    lookup('NEGSIGN', [f"ignore sub [@LAT {' '.join(var(g, 'isol') for g in LAT)}] hyphen' @LAT", "sub hyphen' lookup TONEG @LAT"])
    # decimals: the point between digits, fraction digits set aside, three result slots after the point
    single('TOPOINT', f'sub period by {POINT}')
    lookup('TOFR', subs((g, FRA(i, 0)) for i, g in enumerate(LAT)))
    FRAll = [FRA(i, c) for i in range(10) for c in range(7)]
    FRBll = [FRB(i, c) for i in range(10) for c in range(7)]
    lookup('POINTS', ["sub @LAT period' lookup TOPOINT @LAT", f"sub {POINT} @LAT' lookup TOFR",
                      f"sub {cls(FRAll)} @LAT' lookup TOFR"])
    single('SLOTS', f'sub {POINT} by {POINT} {" ".join(SL(i, 0) for i in range(1, FRACS + 1))}')
    # integer part: base-7 zero slots in front of the first digit
    lookup('PADMULT', subs((g, f'{" ".join([A(0, 0)] * PAD)} {g}') for g in LAT))
    lookup('PAD', ["ignore sub @LAT @LAT'", "sub @LAT' lookup PADMULT"])
    # one reverse-chaining pass per decimal digit: slot = own + 3*left + carry-from-right (acc*10 = acc*7 + acc*3)
    for i in range(MAXDIG):
        X, Y = (A, B) if i % 2 == 0 else (B, A)
        Xall = [X(d, c) for d in range(7) for c in range(4)]
        Xb = lambda b: cls([X(b, c) for c in range(4)])
        Yc = lambda c: cls([Y(d, c) for d in range(7)])
        rules = [f"rsub {Xb(b)} @LAT' by {cls([Y(*carry(3 * b + dd)) for dd in range(10)])}" for b in range(7)]
        sums = lambda k: cls([Y(*carry(d + k)) for d in range(7) for _ in range(4)])
        rules += [f"rsub {Xb(b)} {cls(Xall)}' {Yc(c)} by {sums(3 * b + c)}" for b in range(7) for c in range(4)]
        rules += [f"rsub {cls(Xall)}' {Yc(c)} by {sums(c)}" for c in range(4)]
        lookup(f'PASS{i}', rules)
    # fraction: multiply the decimal fraction by 7 (right to left, carry on the glyph); the carry out of its first
    # digit is the next base-7 digit, shifted into the slots
    slots = lambda i: cls([SL(i, x) for x in range(7)])
    for i in range(1, FRACS + 1):
        for d in range(7):
            lookup(f'SET{i}_{d}', subs((SL(i, x), SL(i, d)) for x in range(7)))
    for j in range(FRACS):
        X, Y = (FRA, FRB) if j % 2 == 0 else (FRB, FRA)
        Xall = [X(i, c) for i in range(10) for c in range(7)]
        Yc = lambda c: cls([Y(i, c) for i in range(10)])
        times7 = lambda c: cls([Y((7 * i + c) % 10, (7 * i + c) // 10) for i in range(10) for _ in range(7)])
        lookup(f'FRMUL{j}', [f"rsub {cls(Xall)}' {Yc(c)} by {times7(c)}" for c in range(7)]
               + [f"rsub {cls(Xall)}' by {times7(0)}"])
        lookup(f'FRSHIFT{j}', [f"sub {slots(i)}' lookup SET{i}_{d} {SL(i + 1, d)}"
                               for i in range(1, FRACS) for d in range(7)]
               + [f"sub {slots(FRACS)}' lookup SET{FRACS}_{c} {Yc(c)}" for c in range(7)])
    lookup('NORM', subs((g(d, c), D(d)) for g in (A, B) for d in range(7) for c in range(4)))

    # decimals of 2401 or more: drop the fraction, print the integer part
    single('TOBIG', f'sub {POINT} by {POINTBIG}')
    lookup('BIGPOINT', [f"sub {cls(Dall[1:])}" + ' @D' * (j - 1) + f" {POINT}' lookup TOBIG"
                        for j in range(5, PAD + MAXDIG + 1)])
    SLall = [SL(i, d) for i in range(1, FRACS + 1) for d in range(7)]
    lookup('TOBIGE', subs((g, BIGE) for g in [POINTBIG] + SLall))
    lookup('BIGDROP', [f"sub {POINTBIG}' lookup TOBIGE", f"sub {BIGE} {cls(SLall)}' lookup TOBIGE"])

    # small decimals: round on the third fractional digit, carry left across the point, spell by place
    lookup('INC2', subs((SL(2, d), SL(2, d + 1) if d < 6 else SLC(2)) for d in range(7)))
    single('ROUNDF', f"sub {POINT} {slots(1)} {slots(2)}' lookup INC2 {cls([SL(3, d) for d in range(4, 7)])}")
    incD = cls([D(d + 1) if d < 6 else DC for d in range(7)])
    lookup('CARRYF', [f"rsub {slots(1)}' {SLC(2)} by {cls([SL(1, d + 1) if d < 6 else SLC(1) for d in range(7)])}",
                      f"rsub @D' {POINT} {SLC(1)} by {incD}", f"rsub @D' {DC} by {incD}"])
    z = cls([D(0), DC])
    single('TOPZ', f'sub {POINT} by {POINTZ}')
    single('FZERO', f"sub {z} {z} {z} {z} {z} {POINT}' lookup TOPZ {SL(1, 0)} {cls([SL(2, 0), SLC(2)])}")
    for p in range(5):
        lookup(f'GP{p}', subs((D(d), G(d, p) if d else EMPTY) for d in range(7)) + [f'sub {DC} by {EMPTY}'])
    lookup('DROPD', subs((g, EMPTY) for g in Dx))
    points = cls([POINT, POINTZ])
    lookup('FOUT', [f"sub @DX' lookup {'GP' + str(p) if p < 5 else 'DROPD'}" + ' @DX' * p + f' {points}'
                    for p in range(PAD + MAXDIG + 1)])
    slot_out = []
    for i in range(1, FRACS + 1):
        slot_out += [(SL(i, d), G(d, -i) if d and i <= 2 else EMPTY) for d in range(7)]
        if i <= 2:
            slot_out.append((SLC(i), EMPTY))
    lookup('FSLOTS', subs(slot_out + [(POINT, EMPTY), (POINTZ, G(0, 0))] + [(g, EMPTY) for g in FRAll + FRBll]))

    # integers (and the integer part of big decimals)
    single('TOEMPTY', f'sub {D(0)} by {EMPTY}')
    lookup('LZ', [f"sub {EMPTY} {D(0)}' lookup TOEMPTY @D", f"ignore sub @D {D(0)}'", f"sub {D(0)}' lookup TOEMPTY @D"])
    # the first digit is never 0 unless it is the whole number
    for k in range(KMAX):
        lookup(f'MARK{k}', subs((D(d), L(d, k)) for d in range(0 if k == 0 else 1, 7)))
    Lall = [L(d, k) for d in range(7) for k in range(KMAX) if d or k == 0] + [L(1, KMAX)]
    w(f'@L = {cls(Lall)};\n')
    lookup('LEAD', ["ignore sub [@D @L] @D'"]
           + [f"sub @D' lookup MARK{k}" + ' @D' * k for k in range(KMAX - 1, -1, -1)])

    # from 343 on, in place: round on the third digit, then write digit, digit, exp7, exponent
    Lk = lambda k: [L(d, k) for d in range(1, 7)] if k < KMAX else [L(1, KMAX)]
    w(f'@BIG = {cls(g for k in range(3, KMAX + 1) for g in Lk(k))};\n')
    lookup('INCD', subs(zip(Dall, Dall[1:] + [DC])))
    lookup('ROUND', [f"sub @BIG @D' lookup INCD {cls(Dall[4:])}"])
    lookup('INCL', subs((L(d, k), L(d + 1, k) if d < 6 else L(1, k + 1)) for d in range(1, 7) for k in range(3, KMAX)))
    lookup('CARRY', [f"sub @BIG' lookup INCL {DC}"])
    single('TOTAIL', f'sub @D by {TAIL}')
    lookup('SCITAIL', [f"sub @BIG @DX @D @D' lookup TOTAIL", f"sub {TAIL} @D' lookup TOTAIL"])
    for k in range(3, KMAX + 1):
        single(f'TOEXP{k}', f'sub @D by {EXP(k)}')
    lookup('SCIEXP', [f"sub {cls(Lk(k))} @DX @D' lookup TOEXP{k}" for k in range(3, KMAX + 1)])
    lookup('SECOND', subs((D(d), G(d, -1) if d else EMPTY) for d in range(7)) + [f'sub {DC} by {EMPTY}'])
    lookup('SCID2', ["sub @BIG @DX' lookup SECOND"])
    lookup('LPOS', subs((L(d, k), G(d, k)) for d in range(7) for k in range(3) if d or k == 0)
           + subs((g, G(int(g[5]), 0)) for k in range(3, KMAX + 1) for g in Lk(k)))
    lookup('F1', subs((D(d), G(d, 1) if d else EMPTY) for d in range(7)))
    lookup('F0', subs((D(d), G(d, 0) if d else EMPTY) for d in range(7)))
    lookup('POS', ["sub @D' lookup F1 @D", "sub @D' lookup F0"])

    def spell(k):
        hi, lo = divmod(k, 7)
        return ' '.join([WORDC('exp7')] + ([G(hi, 1)] if hi else []) + ([G(lo, 0)] if lo else []))
    lookup('SPELL', subs((EXP(k), spell(k)) for k in range(3, KMAX + 1)))
    lookup('UNLONG', subs((var(g, 'isol'), g) for g in LAT))

    # ss02 also joins words like the game does: between two word glyphs, one space of a run takes no room.
    # GPOS on the word, not GSUB on the space: WebKit restores a space character's width whatever glyph replaced it.
    w(f'@XW = {cls(joined)};\n')
    lookup('JOIN', [f"pos @XW' <0 0 -{SPACE_ADV} -{ALIEN_ADV}> space" + ' space' * k + ' @XW' for k in range(JOINRUN)])

    feature = lambda tag, names, lookups: w(f'feature {tag} {{\n  featureNames {{ {names}; }};\n'
                                            + ''.join(f'  lookup {n};\n' for n in lookups) + f'}} {tag};\n')
    feature('ss02', 'name "Alien words"; name 3 1 0x0804 "兴语单词"', ['WSTART', 'WEND', 'WORDS', 'WREVERT', 'JOIN'])
    feature('ss01', 'name "Alien numerals"; name 3 1 0x0804 "兴语数字"',
            ['LONG', 'NEGSIGN', 'POINTS', 'SLOTS', 'PAD'] + [f'PASS{i}' for i in range(MAXDIG)]
            + [x for j in range(FRACS) for x in (f'FRMUL{j}', f'FRSHIFT{j}')]
            + ['NORM', 'BIGPOINT', 'BIGDROP', 'ROUNDF', 'CARRYF', 'FZERO', 'FOUT', 'FSLOTS',
               'LZ', 'LEAD', 'ROUND', 'CARRY', 'SCITAIL', 'SCIEXP', 'SCID2', 'LPOS', 'POS', 'SPELL', 'UNLONG'])
    internal = ([A(d, c) for d in range(7) for c in range(4)] + [B(d, c) for d in range(7) for c in range(4)] + Dx
                + Lall + [EXP(k) for k in range(3, KMAX + 1)] + FRAll + FRBll + SLall + [SLC(1), SLC(2), POINT, POINTBIG, POINTZ, EMPTY, TAIL, BIGE])
    return ''.join(f), variants + internal


def share_scratch(fea, scratch):
    '''Interval colouring: blank glyphs that are never alive in the same lookups can be one glyph.

    A glyph lives from the first to the last top-level lookup that names it; greedy by start time uses the fewest.
    Colours run on from the previous one where they can, so coverage tables stay in ranges. nul.* outlive shaping.'''
    classes = {m[1]: m[2] for m in re.finditer(r'^@(\w+) = \[(.*?)\];$', fea, re.M)}
    bodies = {m[1]: m[2] for m in re.finditer(r'^lookup (\w+) \{(.*?)\} \1;$', fea, re.M | re.S)}
    called = set(re.findall(r'^  lookup (\w+);$', fea, re.M))
    index = {g: i for i, g in enumerate(scratch)}

    def named(name):
        body = bodies[name]
        text = body + ' '.join(classes[c] for c in re.findall(r'@(\w+)', body))
        found = set(re.findall(r'[A-Za-z_][\w.]*', text)) & set(scratch)
        for inner in re.findall(r'lookup (\w+)', body):
            found |= named(inner)
        return found

    spans = {}
    for step, name in enumerate(n for n in bodies if n in called):
        for g in named(name):
            spans[g] = (spans[g][0] if g in spans else step, step)
    rename, free, busy, prev, count = {}, set(), [], None, 0
    for g in sorted(spans, key=lambda g: (spans[g][0], index[g])):
        if g.startswith('nul.'):
            continue
        while busy and busy[0][0] < spans[g][0]:
            free.add(heapq.heappop(busy)[1])
        if prev is not None and prev + 1 in free:
            colour = prev + 1
        else:
            colour = min(free) if free else count
        free.discard(colour)
        count = max(count, colour + 1)
        heapq.heappush(busy, (spans[g][1], colour))
        rename[g], prev = f't{colour}', colour
    fea = re.sub(r'(?<![\w.@])[A-Za-z_][\w.]*', lambda m: rename.get(m[0], m[0]), fea)
    return fea, [f't{i}' for i in range(count)] + [g for g in scratch if g.startswith('nul.')]


# ---------- the in-game dictionary ----------

def digits7(n):
    ds = []
    while n:
        n, r = divmod(n, 7)
        ds.append(r)
    return ds or [0]


def to_base7(n):
    '''Every non-zero base-7 digit d at place p as "d" / "dep".'''
    if n == 0:
        return ['0']
    ds = digits7(abs(n))
    places = [str(d) if p == 0 else f'{d}e{p}' for p, d in reversed(list(enumerate(ds))) if d]
    return (['negative'] if n < 0 else []) + places


def to_base7_exp(n):
    '''Two significant base-7 digits (the third rounds), then exp7 and the exponent.'''
    ds = digits7(abs(n))[::-1]
    k = len(ds) - 1
    d1, d2 = ds[0], ds[1] + (ds[2] >= 4)
    if d2 == 7:
        d1, d2 = d1 + 1, 0
    out = ['negative'] if n < 0 else []
    if d1 == 7:
        return out + ['1', 'exp7'] + to_base7(k + 1)
    return out + [str(d1)] + ([f'{d2}e-1'] if d2 else []) + ['exp7'] + to_base7(k)


def integer_words(n):
    '''An integer the way the game writes it.'''
    return to_base7_exp(n) if abs(n) >= 343 else to_base7(n)



def number_words(t):
    '''A number in a definition ("12", "-3", "1e-2") as numeral words, or None.'''
    if re.fullmatch(r'-?\d+', t):
        return [num_word(int(x[0]), int(x[2:] or 0)) if x[0].isdigit() else x for x in integer_words(int(t))]
    if (m := re.fullmatch(r'(-?)(\d)e(-?\d+)', t)) and abs(int(m[3])) < 4:
        return (['negative'] if m[1] else []) + [num_word(int(m[2]), int(m[3]))]
    return None


def definition(text, by, units):
    '''A definition as the game's dictionary writes it: lines of words, numbers as base-7 numerals followed by
    their unit ("49As": 49 seconds). Other notations stay text ("~1div343").'''
    lines = [[]]
    for t in text.replace('<', '').replace('>', '').replace(';', ' newline ').split():
        m = re.fullmatch(r'(.+?)A(\w+)', t)
        if t == 'newline':
            lines.append([])
        elif t in by or t == '.':
            lines[-1] += [t] if t != '.' else []
        elif (ws := number_words(t)) is not None:
            lines[-1] += ws
        elif m and m[2] in units and (ws := number_words(m[1])) is not None:
            lines[-1] += ws + units[m[2]]
        else:
            lines[-1].append('~' + t.replace('div', '/'))
    return lines


def roots(r, by):
    '''A compound's components, under their display names, as the dictionary lists them.'''
    if r['struct'] in ('s', 'exp'):
        return []
    return [by[c]['rename'] or c for c in (r['component1'], r['component2']) if c]


# ---------- code points ----------

num_word = lambda d, e: str(d) if e == 0 else f':{d}e{e}'
category = lambda r: r['category'].split()[0]
hexcp = lambda cp: f'U+{cp:05X}'
SPECIAL = ('numeral', 'token', 'overflow')


def read_csv(path):
    with open(path, newline='') as fh:
        return list(csv.DictReader(fh))


def write_csv(path, header, rows):
    with open(path, 'w', newline='') as fh:
        csv.writer(fh, lineterminator='\n').writerows([header, *rows])


def allocate(rows, words):
    '''word -> code point. Cells of words dropped from the game are freed. New words take the first free cell of
    their category's block, else of the overflow.'''
    chars = {r['word']: int(r['codepoint'][2:], 16) for r in read_csv(REGISTRY) if r['block'] == 'numeral' or r['word'] in words}
    blocks = [(r['block'], int(r['start'][2:], 16), int(r['end'][2:], 16)) for r in read_csv(BLOCKS)]
    span = {b: (lo, hi) for b, lo, hi in blocks}
    free = lambda lo, hi: next((c for c in range(lo, hi + 1) if c not in chars.values()), None)
    for r in rows:
        if r['word'] in words and r['word'] not in chars:
            chars[r['word']] = free(*span.get(category(r), span['overflow'])) or free(*span['overflow'])
            print('new', hexcp(chars[r['word']]), r['word'])
    block_of = lambda cp: next(b for b, lo, hi in blocks if lo <= cp <= hi)
    write_csv(REGISTRY, ['codepoint', 'word', 'block'],
              [[hexcp(cp), w, block_of(cp)] for w, cp in sorted(chars.items(), key=lambda x: x[1])])
    return chars, blocks


def write_table(path, shown, chars, blocks, by, units):
    '''The page's data: blocks, then every character with its dictionary entry.'''
    ref = lambda w: f'{chars[w]:X}'
    out_blocks = []
    for b, lo, hi in blocks:
        if used := [chars[w] for w in shown if lo <= chars[w] <= hi]:
            blk = {'start': f'{min(used) & ~15:X}', 'end': f'{max(used) | 15:X}'}
            out_blocks.append(blk | ({'kind': b} if b in SPECIAL else {'head': ref(b), 'name': b}))
    entries = []
    for w in sorted(shown, key=chars.get):
        r = by.get(w)
        e = {'cp': f'{chars[w]:X}', 'struct': r['struct'] if r else 'exp'}
        if r and r['struct'] not in ('s', 'exp'):
            e['parts'] = [ref(c) for c in (r['component1'], r['component2']) if c]
        if r and (cats := [ref(c) for c in r['category'].split() if c in chars]):
            e['cats'] = cats
        if r and r['wordtype'] != 'token':    # the internal tokens have no dictionary entry of their own
            e['wt'] = [ref(x) for x in r['wordtype'].split() if x in by]
            e['roots'] = [ref(x) for x in roots(r, by)]
        if r and r['meaning']:
            e['def'] = [[x if x[0] == '~' else ref(x) for x in line] for line in definition(r['meaning'], by, units)]
        e = {k: v for k, v in e.items() if v != []}
        entries.append(e | {'name': w.lstrip(':'), 'meaning': r['meaning'] if r else ''})
    dump = lambda xs: ',\n'.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in xs)
    path.write_text(f'{{"version":"{VERSION}","blocks":[\n{dump(out_blocks)}\n],"entries":[\n{dump(entries)}\n]}}\n')


def name_strings(family, zh):
    ps = family.replace(' ', '')
    return {'copyright': f'(c) 2026 {AUTHOR}. Glyph designs (c) Artless Games.',
            'familyName': {'en': family, 'zh': zh}, 'styleName': 'Regular',
            'uniqueFontIdentifier': f'{VERSION:.3f};{ps}',
            'fullName': {'en': f'{family} Regular', 'zh': f'{zh} Regular'},
            'version': f'Version {VERSION:.3f}', 'psName': f'{ps}-Regular',
            'manufacturer': AUTHOR, 'designer': AUTHOR,
            'vendorURL': f'https://github.com/{AUTHOR}', 'designerURL': f'https://github.com/{AUTHOR}',
            'licenseInfoURL': f'https://{AUTHOR}.github.io/xingyu/',
            'description': {'en': 'Fan font for the alien script of Message From Aliens.',
                            'zh': '《外星来信》外星文字同人字体。'},
            'licenseDescription': {'en': 'Unofficial fan work. Personal, non-commercial use only.',
                                   'zh': '非官方同人作品，仅限个人非商业使用。'},
            'variationsPostScriptNamePrefix': ps}


# ---------- build ----------

def build_master(width, order, outlines, advances, fits, clear, cmap, fea, names):
    '''fits: Latin glyph -> (left, right, centre-line width); its ink keeps those side bearings at this weight.
    clear: alien glyph -> its clearance, for the stroke width fitted to it.'''
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    glyphs, advances = {}, dict(advances)
    for g in order:
        lines, dots = outlines.get(g, ([], []))
        if g in fits:
            left, right, cw = fits[g]
            dx = left + width / 2
            lines, dots = [[(x + dx, y) for x, y in l] for l in lines], [(x + dx, y) for x, y in dots]
            advances[g] = round(left + cw + width + right)
        glyphs[g] = draw(lines, dots, fitted(width, clear.get(g)))
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g: (advances[g], getattr(glyphs[g], 'xMin', 0)) for g in order})
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT, lineGap=0)
    fb.setupVerticalMetrics({g: (ALIEN_ADV if advances[g] else 0, VORIGIN - getattr(glyphs[g], 'yMax', 0)) for g in order})
    fb.setupVerticalHeader(ascent=ALIEN_ADV // 2, descent=-ALIEN_ADV // 2, lineGap=0)
    fb.setupNameTable(names, mac=False)
    fb.setupOS2(version=4, sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0, usWinAscent=ASCENT,
                usWinDescent=-DESCENT, sxHeight=round(10 * LAT_U), sCapHeight=round(14 * LAT_U), usWeightClass=400,
                fsType=0, achVendID='WLNK', fsSelection=0xC0, ulCodePageRange1=1)   # Regular, USE_TYPO_METRICS; Latin 1
    fb.setupPost()
    fb.font['head'].fontRevision = VERSION
    fb.font['gasp'] = newTable('gasp')
    fb.font['gasp'].gaspRange = {0xFFFF: 0x000F}
    fb.font['prep'] = newTable('prep')
    fb.font['prep'].program = ttProgram.Program()
    fb.font['prep'].program.fromAssembly('PUSHW[ ] 511 SCANCTRL[ ] PUSHB[ ] 4 SCANTYPE[ ]')
    addOpenTypeFeaturesFromString(fb.font, fea)
    return fb.font


def build_vf(family, zh, *master_args):
    ps = family.replace(' ', '')
    ds = DesignSpaceDocument()
    ds.addAxisDescriptor(tag='wght', name='Weight', minimum=100, default=400, maximum=900)
    for wght, width in MASTERS.items():
        ds.addSourceDescriptor(font=build_master(width, *master_args, name_strings(family, zh)),
                               location={'Weight': wght}, name=f'master{wght}')
    for style, wght in INSTANCES.items():
        ds.addInstanceDescriptor(familyName=family, styleName=style, location={'Weight': wght},
                                 postScriptFontName=f'{ps}-{style}')
    vf, _, _ = varLib.build(ds, exclude=['STAT'], optimize=False)     # save_font applies IUP to the TTF only
    values = [{'value': v, 'name': n} | ({'flags': 2, 'linkedValue': 700} if v == 400 else {}) for n, v in INSTANCES.items()]
    buildStatTable(vf, [{'tag': 'wght', 'name': 'Weight', 'values': values}], macNames=False)
    vf['OS/2'].recalcUnicodeRanges(vf)
    save_font(vf, DATA / f'{ps}-VF.ttf')


def main():
    rows = read_csv(SOURCE / 'words.csv')
    by = {r['word']: r for r in rows}
    strokes = json.loads((SOURCE / 'glyphs.json').read_text())
    units = json.loads((SOURCE / 'units.json').read_text())
    # every word with a glyph of its own (numerals are drawn from the digits); ss02 types the alphanumeric ones
    # the "solid" token is the notebook's filled cursor block, not a character
    words = [r['word'] for r in rows if r['struct'] not in ('exp', 'solid') and not r['word'].isdigit()]
    typed = lambda w: all(c in LATIN_CHARS and c.isalnum() for c in w)
    chars, blocks = allocate(rows, set(words))
    numerals = {num_word(d, e): G(d, e) for d, e in NUMERALS}

    outlines = {WORDC(w): alien_lines(strokes[w]) for w in words}
    outlines |= {G(d, e): alien_lines(numeral_strokes(by[str(d)]['component1'], e)) for d, e in NUMERALS}
    advances = {g: ALIEN_ADV for g in outlines} | {'.notdef': 600, 'space': SPACE_ADV}
    outlines['.notdef'] = ([[(80, 0), (520, 0), (520, 700), (80, 700), (80, 0)]], [])
    fits = {}
    for name in LATIN:
        ln, dt, cw = latin_lines(name)
        outlines[name], fits[name] = (ln, dt), SIDEBEARINGS[name] + (cw,)

    clear = {g: clearance(lines) for g, (lines, _) in outlines.items() if g not in fits}

    DATA.mkdir(exist_ok=True)
    joined = [WORDC(w) for w in words if w not in NUMBER_WORDS]
    fea, internal = feature_code([w for w in words if typed(w)], joined)
    fea, internal = share_scratch(fea, internal)
    advances |= {g: 0 for g in internal}                # only ever seen mid-shaping
    glyph = numerals | {w: WORDC(w) for w in words}
    cmap = {0x20: 'space', 0xA0: 'space', 0x2212: 'hyphen'} | {ord(c): g for c, g in LATIN_CHARS.items()}
    cmap |= {cp: glyph[w] for w, cp in chars.items() if w in glyph}
    order = ['.notdef', 'space', *LATIN, *numerals.values(), *(WORDC(w) for w in words), *internal]
    assert len(order) == len(set(order))
    build_vf('Xingyu', '兴语', order, outlines, advances, fits, clear, cmap, fea)
    write_table(DATA / 'xingyu.json', set(glyph) & set(chars), chars, blocks, by, units)
    print(f'{len(order)} glyphs, {len(cmap)} characters')


if __name__ == '__main__':
    main()
