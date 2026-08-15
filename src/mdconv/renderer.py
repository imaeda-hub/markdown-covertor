"""IR を Markdown 文字列に変換する。

出力方言は GitHub Flavored Markdown (GFM) を既定とする。
変換ルールの一覧は docs/specs/05-conversion-rules.md にある。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import (
    Block,
    Callout,
    CodeBlock,
    Divider,
    Document,
    Heading,
    Image,
    ListBlock,
    Paragraph,
    Span,
    Table,
)

# Markdown で意味を持つ文字。行頭記号（# や -）は別扱い、パイプは表セルでのみ扱う。
_INLINE_ESCAPE = re.compile(r"([\\`*_\[\]<>])")
_LINE_LEAD = re.compile(r"^(\s*)([#>+\-]|\d+[.)])(\s)")


@dataclass(slots=True)
class RenderOptions:
    heading_offset: int = 0
    """見出しレベルの底上げ量。1 にすると H1 が H2 になる。"""

    front_matter: bool = False
    """YAML フロントマターにタイトルなどのメタ情報を出力する。"""

    include_notices: bool = False
    """変換時の警告を末尾にコメントとして残す。"""

    bullet: str = "-"
    max_heading_level: int = 6


def render(doc: Document, options: RenderOptions | None = None) -> str:
    return Renderer(options or RenderOptions()).render(doc)


class Renderer:
    def __init__(self, options: RenderOptions) -> None:
        self.o = options

    # -- 公開 API ---------------------------------------------------------
    def render(self, doc: Document) -> str:
        parts: list[str] = []
        if self.o.front_matter:
            parts.append(self._front_matter(doc))
        body = "\n\n".join(p for p in (self._block(b) for b in doc.blocks) if p)
        if body:
            parts.append(body)
        if self.o.include_notices and doc.notices:
            lines = ["<!-- 変換時の注意"]
            for n in doc.notices:
                where = f" ({n.location})" if n.location else ""
                lines.append(f"  - [{n.severity}]{where} {n.message}")
            lines.append("-->")
            parts.append("\n".join(lines))
        return "\n\n".join(parts).strip() + "\n"

    # -- ブロック ---------------------------------------------------------
    def _block(self, block: Block) -> str:
        match block:
            case Heading():
                level = min(max(block.level + self.o.heading_offset, 1), self.o.max_heading_level)
                text = self._spans(block.spans).strip()
                return f"{'#' * level} {text}" if text else ""
            case Paragraph():
                return self._escape_leading(self._spans(block.spans).strip())
            case ListBlock():
                return self._list(block)
            case Table():
                return self._table(block)
            case CodeBlock():
                fence = self._fence(block.text)
                lang = block.language or ""
                return f"{fence}{lang}\n{block.text.rstrip()}\n{fence}"
            case Image():
                title = f' "{block.title}"' if block.title else ""
                return f"![{_escape_text(block.alt)}]({_encode_url(block.path)}{title})"
            case Divider():
                return "---"
            case Callout():
                inner = "\n\n".join(p for p in (self._block(b) for b in block.blocks) if p)
                if block.label:
                    inner = f"**{block.label}**\n\n{inner}" if inner else f"**{block.label}**"
                return "\n".join(f"> {line}".rstrip() for line in inner.split("\n"))
            case _:  # pragma: no cover - 将来のブロック追加に対する保険
                return ""

    def _list(self, block: ListBlock) -> str:
        lines: list[str] = []
        counters: dict[int, int] = {}
        for item in block.items:
            level = max(item.level, 0)
            indent = "  " * level
            if item.ordered:
                counters[level] = counters.get(level, 0) + 1
                marker = f"{counters[level]}."
            else:
                counters.pop(level, None)
                marker = self.o.bullet
            # 深い階層のカウンタは親が変わった時点でリセットする
            for deeper in [k for k in counters if k > level]:
                del counters[deeper]
            box = ""
            if item.checked is not None:
                box = "[x] " if item.checked else "[ ] "
            text = self._spans(item.spans).strip()
            lines.append(f"{indent}{marker} {box}{text}".rstrip())
        return "\n".join(lines)

    def _table(self, table: Table) -> str:
        header = [self._cell(c) for c in table.header] if table.header else []
        rows = [[self._cell(c) for c in row] for row in table.rows]
        width = max([len(header)] + [len(r) for r in rows] or [0]) if (header or rows) else 0
        if width == 0:
            return ""
        if not header:
            # GFM の表はヘッダ必須。元データにヘッダが無い場合は空ヘッダを立てる。
            header = [""] * width
        header = _pad(header, width)
        rows = [_pad(r, width) for r in rows]

        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join(["---"] * width) + " |")
        lines.extend("| " + " | ".join(r) + " |" for r in rows)
        body = "\n".join(lines)
        if table.caption:
            body = f"**{_escape_text(table.caption)}**\n\n{body}"
        return body

    def _cell(self, spans: list[Span]) -> str:
        # セル内の改行は <br>、パイプはエスケープ
        text = self._spans(spans).replace("\n", "<br>")
        return text.replace("|", "\\|").strip()

    # -- インライン -------------------------------------------------------
    def _spans(self, spans: list[Span]) -> str:
        return "".join(self._span(s) for s in merge_spans(spans))

    def _span(self, span: Span) -> str:
        text = span.text
        if not text:
            return ""
        if span.code:
            tick = "`" * (_max_run(text, "`") + 1)
            pad = " " if text.startswith("`") or text.endswith("`") else ""
            out = f"{tick}{pad}{text}{pad}{tick}"
        else:
            out = _escape_text(text)
            # 空白のみの Span に装飾を掛けると Markdown が壊れるので素通しする
            if out.strip():
                if span.bold:
                    out = _wrap(out, "**")
                if span.italic:
                    out = _wrap(out, "*")
                if span.strike:
                    out = _wrap(out, "~~")
        if span.href:
            out = f"[{out}]({_encode_url(span.href)})"
        return out

    # -- 補助 -------------------------------------------------------------
    def _escape_leading(self, text: str) -> str:
        """段落の先頭が見出し記号などに化けないようにエスケープする。"""
        return _LINE_LEAD.sub(lambda m: f"{m.group(1)}\\{m.group(2)}{m.group(3)}", text)

    @staticmethod
    def _fence(text: str) -> str:
        return "`" * max(3, _max_run(text, "`") + 1)

    def _front_matter(self, doc: Document) -> str:
        lines = ["---"]
        if doc.title:
            lines.append(f'title: "{doc.title.replace(chr(34), chr(39))}"')
        if doc.source_name:
            lines.append(f'source: "{doc.source_name}"')
        lines.append(f"source_format: {doc.source_format}")
        lines.append("---")
        return "\n".join(lines)


def merge_spans(spans: list[Span]) -> list[Span]:
    """装飾が同じ隣接 Span を 1 つにまとめ、`**a****b**` のような出力を防ぐ。"""
    merged: list[Span] = []
    for span in spans:
        if not span.text:
            continue
        if merged and merged[-1].style_key() == span.style_key():
            merged[-1] = Span(merged[-1].text + span.text, *span.style_key())
        else:
            merged.append(Span(span.text, *span.style_key()))
    return merged


def _wrap(text: str, marker: str) -> str:
    """前後の空白を装飾の外に出す（`** bold **` は装飾として解釈されないため）。"""
    stripped = text.strip()
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    return f"{lead}{marker}{stripped}{marker}{trail}"


def _escape_text(text: str) -> str:
    return _INLINE_ESCAPE.sub(r"\\\1", text)


def _encode_url(url: str) -> str:
    if any(ch in url for ch in " ()"):
        return "<" + url.replace(">", "%3E") + ">"
    return url


def _max_run(text: str, ch: str) -> int:
    best = run = 0
    for c in text:
        run = run + 1 if c == ch else 0
        best = max(best, run)
    return best


def _pad(cells: list[str], width: int) -> list[str]:
    return cells + [""] * (width - len(cells))
