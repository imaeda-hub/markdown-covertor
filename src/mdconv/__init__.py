"""mdconv — Word / Excel / PowerPoint / PDF を Markdown に変換する。"""

from .api import ConvertOptions, ConvertResult, convert_file
from .errors import (
    BrokenDocumentError,
    MdconvError,
    MissingDependencyError,
    UnsupportedFormatError,
)
from .registry import SUPPORTED_EXTENSIONS

__version__ = "0.1.0"

__all__ = [
    "ConvertOptions",
    "ConvertResult",
    "convert_file",
    "MdconvError",
    "UnsupportedFormatError",
    "BrokenDocumentError",
    "MissingDependencyError",
    "SUPPORTED_EXTENSIONS",
    "__version__",
]
