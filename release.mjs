import assert from 'node:assert/strict'
import { copyFileSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { fontTokens } from './web/src/font-tokens.js'

const file = (path) => new URL(path, import.meta.url)
const read = (path) => readFileSync(file(path))
for (const name of ['demo.json', 'XingyuDemo-VF.ttf', 'XingyuDemo-VF.woff2']) {
  copyFileSync(file(`./data/${name}`), file(`./web/dist/${name}`))
}

const data = JSON.parse(read('./web/dist/demo.json'))
const fields = (object, allowed) => assert(Object.keys(object).every((k) => allowed.includes(k)), 'Unexpected data field')
fields(data, ['version', 'blocks', 'entries'])
const points = new Set(data.entries.map((e) => e.cp))
assert.equal(points.size, data.entries.length)
const ref = (cp) => assert(cp === '?' || points.has(cp), `Non-Demo reference: ${cp}`)
for (const e of data.entries) {
  fields(e, ['cp', 'struct', 'parts', 'cats', 'wt', 'roots', 'def'])
  assert(/^[A-F0-9]{5}$/.test(e.cp))
  assert(['s', 'exp', 'lr', 'ud', 'oi', 'our', 'oul', 'odr', 'odl', 'ol', 'or', 'd', 't', 'q', 'vd', 'flr', 'fud', 'fb'].includes(e.struct))
  for (const cp of [...e.parts ?? [], ...e.cats ?? [], ...e.wt ?? [], ...e.roots ?? []]) ref(cp)
  for (const cp of (e.def ?? []).flat()) {
    if (cp.startsWith('~')) assert(/^~[-\d./]+$/.test(cp), 'Non-numeric definition text')
    else ref(cp)
  }
}
for (const b of data.blocks) {
  fields(b, ['start', 'end', 'kind', 'head'])
  if (b.head) ref(b.head)
  if (b.kind) assert(['numeral', 'token', 'overflow'].includes(b.kind))
  const used = data.entries.filter((e) => e.cp >= b.start && e.cp <= b.end)
  assert(used.length)
  assert.equal(parseInt(b.start, 16), parseInt(used[0].cp, 16) & ~15)
  assert.equal(parseInt(b.end, 16), parseInt(used.at(-1).cp, 16) | 15)
}
rmSync(file('./web/dist/.DS_Store'), { force: true })
assert.deepEqual(readdirSync(file('./web/dist/')).sort(), ['XingyuDemo-VF.ttf', 'XingyuDemo-VF.woff2', 'assets', 'demo.json', 'index.html'])
const assets = readdirSync(file('./web/dist/assets/'))
assert.equal(assets.length, 2)
for (const name of assets) {
  assert(/^index-[\w-]+\.(js|css)$/.test(name), 'Unexpected build asset')
  assert(!/full\.json|Xingyu-VF\.(ttf|woff2)|sourceMappingURL/.test(read(`./web/dist/assets/${name}`).toString()), 'Private asset reference')
}
let ttfTokens
for (const ext of ['ttf', 'woff2']) {
  const bytes = read(`./web/dist/XingyuDemo-VF.${ext}`)
  const tokens = await fontTokens(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength))
  assert.deepEqual(new Set(tokens.values()), points)
  if (ttfTokens) assert.deepEqual(tokens, ttfTokens, 'Font index mismatch')
  else ttfTokens = tokens
}
console.log(`Release verified: ${points.size} Demo characters; no word hashes, names, meanings or full-edition files`)
