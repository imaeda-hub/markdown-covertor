"""出力の補正（markitdown だけでは足りない部分）の単体テスト。

ここは文字列 → 文字列の変換なので、実ファイルなしで確かめられる。
"""

from mdconv import postprocess as pp
from mdconv.types import Notice

# -- 画像 -----------------------------------------------------------------

PLACEHOLDER = "![図](data:image/png;base64...)"


def test_placeholder_is_replaced_by_the_real_image():
    md, assets, unmatched = pp.place_images(PLACEHOLDER, [("photo.png", b"PNG")], "assets/x")
    assert len(assets) == 1
    assert md == f"![図]({assets[0].path})"
    assert assets[0].data == b"PNG"
    assert unmatched == 0


def test_same_image_is_stored_once():
    text = PLACEHOLDER + "\n" + PLACEHOLDER
    md, assets, _ = pp.place_images(text, [("a.png", b"X"), ("b.png", b"X")], "assets/x")
    assert len(assets) == 1, "中身が同じ画像は 1 ファイルにまとめる"
    assert md.count(assets[0].path) == 2


def test_placeholder_without_a_real_image_is_removed():
    md, assets, unmatched = pp.place_images(PLACEHOLDER, [], "assets/x")
    assert md == ""
    assert assets == []
    assert unmatched == 1, "壊れたリンクを残さず、落としたことを数える"


def test_url_image_reference_is_left_alone():
    """利用者が意図して張った URL は触らない。"""
    text = "![図](https://example.com/photo.png)"
    md, assets, unmatched = pp.place_images(text, [("x.png", b"X")], "assets/x")
    assert md == text
    assert assets == [] and unmatched == 0


def test_bare_name_reference_is_treated_as_a_placeholder():
    """PowerPoint の `Picture4.jpg` のような参照は、指す先が存在しない。"""
    md, assets, _ = pp.place_images("![図](Picture4.jpg)", [("x.png", b"X")], "assets/x")
    assert assets[0].data == b"X"
    assert "Picture4.jpg" not in md


def test_drop_images_keeps_real_links():
    text = f"{PLACEHOLDER}\n![実物](https://example.com/photo.png)"
    md, count = pp.drop_images(text)
    assert count == 1
    assert md.strip() == "![実物](https://example.com/photo.png)"


# -- 非表示シート ---------------------------------------------------------


def test_hidden_section_is_dropped_with_its_contents():
    text = "## 表\n| a |\n\n## 内部用\n| 原価 | 800 |\n\n## 別表\n| b |"
    assert pp.drop_sections(text, ["内部用"]) == "## 表\n| a |\n\n## 別表\n| b |"


def test_dropping_stops_at_the_same_heading_level():
    text = "## 秘密\n中身\n### 子\n子の中身\n## 公開\n見える"
    result = pp.drop_sections(text, ["秘密"])
    assert "中身" not in result and "子の中身" not in result
    assert "見える" in result


def test_dropping_nothing_leaves_the_text_untouched():
    text = "## 表\n| a |"
    assert pp.drop_sections(text, []) == text


# -- 表 -------------------------------------------------------------------


def test_empty_header_is_replaced_by_the_first_row():
    text = "|  |  |\n| --- | --- |\n| 項目 | 値 |\n| A | 1 |"
    assert pp.promote_empty_table_header(text) == "| 項目 | 値 |\n| --- | --- |\n| A | 1 |"


def test_normal_table_is_untouched():
    text = "| 項目 | 値 |\n| --- | --- |\n| A | 1 |"
    assert pp.promote_empty_table_header(text) == text


def test_nan_cells_become_empty():
    text = "| 月 | 金額 |\n| --- | --- |\n| 1月 | NaN |"
    assert pp.clean_tables(text).endswith("| 1月 |  |")


def test_degenerate_table_row_is_dropped():
    assert pp.clean_tables("## 空シート\n|\n|  |") == "## 空シート\n|  |"


def test_text_containing_nan_outside_a_table_is_untouched():
    assert pp.clean_tables("値は NaN でした") == "値は NaN でした"


# -- 箇条書きの入れ子 ------------------------------------------------------


def test_nest_lists_reindents_bullets_by_level():
    text = "* a\n* b\n* c"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b"), (0, "c")])
    assert applied
    assert md == "* a\n  + b\n* c"


def test_nest_lists_cycles_bullet_markers_every_three_levels():
    text = "* a\n* b\n* c\n* d"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b"), (2, "c"), (3, "d")])
    assert applied
    assert md == "* a\n  + b\n    - c\n      * d"


def test_nest_lists_keeps_the_original_marker_for_numbered_lists():
    text = "1. a\n2. b"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b")])
    assert applied
    assert md == "1. a\n  2. b"


def test_nest_lists_ignores_markdown_decoration_when_matching_text():
    """太字にした段落は `**a**` になるが、中身は元の `a` と同じとみなす。"""
    text = "* **a**\n* b"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b")])
    assert applied
    assert md == "* **a**\n  + b"


def test_nest_lists_does_nothing_when_counts_do_not_match():
    """対応が取れないときは、誤った入れ替えで順序を壊すより何もしない方が安全。"""
    text = "* a\n* b"
    md, applied = pp.nest_lists(text, [(0, "a")])
    assert not applied
    assert md == text


def test_nest_lists_does_nothing_when_content_does_not_match():
    """行数がたまたま同じでも、中身が対応していなければ誤った入れ替えになる。

    たとえば元ファイルで番号を解除した段落（numId=0）が誤って数えられ、
    たまたま `- ` で始まる本文行と行数だけ噛み合うことがある。
    その場合は数だけでなく中身も見て、対応が取れないと判断する。
    """
    text = "* a\n- 本文中のハイフン行"
    md, applied = pp.nest_lists(text, [(0, "a"), (0, "番号を解除した段落")])
    assert not applied
    assert md == text


def test_nest_lists_does_nothing_without_items():
    text = "* a\n* b"
    md, applied = pp.nest_lists(text, [])
    assert not applied
    assert md == text


# -- 見出し・体裁 ---------------------------------------------------------


def test_heading_offset():
    assert pp.shift_headings("# 題\n## 節", 1) == "## 題\n### 節"


def test_heading_offset_stops_at_six():
    assert pp.shift_headings("###### 深い", 2) == "###### 深い"


def test_heading_offset_of_zero_changes_nothing():
    assert pp.shift_headings("# 題", 0) == "# 題"


def test_front_matter():
    assert pp.front_matter("題名", "a.docx", "docx") == (
        "---\ntitle: '題名'\nsource: 'a.docx'\nsource_format: docx\n---"
    )


def test_front_matter_does_not_corrupt_backslashes():
    """二重引用符だと `C:\\temp` がエスケープとして壊れる。"""
    assert "C:\\temp" in pp.front_matter("C:\\temp", None, "docx")


def test_front_matter_escapes_quotes():
    assert "'it''s'" in pp.front_matter("it's", None, "docx")


def test_notices_comment():
    out = pp.notices_comment([Notice("画像を落とした")])
    assert out.startswith("<!-- 変換時の注意") and "画像を落とした" in out


def test_tidy_collapses_blank_lines_and_ends_with_one_newline():
    assert pp.tidy("a\n\n\n\nb\n\n\n") == "a\n\nb\n"
