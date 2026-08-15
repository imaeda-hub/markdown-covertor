"""コマンドラインインタフェース。

mdconv 資料.docx                  # 標準出力へ
mdconv 資料.docx -o 資料.md        # ファイルへ
mdconv docs/ -o out/ --recursive  # ディレクトリ一括
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .api import ConvertOptions, convert_file
from .errors import MdconvError
from .registry import FORMATS, SUPPORTED_EXTENSIONS

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdconv",
        description="Word / Excel / PowerPoint / PDF の資料を Markdown に変換します。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="対応形式:\n"
        + "\n".join(
            f"  {f.name:5s} {', '.join(f.extensions):16s} {f.description}" for f in FORMATS
        ),
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="変換するファイルまたはディレクトリ")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力先。入力が複数またはディレクトリの場合は出力ディレクトリとして扱う",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="ディレクトリを再帰的に探索")
    parser.add_argument("-f", "--format", help="形式を明示指定 (docx/xlsx/pptx/pdf)")
    parser.add_argument("--overwrite", action="store_true", help="既存ファイルを上書きする")
    parser.add_argument("-q", "--quiet", action="store_true", help="警告を表示しない")
    parser.add_argument("--version", action="version", version=f"mdconv {__version__}")

    out = parser.add_argument_group("出力の調整")
    out.add_argument("--heading-offset", type=int, default=0, help="見出しレベルを下げる量")
    out.add_argument("--front-matter", action="store_true", help="YAML フロントマターを付ける")
    out.add_argument(
        "--include-notices", action="store_true", help="変換時の警告を末尾のコメントに残す"
    )
    out.add_argument("--extract-images", action="store_true", help="画像を assets/ に書き出す")

    fmt = parser.add_argument_group("形式ごとの調整")
    fmt.add_argument("--include-hidden", action="store_true", help="[xlsx] 非表示シートも出力")
    fmt.add_argument("--max-rows", type=int, help="[xlsx] 1 シートあたりの最大行数")
    fmt.add_argument("--no-notes", action="store_true", help="[pptx] 発表者ノートを出力しない")
    fmt.add_argument("--page-headings", action="store_true", help="[pdf] ページ番号を見出しにする")
    fmt.add_argument(
        "--no-page-dividers", action="store_true", help="[pdf/pptx] 区切り線を入れない"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = _options(args)

    try:
        targets = _collect(args.inputs, recursive=args.recursive)
    except MdconvError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not targets:
        print("変換対象が見つかりませんでした", file=sys.stderr)
        return EXIT_USAGE

    to_stdout = args.output is None
    if to_stdout and len(targets) > 1:
        print(
            "複数ファイルを変換する場合は -o で出力先ディレクトリを指定してください",
            file=sys.stderr,
        )
        return EXIT_USAGE

    failures = 0
    for target in targets:
        try:
            result = convert_file(target, options=options, format=args.format)
        except (MdconvError, FileNotFoundError) as exc:
            print(f"[失敗] {target}: {exc}", file=sys.stderr)
            failures += 1
            continue

        if not args.quiet:
            for notice in result.notices:
                print(f"[注意] {target.name}: {notice.message}", file=sys.stderr)

        if to_stdout:
            sys.stdout.write(result.markdown)
            continue

        destination = _destination(target, args.output, len(targets) > 1)
        if destination.exists() and not args.overwrite:
            print(
                f"[スキップ] {destination} は既に存在します（--overwrite で上書き）",
                file=sys.stderr,
            )
            continue
        result.write(destination)
        if not args.quiet:
            print(f"[完了] {target} -> {destination}", file=sys.stderr)

    return EXIT_ERROR if failures else EXIT_OK


def _options(args: argparse.Namespace) -> ConvertOptions:
    return ConvertOptions(
        heading_offset=args.heading_offset,
        front_matter=args.front_matter,
        include_notices=args.include_notices,
        extract_images=args.extract_images,
        include_hidden=args.include_hidden,
        max_rows=args.max_rows,
        include_notes=not args.no_notes,
        slide_dividers=not args.no_page_dividers,
        page_dividers=not args.no_page_dividers,
        page_headings=args.page_headings,
    )


def _collect(inputs: list[Path], *, recursive: bool) -> list[Path]:
    targets: list[Path] = []
    for item in inputs:
        if item.is_dir():
            pattern = "**/*" if recursive else "*"
            targets.extend(
                sorted(
                    p
                    for p in item.glob(pattern)
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
                )
            )
        elif item.exists():
            targets.append(item)
        else:
            print(f"[警告] 見つかりません: {item}", file=sys.stderr)
    # 同じファイルを 2 回変換しない
    seen: set[Path] = set()
    unique: list[Path] = []
    for target in targets:
        resolved = target.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(target)
    return unique


def _destination(source: Path, output: Path, multiple: bool) -> Path:
    """出力先を決める。複数入力や既存ディレクトリ指定ならその配下に .md を作る。"""
    if multiple or output.is_dir() or output.suffix == "":
        return output / f"{source.stem}.md"
    return output


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
