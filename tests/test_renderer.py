"""renderer（IR → Markdown）の単体テスト。"""

from mdconv.model import (
    Callout,
    CodeBlock,
    Divider,
    Document,
    Heading,
    Image,
    ListBlock,
    ListItem,
    Paragraph,
    Span,
    Table,
)
from mdconv.renderer import RenderOptions, render


def md(*blocks, **options) -> str:
    return render(Document(blocks=list(blocks)), RenderOptions(**options))


def test_heading_levels_are_clamped():
    assert md(Heading(1, [Span("題")])) == "# 題\n"
    assert md(Heading(9, [Span("深い")])) == "###### 深い\n"


def test_heading_offset():
    assert md(Heading(1, [Span("題")]), heading_offset=1) == "## 題\n"


def test_inline_decorations():
    spans = [Span("普通 "), Span("太字", bold=True), Span(" と "), Span("斜体", italic=True)]
    assert md(Paragraph(spans)) == "普通 **太字** と *斜体*\n"


def test_bold_italic_combined():
    assert md(Paragraph([Span("両方", bold=True, italic=True)])) == "***両方***\n"


def test_adjacent_same_style_spans_are_merged():
    spans = [Span("太", bold=True), Span("字", bold=True)]
    assert md(Paragraph(spans)) == "**太字**\n"


def test_decoration_does_not_swallow_surrounding_spaces():
    assert md(Paragraph([Span(" 前後 ", bold=True)])) == "**前後**\n"


def test_special_characters_are_escaped():
    assert md(Paragraph([Span("a_b*c[d]")])) == "a\\_b\\*c\\[d\\]\n"


def test_paragraph_starting_with_marker_is_escaped():
    assert md(Paragraph([Span("- これは箇条書きではない")])) == "\\- これは箇条書きではない\n"


def test_inline_code_is_not_escaped():
    assert md(Paragraph([Span("a_b", code=True)])) == "`a_b`\n"


def test_link():
    assert md(Paragraph([Span("例", href="https://example.com")])) == "[例](https://example.com)\n"


def test_link_with_space_is_wrapped():
    span = Span("例", href="https://example.com/a b")
    assert md(Paragraph([span])) == "[例](<https://example.com/a b>)\n"


def test_unordered_list_with_nesting():
    block = ListBlock(
        [
            ListItem([Span("親")]),
            ListItem([Span("子")], level=1),
            ListItem([Span("親2")]),
        ]
    )
    assert md(block) == "- 親\n  - 子\n- 親2\n"


def test_ordered_list_numbers_increment_per_level():
    block = ListBlock(
        [
            ListItem([Span("一")], ordered=True),
            ListItem([Span("一の一")], level=1, ordered=True),
            ListItem([Span("二")], ordered=True),
        ]
    )
    assert md(block) == "1. 一\n  1. 一の一\n2. 二\n"


def test_table_with_header():
    table = Table(
        header=[[Span("名前")], [Span("値")]],
        rows=[[[Span("A")], [Span("1")]]],
    )
    assert md(table) == "| 名前 | 値 |\n| --- | --- |\n| A | 1 |\n"


def test_table_rows_are_padded_to_widest_row():
    table = Table(header=[[Span("A")]], rows=[[[Span("1")], [Span("2")]]])
    assert md(table) == "| A |  |\n| --- | --- |\n| 1 | 2 |\n"


def test_table_cell_escapes_pipe_and_newline():
    table = Table(header=[[Span("a|b")]], rows=[[[Span("1\n2")]]])
    assert md(table) == "| a\\|b |\n| --- |\n| 1<br>2 |\n"


def test_code_block_uses_longer_fence_when_needed():
    assert md(CodeBlock("```", "python")) == "````python\n```\n````\n"


def test_callout():
    block = Callout("発表者ノート", [Paragraph([Span("補足")])])
    assert md(block) == "> **発表者ノート**\n>\n> 補足\n"


def test_image_and_divider():
    assert md(Image("assets/a.png", alt="図")) == "![図](assets/a.png)\n"
    assert md(Divider()) == "---\n"


def test_front_matter():
    doc = Document(blocks=[Paragraph([Span("本文")])], title="題名", source_format="docx")
    doc.source_name = "a.docx"
    out = render(doc, RenderOptions(front_matter=True))
    assert out.startswith('---\ntitle: "題名"\nsource: "a.docx"\nsource_format: docx\n---\n')


def test_notices_are_optional():
    doc = Document(blocks=[Paragraph([Span("本文")])])
    doc.warn("画像を省略しました")
    assert "画像を省略しました" not in render(doc, RenderOptions())
    assert "画像を省略しました" in render(doc, RenderOptions(include_notices=True))
