'''Shape text with HarfBuzz and check the font's features against reference implementations.

  ss01  integers: the game's own formatting (every non-zero digit by place; from 343 on, two digits and exp7)
        decimals:  < 2401: positional digits, two base-7 places rounded on the third; else the integer part
  ss02  dictionary words and "3e2" tokens

  python3 test_font.py data/Xingyu-VF.ttf'''
import random
import sys
import time
from fractions import Fraction

import uharfbuzz as hb

from build_font import NUMBER_WORDS, PRIVATE, read_csv, to_base7, integer_words as game


def decimal(s):
    x = Fraction(s)
    if abs(x) >= 2401:
        return game(int(x))
    scaled = int(abs(x) * 343)                 # three base-7 places, truncated
    scaled = scaled // 7 + (scaled % 7 >= 4)   # round on the third
    ip, f = divmod(scaled, 49)
    out = [] if ip == 0 else [t for t in to_base7(ip)]
    out += [f'{d}e-{i}' for i, d in ((1, f // 7), (2, f % 7)) if d]
    return (['negative'] if x < 0 else []) + (out or ['0'])


def main():
    font = hb.Font(hb.Face(hb.Blob.from_file_path(sys.argv[1])))

    def shape(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        out = []
        for i in buf.glyph_infos:
            n = font.glyph_to_string(i.codepoint)
            if n.startswith('nul.'):
                continue
            if n.startswith('num.'):
                d, e = n[4:].split('e')
                e = e.replace('m', '-')
                n = d if e == '0' else f'{d}e{e}'
            elif n.startswith('w.'):
                n = n[2:]
            out.append(n)
        return out

    def check(label, cases, want, feats):
        bad = 0
        for c in cases:
            got, exp = shape(c, feats), want(c)
            if got != exp:
                bad += 1
                if bad <= 8:
                    print('  MISMATCH', repr(c), 'got', got, 'want', exp)
        print(f'{label}: {len(cases) - bad}/{len(cases)}')

    rng = random.Random(7)
    ints = list(range(0, 3000)) + [-1, -5, -342, -343, -2017, -10 ** 19, 10 ** 20 - 1]
    ints += [7 ** k + o for k in range(1, 23) for o in (-1, 0, 1) if 7 ** k + o < 10 ** 20]
    ints += [rng.randrange(10 ** rng.randint(3, 20)) for _ in range(3000)]
    check('ss01 integers', [str(n) for n in ints], lambda s: game(int(s)), {'ss01': True})

    decs = ['0.5', '-0.5', '3.14159', '0.01', '0.02', '0.07', '6.99', '48.99', '342.9', '2400.99', '2401.5', '0.0',
            '10.0', '123456.789', '-2017.5']
    decs += [f'{rng.randrange(3000)}.{rng.randrange(10 ** rng.randint(1, 6)):0d}' for _ in range(2000)]
    decs += [f'0.{rng.randrange(10 ** 4):04d}' for _ in range(1000)]
    check('ss01 decimals', decs, decimal, {'ss01': True})

    rows = read_csv(PRIVATE / 'words.csv')
    words = [r['word'] for r in rows if r['struct'] != 'exp' and len(r['word']) > 0 and r['word'].isalnum()
             and r['word'] not in '0123456789' and font.get_glyph_from_name('w.' + r['word']) is not None]
    check('ss02 words', words, lambda s: [s], {'ss02': True})
    # the space between two words is hidden; one of two is kept
    gap = lambda a, b: ['space'] if a in NUMBER_WORDS or b in NUMBER_WORDS else []
    trios = {f'{a} {b}  {c}.': [a, *gap(a, b), b, 'space', *gap(b, c), c, 'period']
             for a, b, c in zip(words, words[1:], words[2:])}
    check('ss02 in text', list(trios), trios.get, {'ss02': True})
    # partial words stay Latin
    for text in ['i feel happy today', 'happys', 'Happy', 'exp7 3e2 3e-1 2017', 'water-1 sky.']:
        print(f'  {text!r:24} ->', ' '.join(shape(text, {'ss02': True})))
    print('  both features:', ' '.join(shape('happy 2017 -3.5 3e2', {'ss01': True, 'ss02': True})))

    # long runs: HarfBuzz's op budget scales with the buffer length; time a paragraph
    para = ' '.join(rng.choice(words + [str(rng.randrange(10 ** 6)) for _ in range(50)]) for _ in range(2000))
    t = time.time()
    n = len(shape(para, {'ss01': True, 'ss02': True}))
    print(f'paragraph of {len(para)} chars -> {n} glyphs in {time.time() - t:.2f}s')
    big = ' '.join(str(rng.randrange(10 ** 19)) for _ in range(400))
    out = shape(big, {'ss01': True})
    want = [t for x in big.split(' ') for t in game(int(x)) + ['space']][:-1]
    print('400 big numbers in one run:', 'ok' if out == want else f'MISMATCH ({len(out)} vs {len(want)} glyphs)')


if __name__ == '__main__':
    main()
