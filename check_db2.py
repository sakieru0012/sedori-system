import config, httpx

client = httpx.Client(
    base_url=config.SUPABASE_URL,
    headers={
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
    },
    timeout=15.0,
)

# 1. エイリアスDBの逆引き確認
from database import _mock_conn
with _mock_conn() as conn:
    rows = conn.execute(
        "SELECT alias FROM product_aliases WHERE canonical_name = ?",
        ("PS2 サクラ大戦V さらば愛しき人よ",)
    ).fetchall()
    print(f"逆引き結果: {len(rows)}件")
    for r in rows:
        print(f"  alias: {r['alias']}")

# 2. Supabase直接検索テスト
print()
resp = client.get("/rest/v1/items", params={
    "select": "item_id,name,platform,sales_json",
    "name": "ilike.*サクラ大戦V*",
    "limit": "5",
})
items = resp.json()
print(f"Supabase検索（サクラ大戦V）: {len(items)}件")
for item in items:
    sales = item.get("sales_json") or []
    print(f"  [{item.get('platform','')}] {item['name'][:50]} 売却:{len(sales)}件")

