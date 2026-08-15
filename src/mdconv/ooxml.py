"""Office Open XML (docx / xlsx / pptx) 共通のユーティリティ。

docx・xlsx・pptx はいずれも「ZIP の中に XML が入っているだけ」なので、
標準ライブラリの zipfile と ElementTree で読める。外部依存を持たない方針
（docs/specs/03-design.md「依存方針」）の土台がこのモジュール。
"""

from __future__ import annotations

import zipfile
from xml.etree import ElementTree as ET

from .errors import BrokenDocumentError

# よく使う名前空間。タグ名は `ns("w", "p")` のように組み立てる。
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xml": "http://www.w3.org/XML/1998/namespace",
}


def q(prefix: str, tag: str) -> str:
    """名前空間つきタグ名を返す。例: q("w", "p") -> "{...}p" """
    return f"{{{NS[prefix]}}}{tag}"


def attr(el: ET.Element, prefix: str, name: str, default: str | None = None) -> str | None:
    return el.get(q(prefix, name), default)


class OoxmlPackage:
    """OOXML パッケージ（ZIP）への読み取り専用アクセス。"""

    def __init__(self, path: str) -> None:
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise BrokenDocumentError(f"ファイルを開けません: {path} ({exc})") from exc
        self._cache: dict[str, ET.Element] = {}

    def __enter__(self) -> OoxmlPackage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.zip.close()

    def has(self, name: str) -> bool:
        return name in self.zip.namelist()

    def read(self, name: str) -> bytes:
        try:
            return self.zip.read(name)
        except KeyError as exc:
            raise BrokenDocumentError(f"必要なパートがありません: {name}") from exc

    def xml(self, name: str) -> ET.Element:
        """XML パートを読み、パース結果をキャッシュして返す。"""
        if name not in self._cache:
            try:
                self._cache[name] = ET.fromstring(self.read(name))
            except ET.ParseError as exc:
                raise BrokenDocumentError(f"XML を解釈できません: {name} ({exc})") from exc
        return self._cache[name]

    def xml_or_none(self, name: str) -> ET.Element | None:
        return self.xml(name) if self.has(name) else None

    def rels(self, part: str) -> dict[str, str]:
        """パートのリレーション（rId -> 解決済みパスまたは URL）を返す。"""
        directory, _, filename = part.rpartition("/")
        rels_path = f"{directory}/_rels/{filename}.rels" if directory else f"_rels/{filename}.rels"
        root = self.xml_or_none(rels_path)
        if root is None:
            return {}
        out: dict[str, str] = {}
        for rel in root.findall(q("rel", "Relationship")):
            rid = rel.get("Id")
            target = rel.get("Target")
            if not rid or not target:
                continue
            if rel.get("TargetMode") == "External" or "://" in target:
                out[rid] = target
            else:
                out[rid] = _resolve(directory, target)
        return out


def _resolve(base_dir: str, target: str) -> str:
    """相対パス（../media/image1.png など）をパッケージ内の絶対パスに直す。"""
    if target.startswith("/"):
        return target.lstrip("/")
    parts = [p for p in base_dir.split("/") if p]
    for segment in target.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
        else:
            parts.append(segment)
    return "/".join(parts)


def text_of(el: ET.Element | None) -> str:
    """要素配下のテキストをすべて連結する。"""
    return "".join(el.itertext()) if el is not None else ""
