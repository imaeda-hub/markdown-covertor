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
    out.add_argument(
        "--no-images",
        action="store_true",
        help="画像を書き出さない（既定は出力先の assets/ に書き出す）",
    )

    fmt = parser.add_argument_group("形式ごとの調整")
    fmt.add_argument("--include-hidden", action="store_true", help="[xlsx] 非表示シートも出力")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = _options(args)
    # 標準出力に書く場合、画像の置き場所が決まらないので書き出しを止める
    if args.output is None:
        options.extract_images = False

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

    destinations = {} if to_stdout else _destinations(targets, args.output, len(targets) > 1)

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

        destination = destinations[target]
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
        extract_images=not args.no_images,
        include_hidden=args.include_hidden,
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


def _destinations(targets: list[Path], output: Path, multiple: bool) -> dict[Path, Path]:
    """全入力ぶんの出力先をまとめて決める。

    `資料.docx` と `資料.xlsx` のように**拡張子違いで stem が同じ**ファイルは、
    素直に `{stem}.md` にすると出力先が衝突し、片方が黙って消える（T-23）。
    衝突する組だけ、元の拡張子を残した `{名前}.md`（例: `資料.docx.md`）にして避ける。

    `--recursive` で `a/報告.docx` と `b/報告.docx` のように**フォルダ違いで
    名前も拡張子も同じ**ファイルは、拡張子を残しても `報告.docx.md` のまま
    衝突する（T-34）。この場合だけ、確実に分けるため連番を付ける。
    """
    if not multiple and output.suffix != "" and not output.is_dir():
        return {targets[0]: output}

    stems = [_destination(t, output, True) for t in targets]
    collisions = {d for d in stems if stems.count(d) > 1}
    result: dict[Path, Path] = {}
    used: set[Path] = set()
    for target, plain in zip(targets, stems, strict=True):
        candidate = output / f"{target.name}.md" if plain in collisions else plain
        if candidate in used:
            n = 2
            while output / f"{target.name}-{n}.md" in used:
                n += 1
            candidate = output / f"{target.name}-{n}.md"
        used.add(candidate)
        result[target] = candidate
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
