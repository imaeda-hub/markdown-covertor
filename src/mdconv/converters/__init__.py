"""フォーマット別コンバータ。

新しい形式を足すときは
  1. このパッケージに `<format>.py` を作り `convert(path, **options) -> Document` を実装
  2. registry.py の FORMATS に 1 行追加
の 2 ステップで済むようにしてある。
"""
