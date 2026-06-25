import config
from database import SalesDB, _mock_conn

db = SalesDB(
    use_supabase=True,
    supabase_url=config.SUPABASE_URL,
    supabase_key=config.SUPABASE_KEY,
)

# _fetch_supabase_items を直接呼ぶ
print("=== _fetch_supabase_items 直接テスト ===")
result = db._fetch_supabase_items("PS2 サクラ大戦V さらば愛しき人よ")
print(f"結果: {len(result)}件")
for item in result:
    print(f"  {item.get('name','')[:50]}")

# _get_records を直接呼ぶ（エラートレース付き）
print()
print("=== _get_records 直接テスト ===")
try:
    records = db._get_records("PS2 サクラ大戦V さらば愛しき人よ")
    print(f"結果: {len(records)}件")
except Exception as e:
    import traceback
    traceback.print_exc()
