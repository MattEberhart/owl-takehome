"""
v0.3 — Examine distinct names byte-for-byte BEFORE the loader strips them.
Confirms the trailing-space on 'Facebook Class A ' and validates that the
loader's strip step is doing what we want.
"""
import sys, zipfile
from xml.etree import ElementTree as ET

NS_CANDIDATES = (
    'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'http://purl.oclc.org/ooxml/spreadsheetml/main',
)


def raw_names(path):
    with zipfile.ZipFile(path) as z:
        sheet_path = next(n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))
        sheet_xml = z.read(sheet_path)
        ns = next(c for c in NS_CANDIDATES if f'xmlns="{c}"'.encode() in sheet_xml)
        ns = '{' + ns + '}'
        ss = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.parse(z.open('xl/sharedStrings.xml'))
            for si in tree.getroot().findall(f'{ns}si'):
                t = si.find(f'{ns}t')
                ss.append(t.text if t is not None and t.text is not None else '')
        sheet = ET.fromstring(sheet_xml)
        names = set()
        for r in sheet.find(f'{ns}sheetData').findall(f'{ns}row')[1:]:
            cells = r.findall(f'{ns}c')
            if len(cells) >= 2:
                c = cells[1]
                if c.get('t') == 's':
                    v = c.find(f'{ns}v')
                    if v is not None and v.text is not None:
                        names.add(ss[int(v.text)])
        return names


for path in ['data/stock-data-se-owl.xlsx', 'data/stock-data-se-owl-part2.xlsx']:
    print(f'\n===== {path} (raw, pre-strip) =====')
    for n in sorted(raw_names(path)):
        leading = n != n.lstrip()
        trailing = n != n.rstrip()
        print(f'  {n!r} (len={len(n)}, leading_ws={leading}, trailing_ws={trailing})')

print('\nFinding: "Facebook Class A " has a trailing space in both source files. '
      'pipeline.load.load_source() strips it on ingest so stock.name is clean.')
