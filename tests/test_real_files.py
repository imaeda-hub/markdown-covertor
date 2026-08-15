"""実ファイルの回帰テスト（タスク T-01）。

`tests/assets/` に置いた**本物の Office ファイル**（python-docx / openpyxl /
python-pptx が生成したもの）を変換し、出力を 1 文字も違わず固定する。

手書き XML のテスト（`tests/fixtures.py`）は「読み方」を確かめるもので、
こちらは「本物のファイルに含まれる想定外の構造」を検出するためのもの。
実際、このテストの導入時に「スタイル側に番号定義がある箇条書き」を
取りこぼすバグが見つかった。

期待値を更新するには（**差分を必ず目で確認すること**）:

    UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_real_files.py

入力ファイル自体を作り直すには:

    .venv/bin/python tools/build_fixtures.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mdconv import ConvertOptions, convert_file

ASSETS = Path(__file__).resolve().parent / "assets"
EXPECTED = ASSETS / "expected"
SAMPLES = ("sample.docx", "sample.xlsx", "sample.pptx")


@pytest.mark.parametrize("name", SAMPLES)
def test_real_file_conversion_is_frozen(name: str):
    """本物のファイルの変換結果が、記録した Markdown と完全一致すること。"""
    result = convert_file(ASSETS / name)
    golden = EXPECTED / f"{name}.md"

    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(result.markdown, encoding="utf-8")

    assert golden.exists(), f"{golden.name} がない。UPDATE_GOLDEN=1 で生成できる"
    assert result.markdown == golden.read_text(encoding="utf-8")


def test_real_docx_reports_what_it_dropped():
    """本物の Word ファイルで、落とした情報が報告されること。"""
    result = convert_file(ASSETS / "sample.docx", options=ConvertOptions(extract_images=False))
    messages = [n.message for n in result.notices]
    assert any("表題" in m for m in messages)
    assert any("画像" in m for m in messages)


def test_real_docx_extracts_its_image():
    result = convert_file(ASSETS / "sample.docx")
    assert [a.path for a in result.document.assets] == ["assets/sample/image1.png"]
    assert result.document.assets[0].data.startswith(b"\x89PNG")


def test_real_xlsx_hides_the_hidden_sheet():
    result = convert_file(ASSETS / "sample.xlsx")
    assert "内部用" not in result.markdown
    assert "原価" not in result.markdown
    assert any("内部用" in n.message for n in result.notices)


def test_sample_xlsx_actually_contains_formulas():
    """テスト資産に数式が入っていること。

    数式が消えた資産で「数式が出ない」を確かめても意味がないので、
    前提そのものをテストする（このガードが無く空振りしていた指摘への対応）。
    """
    import zipfile

    with zipfile.ZipFile(ASSETS / "sample.xlsx") as book:
        sheet = book.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "<f>" in sheet, "sample.xlsx に数式が含まれていない"
    assert "<f>B3/B2</f><v>" in sheet, "数式に計算結果が入っていない"


def test_real_xlsx_uses_cached_formula_values():
    """数式セルが計算結果として出ること（数式そのものが出ないこと）。"""
    result = convert_file(ASSETS / "sample.xlsx")
    assert "B3/B2" not in result.markdown
    assert "1.25" in result.markdown


def test_real_pptx_keeps_speaker_notes():
    result = convert_file(ASSETS / "sample.pptx")
    assert "> **発表者ノート**" in result.markdown
    assert "ここで事例を 1 つ話す" in result.markdown


def test_conversion_is_deterministic():
    """同じ入力から常に同じ出力になること（NFR-01）。"""
    for name in SAMPLES:
        first = convert_file(ASSETS / name).markdown
        second = convert_file(ASSETS / name).markdown
        assert first == second, f"{name} の出力が実行ごとに変わる"
