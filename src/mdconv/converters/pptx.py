"""PowerPoint (.pptx) → IR。

1 スライド = 見出し（タイトル）+ 本文（箇条書き・表）+ 発表者ノート（引用）。
スライドの順序は presentation.xml の p:sldIdLst に従う（ファイル名順ではない）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from ..model import (
    Callout,
    Divider,
    Document,
    Heading,
    ListBlock,
    ListItem,
    Paragraph,
    Span,
    Table,
)
from ..ooxml import OoxmlPackage, attr, q

PRESENTATION_PART = "ppt/presentation.xml"
_TITLE_PLACEHOLDERS = {"title", "ctrTitle"}


def convert(path: str, *, include_notes: bool = True, slide_dividers: bool = True) -> Document:
    doc = Document(source_format="pptx", source_name=path)
    with OoxmlPackage(path) as pkg:
        for number, part in enumerate(_slide_parts(pkg, doc), start=1):
            if slide_dividers and number > 1:
                doc.add(Divider())
            _slide(pkg, doc, part, number, include_notes=include_notes)
    return doc


def _slide_parts(pkg: OoxmlPackage, doc: Document) -> list[str]:
    root = pkg.xml_or_none(PRESENTATION_PART)
    if root is None:
        doc.warn("presentation.xml が見つかりませんでした")
        return []
    rels = pkg.rels(PRESENTATION_PART)
    lst = root.find(q("p", "sldIdLst"))
    if lst is None:
        return []
    parts: list[str] = []
    for sld in lst.findall(q("p", "sldId")):
        target = rels.get(attr(sld, "r", "id") or "")
        if target and pkg.has(target):
            parts.append(target)
    return parts


def _slide(
    pkg: OoxmlPackage, doc: Document, part: str, number: int, *, include_notes: bool
) -> None:
    root = pkg.xml(part)
    tree = root.find(f"{q('p', 'cSld')}/{q('p', 'spTree')}")
    if tree is None:
        doc.warn(f"スライド {number} の内容を読めませんでした", location=part)
        return

    title: list[Span] | None = None
    body: list = []
    state = _SlideState(doc=doc, number=number)
    _collect_shapes(tree, body, state)
    title = state.title

    doc.add(Heading(level=1, spans=title or [Span(f"スライド {number}")]))
    doc.blocks.extend(body)
    state.report()

    if include_notes:
        notes = _notes(pkg, part)
        if notes:
            doc.add(Callout(label="発表者ノート", blocks=[Paragraph(spans=[Span(notes)])]))


@dataclass
class _SlideState:
    """1 枚のスライドを走査する間の持ち物。

    グループ図形は入れ子になるので、タイトルと「落とした要素」の集計を
    再帰の間ずっと持ち回る必要がある。
    """

    doc: Document
    number: int
    title: list[Span] | None = None
    dropped: Counter = field(default_factory=Counter)

    def drop(self, kind: str) -> None:
        self.dropped[kind] += 1

    def report(self) -> None:
        """落とした要素をまとめて警告する。黙って消さないことが最優先（01-product.md）。"""
        for kind, count in sorted(self.dropped.items()):
            self.doc.warn(f"スライド {self.number}: {kind} を {count} 個出力していません")


def _collect_shapes(parent: ET.Element, out: list, state: _SlideState) -> None:
    """図形ツリーを再帰的に辿る。グループ化された図形の中にも本文がある。"""
    for shape in parent:
        if shape.tag == q("p", "sp"):
            if state.title is None and _is_title(shape):
                state.title = _shape_title(shape)
                continue
            out.extend(_shape_blocks(shape))
        elif shape.tag == q("p", "grpSp"):
            _collect_shapes(shape, out, state)
        elif shape.tag == q("p", "graphicFrame"):
            table = _table(shape)
            if table is not None:
                out.append(table)
            else:
                state.drop(_graphic_kind(shape))
        elif shape.tag == q("p", "pic"):
            state.drop("画像")


def _graphic_kind(frame: ET.Element) -> str:
    """表以外の graphicFrame が何なのかを、埋め込まれた名前空間から判別する。"""
    data = frame.find(f"{q('a', 'graphic')}/{q('a', 'graphicData')}")
    uri = (data.get("uri") or "") if data is not None else ""
    if "chart" in uri:
        return "グラフ"
    if "diagram" in uri or "smartArt" in uri:
        return "SmartArt"
    if "ole" in uri.lower():
        return "埋め込みオブジェクト"
    return "図表"


def _placeholder_type(shape: ET.Element) -> str | None:
    """図形のプレースホルダ種別。type 属性が省略された場合の既定は body ではなく title。"""
    ph = shape.find(f"{q('p', 'nvSpPr')}/{q('p', 'nvPr')}/{q('p', 'ph')}")
    if ph is None:
        return None
    return ph.get("type") or "title"


def _is_title(shape: ET.Element) -> bool:
    return _placeholder_type(shape) in _TITLE_PLACEHOLDERS


def _shape_title(shape: ET.Element) -> list[Span]:
    spans: list[Span] = []
    body = shape.find(q("p", "txBody"))
    if body is None:
        return spans
    for i, para in enumerate(body.findall(q("a", "p"))):
        if i:
            spans.append(Span(" "))
        spans.extend(_para_spans(para))
    # 空のタイトル枠は「無題」として扱えるよう空リストを返す
    return spans if any(s.text.strip() for s in spans) else []


def _shape_blocks(shape: ET.Element) -> list:
    """図形のテキストを箇条書き（インデントつき）に変換する。"""
    body = shape.find(q("p", "txBody"))
    if body is None:
        return []
    items: list[ListItem] = []
    for para in body.findall(q("a", "p")):
        spans = _para_spans(para)
        if not any(s.text.strip() for s in spans):
            continue
        items.append(ListItem(spans=spans, level=_indent(para)))
    if not items:
        return []
    # 箇条書き記号を持たない 1 行だけの図形は、ただの本文として扱う
    if len(items) == 1 and items[0].level == 0 and _plain_text(body):
        return [Paragraph(spans=items[0].spans)]
    return [ListBlock(items=items)]


def _plain_text(body: ET.Element) -> bool:
    return any(p.find(f"{q('a', 'pPr')}/{q('a', 'buNone')}") is not None for p in body)


def _para_spans(para: ET.Element) -> list[Span]:
    spans: list[Span] = []
    for node in para:
        if node.tag == q("a", "r"):
            props = node.find(q("a", "rPr"))
            text_el = node.find(q("a", "t"))
            spans.append(
                Span(
                    text_el.text or "" if text_el is not None else "",
                    bold=_flag(props, "b"),
                    italic=_flag(props, "i"),
                    strike=_strike(props),
                    href=_hyperlink(props),
                )
            )
        elif node.tag == q("a", "br"):
            spans.append(Span(" "))
        elif node.tag == q("a", "fld"):
            text_el = node.find(q("a", "t"))
            if text_el is not None and text_el.text:
                spans.append(Span(text_el.text))
    return spans


def _flag(props: ET.Element | None, name: str) -> bool:
    return props is not None and props.get(name) in ("1", "true")


def _strike(props: ET.Element | None) -> bool:
    return props is not None and props.get("strike") not in (None, "noStrike")


def _hyperlink(props: ET.Element | None) -> str | None:
    # 外部 URL の解決には rels が要るため、現状は内部リンクのみ検出して落とす
    return None


def _indent(para: ET.Element) -> int:
    ppr = para.find(q("a", "pPr"))
    if ppr is None:
        return 0
    try:
        return max(0, min(int(ppr.get("lvl") or 0), 5))
    except ValueError:
        return 0


def _table(frame: ET.Element) -> Table | None:
    tbl = frame.find(f"{q('a', 'graphic')}/{q('a', 'graphicData')}/{q('a', 'tbl')}")
    if tbl is None:
        return None
    rows: list[list[list[Span]]] = []
    for tr in tbl.findall(q("a", "tr")):
        row: list[list[Span]] = []
        for tc in tr.findall(q("a", "tc")):
            cell: list[Span] = []
            body = tc.find(q("a", "txBody"))
            if body is not None:
                for i, para in enumerate(body.findall(q("a", "p"))):
                    if i:
                        cell.append(Span("\n"))
                    cell.extend(_para_spans(para))
            row.append(cell)
        rows.append(row)
    if not rows:
        return None
    return Table(header=rows[0], rows=rows[1:])


def _notes(pkg: OoxmlPackage, slide_part: str) -> str:
    for target in pkg.rels(slide_part).values():
        if "notesSlide" not in target or not pkg.has(target):
            continue
        root = pkg.xml(target)
        lines: list[str] = []
        for shape in root.iter(q("p", "sp")):
            if _placeholder_type(shape) in {"title", "ctrTitle", "sldNum", "dt", "ftr"}:
                continue
            body = shape.find(q("p", "txBody"))
            if body is None:
                continue
            for para in body.findall(q("a", "p")):
                text = "".join(s.text for s in _para_spans(para)).strip()
                if text:
                    lines.append(text)
        if lines:
            return "\n".join(lines)
    return ""
