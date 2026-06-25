"""
相場データ抽象化レイヤー

【設計方針】
- MarketDataSource: 相場取得の抽象基底クラス（インターフェース）
- RakumaSource:     既存 RakumaScraper のラッパー
- MarketDataAggregator: 複数ソースを束ねて MarketSnapshot を生成

将来追加予定のソース：
  OwnSalesSource      自分の販売実績DB
  MercariSource       メルカリ（参考相場）
  YahooFleaSource     ヤフオクフリマ

新しいソースを追加しても profit_calculator.py や app.py は変更不要。
"""

from __future__ import annotations

import statistics
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# 相場スナップショット（集約後の統一データ型）
# ============================================================

@dataclass
class MarketSnapshot:
    """
    1商品の相場データをソース横断で集約した結果。
    profit_calculator.py はこれだけを受け取って計算する。

    全フィールドはOptional。データが取れなかった場合はNone。
    """
    # ---- ラクマ相場 ----
    sold_prices: list[int] = field(default_factory=list)  # 売れ済み価格リスト（生データ）
    sold_median: Optional[int] = None    # 中央値（優先）
    sold_avg: Optional[int] = None       # 平均（フォールバック）
    sold_count: int = 0
    current_min: Optional[int] = None   # 現在最安値（表示のみ・計算非使用）
    search_keyword: str = ""

    # ---- 自社販売実績（将来用・今はNone） ----
    # own_sold_prices: list[int] = field(default_factory=list)
    # own_sold_median: Optional[int] = None
    # own_sold_count: int = 0
    # own_avg_days_to_sell: Optional[float] = None  # 平均回転日数

    # ---- メタ情報 ----
    sources_used: list[str] = field(default_factory=list)  # 使用したソース名

    @classmethod
    def empty(cls, search_keyword: str = "") -> "MarketSnapshot":
        return cls(search_keyword=search_keyword)

    def is_empty(self) -> bool:
        return self.sold_count == 0


