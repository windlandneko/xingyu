// What the font's features do, in plain JS (the same rules as test_font.py): used for search and to turn text into
// PUA characters that keep their look without the features.

const digits7 = (n) => {
  const ds = []
  for (; n > 0n; n /= 7n) ds.push(Number(n % 7n))
  return ds.length ? ds : [0]
}

// every non-zero base-7 digit d at place p as "d" / "dep"
export function toBase7(n) {
  if (n === 0n) return ['0']
  const neg = n < 0n
  const ds = digits7(neg ? -n : n)
  const out = neg ? ['negative'] : []
  for (let p = ds.length - 1; p >= 0; p--) if (ds[p]) out.push(p === 0 ? String(ds[p]) : `${ds[p]}e${p}`)
  return out
}

// from 343 on: two significant base-7 digits (the third rounds), exp7 and the exponent
export function toBase7Exp(n) {
  const neg = n < 0n
  const ds = digits7(neg ? -n : n).reverse()
  const k = ds.length - 1
  let d1 = ds[0], d2 = ds[1] + (ds[2] >= 4 ? 1 : 0)
  if (d2 === 7) { d1 += 1; d2 = 0 }
  const out = neg ? ['negative'] : []
  if (d1 === 7) return [...out, '1', 'exp7', ...toBase7(BigInt(k + 1))]
  return [...out, String(d1), ...(d2 ? [`${d2}e-1`] : []), 'exp7', ...toBase7(BigInt(k))]
}

export const integer = (n) => (n >= 343n || n <= -343n ? toBase7Exp(n) : toBase7(n))

// decimals below 2401: positional digits and two base-7 places, rounded on the third; otherwise the integer part
export function decimal(s) {
  const neg = s.startsWith('-')
  const [ip, fp] = s.replace('-', '').split('.')
  const scale = 10n ** BigInt(fp.length)
  const num = BigInt(ip) * scale + BigInt(fp)
  if (num >= 2401n * scale) return integer(neg ? -BigInt(ip) : BigInt(ip))
  let q = (num * 343n) / scale
  q = q / 7n + (q % 7n >= 4n ? 1n : 0n)
  const whole = q / 49n, f = Number(q % 49n)
  const out = whole ? toBase7(whole) : []
  if (Math.floor(f / 7)) out.push(`${Math.floor(f / 7)}e-1`)
  if (f % 7) out.push(`${f % 7}e-2`)
  return [...(neg ? ['negative'] : []), ...(out.length ? out : ['0'])]
}

export const NUMBER = /-?\d+(?:\.\d+)?/g
export const MAX_DIGITS = 20     // longest integer part the font's GSUB arithmetic handles

// how ss01 reads one number token, or null when the font leaves it alone
export function readNumber(tok) {
  const ip = tok.replace('-', '').split('.')[0]
  if (ip.length > MAX_DIGITS) return null
  return tok.includes('.') ? decimal(tok) : integer(BigInt(tok))
}

// text -> pieces [{text} | {pua}], applying ss02 (whole words, "3e-1" tokens) and then ss01 (numbers);
// lookup(token) gives the token's character, if the edition has one
export function toPieces(text, { ss01, ss02, lookup }) {
  const pieces = []
  const plain = (t) => {
    if (!ss01) return t && pieces.push({ text: t })
    let last = 0
    for (const m of t.matchAll(NUMBER)) {
      const read = readNumber(m[0])
      if (!read) continue
      if (m.index > last) pieces.push({ text: t.slice(last, m.index) })
      for (const r of read) pieces.push({ pua: lookup(r) })
      last = m.index + m[0].length
    }
    if (last < t.length) pieces.push({ text: t.slice(last) })
  }
  if (!ss02) { plain(text); return pieces }
  // a word is a run of letters and digits; "3e-1" is the run "3e", a hyphen and a lone digit
  const re = /([A-Za-z0-9]+)(-[0-9]+(?![A-Za-z0-9]))?/g
  let last = 0
  for (const m of text.matchAll(re)) {
    let pua, len
    if (m[2] && /^[1-6]e$/.test(m[1]) && (pua = lookup(m[1] + m[2]))) len = m[0].length
    else if (!/^[0-6]$/.test(m[1]) && (pua = lookup(m[1]))) len = m[1].length
    if (!pua) continue
    plain(text.slice(last, m.index))
    pieces.push({ pua })
    last = m.index + len
  }
  plain(text.slice(last))
  return pieces
}

// ss02 joins words: between two word characters the first space of a run is hidden (the font does the same)
export const joinWords = (s, isWord) =>
  s.replace(/(?<=([\s\S])) {1,8}(?=([\s\S]))/gu, (sp, a, b) => (isWord(a) && isWord(b) ? sp.slice(1) : sp))
