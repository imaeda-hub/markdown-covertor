"""PDF → IR。

PDF は「見た目の座標」しか持たないため、見出しや表の復元は本質的に推測になる。
v0.1 では pypdf によるテキスト抽出 + 段落復元までを担当し、
高精度なレイアウト解析（Docling / Marker 等）は将来のプラグインに委ねる。
現在の限界は docs/specs/05-conversion-rules.md「PDF」節に明記している。
"""

from __future__ import annotations

import re

from ..errors import BrokenDocumentError, MissingDependencyError
from ..model import Divider, Document, Heading, ListBlock, ListItem, Paragraph, Span

# 和文の中黒などは後ろに空白を置かないことが多いので、記号の種類で条件を分ける
_BULLET = re.compile(r"^\s*(?:[•・●○◦▪▫]\s*|[*\-–—]\s+)(?P<text>\S.*)$")
_NUMBERED = re.compile(r"^\s*(?P<n>\d{1,2})[.)]\s+(?P<text>.+)$")
_HEADING = re.compile(r"^\s*(?:第?\s*)?(\d+(?:\.\d+)*)[.、]?\s+(?P<text>\S.*)$")
# 行末のハイフンは次行と連結する（英文の折り返し）
_HYPHEN_END = re.compile(r"(\w)-$")


def convert(path: str, *, page_dividers: bool = True, page_headings: bool = False) -> Document:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise MissingDependencyError("pypdf", "pdf") from exc

    doc = Document(source_format="pdf", source_name=path)
    try:
        reader = PdfReader(path)
    except Exception as exc:  # pypdf は多様な例外を投げる
        raise BrokenDocumentError(f"PDF を開けません: {path} ({exc})") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise BrokenDocumentError("暗号化された PDF です（パスワードが必要）") from exc

    meta_title = None
    try:
        meta_title = (reader.metadata or {}).get("/Title")
    except Exception:  # pragma: no cover - 壊れたメタデータ
        meta_title = None
    doc.title = str(meta_title).strip() if meta_title else None

    empty_pages = 0
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover
            doc.warn(f"{index} ページを抽出できませんでした ({exc})")
            continue
        if not text.strip():
            empty_pages += 1
            continue
        if page_dividers and doc.blocks:
            doc.add(Divider())
        if page_headings:
            doc.add(Heading(level=2, spans=[Span(f"ページ {index}")]))
        doc.blocks.extend(blocks_from_text(text))

    if empty_pages:
        doc.warn(
            f"テキストを含まないページが {empty_pages} ページありました。"
            "スキャン画像の可能性があります（OCR は未対応）"
        )
    return doc


def blocks_from_text(text: str) -> list:
    """抽出した平文テキストを段落・箇条書き・見出しに復元する。"""
    blocks: list = []
    pending_list: list[ListItem] = []
    buffer: list[str] = []

    def flush_paragraph() -> None:
        if buffer:
            blocks.append(Paragraph(spans=[Span(_join(buffer))]))
            buffer.clear()

    def flush_list() -> None:
        if pending_list:
            blocks.append(ListBlock(items=list(pending_list)))
            pending_list.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue

        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        heading = _HEADING.match(line)

        if bullet:
            flush_paragraph()
            pending_list.append(ListItem(spans=[Span(bullet.group("text").strip())]))
            continue
        if numbered and not _looks_like_heading(numbered.group("text")):
            flush_paragraph()
            pending_list.append(
                ListItem(spans=[Span(numbered.group("text").strip())], ordered=True)
            )
            continue
        if heading and _looks_like_heading(heading.group("text")):
            flush_paragraph()
            flush_list()
            level = min(heading.group(1).count(".") + 2, 6)
            blocks.append(Heading(level=level, spans=[Span(heading.group("text").strip())]))
            continue

        flush_list()
        buffer.append(line.strip())

    flush_paragraph()
    flush_list()
    return blocks


def _looks_like_heading(text: str) -> bool:
    """短く句点で終わらない行は見出しとみなす（PDF には見出し情報が無いための推定）。"""
    stripped = text.strip()
    return len(stripped) <= 40 and not stripped.endswith(("。", ".", "、", ","))


def _join(lines: list[str]) -> str:
    """折り返された行を 1 つの段落に戻す。日本語は空白なし、英語は空白ありで連結。"""
    out = ""
    for line in lines:
        if not out:
            out = line
            continue
        hyphen = _HYPHEN_END.search(out)
        if hyphen:
            out = out[:-1] + line
        elif _is_wide(out[-1]) or _is_wide(line[0]):
            out += line
        else:
            out += " " + line
    return out


def _is_wide(ch: str) -> bool:
    """全角（CJK）文字かどうか。行連結時に空白を入れるかの判定に使う。"""
    return any(
        start <= ord(ch) <= end
        for start, end in (
            (0x3000, 0x303F),  # 記号
            (0x3040, 0x30FF),  # かな
            (0x4E00, 0x9FFF),  # 漢字
            (0xFF00, 0xFFEF),  # 全角英数
        )
    )