def _calc_median(prices: list[int]) -> Optional[int]:
    """ソート済み整数リストの中央値（切り捨て中央値）"""
    if not prices:
        return None
    s = sorted(prices)
    return s[len(s) // 2]


def _calc_avg(prices: list[int]) -> Optional[int]:
    if not prices:
        return None
    return int(statistics.mean(prices))


def _remove_outliers_iqr(prices: list[int]) -> list[int]:
    """
    IQR法で外れ値を除去する。

    四分位範囲（IQR = Q3 - Q1）を使い、
    [Q1 - 1.5×IQR, Q3 + 1.5×IQR] の範囲外を外れ値として除去する。

    件数が少ない場合（4件未満）は除去を行わない。
    除去後に0件になる場合は元のリストをそのまま返す。

    例（ドラクエ7 3DS）:
      入力 : [500, 1000, 1000, 1150, 1200, 1380, 1480, 1550, 1650, 3380]
      Q1=1000, Q3=1550, IQR=550, 上限=2425, 下限=175
      出力 : [500, 1000, 1000, 1150, 1200, 1380, 1480, 1550, 1650]
      → 3,380円（まとめ売り）を除外
    """
    if len(prices) < 4:
        return prices  # 件数が少なすぎる場合はスキップ

    s = sorted(prices)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[3 * n // 4]
    iqr = q3 - q1

    if iqr == 0:
        return prices  # 全件同額の場合はスキップ

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    filtered = [p for p in s if lower <= p <= upper]

    if not filtered:
        return prices  # 全件除去されてしまう場合は元に戻す

    removed = len(prices) - len(filtered)
    if removed:
        logger.debug(f"IQR外れ値除去: {removed}件除外 (下限{lower:.0f}〜上限{upper:.0f}円)")

    return filtered


# ============================================================
# 抽象基底クラス（全ソースが実装するインターフェース）
# ============================================================

class MarketDataSource(ABC):
    """
    相場データソースの抽象基底クラス。

    新しい相場ソース（自社DB・メルカリ等）を追加する場合は
    このクラスを継承して fetch() を実装するだけでよい。
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """ソース識別名（ログ・デバッグ用）"""
        ...

    @abstractmethod
    def fetch(
        self,
        product_name: str,
        category_short: str = "",
    ) -> "SourceResult":
        """
        商品名・カテゴリから相場データを取得する。

        Parameters
        ----------
        product_name   : 検索する商品名
        category_short : カテゴリ短縮形（PS1/PS2/SS/DC等）

        Returns
        -------
        SourceResult : 取得結果（失敗時は prices=[] の空結果）
        """
        ...

    def teardown(self) -> None:
        """セッション終了処理（Seleniumのquit等）。必要なら override。"""
        pass


@dataclass
class SourceResult:
    """各ソースの生取得結果"""
    source_name: str
    sold_prices: list[int] = field(default_factory=list)
    current_min: Optional[int] = None
    search_keyword: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ============================================================
# RakumaSource（既存 RakumaScraper のラッパー）
# ============================================================

class RakumaSource(MarketDataSource):
    """
    既存の RakumaScraper を MarketDataSource として包むアダプタ。
    RakumaScraper の内部実装には一切手を加えない。
    """

    source_name = "ラクマ"

    def __init__(self):
        from rakuma_scraper import RakumaScraper
        self._scraper = RakumaScraper()

    def start(self) -> None:
        self._scraper.start()

    def fetch(self, product_name: str, category_short: str = "") -> SourceResult:
        try:
            rd = self._scraper.fetch(product_name, category_short)
            # sold_avg しか返ってこない場合は prices リストが空になる
            # → スクレイパー拡張後は sold_prices を直接返せるようにする（後述）
            prices = getattr(rd, "sold_prices", [])
            if not prices and rd.sold_avg:
                # 拡張前の互換：avg を1件分の価格として扱う（暫定）
                prices = [rd.sold_avg] * rd.sold_count if rd.sold_count > 0 else []

            return SourceResult(
                source_name    = self.source_name,
                sold_prices    = prices,
                current_min    = rd.current_min,
                search_keyword = rd.search_keyword,
            )
        except Exception as e:
            logger.warning(f"[{self.source_name}] fetch失敗: {product_name} / {e}")
            return SourceResult(
                source_name = self.source_name,
                error       = str(e),
            )

    def teardown(self) -> None:
        self._scraper.stop()


# ============================================================
# 将来用スタブ（今は何もしない・インターフェースの例示）
# ============================================================

class OwnSalesSource(MarketDataSource):
    """
    【将来実装】自分の販売実績DB。
    SQLite or CSV から自分の過去売値・回転日数を取得する。

    実装時に追加するフィールド（SourceResult拡張 or 別クラス）：
      - own_sold_prices: list[int]
      - avg_days_to_sell: float
    """
    source_name = "自社実績"

    def fetch(self, product_name: str, category_short: str = "") -> SourceResult:
        # 将来実装
        return SourceResult(source_name=self.source_name, error="未実装")


# ============================================================
# MarketDataAggregator（複数ソースを束ねる集約クラス）
# ============================================================

class MarketDataAggregator:
    """
    登録された全ソースからデータを取得し、
    MarketSnapshot に集約して返す。

    使用例（将来・複数ソース）：
        agg = MarketDataAggregator()
        agg.add_source(RakumaSource())
        agg.add_source(OwnSalesSource())   # 将来
        snapshot = agg.fetch("サクラ大戦", "DC")

    使用例（現在・単一ソース）：
        agg = MarketDataAggregator()
        agg.add_source(RakumaSource())
        snapshot = agg.fetch("サクラ大戦", "DC")
    """

    def __init__(self):
        self._sources: list[MarketDataSource] = []

    def add_source(self, source: MarketDataSource) -> None:
        self._sources.append(source)
        logger.debug(f"ソース追加: {source.source_name}")

    def fetch(self, product_name: str, category_short: str = "") -> MarketSnapshot:
        """
        全ソースから取得し、MarketSnapshot に集約する。

        集約ロジック（現在）：
          sold_prices → 全ソースの価格を合算して中央値・平均を計算
          current_min → ラクマの値をそのまま使用

        将来拡張ポイント：
          - 自社実績の件数が多い場合はそちらの中央値を優先
          - ソースごとに重み付けを変える
        """
        if not self._sources:
            logger.warning("ソースが登録されていません")
            return MarketSnapshot.empty(product_name)

        all_sold_prices: list[int] = []
        current_min: Optional[int] = None
        search_keyword: str = product_name
        sources_used: list[str] = []

        for source in self._sources:
            result = source.fetch(product_name, category_short)
            if not result.ok:
                logger.warning(f"[{result.source_name}] エラー: {result.error}")
                continue

            sources_used.append(result.source_name)
            all_sold_prices.extend(result.sold_prices)

            if result.search_keyword:
                search_keyword = result.search_keyword

            # current_min はラクマを優先（最初に取得した値を使用）
            if current_min is None and result.current_min is not None:
                current_min = result.current_min

        # IQR法で外れ値を除去してから統計値を計算
        prices_raw      = all_sold_prices
        prices_filtered = _remove_outliers_iqr(all_sold_prices)

        return MarketSnapshot(
            sold_prices    = prices_filtered,
            sold_median    = _calc_median(prices_filtered),
            sold_avg       = _calc_avg(prices_filtered),
            sold_count     = len(prices_filtered),
            current_min    = current_min,
            search_keyword = search_keyword,
            sources_used   = sources_used,
        )

    def teardown(self) -> None:
        """全ソースの終了処理"""
        for source in self._sources:
            try:
                source.teardown()
            except Exception as e:
                logger.warning(f"[{source.source_name}] teardown失敗: {e}")
