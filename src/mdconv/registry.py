"""拡張子 → コンバータの対応表と、形式の判定。

拡張子が信用できない場合（.doc という名前の .docx など）に備え、
ファイル先頭のシグネチャでも判定できるようにしてある。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .errors import UnsupportedFormatError
from .model import Document


@dataclass(frozen=True, slots=True)
class Format:
    name: str
    extensions: tuple[str, ...]
    loader: Callable[[], Callable[..., Document]]
    description: str


def _docx_loader() -> Callable[..., Document]:
    from .converters import docx

    return docx.convert


def _xlsx_loader() -> Callable[..., Document]:
    from .converters import xlsx

    return xlsx.convert


def _pptx_loader() -> Callable[..., Document]:
    from .converters import pptx

    return pptx.convert


def _pdf_loader() -> Callable[..., Document]:
    from .converters import pdf

    return pdf.convert


FORMATS: tuple[Format, ...] = (
    Format("docx", (".docx", ".docm"), _docx_loader, "Word 文書"),
    Format("xlsx", (".xlsx", ".xlsm"), _xlsx_loader, "Excel ブック"),
    Format("pptx", (".pptx", ".pptm"), _pptx_loader, "PowerPoint プレゼンテーション"),
    Format("pdf", (".pdf",), _pdf_loader, "PDF 文書"),
)

_BY_EXT = {ext: fmt for fmt in FORMATS for ext in fmt.extensions}
_BY_NAME = {fmt.name: fmt for fmt in FORMATS}

SUPPORTED_EXTENSIONS = tuple(sorted(_BY_EXT))

# 旧形式（バイナリの .doc / .xls / .ppt）は OOXML ではないため別メッセージを出す
_LEGACY = {".doc": "Word 97-2003", ".xls": "Excel 97-2003", ".ppt": "PowerPoint 97-2003"}


def detect(path: str | Path, *, explicit: str | None = None) -> Format:
    """変換に使う形式を決める。explicit が与えられればそれを優先する。"""
    if explicit:
        fmt = _BY_NAME.get(explicit.lower().lstrip("."))
        if fmt is None:
            raise UnsupportedFormatError(
                f"未対応の形式です: {explicit}（対応: {', '.join(_BY_NAME)}）"
            )
        return fmt

    suffix = Path(path).suffix.lower()
    if suffix in _BY_EXT:
        return _BY_EXT[suffix]
    if suffix in _LEGACY:
        raise UnsupportedFormatError(
            f"{_LEGACY[suffix]} 形式（{suffix}）は未対応です。"
            "Office で新しい形式に保存し直してください。"
        )
    sniffed = sniff(path)
    if sniffed is not None:
        return sniffed
    raise UnsupportedFormatError(
        f"拡張子 '{suffix or '(なし)'}' には対応していません"
        f"（対応: {', '.join(SUPPORTED_EXTENSIONS)}）"
    )


def sniff(path: str | Path) -> Format | None:
    """中身を見て形式を推定する。判定できなければ None。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
    except OSError:
        return None
    if head.startswith(b"%PDF"):
        return _BY_NAME["pdf"]
    if head.startswith(b"PK\x03\x04"):
        return _sniff_ooxml(path)
    return None


def _sniff_ooxml(path: str | Path) -> Format | None:
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return None
    if "word/document.xml" in names:
        return _BY_NAME["docx"]
    if "xl/workbook.xml" in names:
        return _BY_NAME["xlsx"]
    if "ppt/presentation.xml" in names:
        return _BY_NAME["pptx"]
    return None
