"""
利益計算モジュール（ラクマ非依存版）

【変更履歴】
  v2: ラクマ相場取得を削除。実績DBまたは手動予想売価ベースの計算に変更。
  v1: ラクマ売れ済み中央値ベース（凍結・rakuma_scraper.py と連携）

【計算式】
  利益目標 = max(売値 × 15%, 150円)
  推奨上限入札額 = 売値 - 手数料(10%) - 送料(210円) - 利益目標
  攻め入札額    = 売値 - 手数料(10%) - 利益目標  ← 同梱前提・送料なし
  ROI          = 利益 ÷ 入札額 × 100
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import config
    _FEE_RATE     = config.MERCARI_FEE_RATE
    _SHIPPING     = config.SHIPPING_COST
except (ImportError, AttributeError):
    _FEE_RATE = 0.10
    _SHIPPING = 210

PROFIT_TARGET_RATIO = 0.15
PROFIT_TARGET_MIN   = 150


# ============================================================
# 利益目標
# ============================================================

def calc_profit_target(sell_price: int) -> int:
    """利益目標 = max(売値×15%, 150円)"""
    return max(int(sell_price * PROFIT_TARGET_RATIO), PROFIT_TARGET_MIN)


# ============================================================
# 推奨上限入札額
# ============================================================

def calc_max_bid(
    sell_price: int,
    fee_rate: float = None,
    shipping: int = None,
) -> int:
    """
    安全入札額（単品仕入れ前提）。
    sell_price - 手数料 - 送料 - 利益目標

    Parameters
    ----------
    sell_price : 売値予測（実績平均 or 手動入力）
    fee_rate   : 販売手数料率（省略時は config.MERCARI_FEE_RATE）
    shipping   : 出品時送料（省略時は config.SHIPPING_COST）
    """
    if fee_rate is None:
        fee_rate = _FEE_RATE
    if shipping is None:
        shipping = _SHIPPING

    profit_target = calc_profit_target(sell_price)
    fee           = int(sell_price * fee_rate)
    return max(sell_price - fee - shipping - profit_target, 0)


def calc_aggressive_bid(
    sell_price: int,
    fee_rate: float = None,
) -> int:
    """
    攻め入札額（同梱前提・送料なし）。
    sell_price - 手数料 - 利益目標
    """
    if fee_rate is None:
        fee_rate = _FEE_RATE
    profit_target = calc_profit_target(sell_price)
    fee           = int(sell_price * fee_rate)
    return max(sell_price - fee - profit_target, 0)


# ============================================================
# ROI
# ============================================================

def calc_roi(profit: int, purchase_price: int) -> Optional[float]:
    """ROI = 利益 ÷ 仕入れ額 × 100"""
    if purchase_price <= 0:
        return None
    return round(profit / purchase_price * 100, 1)


# ============================================================
# 信頼度スコア（実績件数ベース）
# ============================================================

@dataclass
class ReliabilityScore:
    level: str       # "高" / "中" / "低" / "不明"
    sold_count: int

    @classmethod
    def from_sales_count(cls, count: int) -> "ReliabilityScore":
        if count >= 5:
            level = "高"
        elif count >= 3:
            level = "中"
        elif count >= 1:
            level = "低"
        else:
            level = "不明"
        return cls(level=level, sold_count=count)

    def label(self) -> str:
        icons = {"高": "🟢", "中": "🟡", "低": "🔴", "不明": "⚫"}
        return f"{icons.get(self.level, '')} {self.level}（{self.sold_count}回）"
