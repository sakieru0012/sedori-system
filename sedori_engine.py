"""
せどり判定エンジン

【役割】
  ウォッチリスト商品 + DB照合結果 → 判定結果（入札 / 検討 / 見送り）

【判定ロジック】
  合計仕入れ額 = 現在価格 + 送料

  合計仕入れ額 ≤ 推奨上限入札額     → 🟢 入札
  推奨上限入札額 < 合計仕入れ額
    かつ 現在価格 ≤ 推奨上限入札額  → 🟡 検討（送料次第）
  現在価格 > 推奨上限入札額         → 🔴 見送り
  送料不明                         → 🟡 検討（送料不明）
  推奨上限入札額未設定              → ⚫ 未調査
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from database import SalesDB, ResearchDB, SalesSummary, ResearchItem
from models import Product
from name_resolver import NameResolver
from profit_calculator import calc_max_bid

logger = logging.getLogger(__name__)

# ============================================================
# 判定結果
# ============================================================

VERDICT_BID      = "入札"
VERDICT_CONSIDER = "検討"
VERDICT_PASS     = "見送り"
VERDICT_UNKNOWN  = "未調査"

VERDICT_ICONS = {
    VERDICT_BID     : "🟢",
    VERDICT_CONSIDER: "🟡",
    VERDICT_PASS    : "🔴",
    VERDICT_UNKNOWN : "⚫",
}


from name_resolver import ResolutionResult

@dataclass
class EngineResult:
    """1商品の判定結果"""
    product: Product

    # 名寄せ結果
    resolution: Optional[ResolutionResult] = None
    canonical_name: str = ""
    sales_summary: Optional[SalesSummary] = None
    research_item: Optional[ResearchItem] = None

    # 入札額計算
    recommended_max_bid: int = 0
    sell_price: int = 0              # 売値（推奨上限算出に使った値）
    basis: str = ""

    # 判定
    verdict: str = VERDICT_UNKNOWN
    verdict_reason: str = ""

    # 差額
    diff_safe: Optional[int] = None
    diff_total: Optional[int] = None

    @property
    def needs_resolution(self) -> bool:
        """名寄せが未確定で候補がある"""
        return (
            self.resolution is not None
            and not self.resolution.is_confirmed
            and len(self.resolution.candidates) > 0
        )

    @property
    def is_unregistered(self) -> bool:
        """DB未登録・名寄せ候補なし"""
        return (
            self.resolution is not None
            and not self.resolution.is_confirmed
            and len(self.resolution.candidates) == 0
        )

    @property
    def verdict_icon(self) -> str:
        return VERDICT_ICONS.get(self.verdict, "⚫")

    @property
    def total_cost(self) -> Optional[int]:
        """現在価格 + 送料（送料不明時はNone）"""
        p = self.product
        if p.current_price is None:
            return None
        if p.shipping_fee is None:
            return None
        return p.current_price + p.shipping_fee

    def sell_price_display(self) -> str:
        if self.sales_summary:
            return f"{self.sales_summary.avg_sold_price:,}円"
        if self.research_item:
            return f"{self.research_item.estimated_sell_price:,}円"
        return "-"

    def basis_display(self) -> str:
        if self.sales_summary:
            return f"実績（{self.sales_summary.sales_count}回）"
        if self.research_item:
            return "手動予想"
        return ""


# ============================================================
# エンジン本体
# ============================================================

class SedoriEngine:
    """
    ウォッチリスト商品をDBと照合して判定結果を返す。

    Supabase接続情報が config.py にあれば本番DB、なければモックDBを使用。
    """

    def __init__(self):
        try:
            import config
            url = getattr(config, "SUPABASE_URL", "")
            key = getattr(config, "SUPABASE_KEY", "")
            use_sb = bool(url and key)
        except ImportError:
            url = key = ""
            use_sb = False

        self.sales_db    = SalesDB(use_supabase=use_sb,
                                   supabase_url=url, supabase_key=key)
        self.research_db = ResearchDB()
        self.resolver    = NameResolver()

        # 名寄せ候補検索用にSupabaseの商品名をキャッシュ
        if use_sb:
            n = self.resolver.load_supabase_cache(url, key)
            logger.info(f"名寄せキャッシュ: {n}件")

        logger.info(f"SedoriEngine: {'Supabase' if use_sb else 'SQLiteモック'}モード")

    def process(self, product: Product) -> EngineResult:
        """1商品を処理して EngineResult を返す。"""
        result = EngineResult(product=product)

        # ① 名寄せ（エイリアスDB照合 → 候補提示）
        resolution = self.resolver.resolve(product.name, product.category_short)
        result.resolution = resolution

        # 確定済みの正規名、または未確定の場合は元の商品名をそのまま使用
        result.canonical_name = (
            resolution.canonical_name
            if resolution.is_confirmed and resolution.canonical_name
            else product.name
        )

        # ② 売買実績DBを照合
        summary = self.sales_db.find_by_name(
            result.canonical_name, product.category_short
        )
        if summary and summary.sales_count > 0:
            result.sales_summary        = summary
            result.recommended_max_bid  = summary.recommended_max_bid
            result.sell_price           = summary.avg_sold_price
            result.basis                = f"実績（{summary.sales_count}回）"
        else:
            # ③ リサーチDBを照合
            research = self.research_db.find(
                result.canonical_name, product.category_short
            )
            if research:
                result.research_item        = research
                result.recommended_max_bid  = research.recommended_max_bid
                result.sell_price           = research.estimated_sell_price
                result.basis                = "手動予想"

        # ④ 判定
        result = self._judge(result)
        return result

    def _judge(self, result: EngineResult) -> EngineResult:
        """判定ロジック"""
        p   = result.product
        max_bid = result.recommended_max_bid

        if max_bid <= 0:
            result.verdict        = VERDICT_UNKNOWN
            result.verdict_reason = "DB未登録・予想売価未入力"
            return result

        cur = p.current_price or 0
        result.diff_safe = max_bid - cur

        if p.shipping_fee is None:
            # 送料不明
            result.diff_total     = None
            result.verdict        = VERDICT_CONSIDER
            result.verdict_reason = f"送料不明（現在価格{cur:,}円 / 上限{max_bid:,}円）"
        else:
            total = cur + p.shipping_fee
            result.diff_total = max_bid - total

            if total <= max_bid:
                result.verdict        = VERDICT_BID
                result.verdict_reason = (
                    f"合計{total:,}円 ≤ 上限{max_bid:,}円"
                    f"（差額 +{result.diff_total:,}円）"
                )
            elif cur <= max_bid:
                result.verdict        = VERDICT_CONSIDER
                result.verdict_reason = (
                    f"送料込みで上限超過"
                    f"（現在{cur:,}円 + 送料{p.shipping_fee:,}円 = {total:,}円 / 上限{max_bid:,}円）"
                )
            else:
                result.verdict        = VERDICT_PASS
                result.verdict_reason = (
                    f"現在価格{cur:,}円 > 上限{max_bid:,}円"
                )

        return result

    def process_batch(self, products: list[Product]) -> list[EngineResult]:
        """複数商品を一括処理"""
        results = []
        for p in products:
            results.append(self.process(p))
        return results

    def save_research(self, canonical_name: str, platform: str,
                      original_name: str, estimated_sell_price: int,
                      listing_price: int = 0,
                      doubtful: bool = False,
                      memo: str = "") -> ResearchItem:
        """
        手動入力の予想売価をリサーチDBに保存する。
        推奨上限入札額は自動計算して保存。
        listing_price: 実際に出品する予定価格（0の場合は未設定）
        """
        from database import ResearchItem as RI
        max_bid = calc_max_bid(estimated_sell_price) if estimated_sell_price > 0 else 0
        item = RI(
            id                   = None,
            name                 = original_name,
            canonical_name       = canonical_name,
            platform             = platform,
            estimated_sell_price = estimated_sell_price,
            recommended_max_bid  = max_bid,
            listing_price        = listing_price,
            doubtful             = doubtful,
            basis                = "手動予想",
            memo                 = memo,
        )
        item_id = self.research_db.save(item)
        item.id = item_id
        if estimated_sell_price > 0:
            logger.info(
                f"リサーチDB保存: '{canonical_name}' "
                f"予想売価{estimated_sell_price:,}円 → 上限{max_bid:,}円"
            )
        else:
            logger.info(f"リサーチDB保存（スキップ）: '{canonical_name}' memo={memo}")
        return item
