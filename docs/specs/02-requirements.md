# 要件

各要件は **ID / 状態 / 内容 / 確認方法** の 4 点セットで書く。
「確認方法」は実際のテスト関数名なので、**仕様と実装のズレはテストを見れば分かる**。

状態の記号: ✅ 実装済 ／ 🚧 作業中 ／ 📋 未着手 ／ ❄️ 保留

---

## 1. 変換の基本（FR-1xx）

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-101 | ✅ | 利用者が .docx を指定したとき、システムは Markdown を出力する | `test_docx.py` |
| FR-102 | ✅ | 利用者が .xlsx を指定したとき、システムは Markdown を出力する | `test_xlsx.py` |
| FR-103 | ✅ | 利用者が .pptx を指定したとき、システムは Markdown を出力する | `test_pptx.py` |
| FR-104 | ✅ | 利用者が .pdf を指定したとき、システムは Markdown を出力する | `test_pdf.py` |
| FR-105 | ✅ | 拡張子が実際の形式と食い違う場合、システムは中身を見て形式を判定する | `test_detect_by_content_when_extension_is_wrong` |
| FR-106 | ✅ | 旧バイナリ形式（.doc 等）が渡された場合、システムは「新形式で保存し直す」よう案内する | `test_legacy_binary_format_has_dedicated_message` |
| FR-107 | ✅ | 未対応の形式が渡された場合、システムは対応形式の一覧を添えて拒否する | `test_unknown_extension_raises` |

## 2. 構造の保存（FR-2xx）

Markdown への写像規則の詳細は [05-変換ルール](05-conversion-rules.md) を参照。

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-201 | ✅ | 見出しスタイルの段落は、対応する階層の Markdown 見出しになる | `test_headings_and_paragraph` |
| FR-202 | ✅ | 箇条書き・番号付きリストは、入れ子の深さを保って変換される | `test_bullet_list_is_grouped_into_one_block` |
| FR-203 | ✅ | Word / PowerPoint の表は GFM の表になり、1 行目をヘッダとして扱う | `test_table_first_row_is_header` |
| FR-204 | ✅ | 太字・斜体・打消し線は対応する記法になる | `test_run_decorations` |
| FR-205 | ✅ | ハイパーリンクはリンク先を保ったまま変換される | `test_hyperlink_resolves_relationship` |
| FR-206 | ✅ | 本文中の記号（`*` `_` `[` 等）はエスケープされ、意図しない装飾にならない | `test_special_characters_are_escaped` |
| FR-207 | ✅ | Excel の各シートは「見出し + 表」になり、ブックの順序を保つ | `test_multiple_sheets_keep_workbook_order` |
| FR-208 | ✅ | PowerPoint の各スライドは「見出し + 本文」になり、区切り線で分かれる | `test_slides_are_separated_by_divider` |
| FR-209 | ✅ | PowerPoint の発表者ノートは引用ブロックとして出力される | `test_speaker_notes_become_callout` |
| FR-210 | ✅ | PDF の折り返された行は 1 つの段落に戻される（和文は詰め、英文は空白で連結） | `test_wrapped_japanese_lines_are_joined_without_space` |
| FR-211 | 📋 | Word の脚注・コメントは本文末尾に集約して出力される | 未 |
| FR-212 | 📋 | Word の数式は LaTeX 記法（`$...$`）に変換される | 未 |
| FR-213 | 📋 | 表の結合セルは、値を複製せず結合の事実が分かる形で出力される | 未 |
| FR-214 | ✅ | Excel の見出し行は自動判定する（1 行目固定にしない） | `test_first_row_containing_a_number_is_not_a_header` |
| FR-215 | ✅ | Word の表題は本文の見出しにせず、文書のタイトルとして保持する | `test_title_style_is_not_a_heading` |
| FR-216 | ✅ | 段落ではなくスタイル側に番号定義がある箇条書きも、リストとして復元する | `test_list_style_without_paragraph_numbering` |

## 3. 失われる情報の扱い（FR-3xx）

