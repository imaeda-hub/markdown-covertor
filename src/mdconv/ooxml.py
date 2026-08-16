"""Office Open XML (docx / xlsx / pptx) 共通のユーティリティ。

docx・xlsx・pptx はいずれも「ZIP の中に XML が入っているだけ」なので、
標準ライブラリの zipfile と ElementTree で読める。検査・補正が見るのは
markitdown が出力に反映しない元ファイルの構造情報なので、python-docx 等の
上位ライブラリは要らない（プロジェクト全体は v0.2 で markitdown に依存する。
NFR-02 参照。このモジュール限定の話）。
"""

from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

from .errors import BrokenDocumentError

# よく使う名前空間。タグ名は `ns("w", "p")` のように組み立てる。
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xml": "http://www.w3.org/XML/1998/namespace",
}


def q(prefix: str, tag: str) -> str:
    """名前空間つきタグ名を返す。例: q("w", "p") -> "{...}p" """
    return f"{{{NS[prefix]}}}{tag}"


def attr(el: ET.Element, prefix: str, name: str, default: str | None = None) -> str | None:
    return el.get(q(prefix, name), default)


class OoxmlPackage:
    """OOXML パッケージ（ZIP）への読み取り専用アクセス。"""

    def __init__(self, path: str) -> None:
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise BrokenDocumentError(f"ファイルを開けません: {path} ({exc})") from exc
        self._cache: dict[str, ET.Element] = {}

    def __enter__(self) -> OoxmlPackage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.zip.close()

    def has(self, name: str) -> bool:
        return name in self.zip.namelist()

    def read(self, name: str) -> bytes:
        try:
            return self.zip.read(name)
        except KeyError as exc:
            raise BrokenDocumentError(f"必要なパートがありません: {name}") from exc

    def xml(self, name: str) -> ET.Element:
        """XML パートを読み、パース結果をキャッシュして返す。"""
        if name not in self._cache:
            try:
                self._cache[name] = ET.fromstring(self.read(name))
            except ET.ParseError as exc:
                raise BrokenDocumentError(f"XML を解釈できません: {name} ({exc})") from exc
        return self._cache[name]

    def xml_or_none(self, name: str) -> ET.Element | None:
        return self.xml(name) if self.has(name) else None

    def rels(self, part: str) -> dict[str, str]:
        """パートのリレーション（rId -> 解決済みパスまたは URL）を返す。"""
        directory, _, filename = part.rpartition("/")
        rels_path = f"{directory}/_rels/{filename}.rels" if directory else f"_rels/{filename}.rels"
        root = self.xml_or_none(rels_path)
        if root is None:
            return {}
        out: dict[str, str] = {}
        for rel in root.findall(q("rel", "Relationship")):
            rid = rel.get("Id")
            target = rel.get("Target")
            if not rid or not target:
                continue
            if rel.get("TargetMode") == "External" or "://" in target:
                out[rid] = target
            else:
                out[rid] = _resolve(directory, target)
        return out


def _resolve(base_dir: str, target: str) -> str:
    """相対パス（../media/image1.png など）をパッケージ内の絶対パスに直す。"""
    if target.startswith("/"):
        return target.lstrip("/")
    parts = [p for p in base_dir.split("/") if p]
    for segment in target.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
        else:
            parts.append(segment)
    return "/".join(parts)


def text_of(el: ET.Element | None) -> str:
    """要素配下のテキストをすべて連結する。"""
    return "".join(el.itertext()) if el is not None else ""


# 「List Bullet 2」のような Word 組み込みスタイル。末尾の数字がそのまま階層を表す
# （styleId は UI の言語に関わらずこの英語表記で固定）。
_LIST_STYLE = re.compile(r"^(ListBullet|ListNumber)(\d*)$")


def docx_list_levels(path: str) -> list[tuple[int, str]]:
    """Word 文書の箇条書き段落を出現順に辿り、(階層, 段落の文字列) の一覧を返す。

    mammoth は同じ numId の中で `w:ilvl` が増える段落は正しく入れ子にできるが、
    「List Bullet 2」のように**階層ごとに別の numId を持つ組み込みスタイル**は
    無関係な別リストとして扱われ、フラットに出力される（劣化）。
    ここでは組み込みスタイル名の末尾の数字と `w:ilvl` の両方から階層を復元する。
    表の中の段落は markitdown 側で箇条書きにならないため対象外にする。

    文字列も一緒に返すのは、`postprocess.nest_lists()` が Markdown 側の行と
    **中身が一致するときだけ**対応づけるため。行数が偶然一致しただけの
    誤った対応づけ（例: `numId="0"` でリストを解除した段落と、たまたま
    `- ` で始まる本文が数だけ噛み合う）を防ぐ。
    """
    with OoxmlPackage(path) as pkg:
        document_root = pkg.xml("word/document.xml")  # <w:document> 直下。<w:body> はこの子
        out: list[tuple[int, str]] = []
        for p in _body_paragraphs(document_root):
            level = _paragraph_list_level(p)
            if level is not None:
                out.append((level, text_of(p)))
        return out


def _body_paragraphs(root: ET.Element):
    """本文の段落を出現順に辿る。表の中身（GFM の表に化けるので箇条書きにならない）は除く。"""
    for child in root:
        if child.tag == q("w", "tbl"):
            continue
        if child.tag == q("w", "p"):
            yield child
        else:
            yield from _body_paragraphs(child)


