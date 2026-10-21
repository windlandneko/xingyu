import { createElement, createIcons, Copy, Download, Eye, Info, Search, X } from 'lucide'
import { joinWords, toPieces } from './convert.js'
import { fontTokens } from './font-tokens.js'
import { PRESETS } from './presets.js'

const $ = (id) => document.getElementById(id)
const esc = (s) => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
const hex = (n) => n.toString(16).toUpperCase()
const chr = (h) => String.fromCodePoint(parseInt(h, 16))
const icon = (node) => createElement(node, { 'aria-hidden': 'true' }).outerHTML
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem('xingyu.' + k)) ?? d } catch { return d } },
  set(k, v) { try { localStorage.setItem('xingyu.' + k, JSON.stringify(v)) } catch {} },
}
let toastTimer
function toast(msg) {
  $('toast').textContent = msg
  $('toast').classList.add('on')
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => $('toast').classList.remove('on'), 1600)
}
const copy = (text, what) => navigator.clipboard.writeText(text).then(() => toast(`已复制${what}`), () => toast('复制失败'))
createIcons({ icons: { Copy, Download, Eye, Info, Search, X }, attrs: { 'aria-hidden': 'true' } })

// ---------- data: data/ holds each edition's font and table; the full edition is optional ----------

async function loadEdition(family, font, table) {
  let face
  try {
    const [res, fontRes] = await Promise.all([fetch(import.meta.env.BASE_URL + table), fetch(import.meta.env.BASE_URL + font)])
    if (!res.ok || !fontRes.ok) throw new Error('Edition unavailable')
    const [data, buffer] = await Promise.all([res.json(), fontRes.arrayBuffer()])
    face = new FontFace(family, buffer, { weight: '100 900', display: 'block' })
    document.fonts.add(face)
    await face.load()
    const entries = data.entries.map((e) => ({ ...e, char: chr(e.cp) }))
    const byCp = new Map(entries.map((e) => [e.cp, e]))
    const byToken = new Map([...fontTokens(buffer)].map(([token, cp]) => [token, byCp.get(cp)]).filter(([, e]) => e))
    return { ...data, font, entries, byCp, byToken }
  } catch {
    if (face) document.fonts.delete(face)
    return null
  }
}
const [demo, full] = await Promise.all([
  loadEdition('Xingyu Demo', 'XingyuDemo-VF.ttf', 'demo.json'),
  import.meta.env.DEV ? loadEdition('Xingyu', 'Xingyu-VF.ttf', 'full.json') : null,
])

$('dl-demo').href = demo.font
if (full) {
  $('dl-full').href = full.font
  $('dl-full').hidden = false
} else $('dl-full').remove()
$('brand').textContent = chr('F7666')

const spoil = $('spoil')
if (full) spoil.hidden = false
else spoil.remove()
let showFull = !!full && store.get('spoil', false)
let ed
function applySpoil() {
  ed = showFull ? full : demo
  spoil.setAttribute('aria-pressed', String(showFull))
  document.documentElement.classList.toggle('spoil', showFull)
  $('stat').textContent = `v${ed.version} · ${showFull ? '完整版' : 'Demo 版'} ${ed.entries.length} 字`
}
spoil.addEventListener('click', () => {
  showFull = !showFull
  store.set('spoil', showFull)
  applySpoil()
  hist.list = []
  hist.i = -1
  hist.auto = false
  showDetail(null)
  renderChart()
})
applySpoil()
const lookup = (token) => ed.byToken.get(token)?.char

// ---------- typing pad ----------

const pad = $('pad-input')
$('presets').innerHTML = Object.keys(PRESETS).map((k) => `<button type="button" class="pill">${k}</button>`).join('')
$('presets').addEventListener('click', (ev) => {
  if (ev.target.tagName === 'BUTTON') { pad.value = PRESETS[ev.target.textContent]; pad.scrollTop = 0; updatePad() }
})
pad.value = store.get('pad', PRESETS.混排)

