"""PDF 変換のテスト。

テキスト復元ロジック（blocks_from_text）は pypdf なしでも検証できるよう分離している。
PDF ファイル経由の end-to-end テストは pypdf がある環境でのみ実行する。
"""

import pytest

from mdconv.converters.pdf import blocks_from_text
from mdconv.model import Document, Heading, ListBlock, Paragraph
from mdconv.renderer import render


def to_md(text: str) -> str:
    return render(Document(blocks=blocks_from_text(text)))


def test_blank_line_separates_paragraphs():
    assert to_md("一つ目の段落。\n\n二つ目の段落。") == "一つ目の段落。\n\n二つ目の段落。\n"


def test_wrapped_japanese_lines_are_joined_without_space():
    assert to_md("これは折り返された\n日本語の文です。") == "これは折り返された日本語の文です。\n"


def test_wrapped_english_lines_are_joined_with_space():
    assert to_md("This line is\nwrapped.") == "This line is wrapped.\n"


def test_hyphenated_english_word_is_rejoined():
    assert to_md("docu-\nment") == "document\n"


def test_bullets_are_recognised():
    blocks = blocks_from_text("・りんご\n・みかん")
    assert isinstance(blocks[0], ListBlock)
    assert len(blocks[0].items) == 2


def test_numbered_section_title_becomes_heading():
    blocks = blocks_from_text("1.2 概要\n本文が続きます。")
    assert isinstance(blocks[0], Heading)
    assert blocks[0].level == 3
    assert isinstance(blocks[1], Paragraph)


def test_numbered_sentence_is_a_list_not_a_heading():
    blocks = blocks_from_text("1. これは長めの文章なので見出しではなく箇条書きとして扱われます。")
    assert isinstance(blocks[0], ListBlock)


pypdf = pytest.importorskip("pypdf", reason="PDF の end-to-end テストには pypdf が必要")


def make_pdf(path, lines):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


def test_empty_pdf_reports_no_text(tmp_path):
    from mdconv import convert_file

    path = make_pdf(tmp_path / "blank.pdf", [])
    result = convert_file(path)
    assert result.format == "pdf"
    assert any("スキャン画像" in n.message for n in result.notices)
