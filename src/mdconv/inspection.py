"""元ファイルを調べて「markitdown が落としたもの」を突き止める。

markitdown は本文を Markdown にするだけで、**何が落ちたかは教えてくれない**。
グラフが消えても非表示シートが混ざっても、出力を見ただけでは分からない。
そこで元ファイル（OOXML = ZIP + XML）を直接開いて、
出力に現れないはずの要素を数え、警告として返す。

ここは ZIP を開いて名前を数える程度の処理しかしない。
本文の解釈は一切しない（それは markitdown の仕事）。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .errors import MdconvError
from .ooxml import OoxmlPackage, attr, q
from .types import Inspection

# graphicData の uri から図表の種類を判別する
_GRAPHIC_KINDS = (("chart", "グラフ"), ("diagram", "SmartArt"), ("smartArt", "SmartArt"))


def inspect(path: Path, fmt: str, markdown: str) -> Inspection:
    """形式に応じて元ファイルを調べる。失敗しても変換自体は止めない。"""
    found = Inspection()
    try:
        if fmt == "docx":
            _docx(path, found)
        elif fmt == "xlsx":
            _xlsx(path, found)
        elif fmt == "pptx":
            _pptx(path, found)
        elif fmt == "pdf":
            _pdf(markdown, found)
    except (MdconvError, zipfile.BadZipFile, OSError):
        # 調べられなくても本文の変換結果は返す。警告が出ないだけ
        found.info("元ファイルを調べられなかったため、落ちた情報の報告はありません")
    return found


# --------------------------------------------------------------------------
# 形式ごとの検査
# --------------------------------------------------------------------------


def _docx(path: Path, found: Inspection) -> None:
    with OoxmlPackage(str(path)) as pkg:
        found.title = _core_title(pkg)
        body = pkg.xml("word/document.xml")
        counts: dict[str, int] = {}
        for element in _walk_without_fallback(body):
            if element.tag == q("a", "graphicData"):
                kind = _graphic_kind(element.get("uri") or "")
                if kind:
                    counts[kind] = counts.get(kind, 0) + 1
            elif element.tag == q("w", "txbxContent"):
                counts["テキストボックス"] = counts.get("テキストボックス", 0) + 1
        _report(found, counts)


def _xlsx(path: Path, found: Inspection) -> None:
    with OoxmlPackage(str(path)) as pkg:
        book = pkg.xml("xl/workbook.xml")
        sheets = book.find(q("x", "sheets"))
        for sheet in sheets.findall(q("x", "sheet")) if sheets is not None else []:
            if sheet.get("state") in ("hidden", "veryHidden"):
                found.hidden_sheets.append(sheet.get("name") or "")

        names = pkg.zip.namelist()
        counts = {
            "グラフ": sum(1 for n in names if n.startswith("xl/charts/chart")),
            "画像": sum(1 for n in names if n.startswith("xl/media/")),
        }
        _report(found, counts)


def _pptx(path: Path, found: Inspection) -> None:
    with OoxmlPackage(str(path)) as pkg:
        # markitdown は PowerPoint の画像を図形名で参照するだけで、実体を出さない。
        # 対応づけられないので、せめて枚数を伝える（T-24）
        counts: dict[str, int] = {
            "画像": sum(1 for n in pkg.zip.namelist() if n.startswith("ppt/media/"))
        }
        for name in pkg.zip.namelist():
            if not name.startswith("ppt/slides/slide"):
                continue
            # Word と同じく、mc:Fallback の中は二重に数えないよう飛ばす
            for data in _walk_without_fallback(pkg.xml(name)):
                if data.tag != q("a", "graphicData"):
                    continue
                uri = data.get("uri") or ""
                if "table" in uri:
                    continue  # 表は Markdown になるので落ちていない
                kind = _graphic_kind(uri)
                if kind:
                    counts[kind] = counts.get(kind, 0) + 1
        _report(found, counts)


def _pdf(markdown: str, found: Inspection) -> None:
    """PDF は中を覗かず、出力の空きだけで判断する（スキャン資料の検出）。"""
    if not markdown.strip():
        found.warn(
            "文字を 1 つも取り出せませんでした。"
            "紙をスキャンした PDF の可能性があります（OCR は未対応）"
        )


# --------------------------------------------------------------------------
# 小物
# --------------------------------------------------------------------------


def _report(found: Inspection, counts: dict[str, int]) -> None:
    for kind, count in sorted(counts.items()):
        if count:
            found.warn(f"{kind}を {count} 個出力していません（Markdown に表現がありません）")


def _graphic_kind(uri: str) -> str | None:
    for token, label in _GRAPHIC_KINDS:
        if token in uri:
            return label
    return None


MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _walk_without_fallback(root):
    """要素を辿る。ただし mc:Fallback の中には入らない。

    Word は 1 つの図表を mc:Choice（新しい表現）と mc:Fallback（古い表現）の
    両方で書くことがある。素直に走査すると同じ図表を 2 回数えてしまう。
    """
    for child in root:
        if child.tag == f"{{{MC}}}Fallback":
            continue
        yield child
        yield from _walk_without_fallback(child)


def _core_title(pkg: OoxmlPackage) -> str | None:
    root = pkg.xml_or_none("docProps/core.xml")
    if root is None:
        return None
    for el in root:
        if el.tag.endswith("}title") and (el.text or "").strip():
            return el.text.strip()
    return None


__all__ = ["inspect", "attr"]
