"""
ラクマ カテゴリID調査ツール

HTMLを解析してカテゴリ関連のリンク・要素を全パターン抽出する。
保存済みの debug_xxx_sold.html を使う場合：
  python debug_category.py --html "debug_ドラゴンクエスト7 _sold.html"

ライブ取得する場合：
  python debug_category.py --name "ドラゴンクエスト7" --category 3DS
"""

import argparse
import re
import sys
import time
import logging
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("WDM").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("selenium").setLevel(logging.WARNING)


def analyze_html(html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    print("\n" + "=" * 60)
    print("【1】 category を含む全リンク")
    print("=" * 60)
    found = False
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "category" in href.lower():
            label = a.get_text(strip=True)[:40]
            print(f"  href : {href[:100]}")
            print(f"  text : {label}")
            print()
            found = True
    if not found:
        print("  → 見つかりませんでした")

    print("\n" + "=" * 60)
    print("【2】 URLパラメータに category を含む全要素")
    print("=" * 60)
    found = False
    for tag in soup.find_all(href=re.compile(r"category", re.I)):
        href = tag.get("href", "")
        qs = parse_qs(urlparse(href).query)
        label = tag.get_text(strip=True)[:40]
        if qs:
            print(f"  text : {label}")
            print(f"  params: {qs}")
            print()
            found = True
    if not found:
        print("  → 見つかりませんでした")

    print("\n" + "=" * 60)
    print("【3】 ページ内の全フォーム・セレクト（カテゴリ選択UI）")
    print("=" * 60)
    found = False
    for form in soup.find_all(["form", "select"]):
        txt = str(form)[:300]
        if "category" in txt.lower() or "ゲーム" in txt:
            print(txt[:300])
            print()
            found = True
    if not found:
        print("  → 見つかりませんでした")

    print("\n" + "=" * 60)
    print("【4】 「ゲーム」を含むリンク全件")
    print("=" * 60)
    found = False
    for a in soup.find_all("a", href=True):
        label = a.get_text(strip=True)
        if "ゲーム" in label or "game" in label.lower():
            print(f"  [{label[:30]}]  {a['href'][:100]}")
            found = True
    if not found:
        print("  → 見つかりませんでした")

    print("\n" + "=" * 60)
    print("【5】 検索フォームのaction・hiddenパラメータ")
    print("=" * 60)
    for form in soup.find_all("form"):
        action = form.get("action", "")
        print(f"  action: {action}")
        for inp in form.find_all("input"):
            name  = inp.get("name", "")
            value = inp.get("value", "")
            itype = inp.get("type", "text")
            if name:
                print(f"    input: name={name}  value={value}  type={itype}")
        print()

    print("\n" + "=" * 60)
    print("【6】 URLに数字IDを含むリンク（カテゴリIDの候補）")
    print("=" * 60)
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # fril.jp/categories/NNN or ?category_id=NNN や類似パターン
        m = re.search(r"/categories?/(\d+)|category[_\-]id[=:](\d+)", href, re.I)
        if m:
            cid = m.group(1) or m.group(2)
            label = a.get_text(strip=True)[:30]
            key = (cid, label)
            if key not in seen:
                seen.add(key)
                print(f"  ID={cid:6}  [{label}]  {href[:80]}")
                found = True
    if not seen:
        print("  → 見つかりませんでした")


def fetch_live(name: str, category: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from keyword_generator import generate_search_keyword

    keyword = generate_search_keyword(name, category)
    encoded = quote(keyword)
    url = f"https://fril.jp/s?query={encoded}&sold=1&sort=created_at&order=desc"
    logger.info(f"取得中: {url}")

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
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
    try:
        driver.get(url)
        time.sleep(3.0)
        html = driver.page_source
    finally:
        driver.quit()
    return html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ラクマ カテゴリID調査ツール")
    parser.add_argument("--html",     help="保存済みHTMLファイルのパス")
    parser.add_argument("--name",     help="商品名（ライブ取得時）")
    parser.add_argument("--category", default="", help="カテゴリ短縮形")
    args = parser.parse_args()

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8", errors="replace")
    elif args.name:
        html = fetch_live(args.name, args.category)
    else:
        parser.print_help()
        sys.exit(1)

    analyze_html(html)
