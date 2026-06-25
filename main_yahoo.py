"""
ヤフオクウォッチリスト → ラクマ相場取得 → 推奨入札額算出
メインフロー（CLI版）

使い方：
  python main_yahoo.py --input watchlist.txt
  python main_yahoo.py --input watchlist.txt --output result.csv
"""

import argparse
import csv
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import config
from market_data import MarketDataAggregator, MarketSnapshot, RakumaSource
from models import Product
from profit_calculator import (
    ProfitResult,
    ReliabilityScore,
    calculate,
    sort_by_roi,
    sort_by_profit,
)
from yahoo_parser import parse_watchlist

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# 相場取得 + 利益計算（1商品）
# ============================================================

def process_product(
    product: Product,
    aggregator: MarketDataAggregator,
) -> ProfitResult:
    """
    1商品について相場取得〜利益計算を実行する。
    aggregator に登録されたソースが増えても、この関数は変更不要。
    """
    snapshot: MarketSnapshot = aggregator.fetch(
        product_name   = product.name,
        category_short = product.category_short,
    )

    # MarketSnapshot → RakumaData 互換オブジェクトに変換して calculate() に渡す
    # （将来は calculate() が MarketSnapshot を直接受け取るように変更可能）
    class _SnapshotAdapter:
        sold_avg      = snapshot.sold_avg
        sold_count    = snapshot.sold_count
        current_min   = snapshot.current_min
        search_keyword= snapshot.search_keyword
        sold_prices   = snapshot.sold_prices
        sold_median   = snapshot.sold_median

    return calculate(product, _SnapshotAdapter())


# ============================================================
# CSV 出力
# ============================================================

def results_to_csv(results: list[ProfitResult], path: str) -> None:
    fieldnames = [
        "商品名", "カテゴリ", "現在価格", "送料", "合計仕入れ額",
        "売値予測", "相場信頼度", "売れ済み件数",
        "安全入札額", "攻め入札額",
        "想定利益", "ROI(%)",
        "同梱失敗利益", "ROI_同梱失敗(%)",
        "current_min警告",
        "検索キーワード", "URL",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            b   = r.bid
            p   = r.product
            sf  = p.shipping_fee if p.shipping_fee is not None else 0
            writer.writerow({
                "商品名"          : p.name,
                "カテゴリ"        : p.category_short,
                "現在価格"        : p.current_price or "",
                "送料"            : sf,
                "合計仕入れ額"    : (p.current_price or 0) + sf,
                "売値予測"        : r.sell_price_estimate or "",
                "相場信頼度"      : r.reliability.level,
                "売れ済み件数"    : r.reliability.sold_count,
                "安全入札額"      : b.get("safe_bid", ""),
                "攻め入札額"      : b.get("aggressive_bid", ""),
                "想定利益"        : b.get("profit_safe", ""),
                "ROI(%)"          : b.get("roi_safe", ""),
                "同梱失敗利益"    : b.get("profit_aggressive_fail", ""),
                "ROI_同梱失敗(%)": b.get("roi_aggressive_fail", ""),
                "current_min警告": r.current_min_alert or "",
                "検索キーワード"  : r.market.search_keyword,
                "URL"             : p.url,
            })
    logger.info(f"CSV出力: {path} ({len(results)}件)")



def search_failures_to_csv(results: list, path: str) -> int:
    """
    検索失敗候補を search_failures.csv に追記保存する。
    後から見返して正規化辞書・キーワード改善に活用するためのログ。
    """
    from datetime import datetime
    from urllib.parse import quote
    from keyword_generator import is_search_failure

    failures = [r for r in results if is_search_failure(r.reliability.sold_count)]
    if not failures:
        return 0

    fieldnames = ["日時", "商品名", "検索キーワード", "売れ済み件数",
                  "プラットフォーム", "現在価格", "ラクマ検索URL"]

    file_exists = Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in failures:
            p  = r.product
            kw = r.market.search_keyword if hasattr(r, "market") else ""
            url = f"https://fril.jp/s?query={quote(kw)}&sold=1" if kw else ""
            writer.writerow({
                "日時"           : now,
                "商品名"         : p.name,
                "検索キーワード" : kw,
                "売れ済み件数"   : r.reliability.sold_count,
                "プラットフォーム": p.category_short,
                "現在価格"       : p.current_price or "",
                "ラクマ検索URL"  : url,
            })

    logger.info(f"検索失敗ログ追記: {path} ({len(failures)}件)")
    return len(failures)

# ============================================================
# メイン
# ============================================================

def main(input_text: str, output_csv: Optional[str] = None) -> list[ProfitResult]:
    # ---- パース ----
    products = parse_watchlist(input_text)
    if not products:
        logger.warning("商品が検出されませんでした")
        return []
    logger.info(f"対象商品: {len(products)}件")

    # ---- 相場ソース設定 ----
    # 将来: agg.add_source(OwnSalesSource()) を追加するだけで自社DB連携
    agg = MarketDataAggregator()
    rakuma = RakumaSource()
    rakuma.start()
    agg.add_source(rakuma)

    results: list[ProfitResult] = []
    try:
        for i, product in enumerate(products, 1):
            logger.info(f"[{i}/{len(products)}] {product.name}")
            result = process_product(product, agg)
            results.append(result)

            # 進捗サマリ
            if result.sell_price_estimate:
                b = result.bid
                logger.info(
                    f"  売値予測:{result.sell_price_estimate:,}円 "
                    f"信頼度:{result.reliability.level} "
                    f"安全入札:{b['safe_bid']:,}円 "
                    f"ROI:{b['roi_safe']}%"
                )
            else:
                logger.info(f"  ラクマデータなし（{result.reliability.label()}）")

            time.sleep(config.REQUEST_DELAY)

    finally:
        agg.teardown()

    # ---- ソート・出力 ----
    sorted_results = sort_by_roi(results)

    if output_csv:
        results_to_csv(sorted_results, output_csv)

    # ---- 検索失敗ログ（常に追記保存） ----
    fail_count = search_failures_to_csv(sorted_results, "search_failures.csv")
    if fail_count:
        logger.warning(f"検索失敗候補: {fail_count}件 → search_failures.csv に追記")

    # ---- サマリ表示 ----
    biddable = [r for r in sorted_results if r.is_worth_bidding()]
    logger.info(
        f"\n=== 完了: {len(results)}件処理 / "
        f"入札候補: {len(biddable)}件 ==="
    )
    for r in biddable[:10]:
        b = r.bid
        logger.info(
            f"  {r.product.name[:30]:30} "
            f"安全入札:{b['safe_bid']:>6,}円 "
            f"ROI:{b['roi_safe']:>6}% "
            f"信頼度:{r.reliability.level}"
        )

    return sorted_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ヤフオクウォッチリスト → 推奨入札額算出")
    parser.add_argument("--input",  required=True, help="ウォッチリストテキストファイル")
    parser.add_argument("--output", default=None,  help="CSV出力先（省略可）")
    args = parser.parse_args()

    input_text = Path(args.input).read_text(encoding="utf-8")
    main(input_text, args.output)
