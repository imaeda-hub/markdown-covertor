"""公開 API。CLI も GUI も将来のサーバもここだけを呼ぶ。

    from mdconv import convert_file
    result = convert_file("資料.docx")
    print(result.markdown)
    for notice in result.notices:
        print("落ちた情報:", notice.message)

変換の流れ:

    ①形式判定 → ②markitdown で変換 → ③元ファイルを検査 → ④出力を整える
     registry     engine              inspection        postprocess

②が本体、③④が**markitdown だけでは足りない部分の補完**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import engine, media, postprocess
from .inspection import inspect
from .ooxml import docx_list_levels, pptx_list_levels
from .registry import detect
from .types import Asset, Notice


@dataclass(slots=True)
class ConvertOptions:
    """変換の挙動。"""

    heading_offset: int = 0
    front_matter: bool = False
    include_notices: bool = False

    extract_images: bool = True
    """画像を assets/ に書き出して参照を張る。False なら本文から取り除く。"""

    include_hidden: bool = False
    """Excel の非表示シートも出力する。既定は落とす（情報漏洩を避けるため）。"""


@dataclass(slots=True)
class ConvertResult:
    markdown: str
    source: Path
    format: str
    title: str | None = None
    notices: list[Notice] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)

    def write(self, destination: str | Path) -> Path:
        """Markdown を書き出す。画像は本文の参照と同じ相対パスに置く。"""
        out = Path(destination)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.markdown, encoding="utf-8")
        for asset in self.assets:
            target = out.parent / asset.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(asset.data)
        return out


def convert_file(
    path: str | Path,
    *,
    options: ConvertOptions | None = None,
    format: str | None = None,
) -> ConvertResult:
    """1 ファイルを Markdown に変換する。"""
    opts = options or ConvertOptions()
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"ファイルがありません: {source}")

    fmt = detect(source, explicit=format)
    markdown, engine_title = engine.convert(source)
    found = inspect(source, fmt.name, markdown)
    found.format = fmt.name

    markdown, assets = _apply(markdown, found, opts, source)
    title = found.title or engine_title
    notices = list(found.notices)

    if opts.front_matter:
        markdown = postprocess.front_matter(title, source.name, fmt.name) + "\n\n" + markdown
    if opts.include_notices and notices:
        markdown = markdown + "\n\n" + postprocess.notices_comment(notices)

    return ConvertResult(
        markdown=postprocess.tidy(markdown),
        source=source,
        format=fmt.name,
        title=title,
        notices=notices,
        assets=assets,
    )


def _apply(markdown, found, opts: ConvertOptions, source: Path):
    """本文への補正をまとめて適用する。順序に意味があるので 1 か所に集める。"""
    # 非表示シートは真っ先に落とす。以降の処理で中身が混ざらないように
    if found.hidden_sheets and not opts.include_hidden:
        markdown = postprocess.drop_sections(markdown, found.hidden_sheets)
        names = "、".join(found.hidden_sheets)
        found.warn(f"非表示シート「{names}」を除外しました（--include-hidden で出力）")

    if found.format == "pptx":
        # グラフの表と直後の図形の表が改行なしで連結されることがある（T-37）。
        # 後続の表の補正が正しい行境界を見られるよう、他の表補正より先に直す
        markdown = postprocess.split_merged_table_rows(markdown)

    markdown = postprocess.clean_tables(markdown)
    markdown = postprocess.promote_empty_table_header(markdown)
    if found.format == "xlsx":
        # 桁揃えは pandas 経由で Excel を読むときだけ起きる現象。
        # Word の表はセルの文字列をそのまま出すので、"100.00" のような
        # 意図した表記まで壊してしまう（AI レビューで発見）
        markdown = postprocess.fix_number_padding(markdown)

    if found.format == "docx":
        items = docx_list_levels(str(source))
        markdown, nested = postprocess.nest_lists(markdown, items)
        if not nested and any(level > 0 for level, _ in items):
            # 元ファイルに入れ子があるのに直せなかった。黙って崩れたままにしない
            found.warn("箇条書きの入れ子を復元できませんでした（本文との対応が取れないため）")

    if found.format == "pptx":
        items = pptx_list_levels(str(source))
        markdown, bulleted = postprocess.add_pptx_bullets(markdown, items)
        if not bulleted and items:
            # 本文プレースホルダーがあるのに記号を付けられなかった。黙って平文のままにしない
            found.warn("箇条書きの記号を復元できませんでした（本文との対応が取れないため）")

    assets: list[Asset] = []
    if opts.extract_images:
        images = media.ordered_images(source, found.format)
        markdown, assets, unmatched = postprocess.place_images(
            markdown, images, f"assets/{source.stem}"
        )
        if unmatched:
            # Word 以外は markitdown が図形名で参照するだけなので実体に辿り着けない
            reason = "（この形式では実体を取り出せません）" if found.format != "docx" else ""
            found.warn(f"画像を {unmatched} 個出力していません{reason}")
    else:
        markdown, dropped = postprocess.drop_images(markdown)
        if dropped:
            found.warn(f"画像を {dropped} 個出力していません")

    return postprocess.shift_headings(markdown, opts.heading_offset), assets
