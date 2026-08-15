"""Word (.docx) 変換のテスト。"""

import pytest

from mdconv import ConvertOptions, convert_file
from mdconv.errors import BrokenDocumentError

from . import fixtures as fx


def convert(tmp_path, body, **kwargs):
    options = kwargs.pop("options", None)
    path = fx.docx(tmp_path / "a.docx", body, **kwargs)
    return convert_file(path, options=options or ConvertOptions())


def test_headings_and_paragraph(tmp_path):
    body = (
        fx.para("第 1 章", style="Heading1")
        + fx.para("節", style="Heading2")
        + fx.para("本文です。")
    )
    assert convert(tmp_path, body).markdown == "# 第 1 章\n\n## 節\n\n本文です。\n"


def test_title_style_is_not_a_heading(tmp_path):
    """表題は文書のタイトル。見出し 1 と `#` が二重にならないよう本文には出さない。"""
    body = fx.para("提案書", style="Title") + fx.para("背景", style="Heading1")
    result = convert(tmp_path, body)
    assert result.markdown == "# 背景\n"
    assert result.document.title == "提案書"
    assert any("提案書" in n.message for n in result.notices)


def test_title_is_kept_in_front_matter(tmp_path):
    body = fx.para("提案書", style="Title") + fx.para("本文")
    path = fx.docx(tmp_path / "a.docx", body)
    result = convert_file(path, options=ConvertOptions(front_matter=True))
    assert result.markdown.startswith('---\ntitle: "提案書"\n')


def test_body_title_wins_over_document_properties(tmp_path):
    """本文の表題が docProps のタイトルに負けて消えないこと。"""
    result = convert(tmp_path, fx.para("2026年度 事業計画", style="Title"), title="古いテンプレ名")
    assert result.document.title == "2026年度 事業計画"


def test_second_title_paragraph_is_kept_as_text(tmp_path):
    """表題スタイルが 2 回使われても、2 つ目の文字が消えないこと。"""
    body = fx.para("一つ目", style="Title") + fx.para("二つ目", style="Title")
    result = convert(tmp_path, body)
    assert result.markdown == "二つ目\n"
    assert result.document.title == "一つ目"


def test_subtitle_becomes_a_paragraph(tmp_path):
    assert convert(tmp_path, fx.para("副題です", style="Subtitle")).markdown == "副題です\n"


def test_run_decorations(tmp_path):
    body = (
        "<w:p>"
        + fx.run("普通と")
        + fx.run("太字", bold=True)
        + fx.run("と")
        + fx.run("斜体", italic=True)
        + "</w:p>"
    )
    assert convert(tmp_path, body).markdown == "普通と**太字**と*斜体*\n"


def test_bullet_list_is_grouped_into_one_block(tmp_path):
    body = (
        fx.para("一つ目", num=("1", 0))
        + fx.para("入れ子", num=("1", 1))
        + fx.para("二つ目", num=("1", 0))
    )
    assert convert(tmp_path, body).markdown == "- 一つ目\n  - 入れ子\n- 二つ目\n"


def test_numbered_list(tmp_path):
    body = fx.para("最初", num=("2", 0)) + fx.para("次", num=("2", 0))
    assert convert(tmp_path, body).markdown == "1. 最初\n2. 次\n"


def test_list_style_without_paragraph_numbering(tmp_path):
    """Word の「箇条書き」スタイルは段落に番号設定を持たず、スタイル側に持つ。

    実ファイルで見つかった取りこぼし（T-01）。段落だけ見ているとリストにならない。
    """
    body = (
        fx.para("一つ目", style="ListBullet")
        + fx.para("入れ子", style="ListBullet2")
        + fx.para("二つ目", style="ListBullet")
    )
    assert convert(tmp_path, body).markdown == "- 一つ目\n  - 入れ子\n- 二つ目\n"


def test_number_list_style_without_paragraph_numbering(tmp_path):
    body = fx.para("最初", style="ListNumber") + fx.para("次", style="ListNumber")
    assert convert(tmp_path, body).markdown == "1. 最初\n2. 次\n"


