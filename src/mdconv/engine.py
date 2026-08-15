"""変換エンジン（markitdown の薄い包み）。

**このモジュールだけが markitdown を知っている。** 将来エンジンを差し替える
（Docling など）ときに、直すのはここ 1 箇所で済むようにしてある。

markitdown を土台に選んだ理由は docs/specs/03-design.md「なぜ markitdown か」を参照。
"""

from __future__ import annotations

from pathlib import Path

from .errors import BrokenDocumentError, MissingDependencyError


def convert(path: Path) -> tuple[str, str | None]:
    """ファイルを Markdown にする。戻り値は (本文, タイトル)。"""
    converter = _markitdown()
    try:
        result = converter.convert(str(path))
    except Exception as exc:  # markitdown は多様な例外を投げる
        raise BrokenDocumentError(_explain(path, exc)) from exc
    title = (result.title or "").strip() or None
    return result.text_content, title


_INSTANCE = None


def _markitdown():
    """MarkItDown のインスタンスを使い回す（初期化に時間がかかるため）。"""
    global _INSTANCE
    if _INSTANCE is None:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise MissingDependencyError("markitdown", "all") from exc
        # 既定ではネットワークへ出ない。外部 API の利用は利用者が明示的に有効にする
        _INSTANCE = MarkItDown(enable_plugins=False)
    return _INSTANCE


def _explain(path: Path, exc: Exception) -> str:
    """利用者にスタックトレースではなく、原因の分かる日本語を返す（NFR-04）。"""
    text = str(exc)
    if "password" in text.lower() or "encrypt" in text.lower():
        return f"暗号化された文書です（パスワードが必要）: {path.name}"
    if "not a zip" in text.lower() or "BadZipFile" in type(exc).__name__:
        return f"ファイルが壊れているか、想定した形式ではありません: {path.name}"
    return f"変換できませんでした: {path.name}（{type(exc).__name__}: {text}）"
