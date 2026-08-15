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


@pytest.fixture
def with_image(tmp_path):
    return fx.docx(tmp_path / "図あり.docx", fx.para("本文"), picture=fx.png())


def test_images_are_written_next_to_the_output_file(with_image, tmp_path):
    out = tmp_path / "out" / "a.md"
    assert main([str(with_image), "-o", str(out)]) == 0
    written = out.read_text(encoding="utf-8")
    assert "](assets/図あり/" in written
    assert list((tmp_path / "out" / "assets" / "図あり").glob("*.png"))


def test_images_of_different_documents_do_not_collide(tmp_path):
    """同名の画像を持つ 2 文書を一括変換しても、互いに上書きしないこと。"""
    src = tmp_path / "src"
    src.mkdir()
    for name, color in (("a", (255, 0, 0)), ("b", (0, 0, 255))):
        fx.docx(src / f"{name}.docx", fx.para(name), picture=fx.png(color))

    out = tmp_path / "out"
    assert main([str(src), "-o", str(out)]) == 0
    assert list((out / "assets" / "a").glob("*.png"))
    assert list((out / "assets" / "b").glob("*.png"))


def test_no_images_option_skips_extraction(with_image, tmp_path, capsys):
    out = tmp_path / "out" / "a.md"
    assert main([str(with_image), "-o", str(out), "--no-images"]) == 0
    assert not (tmp_path / "out" / "assets").exists()
    assert "画像を 1 個出力していません" in capsys.readouterr().err


def test_stdout_cannot_hold_images_so_extraction_is_disabled(with_image, capsys):
    """標準出力には画像の置き場所がないため、既定でも書き出さず警告する。"""
    assert main([str(with_image)]) == 0
    captured = capsys.readouterr()
    assert "![" not in captured.out
    assert "画像を 1 個出力していません" in captured.err


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
