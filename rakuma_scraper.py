"""
ラクマスクレイパー（拡張版）
- sold_prices リストを返すよう拡張（中央値計算をAggregator側で行う）
- セッション切れを検知して自動再起動
"""

import time
import logging
import re
from typing import Optional
from dataclasses import dataclass, field
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, InvalidSessionIdException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

CATEGORY_KEYWORDS = {
    "PS1": "プレイステーション",
    "PS2": "PS2",
    "PS3": "PS3",
    "SS":  "セガサターン",
    "DC":  "ドリームキャスト",
    "Wii": "Wii",
    "3DS": "3DS",
    "NDS": "ニンテンドーDS",
    "PSP": "PSP",
    "VITA":"PS Vita",
}


@dataclass
class RakumaData:
    # 既存フィールド（後方互換）
    sold_avg: Optional[int]
    sold_count: int
    current_min: Optional[int]
    search_keyword: str
    # 拡張フィールド：生価格リスト（中央値計算はAggregator側）
    sold_prices: list[int] = field(default_factory=list)


def _build_driver() -> webdriver.Chrome:
    options = Options()
    if config.HEADLESS:
        options.add_argument("--headless=new")
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


def _clean_keyword(product_name: str) -> str:
    cleaned = re.sub(r"[【】\[\]（）\(\)].*?[【】\[\]（）\(\)]", " ", product_name)
    cleaned = re.sub(r"[/／＋+★☆◆◇●○■□▲△▽▼⚠️]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 30:
        cleaned = cleaned[:30].rsplit(" ", 1)[0]
    return cleaned


def _get_prices_from_page(
    driver: webdriver.Chrome, url: str, limit: int
) -> list[int]:
    prices = []
    try:
        driver.get(url)
        time.sleep(2.5)
        if "fril.jp/s" not in driver.current_url:
            return prices
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for item in soup.select("div.item-box")[:limit * 2]:
            if len(prices) >= limit:
                break
            try:
                link = item.select_one("a.link_search_image")
                if link:
                    price_str = link.get("data-rat-cp-price", "")
                    if price_str and price_str.isdigit():
                        price = int(price_str)
                        if price > 0:
                            prices.append(price)
            except Exception as e:
                logger.debug(f"価格取得エラー: {e}")
    except (InvalidSessionIdException, WebDriverException):
        raise
    return prices


class RakumaScraper:
    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None

    def start(self):
        logger.info("ラクマ Selenium 起動中...")
        self.driver = _build_driver()
        logger.info("ラクマ Selenium 起動完了")

    def _restart(self):
        logger.info("ラクマ: ドライバー再起動...")
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        time.sleep(2)
        self.driver = _build_driver()
        logger.info("ラクマ: 再起動完了")

    def stop(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            logger.info("ラクマ Selenium 終了")

    def fetch(self, product_name: str, category_short: str = "") -> RakumaData:
        from keyword_generator import generate_search_keyword, get_rakuma_category_id
        keyword = generate_search_keyword(product_name, category_short)
        logger.debug(f"  ラクマ検索: '{keyword}'")

        if not self.driver:
            return RakumaData(
                sold_avg=None, sold_count=0, current_min=None,
                search_keyword=keyword, sold_prices=[],
            )

        encoded   = quote(keyword)
        cat_id    = get_rakuma_category_id(category_short)
        cat_param = f"&category_id={cat_id}" if cat_id else ""

        # ---- 売れ済み価格リスト取得 ----
        sold_prices: list[int] = []
        for attempt in range(2):
            try:
                url = (
                    f"https://fril.jp/s?query={encoded}"
                    f"{cat_param}"
                    f"&transaction=soldout&sort=created_at&order=desc"
                )
                sold_prices = _get_prices_from_page(
                    self.driver, url, config.RAKUMA_SOLD_COUNT
                )
                break
            except (InvalidSessionIdException, WebDriverException):
                if attempt == 0:
                    self._restart()
                else:
                    logger.warning(f"  売れ済み取得スキップ: {keyword}")

        # 平均（フォールバック用）
        sold_avg = int(sum(sold_prices) / len(sold_prices)) if sold_prices else None
        if sold_avg:
            logger.debug(f"  売れ済み {len(sold_prices)}件 avg={sold_avg}円")

        time.sleep(config.REQUEST_DELAY)

        # ---- 現在最安値 ----
        current_min: Optional[int] = None
        for attempt in range(2):
            try:
                url = f"https://fril.jp/s?query={encoded}{cat_param}&sort=price_asc"
                prices = _get_prices_from_page(self.driver, url, 1)
                current_min = prices[0] if prices else None
                break
            except (InvalidSessionIdException, WebDriverException):
                if attempt == 0:
                    self._restart()
                else:
                    logger.warning(f"  最安値取得スキップ: {keyword}")

        if current_min:
            logger.debug(f"  現在最安値: {current_min}円")

        time.sleep(config.REQUEST_DELAY)

        return RakumaData(
            sold_avg       = sold_avg,
            sold_count     = len(sold_prices),
            current_min    = current_min,
            search_keyword = keyword,
            sold_prices    = sold_prices,   # ← 拡張フィールド
        )
