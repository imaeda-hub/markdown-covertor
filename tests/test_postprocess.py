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


# -- グラフの表と次の図形の表の連結（T-37） --------------------------------


def test_split_merged_table_rows_separates_chart_and_next_table():
    """markitdown は PowerPoint のグラフの表の最終行に改行を付けずに返す。

    直後に別の表（図形）が続くと同じ行に連結され、両方の表が壊れる
    （実際の検体で再現した文字列そのもの、2026-08-17 の journal 参照）。
    分割は空行を挟む。ただの改行だけでは列数が同じ場合に GFM の表として
    1 つに融合したままになる（区切り行を挟まない `|` 行は前の表の続きと
    読まれるため）。
    """
    merged = "| C | 1500.0 || 項目 | 値 |\n| --- | --- |\n| 手入力 | 100.00 |"
    fixed = pp.split_merged_table_rows(merged)
    assert fixed == "| C | 1500.0 |\n\n| 項目 | 値 |\n| --- | --- |\n| 手入力 | 100.00 |"


def test_split_merged_table_rows_handles_multiple_merges_on_one_line():
    merged = "| A | 1 || B | 2 || C | 3 |"
    fixed = pp.split_merged_table_rows(merged)
    assert fixed == "| A | 1 |\n\n| B | 2 |\n\n| C | 3 |"


def test_split_merged_table_rows_leaves_normal_tables_alone():
    text = "| 項目 | 値 |\n| --- | --- |\n| A | 1 |\n\n本文の段落。"
    assert pp.split_merged_table_rows(text) == text


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


def test_number_padding_is_stripped_to_match_the_original_value():
    text = "| A |\n| --- |\n| 0.60 |\n| 0.65 |"
    assert pp.fix_number_padding(text) == "| A |\n| --- |\n| 0.6 |\n| 0.65 |"


def test_number_padding_strips_a_trailing_dot_for_integers_shown_as_floats():
    text = "| A |\n| --- |\n| 1.0 |\n| 2.5 |"
    assert pp.fix_number_padding(text) == "| A |\n| --- |\n| 1 |\n| 2.5 |"


def test_number_padding_leaves_unpadded_decimals_untouched():
    text = "| A |\n| --- |\n| 0.65 |"
    assert pp.fix_number_padding(text) == text


def test_number_padding_leaves_plain_integers_untouched():
    text = "| A |\n| --- |\n| 100 |"
    assert pp.fix_number_padding(text) == text


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


def test_nest_lists_renumbers_nested_numbered_lists():
    """入れ子にした番号付きリストは、階層ごとに 1 から振り直す（T-33）。

    markitdown は元の numId ごとに新しいリストとして出力するため、
    素の入力の番号は元の値のままあてにならない（ここでは意図的にでたらめな値にしている）。
    """
    text = "5. a\n9. b"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b")])
    assert applied
    assert md == "1. a\n  1. b"


def test_nest_lists_resumes_the_parent_numbering_after_a_nested_list():
    text = "1. a\n1. b\n2. c\n1. d"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b"), (1, "c"), (0, "d")])
    assert applied
    assert md == "1. a\n  1. b\n  2. c\n2. d"


def test_nest_lists_restarts_numbering_for_a_new_sublist_under_a_later_sibling():
    text = "1. a\n1. b\n1. c\n1. d"
    md, applied = pp.nest_lists(text, [(0, "a"), (1, "b"), (0, "c"), (1, "d")])
    assert applied
    assert md == "1. a\n  1. b\n2. c\n  1. d"


def test_nest_lists_does_not_bleed_numbers_across_two_unrelated_lists():
    """レビューで発覚: 本文を挟んだ 2 つの独立した番号付きリストが連番になってしまう。

    mammoth は本文が挟まると別のリスト（別の <ol>）として出力し、そこで
    すでに "1." から振り直している。行が連続していない（間に本文がある）ときは
    続きの番号として数えず、新しいリストとして扱う。
    """
    text = "5. a\n9. b\n\n本文\n\n5. c\n9. d"
    md, applied = pp.nest_lists(text, [(0, "a"), (0, "b"), (0, "c"), (0, "d")])
    assert applied
    assert md == "1. a\n2. b\n\n本文\n\n1. c\n2. d"


def test_nest_lists_restarts_a_numbered_sublist_under_each_bullet_sibling():
    """箇条書きの下にぶら下がる番号付きサブリストは、親が変わるたびに 1 から数える。"""
    text = "* a\n\n1. a1\n1. a2\n\n* b\n\n1. b1\n1. b2"
    md, applied = pp.nest_lists(
        text, [(0, "a"), (1, "a1"), (1, "a2"), (0, "b"), (1, "b1"), (1, "b2")]
    )
    assert applied
    assert md == "* a\n\n  1. a1\n  2. a2\n\n* b\n\n  1. b1\n  2. b2"


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


# -- PowerPoint の箇条書き（T-32） ------------------------------------------


def test_add_pptx_bullets_adds_symbols_and_indentation():
    text = "<!-- Slide number: 1 -->\n# 見出し\n親 1\n子 1\n子 2\n親 2"
    md, applied = pp.add_pptx_bullets(text, [(0, "親 1"), (1, "子 1"), (1, "子 2"), (0, "親 2")])
    assert applied
    assert "* 親 1\n  + 子 1\n  + 子 2\n* 親 2" in md
    assert "# 見出し" in md  # 表題は候補行から除かれ、書き換わらない


def test_add_pptx_bullets_skips_slide_comments_and_notes():
    text = "<!-- Slide number: 1 -->\n# 見出し\n項目\n\n### Notes:\nメモです"
    md, applied = pp.add_pptx_bullets(text, [(0, "項目")])
    assert applied
    assert "* 項目" in md
    assert "メモです" in md and "* メモです" not in md


def test_add_pptx_bullets_does_nothing_when_counts_do_not_match():
    text = "項目 1\n項目 2"
    md, applied = pp.add_pptx_bullets(text, [(0, "項目 1")])
    assert not applied
    assert md == text


def test_add_pptx_bullets_does_nothing_when_content_does_not_match():
    text = "項目 1\n無関係な本文"
    md, applied = pp.add_pptx_bullets(text, [(0, "項目 1"), (0, "項目 2")])
    assert not applied
    assert md == text


def test_add_pptx_bullets_does_nothing_without_items():
    text = "項目 1\n項目 2"
    md, applied = pp.add_pptx_bullets(text, [])
    assert not applied
    assert md == text


def test_add_pptx_bullets_uses_strict_comparison_unlike_nest_lists():
    """pptx は mammoth と違い Markdown 装飾を付けずに平文で出すため、
    `nest_lists()` のように `*`/`_` などの装飾を無視して比較しない（レビュー指摘）。
    装飾らしき文字が元と違う行は「別物」として扱い、何もしない。
    """
    text = "Item * note"
    md, applied = pp.add_pptx_bullets(text, [(0, "Item  note")])
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
