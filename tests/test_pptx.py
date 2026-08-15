"""PowerPoint (.pptx) 変換のテスト。"""

from mdconv import ConvertOptions, convert_file

from . import fixtures as fx


def convert(tmp_path, slides, *, options=None):
    path = fx.pptx(tmp_path / "a.pptx", slides)
    return convert_file(path, options=options or ConvertOptions())


def test_title_and_bullets(tmp_path):
    slides = [{"title": "はじめに", "bullets": [(0, "背景"), (1, "詳細"), (0, "目的")]}]
    assert convert(tmp_path, slides).markdown == "# はじめに\n\n- 背景\n  - 詳細\n- 目的\n"


def test_slides_are_separated_by_divider(tmp_path):
    slides = [{"title": "1枚目"}, {"title": "2枚目"}]
    assert convert(tmp_path, slides).markdown == "# 1枚目\n\n---\n\n# 2枚目\n"


def test_divider_can_be_disabled(tmp_path):
    slides = [{"title": "1枚目"}, {"title": "2枚目"}]
    result = convert(tmp_path, slides, options=ConvertOptions(slide_dividers=False))
    assert "---" not in result.markdown


def test_speaker_notes_become_callout(tmp_path):
    slides = [{"title": "資料", "notes": "ここで事例を話す"}]
    result = convert(tmp_path, slides)
    assert "> **発表者ノート**" in result.markdown
    assert "> ここで事例を話す" in result.markdown


def test_notes_can_be_excluded(tmp_path):
    slides = [{"title": "資料", "notes": "秘密のメモ"}]
    result = convert(tmp_path, slides, options=ConvertOptions(include_notes=False))
    assert "秘密のメモ" not in result.markdown


def test_table_on_slide(tmp_path):
    slides = [{"title": "比較", "table": [["項目", "値"], ["A", "1"]]}]
    result = convert(tmp_path, slides)
    assert "| 項目 | 値 |" in result.markdown
    assert "| A | 1 |" in result.markdown


def test_graphic_kind_is_named_from_its_namespace():
    """出力できない図表の種類を uri から言い当てられること。

    手元の実資料に SmartArt が無いので、ここだけは合成した uri で確かめる。
    """
    from xml.etree import ElementTree as ET

    from mdconv.converters.pptx import _graphic_kind

    def frame(uri: str) -> ET.Element:
        return ET.fromstring(
            f'<graphicFrame xmlns:a="{fx.A.split(chr(34))[1]}">'
            f'<a:graphic><a:graphicData uri="{uri}"/></a:graphic></graphicFrame>'
        )

    assert (
        _graphic_kind(frame("http://schemas.openxmlformats.org/drawingml/2006/chart")) == "グラフ"
    )
    assert (
        _graphic_kind(frame("http://schemas.openxmlformats.org/drawingml/2006/diagram"))
        == "SmartArt"
    )
    assert _graphic_kind(frame("http://example.com/unknown")) == "図表"


def test_untitled_slide_falls_back_to_number(tmp_path):
    result = convert(tmp_path, [{"title": ""}, {"title": ""}])
    assert "# スライド 1" in result.markdown
    assert "# スライド 2" in result.markdown
