"""
Supabase items テーブルの platform カラムを商品名から自動推定して一括更新するスクリプト

【実行手順】
  Step1: プレビュー（更新なし・確認のみ）
    python update_platform.py --preview

  Step2: 内容を確認してから本番更新
    python update_platform.py --update

  Step3: 特定カテゴリだけ確認したい場合
    python update_platform.py --preview --category PS2
"""

import argparse
import logging
import sys
import time
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def infer_platform(name: str) -> str:
    """
    商品名からプラットフォームを推定する。
    yahoo_parser._infer_category() と同じロジックを使用。
    """
    import re

    rules = [
        (re.compile(r"PlayStation\s*VITA|PS\s*VITA",                   re.I), "VITA"),
        (re.compile(r"PlayStation\s*Portable|PSP",                     re.I), "PSP"),
        (re.compile(r"PlayStation\s*5|PS\s*5\b",                       re.I), "PS5"),
        (re.compile(r"PlayStation\s*4|PS\s*4\b",                       re.I), "PS4"),
        (re.compile(r"PlayStation\s*3|PS\s*3\b",                       re.I), "PS3"),
        (re.compile(r"PlayStation\s*2|PS\s*2\b|プレイステーション\s*2|プレステ\s*2", re.I), "PS2"),
        (re.compile(r"PlayStation\s*1|プレイステーション(?!2|3|4|5|Portable|VITA)", re.I), "PS1"),
        (re.compile(r"\bPS1\b",                                        re.I), "PS1"),
        (re.compile(r"\bPS2\b|PS2ソフト",                              re.I), "PS2"),
        (re.compile(r"\bPS3\b|PS3ソフト",                              re.I), "PS3"),
        (re.compile(r"\bPS4\b|PS4ソフト",                              re.I), "PS4"),
        (re.compile(r"\bPS5\b|PS5ソフト",                              re.I), "PS5"),
        (re.compile(r"Dreamcast|ドリームキャスト",                       re.I), "DC"),
        (re.compile(r"セガサターン|SEGA\s*SATURN",                       re.I), "SS"),
        (re.compile(r"スーパーファミコン|スーファミ|\bSFC\b|スーパーファミコンソフト", re.I), "スーパーファミコン"),
        (re.compile(r"ファミリーコンピュータ|ファミコン|\bFC\b|ファミコンソフト",    re.I), "ファミコン"),
        (re.compile(r"NINTENDO\s*SWITCH|ニンテンドースイッチ",             re.I), "Switch"),
        (re.compile(r"new\s*NINTENDO\s*3DS|NINTENDO\s*3DS|ニンテンドー3DS|3DSソフト", re.I), "3DS"),
        (re.compile(r"NINTENDO\s*DS|ニンテンドーDS|\bNDS\b|ニンテンドーDSソフト",  re.I), "NDS"),
        (re.compile(r"GAME\s*BOY\s*ADVANCE|ゲームボーイアドバンス|\bGBA\b", re.I), "GBA"),
        (re.compile(r"GAME\s*BOY|ゲームボーイ|\bGB\b",                   re.I), "ゲームボーイ"),
        (re.compile(r"XBOX\s*360",                                     re.I), "Xbox360"),
        (re.compile(r"\bWii\s*U\b",                                    re.I), "WiiU"),
        (re.compile(r"\bWii\b|Wiiソフト",                              re.I), "Wii"),
        (re.compile(r"\b3DO\b",                                        re.I), "3DO"),
        (re.compile(r"メガドライブ|MEGA\s*DRIVE",                        re.I), "MD"),
        (re.compile(r"PCエンジン|PC-ENGINE",                             re.I), "PCE"),
        (re.compile(r"PSPソフト",                                       re.I), "PSP"),
        (re.compile(r"PSVITAソフト|PS\s*VITAソフト",                    re.I), "VITA"),
        # トレカはplatform=""のままにする（将来別カテゴリで管理）
    ]

    for pattern, platform in rules:
        if pattern.search(name):
            return platform
    return ""   # 推定不能


def fetch_all_items(client) -> list[dict]:
    """全件取得（1000件制限を超える場合はページング）"""
    all_items = []
    offset = 0
    limit  = 1000

    while True:
        resp = client.get("/rest/v1/items", params={
            "select": "item_id,name,platform",
            "limit":  str(limit),
            "offset": str(offset),
            "order":  "item_id.asc",
        })
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return all_items


