'''Turn the game's files into source/. Only needed when the game changes.

  uv run --no-project --with UnityPy --with pycryptodome python prepare.py

  source/words.csv    word, category, struct, component1, component2, rename, wordtype, meaning (file order kept)
  source/glyphs.json  word -> strokes, composed like AlienInfo.GetCharacter
  source/extra.csv    fan-made words not in the game (kept by hand, in the game's columns), appended to the above

The game has no category column: it derives categories from radicals (Global.Search_Radicial and Global.Init), which
categorize() follows. CATEGORIES is the list in Global..cctor, read off GameAssembly.dll.'''
import base64
import csv
import json
import re
import sys
from pathlib import Path

import UnityPy
from Crypto.Cipher import AES

HERE = Path(__file__).resolve().parent
GAME = HERE.parent / 'Message From Aliens/MessageFromAliens_Data'
COLUMNS = ['word', 'category', 'struct', 'component1', 'component2', 'rename', 'wordtype', 'meaning']
CATEGORIES = '''big positive amount yes group join loop change same eq place road sky time light direction person gender
alien terran god hand anti move do item weapon head brain mouth eye think nose gill science this and symbol surface word
de ness in to whether object game boat fish bird fin beast snake branch scale shell spike weed tree air earth fire hot
water ice metal wave elec xx changeword linkword 0 1 2 3 4 5 6'''.split()
FROM_EARLIER = ('d', 'vd', 't', 'q', 'fb', 'flr', 'fud')     # one component, the shape of which is reused
CORNERS = {'our': (1, 1), 'oul': (-1, 1), 'odl': (-1, -1), 'odr': (1, -1), 'od': (0, -1), 'ou': (0, 1), 'ol': (-1, 0),
           'or': (1, 0)}


def read_dictionary():
    env = UnityPy.load(str(GAME / 'resources.assets'))
    asset = next(o.read() for o in env.objects if o.type.name == 'TextAsset' and o.read().m_Name == 'newalien')
    cipher = AES.new(b'terrible_artwork', AES.MODE_CBC, b"wedidn'tplaytest")
    plain = cipher.decrypt(base64.b64decode(asset.m_Script))
    return list(csv.DictReader(plain[:-plain[-1]].decode().splitlines()))


# ---------- glyphs: Global.string_to_pos, Normalize, Scale_to, Pos_combine, StringToCharacter ----------

def points(strokes):
    return [p for s in strokes for p in s]


def to_strokes(text, center=True):
    out = []
    for part in text.split(';'):
        v = [float(x) for x in re.findall(r'[+-]?\d+(?:\.\d+)?', part)]
        out.append([(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)])
    if center:
        xs, ys = zip(*points(out))
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        out = [[(x - cx, y - cy) for x, y in s] for s in out]
    return out


def normalize(strokes, center=True):
    xs, ys = zip(*points(strokes))
    half = max(max(xs) - min(xs), max(ys) - min(ys), 0.1) / 2
    cx, cy = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) if center else (0, 0)
    return [[((x - cx) / half, (y - cy) / half) for x, y in s] for s in strokes]


def extent(strokes, least=0.0):
    return (max([least] + [abs(x) for x, _ in points(strokes)]), max([least] + [abs(y) for _, y in points(strokes)]))


def scale_to(strokes, ext, size, offset=(0, 0)):
    n = max(ext[0] * 2 / size[0], ext[1] * 2 / size[1])
    return [[(x / n + offset[0], y / n + offset[1]) for x, y in s] for s in strokes]


def repeat(strokes, size, offsets):
    return [s for off in offsets for s in scale_to(strokes, extent(strokes), size, off)]


def combine(a, b, how, mod, a_center, b_center):
    a, b = normalize(a, a_center), normalize(b, b_center)
    (ax, ay), (bx, by) = extent(a, 0.01), extent(b, 0.01)
    space = 0.05 if 'n' in mod else 0.3 if 's' in mod else 0.15
    drop = -0.05 if 'x' in mod else 0
    fixed = '=' in mod or 'l' in mod or 'r' in mod
    rate = 0.65 if 'l' in mod else 0.35 if 'r' in mod else 0.5
    if how == 'lr':
        wide = 1, 1
        if not fixed:
            k = ax / ay * by / bx
            rate = k / (1 + k)
            wide = (min(rate / ax * ay, 1),) * 2
        w1, w2 = rate * (1 - space), (1 - rate) * (1 - space)
        return normalize(scale_to(a, (ax, ay), (w1, wide[0]), (-0.5 + w1 / 2, 0))
                         + scale_to(b, (bx, by), (w2, wide[1]), (0.5 - w2 / 2, drop)))
    if how == 'ud':
        tall = 1, 1
        if not fixed:
            k = ay / ax * bx / by
            rate = k / (1 + k)
            tall = (min(rate / ay * ax, 1),) * 2
        h1, h2 = rate * (1 - space), (1 - rate) * (1 - space)
        return normalize(scale_to(a, (ax, ay), (tall[0], h1), (0, 0.5 - h1 / 2))
                         + scale_to(b, (bx, by), (tall[1], h2), (0, -0.5 + h2 / 2 + drop)))
    if how == 'over':
        rate = 1
    elif '+' in mod:
        rate = 0.7
    elif '-' in mod:
        rate = 0.4
    elif 'x' in mod:
        rate = 0.25
    else:
        rate = 0.5
    vx, vy = CORNERS.get(how, (0, 0))
    return scale_to(a, (ax, ay), (1, 1)) + scale_to(b, (bx, by), (rate, rate),
                                                    (vx * (1 - rate) / 2, vy * (1 - rate) / 2 + drop))


