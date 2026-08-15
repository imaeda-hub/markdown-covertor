"""テスト用に最小限の OOXML ファイルを組み立てるヘルパ。

python-docx などの生成用ライブラリに頼らず、必要な XML だけを手で書くことで
  * テストが外部依存なしで動く
  * 「どの XML がどの Markdown になるか」がテストを読めば分かる
ようにしている。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
X = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'


def write_zip(path: Path, parts: dict[str, str | bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in parts.items():
            zf.writestr(name, content)
    return path


# --------------------------------------------------------------------------
# Word
# --------------------------------------------------------------------------

DEFAULT_STYLES = f"""<w:styles {W}>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/></w:style>
  <!-- Word の「箇条書き」スタイルは、段落ではなくスタイル側に番号定義を持つ -->
  <w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/>
    <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListBullet2"><w:name w:val="List Bullet 2"/>
    <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListNumber"><w:name w:val="List Number"/>
    <w:pPr><w:numPr><w:numId w:val="2"/></w:numPr></w:pPr></w:style>
  <!-- 日本語版 Word は styleId に連番を振る。末尾の 5 を階層と誤読しないこと -->
  <w:style w:type="paragraph" w:styleId="a5"><w:name w:val="List Bullet 2"/>
    <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
</w:styles>"""

DEFAULT_NUMBERING = f"""<w:numbering {W}>
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
    <w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""


def docx(
    path: Path,
    body: str,
    *,
    rels: dict[str, str] | None = None,
    media: dict[str, bytes] | None = None,
    title: str | None = None,
) -> Path:
    parts: dict[str, str | bytes] = {
        "word/document.xml": f"<w:document {W} {R}><w:body>{body}</w:body></w:document>",
        "word/styles.xml": DEFAULT_STYLES,
        "word/numbering.xml": DEFAULT_NUMBERING,
        "word/_rels/document.xml.rels": _rels(rels or {}),
    }
    for name, data in (media or {}).items():
        parts[f"word/media/{name}"] = data
    if title:
        parts["docProps/core.xml"] = (
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
            'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{title}</dc:title></cp:coreProperties>"
        )
    return write_zip(path, parts)


def para(
    text: str,
    *,
    style: str | None = None,
    num: tuple[str | None, int | None] | None = None,
) -> str:
    """段落を組み立てる。num は (numId, ilvl)。片方だけ指定すると実ファイル同様その要素だけ書く。"""
    props = ""
    if style:
        props += f'<w:pStyle w:val="{style}"/>'
    if num:
        num_id, ilvl = num
        inner = ""
        if ilvl is not None:
            inner += f'<w:ilvl w:val="{ilvl}"/>'
        if num_id is not None:
            inner += f'<w:numId w:val="{num_id}"/>'
        props += f"<w:numPr>{inner}</w:numPr>"
    ppr = f"<w:pPr>{props}</w:pPr>" if props else ""
    return f"<w:p>{ppr}{run(text)}</w:p>"


