"""mdconv が投げる例外。CLI はこれらを終了コードに対応付ける。"""

from __future__ import annotations


class MdconvError(Exception):
    """すべての mdconv 例外の基底。"""


class UnsupportedFormatError(MdconvError):
    """対応していない拡張子・形式が指定された。"""


class BrokenDocumentError(MdconvError):
    """ファイルが壊れている、または想定した構造を持たない。"""


class MissingDependencyError(MdconvError):
    """変換に必要な追加パッケージが入っていない。"""

    def __init__(self, package: str, extra: str) -> None:
        super().__init__(
            f"'{package}' が必要です。`pip install 'mdconv[{extra}]'` でインストールしてください。"
        )
        self.package = package
        self.extra = extra
