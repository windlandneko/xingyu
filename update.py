'''Follow a game update from Steam to a GitHub release.

  uv run --no-project --with pillow python update.py            rebuild from the Mac Steam install, test, then
                                                                 publish, or stop for review
  uv run --no-project --with pillow python update.py --force    the same even when the build is in source/buildid.txt
  uv run --no-project --with pillow python update.py publish    commit, tag, push and release the last run's build

Steps: Steam keeps the native Mac game up to date; when its build id differs from source/buildid.txt, prepare.py
(which reads the game in place), build_font.py (VERSION bumped to the next minor) and test_font.py run. If any code
point is added, removed or redrawn, .update/diff.png is drawn (green added, red deprecated, blue redrawn) and the run
stops: look at it, edit .update/notes.md if needed, then run publish.
Otherwise it publishes at once.'''
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / '.update'
BUILDID = HERE / 'source/buildid.txt'
MANIFEST = Path.home() / 'Library/Application Support/Steam/steamapps/appmanifest_1858720.acf'
ASSETS = ['data/Xingyu-VF.ttf', 'data/Xingyu-VF.woff2', 'data/Xingyu-QQ.ttf']
UV_PREPARE = ['uv', 'run', '--no-project', '--with', 'UnityPy', '--with', 'pycryptodome', 'python']
UV_BUILD = ['uv', 'run', '--no-project', '--with-requirements', 'requirements.txt', 'python']


def run(*cmd, capture=False):
    print('$', ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE, check=True, stdout=subprocess.PIPE if capture else None)
    return r.stdout.decode('utf-8', 'replace') if capture else None


def git(*args):
    return run('git', *args, capture=True).strip()


# ---------- game ----------

def installed_build():
    fields = dict(re.findall(r'"(\w+)"\s+"([^"]*)"', MANIFEST.read_text()))
    if fields['StateFlags'] != '4':     # 4: fully installed; anything else is mid-update
        sys.exit(f"Steam is still updating the game (StateFlags {fields['StateFlags']}); try again later")
    return fields['buildid']


# ---------- diff ----------

def registry(text):
    return {r['codepoint']: r for r in csv.DictReader(io.StringIO(text))}


def changes():
    '''code point -> ('add' | 'del' | 'mod', old word, new word), plus words whose meaning changed. 'del' is a word
    that left the game: its glyph stays as a deprecated one.'''
    old, new = registry(git('show', 'HEAD:source/registry.csv')), registry((HERE / 'source/registry.csv').read_text())
    shown = run('git', 'ls-tree', 'HEAD', 'source/retired.json', capture=True)
    oldr = json.loads(git('show', 'HEAD:source/retired.json')) if shown else {}
    newr = json.loads((HERE / 'source/retired.json').read_text())
    og = json.loads(git('show', 'HEAD:source/glyphs.json')) | {w: r['strokes'] for w, r in oldr.items()}
    ng = json.loads((HERE / 'source/glyphs.json').read_text()) | {w: r['strokes'] for w, r in newr.items()}
    shape = lambda g, w: json.dumps(g.get(w), separators=(',', ':'))
    out = {}
    for cp in old.keys() | new.keys():
        a, b = old.get(cp), new.get(cp)
        if b and b['word'] in newr and b['word'] not in oldr:
            out[cp] = ('del', b['word'], '')     # dropped from the game, kept as a deprecated glyph
        elif not b:
            out[cp] = ('del', a['word'], '')
        elif not a:
            out[cp] = ('add', '', b['word'])
        elif a['word'] != b['word'] or shape(og, a['word']) != shape(ng, b['word']):
            out[cp] = ('mod', a['word'], b['word'])
    ow = {r['word']: r for r in csv.DictReader(io.StringIO(git('show', 'HEAD:source/words.csv')))}
    with open(HERE / 'source/words.csv', newline='') as fh:
        meanings = [(w, ow[w]['meaning'], r['meaning']) for r in csv.DictReader(fh)
                    if (w := r['word']) in ow and ow[w]['meaning'] != r['meaning']]
    return dict(sorted(out.items())), meanings


