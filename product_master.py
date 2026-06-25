"""
商品名正規化モジュール

【役割】
  ヤフオクの商品名（クリーニング済み）→ 正規化済み商品名 への変換

【正規化の優先順位】
  1. ProductAliasDB（別名辞書）に登録済み → 辞書の正規名を使用
  2. 未登録 → keyword_generator._clean_name() の結果をそのまま使用

【将来拡張】
  - メルカリ・ヤフーフリマの商品名も同じ正規化フローを通す
  - 外部ゲームDB（IGDB等）との照合
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from database import ProductAliasDB
from keyword_generator import generate_search_keyword

logger = logging.getLogger(__name__)

_alias_db = ProductAliasDB()


def normalize(product_name: str, platform: str = "") -> str:
    """
    商品名を正規化して返す。

    1. 別名辞書に登録済みなら辞書の正規名を返す
    2. 未登録なら入力商品名をそのまま返す

    Parameters
    ----------
    product_name : yahoo_parser._clean_name() 済みの商品名
    platform     : カテゴリ短縮形（PS2 / スーパーファミコン 等）

    Returns
    -------
    str : 正規化済み商品名
    """
    # 別名辞書で検索
    canonical = _alias_db.find_canonical(product_name)
    if canonical:
        logger.debug(f"別名ヒット: '{product_name}' → '{canonical}'")
        return canonical

    # 未登録はそのまま返す
    return product_name


def register_alias(alias: str, canonical_name: str,
                   platform: str = "") -> None:
    """
    別名を辞書に登録する。

    例：
        register_alias("チンクル", "もぎたてチンクルのばら色ルッピーランド", "NDS")
        register_alias("もぎたてチンクル", "もぎたてチンクルのばら色ルッピーランド", "NDS")
    """
    _alias_db.add_alias(alias, canonical_name, platform)


def search_keyword_for_rakuma(canonical_name: str, platform: str = "") -> str:
    """正規化済み商品名からラクマ検索キーワードを生成する（将来Phase3用）"""
    return generate_search_keyword(canonical_name, platform)
