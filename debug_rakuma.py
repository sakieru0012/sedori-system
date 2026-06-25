"""
ラクマ相場取得 デバッグスクリプト

【目的】
  本番実装前に「実際にラクマから何が取れているか」を1商品単位で確認する。

【確認できること】
  - Seleniumが正常にラクマにアクセスできているか
  - HTML構造（div.item-box / data-rat-cp-price）が想定通りか
  - 売れ済み価格リストが正しく取れているか
  - 現在最安値が取れているか
  - keyword_generator が生成したキーワードが適切か
  - bot検知・リダイレクトが発生していないか

【使い方】
  # 1商品だけ確認（ヘッドあり）
  python debug_rakuma.py --name "サクラ大戦" --category DC

  # ヘッドレスで確認
  python debug_rakuma.py --name "サクラ大戦" --category DC --headless

  # HTMLソースも保存して確認
  python debug_rakuma.py --name "サクラ大戦" --category DC --save-html

  # 複数商品をまとめて検証（テキストファイルから）
  python debug_rakuma.py --batch sample.txt
"""

import argparse
import json
import logging
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

# ============================================================
# ログ設定
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("WDM").setLevel(logging.WARNING)


def _iqr_filter(prices: list[int]) -> list[int]:
    """IQR法で外れ値を除去する（market_data.py と同じロジック）"""
    if len(prices) < 4:
        return prices
    s = sorted(prices)
    n = len(s)
    q1, q3 = s[n // 4], s[3 * n // 4]
    iqr = q3 - q1
    if iqr == 0:
        return prices
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    filtered = [p for p in s if lower <= p <= upper]
    return filtered if filtered else prices


# ============================================================
# 取得結果データクラス
# ============================================================

@dataclass
class DebugResult:
    """1商品の取得結果詳細"""
    product_name: str
    category_short: str
    search_keyword: str
    rakuma_search_url: str

    # 売れ済み
    sold_prices: list[int] = field(default_factory=list)
    sold_prices_raw: list[int] = field(default_factory=list)  # IQR除去前の生データ
    sold_count: int = 0
    sold_median: Optional[int] = None
    sold_avg: Optional[int] = None
    sold_min: Optional[int] = None
    sold_max: Optional[int] = None
    sold_std: Optional[float] = None   # 価格の標準偏差（ばらつき確認用）

    # 現在最安値
    current_min: Optional[int] = None
    current_min_url: str = ""

    # デバッグ情報
    final_url_sold: str = ""      # 実際にアクセスしたURL
    final_url_min: str = ""
    redirected: bool = False      # リダイレクト検知
    bot_detected: bool = False    # bot検知の疑い
    html_item_count: int = 0      # ページ上のitem-box数
    error: Optional[str] = None

    def calc_stats(self):
        """取得後にIQR外れ値除去を適用し、統計値を計算する"""
        if not self.sold_prices:
            return

        # IQR除去
        self.sold_prices_raw = list(self.sold_prices)
        self.sold_prices     = _iqr_filter(self.sold_prices)

        s = sorted(self.sold_prices)
        self.sold_count  = len(s)
        self.sold_median = s[len(s) // 2]
        self.sold_avg    = int(statistics.mean(s))
        self.sold_min    = s[0]
        self.sold_max    = s[-1]
        self.sold_std    = round(statistics.stdev(s), 1) if len(s) >= 2 else 0.0

    def print_report(self):
        """コンソールにレポートを出力する"""
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  商品名    : {self.product_name}")
        print(f"  カテゴリ  : {self.category_short}")
        print(f"  検索キー  : {self.search_keyword}")
        print(f"  検索URL   : {self.rakuma_search_url}")
        print(sep)

        # 取得状態
        if self.error:
            print(f"  ❌ エラー: {self.error}")
            return

        if self.bot_detected:
            print("  ⚠️  bot検知の疑い（ページが想定外のURLにリダイレクト）")
        if self.redirected:
            print(f"  ↪️  リダイレクト先: {self.final_url_sold}")

        print(f"  ページ内 item-box 数: {self.html_item_count}")
        print()

        # 売れ済み価格
        removed_count = len(self.sold_prices_raw) - len(self.sold_prices)
        header = f"  【売れ済み価格リスト】 {self.sold_count}件"
        if removed_count > 0:
            removed = sorted(set(self.sold_prices_raw) - set(self.sold_prices))
            removed_str = " / ".join(f"{p:,}円" for p in removed)
            header += f"  ※{removed_count}件をIQR除去: {removed_str}"
        print(header)
        if self.sold_prices:
            for i, p in enumerate(sorted(self.sold_prices), 1):
                bar = "█" * (p // 500)
                print(f"    {i:2}. {p:>6,}円  {bar}")
            print()
            print(f"  中央値  : {self.sold_median:,}円  ← 売値予測に使用")
            print(f"  平均    : {self.sold_avg:,}円")
            print(f"  最安値  : {self.sold_min:,}円")
            print(f"  最高値  : {self.sold_max:,}円")
            print(f"  標準偏差: {self.sold_std}円  ← 大きいほど価格がばらついている")
            if self.sold_std and self.sold_avg:
                cv = self.sold_std / self.sold_avg * 100
                if cv > 50:
                    print(f"  ⚠️  価格のばらつきが大きいです（CV={cv:.0f}%）状態違い品が混在している可能性")
        else:
            print("  ❌ 売れ済みデータ取得できず")
            print("     → キーワードが合っていない / 出品数が少ない / bot検知の可能性")

        print()
        print(f"  【現在最安値】")
        if self.current_min:
            print(f"    {self.current_min:,}円")
            if self.sold_median and self.current_min < self.sold_median * 0.7:
                gap = self.current_min / self.sold_median * 100
                print(f"  ⚠️  売値予測の{gap:.0f}%（状態違い品・訳あり品が最安値の可能性）")
        else:
            print("  ❌ 最安値取得できず")

        print(sep)

    def to_dict(self) -> dict:
        return {
            "product_name"    : self.product_name,
            "category_short"  : self.category_short,
            "search_keyword"  : self.search_keyword,
            "sold_count"      : self.sold_count,
            "sold_prices"     : self.sold_prices,
            "sold_median"     : self.sold_median,
            "sold_avg"        : self.sold_avg,
            "sold_std"        : self.sold_std,
            "current_min"     : self.current_min,
            "bot_detected"    : self.bot_detected,
            "html_item_count" : self.html_item_count,
            "error"           : self.error,
        }


# ============================================================
# Selenium取得（デバッグ情報付き）
# ============================================================

def _build_driver(headless: bool):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    if headless:
        options.add_argument("--headless=new")
        logger.info("ヘッドレスモードで起動")
    else:
        logger.info("ヘッドありモードで起動（ブラウザが表示されます）")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def fetch_debug(
    product_name: str,
    category_short: str = "",
    headless: bool = False,
    sold_count: int = 10,
    save_html: bool = False,
) -> DebugResult:
    """
    1商品のデバッグ取得を実行する。

    通常の RakumaScraper より詳細な情報を返す：
    - 価格リスト全件
    - 統計値（中央値・平均・標準偏差）
    - リダイレクト・bot検知フラグ
    - ページ上のitem-box数
    """
    from bs4 import BeautifulSoup
    from keyword_generator import generate_search_keyword, get_rakuma_category_id

    keyword   = generate_search_keyword(product_name, category_short)
    encoded   = quote(keyword)
    cat_id    = get_rakuma_category_id(category_short)
    cat_param = f"&category_id={cat_id}" if cat_id else ""
    sold_url  = (
        f"https://fril.jp/s?query={encoded}{cat_param}&transaction=soldout&sort=created_at&order=desc"
    )

    result = DebugResult(
        product_name      = product_name,
        category_short    = category_short,
        search_keyword    = keyword,
        rakuma_search_url = sold_url,
    )

    driver = None
    try:
        driver = _build_driver(headless)
        logger.info(f"取得中: {keyword}...")

        # ---- 売れ済み取得 ----
        driver.get(sold_url)
        time.sleep(3.0)

        result.final_url_sold = driver.current_url
        if "fril.jp/s" not in driver.current_url:
            result.redirected  = True
            result.bot_detected = True
            logger.warning(f"リダイレクト検知: {driver.current_url}")
        else:
            pass  # 正常アクセス

        html  = driver.page_source
        soup  = BeautifulSoup(html, "html.parser")
        items = soup.select("div.item-box")
        result.html_item_count = len(items)
        logger.info(f"ページ内 item-box 数: {len(items)}")

        # HTMLを保存（デバッグ用）
        if save_html:
            html_path = f"debug_{keyword[:10]}_sold.html"
            Path(html_path).write_text(html, encoding="utf-8")
            logger.info(f"HTMLを保存: {html_path}")

        # カテゴリリンクからIDを取得（初回確認用）
        cat_links = soup.select("a[href*='category_id']")
        if cat_links:
            logger.info("--- ラクマカテゴリID一覧 ---")
            seen = set()
            for a in cat_links[:40]:
                href = a.get("href", "")
                m = re.search(r"category_id=(\d+)", href)
                label = a.get_text(strip=True)[:30]
                if m and m.group(1) not in seen and label:
                    seen.add(m.group(1))
                    logger.info(f"  category_id={m.group(1):6}  {label}")

        # 価格抽出（全件ログ付き）
        prices = []
        for i, item in enumerate(items[:sold_count * 2]):
            if len(prices) >= sold_count:
                break
            try:
                link = item.select_one("a.link_search_image")
                if link:
                    price_str = link.get("data-rat-cp-price", "")
                    title_el  = item.select_one(".item-box__item-name, .item-name, h2, h3")
                    title     = title_el.text.strip()[:30] if title_el else "タイトル取得不可"
                    if price_str and price_str.isdigit():
                        price = int(price_str)
                        if price > 0:
                            prices.append(price)
                            logger.debug(f"  [{i+1:2}] {price:>6,}円  {title}")
                    else:
                        logger.debug(f"  [{i+1:2}] 価格なし  {title}  (data-rat-cp-price='{price_str}')")
            except Exception as e:
                logger.debug(f"  [{i+1:2}] 取得エラー: {e}")

        result.sold_prices = prices
        result.calc_stats()

        time.sleep(1.5)

        # ---- 現在最安値取得 ----
        min_url = f"https://fril.jp/s?query={encoded}{cat_param}&sort=price_asc"
        driver.get(min_url)
        time.sleep(3.0)

        result.final_url_min = driver.current_url
        soup2 = BeautifulSoup(driver.page_source, "html.parser")
        items2 = soup2.select("div.item-box")
        if items2:
            try:
                link = items2[0].select_one("a.link_search_image")
                if link:
                    price_str = link.get("data-rat-cp-price", "")
                    if price_str and price_str.isdigit():
                        result.current_min = int(price_str)
                        # 最安値商品のURLも取得
                        href = link.get("href", "")
                        result.current_min_url = f"https://fril.jp{href}" if href.startswith("/") else href
                        logger.info(f"現在最安値: {result.current_min:,}円")
            except Exception as e:
                logger.debug(f"最安値取得エラー: {e}")

        if save_html:
            html2_path = f"debug_{keyword[:10]}_min.html"
            Path(html2_path).write_text(driver.page_source, encoding="utf-8")
            logger.info(f"最安値ページHTML保存: {html2_path}")

    except Exception as e:
        result.error = str(e)
        logger.error(f"取得エラー: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()

    return result


# ============================================================
# バッチモード（複数商品をテキストファイルから読み込み）
# ============================================================

def run_batch(text_path: str, headless: bool, save_html: bool):
    """
    ウォッチリストのテキストファイルを読み込んで一括デバッグ取得する。
    結果は debug_results.json に保存する。
    """
    from yahoo_parser import parse_watchlist

    text     = Path(text_path).read_text(encoding="utf-8")
    products = parse_watchlist(text)

    if not products:
        print("商品が検出されませんでした。")
        return

    print(f"\n{len(products)}件を順番に取得します。")
    print("Ctrl+C で中断できます。\n")

    results = []
    for i, p in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}] {p.name}")
        r = fetch_debug(
            product_name   = p.name,
            category_short = p.category_short,
            headless       = headless,
            save_html      = save_html,
        )
        r.print_report()
        results.append(r.to_dict())
        time.sleep(2.0)

    # JSON保存
    out_path = "debug_results.json"
    Path(out_path).write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果を保存しました: {out_path}")

    # サマリ
    ok    = [r for r in results if r["sold_count"] > 0]
    fails = [r for r in results if r["sold_count"] == 0]
    print(f"\n=== サマリ ===")
    print(f"  取得成功: {len(ok)}件")
    print(f"  取得失敗: {len(fails)}件")
    if fails:
        print("  失敗商品:")
        for r in fails:
            print(f"    - {r['product_name']}（検索語: {r['search_keyword']}）")


# ============================================================
# エントリーポイント
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ラクマ相場取得デバッグツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 1商品デバッグ（ブラウザ表示あり）
  python debug_rakuma.py --name "サクラ大戦" --category DC

  # ヘッドレスで取得
  python debug_rakuma.py --name "ギルティギア" --category DC --headless

  # HTMLも保存して詳細確認
  python debug_rakuma.py --name "ドラゴンクエスト7" --category 3DS --save-html

  # ウォッチリストから一括デバッグ
  python debug_rakuma.py --batch watchlist.txt --headless
        """,
    )
    parser.add_argument("--name",      help="商品名")
    parser.add_argument("--category",  default="", help="カテゴリ短縮形（DC/PS1/SS等）")
    parser.add_argument("--headless",  action="store_true", help="ヘッドレスモード")
    parser.add_argument("--save-html", action="store_true", help="HTMLを保存")
    parser.add_argument("--sold-count",type=int, default=10, help="取得する売れ済み件数（デフォルト10）")
    parser.add_argument("--batch",     help="ウォッチリストテキストファイル（一括モード）")
    args = parser.parse_args()

    if args.batch:
        run_batch(args.batch, headless=args.headless, save_html=args.save_html)
    elif args.name:
        result = fetch_debug(
            product_name   = args.name,
            category_short = args.category,
            headless       = args.headless,
            sold_count     = args.sold_count,
            save_html      = args.save_html,
        )
        result.print_report()
    else:
        parser.print_help()
