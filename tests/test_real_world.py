"""実世界の資料での回帰テスト（タスク T-18）。

`tests/assets/real/` に置いた第三者製の資料を変換する。
自分で作った素直なファイルでは出てこない構造（グラフ・SmartArt・グループ図形・
スキャン画像・罫線のない表）を持ち込むのが目的。出どころは同フォルダの README を参照。

大きいので全文は貼らず、**要約 + ハッシュ**を固定する。
  * ハッシュ … 1 文字でも変われば落ちる（完全一致の担保）
  * 要約   … 落ちたときに「何がどう変わったか」を人間が読んで分かる

期待値の更新:

    UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_real_world.py
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path

import pytest

from mdconv import convert_file
from mdconv.model import Heading, Table

REAL = Path(__file__).resolve().parent / "assets" / "real"
EXPECTED = REAL / "expected"

pypdf = pytest.importorskip("pypdf", reason="PDF の実資料テストには pypdf が必要")

OFFICE = ("test.docx", "test.xlsx", "test.pptx")
PDFS = (
    "test.pdf",
    "SPARSE-2024-INV-1234_borderless_table.pdf",
    "MEDRPT-2024-PAT-3847_medical_report_scan.pdf",
)


def summarize(name: str) -> str:
    """変換結果の要約を作る。人間がレビューできる粒度に落とす。"""
    result = convert_file(REAL / name)
    doc = result.document
    kinds = Counter(type(b).__name__ for b in doc.blocks)

    lines = [
        f"# {name}",
        "",
        f"- 形式: {doc.source_format}",
        f"- タイトル: {doc.title or '(なし)'}",
        f"- 文字数: {len(result.markdown)}",
        f"- SHA256: {hashlib.sha256(result.markdown.encode('utf-8')).hexdigest()}",
        "",
        "## ブロックの内訳",
        "",
    ]
    lines += [f"- {kind}: {count}" for kind, count in sorted(kinds.items())]

    headings = [b for b in doc.blocks if isinstance(b, Heading)]
    lines += ["", f"## 見出し（{len(headings)} 個）", ""]
    lines += [
        "- " + "#" * b.level + " " + "".join(s.text for s in b.spans).strip() for b in headings[:40]
    ]
    if len(headings) > 40:
        lines.append(f"- …ほか {len(headings) - 40} 個")

    tables = [b for b in doc.blocks if isinstance(b, Table)]
    lines += ["", f"## 表（{len(tables)} 個）", ""]
    lines += [f"- {len(t.rows) + (1 if t.header else 0)} 行 × {len(t.header)} 列" for t in tables]

    lines += ["", f"## 落とした情報の報告（{len(doc.notices)} 件）", ""]
    lines += [f"- {n.message}" for n in doc.notices] or ["- (なし)"]
    lines += ["", "## 本文の先頭", "", "```", result.markdown[:400].rstrip(), "```", ""]
    return "\n".join(lines)


@pytest.mark.parametrize("name", OFFICE + PDFS)
def test_real_world_document_is_frozen(name: str):
    summary = summarize(name)
    golden = EXPECTED / f"{name}.summary.md"

    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(summary, encoding="utf-8")

    assert golden.exists(), f"{golden.name} がない。UPDATE_GOLDEN=1 で生成できる"
    assert summary == golden.read_text(encoding="utf-8")


def test_powerpoint_reports_chart_and_image_it_cannot_render():
    """グラフや画像を黙って消さないこと。"""
    messages = " ".join(n.message for n in convert_file(REAL / "test.pptx").notices)
    assert "グラフ" in messages
    assert "画像" in messages


def test_powerpoint_recovers_text_inside_grouped_shapes():
    """グループ化された図形の中の本文も拾うこと。"""
    markdown = convert_file(REAL / "test.pptx").markdown
    assert "This is a nested shape with content in 2 shapes" in markdown


def test_scanned_pdf_is_reported_as_having_no_text():
    """スキャン PDF は空になるが、その理由を伝えること。"""
    result = convert_file(REAL / "MEDRPT-2024-PAT-3847_medical_report_scan.pdf")
    assert any("スキャン画像" in n.message for n in result.notices)
