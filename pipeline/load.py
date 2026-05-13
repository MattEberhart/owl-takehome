"""
Source-file loading. Dispatches on file extension:
  .csv  → pd.read_csv
  .xlsx → custom zipfile/XML parser (these particular files use a
          non-standard namespace that openpyxl refuses to parse;
          rolling our own keeps the pipeline self-contained and works
          regardless of vendor/exporter quirks)

Returned DataFrame has cleaned columns:
  - name stripped of leading/trailing whitespace
  - asof normalized to ISO date string (YYYY-MM-DD)
  - volume cast to int, close_usd & mktcap_usd cast to float
The mktcap_usd column is present iff the source has it.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

# Two namespaces the OOXML standard uses; some exporters pick the OCLC variant.
_NS_CANDIDATES = (
    'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'http://purl.oclc.org/ooxml/spreadsheetml/main',
)


def _read_xlsx_rows(path: str | Path) -> list[list[str]]:
    """Parse the first worksheet of an xlsx via zipfile + ET. Returns rows of strings."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        # Pick whichever namespace this file actually uses by sniffing sheet1.xml.
        sheet_path = next(n for n in names if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))
        with z.open(sheet_path) as f:
            sheet_xml = f.read()
        ns = None
        for candidate in _NS_CANDIDATES:
            if f'xmlns="{candidate}"'.encode() in sheet_xml:
                ns = '{' + candidate + '}'
                break
        if ns is None:
            raise ValueError(f'Unrecognized OOXML namespace in {path}')

        shared_strings: list[str] = []
        if 'xl/sharedStrings.xml' in names:
            with z.open('xl/sharedStrings.xml') as f:
                tree = ET.parse(f)
            for si in tree.getroot().findall(f'{ns}si'):
                t = si.find(f'{ns}t')
                shared_strings.append(t.text if t is not None and t.text is not None else '')

        sheet = ET.fromstring(sheet_xml)
        sheet_data = sheet.find(f'{ns}sheetData')
        if sheet_data is None:
            raise ValueError(f'No sheetData in {path}')

        rows: list[list[str]] = []
        for r in sheet_data.findall(f'{ns}row'):
            row: list[str] = []
            for c in r.findall(f'{ns}c'):
                t = c.get('t')
                v = c.find(f'{ns}v')
                text = v.text if v is not None and v.text is not None else ''
                row.append(shared_strings[int(text)] if t == 's' else text)
            rows.append(row)
        return rows


def _xlsx_to_dataframe(path: str | Path) -> pd.DataFrame:
    rows = _read_xlsx_rows(path)
    if not rows:
        raise ValueError(f'No rows in {path}')
    header, *body = rows
    return pd.DataFrame(body, columns=header)


def load_source(path: str | Path) -> pd.DataFrame:
    """
    Load the source file and return a cleaned DataFrame.

    Cleaning steps:
      - Whitespace-strip `name`.
      - Coerce numeric columns.
      - Render `asof` as ISO date string.
      - Drop the row-index `#` column (it's a CSV-export artifact, not data).
    """
    path = str(path)
    if path.endswith('.csv'):
        df = pd.read_csv(path)
    elif path.endswith('.xlsx'):
        df = _xlsx_to_dataframe(path)
    else:
        raise ValueError(f'Unsupported file extension: {path}')

    # Drop the leading row-counter column if present.
    if '#' in df.columns:
        df = df.drop(columns=['#'])

    df['name'] = df['name'].astype(str).str.strip()
    df['asof'] = pd.to_datetime(df['asof']).dt.strftime('%Y-%m-%d')
    df['volume'] = pd.to_numeric(df['volume']).astype('int64')
    df['close_usd'] = pd.to_numeric(df['close_usd']).astype('float64')
    df['sector_level1'] = df['sector_level1'].astype(str).str.strip()
    df['sector_level2'] = df['sector_level2'].astype(str).str.strip()
    if 'mktcap_usd' in df.columns:
        df['mktcap_usd'] = pd.to_numeric(df['mktcap_usd']).astype('float64')

    return df.reset_index(drop=True)
