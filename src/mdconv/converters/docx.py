"""Word (.docx) → IR。"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from ..model import (
    Asset,
    Callout,
    Document,
    Heading,
    Image,
    ListBlock,
    ListItem,
    Paragraph,
    Span,
    Table,
)
from ..ooxml import OoxmlPackage, attr, q

DOCUMENT_PART = "word/document.xml"

# 「Heading 2」「見出し 2」「Titre 2」などから数字を拾う
_HEADING_NUM = re.compile(r"(\d+)\s*$")
_HEADING_WORDS = ("heading", "見出し", "titre", "berschrift", "titolo", "encabezado")


def convert(path: str, *, extract_images: bool = False) -> Document:
    doc = Document(source_format="docx", source_name=path)
    with OoxmlPackage(path) as pkg:
        parser = _DocxParser(pkg, doc, extract_images=extract_images)
        parser.run()
    return doc


class _DocxParser:
    def __init__(self, pkg: OoxmlPackage, doc: Document, *, extract_images: bool) -> None:
        self.pkg = pkg
        self.doc = doc
        self.extract_images = extract_images
        self.rels = pkg.rels(DOCUMENT_PART)
        self.heading_levels = _heading_styles(pkg)
        self.numbering = _numbering(pkg)
        self._image_count = 0

    # -- 本体 -------------------------------------------------------------
    def run(self) -> None:
        self.doc.title = _core_title(self.pkg)
        body = self.pkg.xml(DOCUMENT_PART).find(q("w", "body"))
        if body is None:
            self.doc.warn("本文 (w:body) が見つかりませんでした")
            return
        self._blocks(body, self.doc.blocks)

    def _blocks(self, parent: ET.Element, out: list) -> None:
        """w:p / w:tbl の並びを IR ブロック列に変換する。連続する箇条書きは 1 つに束ねる。"""
        pending: list[ListItem] = []

        def flush() -> None:
            if pending:
                out.append(ListBlock(items=list(pending)))
                pending.clear()

        for child in parent:
            if child.tag == q("w", "p"):
                for block in self._paragraph(child):
                    if isinstance(block, ListItem):
                        pending.append(block)
                        continue
                    flush()
                    out.append(block)
            elif child.tag == q("w", "tbl"):
                flush()
                out.append(self._table(child))
        flush()

    # -- 段落 -------------------------------------------------------------
    def _paragraph(self, p: ET.Element) -> list:
        """1 つの w:p から 0 個以上のブロックを作る（画像は独立ブロックになる）。"""
        spans = self._spans(p)
        blocks: list = list(self._images(p))
        if not spans:
            return blocks

        style = _style_id(p)
        level = self.heading_levels.get(style or "")
        if level:
            blocks.append(Heading(level=level, spans=spans))
            return blocks

        num = _num_ref(p)
        if num is not None:
            num_id, ilvl = num
            ordered = self.numbering.get((num_id, ilvl), False)
            blocks.append(ListItem(spans=spans, level=ilvl, ordered=ordered))
            return blocks

        if style in ("Quote", "IntenseQuote"):
            blocks.append(Callout(label=None, blocks=[Paragraph(spans=spans)]))
            return blocks

        blocks.append(Paragraph(spans=spans))
        return blocks

    def _spans(self, parent: ET.Element) -> list[Span]:
        spans: list[Span] = []
        self._collect_spans(parent, spans, href=None)
        return spans

    def _collect_spans(self, parent: ET.Element, out: list[Span], href: str | None) -> None:
        for child in parent:
            if child.tag == q("w", "hyperlink"):
                rid = attr(child, "r", "id")
                target = self.rels.get(rid or "", href)
                self._collect_spans(child, out, href=target)
            elif child.tag == q("w", "r"):
                out.extend(self._run(child, href))
            elif child.tag in (q("w", "smartTag"), q("w", "sdt"), q("w", "sdtContent")):
                self._collect_spans(child, out, href)

    def _run(self, run: ET.Element, href: str | None) -> list[Span]:
        props = run.find(q("w", "rPr"))
        bold = _on(props, "b")
        italic = _on(props, "i")
        strike = _on(props, "strike") or _on(props, "dstrike")
        code = _is_monospace(props)

        spans: list[Span] = []
        for node in run:
            if node.tag == q("w", "t"):
                spans.append(
                    Span(
                        node.text or "",
                        bold=bold,
                        italic=italic,
                        code=code,
                        strike=strike,
                        href=href,
                    )
                )
            elif node.tag == q("w", "tab"):
                spans.append(Span(" ", href=href))
            elif node.tag == q("w", "br"):
                spans.append(Span("\n", href=href))
        return spans

    def _images(self, p: ET.Element) -> list[Image]:
        out: list[Image] = []
        for blip in p.iter(q("a", "blip")):
            rid = attr(blip, "r", "embed")
            target = self.rels.get(rid or "")
            if not target:
                continue
            name = target.rsplit("/", 1)[-1]
            if self.extract_images:
                self.doc.assets.append(_asset(self.pkg, target, name))
                out.append(Image(path=f"assets/{name}", alt=name))
            else:
                self._image_count += 1
                self.doc.warn(f"画像を出力しませんでした ({name})。--extract-images で書き出せます")
        return out

    # -- 表 ---------------------------------------------------------------
    def _table(self, tbl: ET.Element) -> Table:
        rows: list[list[list[Span]]] = []
        for tr in tbl.findall(q("w", "tr")):
            row: list[list[Span]] = []
            for tc in tr.findall(q("w", "tc")):
                cell: list[Span] = []
                for i, p in enumerate(tc.findall(q("w", "p"))):
                    if i:
                        cell.append(Span("\n"))
                    cell.extend(self._spans(p))
                row.append(cell)
            rows.append(row)
        if not rows:
            return Table()
        # 1 行目をヘッダとして扱う（Word は罫線でしかヘッダを区別しないことが多いため）
        return Table(header=rows[0], rows=rows[1:])


# --------------------------------------------------------------------------
# スタイル・番号定義の読み取り
# --------------------------------------------------------------------------


def _heading_styles(pkg: OoxmlPackage) -> dict[str, int]:
    """styleId -> 見出しレベル の対応表を作る。"""
    levels: dict[str, int] = {}
    root = pkg.xml_or_none("word/styles.xml")
    if root is None:
        return levels
    for style in root.findall(q("w", "style")):
        style_id = attr(style, "w", "styleId") or ""
        name_el = style.find(q("w", "name"))
        name = (attr(name_el, "w", "val") or "") if name_el is not None else ""
        level = _heading_level(style_id) or _heading_level(name)
        if level:
            levels[style_id] = level
        elif style_id.lower() == "title" or name.lower() == "title":
            levels[style_id] = 1
        elif style_id.lower() == "subtitle" or name.lower() == "subtitle":
            levels[style_id] = 2
    return levels


def _heading_level(label: str) -> int | None:
    low = label.lower().replace("-", " ")
    if not any(word in low for word in _HEADING_WORDS):
        return None
    m = _HEADING_NUM.search(low.strip())
    if not m:
        return None
    return min(max(int(m.group(1)), 1), 6)


def _numbering(pkg: OoxmlPackage) -> dict[tuple[str, int], bool]:
    """(numId, ilvl) -> 番号付きかどうか。"""
    root = pkg.xml_or_none("word/numbering.xml")
    if root is None:
        return {}
    abstract: dict[str, dict[int, bool]] = {}
    for anum in root.findall(q("w", "abstractNum")):
        aid = attr(anum, "w", "abstractNumId") or ""
        levels: dict[int, bool] = {}
        for lvl in anum.findall(q("w", "lvl")):
            ilvl = int(attr(lvl, "w", "ilvl") or 0)
            fmt_el = lvl.find(q("w", "numFmt"))
            fmt = attr(fmt_el, "w", "val") if fmt_el is not None else None
            levels[ilvl] = fmt not in (None, "bullet", "none")
        abstract[aid] = levels

    out: dict[tuple[str, int], bool] = {}
    for num in root.findall(q("w", "num")):
        num_id = attr(num, "w", "numId") or ""
        ref = num.find(q("w", "abstractNumId"))
        aid = attr(ref, "w", "val") if ref is not None else None
        for ilvl, ordered in abstract.get(aid or "", {}).items():
            out[(num_id, ilvl)] = ordered
    return out


def _core_title(pkg: OoxmlPackage) -> str | None:
    root = pkg.xml_or_none("docProps/core.xml")
    if root is None:
        return None
    for el in root:
        if el.tag.endswith("}title") and (el.text or "").strip():
            return el.text.strip()
    return None


# --------------------------------------------------------------------------
# 小物
# --------------------------------------------------------------------------


def _style_id(p: ET.Element) -> str | None:
    ppr = p.find(q("w", "pPr"))
    if ppr is None:
        return None
    style = ppr.find(q("w", "pStyle"))
    return attr(style, "w", "val") if style is not None else None


def _num_ref(p: ET.Element) -> tuple[str, int] | None:
    ppr = p.find(q("w", "pPr"))
    if ppr is None:
        return None
    numpr = ppr.find(q("w", "numPr"))
    if numpr is None:
        return None
    num_el = numpr.find(q("w", "numId"))
    ilvl_el = numpr.find(q("w", "ilvl"))
    num_id = attr(num_el, "w", "val") if num_el is not None else None
    if num_id is None:
        return None
    ilvl = int(attr(ilvl_el, "w", "val") or 0) if ilvl_el is not None else 0
    return num_id, ilvl


def _on(props: ET.Element | None, tag: str) -> bool:
    """w:b / w:i などのトグルプロパティ。val 未指定は ON、"0"/"false" は OFF。"""
    if props is None:
        return False
    el = props.find(q("w", tag))
    if el is None:
        return False
    val = attr(el, "w", "val")
    return val not in ("0", "false", "off")


def _is_monospace(props: ET.Element | None) -> bool:
    if props is None:
        return False
    fonts = props.find(q("w", "rFonts"))
    if fonts is None:
        return False
    name = (attr(fonts, "w", "ascii") or "").lower()
    return any(k in name for k in ("mono", "consolas", "courier", "menlo", "ゴシック等幅"))


def _asset(pkg: OoxmlPackage, target: str, name: str) -> Asset:
    return Asset(name=name, data=pkg.read(target))
