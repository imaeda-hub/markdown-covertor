"""元ファイルから画像の実体を取り出す。

markitdown は画像を `![alt](data:image/png;base64...)` という**プレースホルダ**で出す。
中身が入っていないので、そのままでは画像が失われる。
そこで元ファイル（OOXML の ZIP）から実体を取り出し、
出現順にプレースホルダと突き合わせて置き換える。

順番で対応づけるのは、プレースホルダ側に「どの画像か」を示す情報が無いため。
本文中の出現順と、document.xml が画像を参照する順は一致する。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .errors import MdconvError
from .ooxml import OoxmlPackage, attr, q

# 形式ごとの「本文パート」と、その rels を辿って画像を集める設定
_BODY_PART = {"docx": "word/document.xml"}


def ordered_images(path: Path, fmt: str) -> list[tuple[str, bytes]]:
    """本文に現れる順で (ファイル名, 中身) を返す。取り出せなければ空。

    現状は Word のみ。PowerPoint / Excel は markitdown が画像を
    データ URI ではなく図形名で参照するため、実体と対応づけられない（T-24）。
    """
    part = _BODY_PART.get(fmt)
    if part is None:
        return []
    try:
        with OoxmlPackage(str(path)) as pkg:
            rels = pkg.rels(part)
            out: list[tuple[str, bytes]] = []
            for blip in pkg.xml(part).iter(q("a", "blip")):
                target = rels.get(attr(blip, "r", "embed") or "")
                if not target or not pkg.has(target):
                    continue
                # 同じ画像が 2 回出てもここでは間引かない。
                # 本文のプレースホルダと**順番で**対応づけるため、数が合わなくなる。
                # 実ファイルの重複は place_images が内容ハッシュでまとめる
                out.append((target.rsplit("/", 1)[-1], pkg.read(target)))
            return out
    except (MdconvError, zipfile.BadZipFile, OSError):
        return []


def count_media(path: Path) -> int:
    """パッケージに含まれる画像の数（対応づけられない形式の警告に使う）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            return sum(1 for n in zf.namelist() if "/media/" in n)
    except (zipfile.BadZipFile, OSError):
        return 0
