import config
from database import SalesDB

db = SalesDB(
    use_supabase=True,
    supabase_url=config.SUPABASE_URL,
    supabase_key=config.SUPABASE_KEY,
)

# 売却済みデータで確認
items = db._fetch_supabase_items("トレジャーハンターG")
print(f"取得: {len(items)}件")

for item in items:
    print(f"\nname: {item.get('name','')}")
    print(f"platform: {item.get('platform','')}")
    sales = item.get("sales_json")
    print(f"sales_json type: {type(sales)}, value: {repr(sales)[:100]}")

    records = db._parse_supabase_item(item)
    print(f"records: {len(records)}件")
    for r in records:
        print(f"  sold:{r.sold_price}円 profit:{r.profit}円 sold_at:{r.sold_at}")

# find_by_name でも確認
print()
result = db.find_by_name("スーパーファミコン トレジャーハンターG")
print(f"find_by_name結果: {result}")
