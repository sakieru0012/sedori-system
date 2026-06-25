"""
ローカルSQLite（research_items）→ Supabase 移行スクリプト

【方針】
  - SQLiteのデータは削除しない（バックアップとして保持）
  - Supabaseに同じ内容をコピーする
  - 既に移行済みのデータは重複登録しない

【使い方】
  python migrate_research.py --preview   確認のみ
  python migrate_research.py --migrate   本番移行
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

    # ---- SQLiteから全件取得 ----
    with _mock_conn() as conn:
        rows = conn.execute("""
            SELECT canonical_name, platform, estimated_sell_price,
                   listing_price, doubtful, memo
            FROM research_items
        """).fetchall()
        local_items = [dict(r) for r in rows]

    print(f"ローカルSQLite: {len(local_items)}件")

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

    # ---- Supabase側の既存確認 ----
    try:
        resp = client.get("/rest/v1/research_items", params={"select": "canonical_name"})
        if resp.status_code != 200:
            print(f"Supabase接続エラー: {resp.status_code} {resp.text[:200]}")
            sys.exit(1)
        existing = resp.json()
        existing_names = {item["canonical_name"] for item in existing}
    except Exception as e:
        print(f"Supabase確認エラー: {e}")
        sys.exit(1)

    print(f"Supabase既存: {len(existing_names)}件")

    # ---- 移行対象を抽出（重複除外） ----
    to_migrate = [
        item for item in local_items
        if item["canonical_name"] not in existing_names
    ]
    skipped = len(local_items) - len(to_migrate)
    print(f"移行対象: {len(to_migrate)}件（スキップ: {skipped}件・既存）")
    print()

    if args.preview:
        print("=== プレビュー（最大20件） ===")
        for item in to_migrate[:20]:
            lp = item.get("listing_price") or 0
            print(
                f"  '{item['canonical_name'][:35]}'"
                f" 予想:{item['estimated_sell_price']}円"
                f" 出品予定:{lp}円"
                f" [{item['platform']}]"
            )
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

        # 1件ずつ送信（research_itemsは件数が少ないので安全に）
        for i, item in enumerate(to_migrate, 1):
            data = {
                "canonical_name"       : item["canonical_name"],
                "platform"             : item["platform"] or "",
                "estimated_sell_price" : item["estimated_sell_price"] or 0,
                "listing_price"        : item.get("listing_price") or 0,
                "memo"                 : item.get("memo") or "",
            }
            try:
                resp = client.post("/rest/v1/research_items", json=data)
                if resp.status_code in (200, 201):
                    success += 1
                    if i % 10 == 0 or i == len(to_migrate):
                        print(f"  [{i}/{len(to_migrate)}] 成功...")
                else:
                    failed += 1
                    print(f"  [{i}] 失敗: {resp.status_code} {resp.text[:80]}")
            except Exception as e:
                failed += 1
                print(f"  [{i}] エラー: {e}")
            time.sleep(0.05)

        print()
        print("=== 完了 ===")
        print(f"  成功: {success}件")
        if failed:
            print(f"  失敗: {failed}件")
        print()
        print("ローカルSQLiteのデータはそのまま残っています（バックアップ）")


if __name__ == "__main__":
    main()
