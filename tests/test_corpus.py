"""検体（実資料）での回帰テスト。

`tests/corpus/` の 3 フォルダを対象にする。運用は同フォルダの README を参照。

  * `passing/` … 通った資料。変換結果の要約を固定し、**退行を検出する**
  * `failing/` … 通らなかった資料。**例外を出さないこと**だけを保証し、実例として残す
  * `inbox/`   … 未検査。例外の種類だけ確かめる（ループが振り分ける）

期待値の更新:

    UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_corpus.py
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

from mdconv import MdconvError, convert_file

CORPUS = Path(__file__).resolve().parent / "corpus"
PASSING = CORPUS / "passing"
FAILING = CORPUS / "failing"
INBOX = CORPUS / "inbox"
CONVERTED = PASSING / "converted"

# 説明用のテキストと、生成物の置き場所。それ以外はすべて検体として扱う
_NOT_SAMPLES = {".md", ".txt", ".gitkeep"}


def documents(folder: Path) -> list[Path]:
    """フォルダ内の検体。

    拡張子で絞り込まないのは、`.doc` のような**未対応形式こそ検体になる**から。
    未対応なら「対応形式を案内して断る」のが正しい振る舞いで、それも検証対象。
    """
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() not in _NOT_SAMPLES
    )


def test_generated_files_have_their_document():
    """生成物が取り残されていないこと。

    昇格（failing → passing）のときに古いゴールデンを消し忘れると、
    「まだ壊れている」という嘘の期待値が残ったままテストは緑になる。
    掃除漏れを機械的に検出する。
    """
    passing = {p.name for p in documents(PASSING)}
    failing = {p.name for p in documents(FAILING)}
    orphans: list[str] = []

    for folder, owners in (
        (CONVERTED, passing),
        (expected_dir(PASSING), passing),
        (expected_dir(FAILING), failing),
    ):
        for generated in folder.glob("*.md"):
            source = generated.name.removesuffix(".summary.md").removesuffix(".md")
            if source not in owners:
                orphans.append(str(generated.relative_to(CORPUS)))

    assets = CONVERTED / "assets"
    if assets.is_dir():
        stems = {Path(name).stem for name in passing}
        orphans += [
            str(d.relative_to(CORPUS))
            for d in assets.iterdir()
            if d.is_dir() and d.name not in stems
        ]

    assert not orphans, f"元の検体が無い生成物: {sorted(orphans)}"


def expected_dir(folder: Path) -> Path:
    return folder / "expected"


def find_sample(name: str) -> Path:
    """検体を名前で探す。passing / failing のどちらにあっても見つける。

    直った検体は passing へ昇格する。置き場所を決め打ちにすると、
    **バグが直った瞬間にテストが壊れる**ので名前で引く。
    """
    for folder in (PASSING, FAILING):
        candidate = folder / name
        if candidate.exists():
            return candidate
    pytest.skip(f"検体 {name} が見つからない（削除された可能性）")


def ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{2,}:?\s*\|)+\s*$")


def summarize(path: Path) -> str:
    """変換結果の要約。人間がレビューできる粒度に落とす。

    v0.2 から本文は markitdown が作る文字列なので、構造は Markdown を
    読み直して数える（内部表現に依存しない = エンジンを替えても比べられる）。
    """
    result = convert_file(path)
    lines_in = result.markdown.splitlines()

    headings = [(len(m.group(1)), m.group(2).strip()) for m in map(_HEADING.match, lines_in) if m]
    tables = _table_shapes(lines_in)

    lines = [
        f"# {path.name}",
        "",
        f"- 形式: {result.format}",
        f"- タイトル: {result.title or '(なし)'}",
        f"- 文字数: {len(result.markdown)}",
        f"- 行数: {len(lines_in)}",
        f"- 画像: {len(result.assets)} 個",
        f"- SHA256: {hashlib.sha256(result.markdown.encode('utf-8')).hexdigest()}",
        "",
        f"## 見出し（{len(headings)} 個）",
        "",
    ]
    lines += ["- " + "#" * level + " " + text for level, text in headings[:40]]
    if len(headings) > 40:
        lines.append(f"- …ほか {len(headings) - 40} 個")

    lines += ["", f"## 表（{len(tables)} 個）", ""]
    lines += [f"- {rows} 行 × {cols} 列" for rows, cols in tables]

    lines += ["", f"## 落とした情報の報告（{len(result.notices)} 件）", ""]
    lines += [f"- {n.message}" for n in result.notices] or ["- (なし)"]
    lines += ["", "## 本文の先頭", "", "```", result.markdown[:400].rstrip(), "```", ""]
    return "\n".join(lines)


def _table_shapes(lines: list[str]) -> list[tuple[int, int]]:
    """表ごとの (行数, 列数)。区切り行を目印に数える。"""
    shapes: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if not _TABLE_SEPARATOR.match(line):
            continue
        cols = line.count("|") - 1
        rows = 1  # 見出し行
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].startswith("|"):
            rows += 1
            cursor += 1
        shapes.append((rows, cols))
    return shapes


# -- passing --------------------------------------------------------------


@pytest.mark.parametrize("path", documents(PASSING), ids=ids(documents(PASSING)))
def test_passing_document_output_is_frozen(path: Path):
    """通った資料の変換結果が変わっていないこと。"""
    assert_output_is_frozen(path, PASSING)


@pytest.mark.parametrize("path", documents(PASSING), ids=ids(documents(PASSING)))
def test_passing_document_converted_file_is_stored(path: Path):
    """**変換後の Markdown そのもの**をリポジトリに置き、内容を固定する。

    要約だけでは「実際にどんな Markdown になるのか」を人間が確認できない。
    `converted/` には CLI で変換したのと同じ成果物（画像を含む）が入る。
    """
    result = convert_file(path)
    # 拡張子を残すのは、同名で形式違いの検体（test.docx と test.xlsx）が衝突するため。
    # なお画像の置き場所は拡張子を含まないので、まだ衝突しうる（T-23）
    converted = CONVERTED / f"{path.name}.md"

    if os.environ.get("UPDATE_GOLDEN"):
        result.write(converted)

    assert converted.exists(), f"{converted.name} がない。UPDATE_GOLDEN=1 で生成できる"
    assert result.markdown == converted.read_text(encoding="utf-8")

    for asset in result.assets:
        stored = converted.parent / asset.path
        assert stored.exists(), f"{asset.path} が置かれていない"
        assert stored.read_bytes() == asset.data, f"{asset.path} の中身が変わっている"


def assert_output_is_frozen(path: Path, folder: Path) -> None:
    summary = summarize(path)
    golden = expected_dir(folder) / f"{path.name}.summary.md"

    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(summary, encoding="utf-8")

    assert golden.exists(), f"{golden.name} がない。UPDATE_GOLDEN=1 で生成できる"
    assert summary == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", documents(PASSING), ids=ids(documents(PASSING)))
def test_passing_document_keeps_its_text(path: Path):
    """通った資料が空にならないこと（判定基準の最低ライン）。"""
    assert convert_file(path).markdown.strip(), f"{path.name} の出力が空"


def test_powerpoint_reports_chart_and_image_it_cannot_render():
    """グラフや画像を黙って消さないこと。"""
    messages = " ".join(n.message for n in convert_file(find_sample("test.pptx")).notices)
    assert "グラフ" in messages
    assert "画像" in messages


def test_powerpoint_recovers_text_inside_grouped_shapes():
    """グループ化された図形の中の本文も拾うこと。"""
    markdown = convert_file(find_sample("test.pptx")).markdown
    assert "This is a nested shape with content in 2 shapes" in markdown


# -- failing --------------------------------------------------------------


def test_borderless_table_pdf_is_restored_as_a_table():
    """罫線のない表が、段落に潰れず表として出ること（v0.2 で直った）。"""
    result = convert_file(find_sample("SPARSE-2024-INV-1234_borderless_table.pdf"))
    assert "| Product Code | Location |" in result.markdown


def test_scanned_pdf_is_reported_as_having_no_text():
    """スキャン PDF は空になるが、その理由を伝えること。"""
    result = convert_file(find_sample("MEDRPT-2024-PAT-3847_medical_report_scan.pdf"))
    assert any("スキャン" in n.message for n in result.notices)


@pytest.mark.parametrize("path", documents(FAILING), ids=ids(documents(FAILING)))
def test_failing_document_fails_gracefully(path: Path):
    """通らなかった資料でも、説明できない例外で落ちないこと。

    出力の質は問わない（それが failing である理由）。ただし利用者に
    スタックトレースを見せないという約束（NFR-04）だけは守る。
    """
    try:
        convert_file(path)
    except MdconvError:
        pass  # 原因を日本語で説明できる失敗は想定内


@pytest.mark.parametrize("path", documents(FAILING), ids=ids(documents(FAILING)))
def test_failing_document_output_is_frozen(path: Path):
    """**壊れ方**も固定する。

    直っていないものを放置すると、静かに悪化しても気づけない。
    出力が変わったら（良くなったときも）このテストが落ち、差分が見える。
    """
    try:
        assert_output_is_frozen(path, FAILING)
    except MdconvError:
        pytest.skip("変換できない検体（例外の扱いは別テストで確認）")


@pytest.mark.parametrize("path", documents(FAILING), ids=ids(documents(FAILING)))
def test_failing_document_has_a_report(path: Path):
    """通らなかった資料には、何がどう壊れているかの説明が添えてあること。"""
    report = FAILING / f"{path.name}.md"
    assert report.exists(), f"{report.name} がない。症状と原因を書くこと"
    text = report.read_text(encoding="utf-8")
    assert "## 症状" in text and "## タスク" in text, f"{report.name} の項目が足りない"


def test_failing_reports_have_their_document():
    """症状レポートだけが取り残されていないこと（昇格時の消し忘れ検出）。"""
    names = {p.name for p in documents(FAILING)}
    orphans = [
        p.name
        for p in FAILING.glob("*.md")
        if p.name != "README.md" and p.name[: -len(".md")] not in names
    ]
    assert not orphans, f"対応する資料が無いレポート: {orphans}"


# -- inbox ----------------------------------------------------------------


@pytest.mark.parametrize("path", documents(INBOX), ids=ids(documents(INBOX)))
def test_inbox_document_fails_gracefully_if_at_all(path: Path):
    """未検査の資料でも、想定外の例外で落ちないこと。

    inbox は人間が置いたばかりの場所なので、変換の質はまだ問わない。
    mdconv 自身の例外（原因を日本語で説明できるもの）以外が出たら、それは欠陥。
    """
    try:
        convert_file(path)
    except MdconvError:
        pass  # 原因を説明できる失敗は想定内