def test_list_depth_comes_from_style_name_not_style_id(tmp_path):
    """日本語版 Word の styleId（a5 など）の数字を階層と誤読しないこと。"""
    body = fx.para("一つ目", style="ListBullet") + fx.para("入れ子", style="a5")
    assert convert(tmp_path, body).markdown == "- 一つ目\n  - 入れ子\n"


def test_paragraph_level_overrides_style_numbering(tmp_path):
    """段落が階層だけを上書きする形（w:ilvl のみ）でも入れ子が保たれること。"""
    body = fx.para("親", style="ListBullet") + fx.para("子", style="ListBullet", num=(None, 1))
    assert convert(tmp_path, body).markdown == "- 親\n  - 子\n"


def test_numbering_removed_by_num_id_zero(tmp_path):
    """numId="0" は「番号を外す」指定なので、箇条書きにしないこと。"""
    body = fx.para("ただの段落", style="ListBullet", num=("0", 0))
    assert convert(tmp_path, body).markdown == "ただの段落\n"


def test_list_ends_when_normal_paragraph_appears(tmp_path):
    body = fx.para("項目", num=("1", 0)) + fx.para("段落")
    assert convert(tmp_path, body).markdown == "- 項目\n\n段落\n"


def test_table_first_row_is_header(tmp_path):
    body = fx.table([["名前", "値"], ["A", "1"]])
    assert convert(tmp_path, body).markdown == "| 名前 | 値 |\n| --- | --- |\n| A | 1 |\n"


def test_hyperlink_resolves_relationship(tmp_path):
    body = f'<w:p><w:hyperlink r:id="rId9">{fx.run("リンク")}</w:hyperlink></w:p>'
    result = convert(tmp_path, body, rels={"rId9": "https://example.com"})
    assert result.markdown == "[リンク](https://example.com)\n"


def test_quote_style_becomes_blockquote(tmp_path):
    assert convert(tmp_path, fx.para("引用文", style="Quote")).markdown == "> 引用文\n"


def test_line_break_inside_paragraph(tmp_path):
    body = "<w:p>" + fx.run("上") + "<w:r><w:br/></w:r>" + fx.run("下") + "</w:p>"
    assert convert(tmp_path, body).markdown == "上\n下\n"


def test_empty_paragraphs_are_dropped(tmp_path):
    body = fx.para("本文") + "<w:p></w:p>" + fx.para("続き")
    assert convert(tmp_path, body).markdown == "本文\n\n続き\n"


def test_core_title_is_kept_as_metadata(tmp_path):
    result = convert(tmp_path, fx.para("本文"), title="議事録")
    assert result.document.title == "議事録"


def test_image_is_extracted_by_default(tmp_path):
    body = f'<w:p><w:drawing><a:blip {fx.A} r:embed="rId5"/></w:drawing></w:p>'
    result = convert(
        tmp_path, body, rels={"rId5": "media/image1.png"}, media={"image1.png": b"PNG"}
    )
    # 一括変換で衝突しないよう、画像は文書名のフォルダに分けて置かれる
    assert result.markdown == "![image1.png](assets/a/image1.png)\n"

    result.write(tmp_path / "out" / "a.md")
    assert (tmp_path / "out" / "assets" / "a" / "image1.png").read_bytes() == b"PNG"


def test_image_is_reported_when_extraction_is_off(tmp_path):
    body = f'<w:p><w:drawing><a:blip {fx.A} r:embed="rId5"/></w:drawing></w:p>'
    path = fx.docx(
        tmp_path / "a.docx", body, rels={"rId5": "media/image1.png"}, media={"image1.png": b"PNG"}
    )
    result = convert_file(path, options=ConvertOptions(extract_images=False))
    assert any("image1.png" in n.message for n in result.notices)
    assert result.markdown.strip() == ""


def test_broken_file_raises(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")
    with pytest.raises(BrokenDocumentError):
        convert_file(path)
