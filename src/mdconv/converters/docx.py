"""Word (.docx) → IR。"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
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


def convert(path: str, *, extract_images: bool = True) -> Document:
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
        self.style_roles = _style_roles(pkg)
        self.style_numbering = _style_numbering(pkg)
        self.numbering = _numbering(pkg)
        self._title_used = False
        # 一括変換で別々の文書の image1.png が衝突しないよう、文書名でフォルダを分ける
        self._asset_dir = f"assets/{Path(doc.source_name or 'document').stem}"

    # -- 本体 -------------------------------------------------------------
    def run(self) -> None:
        self.doc.title = _core_title(self.pkg)
        body = self.pkg.xml(DOCUMENT_PART).find(q("w", "body"))
        if body is None:
            self.doc.warn("本文 (w:body) が見つかりませんでした")
            return
        self._blocks(body, self.doc.blocks)
        self._report_graphics(body)

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
        role = self.style_roles.get(style or "")
        if role == "title" and not self._title_used:
            # 表題は文書のタイトルであって本文の見出しではない。`#` が 2 つ並ぶのを避け、
            # 代わりにメタ情報として保持する（--front-matter で出力される）。
            # 本文の表題は docProps のタイトルより優先する。利用者が目にしているのは本文であり、
            # 上書きしないと「--front-matter で残せます」という案内が嘘になるため。
            self._title_used = True
            self.doc.title = "".join(s.text for s in spans).strip()
            self.doc.warn(
                f"表題「{self.doc.title}」は本文に出力していません（--front-matter で残せます）"
            )
            return blocks
        if role in ("title", "subtitle"):
            # 2 つ目以降の表題と副題は、捨てずに段落として残す
            blocks.append(Paragraph(spans=spans))
            return blocks
        if isinstance(role, int):
            blocks.append(Heading(level=role, spans=spans))
            return blocks

        listing = self._list_ref(p, style)
        if listing is not None:
            num_id, ilvl, level = listing
            ordered = self.numbering.get((num_id, ilvl), False)
            blocks.append(ListItem(spans=spans, level=level, ordered=ordered))
            return blocks

        if style in ("Quote", "IntenseQuote"):
            blocks.append(Callout(label=None, blocks=[Paragraph(spans=spans)]))
            return blocks

        blocks.append(Paragraph(spans=spans))
        return blocks

    def _list_ref(self, p: ET.Element, style: str | None) -> tuple[str, int, int] | None:
        """段落が箇条書きなら (numId, ilvl, 表示上の階層) を返す。

        箇条書きの指定は 2 か所に分かれて置かれることがある。
          * 段落の w:numPr … 番号定義と階層。ただし**階層だけ**書かれることも多い
          * スタイルの w:numPr … Word の「箇条書き」スタイルはこちらに番号定義を持つ
        どちらか片方だけを見ると、リストの取りこぼしや入れ子の潰れが起きる。
        """
        para = _num_ref(p)
        from_style = self.style_numbering.get(style or "") if style else None
        if para is None and from_style is None:
            return None

        para_num_id, para_ilvl = para if para else (None, None)
        num_id = para_num_id or (from_style[0] if from_style else None)
        if num_id is None or num_id == "0":
            # numId="0" は「このスタイルの番号を外す」という指定
            return None

        if para_ilvl is not None:
            return num_id, para_ilvl, para_ilvl
        if from_style is not None:
            return num_id, from_style[1], from_style[2]
        return num_id, 0, 0

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
                path = f"{self._asset_dir}/{name}"
                self.doc.assets.append(Asset(path=path, data=self.pkg.read(target)))
                out.append(Image(path=path, alt=name))
            else:
                self.doc.warn(f"画像を出力しませんでした ({name})")
        return out

    def _report_graphics(self, body: ET.Element) -> None:
        """グラフ・SmartArt・テキストボックスなど、出力できない要素の存在を伝える。

        画像と違って書き出す先がないので、せめて「あった」ことだけは残す。
        黙って消すのが最悪（01-product.md の優先順位 1）。

        本文だけでなく表の中も対象にするため、段落単位ではなく本文全体を一度に走査する。
        """
        found: Counter[str] = Counter()
        for element in _walk_without_fallback(body):
            if element.tag == q("a", "graphicData"):
                kind = _graphic_kind(element.get("uri") or "")
                if kind:
                    found[kind] += 1
            elif element.tag == q("w", "txbxContent"):
                found["テキストボックス"] += 1
        for kind, count in sorted(found.items()):
            self.doc.warn(f"{kind}を {count} 個出力していません（Markdown に表現がありません）")

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


def _style_roles(pkg: OoxmlPackage) -> dict[str, int | str]:
    """styleId -> 役割 の対応表。値は見出しレベル(int) か "title" / "subtitle"。"""
    roles: dict[str, int | str] = {}
    root = pkg.xml_or_none("word/styles.xml")
    if root is None:
        return roles
    for style in root.findall(q("w", "style")):
        style_id = attr(style, "w", "styleId") or ""
        name_el = style.find(q("w", "name"))
        name = (attr(name_el, "w", "val") or "") if name_el is not None else ""
        level = _heading_level(style_id) or _heading_level(name)
        if level:
            roles[style_id] = level
        elif _is_named(style_id, name, "title", "表題"):
            roles[style_id] = "title"
        elif _is_named(style_id, name, "subtitle", "副題"):
            roles[style_id] = "subtitle"
    return roles


def _style_numbering(pkg: OoxmlPackage) -> dict[str, tuple[str, int, int]]:
    """styleId -> (numId, ilvl, 表示上の階層) の対応表。

    「箇条書き」「段落番号」スタイルは、段落ではなくスタイル定義に w:numPr を持つ。
    階層はスタイル名の末尾の数字で表される（List Bullet 2 = 2 階層目）ので、
    ilvl ではなくそちらから読む。
    """
    out: dict[str, tuple[str, int, int]] = {}
    root = pkg.xml_or_none("word/styles.xml")
    if root is None:
        return out
    for style in root.findall(q("w", "style")):
        style_id = attr(style, "w", "styleId")
        if not style_id:
            continue  # 空キーにすると pStyle を持たない段落すべてに一致してしまう
        ppr = style.find(q("w", "pPr"))
        numpr = ppr.find(q("w", "numPr")) if ppr is not None else None
        if numpr is None:
            continue
        num_el = numpr.find(q("w", "numId"))
        num_id = attr(num_el, "w", "val") if num_el is not None else None
        if num_id is None or num_id == "0":
            continue
        ilvl_el = numpr.find(q("w", "ilvl"))
        ilvl = int(attr(ilvl_el, "w", "val") or 0) if ilvl_el is not None else 0
        name_el = style.find(q("w", "name"))
        name = (attr(name_el, "w", "val") or "") if name_el is not None else ""
        out[style_id] = (num_id, ilvl, max(ilvl, _style_depth(name)))
    return out


MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _walk_without_fallback(root: ET.Element):
    """要素を辿る。ただし mc:Fallback の中には入らない。

    Word は 1 つの図表を mc:Choice（新しい表現）と mc:Fallback（古い表現）の
    両方で書くことがある。素直に走査すると同じ図表を 2 回数えてしまう。
    """
    for child in root:
        if child.tag == f"{{{MC}}}Fallback":
            continue
        yield child
        yield from _walk_without_fallback(child)


def _graphic_kind(uri: str) -> str | None:
    """graphicData の uri から図表の種類を判別する。画像と表は別扱いなので None。"""
    if "chart" in uri:
        return "グラフ"
    if "diagram" in uri or "smartArt" in uri:
        return "SmartArt"
    return None


def _style_depth(name: str) -> int:
    """「List Bullet 2」のようなスタイル名から表示上の階層を読む（2 なら 1 段目の入れ子）。

    styleId ではなく w:name を見るのは、日本語版 Word が styleId に `a5` のような
    連番を振るため。styleId の末尾の数字を階層と誤読すると、深く字下げされてしまう。
    """
    m = re.search(r"(\d+)\s*$", name)
    return max(int(m.group(1)) - 1, 0) if m else 0


def _is_named(style_id: str, name: str, *candidates: str) -> bool:
    return any(label.lower() in candidates for label in (style_id, name))


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


def _num_ref(p: ET.Element) -> tuple[str | None, int | None] | None:
    """段落の w:numPr を (numId, ilvl) で返す。

    numId だけ・ilvl だけという書かれ方が実ファイルには両方あるので、
    「無い」を None として区別し、足りない方はスタイル側から補えるようにする。
    """
    ppr = p.find(q("w", "pPr"))
    if ppr is None:
        return None
    numpr = ppr.find(q("w", "numPr"))
    if numpr is None:
        return None
    num_el = numpr.find(q("w", "numId"))
    ilvl_el = numpr.find(q("w", "ilvl"))
    num_id = attr(num_el, "w", "val") if num_el is not None else None
    ilvl = int(attr(ilvl_el, "w", "val") or 0) if ilvl_el is not None else None
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