def _paragraph_list_level(p: ET.Element) -> int | None:
    ppr = p.find(q("w", "pPr"))
    if ppr is None:
        return None
    pstyle = ppr.find(q("w", "pStyle"))
    style_level = _style_list_level(attr(pstyle, "w", "val")) if pstyle is not None else None
    numpr = ppr.find(q("w", "numPr"))
    if numpr is not None:
        num_id = numpr.find(q("w", "numId"))
        if num_id is not None and attr(num_id, "w", "val") == "0":
            return None  # numId=0 は「番号なし」への明示的な解除。箇条書きではない
        ilvl = numpr.find(q("w", "ilvl"))
        if ilvl is not None:
            return int(attr(ilvl, "w", "val", "0"))
        return style_level if style_level is not None else 0
    return style_level


def _style_list_level(style_id: str | None) -> int | None:
    if not style_id:
        return None
    m = _LIST_STYLE.match(style_id)
    if not m:
        return None
    digits = m.group(2)
    return int(digits) - 1 if digits else 0


# 表題・字幕・ヘッダ/フッタ・日付・スライド番号などの「本文ではない」プレースホルダー。
# markitdown はプレースホルダーの種類を区別せず shape.text をすべて出力するため、
# ここで除外し損なうと（例: フッタ文字列）本文の候補行と件数・中身がたまたま噛み合い、
# 無関係な文字列を箇条書きとして書き換えてしまう（レビューで実際に再現された）。
_NON_BODY_PLACEHOLDER_TYPES = {
    "title",
    "ctrTitle",
    "subTitle",
    "ftr",
    "hdr",
    "sldNum",
    "dt",
    "pic",
    "chart",
    "tbl",
    "clipArt",
    "dgm",
    "media",
    "sldImg",
}


def pptx_list_levels(path: str) -> list[tuple[int, str]]:
    """PowerPoint の本文プレースホルダーの段落を出現順に辿り、(階層, 段落の文字列) の一覧を返す。

    markitdown は PowerPoint の箇条書きを記号も階層も付けない平文で出す（劣化）。
    表題・字幕・ヘッダ/フッタ・日付・スライド番号等（`_NON_BODY_PLACEHOLDER_TYPES`）以外の
    プレースホルダーを本文とみなし、段落の `a:pPr/@lvl`（省略時は階層 0）から階層を復元する。
    表は markitdown 側で GFM の表になるため対象外（`p:sp` 図形のみを見る＝
    `p:graphicFrame` の表は拾わない）。

    プレースホルダーでないテキストボックスの箇条書きは検出しない（対応づけの手がかりが
    無い）。markitdown 側では平文になるが、この関数が空を返すため
    `api.py` は「本文プレースホルダーが無い」と「対応づけに失敗した」を区別できず、
    テキストボックスのみの箇条書きには警告も出ない（既知の制約。03-design.md 4.6）。

    文字列も一緒に返すのは、`postprocess.add_pptx_bullets()` が Markdown 側の行と
    **中身が一致するときだけ**対応づけるため（docx と同じ設計、03-design.md 4.5）。
    """
    with OoxmlPackage(path) as pkg:
        out: list[tuple[int, str]] = []
        for slide_path in _pptx_slide_order(pkg):
            root = pkg.xml(slide_path)
            for shape in root.iter(q("p", "sp")):
                if not _is_body_placeholder(shape):
                    continue
                body = shape.find(q("p", "txBody"))
                if body is None:
                    continue
                for p in body.findall(q("a", "p")):
                    text = text_of(p)
                    if text.strip():
                        out.append((_pptx_paragraph_level(p), text))
        return out


def _pptx_slide_order(pkg: OoxmlPackage) -> list[str]:
    """スライドの表示順（`p:sldIdLst`）をパートのパスで返す。

    ZIP 内のファイル名の並び（slide1, slide2, …）は表示順と一致するとは限らない
    （スライドの並べ替え）ため、`presentation.xml` のリレーションを辿って解決する。
    """
    presentation = pkg.xml_or_none("ppt/presentation.xml")
    if presentation is None:
        return []
    id_list = presentation.find(q("p", "sldIdLst"))
    if id_list is None:
        return []
    rels = pkg.rels("ppt/presentation.xml")
    order: list[str] = []
    for sld_id in id_list.findall(q("p", "sldId")):
        rid = attr(sld_id, "r", "id")
        target = rels.get(rid) if rid else None
        if target:
            order.append(target)
    return order


def _is_body_placeholder(shape: ET.Element) -> bool:
    """本文プレースホルダーかどうか。

    表題・字幕・ヘッダ/フッタ・日付・スライド番号等（`_NON_BODY_PLACEHOLDER_TYPES`）と、
    テキストボックス等（プレースホルダーでない図形）は除く。`type` 省略はレイアウト側の
    種類を引き継ぐが、`idx` を持つ標準的な内容プレースホルダーは省略されることが多いため
    「本文」として扱う（表題プレースホルダーは実務上ほぼ必ず `type="title"` を明示するため、
    この既定値でも誤って表題を本文扱いすることは少ない）。
    """
    ph = shape.find(f"{q('p', 'nvSpPr')}/{q('p', 'nvPr')}/{q('p', 'ph')}")
    if ph is None:
        return False
    return (ph.get("type") or "body") not in _NON_BODY_PLACEHOLDER_TYPES


def _pptx_paragraph_level(p: ET.Element) -> int:
    ppr = p.find(q("a", "pPr"))
    if ppr is None:
        return 0
    return int(ppr.get("lvl") or "0")
