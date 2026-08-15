"""CLI とフォーマット判定のテスト。"""

import pytest

from mdconv.cli import main
from mdconv.errors import UnsupportedFormatError
from mdconv.registry import detect

from . import fixtures as fx


@pytest.fixture
def sample(tmp_path):
    return fx.docx(tmp_path / "資料.docx", fx.para("見出し", style="Heading1") + fx.para("本文"))


def test_stdout_output(sample, capsys):
    assert main([str(sample)]) == 0
    assert capsys.readouterr().out == "# 見出し\n\n本文\n"


def test_file_output(sample, tmp_path):
    out = tmp_path / "out.md"
    assert main([str(sample), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# 見出し")


def test_existing_file_is_not_overwritten_without_flag(sample, tmp_path, capsys):
    out = tmp_path / "out.md"
    out.write_text("既存", encoding="utf-8")
    main([str(sample), "-o", str(out)])
    assert out.read_text(encoding="utf-8") == "既存"
    assert "スキップ" in capsys.readouterr().err

    main([str(sample), "-o", str(out), "--overwrite"])
    assert out.read_text(encoding="utf-8").startswith("# 見出し")


def test_directory_input_writes_one_file_per_document(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    fx.docx(src / "a.docx", fx.para("A"))
    fx.xlsx(src / "b.xlsx", {"S": [["x"]]})
    (src / "readme.txt").write_text("無視される", encoding="utf-8")

    out = tmp_path / "out"
    assert main([str(src), "-o", str(out)]) == 0
    assert sorted(p.name for p in out.glob("*.md")) == ["a.md", "b.md"]


def test_multiple_inputs_without_output_is_a_usage_error(tmp_path, capsys):
    a = fx.docx(tmp_path / "a.docx", fx.para("A"))
    b = fx.docx(tmp_path / "b.docx", fx.para("B"))
    assert main([str(a), str(b)]) == 2
    assert "-o" in capsys.readouterr().err


def test_unknown_file_returns_usage_error(tmp_path, capsys):
    assert main([str(tmp_path / "missing.docx")]) == 2


def test_broken_file_returns_error_code(tmp_path, capsys):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"garbage")
    assert main([str(path)]) == 1
    assert "[失敗]" in capsys.readouterr().err


def test_heading_offset_option(sample, capsys):
    main([str(sample), "--heading-offset", "1"])
    assert capsys.readouterr().out.startswith("## 見出し")


def test_front_matter_option(sample, capsys):
    main([str(sample), "--front-matter"])
    assert capsys.readouterr().out.startswith("---\n")


# -- 形式判定 -------------------------------------------------------------


def test_detect_by_extension(tmp_path):
    assert detect(tmp_path / "a.docx").name == "docx"
    assert detect(tmp_path / "a.PPTX").name == "pptx"


def test_detect_by_content_when_extension_is_wrong(tmp_path):
    path = fx.docx(tmp_path / "mislabeled.bin", fx.para("A"))
    assert detect(path).name == "docx"


def test_legacy_binary_format_has_dedicated_message(tmp_path):
    with pytest.raises(UnsupportedFormatError, match="97-2003"):
        detect(tmp_path / "old.doc")


def test_unknown_extension_raises(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        detect(path)
