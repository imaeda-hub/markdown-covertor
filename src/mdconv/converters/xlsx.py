"""Excel (.xlsx) → IR。

1 シート = 1 見出し + 1 表。数式はキャッシュされた計算結果を採用する
（.xlsx には最後に Excel が計算した値が保存されている）。
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from ..model import Document, Heading, Paragraph, Span, Table
from ..ooxml import OoxmlPackage, attr, q

WORKBOOK_PART = "xl/workbook.xml"
_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def convert(path: str, *, include_hidden: bool = False, max_rows: int | None = None) -> Document:
    doc = Document(source_format="xlsx", source_name=path)
    with OoxmlPackage(path) as pkg:
        shared = _shared_strings(pkg)
        rels = pkg.rels(WORKBOOK_PART)
        book = pkg.xml(WORKBOOK_PART)
        sheets = book.find(q("x", "sheets"))
        if sheets is None:
            doc.warn("シートが見つかりませんでした")
            return doc

        for sheet in sheets.findall(q("x", "sheet")):
            name = sheet.get("name") or "Sheet"
            state = sheet.get("state")
            if state in ("hidden", "veryHidden") and not include_hidden:
                doc.warn(f"非表示シート「{name}」を除外しました（--include-hidden で出力）")
                continue
            target = rels.get(attr(sheet, "r", "id") or "")
            if not target or not pkg.has(target):
                doc.warn(f"シート「{name}」の実体が見つかりませんでした")
                continue

            doc.add(Heading(level=1, spans=[Span(name)]))
            grid = _sheet_grid(pkg.xml(target), shared)
            if max_rows is not None and len(grid) > max_rows:
                doc.warn(f"シート「{name}」を {max_rows} 行で打ち切りました（全 {len(grid)} 行）")
                grid = grid[:max_rows]
            if not grid:
                doc.add(Paragraph(spans=[Span("（空のシート）")]))
                continue
            doc.add(_table(grid))
    return doc


def _table(grid: list[list[str]]) -> Table:
    width = max(len(row) for row in grid)
    padded = [row + [""] * (width - len(row)) for row in grid]
    header = [[Span(c)] for c in padded[0]]
    rows = [[[Span(c)] for c in row] for row in padded[1:]]
    return Table(header=header, rows=rows)


def _sheet_grid(sheet: ET.Element, shared: list[str]) -> list[list[str]]:
    """sheetData を二次元の文字列配列にする。空行・空列は前詰めせず位置を保つ。"""
    data = sheet.find(q("x", "sheetData"))
    if data is None:
        return []

    cells: dict[tuple[int, int], str] = {}
    max_row = max_col = -1
    for r_index, row in enumerate(data.findall(q("x", "row"))):
        row_no = int(row.get("r") or r_index + 1) - 1
        for c_index, cell in enumerate(row.findall(q("x", "c"))):
            ref = cell.get("r")
            col_no = _column_index(ref) if ref else c_index
            value = _cell_value(cell, shared)
            if value == "":
                continue
            cells[(row_no, col_no)] = value
            max_row = max(max_row, row_no)
            max_col = max(max_col, col_no)

    if max_row < 0:
        return []
    grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for (r, c), value in cells.items():
        grid[r][c] = value
    # 完全に空の行は落とす（Excel は書式だけの行を大量に持つことがある）
    return [row for row in grid if any(cell for cell in row)]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    ctype = cell.get("t")
    if ctype == "inlineStr":
        return _rich_text(cell.find(q("x", "is")))
    value_el = cell.find(q("x", "v"))
    if value_el is None or value_el.text is None:
        return ""
    raw = value_el.text
    if ctype == "s":
        index = int(raw)
        return shared[index] if 0 <= index < len(shared) else ""
    if ctype == "b":
        return "TRUE" if raw == "1" else "FALSE"
    if ctype == "e":
        return raw  # #DIV/0! などのエラー値はそのまま見せる
    return _trim_number(raw)


def _trim_number(raw: str) -> str:
    """1.0 → 1、0.30000000000000004 → 0.3 のように見た目を整える。"""
    try:
        number = float(raw)
    except ValueError:
        return raw
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return repr(round(number, 10))


def _shared_strings(pkg: OoxmlPackage) -> list[str]:
    root = pkg.xml_or_none("xl/sharedStrings.xml")
    if root is None:
        return []
    return [_rich_text(si) for si in root.findall(q("x", "si"))]


def _rich_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    parts: list[str] = []
    for t in el.iter(q("x", "t")):
        parts.append(t.text or "")
    return "".join(parts)


def _column_index(ref: str) -> int:
    m = _CELL_REF.match(ref)
    if not m:
        return 0
    letters = m.group(1)
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1
