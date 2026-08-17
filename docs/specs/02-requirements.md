# 要件

各要件は **ID / 状態 / 内容 / 確認方法** の 4 点セットで書く。
「確認方法」は実際のテスト関数名なので、**仕様と実装のズレはテストを見れば分かる**。

状態の記号: ✅ 実装済 ／ 🚧 作業中 ／ 📋 未着手 ／ ❄️ 保留

> **v0.2 で変換の本体が markitdown になった。**
> 「できること」の多くは markitdown が担い、このツールは**その不足を補う**。
> どこまでが markitdown の担当かは [03-設計](03-design.md) を参照。

---

## 1. 変換の基本（FR-1xx）

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-101 | ✅ | 利用者が .docx を指定したとき、システムは Markdown を出力する | `test_docx_headings_and_text` |
| FR-102 | ✅ | 利用者が .xlsx を指定したとき、システムは Markdown を出力する | `test_xlsx_sheets_become_sections` |
| FR-103 | ✅ | 利用者が .pptx を指定したとき、システムは Markdown を出力する | `test_passing_document_keeps_its_text` |
| FR-104 | ✅ | 利用者が .pdf を指定したとき、システムは Markdown を出力する | `test_passing_document_keeps_its_text` |
| FR-105 | ✅ | 拡張子が実際の形式と食い違う場合、システムは中身を見て形式を判定する | `test_detect_by_content_when_extension_is_wrong` |
| FR-106 | ✅ | 旧バイナリ形式（.doc 等）が渡された場合、システムは「新形式で保存し直す」よう案内する | `test_legacy_binary_format_has_dedicated_message` |
| FR-107 | ✅ | 未対応の形式が渡された場合、システムは対応形式の一覧を添えて拒否する | `test_unknown_extension_raises` |

## 2. 構造の保存（FR-2xx）

入出力の対応は [05-変換ルール](05-conversion-rules.md) に実例つきでまとめてある。
**markitdown が担当する部分は、そこで「エンジン依存」と明記している。**

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-201 | ✅ | 見出しスタイルの段落は、対応する階層の Markdown 見出しになる | `test_docx_headings_and_text` |
| FR-203 | ✅ | 表は GFM の表になる | `test_xlsx_sheets_become_sections` |
| FR-207 | ✅ | Excel の各シートは「見出し + 表」になる | `test_xlsx_sheets_become_sections` |
| FR-218 | ✅ | Word の表が空ヘッダで出たとき、1 行目を見出しに繰り上げる | `test_empty_header_is_replaced_by_the_first_row` |
| FR-219 | ✅ | Excel の空セルが `NaN` として出るのを、空欄に戻す | `test_nan_cells_become_empty` |
| FR-220 | ✅ | PDF の罫線がない表も、表として復元される（v0.2 で改善） | `test_borderless_table_pdf_is_restored_as_a_table` |
| FR-202 | ✅ | Word の箇条書きの入れ子の深さを保つ（元ファイルのスタイル名から復元） | `test_docx_nested_bullets_keep_their_level` |
| FR-223 | ✅ | Word の番号付きリストは、入れ子にしたとき番号も振り直す | `test_docx_nested_numbered_list_renumbers_by_level` |
| FR-222 | ✅ | PowerPoint の箇条書きに記号と階層を付ける | `test_pptx_bullets_get_symbols_and_levels` |
| FR-221 | ➖ | Word の引用スタイルを `>` にする | **対応しない**（Q-07 決定）。読めれば実害小さいと判断 |
| FR-215 | ➖ | Word の表題を文書のタイトルとして扱う | **対応しない**（Q-07 決定）。読めれば実害小さいと判断 |
| FR-211 | 📋 | Word の脚注・コメントは本文末尾に集約して出力される | 未 |
| FR-213 | 📋 | 表の結合セルは、値を複製せず結合の事実が分かる形で出力される | 未 |
| FR-224 | ✅ | Excel の数値は、同じ列に精度の高い値があっても桁を揃えられない（元の値のまま出す） | `test_xlsx_number_padding_is_restored_to_the_original_value` |
| FR-225 | ✅ | PowerPoint のグラフの表の直後に別の図形の表が続いても、両方とも壊れず GFM の表になる | `test_split_merged_table_rows_separates_chart_and_next_table` |

## 3. 失われる情報の扱い（FR-3xx）

