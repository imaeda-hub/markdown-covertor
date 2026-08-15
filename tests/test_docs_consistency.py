"""ドキュメントの健全性テスト。

仕様書は人間がレビューする対象なので、**壊れたまま放置されるのが最も困る**。
目視に頼らず、機械的に落とせるものはここで落とす。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TESTS = ROOT / "tests"

_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
# ``…`` や ```…``` も 1 つの塊として扱う（中の例をリンクと誤認しないため）
_CODE_SPAN = re.compile(r"(`+)[\s\S]*?\1")
_REQUIREMENT_ROW = re.compile(r"^\|\s*((?:FR|NFR)-\d+)\s*\|(.+)$", re.MULTILINE)
_TASK_ROW = re.compile(r"^\|\s*(T-\d+)\s*\|", re.MULTILINE)


def markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if ".venv" not in p.parts)


def test_no_broken_relative_links():
    """ドキュメント間のリンクが切れていないこと。"""
    broken: list[str] = []
    for md in markdown_files():
        # コードスパン内は「例」であって実リンクではないので除外する
        text = _CODE_SPAN.sub("", md.read_text(encoding="utf-8"))
        for label, link in _LINK.findall(text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = (md.parent / link.split("#")[0]).resolve()
            if not target.exists():
                broken.append(f"{md.relative_to(ROOT)}: [{label}]({link})")
    assert not broken, "リンク切れ:\n" + "\n".join(broken)


def test_requirements_reference_existing_tests():
    """要件表の「確認方法」に書いたテストが実在すること。

    仕様とテストの対応は、この表だけが担保している。テストを消したり改名したりすると
    仕様書が静かに嘘になるので、ここで気づけるようにする。
    """
    source = "\n".join(p.read_text(encoding="utf-8") for p in TESTS.glob("test_*.py"))
    functions = set(re.findall(r"^def (test_\w+)", source, re.MULTILINE))
    files = {p.name for p in TESTS.glob("test_*.py")}

    missing: list[str] = []
    for req_id, row in _REQUIREMENT_ROW.findall(
        (DOCS / "specs" / "02-requirements.md").read_text(encoding="utf-8")
    ):
        reference = row.rsplit("|", 2)[-2].strip().strip("`")
        if reference in ("未", "", "テストが完全一致で比較", "ベンチマーク未整備"):
            continue
        if reference.endswith(".py"):
            if reference not in files:
                missing.append(f"{req_id}: {reference} というテストファイルは無い")
        elif reference.startswith("test_") and reference not in functions:
            missing.append(f"{req_id}: {reference} というテストは無い")
    assert not missing, "要件表が実在しないテストを指している:\n" + "\n".join(missing)


def test_ids_are_unique():
    """要件 ID とタスク ID が重複していないこと（採番ミスの検出）。"""
    duplicates: list[str] = []

    requirements = [
        rid
        for rid, _ in _REQUIREMENT_ROW.findall(
            (DOCS / "specs" / "02-requirements.md").read_text(encoding="utf-8")
        )
    ]
    tasks = _TASK_ROW.findall((DOCS / "specs" / "04-tasks.md").read_text(encoding="utf-8"))
    for name, ids in (("要件", requirements), ("タスク", tasks)):
        seen = {i for i in ids if ids.count(i) > 1}
        duplicates.extend(f"{name} ID の重複: {i}" for i in sorted(seen))
    assert not duplicates, "\n".join(duplicates)


def test_journal_entries_live_in_month_folders():
    """作業ログが月ごとのフォルダに整理されていること（1 年で 365 個並ぶのを防ぐ）。"""
    stray = [
        p.name
        for p in (DOCS / "loop" / "journal").glob("*.md")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name)
    ]
    assert not stray, f"journal/YYYY-MM/ に移動してください: {stray}"
