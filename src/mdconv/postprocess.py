"""markitdown の出力を、実用に耐える Markdown に整える。

markitdown はそのままでは次の問題がある。ここで直す。

| 問題 | 直し方 |
|---|---|
| 画像が base64 で本文に埋め込まれ、ファイルが肥大する | 実ファイルに書き出して参照に置き換える |
| 非表示シートの中身がそのまま出る（情報漏洩） | 該当する節を丸ごと落とす |
| 表の 1 行目が空ヘッダになり、実データがずれる | 空ヘッダなら次の行を見出しに繰り上げる |
| 落ちた情報が分からない | 警告を末尾コメントに残せるようにする |
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .types import Asset, Notice

# markitdown が出す画像参照。中身は入っておらず `data:image/png;base64...` という印だけ
_IMAGE_REF = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)]*)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_EMPTY_HEADER_ROW = re.compile(r"^\|(?:\s*\|)+\s*$")
_SEPARATOR_ROW = re.compile(r"^\|(?:\s*:?-{2,}:?\s*\|)+\s*$")
_NAN_CELL = re.compile(r"\|\s*NaN\s*\|")
_PADDED_DECIMAL = re.compile(r"(?<=\|)([ \t]*)(-?\d+\.\d+)([ \t]*)(?=\|)")
_LIST_ITEM = re.compile(r"^(?P<indent>[ ]*)(?P<marker>[*+-]|\d+\.)(?P<sep>[ ]+)(?P<text>.*)$")
_BULLET_CYCLE = "*+-"  # mammoth 自身が入れ子で使う記号の順序に合わせる


def place_images(
    markdown: str, images: list[tuple[str, bytes]], asset_dir: str
) -> tuple[str, list[Asset], int]:
    """画像のプレースホルダを、実体への参照に置き換える。

    markitdown は画像の中身を出力に含めない（`data:image/png;base64...` という印だけ）。
    元ファイルから取り出した実体を**出現順**に対応づける。
    同じ画像が複数回出ても 1 ファイルで済むよう、内容のハッシュで名前を付ける。

    戻り値は (本文, 書き出す画像, 対応づけられなかった数)。
    """
    assets: list[Asset] = []
    by_digest: dict[str, str] = {}
    used = 0
    unmatched = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal used, unmatched
        if not _is_placeholder(match.group("target")):
            return match.group(0)  # 元から実体を指している参照は触らない
        if used >= len(images):
            unmatched += 1
            return ""  # 実体が無い参照は残さない（壊れたリンクになるため）
        name, data = images[used]
        used += 1
        digest = hashlib.sha256(data).hexdigest()[:12]
        if digest not in by_digest:
            ext = _normalise_extension(Path(name).suffix.lstrip(".") or "png")
            path = f"{asset_dir}/image-{digest}.{ext}"
            by_digest[digest] = path
            assets.append(Asset(path=path, data=data))
        alt = match.group("alt").strip() or name
        return f"![{alt}]({by_digest[digest]})"

    return _IMAGE_REF.sub(replace, markdown), assets, unmatched


def drop_images(markdown: str) -> tuple[str, int]:
    """画像の参照を本文から取り除き、取り除いた数を返す（`--no-images` 用）。"""
    count = 0

    def remove(match: re.Match[str]) -> str:
        nonlocal count
        if not _is_placeholder(match.group("target")):
            return match.group(0)
        count += 1
        return ""

    return _IMAGE_REF.sub(remove, markdown), count


def _is_placeholder(target: str) -> bool:
    """markitdown が中身なしで出した参照かどうか。

    2 つの形がある。どちらも指す先が存在しないので、そのままでは壊れたリンクになる。
      * `data:image/png;base64...`  … Word。中身が入っていない印
      * `Picture4.jpg`              … PowerPoint。図形名で、ファイルは存在しない
    URL は利用者が意図して張ったリンクなので触らない。
    """
    if target.startswith("data:"):
        return True
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return False
    return "/" not in target  # 階層を持たない裸の名前は実体を指していない


def drop_sections(markdown: str, titles: list[str]) -> str:
    """指定した見出しの節を、次の同じ深さの見出しまで丸ごと落とす。

    Excel の非表示シートに使う。**中身が出力に残ると情報漏洩になる**ので、
    見出しだけでなく配下もまとめて消す。
    """
    if not titles:
        return markdown
    targets = {t.strip() for t in titles if t.strip()}
    out: list[str] = []
    skipping_at: int | None = None

    for line in markdown.splitlines():
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if skipping_at is not None and level <= skipping_at:
                skipping_at = None  # 同じ深さ以上の見出しが来たら削除を終える
            if skipping_at is None and heading.group(2).strip() in targets:
                skipping_at = level
                continue
        if skipping_at is None:
            out.append(line)
    return "\n".join(out)


def clean_tables(markdown: str) -> str:
    """markitdown が出す表の粗を取る。

    * 空セルが `NaN` になる（pandas 経由の Excel 変換でそうなる）
    * 空のシートが `|` だけの壊れた表になる
    どちらも「元データに無いもの」なので、そのまま出すと誤読を招く。
    """
    out: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            out.append(line)
            continue
        cleaned = _NAN_CELL.sub("|  |", line)
        cleaned = _NAN_CELL.sub("|  |", cleaned)  # 連続する NaN セル用に 2 周
        if _is_degenerate_row(cleaned):
            continue
        out.append(cleaned)
    return "\n".join(out)


def _is_degenerate_row(line: str) -> bool:
    """表として意味を成さない行（`|` だけ、セルが 1 つも無い）。"""
    stripped = line.strip()
    return stripped == "|" or stripped == "||"


def fix_number_padding(markdown: str) -> str:
    """表の数値セルから、同じ列で桁を揃えるために付いた余分な `0` を取り除く（T-28）。

    markitdown は Excel の数値セルを pandas 経由で読むため、同じ列に
    より精度の高い値（例: `0.65`）があると、精度の低い値（`0.6`）にも
    `0` を付けて桁を揃えてしまう（`0.60` になる）。値そのものは変わって
    いないので、末尾の `0`（と、余った `.`）を削るだけで元の値に戻る。
    """

    def strip(match: re.Match[str]) -> str:
        lead, number, trail = match.groups()
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return f"{lead}{number}{trail}"

    return _PADDED_DECIMAL.sub(strip, markdown)


def promote_empty_table_header(markdown: str) -> str:
    """空のヘッダ行を持つ表で、次の行を見出しに繰り上げる。

    markitdown は Word の表を「空ヘッダ + 全行データ」で出すことがある。
    そのままだと 1 行目の項目名がデータ行に見えてしまう。
    """
    lines = markdown.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        header, separator, first = lines[i], _get(lines, i + 1), _get(lines, i + 2)
        if (
            _EMPTY_HEADER_ROW.match(header)
            and _SEPARATOR_ROW.match(separator)
            and first.startswith("|")
            and not _EMPTY_HEADER_ROW.match(first)
        ):
            out.extend([first, separator])
            i += 3
            continue
        out.append(header)
        i += 1
    return "\n".join(out)


def nest_lists(markdown: str, items: list[tuple[int, str]]) -> tuple[str, bool]:
    """箇条書きの階層を、元ファイルから復元した `items` の通りに付け直す。

    `items` は本文中の箇条書き段落を (階層, 段落の文字列) で出現順に並べたもの
    （`ooxml.docx_list_levels`）。行数が一致するだけでは対応づけの根拠として弱い
    （例: 番号を解除した段落と、たまたま `- ` で始まる本文の数が偶然噛み合う）ので、
    **各行の中身も元の段落の文字列と一致するときだけ**適用する。
    一致しないときは何もしない（誤った入れ替えで順序を壊すより安全）。

    戻り値は (本文, 適用したかどうか)。適用できなかったことは呼び出し側が
    警告として報告できるようにする（黙って直らないのを防ぐ）。
    """
    lines = markdown.splitlines()
    indices = [i for i, line in enumerate(lines) if _LIST_ITEM.match(line)]
    if not items or len(indices) != len(items):
        return markdown, False

    pairs = list(zip(indices, items, strict=True))
    for index, (_, text) in pairs:
        match = _LIST_ITEM.match(lines[index])
        if _normalize_list_text(match.group("text")) != _normalize_list_text(text):
            return markdown, False

    numbering: dict[int, int] = {}
    prev_index: int | None = None
    for index, (level, _) in pairs:
        if prev_index is not None and index != prev_index + 1:
            # 行が連続していない = 間に本文や別のリストが挟まっている。
            # mammoth はそこで別のリストとして出力しているので、続きの番号ではなく
            # 新しいリストとして数え直す（そうしないと無関係な 2 つのリストが
            # 1 つに数珠つなぎになってしまう）。
            numbering = {}
        prev_index = index
        match = _LIST_ITEM.match(lines[index])
        marker = match.group("marker")
        if marker in _BULLET_CYCLE:
            marker = _BULLET_CYCLE[level % len(_BULLET_CYCLE)]
        else:
            # markitdown は元の numId ごとに新しいリストとして番号を振るため、
            # 階層をまたぐと数字があてにならない。階層ごとに 1 から数え直す
            # （深い階層に潜っていた分の続きは、浅い階層へ戻った時点で捨てる）。
            numbering = {lv: n for lv, n in numbering.items() if lv <= level}
            numbering[level] = numbering.get(level, 0) + 1
            marker = f"{numbering[level]}."
        lines[index] = f"{'  ' * level}{marker} {match.group('text')}"
    return "\n".join(lines), True


_SLIDE_COMMENT = re.compile(r"^<!--.*-->$")
_NOTES_HEADING = "### Notes:"


def add_pptx_bullets(markdown: str, items: list[tuple[int, str]]) -> tuple[str, bool]:
    """PowerPoint の本文行に、記号と階層を付け直す。

    markitdown は PowerPoint の箇条書きを記号も階層も付けない平文で出す（劣化、T-32）。
    docx の `nest_lists()` と違い、行に元から記号が付いていないため、
    見出し・スライド区切りのコメント・表・発表者ノートを除いた「本文候補行」を数え、
    `items`（`ooxml.pptx_list_levels`）と**件数・中身の両方が一致するときだけ**適用する。
    中身の比較は前後の空白を無視するだけの厳密一致（`nest_lists()` の
    `_normalize_list_text` のような Markdown 装飾の除去はしない）。markitdown は
    mammoth と違って pptx の段落を装飾なしの素のテキストで出すため、緩める必要がない。

    戻り値は (本文, 適用したかどうか)。
    """
    lines = markdown.splitlines()
    candidates = _pptx_body_line_indices(lines)
    if not items or len(candidates) != len(items):
        return markdown, False

    pairs = list(zip(candidates, items, strict=True))
    for index, (_, text) in pairs:
        if lines[index].strip() != text.strip():
            return markdown, False

    for index, (level, _) in pairs:
        marker = _BULLET_CYCLE[level % len(_BULLET_CYCLE)]
        lines[index] = f"{'  ' * level}{marker} {lines[index]}"
    return "\n".join(lines), True


def _pptx_body_line_indices(lines: list[str]) -> list[int]:
    """箇条書きの記号を付け得る「本文候補行」の位置を返す。

    見出し（表題）・`<!-- Slide number: N -->`・表・空行・発表者ノートの中身は対象外。
    """
    out: list[int] = []
    in_notes = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _SLIDE_COMMENT.match(stripped):
            in_notes = False
            continue
        if stripped == _NOTES_HEADING:
            in_notes = True
            continue
        if in_notes or not stripped or stripped.startswith(("#", "|")):
            continue
        out.append(i)
    return out


_MD_DECORATION = re.compile(r"[*_`\\]")


def _normalize_list_text(text: str) -> str:
    """太字などの Markdown 装飾やエスケープの差を無視して比較するための正規化。"""
    return _MD_DECORATION.sub("", text).strip()


def shift_headings(markdown: str, offset: int) -> str:
    """見出しレベルを下げる（最大 6 で頭打ち）。"""
    if offset <= 0:
        return markdown

    def bump(match: re.Match[str]) -> str:
        level = min(len(match.group(1)) + offset, 6)
        return f"{'#' * level} {match.group(2)}"

    return "\n".join(_HEADING.sub(bump, line) for line in markdown.splitlines())


def front_matter(title: str | None, source: str | None, fmt: str) -> str:
    lines = ["---"]
    if title:
        lines.append(f"title: {_yaml_string(title)}")
    if source:
        lines.append(f"source: {_yaml_string(source)}")
    lines.append(f"source_format: {fmt}")
    lines.append("---")
    return "\n".join(lines)


def _yaml_string(value: str) -> str:
    """YAML の単引用符で囲む。

    二重引用符だとバックスラッシュがエスケープとして解釈され、
    `C:\\temp` のようなパスが壊れる。単引用符の中は素の文字列で、
    `'` だけを 2 つ重ねて書けばよい。
    """
    return "'" + value.replace("\n", " ").replace("'", "''") + "'"


def notices_comment(notices: list[Notice]) -> str:
    lines = ["<!-- 変換時の注意"]
    for notice in notices:
        where = f" ({notice.location})" if notice.location else ""
        lines.append(f"  - [{notice.severity}]{where} {notice.message}")
    lines.append("-->")
    return "\n".join(lines)


def tidy(markdown: str) -> str:
    """空行の連続をならし、末尾を改行 1 つで終える（差分を安定させるため）。"""
    text = re.sub(r"\n{3,}", "\n\n", markdown.replace("\r\n", "\n"))
    return text.strip() + "\n"


def _get(lines: list[str], index: int) -> str:
    return lines[index] if 0 <= index < len(lines) else ""


def _normalise_extension(ext: str) -> str:
    lowered = ext.lower()
    return {"jpeg": "jpg", "svg+xml": "svg", "x-emf": "emf", "x-wmf": "wmf"}.get(lowered, lowered)
