"""Excel (.xlsx) → IR。

1 シート = 1 見出し + 1 表。数式はキャッシュされた計算結果を採用する
（.xlsx には最後に Excel が計算した値が保存されている）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ..model import Document, Heading, Paragraph, Span, Table
from ..ooxml import OoxmlPackage, attr, q

WORKBOOK_PART = "xl/workbook.xml"
_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass(slots=True)
class _Cell:
    """セルの値と「データらしさ」。見出し行の推定に型の情報が要るため保持する。"""

    text: str
    is_data: bool = False
    """数値・真偽値・エラー値なら True。見出しには通常こうした値が来ない。"""


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
            if not grid:
                doc.add(Paragraph(spans=[Span("（空のシート）")]))
                continue
            # 見出し行の判定は打ち切る前の表全体で行う。
            # 先に切ると、下にあった数値が消えて判定が変わってしまうため
            header = has_header_row(grid)
            if max_rows is not None and len(grid) > max_rows:
                doc.warn(f"シート「{name}」を {max_rows} 行で打ち切りました（全 {len(grid)} 行）")
                grid = grid[:max_rows]
            doc.add(_table(grid, header=header))
        _report_graphics(pkg, doc)
    return doc


def _report_graphics(pkg: OoxmlPackage, doc: Document) -> None:
    """グラフ・図形の存在を伝える。セルの値しか読まないので、これらは必ず落ちる。"""
    names = pkg.zip.namelist()
    # グラフと画像は別々に数える。グラフがある本に画像も入っていることは普通にある
    charts = sum(1 for n in names if n.startswith("xl/charts/chart"))
    if charts:
        doc.warn(f"グラフを {charts} 個出力していません（Markdown に表現がありません）")
    images = sum(1 for n in names if n.startswith("xl/media/"))
    if images:
        doc.warn(f"画像を {images} 個出力していません")


def _table(grid: list[list[_Cell]], *, header: bool) -> Table:
    width = max(len(row) for row in grid)
    padded = [row + [_Cell("")] * (width - len(row)) for row in grid]
    if header:
        header = [[Span(c.text)] for c in padded[0]]
        body = padded[1:]
    else:
        # 見出しが無い表。GFM は空ヘッダを立てて全行をデータとして出す
        header = [[Span("")] for _ in range(width)]
        body = padded
    rows = [[[Span(c.text)] for c in row] for row in body]
    return Table(header=header, rows=rows)


def has_header_row(grid: list[list[_Cell]]) -> bool:
    """1 行目が見出し行かどうかを推定する。

    Excel のファイルには「ここが見出し」という情報が無いので、次の経験則で判定する。
      * 1 行目に値があり、そのすべてが文字列（数値・真偽値・エラーでない）
      * かつ 2 行目以降に数値などのデータらしい値が 1 つ以上ある
    判定ルールは docs/specs/05-conversion-rules.md に明記している。
    """
    if len(grid) < 2:
        return False
    first = [c for c in grid[0] if c.text]
    if not first or any(c.is_data for c in first):
        return False
    return any(c.is_data for row in grid[1:] for c in row)


def _sheet_grid(sheet: ET.Element, shared: list[str]) -> list[list[_Cell]]:
    """sheetData を二次元のセル配列にする。空行・空列は前詰めせず位置を保つ。"""
    data = sheet.find(q("x", "sheetData"))
    if data is None:
        return []

    cells: dict[tuple[int, int], _Cell] = {}
    max_row = max_col = -1
    for r_index, row in enumerate(data.findall(q("x", "row"))):
        row_no = int(row.get("r") or r_index + 1) - 1
        for c_index, cell in enumerate(row.findall(q("x", "c"))):
            ref = cell.get("r")
            col_no = _column_index(ref) if ref else c_index
            value = _cell_value(cell, shared)
            if value.text == "":
                continue
            cells[(row_no, col_no)] = value
            max_row = max(max_row, row_no)
            max_col = max(max_col, col_no)

    if max_row < 0:
        return []
    grid = [[_Cell("") for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for (r, c), value in cells.items():
        grid[r][c] = value
    # 完全に空の行は落とす（Excel は書式だけの行を大量に持つことがある）
    return [row for row in grid if any(cell.text for cell in row)]


def _cell_value(cell: ET.Element, shared: list[str]) -> _Cell:
    ctype = cell.get("t")
    if ctype == "inlineStr":
        return _Cell(_rich_text(cell.find(q("x", "is"))))
    value_el = cell.find(q("x", "v"))
    if value_el is None or value_el.text is None:
        return _Cell("")
    raw = value_el.text
    if ctype == "s":
        index = int(raw)
        return _Cell(shared[index] if 0 <= index < len(shared) else "")
    if ctype == "str":
        return _Cell(raw)  # 数式が返した文字列
    if ctype == "b":
        return _Cell("TRUE" if raw == "1" else "FALSE", is_data=True)
    if ctype == "e":
        return _Cell(raw, is_data=True)  # #DIV/0! などのエラー値はそのまま見せる
    return _Cell(_trim_number(raw), is_data=True)


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