**markitdown は何も報告しない。この節はすべて自前の補完。**
「消えたことに気づけない」のが最悪の失敗なので、独立した節にしている。

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-301 | ✅ | 画像を出力しない設定のとき、システムは画像を省いた旨を警告として報告する | `test_images_can_be_turned_off` |
| FR-302 | ✅ | システムは既定で画像を `assets/` に書き出し、参照を張る | `test_image_is_written_next_to_the_markdown` |
| FR-303 | ✅ | 非表示シートは既定で**中身ごと除外**し、除外した事実を警告として報告する | `test_hidden_sheet_is_removed_and_reported` |
| FR-304 | ✅ | 文字を取り出せない PDF は、スキャン画像の可能性を警告する | `test_scanned_pdf_is_reported_as_having_no_text` |
| FR-305 | ✅ | 利用者が指定したとき、警告を出力 Markdown の末尾にコメントとして残せる | `test_notices_can_be_embedded` |
| FR-306 | ✅ | グラフ・SmartArt・テキストボックスを検出したとき、その存在を警告として報告する | `test_chart_is_reported` |
| FR-310 | ✅ | 同じ図表を二重に数えない（mc:Choice と mc:Fallback の重複） | `test_the_same_graphic_is_not_counted_twice` |
| FR-311 | ✅ | 画像の実体を対応づけられない形式では、枚数を警告として報告する | `test_powerpoint_reports_chart_and_image_it_cannot_render` |
| FR-307 | ✅ | 標準出力へ変換するとき、画像の置き場所がないため書き出しを止めて警告する | `test_stdout_cannot_hold_images_so_extraction_is_disabled` |

## 4. コマンドライン（FR-4xx）

| ID | 状態 | 要件 | 確認方法 |
|---|---|---|---|
| FR-401 | ✅ | 出力先を指定しないとき、結果は標準出力に書かれる（パイプで繋げる） | `test_stdout_output` |
| FR-402 | ✅ | `-o` でファイルを指定したとき、そのファイルに書き出す | `test_file_output` |
| FR-403 | ✅ | ディレクトリを指定したとき、対応形式のファイルをすべて変換する | `test_directory_input_writes_one_file_per_document` |
| FR-404 | ✅ | 出力先が既に存在するとき、`--overwrite` がなければ上書きせずスキップする | `test_existing_file_is_not_overwritten_without_flag` |
| FR-405 | ✅ | 複数ファイルを標準出力に混ぜようとしたとき、使い方の誤りとして拒否する | `test_multiple_inputs_without_output_is_a_usage_error` |
| FR-406 | ✅ | 一部のファイルが失敗しても、残りの変換は続行し、終了コードで失敗を伝える | `test_broken_file_returns_error_code` |
| FR-408 | ✅ | 一括変換で、文書ごとに画像の置き場所を分ける | `test_images_of_different_documents_do_not_collide` |
| FR-409 | ✅ | 同名の資料（拡張子違い・`--recursive` でのフォルダ違いを含む）を一括変換しても、出力ファイル名が衝突しない | `test_same_name_same_format_in_different_folders_do_not_collide` |
| FR-407 | 📋 | 変換の進捗をファイル数つきで表示する（大量変換時） | 未 |

**終了コード**: `0` 成功 ／ `1` 変換失敗あり ／ `2` 使い方の誤り

## 5. 品質特性（NFR）

| ID | 状態 | 要件 | 測り方 |
|---|---|---|---|
| NFR-01 | ✅ | 同じ入力からは常に同じ出力になる（Git 差分が意味を持つ） | `test_conversion_is_deterministic` |
| NFR-03 | ✅ | 既定の動作でネットワーク通信を行わない | markitdown のプラグインを無効化して使う |
| NFR-04 | ✅ | 変換に失敗してもスタックトレースを出さず、原因の分かる日本語を返す | `test_broken_file_raises_a_readable_error` |
| NFR-08 | ✅ | 実資料を通ったもの／通らなかったものに分けて残す | `test_passing_document_output_is_frozen` |
| NFR-09 | ✅ | 通らなかった資料でも説明できない例外で落ちない | `test_failing_document_fails_gracefully` |
| NFR-10 | ✅ | 通らなかった資料の**壊れ方**も固定し、静かな悪化を検出する | `test_failing_document_output_is_frozen` |
| NFR-11 | ✅ | 通った資料の**変換後 Markdown そのもの**を保存し、実物を確認できる | `test_passing_document_converted_file_is_stored` |
| NFR-02 | ❄️ | ~~コア機能は標準ライブラリのみで動く~~ | **v0.2 で放棄**。markitdown に依存する（本人合意） |
| NFR-05 | 📋 | 10MB の .docx を 3 秒以内に変換する | ベンチマーク未整備（T-10） |
| NFR-06 | 📋 | 巨大な .xlsx でメモリを使い切らない | 未 |

## 6. 用語

| 用語 | 意味 |
|---|---|
| エンジン | 変換の本体。現在は markitdown。`src/mdconv/engine.py` が唯一の接点 |
| 検査（Inspection） | 元ファイルを開いて「出力に現れないもの」を数える処理 |
| 補正（Postprocess） | エンジンの出力を実用に耐える Markdown に整える処理 |
| 警告（Notice） | 変換で失われた情報の記録。エラーではなく、利用者への申告 |
| 検体（Corpus） | 実資料でのテスト。`tests/corpus/` の inbox / passing / failing |
| GFM | GitHub Flavored Markdown。表やチェックボックスを含む方言 |
