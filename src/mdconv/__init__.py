"""mdconv — Word / Excel / PowerPoint / PDF を Markdown に変換する。

変換の本体は markitdown。このパッケージは
「markitdown だけでは足りない部分」を補うために存在する。
  * 落とした情報（グラフ・非表示シート等）を警告として伝える
  * 埋め込み画像を実ファイルに書き出す
  * 表の空ヘッダなど、出力の崩れを整える
  * 日本語のエラー、一括変換、出力オプション
"""

from .api import ConvertOptions, ConvertResult, convert_file
from .errors import (
    BrokenDocumentError,
    MdconvError,
    MissingDependencyError,
    UnsupportedFormatError,
)
from .registry import SUPPORTED_EXTENSIONS
from .types import Asset, Notice

__version__ = "0.2.0"

__all__ = [
    "ConvertOptions",
    "ConvertResult",
    "convert_file",
    "Notice",
    "Asset",
    "MdconvError",
    "UnsupportedFormatError",
    "BrokenDocumentError",
    "MissingDependencyError",
    "SUPPORTED_EXTENSIONS",
    "__version__",
]
