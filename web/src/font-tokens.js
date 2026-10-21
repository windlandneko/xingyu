// Read the font's original post/cmap tables, also embedded in our WOFF2 private block.
export async function fontTokens(buffer) {
  const header = new DataView(buffer)
  if (header.getUint32(0) === 0x774f4632) {
    const offset = header.getUint32(40), length = header.getUint32(44)
    if (!offset || offset + length > buffer.byteLength) throw new Error('Missing font index')
    const stream = new Blob([buffer.slice(offset, offset + length)]).stream().pipeThrough(new DecompressionStream('deflate'))
    buffer = await new Response(stream).arrayBuffer()
  }
  const view = new DataView(buffer)
  const u16 = (p) => view.getUint16(p)
  const u32 = (p) => view.getUint32(p)
  const text = (p, n) => new TextDecoder().decode(new Uint8Array(buffer, p, n))
  const tables = new Map()
  for (let p = 12; p < 12 + u16(4) * 16; p += 16) tables.set(text(p, 4), u32(p + 8))

  const post = tables.get('post')
  if (u32(post) !== 0x20000) throw new Error('Expected post 2.0')
  const count = u16(post + 32)
  const indices = Array.from({ length: count }, (_, i) => u16(post + 34 + i * 2))
  const names = []
  let p = post + 34 + count * 2
  for (let i = 258; i <= Math.max(...indices); i++) {
    const length = view.getUint8(p++)
    names[i] = text(p, length)
    p += length
  }

  const cmap = tables.get('cmap')
  let format12
  for (let i = 0; i < u16(cmap + 2); i++) {
    const offset = cmap + u32(cmap + 8 + i * 8)
    if (u16(offset) === 12) { format12 = offset; break }
  }
  if (!format12) throw new Error('Expected cmap 12')
  const tokens = new Map()
  for (let i = 0; i < u32(format12 + 12); i++) {
    const group = format12 + 16 + i * 12
    const start = u32(group), end = u32(group + 4), glyph = u32(group + 8)
    for (let cp = Math.max(start, 0xf7000); cp <= end; cp++) {
      const name = names[indices[glyph + cp - start]] ?? ''
      const token = name.startsWith('w.') ? name.slice(2)
        : name.startsWith('num.') ? name.slice(4).replace('em', 'e-').replace(/e0$/, '') : null
      if (token) tokens.set(token, cp.toString(16).toUpperCase())
    }
  }
  return tokens
}
