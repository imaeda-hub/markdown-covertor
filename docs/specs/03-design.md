# 設計

## 1. 全体像

```
入力ファイル                                             出力
    │                                                    │
    ▼                                                    ▼
┌─────────┐   ┌──────────────┐   ┌────────┐   ┌──────────┐
│ registry │──▶│  コンバータ   │──▶│   IR   │──▶│ レンダラ  │
│ 形式判定  │   │ 形式ごとに 1 つ│   │中間表現 │   │ Markdown │
└─────────┘   └──────────────┘   └────────┘   └──────────┘
                      │                │
                 docx/xlsx/        Heading, Table,
                 pptx/pdf          ListBlock, ...
```

**要点は「IR を真ん中に挟む」こと。** これにより

- 出力書式を変えるとき、直すのはレンダラ 1 箇所だけ
- 新しい入力形式は、IR を作る関数を 1 つ書けば足りる
- テストが「文字列の一致」ではなく「構造の一致」で書ける
- 将来 GUI / HTML 出力 / JSON 出力を足しても、コンバータは無改造

## 2. ファイル構成

| パス | 役割 | 触る頻度 |
|---|---|---|
| `src/mdconv/model.py` | IR の定義（Heading, Table, Span …） | 低（追加のみ） |
| `src/mdconv/renderer.py` | IR → Markdown | 中 |
| `src/mdconv/registry.py` | 拡張子・中身から形式を判定 | 低 |
| `src/mdconv/api.py` | 公開 API（`convert_file`） | 低 |
| `src/mdconv/cli.py` | コマンドライン | 中 |
| `src/mdconv/ooxml.py` | Office 形式共通の ZIP/XML 読み取り | 低 |
| `src/mdconv/converters/*.py` | 形式ごとの解析 | **高** |
| `tests/fixtures.py` | テスト用の最小 Office ファイル生成 | 中 |
| `tests/test_docs_consistency.py` | 仕様書の健全性チェック（リンク・ID・テスト参照） | 低 |
| `tests/assets/` | 実ファイルの回帰テスト資産（本物の Office ファイルと、固定した出力） | 低 |
| `tools/build_fixtures.py` | `tests/assets/` の入力ファイルを作り直す開発用スクリプト | 低 |

ファイル構成を変えたら、**この表も一緒に直す**（ループ手順書 ⑦.5）。

## 3. 設計判断とその理由

判断を後から覆せるように、**「なぜそうしたか」と「見直す条件」**を書いておく。

### 3.1 Office 形式を外部ライブラリなしで読む

`.docx` / `.xlsx` / `.pptx` は「ZIP の中に XML」なので、`zipfile` + `ElementTree` だけで読める。

| 観点 | 判断 |
|---|---|
| 利点 | インストールが速い。依存の脆弱性・破壊的変更に振り回されない。挙動を完全に制御できる |
| 欠点 | 仕様の細部（結合セル、数式、図形）を自前で実装する必要がある |
| 見直す条件 | 自前実装の複雑さが `python-docx` 等の学習コストを上回ったとき |

### 3.2 PDF だけは追加依存（pypdf）

PDF は ZIP+XML ではなく独自のバイナリ構造で、自前実装は現実的でない。
ただし **PDF を使わない利用者に依存を強制しない**ため、追加インストール（`pip install 'mdconv[pdf]'`）にしている。

### 3.3 PDF の構造復元は「推測」だと明示する

PDF には見出し情報が無く、あるのは文字と座標だけ。
現在は「短くて句点で終わらない行は見出し」といったヒューリスティックで復元しており、
**外れることがある**。この限界は [変換ルール](05-conversion-rules.md#pdf) に明記する。

将来 Docling / Marker（レイアウト解析モデル）をプラグインとして差せるよう、
`registry.py` の対応表にエンジンを足せば切り替わる構造にしてある。

### 3.4 「失われた情報」を戻り値に載せる

変換は必ず情報を失う（画像、色、レイアウト）。
黙って落とすと利用者は気づけないので、`Document.notices` に記録して呼び出し側へ返す。
CLI は標準エラーに出し、`--include-notices` で Markdown 末尾にも残せる。

### 3.5 オプションは 1 つの `ConvertOptions` に集約

形式ごとにオプションの型を分けると、GUI から使うときに分岐が増える。
`ConvertOptions` に全部持たせ、各コンバータが受け取れるものだけを
シグネチャから拾って渡す（`api._kwargs_for`）。

## 4. データ構造（IR）

```
Document
├─ title, source_format, source_name
├─ blocks: [Block]
│   ├─ Heading(level, spans)
│   ├─ Paragraph(spans)
│   ├─ ListBlock(items: [ListItem(spans, level, ordered)])
│   ├─ Table(header, rows)      # 各セルは [Span]
│   ├─ CodeBlock(text, language)
│   ├─ Image(path, alt)
│   ├─ Callout(label, blocks)   # 引用・発表者ノート
│   └─ Divider()
├─ assets: [Asset(path, data)]  # 抽出した画像（path は本文の参照と同じ相対パス）
└─ notices: [Notice(message, severity)]
```

`Span` は「文字列 + 装飾（太字/斜体/コード/打消し/リンク先）」。
インライン装飾をこの 1 型に集約することで、レンダラ側の分岐を抑えている。

## 5. 拡張のしかた

### 新しい入力形式を足す

1. `src/mdconv/converters/<形式>.py` に `convert(path, **options) -> Document` を書く
2. `registry.py` の `FORMATS` に 1 行足す
3. `tests/fixtures.py` に最小ファイルの生成関数を足し、テストを書く

### 新しい出力形式を足す（将来）

`renderer.py` と同じ形（`render(doc, options) -> str`）のモジュールを足す。
コンバータ側は一切変更不要。

## 6. エラーの方針

| 例外 | いつ | CLI の挙動 |
|---|---|---|
| `UnsupportedFormatError` | 未対応の形式 | 終了コード 2、対応形式を提示 |
| `BrokenDocumentError` | ファイルが壊れている | 終了コード 1、そのファイルだけ飛ばす |
| `MissingDependencyError` | 追加依存が未インストール | インストールコマンドを提示 |

**スタックトレースを利用者に見せない**こと。原因と次の行動が分かる日本語にする。

## 7. テスト方針

テストは**二層**になっている。片方だけでは守れないものがある。

| 層 | 何を確かめるか | 置き場所 |
|---|---|---|
| 手書き XML | 「この XML をこう読む」という仕様。テストを読めば挙動が分かる | `tests/fixtures.py` + 各 `test_*.py` |
| 実ファイル | 本物の Office が吐く構造で壊れないこと。**想定外を検出する** | `tests/assets/` + `test_real_files.py` |

手書き XML は自分の想定しか書けないので、想定外は見つけられない。
実際、実ファイル層を入れた初日に「スタイル側に番号定義がある箇条書き」の
取りこぼし（FR-216）が見つかった。逆に実ファイルだけでは、
どの XML 構造が原因で壊れたのかが分からない。**両方いる。**

- **完全一致で比較する**: 出力の安定性（NFR-01）を守るため、部分一致は避ける。
- **1 テスト 1 事実**: 落ちたテスト名だけで壊れた仕様が分かるようにする。
- 実ファイルの期待値は `UPDATE_GOLDEN=1 pytest` で更新できるが、
  **差分を必ず目で確認する**（更新は「仕様が変わった」という宣言になる）。
