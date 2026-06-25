from database import SalesDB, _mock_conn
import config

# エイリアスDB確認
with _mock_conn() as conn:
    cnt = conn.execute('SELECT COUNT(*) as cnt FROM product_aliases').fetchone()
    print(f'エイリアス登録数: {cnt["cnt"]}件')
    rows = conn.execute('SELECT alias, canonical_name FROM product_aliases LIMIT 5').fetchall()
    for r in rows:
        print(f'  {r["alias"][:35]} -> {r["canonical_name"][:35]}')

# Supabase実績検索テスト
db = SalesDB(
    use_supabase=True,
    supabase_url=config.SUPABASE_URL,
    supabase_key=config.SUPABASE_KEY,
)
result = db.find_by_name('PS2 サクラ大戦V さらば愛しき人よ')
print(f'\nサクラ大戦V 検索結果: {result}')

result2 = db.find_by_name('PS2 湾岸ミッドナイト')
print(f'湾岸ミッドナイト 検索結果: {result2}')
