import config
from database import SalesDB, _mock_conn

# エイリアスDB確認
with _mock_conn() as conn:
    rows = conn.execute(
        "SELECT alias, canonical_name FROM product_aliases WHERE alias LIKE ?",
        ("%トレジャーハンター%",)
    ).fetchall()
    print(f"トレジャーハンター エイリアス: {len(rows)}件")
    for r in rows:
        print(f"  '{r['alias']}' -> '{r['canonical_name']}'")

# ウォッチリスト解析後の商品名でテスト
from yahoo_parser import _clean_name
test_names = [
    "◆スーパーファミコン/スーファミ/SFC トレジャーハンターG ソフト",
    "◆スーパーファミコン トレジャーハンターG ソフト",
]
print()
for raw in test_names:
    cleaned = _clean_name(raw)
    print(f"クリーニング後: '{cleaned}'")

# name_resolver で候補確認
from name_resolver import NameResolver
resolver = NameResolver()
resolver._supabase_cache = []
resolver._cache_loaded = True  # キャッシュなしで確認

result = resolver.resolve("スーパーファミコン トレジャーハンターG", "スーパーファミコン")
print(f"\n名寄せ結果:")
print(f"  確定済み: {result.is_confirmed}")
print(f"  正規名: {result.canonical_name}")
print(f"  候補数: {len(result.candidates)}")
