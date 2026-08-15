"""公開 API。CLI も GUI も将来のサーバもここだけを呼ぶ。

from mdconv import convert_file
result = convert_file("資料.docx")
print(result.markdown)
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path

from .model import Document, Notice
from .registry import detect
from .renderer import RenderOptions, render


@dataclass(slots=True)
class ConvertOptions:
    """変換の挙動。フォーマット固有の項目も、関係するコンバータにだけ渡される。"""

    # 出力
    heading_offset: int = 0
    front_matter: bool = False
    include_notices: bool = False

    # 共通
    extract_images: bool = True
    """画像を assets/ に書き出して参照を張る。False なら出力せず警告のみ。"""

    # Excel
    include_hidden: bool = False
    max_rows: int | None = None

    # PowerPoint
    include_notes: bool = True
    slide_dividers: bool = True

    # PDF
    page_dividers: bool = True
    page_headings: bool = False

    def render_options(self) -> RenderOptions:
        return RenderOptions(
            heading_offset=self.heading_offset,
            front_matter=self.front_matter,
            include_notices=self.include_notices,
        )


@dataclass(slots=True)
class ConvertResult:
    markdown: str
    document: Document
    source: Path
    notices: list[Notice] = field(default_factory=list)

    @property
    def format(self) -> str:
        return self.document.source_format

    def write(self, destination: str | Path) -> Path:
        """Markdown を書き出す。抽出済み画像は本文の参照と同じ相対パスに置く。"""
        out = Path(destination)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.markdown, encoding="utf-8")
        for asset in self.document.assets:
            target = out.parent / asset.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(asset.data)
        return out


def convert_file(
    path: str | Path,
    *,
    options: ConvertOptions | None = None,
    format: str | None = None,
) -> ConvertResult:
    """1 ファイルを Markdown に変換する。"""
    opts = options or ConvertOptions()
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"ファイルがありません: {source}")

    fmt = detect(source, explicit=format)
    converter = fmt.loader()
    document = converter(str(source), **_kwargs_for(converter, opts))
    document.source_name = source.name
    markdown = render(document, opts.render_options())
    return ConvertResult(
        markdown=markdown, document=document, source=source, notices=document.notices
    )


def _kwargs_for(converter, opts: ConvertOptions) -> dict:
    """コンバータが受け取れるオプションだけを抜き出して渡す。"""
    accepted = set(inspect.signature(converter).parameters) - {"path"}
    return {name: getattr(opts, name) for name in accepted if hasattr(opts, name)}
