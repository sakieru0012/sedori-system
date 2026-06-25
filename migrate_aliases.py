"""
ローカルSQLite（product_aliases）→ Supabase 移行スクリプト

【方針】
  - SQLiteのデータは削除しない（バックアップとして保持）
  - Supabaseに同じ内容をコピーする
  - 既に移行済みのデータは重複登録しない

【使い方】
  python migrate_aliases.py --preview   確認のみ
  python migrate_aliases.py --migrate   本番移行
"""

import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()

    if not args.preview and not args.migrate:
        parser.print_help()
        sys.exit(0)

    try:
        import config, httpx
        url = getattr(config, "SUPABASE_URL", "")
        key = getattr(config, "SUPABASE_KEY", "")
        if not url or not key:
            print("config.py に SUPABASE_URL / SUPABASE_KEY が未設定です")
            sys.exit(1)
    except ImportError as e:
        print(f"{e}")
        sys.exit(1)

    from database import _mock_conn

    with _mock_conn() as conn:
        rows = conn.execute(
            "SELECT alias, canonical_name, platform FROM product_aliases"
        ).fetchall()
        local_aliases = [dict(r) for r in rows]

    print(f"ローカルSQLite: {len(local_aliases)}件")

    client = httpx.Client(
        base_url=url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=30.0,
    )

    try:
        resp = client.get("/rest/v1/product_aliases", params={"select": "alias"})
        if resp.status_code != 200:
            print(f"Supabase接続エラー: {resp.status_code}")
            print(f"   {resp.text[:200]}")
            print()
            print("先に create_aliases_table.sql を Supabase SQL Editor で実行してください。")
            sys.exit(1)
        existing = resp.json()
        existing_aliases = {item["alias"] for item in existing}
    except Exception as e:
        print(f"Supabase確認エラー: {e}")
        sys.exit(1)

    print(f"Supabase既存: {len(existing_aliases)}件")

    to_migrate = [
        a for a in local_aliases
        if a["alias"] not in existing_aliases
    ]
    skipped = len(local_aliases) - len(to_migrate)

    print(f"移行対象: {len(to_migrate)}件（スキップ: {skipped}件・既存）")
    print()

    if args.preview:
        print("=== プレビュー（最大20件） ===")
        for a in to_migrate[:20]:
            print(f"  '{a['alias'][:35]}' -> '{a['canonical_name'][:35]}' [{a['platform']}]")
        if len(to_migrate) > 20:
            print(f"  ... 他 {len(to_migrate)-20}件")
        print()
        print("プレビュー完了。本番移行は --migrate オプションで実行してください。")
        print("※ ローカルSQLiteのデータは削除されません（バックアップとして保持）")

    if args.migrate:
        if not to_migrate:
            print("移行対象がありません（全件既に移行済み）")
            return

        print(f"移行開始: {len(to_migrate)}件")
        success, failed = 0, 0

        batch_size = 100
        for i in range(0, len(to_migrate), batch_size):
            batch = to_migrate[i:i+batch_size]
            data = [
                {
                    "alias": a["alias"],
                    "canonical_name": a["canonical_name"],
                    "platform": a["platform"] or "",
                }
                for a in batch
            ]
            try:
                resp = client.post("/rest/v1/product_aliases", json=data)
                if resp.status_code in (200, 201):
                    success += len(batch)
                    print(f"  [{min(i+batch_size, len(to_migrate))}/{len(to_migrate)}] 成功...")
                else:
                    failed += len(batch)
                    print(f"  バッチ失敗: {resp.status_code} {resp.text[:100]}")
            except Exception as e:
                failed += len(batch)
                print(f"  エラー: {e}")
            time.sleep(0.1)

        print()
        print(f"=== 完了 ===")
        print(f"  成功: {success}件")
        if failed:
            print(f"  失敗: {failed}件")
        print()
        print("ローカルSQLiteのデータはそのまま残っています（バックアップ）")


if __name__ == "__main__":
    main()
