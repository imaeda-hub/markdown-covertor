# 実世界のテスト資料

**このフォルダのファイルは第三者が作成したものです。編集しないでください。**

自分で作ったきれいなファイルだけでテストすると、「動くことの確認」にしかならない。
実際の資料には、図・グラフ・SmartArt・グループ化された図形・スキャン画像・
罫線のない表など、想定していない構造が入っている。それを持ち込むためのフォルダ。

## 出どころとライセンス

| ファイル | 何が入っているか |
|---|---|
| `test.docx` | 実際の論文（AutoGen）。見出し階層・表・画像・長文 |
| `test.xlsx` | 複数シート・数百行の数値表 |
| `test.pptx` | **グラフ・グループ図形・画像**を含むスライド（SmartArt は入っていない） |
| `test.pdf` | 論文 PDF（2 段組み・数式・参考文献） |
| `SPARSE-2024-INV-1234_borderless_table.pdf` | **罫線のない表**を含む帳票 PDF |
| `MEDRPT-2024-PAT-3847_medical_report_scan.pdf` | **スキャン画像の PDF**（テキスト層なし） |

すべて [microsoft/markitdown](https://github.com/microsoft/markitdown) の
テスト資料（`packages/markitdown/tests/test_files/`）から取得。
MIT License, Copyright (c) Microsoft Corporation。
ライセンス全文は [`LICENSE-markitdown.txt`](LICENSE-markitdown.txt)。

## 期待値の持ち方

これらは大きいので、変換結果の全文を貼ると人間がレビューできない。
代わりに `expected/<ファイル名>.summary.md` に**要約**を固定している。

- **ハッシュ**で全文の完全一致を担保する（1 文字変わればテストが落ちる）
- **要約**（見出し一覧・表の形・警告）で、落ちたときに何が変わったか読んで分かる

期待値の更新は `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_real_world.py`。
**差分を必ず目で確認すること。** 更新は「仕様が変わった」という宣言になる。
