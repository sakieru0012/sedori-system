"""
共通データモデル
全ECサイトで使う汎用Product dataclass
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Product:
    name: str
    price: int               # 仕入れ価格（確定後）
    condition: str
    url: str
    image_url: str           # 商品画像URL（なければ空文字）
    category: str
    category_short: str
    source: str              # 仕入れ元（"駿河屋" / "ゲオ" / "ハードオフ" / "ヤフオク"）

    # ヤフオク拡張フィールド（他ソースでは None でOK）
    current_price: Optional[int] = field(default=None)   # 現在の入札価格
    shipping_fee: Optional[int] = field(default=None)    # 送料（出品者表示）