const feats = () => ({ ss01: $('f-ss01').checked, ss02: $('f-ss02').checked })
function updatePad() {
  const { ss01, ss02 } = feats()
  $('o-wght').textContent = pad.style.fontWeight = $('f-wght').value
  $('o-size').textContent = $('f-size').value
  pad.style.fontSize = $('f-size').value + 'px'
  pad.style.fontFeatureSettings = [ss01 && '"ss01"', ss02 && '"ss02"'].filter(Boolean).join(', ') || 'normal'
  $('pad-src').textContent = pad.value
  store.set('pad', pad.value)
}
for (const el of [pad, $('f-ss01'), $('f-ss02'), $('f-wght'), $('f-size')]) el.addEventListener('input', updatePad)
// word characters for ss02's joining: everything but numerals and the two words ss01 writes
const isWord = (ch) => {
  const e = ed.byCp.get(hex(ch.codePointAt(0)))
  return !!e && e.struct !== 'exp' && e !== ed.byToken.get('negative') && e !== ed.byToken.get('exp7')
}
$('copy-pua').addEventListener('click', () => {
  const text = toPieces(pad.value, { ...feats(), lookup }).map((p) => p.text ?? p.pua ?? '').join('')
  copy(feats().ss02 ? joinWords(text, isWord) : text, ' PUA 文本')
})
updatePad()

// ---------- code chart ----------

const STRUCT = { s: '单体', exp: '数字', lr: '左右', ud: '上下', oi: '内外', our: '右上包围', oul: '左上包围',
  odr: '右下包围', odl: '左下包围', ol: '左包围', or: '右包围', d: '双写', t: '三写', q: '四写', vd: '竖双写',
  flr: '左右翻转', fud: '上下翻转', fb: '旋转' }
const KIND = { numeral: ['数字', '每 8 格一个指数，从 −8 到 +7'], token: ['记号'], overflow: ['溢出区', '留给以后新增的字'] }

// a code point as a glyph button, or "?" for a character outside this edition
const ref = (cp) => (cp === '?' ? '<span class="part">?</span>'
  : `<button type="button" class="part xy" data-cp="${cp}" title="U+${cp}">${chr(cp)}</button>`)

function cell(e) {
  if (!e) return '<span class="cell empty"></span>'
  const title = esc(e.name ?? 'U+' + e.cp)
  return `<button type="button" class="cell${e === selected ? ' sel' : ''}" data-cp="${e.cp}" title="${title}">` +
    `<span class="xy">${e.char}</span><small>${e.cp.slice(-3)}</small></button>`
}

function renderBlock(b) {
  const lo = parseInt(b.start, 16), hi = parseInt(b.end, 16)
  const rows = []
  for (let r = lo; r <= hi; r += 16) {
    const cells = [...Array(16)].map((_, c) => ed.byCp.get(hex(r + c)))
    rows.push(`<div class="crow"><span class="rlabel">${hex(r).slice(0, -1)}x</span>${cells.map(cell).join('')}</div>`)
  }
  const head = () => (b.head === '?' ? '?' : `<span class="xy">${chr(b.head)}</span> ${b.name ?? ''}`)
  const [title, note] = KIND[b.kind] ?? [head()]
  const n = ed.entries.filter((e) => e.cp >= b.start && e.cp <= b.end).length
  return `<div class="block"><div class="bhead"><b>${title}</b><span>U+${b.start}–${b.end} · ${n}</span>` +
    `${note ? `<small>${note}</small>` : ''}</div>${rows.join('')}</div>`
}

// pasted PUA characters, what ss01 / ss02 would turn the text into, then code points (and names in the full edition)
function search(q) {
  const hits = new Map()
  const add = (e) => e && hits.set(e.cp, e)
  const pasted = (ch) => ed.byCp.get(hex(ch.codePointAt(0)))
  for (const ch of q) add(pasted(ch))
  for (const p of toPieces(q, { ss01: true, ss02: true, lookup })) if (p.pua) add(pasted(p.pua))
  const terms = q.toLowerCase().split(/\s+/)
  const match = (e, t) => (/^(u\+)?[0-9a-f]{3,5}$/.test(t) && e.cp.toLowerCase().endsWith(t.replace('u+', '')))
    || (e.name && `${e.name} ${e.meaning}`.toLowerCase().includes(t))
  for (const e of ed.entries) if (terms.every((t) => match(e, t))) add(e)
  return [...hits.values()]
}

function renderChart() {
  const q = $('q').value.trim()
  const hits = q && search(q)
  $('q-clear').disabled = !q
  $('q-count').textContent = q ? `${hits.length} 个` : ''
  $('chart-body').innerHTML = !q ? ed.blocks.map(renderBlock).join('')
    : hits.length ? `<div class="hits">${hits.map(cell).join('')}</div>` : '<p class="none">没有找到。</p>'
  if (hits?.length && !hits.includes(selected)) go(hits[0], true)
}

