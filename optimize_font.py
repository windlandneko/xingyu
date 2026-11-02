'''Deduplicate TTF outlines and build WOFF2: python optimize_font.py [font.ttf ...].'''
import sys
import zlib
from io import BytesIO
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.woff2 import WOFF2FlavorData


def save_font(font, path):
    path = Path(path)
    seen, aliases = {}, 0
    for name in font.getGlyphOrder():
        glyph = font['glyf'][name]
        if glyph.isComposite() or not glyph.numberOfContours:
            continue
        variations = font['gvar'].variations.get(name, [])
        signature = (tuple(glyph.coordinates), bytes(glyph.flags), tuple(glyph.endPtsOfContours),
                     glyph.program.getBytecode(), font['hmtx'][name],
                     tuple((tuple(sorted(v.axes.items())), tuple(v.coordinates)) for v in variations))
        if signature not in seen:
            seen[signature] = name
            continue
        pen = TTGlyphPen(font['glyf'])
        pen.addComponent(seen[signature], (1, 0, 0, 1, 0, 0))
        font['glyf'][name] = pen.glyph()
        font['gvar'].variations[name] = []
        aliases += 1
    # Reuse the original cmap/post tables inside WOFF2's standard private-data block.
    # The browser reads these with native Deflate; no extra word list or WOFF2 decoder.
    font.save(BytesIO())                 # settles maxp, which post compiles against
    index = TTFont()
    for tag in ('cmap', 'post'):
        table = DefaultTable(tag)
        table.data = font.getTableData(tag)
        index[tag] = table
    buffer = BytesIO()
    index.save(buffer)
    post = font['post'].formatType
    font['post'].formatType = 3.0        # the names are in the block above; browsers do not need a second copy
    font.flavor = 'woff2'
    font.flavorData = WOFF2FlavorData(transformedTables={'glyf', 'loca', 'hmtx'})
    font.flavorData.privData = zlib.compress(buffer.getvalue(), 9)
    web = path.with_suffix('.woff2')
    font.save(web)

    # WOFF2 keeps every delta: regular runs compress far better than the gaps IUP leaves. Uncompressed TTF wants IUP.
    font['post'].formatType, font.flavor, font.flavorData = post, None, None
    glyf, hmtx, vmtx = font['glyf'], font['hmtx'].metrics, font['vmtx'].metrics
    for name, variations in font['gvar'].variations.items():
        coords, controls = glyf._getCoordinatesAndControls(name, hmtx, vmtx)
        for v in variations:
            v.optimize(coords, controls.endPts, isComposite=glyf[name].isComposite())
    font.save(path)
    print(f'{path.name}: {path.stat().st_size:,} bytes; {web.name}: {web.stat().st_size:,} bytes; {aliases} shared outlines')


if __name__ == '__main__':
    for path in sys.argv[1:] or [Path(__file__).parent / 'data/Xingyu-VF.ttf']:
        save_font(TTFont(path, recalcTimestamp=False), path)
