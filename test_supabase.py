"""
Supabase 接続テストスクリプト

使い方：
  python test_supabase.py
"""
import json, sys, logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    try:
        import config
        url = getattr(config, "SUPABASE_URL", "")
        key = getattr(config, "SUPABASE_KEY", "")
    except ImportError:
        print("❌ config.py が見つかりません")
        sys.exit(1)

    if not url or not key:
        print("❌ config.py に SUPABASE_URL / SUPABASE_KEY が未設定です")
        print()
        print("以下を config.py に追記してください：")
        print('  SUPABASE_URL = "https://csacyrmcytumkblrvxpv.supabase.co"')
        print('  SUPABASE_KEY = "your-publishable-key"')
        sys.exit(1)

    print(f"接続先: {url}")
    print("接続テスト中...")

    try:
        import httpx
    except ImportError:
        print("❌ httpx が未インストールです")
        print("   pip install httpx")
        sys.exit(1)

    client = httpx.Client(
        base_url=url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )

    # ---- 件数確認 ----
    resp = client.get("/rest/v1/items", params={"select": "count"})
    if resp.status_code != 200:
        print(f"❌ 接続失敗: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("✅ 接続OK")
    print()

    # ---- データ確認 ----
    resp = client.get("/rest/v1/items", params={
        "select": "item_id,name,platform,bid_price,ship_in,sales_json",
        "limit":  "5",
        "order":  "item_id.desc",
    })
    items = resp.json()
    print(f"取得件数: {len(items)}件（最新5件）")
    print()

    sold_count = 0
    platform_missing = 0

    for item in items:
        name     = item.get("name", "")[:40]
        platform = item.get("platform") or ""
        sales    = []
        try:
            raw = item.get("sales_json")
            if isinstance(raw, list):
                sales = raw
            elif isinstance(raw, str) and raw not in ("[]", "null", ""):
                sales = json.loads(raw)
            else:
                sales = []
        except Exception:
            pass

        if not platform:
            platform_missing += 1

        sold_count += len(sales)

        has_sold_at = any(s.get("soldAt") for s in sales)
        has_fee_null = any(s.get("fee") is None for s in sales)

        print(f"  [{platform or '未設定':12}] {name}")
        print(f"    売却数: {len(sales)}件  "
              f"soldAt: {'あり' if has_sold_at else 'なし'}  "
              f"fee null: {'あり' if has_fee_null else 'なし'}")

    print()
    print(f"=== サマリ ===")
    print(f"  platform未設定: {platform_missing}/{len(items)}件")
    print(f"  soldAt: 新規登録分から反映予定")
    print()

    if platform_missing > 0:
        print("⚠️  platform未設定の商品があります。")
        print("   sedori-v3 で商品編集時にプラットフォームを入力してください。")
    else:
        print("✅ 全商品にplatformが設定されています。")

    # ---- 全件数確認 ----
    resp2 = client.get("/rest/v1/items", params={
        "select": "item_id,sales_json",
        "limit":  "1000",
    })
    all_items = resp2.json()
    sold_items = 0
    for item in all_items:
        try:
            raw = item.get("sales_json")
            if isinstance(raw, list):
                sales = raw
            elif isinstance(raw, str) and raw not in ("[]", "null", ""):
                sales = json.loads(raw)
            else:
                sales = []
            if sales:
                sold_items += 1
        except Exception:
            pass

    print()
    print(f"全体: {len(all_items)}件登録 / うち売却済み: {sold_items}件")
    print()
    print("次のステップ:")
    print("  1. config.py の設定確認 ✅")
    print("  2. streamlit run app_new.py で画面から照合テスト")

if __name__ == "__main__":
    main()
