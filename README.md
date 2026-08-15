# mdconv

Word / Excel / PowerPoint / PDF の資料を、読みやすい **Markdown** に変換するツール。

- 🚀 **すぐ動く** — Office 形式はモデルのダウンロードも外部依存もなし
- 🔒 **手元で完結** — 既定でネットワーク通信を一切しない（社内資料を扱う前提）
- 🧾 **落ちた情報を隠さない** — 変換で失われた画像・非表示シートなどは警告で伝える
- 🧩 **構造を保つ** — 見出し・表・箇条書き・リンクを保ったまま変換

## インストール

```bash
pip install -e .          # Word / Excel / PowerPoint
pip install -e ".[pdf]"   # PDF も使う場合
```

## 使い方

```bash
mdconv 資料.docx                      # 標準出力へ
mdconv 資料.docx -o 資料.md            # ファイルへ
mdconv 資料/ -o out/ --recursive      # ディレクトリ一括
mdconv 資料.docx --extract-images     # 画像も assets/ に書き出す
mdconv 見積.xlsx --include-hidden     # 非表示シートも含める
mdconv 提案.pptx --no-notes           # 発表者ノートを除く
```

Python からも使える。

```python
from mdconv import convert_file

result = convert_file("資料.docx")
print(result.markdown)
for notice in result.notices:
    print("落ちた情報:", notice.message)
```

主なオプション:

| オプション | 効果 |
|---|---|
| `-o, --output` | 出力先ファイル／ディレクトリ |
| `-r, --recursive` | ディレクトリを再帰的に探索 |
| `--extract-images` | 画像を `assets/` に書き出す |
| `--front-matter` | YAML フロントマター（タイトル・元ファイル名）を付ける |
| `--include-notices` | 変換時の警告を Markdown 末尾のコメントに残す |
| `--heading-offset N` | 見出しレベルを N 段下げる |
| `--overwrite` | 既存ファイルを上書きする |

全オプションは `mdconv --help`、変換結果の詳細は
**[変換ルール一覧](docs/specs/05-conversion-rules.md)** を参照。

## 対応状況

| 形式 | 状態 | 得意 | 苦手 |
|---|---|---|---|
| Word (.docx) | ✅ | 見出し・表・リスト・リンク | 数式・脚注・図形 |
| Excel (.xlsx) | ✅ | シート・数式の値・空セル位置 | 結合セル・グラフ |
| PowerPoint (.pptx) | ✅ | タイトル・箇条書き・発表者ノート | 画像・図形の位置関係 |
| PDF | ✅ | 段落の復元・箇条書き | 表・段組み・スキャン画像 |

旧バイナリ形式（.doc / .xls / .ppt）は未対応。Office で新形式に保存し直してください。

## 開発

このリポジトリは **仕様駆動開発（SDD）+ 自律ループ**で開発している。

- 仕様を先に書き、コードは仕様に従う（仕様とコードが食い違ったら**仕様が正**）
- AI が毎晩 0:00 JST に「調査 → 仕様更新 → 実装 → テスト → **AI レビュー** → 記録」を 1 周回し、`main` を更新する
- 人間は好きなタイミングで仕様をレビューし、[`docs/feedback/INBOX.md`](docs/feedback/INBOX.md) に指摘を書く

詳細は **[ドキュメントの地図](docs/README.md)** から。

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,pdf]"
.venv/bin/pytest        # テスト
.venv/bin/ruff check .  # lint
```