「消えたことに気づけない」のが最悪の失敗なので、独立した節にしている。

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-301 | ✅ | 画像を出力しない設定のとき、システムは画像を省いた旨を警告として報告する | `test_image_is_reported_when_extraction_is_off` |
| FR-302 | ✅ | システムは既定で画像を `assets/` に書き出し、参照を張る | `test_image_is_extracted_by_default` |
| FR-303 | ✅ | 非表示シートは既定で除外し、除外した事実を警告として報告する | `test_hidden_sheet_is_excluded_by_default` |
| FR-304 | ✅ | テキストを持たない PDF ページがあるとき、スキャン画像の可能性を警告する | `test_empty_pdf_reports_no_text` |
| FR-305 | ✅ | 利用者が指定したとき、警告を出力 Markdown の末尾にコメントとして残せる | `test_notices_are_optional` |
| FR-306 | 📋 | 図形・グラフ・SmartArt を検出したとき、その存在を警告として報告する | 未 |
| FR-307 | ✅ | 標準出力へ変換するとき、画像の置き場所がないため書き出しを止めて警告する | `test_stdout_cannot_hold_images_so_extraction_is_disabled` |
| FR-308 | ✅ | 表題を本文から省いたとき、その旨を警告として報告する | `test_title_style_is_not_a_heading` |

## 4. コマンドライン（FR-4xx）

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-401 | ✅ | 出力先を指定しないとき、結果は標準出力に書かれる（パイプで繋げる） | `test_stdout_output` |
| FR-402 | ✅ | `-o` でファイルを指定したとき、そのファイルに書き出す | `test_file_output` |
| FR-403 | ✅ | ディレクトリを指定したとき、対応形式のファイルをすべて変換する | `test_directory_input_writes_one_file_per_document` |
| FR-404 | ✅ | 出力先が既に存在するとき、`--overwrite` がなければ上書きせずスキップする | `test_existing_file_is_not_overwritten_without_flag` |
| FR-405 | ✅ | 複数ファイルを標準出力に混ぜようとしたとき、使い方の誤りとして拒否する | `test_multiple_inputs_without_output_is_a_usage_error` |
| FR-406 | ✅ | 一部のファイルが失敗しても、残りの変換は続行し、終了コードで失敗を伝える | `test_broken_file_returns_error_code` |
| FR-407 | 📋 | 変換の進捗をファイル数つきで表示する（大量変換時） | 未 |

**終了コード**: `0` 成功 ／ `1` 変換失敗あり ／ `2` 使い方の誤り

## 5. 品質特性（NFR）

| ID | 状態 | 要件 | 測り方 |
|---|---|---|---|
| NFR-01 | ✅ | 同じ入力からは常に同じ出力になる（Git 差分が意味を持つ） | `test_conversion_is_deterministic` |
| NFR-07 | ✅ | 本物の Office ファイルの変換結果を固定し、退行を検出する | `test_real_file_conversion_is_frozen` |
| NFR-02 | ✅ | コア機能は Python 標準ライブラリのみで動く（PDF のみ追加依存） | `pyproject.toml` の `dependencies` が空 |
| NFR-03 | ✅ | 既定の動作でネットワーク通信を行わない | 外部通信コードを持たない |
| NFR-04 | ✅ | 壊れたファイルでもスタックトレースを出さず、原因の分かる日本語メッセージを返す | `test_broken_file_returns_error_code` |
| NFR-05 | 📋 | 10MB の .docx を 3 秒以内に変換する | ベンチマーク未整備 |
| NFR-06 | 📋 | 巨大な .xlsx でメモリを使い切らない（ストリーミング処理） | 未 |

## 6. 用語

| 用語 | 意味 |
|---|---|
| IR（中間表現） | 入力形式にも出力形式にも依存しない、文書構造のデータ。`src/mdconv/model.py` |
| コンバータ | 「入力ファイル → IR」を担当する部品。形式ごとに 1 つ |
| レンダラ | 「IR → Markdown 文字列」を担当する部品。全形式で共有 |
| 警告（Notice） | 変換で失われた情報の記録。エラーではなく、利用者への申告 |
| GFM | GitHub Flavored Markdown。表やチェックボックスを含む方言 |