def glyph(word, by, memo):
    if word in memo:
        return memo[word]
    r = by[word]
    how, c1, c2, mod = r['struct'], r['component1'], r['component2'], r['modifier']
    if how == 'exp':
        digit, e = word.lstrip(':').split('e')
        e = int(e)
        bars = [[(-3.0, (3.0 + k) * (1 if e > 0 else -1)), (3.0, (3.0 + k) * (1 if e > 0 else -1))] for k in range(abs(e))]
        dy = (e - 1) / 2 if e > 0 else (e + 1) / 2
        out = [[(x, y - dy) for x, y in s] for s in glyph(digit, by, memo) + bars]
    elif how in ('s', 'solid'):
        out = to_strokes(c1, '!' not in mod)
    elif how == 'd':
        out = repeat(glyph(c1, by, memo), (0.45, 0.5), [(-0.27, 0), (0.27, 0)])
    elif how == 'vd':
        out = repeat(glyph(c1, by, memo), (0.45, 0.5), [(0, -0.27), (0, 0.27)])
    elif how == 't':
        out = repeat(glyph(c1, by, memo), (0.45, 0.45), [(0, 0.27), (-0.27, -0.27), (0.27, -0.27)])
    elif how == 'q':
        out = repeat(glyph(c1, by, memo), (0.45, 0.45), [(0.27, 0.27), (-0.27, -0.27), (0.27, -0.27), (-0.27, 0.27)])
    elif how == 'shrink':
        out = repeat(glyph(c1, by, memo), (0.45, 0.5), [(0, 0)])
    elif how in ('fb', 'flr', 'fud'):
        sx, sy = -1 if how != 'fud' else 1, -1 if how != 'flr' else 1
        out = [[(x * sx, y * sy) for x, y in s] for s in glyph(c1, by, memo)]
    else:
        out = combine(glyph(c1, by, memo), glyph(c2, by, memo), how, mod, '!' not in by[c1]['modifier'],
                      '!' not in by[c2]['modifier'])
    memo[word] = out
    return out


# ---------- categories: Global.Search_Radicial, Global.Init ----------

def radicals(word, by, memo):
    '''word -> {radical: depth}, in the order the game's dictionary inserts them.'''
    if word in memo:
        return memo[word]
    r, found = by[word], {}
    memo[word] = found
    how = r['struct']
    if how in ('s', 'solid'):
        found[r['redirect'] if r['redirect'] not in ('', 'token') else word] = 0
    elif how == 'exp':
        found[word.lstrip(':')[:1]] = 0     # Init strips ':', then the leading digit is taken
    else:
        if word in CATEGORIES:
            found[word] = 0
        if how in FROM_EARLIER:
            c = r['component1']
            found.update({c: 0} if c in CATEGORIES else radicals(c, by, memo))
            return found
        for c in (r['component1'], r['component2']):
            if not c:
                continue
            if word != 'move' and how == 'ud' and (r['component1'], c) == ('hand', 'hand') and r['component2'] != 'hand':
                found['move'] = 1
                continue
            sub = radicals(c, by, memo)
            if c in CATEGORIES:
                found.setdefault(c, 1)
            else:
                for k, depth in sub.items():
                    found[k] = min(found.get(k, depth + 1), depth + 1)
    return found


def categorize(r, by, memo):
    word = r['word']
    if r['redirect'] == 'token' or r['wordtype'].split(';')[0] == 'token' or (r['rename'] or word) != word:
        return ['token']
    found = radicals(word, by, memo)
    top = min(found.values()) + 1
    out = [by[k]['rename'] or k if k in by else k for k, depth in found.items()
           if depth <= top and not (k in by and by[k]['redirect'] == 'token')]
    return out + [t for t in ('changeword', 'linkword') if r['wordtype'] == t]


# ---------- outputs ----------

def main():
    sys.setrecursionlimit(5000)
    with open(HERE / 'source/extra.csv', newline='') as fh:
        rows = read_dictionary() + list(csv.DictReader(fh))     # fan-made words, composed like the game's
    by = {r['word']: r for r in rows}
    memo, strokes = {}, {}
    for r in rows:
        r['category'] = ' '.join(categorize(r, by, memo))
        glyph(r['word'], by, strokes)
    with open(HERE / 'source/words.csv', 'w', newline='') as fh:
        out = csv.writer(fh, lineterminator='\n')
        out.writerow(COLUMNS)
        out.writerows([r[c] for c in COLUMNS] for r in rows)
    (HERE / 'source/glyphs.json').write_text(json.dumps({w: [[list(p) for p in s] for s in v] for w, v in strokes.items()}))
    print(len(rows), 'words')


if __name__ == '__main__':
    main()
