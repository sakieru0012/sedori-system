import config, httpx
from database import _mock_conn, SalesDB

# Step1: エイリアス逆引き確認
canonical = "PS2 サクラ大戦V さらば愛しき人よ"
with _mock_conn() as conn:
    rows = conn.execute(
        "SELECT alias FROM product_aliases WHERE canonical_name = ?",
        (canonical,)
    ).fetchall()
    print(f"逆引き: {len(rows)}件")
    aliases = [r["alias"] for r in rows]
    for a in aliases:
        print(f"  {a}")

# Step2: 各エイリアスでSupabase検索
client = httpx.Client(
    base_url=config.SUPABASE_URL,
    headers={"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"},
    timeout=15.0,
)

print()
for search_name in [canonical] + aliases:
    encoded = search_name.replace(" ", "%20")
    url = f"/rest/v1/items?select=item_id,name,platform,bid_price,ship_in,sales_json&name=ilike.*{encoded}*"
    resp = client.get(url)
    items = resp.json()
    print(f"検索: '{search_name[:40]}' → {len(items)}件")
    for item in items:
        sales = item.get("sales_json") or []
        print(f"  [{item.get('platform','')}] {item['name'][:50]} 売却:{len(sales)}")

# Step3: SalesDB経由で確認
print()
db = SalesDB(use_supabase=True, supabase_url=config.SUPABASE_URL, supabase_key=config.SUPABASE_KEY)
records = db._get_records(canonical)
print(f"_get_records結果: {len(records)}件")
for r in records:
    print(f"  sold:{r.sold_price}円 profit:{r.profit}円")