INK, MUTED, FAINT, HAIR, BG = (22, 25, 29), (100, 109, 120), (150, 157, 166), (214, 219, 225), (255, 255, 255)
KIND = {'add': ((30, 135, 60), '新增'), 'del': ((200, 35, 35), '弃用'), 'mod': ((60, 72, 175), '重画')}
UI_FONT = Path.home() / 'Library/Fonts/HarmonyOS_SansSC_{}.ttf'


def render(diff, meanings, version):
    '''.update/diff.png: every 16-cell row with a change as a table of square cells, in as many side-by-side panels as
    keeps the grid about 4:3, then a table of the words whose meaning changed, old above new. The old font draws what a redraw
    replaced; deprecated glyphs live on in the new font.'''
    from PIL import Image, ImageDraw, ImageFont
    face = lambda path, size: ImageFont.truetype(str(path), size)
    ui = lambda weight, size: face(str(UI_FONT).format(weight), size)
    tint = lambda color: tuple(round(c * 0.1 + 255 * 0.9) for c in color)
    old_ttf = OUT / 'old.ttf'
    old_ttf.write_bytes(subprocess.run(['git', 'show', 'HEAD:data/Xingyu-VF.ttf'], cwd=HERE, check=True,
                                       stdout=subprocess.PIPE).stdout)
    S, PAD, HEAD, LINE = 160, 48, 96, 30        # cell, margin, row-label column, label line height
    SEP = (176, 183, 191)                        # rule between code rows that are not consecutive
    new_ttf = HERE / 'data/Xingyu-VF.ttf'
    big, pair_new, pair_old = face(new_ttf, 72), face(new_ttf, 52), face(old_ttf, 52)
    label, code, rowcode = ui('Regular', 26), ui('Medium', 20), ui('Medium', 26)
    title, legend, heading, meaning = ui('Bold', 52), ui('Medium', 30), ui('Bold', 36), ui('Regular', 28)
    newline = face('/System/Library/Fonts/Menlo.ttc', 26)        # HarmonyOS has no ↵
    words = registry((HERE / 'source/registry.csv').read_text())
    vocabulary = {r['word'] for r in words.values()}
    rows = sorted({int(cp[2:], 16) & ~15 for cp in diff})
    panel_w, row_h, top = HEAD + 16 * S, S, PAD + 96
    panels = min(range(1, 5), key=lambda k: abs(k * panel_w / (-(-len(rows) // k) * row_h + top) - 4 / 3))
    per = -(-len(rows) // panels)
    ENTRY = 120                                   # one word of the meaning list: old line, new line
    bottom = top + per * row_h
    width = 2 * PAD + panels * panel_w + (panels - 1) * 48
    img = Image.new('RGB', (width, bottom + (88 + len(meanings) * ENTRY if meanings else 0) + PAD), BG)
    d = ImageDraw.Draw(img)
    d.text((PAD, PAD), f'兴语 v{version} 码位变化', font=title, fill=INK)
    keys = [(color, f'{name} {sum(v[0] == kind for v in diff.values())}') for kind, (color, name) in KIND.items()]
    x = width - PAD - sum(42 + d.textlength(t, font=legend) for _, t in keys) - 48 * (len(keys) - 1)
    for color, text in keys:                      # the legend, right-aligned on the title's line
        d.rounded_rectangle((x, PAD + 14, x + 28, PAD + 42), 6, fill=tint(color), outline=color, width=3)
        d.text((x + 42, PAD + 28), text, font=legend, fill=INK, anchor='lm')
        x += 42 + d.textlength(text, font=legend) + 48

    def lines(text, width):
        '''At most two lines: break at the arrow of a renamed cell, else into two lines of about equal width.'''
        fits = lambda t: d.textlength(t, font=label) <= width
        if fits(text):
            return [text]
        if '→' in text:
            cut = text.index('→') + 1
            first = text[:cut]
        else:                                     # split a compound between its words, hyphen at the line end
            width_of = lambda i: max(d.textlength(text[:i] + '-', font=label), d.textlength(text[i:], font=label))
            cuts = range(2, len(text) - 1)
            rank = lambda i: (text[i:] not in vocabulary) + 2 * (text[:i] not in vocabulary)  # 0: both are words
            joints = [i for i in cuts if rank(i) < 3 and width_of(i) <= width]
            cut = min(joints, key=lambda i: (rank(i), width_of(i))) if joints else min(cuts, key=width_of)
            first = text[:cut] + '-'
        rest = text[cut:]
        while not fits(rest):
            rest = rest[:-2] + '…'
        return [first, rest]

    marked = []
    for i, row in enumerate(rows):
        ox, oy = PAD + (i // per) * (panel_w + 48), top + (i % per) * row_h
        d.text((ox, oy + S / 2), f'{row >> 4:X}x', font=rowcode, fill=MUTED, anchor='lm')
        for col in range(16):
            cp = row + col
            key, ch = f'U+{cp:05X}', chr(cp)
            x0 = ox + HEAD + col * S
            kind, was, now = diff.get(key, ('', '', (words.get(key) or {}).get('word', '')))
            color = KIND[kind][0] if kind else None
            if color:
                d.rectangle((x0, oy, x0 + S, oy + S), fill=tint(color))
                marked.append(((x0, oy, x0 + S, oy + S), color))
            d.text((x0 + 10, oy + 8), f'{col:X}', font=code, fill=color or FAINT)
            name = f'{was}→{now}' if kind == 'mod' and was != now else was if kind == 'del' else now
            text = lines(name, S - 16) if name else []
            cx, cy = x0 + S / 2, oy + (S - LINE * max(len(text), 1)) / 2 + 4
            if kind == 'mod' and was == now:
                d.text((cx - 38, cy), ch, font=pair_old, fill=FAINT, anchor='mm')
                d.text((cx, cy), '→', font=label, fill=color, anchor='mm')
                d.text((cx + 38, cy), ch, font=pair_new, fill=INK, anchor='mm')
            elif now or kind == 'del':
                d.text((cx, cy), ch, font=big, fill=INK if kind else MUTED, anchor='mm')
            for k, t in enumerate(text):
                d.text((cx, oy + S - 22 - LINE * (len(text) - 1 - k)), t, font=label, fill=color or MUTED, anchor='mm')

    for p in range(panels):                       # the table: hairlines, a darker rule where code rows skip
        mine = rows[p * per:(p + 1) * per]
        x0, x1, y1 = PAD + p * (panel_w + 48) + HEAD, PAD + p * (panel_w + 48) + panel_w, top + len(mine) * S
        for c in range(1, 16):
            d.line((x0 + c * S, top, x0 + c * S, y1), fill=HAIR, width=2)
        for r in range(1, len(mine)):
            skip = mine[r] != mine[r - 1] + 16
            d.line((x0, top + r * S, x1, top + r * S), fill=SEP if skip else HAIR, width=3 if skip else 2)
        d.rounded_rectangle((x0, top, x1, y1), 12, outline=SEP, width=2)
    for box, color in marked:
        d.rectangle(box, outline=color, width=3)

    def sentence(x, y, text, fill):
        '''A definition on one line; the game's line breaks (;) become ↵.'''
        for k, part in enumerate(text.split(';')):
            if k:
                d.text((x + 10, y), '↵', font=newline, fill=FAINT, anchor='lm')
                x += 10 + d.textlength('↵', font=newline) + 10
            d.text((x, y), part, font=meaning, fill=fill, anchor='lm')
            x += d.textlength(part, font=meaning)

    if meanings:                                   # a second table: glyph and name, then old above new
        d.text((PAD, bottom + 44), f'释义变化 {len(meanings)}', font=heading, fill=INK, anchor='lm')
        by_name = {r['word']: r['codepoint'] for r in words.values()}
        t0, x0, x1 = bottom + 88, PAD + HEAD, width - PAD
        for k, (w, was, now) in enumerate(meanings):
            oy = t0 + k * ENTRY
            if k:
                d.line((x0, oy, x1, oy), fill=HAIR, width=2)
            d.text((x0 + S / 2, oy + 46), chr(int(by_name[w][2:], 16)), font=big, fill=INK, anchor='mm')
            d.text((x0 + S / 2, oy + ENTRY - 22), w, font=label, fill=MUTED, anchor='mm')
            for j, (tag, text, fill) in enumerate((('旧', was, FAINT), ('新', now, INK))):
                ly = oy + 34 + j * 52
                d.text((x0 + S + 24, ly), tag, font=label, fill=MUTED, anchor='lm')
                sentence(x0 + S + 68, ly, text, fill)
        d.line((x0 + S, t0, x0 + S, t0 + len(meanings) * ENTRY), fill=HAIR, width=2)
        d.rounded_rectangle((x0, t0, x1, t0 + len(meanings) * ENTRY), 12, outline=SEP, width=2)
    img.save(OUT / 'diff.png', optimize=True)
    old_ttf.unlink()
    (OUT / 'meanings.txt').write_text(''.join(f'{w}: {a} -> {b}\n' for w, a, b in meanings))


def notes(diff, meanings, version, build):
    '''A draft of the release notes, in the style of the earlier releases.'''
    old = git('describe', '--tags', '--abbrev=0')
    pick = lambda k: [v for v in diff.items() if v[1][0] == k]
    word = lambda kv, w: f'{w}（{kv[0]}）'
    swapped = [kv for kv in pick('mod') if kv[1][1] != kv[1][2]]
    out = ['有码位换了字，见下文。' if swapped else f'{old} 已有的码位不变。', '', '## 字体',
           f'- 跟进游戏更新（Steam build {build}）。']
    if adds := pick('add'):
        out.append('- 新增 ' + '、'.join(word(kv, kv[1][2]) for kv in adds) + '。')
    if dels := pick('del'):
        out.append('- 游戏移除 ' + '、'.join(word(kv, kv[1][1]) for kv in dels) + '，保留为弃用字形（网页里开「显示弃用字形」可见），码位不会分配给别的字。')
    if redrawn := [kv for kv in pick('mod') if kv[1][1] == kv[1][2]]:
        out.append('- 字形随游戏重画：' + '、'.join(kv[1][1] for kv in redrawn) + '。')
    if swapped:
        out.append('- 换字：' + '、'.join(f'{kv[0]} {kv[1][1]} → {kv[1][2]}' for kv in swapped) + '。')
    if meanings:
        out.append('- 释义随游戏修改：' + '、'.join(w for w, _, _ in meanings) + '。')
    (OUT / 'notes.md').write_text('\n'.join(out) + '\n')


# ---------- steps ----------

def next_version():
    major, minor = git('describe', '--tags', '--abbrev=0').lstrip('v').split('.')[:2]
    return f'{major}.{int(minor) + 1}'


def build(force):
    latest = installed_build()
    if not force and BUILDID.exists() and BUILDID.read_text().strip() == latest:
        print('game unchanged at build', latest)
        return
    if git('status', '--porcelain', 'source', 'data', 'build_font.py'):
        sys.exit('the working tree has changes; commit or stash them first')
    run(*UV_PREPARE, 'prepare.py')
    BUILDID.write_text(latest + '\n')
    if not git('status', '--porcelain', 'source/words.csv', 'source/glyphs.json'):
        print('no dictionary change in build', latest)
        git('commit', '-m', f'Game build {latest}: no dictionary change', 'source/buildid.txt')
        return
    version = next_version()
    src = (HERE / 'build_font.py').read_text()
    (HERE / 'build_font.py').write_text(re.sub(r"^VERSION, REVISION = '[\d.]+', [\d.]+",
                                               f"VERSION, REVISION = '{version}', {version}", src, count=1, flags=re.M))
    run(*UV_BUILD, 'build_font.py')
    run(*UV_BUILD, 'test_font.py', 'data/Xingyu-VF.ttf')
    OUT.mkdir(exist_ok=True)
    diff, meanings = changes()
    notes(diff, meanings, version, latest)
    if diff:
        render(diff, meanings, version)
        print(f'\n{len(diff)} code points changed: review {OUT / "diff.png"} and {OUT / "notes.md"}, '
              'then run: uv run --no-project --with pillow python update.py publish')
        sys.exit(3)
    publish()


def publish():
    version = 'v' + re.search(r"^VERSION, REVISION = '([\d.]+)'", (HERE / 'build_font.py').read_text(), re.M)[1]
    if version in git('tag').split():
        sys.exit(f'{version} is already tagged')
    build = BUILDID.read_text().strip()
    git('add', '-A', 'source', 'data', 'build_font.py')
    git('commit', '-m', f'{version}: game build {build}')
    git('tag', version)
    git('push', 'origin', 'HEAD', version)
    run('gh', 'release', 'create', version, *ASSETS, '--title', version, '--notes-file', str(OUT / 'notes.md'))


if __name__ == '__main__':
    if sys.argv[1:2] == ['publish']:
        publish()
    else:
        build('--force' in sys.argv)