def run(text: str, *, bold: bool = False, italic: bool = False, strike: bool = False) -> str:
    props = ""
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if strike:
        props += "<w:strike/>"
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def table(rows: list[list[str]]) -> str:
    out = ["<w:tbl>"]
    for row in rows:
        out.append("<w:tr>")
        for cell in row:
            out.append(f"<w:tc>{para(cell)}</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def _rels(mapping: dict[str, str]) -> str:
    items = []
    for rid, target in mapping.items():
        mode = ' TargetMode="External"' if "://" in target else ""
        items.append(
            f'<Relationship Id="{rid}" Type="http://example/rel" Target="{target}"{mode}/>'
        )
    return f"<Relationships {REL}>{''.join(items)}</Relationships>"


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------


def xlsx(
    path: Path, sheets: dict[str, list[list[object]]], *, hidden: set[str] | None = None
) -> Path:
    hidden = hidden or set()
    strings: list[str] = []
    parts: dict[str, str | bytes] = {}
    sheet_entries: list[str] = []
    rel_entries: dict[str, str] = {}

    for index, (name, grid) in enumerate(sheets.items(), start=1):
        rid = f"rId{index}"
        state = ' state="hidden"' if name in hidden else ""
        sheet_entries.append(f'<sheet name="{name}" sheetId="{index}" r:id="{rid}"{state}/>')
        rel_entries[rid] = f"worksheets/sheet{index}.xml"
        parts[f"xl/worksheets/sheet{index}.xml"] = _sheet(grid, strings)

    parts["xl/workbook.xml"] = (
        f"<workbook {X} {R}><sheets>{''.join(sheet_entries)}</sheets></workbook>"
    )
    parts["xl/_rels/workbook.xml.rels"] = _rels(rel_entries)
    items = "".join(f"<si><t>{s}</t></si>" for s in strings)
    parts["xl/sharedStrings.xml"] = f'<sst {X} count="{len(strings)}">{items}</sst>'
    return write_zip(path, parts)


def _sheet(grid: list[list[object]], strings: list[str]) -> str:
    rows: list[str] = []
    for r, row in enumerate(grid, start=1):
        cells: list[str] = []
        for c, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{_col_letter(c)}{r}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                if value not in strings:
                    strings.append(str(value))
                cells.append(f'<c r="{ref}" t="s"><v>{strings.index(str(value))}</v></c>')
        rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    return f"<worksheet {X}><sheetData>{''.join(rows)}</sheetData></worksheet>"


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


# --------------------------------------------------------------------------
# PowerPoint
# --------------------------------------------------------------------------


def pptx(path: Path, slides: list[dict]) -> Path:
    """slides: [{"title": str, "bullets": [(level, text)], "notes": str}] の並び。"""
    parts: dict[str, str | bytes] = {}
    entries: list[str] = []
    rel_entries: dict[str, str] = {}

    for index, slide in enumerate(slides, start=1):
        rid = f"rId{index}"
        entries.append(f'<p:sldId id="{255 + index}" r:id="{rid}"/>')
        rel_entries[rid] = f"slides/slide{index}.xml"
        parts[f"ppt/slides/slide{index}.xml"] = _slide(slide)
        slide_rels: dict[str, str] = {}
        if slide.get("notes"):
            parts[f"ppt/notesSlides/notesSlide{index}.xml"] = _notes(slide["notes"])
            slide_rels["rId1"] = f"../notesSlides/notesSlide{index}.xml"
        parts[f"ppt/slides/_rels/slide{index}.xml.rels"] = _rels(slide_rels)

    parts["ppt/presentation.xml"] = (
        f"<p:presentation {P} {R}><p:sldIdLst>{''.join(entries)}</p:sldIdLst></p:presentation>"
    )
    parts["ppt/_rels/presentation.xml.rels"] = _rels(rel_entries)
    return write_zip(path, parts)


def _slide(slide: dict) -> str:
    shapes = [_shape(slide.get("title", ""), placeholder="title")]
    bullets = slide.get("bullets") or []
    if bullets:
        paragraphs = "".join(
            f'<a:p><a:pPr lvl="{level}"/><a:r><a:t>{text}</a:t></a:r></a:p>'
            for level, text in bullets
        )
        shapes.append(
            f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>'
            f"<p:txBody>{paragraphs}</p:txBody></p:sp>"
        )
    if slide.get("table"):
        shapes.append(_table_frame(slide["table"]))
    return f"<p:sld {P} {A} {R}><p:cSld><p:spTree>{''.join(shapes)}</p:spTree></p:cSld></p:sld>"


def _shape(text: str, *, placeholder: str) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="{placeholder}"/></p:nvPr></p:nvSpPr>'
        f"<p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>"
    )


def _table_frame(rows: list[list[str]]) -> str:
    trs = "".join(
        "<a:tr>"
        + "".join(
            f"<a:tc><a:txBody><a:p><a:r><a:t>{c}</a:t></a:r></a:p></a:txBody></a:tc>" for c in row
        )
        + "</a:tr>"
        for row in rows
    )
    return (
        "<p:graphicFrame><a:graphic><a:graphicData>"
        f"<a:tbl>{trs}</a:tbl>"
        "</a:graphicData></a:graphic></p:graphicFrame>"
    )


def _notes(text: str) -> str:
    paragraphs = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in text.split("\n"))
    return (
        f"<p:notes {P} {A}><p:cSld><p:spTree>"
        f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>'
        f"<p:txBody>{paragraphs}</p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:notes>"
    )