let selected = null
// The game's dictionary sentences, followed by a blank line and the definition.
const word = (x) => (x[0] === '~' ? `<span class="raw">${esc(x.slice(1).replace('div', '/'))}</span>` : ref(x))
const line = (xs, title = '') => `<p${title && ` title="${title}"`}>${xs.map(word).join('')}</p>`
const historyIcon = (forward) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${forward
  ? 'M23 1H12L1 12L12 23L23 12L12 1'
  : 'M1 23H12L23 12L12 1L1 12L12 23'}"/></svg>`
function showDetail(e) {
  selected = e
  document.querySelector('.cell.sel')?.classList.remove('sel')
  if (!e) { $('detail').innerHTML = '<p class="hint">左键插入兴语，右键查看字典。</p>'; return }
  const cell = document.querySelector(`.cell[data-cp="${e.cp}"]`)
  cell?.classList.add('sel')
  const row = (k, v) => (v ? `<dt>${k}</dt><dd>${v}</dd>` : '')
  const cp = (token) => ed.byToken.get(token)?.cp ?? '?'
  const be = [e.cp, cp('be')]
  const roots = e.roots?.length
    ? [e.cp, cp('de'), cp('radicial'), cp('be'), ...e.roots.flatMap((root, i) => i ? [cp('and'), root] : [root])]
    : [...be, cp('single'), cp('radicial')]
  const dict = e.wt?.length
    ? [line([...be, ...e.wt], '词性'), line(roots, '词根'),
      e.def?.length && '<p></p>', ...(e.def ?? []).map((l) => line(l))].filter(Boolean)
    : [line([e.cp, cp('benot'), cp('word')], '不是字')]
  const nav = (id, forward, title, ok) => `<button type="button" class="tool" id="${id}" title="${title}" aria-label="${title}"${ok ? '' : ' disabled'}>${historyIcon(forward)}</button>`
  $('detail').innerHTML = `<div class="dhead"><span class="dcode">U+${e.cp}</span>` +
    `<button type="button" class="pill" id="d-copy" aria-label="复制 U+${e.cp}">${icon(Copy)}复制</button>` +
    `<div class="dnav">${nav('d-back', false, '上一个', hist.i > 0)}${nav('d-fwd', true, '下一个', hist.i < hist.list.length - 1)}</div>` +
    `</div><div class="dtop"><button type="button" class="big xy" data-cp="${e.cp}" title="左键插入，右键查字典" aria-label="插入 U+${e.cp}">${e.char}</button>` +
    `<div class="dmeta">${e.name ? `<b class="word-name">${esc(e.name)}</b>` : ''}${e.demo === false ? '<small>仅完整版</small>' : ''}` +
    `<dl>${row('结构', STRUCT[e.struct])}${row('部件', !e.roots && e.parts?.map(ref).join(''))}` +
    `${row('类别', e.cats?.map(ref).join(''))}</dl></div></div>` +
    (dict.length ? `<div class="dict">${dict.join('')}</div>` : '') +
    (e.meaning ? `<p class="meaning">${esc(e.meaning)}</p>` : '')
  $('d-copy').onclick = () => copy(e.char, ` U+${e.cp}`)
  $('d-back').onclick = () => showDetail(hist.list[--hist.i])
  $('d-fwd').onclick = () => showDetail(hist.list[++hist.i])
}

// history for the card's back / forward; a search's automatic pick replaces itself instead of piling up
const hist = { list: [], i: -1, auto: false }
function go(e, auto = false) {
  if (e === hist.list[hist.i]) return showDetail(e)
  hist.list = hist.list.slice(0, hist.i + (hist.auto ? 0 : 1)).concat(e)
  hist.i = hist.list.length - 1
  hist.auto = auto
  showDetail(e)
}

for (const area of [$('chart-body'), $('detail')]) {
  area.addEventListener('click', (ev) => {
    const e = ed.byCp.get(ev.target.closest('button[data-cp]')?.dataset.cp)
    if (!e) return
    const start = pad.selectionStart
    pad.setRangeText(e.char, start, pad.selectionEnd, 'end')
    updatePad()
    toast('已加入打字区')
  })
  area.addEventListener('contextmenu', (ev) => {
    const e = ed.byCp.get(ev.target.closest('button[data-cp]')?.dataset.cp)
    if (!e) return
    ev.preventDefault()
    go(e)
  })
}
$('q').value = new URLSearchParams(location.search).get('q') ?? ''
let qTimer
$('q').addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(renderChart, 120) })
$('q-clear').addEventListener('click', () => { $('q').value = ''; renderChart(); $('q').focus() })
showDetail(null)
renderChart()
