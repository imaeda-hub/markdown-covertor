"""ドキュメント中間表現 (IR)。

各フォーマットのコンバータは「入力ファイル → IR」だけを担当し、
Markdown の文字列組み立ては renderer が一手に引き受ける。
こうすることで、
  * 出力書式の変更が 1 箇所で済む
  * コンバータのテストが文字列比較ではなく構造比較でできる
  * 将来 GUI / HTML / JSON 出力を足すときも IR を使い回せる
という利点がある。詳細は docs/specs/03-design.md を参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# --------------------------------------------------------------------------
# インライン要素
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Span:
    """文字列と、それに掛かる装飾。"""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strike: bool = False
    href: str | None = None

    def style_key(self) -> tuple:
        """装飾が同一かどうかの比較キー（隣接 Span のマージに使う）。"""
        return (self.bold, self.italic, self.code, self.strike, self.href)


# --------------------------------------------------------------------------
# ブロック要素
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Heading:
    level: int
    spans: list[Span] = field(default_factory=list)


@dataclass(slots=True)
class Paragraph:
    spans: list[Span] = field(default_factory=list)


@dataclass(slots=True)
class ListItem:
    spans: list[Span] = field(default_factory=list)
    level: int = 0
    ordered: bool = False
    checked: bool | None = None


@dataclass(slots=True)
class ListBlock:
    items: list[ListItem] = field(default_factory=list)


@dataclass(slots=True)
class Table:
    """表。header が空の場合はヘッダ行なしとして描画される。"""

    header: list[list[Span]] = field(default_factory=list)
    rows: list[list[list[Span]]] = field(default_factory=list)
    caption: str | None = None


@dataclass(slots=True)
class CodeBlock:
    text: str
    language: str | None = None


@dataclass(slots=True)
class Image:
    path: str
    alt: str = ""
    title: str | None = None


@dataclass(slots=True)
class Divider:
    pass


@dataclass(slots=True)
class Callout:
    """引用ブロック。スピーカーノートや注釈の表現に使う。"""

    label: str | None
    blocks: list[Block] = field(default_factory=list)


Block = Heading | Paragraph | ListBlock | Table | CodeBlock | Image | Divider | Callout


# --------------------------------------------------------------------------
# ドキュメント
# --------------------------------------------------------------------------

Severity = Literal["info", "warning"]


@dataclass(slots=True)
class Notice:
    """変換中に発生した「捨てた情報」の記録。利用者への説明責任のために残す。"""

    message: str
    severity: Severity = "warning"
    location: str | None = None


@dataclass(slots=True)
class Asset:
    """本文から参照される埋め込みファイル（画像など）。

    path は Markdown ファイルから見た相対パス（例 `assets/資料/image1.png`）。
    本文の Image.path と同じ値にすることで、参照とファイルの置き場所が必ず一致する。
    """

    path: str
    data: bytes


@dataclass(slots=True)
class Document:
    blocks: list[Block] = field(default_factory=list)
    title: str | None = None
    source_format: str = "unknown"
    source_name: str | None = None
    assets: list[Asset] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)

    def add(self, block: Block) -> None:
        self.blocks.append(block)

    def warn(self, message: str, *, location: str | None = None) -> None:
        self.notices.append(Notice(message, "warning", location))
