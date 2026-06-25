import sys, os
sys.path.insert(0, '.')
import config, httpx

client = httpx.Client(
    base_url=config.SUPABASE_URL,
    headers={"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"},
    timeout=15.0,
)

# Supabaseのresearch_itemsを直接確認
resp = client.get("/rest/v1/research_items", params={"select": "*", "limit": "5"})
print(f"Supabase research_items件数チェック: {resp.status_code}")
rows = resp.json()
print(f"取得件数: {len(rows)}")
for r in rows:
    print(f"  {r}")

print()

# SQLiteのresearch_itemsを確認
from database import _mock_conn
with _mock_conn() as conn:
    rows = conn.execute("SELECT id, canonical_name, estimated_sell_price FROM research_items ORDER BY id").fetchall()
    print(f"SQLite research_items件数: {len(rows)}")
    for r in rows:
        print(f"  [{r['id']}] {r['canonical_name']} / {r['estimated_sell_price']}円")
