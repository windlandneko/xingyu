'''Follow a game update from Steam to a GitHub release.

  python3 update.py            sync the game from the Parallels VM, rebuild, test, then publish, or stop for review
  python3 update.py --force    the same even when Steam has no newer build than source/buildid.txt
  python3 update.py publish    commit, tag, push and release what the last run built (after the diff was approved)

Steps: the public build id comes from api.steamcmd.net; the VM's Steam downloads it (the VM is resumed and put back
the way it was), robocopy mirrors it to ../Message From Aliens; prepare.py, build_font.py (VERSION bumped to the next
minor) and test_font.py run. If any code point is added, removed or redrawn, .update/diff.html is written (green added,
red removed, blue changed) and the run stops: look at it, edit .update/notes.md if needed, then run publish.
Otherwise it publishes at once. Only the standard library is needed here; the steps run under uv.'''
import base64
import csv
import html
import io
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / '.update'
BUILDID = HERE / 'source/buildid.txt'
APP = '1858720'
VM = 'Windows 11'
VM_GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Message From Aliens'
VM_MANIFEST = rf'C:\Program Files (x86)\Steam\steamapps\appmanifest_{APP}.acf'
MAC_GAME = r'\\Mac\Home\Documents\alien\Message From Aliens'     # the VM's view of HERE.parent
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

def steam_build():
    with urllib.request.urlopen(f'https://api.steamcmd.net/v1/info/{APP}', timeout=30) as fh:
        return json.load(fh)['data'][APP]['depots']['branches']['public']['buildid']