def update_platform(client, item_id: int, platform: str) -> bool:
    """1件のplatformを更新する"""
    resp = client.patch(
        f"/rest/v1/items",
        params={"item_id": f"eq.{item_id}"},
        json={"platform": platform},
    )
    return resp.status_code in (200, 204)


def main():
    parser = argparse.ArgumentParser(description="platform カラム一括更新ツール")
    parser.add_argument("--preview",  action="store_true", help="確認のみ（更新しない）")
    parser.add_argument("--update",   action="store_true", help="本番更新を実行")
    parser.add_argument("--category", default="",          help="特定カテゴリのみ表示（例: PS2）")
    args = parser.parse_args()

    if not args.preview and not args.update:
        parser.print_help()
        sys.exit(0)

    # ---- Supabase接続 ----
    try:
        import config, httpx
        url = getattr(config, "SUPABASE_URL", "")
        key = getattr(config, "SUPABASE_KEY", "")
        if not url or not key:
            print("❌ config.py に SUPABASE_URL / SUPABASE_KEY が未設定です")
            sys.exit(1)
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        sys.exit(1)

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

    # ---- 全件取得 ----
    print(f"Supabase から全件取得中...")
    items = fetch_all_items(client)
    print(f"取得: {len(items)}件\n")

    # ---- 推定 ----
    results = []
    for item in items:
        current  = item.get("platform") or ""
        inferred = infer_platform(item.get("name", ""))
        results.append({
            "item_id"  : item["item_id"],
            "name"     : item.get("name", ""),
            "current"  : current,
            "inferred" : inferred,
            "needs_update": not current and bool(inferred),  # 未設定かつ推定成功
        })

    # ---- フィルタ ----
    if args.category:
        display = [r for r in results if r["inferred"] == args.category]
    else:
        display = results

    # ---- サマリ ----
    needs_update  = [r for r in results if r["needs_update"]]
    already_set   = [r for r in results if r["current"]]
    cannot_infer  = [r for r in results if not r["current"] and not r["inferred"]]

    print(f"=== 推定結果サマリ ===")
    print(f"  全件         : {len(results)}件")
    print(f"  設定済み     : {len(already_set)}件（スキップ）")
    print(f"  更新対象     : {len(needs_update)}件")
    print(f"  推定不能     : {len(cannot_infer)}件")
    print()

    # カテゴリ別内訳
    counter = Counter(r["inferred"] for r in needs_update if r["inferred"])
    print(f"=== カテゴリ別内訳（更新対象） ===")
    for cat, cnt in sorted(counter.items(), key=lambda x: -x[1]):
        print(f"  {cat:20} : {cnt}件")
    print()

    # ---- プレビュー表示 ----
    if args.preview:
        filter_list = [r for r in display if r["needs_update"]] if not args.category \
                      else display
        print(f"=== {'[' + args.category + '] ' if args.category else ''}更新プレビュー ===")

        if not filter_list:
            print("  該当なし")
        else:
            for r in filter_list[:50]:  # 最大50件表示
                mark = "→" if r["inferred"] else "?"
                print(f"  [{r['inferred']:20}] {mark} {r['name'][:50]}")
            if len(filter_list) > 50:
                print(f"  ... 他 {len(filter_list)-50} 件")

        print()

        if cannot_infer:
            print(f"=== 推定不能（{len(cannot_infer)}件）===")
            for r in cannot_infer[:20]:
                print(f"  ? {r['name'][:55]}")
            if len(cannot_infer) > 20:
                print(f"  ... 他 {len(cannot_infer)-20} 件")
            print()

        print("プレビュー完了。本番更新は --update オプションで実行してください。")

    # ---- 本番更新 ----
    if args.update:
        if not needs_update:
            print("更新対象がありません。")
            return

        print(f"=== 本番更新開始: {len(needs_update)}件 ===")
        print("（Ctrl+C で中断できます）")
        print()

        success = 0
        failed  = 0

        for i, r in enumerate(needs_update, 1):
            ok = update_platform(client, r["item_id"], r["inferred"])
            if ok:
                success += 1
                if i % 10 == 0 or i == len(needs_update):
                    print(f"  [{i}/{len(needs_update)}] {success}件成功...")
            else:
                failed += 1
                print(f"  ❌ 失敗: {r['name'][:40]}")
            time.sleep(0.05)   # レート制限対策

        print()
        print(f"=== 完了 ===")
        print(f"  成功: {success}件")
        if failed:
            print(f"  失敗: {failed}件")


if __name__ == "__main__":
    main()
