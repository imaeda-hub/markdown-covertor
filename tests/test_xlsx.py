"""Excel (.xlsx) 変換のテスト。"""

from mdconv import ConvertOptions, convert_file

from . import fixtures as fx


def convert(tmp_path, sheets, *, hidden=None, options=None):
    path = fx.xlsx(tmp_path / "a.xlsx", sheets, hidden=hidden)
    return convert_file(path, options=options or ConvertOptions())


def test_sheet_becomes_heading_and_table(tmp_path):
    result = convert(tmp_path, {"売上": [["月", "金額"], ["1月", 100]]})
    assert result.markdown == "# 売上\n\n| 月 | 金額 |\n| --- | --- |\n| 1月 | 100 |\n"


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
    grid = [["見出し"]] + [[str(i)] for i in range(1, 11)]
    result = convert(tmp_path, {"S": grid}, options=ConvertOptions(max_rows=3))
    assert "| 2 |" in result.markdown
    assert "| 5 |" not in result.markdown
    assert any("打ち切り" in n.message for n in result.notices)
