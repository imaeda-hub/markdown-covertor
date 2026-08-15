"""変換の入口（api）と、元ファイルの検査（inspection）のテスト。

`tests/fixtures.py` が作る最小の OOXML を使う。実資料での検証は
`tests/test_corpus.py` が担当する。
"""

import pytest

from mdconv import ConvertOptions, convert_file
from mdconv.errors import BrokenDocumentError

from . import fixtures as fx


def convert(tmp_path, body, **kwargs):
    options = kwargs.pop("options", None)
    path = fx.docx(tmp_path / "資料.docx", body, **kwargs)
    return convert_file(path, options=options or ConvertOptions())


# -- 基本 -----------------------------------------------------------------


def test_docx_headings_and_text(tmp_path):
    body = fx.para("第 1 章", style="Heading1") + fx.para("本文です。")
    markdown = convert(tmp_path, body).markdown
    assert "# 第 1 章" in markdown
    assert "本文です。" in markdown


def test_result_carries_format_and_source(tmp_path):
    result = convert(tmp_path, fx.para("本文"))
    assert result.format == "docx"
    assert result.source.name == "資料.docx"


def test_xlsx_sheets_become_sections(tmp_path):
    path = fx.xlsx(tmp_path / "帳簿.xlsx", {"売上": [["月", "金額"], ["1月", 100]]})
    markdown = convert_file(path).markdown
    assert "売上" in markdown
    assert "| 月 | 金額 |" in markdown
    assert "| 1月 | 100 |" in markdown


def test_broken_file_raises_a_readable_error(tmp_path):
    """中身が壊れた資料を「平文として変換できた」ことにしない。"""
    path = tmp_path / "壊れた.docx"
    path.write_bytes(b"not a zip")
    with pytest.raises(BrokenDocumentError) as exc:
        convert_file(path)
    assert "壊れた.docx" in str(exc.value)


def test_wrong_extension_is_detected_from_the_content(tmp_path):
    """.docx という名前の Excel ブックでも、中身どおりに扱うこと（FR-105）。"""
    path = fx.xlsx(tmp_path / "実はエクセル.docx", {"S": [["a", 1]]})
    assert convert_file(path).format == "xlsx"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        convert_file(tmp_path / "ない.docx")


# -- 落とした情報の報告 ---------------------------------------------------


def test_chart_is_reported(tmp_path):
    chart = (
        f"<w:p><w:r><w:drawing><a:graphic {fx.A}><a:graphicData "
        'uri="http://schemas.openxmlformats.org/drawingml/2006/chart"/></a:graphic>'
        "</w:drawing></w:r></w:p>"
    )
    result = convert(tmp_path, fx.para("本文") + chart)
    assert any("グラフ" in n.message for n in result.notices)


def test_smartart_is_reported(tmp_path):
    art = (
        f"<w:p><w:r><w:drawing><a:graphic {fx.A}><a:graphicData "
        'uri="http://schemas.openxmlformats.org/drawingml/2006/diagram"/></a:graphic>'
        "</w:drawing></w:r></w:p>"
    )
    assert any("SmartArt" in n.message for n in convert(tmp_path, art).notices)


def test_text_box_is_reported(tmp_path):
    box = "<w:p><w:r><w:pict><w:txbxContent><w:p/></w:txbxContent></w:pict></w:r></w:p>"
    result = convert(tmp_path, fx.para("本文") + box)
    assert any("テキストボックス" in n.message for n in result.notices)


def test_the_same_graphic_is_not_counted_twice(tmp_path):
    """mc:Choice と mc:Fallback に同じ図表が書かれても 1 個と数えること。"""
    graphic = (
        f"<a:graphic {fx.A}><a:graphicData "
        'uri="http://schemas.openxmlformats.org/drawingml/2006/chart"/></a:graphic>'
    )
    body = (
        '<w:p><mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
        'markup-compatibility/2006">'
        f'<mc:Choice Requires="wps"><w:drawing>{graphic}</w:drawing></mc:Choice>'
        f"<mc:Fallback><w:pict>{graphic}</w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:p>"
    )
    charts = [n.message for n in convert(tmp_path, body).notices if "グラフ" in n.message]
    assert charts == ["グラフを 1 個出力していません（Markdown に表現がありません）"]


def test_hidden_sheet_is_removed_and_reported(tmp_path):
    path = fx.xlsx(
        tmp_path / "帳簿.xlsx",
        {"公開": [["a", "1"]], "内部用": [["原価", "800"]]},
        hidden={"内部用"},
    )
    result = convert_file(path)
    assert "原価" not in result.markdown, "非表示シートの中身が残ってはいけない"
    assert "内部用" not in result.markdown
    assert any("内部用" in n.message for n in result.notices)


def test_hidden_sheet_can_be_included(tmp_path):
    path = fx.xlsx(
        tmp_path / "帳簿.xlsx",
        {"公開": [["a", "1"]], "内部用": [["原価", "800"]]},
        hidden={"内部用"},
    )
    result = convert_file(path, options=ConvertOptions(include_hidden=True))
    assert "原価" in result.markdown


# -- 画像 -----------------------------------------------------------------


def test_image_is_written_next_to_the_markdown(tmp_path):
    """markitdown は画像の中身を出さないので、元ファイルから取り出せていること。"""
    image = fx.png()
    path = fx.docx(tmp_path / "資料.docx", fx.para("本文"), picture=image)
    result = convert_file(path)

    assert len(result.assets) == 1
    assert result.assets[0].data == image
    assert result.assets[0].path in result.markdown

    result.write(tmp_path / "out" / "a.md")
    assert (tmp_path / "out" / result.assets[0].path).read_bytes() == image


def test_images_can_be_turned_off(tmp_path):
    path = fx.docx(tmp_path / "資料.docx", fx.para("本文"), picture=fx.png())
    result = convert_file(path, options=ConvertOptions(extract_images=False))
    assert result.assets == []
    assert "![" not in result.markdown


# -- 出力オプション -------------------------------------------------------


def test_front_matter(tmp_path):
    result = convert(
        tmp_path, fx.para("本文"), title="議事録", options=ConvertOptions(front_matter=True)
    )
    assert result.markdown.startswith("---\ntitle: '議事録'\n")


def test_heading_offset(tmp_path):
    body = fx.para("章", style="Heading1")
    result = convert(tmp_path, body, options=ConvertOptions(heading_offset=1))
    assert "## 章" in result.markdown


def test_notices_can_be_embedded(tmp_path):
    path = fx.xlsx(tmp_path / "帳簿.xlsx", {"公開": [["a"]], "裏": [["b"]]}, hidden={"裏"})
    result = convert_file(path, options=ConvertOptions(include_notices=True))
    assert "<!-- 変換時の注意" in result.markdown


def test_output_ends_with_a_single_newline(tmp_path):
    markdown = convert(tmp_path, fx.para("本文")).markdown
    assert markdown.endswith("\n") and not markdown.endswith("\n\n")


def test_conversion_is_deterministic(tmp_path):
    path = fx.docx(tmp_path / "資料.docx", fx.para("本文", style="Heading1"))
    assert convert_file(path).markdown == convert_file(path).markdown
