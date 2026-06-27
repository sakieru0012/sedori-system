from database import _mock_conn
with _mock_conn() as conn:
    cnt = conn.execute('SELECT COUNT(*) as cnt FROM research_items').fetchone()
    print(f'SQLite件数: {cnt["cnt"]}件')
    rows = conn.execute('SELECT id, canonical_name FROM research_items ORDER BY id DESC LIMIT 10').fetchall()
    print('最新10件:')
    for r in rows:
        print(f'  [{r["id"]}] {r["canonical_name"]}')