def vm(*cmd):
    r = subprocess.run(['prlctl', 'exec', VM, 'cmd', '/c', *cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode('gbk', 'replace')


def sync_game(build):
    '''Wait until the VM's Steam has `build` installed, then mirror the game into HERE.parent.'''
    state = run('prlctl', 'status', VM, capture=True).split()[-1]
    if state != 'running':
        run('prlctl', 'resume' if state in ('suspended', 'paused') else 'start', VM)
    try:
        for _ in range(120):     # 60 min: Steam has to notice the update and download it
            code, acf = vm('type', VM_MANIFEST)
            fields = dict(re.findall(r'"(\w+)"\s+"([^"]*)"', acf))
            if fields.get('buildid') == build and fields.get('StateFlags') == '4':
                break
            print(f"VM: build {fields.get('buildid')}, state {fields.get('StateFlags')}; waiting for {build}", flush=True)
            time.sleep(30)
        else:
            sys.exit(f'Steam in the VM did not install build {build}; is it signed in?')
        code, out = vm('robocopy', VM_GAME, MAC_GAME, '/MIR', '/NJH', '/NDL', '/NP', '/R:1', '/W:1')
        if code >= 8:    # robocopy: below 8 is success
            sys.exit(out)
    finally:
        if state in ('suspended', 'stopped'):
            run('prlctl', 'suspend', VM)


# ---------- diff ----------

def registry(text):
    return {r['codepoint']: r for r in csv.DictReader(io.StringIO(text))}


def changes():
    '''code point -> ('add' | 'del' | 'mod', old word, new word), plus words whose meaning changed.'''
    old, new = registry(git('show', 'HEAD:source/registry.csv')), registry((HERE / 'source/registry.csv').read_text())
    og, ng = json.loads(git('show', 'HEAD:source/glyphs.json')), json.loads((HERE / 'source/glyphs.json').read_text())
    shape = lambda g, w: json.dumps(g.get(w), separators=(',', ':'))
    out = {}
    for cp in old.keys() | new.keys():
        a, b = old.get(cp), new.get(cp)
        if not b:
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


def render(diff, meanings, version):
    '''A page of every 16-cell row with a change; the old font draws removed glyphs, the new one the rest.'''
    font = lambda b: 'data:font/woff2;base64,' + base64.b64encode(b).decode()
    old_font = font(subprocess.run(['git', 'show', 'HEAD:data/Xingyu-VF.woff2'], cwd=HERE, check=True,
                                   stdout=subprocess.PIPE).stdout)
    new_font = font((HERE / 'data/Xingyu-VF.woff2').read_bytes())
    old, new = registry(git('show', 'HEAD:source/registry.csv')), registry((HERE / 'source/registry.csv').read_text())
    rows = sorted({int(cp[2:], 16) & ~15 for cp in diff})
    body = []
    for row in rows:
        cells = []
        for cp in range(row, row + 16):
            key, ch = f'U+{cp:05X}', chr(cp)
            kind, was, now = diff.get(key, ('', '', (new.get(key) or {}).get('word', '')))
            block = (new.get(key) or old.get(key) or {}).get('block', '')
            glyph = (f'<b class="o">{ch}</b>' if kind == 'del' else
                     f'<b class="o">{ch}</b><i>→</i><b>{ch}</b>' if kind == 'mod' and was == now else
                     f'<b>{ch}</b>' if now else '')
            label = html.escape(f'{was} → {now}' if kind == 'mod' and was != now else was if kind == 'del' else now)
            cells.append(f'<div class="c {kind}" title="{key} {block}">{glyph}<span>{label}</span>'
                         f'<code>{cp & 15:X}</code></div>')
        body.append(f'<div class="r"><code class="h">{row >> 4:X}x</code>{"".join(cells)}</div>')
    count = {k: sum(v[0] == k for v in diff.values()) for k in ('add', 'del', 'mod')}
    mean = ''.join(f'<li><b>{html.escape(w)}</b>：<s>{html.escape(a)}</s> → {html.escape(b)}</li>' for w, a, b in meanings)
    page = f'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>码位变化 v{version}</title><style>
@font-face{{font-family:old;src:url({old_font})}} @font-face{{font-family:new;src:url({new_font})}}
:root{{--bg:#fafaf9;--fg:#1c1917;--mute:#a8a29e;--ring:#e7e5e4;--add:#16a34a;--del:#dc2626;--mod:#2563eb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1917;--fg:#f5f5f4;--mute:#78716c;--ring:#44403c;
--add:#4ade80;--del:#f87171;--mod:#60a5fa}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} .k{{display:flex;gap:16px;margin:0 0 20px;flex-wrap:wrap}}
.k span::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;
background:currentColor}} .wrap{{overflow-x:auto}}
.r{{display:grid;grid-template-columns:48px repeat(16,minmax(64px,1fr));gap:4px;margin-bottom:4px;min-width:1100px}}
.h{{align-self:center;color:var(--mute)}}
.c{{position:relative;border-radius:8px;box-shadow:inset 0 0 0 1px var(--ring);padding:6px 4px 4px;text-align:center;
min-height:70px;color:var(--mute)}}
.c b{{font:400 30px/1.1 new;color:var(--fg)}} .c b.o{{font-family:old}} .c i{{font-style:normal;margin:0 2px}}
.c span{{display:block;font-size:11px;overflow-wrap:anywhere}} .c code{{position:absolute;top:3px;left:6px;font-size:10px}}
.add{{box-shadow:inset 0 0 0 2px var(--add);color:var(--add)}} .del{{box-shadow:inset 0 0 0 2px var(--del);color:var(--del)}}
.del b{{opacity:.5}} .mod b{{font-size:22px}} .mod{{box-shadow:inset 0 0 0 2px var(--mod);color:var(--mod)}}
li s{{color:var(--mute)}}</style></head><body>
<h1>兴语 v{version} 码位变化</h1>
<div class="k"><span style="color:var(--add)">新增 {count['add']}</span><span style="color:var(--del)">删除 {count['del']}</span>
<span style="color:var(--mod)">修改 {count['mod']}（字形重画或换字）</span></div>
<div class="wrap">{''.join(body)}</div>
<h2>释义变化 {len(meanings)}</h2><ul>{mean}</ul></body></html>'''
    (OUT / 'diff.html').write_text(page)


def notes(diff, meanings, version, build):
    '''A draft of the release notes, in the style of the earlier releases.'''
    old = git('describe', '--tags', '--abbrev=0')
    pick = lambda k: [v for v in diff.items() if v[1][0] == k]
    word = lambda kv, w: f'{w}（{kv[0]}）'
    swapped = [kv for kv in pick('mod') if kv[1][1] != kv[1][2]]
    out = ['有码位换了字，见下文。' if swapped else f'{old} 已有的码位不变，只增删。', '', '## 字体',
           f'- 跟进游戏更新（Steam build {build}）。']
    if adds := pick('add'):
        out.append('- 新增 ' + '、'.join(word(kv, kv[1][2]) for kv in adds) + '。')
    if dels := pick('del'):
        out.append('- 游戏移除 ' + '、'.join(word(kv, kv[1][1]) for kv in dels) + '，码位留给同组新字。')
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
    latest = steam_build()
    if not force and BUILDID.exists() and BUILDID.read_text().strip() == latest:
        print('game unchanged at build', latest)
        return
    if git('status', '--porcelain', 'source', 'data', 'build_font.py'):
        sys.exit('the working tree has changes; commit or stash them first')
    sync_game(latest)
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
        print(f'\n{len(diff)} code points changed: review {OUT / "diff.html"} and {OUT / "notes.md"}, '
              'then run: python3 update.py publish')
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
