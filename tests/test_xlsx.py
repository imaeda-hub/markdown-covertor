"""Excel (.xlsx) 変換のテスト。"""

from mdconv import ConvertOptions, convert_file

from . import fixtures as fx


def convert(tmp_path, sheets, *, hidden=None, options=None):
    path = fx.xlsx(tmp_path / "a.xlsx", sheets, hidden=hidden)
    return convert_file(path, options=options or ConvertOptions())


def test_sheet_becomes_heading_and_table(tmp_path):
    result = convert(tmp_path, {"売上": [["月", "金額"], ["1月", 100]]})
    assert result.markdown == "# 売上\n\n| 月 | 金額 |\n| --- | --- |\n| 1月 | 100 |\n"


# -- 見出し行の推定 -------------------------------------------------------


def test_text_row_above_numeric_rows_is_a_header(tmp_path):
    result = convert(tmp_path, {"S": [["月", "金額"], ["1月", 100], ["2月", 200]]})
    assert "| 月 | 金額 |\n| --- | --- |\n| 1月 | 100 |" in result.markdown


def test_first_row_containing_a_number_is_not_a_header(tmp_path):
    """1 行目からデータが始まる表で、先頭行が見出しに化けないこと。"""
    result = convert(tmp_path, {"S": [["田中", 30], ["鈴木", 25]]})
    assert result.markdown == "# S\n\n|  |  |\n| --- | --- |\n| 田中 | 30 |\n| 鈴木 | 25 |\n"


def test_all_text_table_has_no_header(tmp_path):
    """すべて文字列の表は見出しの有無を判定できないので、見出しなしとして扱う。"""
    result = convert(tmp_path, {"S": [["田中", "営業"], ["鈴木", "開発"]]})
    assert "| 田中 | 営業 |" in result.markdown
    assert result.markdown.startswith("# S\n\n|  |  |\n")


def test_single_row_sheet_has_no_header(tmp_path):
    result = convert(tmp_path, {"S": [["合計", 100]]})
    assert result.markdown == "# S\n\n|  |  |\n| --- | --- |\n| 合計 | 100 |\n"


def test_multiple_sheets_keep_workbook_order(tmp_path):
    result = convert(tmp_path, {"B": [["x"]], "A": [["y"]]})
    assert result.markdown.index("# B") < result.markdown.index("# A")


def test_hidden_sheet_is_excluded_by_default(tmp_path):
    result = convert(tmp_path, {"表": [["a"]], "裏": [["b"]]}, hidden={"裏"})
    assert "# 裏" not in result.markdown
    assert any("裏" in n.message for n in result.notices)


def test_hidden_sheet_can_be_included(tmp_path):
    result = convert(
        tmp_path,
        {"表": [["a"]], "裏": [["b"]]},
        hidden={"裏"},
        options=ConvertOptions(include_hidden=True),
    )
    assert "# 裏" in result.markdown


def test_gaps_between_cells_are_preserved(tmp_path):
    result = convert(tmp_path, {"S": [["A", "", "C"], ["1", "", "3"]]})
    assert "| A |  | C |" in result.markdown


def test_float_values_are_trimmed(tmp_path):
    result = convert(tmp_path, {"S": [["値"], [1.0], [1.5]]})
    assert "| 1 |" in result.markdown
    assert "| 1.5 |" in result.markdown


def test_empty_sheet_is_labelled(tmp_path):
    result = convert(tmp_path, {"空": []})
    assert "（空のシート）" in result.markdown


def test_max_rows_truncates_with_notice(tmp_path):
    grid = [["見出し"]] + [[i] for i in range(1, 11)]
    result = convert(tmp_path, {"S": grid}, options=ConvertOptions(max_rows=3))
    assert "| 2 |" in result.markdown
    assert "| 5 |" not in result.markdown
    assert any("打ち切り" in n.message for n in result.notices)


def test_truncation_does_not_change_header_detection(tmp_path):
    """打ち切りで数値行が消えても、見出し行の判定は表全体で決めること。"""
    sheets = {"S": [["月", "金額"], ["1月", 100], ["2月", 200]]}
    result = convert(tmp_path, sheets, options=ConvertOptions(max_rows=1))
    assert result.markdown == "# S\n\n| 月 | 金額 |\n| --- | --- |\n"
