"""変換結果を運ぶ型。

v0.2 から変換そのものは markitdown が行う。このモジュールが定義するのは
**markitdown が返さないもの**――落とした情報の報告と、抜き出した画像。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["info", "warning"]


@dataclass(slots=True)
class Notice:
    """変換で失われた情報の記録。

    markitdown は「何が落ちたか」を教えてくれない。だが利用者にとっては
    静かに消えるのが最悪なので（01-product.md の優先順位 1）、
    元ファイルを別途調べて、この形で呼び出し側へ返す。
    """

    message: str
    severity: Severity = "warning"
    location: str | None = None


@dataclass(slots=True)
class Asset:
    """本文から参照される埋め込みファイル（画像など）。

    path は Markdown ファイルから見た相対パス（例 `assets/資料/image1.png`）。
    本文中の参照と同じ値にすることで、書き出し先と参照が必ず一致する。
    """

    path: str
    data: bytes


@dataclass(slots=True)
class Inspection:
    """元ファイルを調べて分かったこと。markitdown の出力を補正するのに使う。"""

    notices: list[Notice] = field(default_factory=list)
    hidden_sheets: list[str] = field(default_factory=list)
    title: str | None = None
    format: str = "unknown"

    def warn(self, message: str, *, location: str | None = None) -> None:
        self.notices.append(Notice(message, "warning", location))

    def info(self, message: str) -> None:
        self.notices.append(Notice(message, "info"))
