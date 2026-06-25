"""
Supabase実績データ 初回取り込みウィザード

【役割】
  Supabaseの生データ（商品名未正規化）を一括でクリーニング・名寄せして
  エイリアスDBに登録する。

【フロー】
  1. Supabaseから全件取得
  2. _clean_name() でクリーニング
  3. 類似商品をグルーピング（bigram類似度）
  4. ユーザーが正規名を確認・承認
  5. エイリアスDBに一括登録

【使い方】
  app_new.py の「取り込みウィザード」タブから呼び出す
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ImportItem:
    """取り込み1件"""
    item_id: int
    raw_name: str               # Supabaseの生商品名
    cleaned_name: str           # _clean_name() 後
    canonical_name_from_db: str # sedori-v3が生成したcanonical_name（あれば優先）
    platform: str
    sold_count: int
    group_id: Optional[int] = None
    canonical_name: str = ""
    approved: bool = False


@dataclass
class ImportGroup:
    """類似商品グループ"""
    group_id: int
    items: list[ImportItem] = field(default_factory=list)
    suggested_canonical: str = ""   # 推薦正規名（最も売却数が多いもの）
    similarity: float = 0.0


def fetch_supabase_items(url: str, key: str) -> list[ImportItem]:
    """Supabaseから全件取得してImportItemリストに変換"""
    import httpx
    from yahoo_parser import _clean_name
    from update_platform import infer_platform

    client = httpx.Client(
        base_url=url,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30.0,
    )

    # 全件取得（ページング対応）
    all_items = []
    offset, limit = 0, 1000
    while True:
        resp = client.get("/rest/v1/items", params={
            "select": "item_id,name,canonical_name,platform,sales_json",
            "limit" : str(limit),
            "offset": str(offset),
            "order" : "item_id.asc",
        })
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    results = []
    for item in all_items:
        raw_name  = item.get("name", "").strip()
        if not raw_name:
            continue
        cleaned   = _clean_name("◆" + raw_name)
        # sedori-v3が生成したcanonical_nameがあればそちらを優先
        db_canonical = item.get("canonical_name", "").strip()
        platform  = item.get("platform") or infer_platform(raw_name)
        sales     = item.get("sales_json") or []
        sold_cnt  = len(sales) if isinstance(sales, list) else 0

        results.append(ImportItem(
            item_id              = item.get("item_id", 0),
            raw_name             = raw_name,
            cleaned_name         = cleaned,
            canonical_name_from_db = db_canonical,
            platform             = platform,
            sold_count           = sold_cnt,
        ))

    return results


def group_by_similarity(
    items: list[ImportItem],
    threshold: float = 0.6,
) -> list[ImportGroup]:
    """
    類似商品をグルーピングする。

    threshold 以上の類似度があれば同一グループとみなす。
    売却数が多い商品を代表（正規名候補）とする。
    """
    from name_resolver import _similarity

    groups: list[ImportGroup] = []
    assigned: dict[int, int] = {}  # item_id → group_id

    # 売却数の多い順に処理（売れている商品が正規名の代表になりやすい）
    sorted_items = sorted(items, key=lambda x: x.sold_count, reverse=True)

    for item in sorted_items:
        if item.item_id in assigned:
            continue

        # 正規名の優先順位: sedori-v3のcanonical_name > _clean_name()の結果
        best_canonical = item.canonical_name_from_db or item.cleaned_name

        gid = len(groups)
        group = ImportGroup(
            group_id             = gid,
            items                = [item],
            suggested_canonical  = best_canonical,
        )
        assigned[item.item_id] = gid

        # 未割当の商品と類似度チェック
        for other in sorted_items:
            if other.item_id in assigned:
                continue
            sim = _similarity(item.cleaned_name, other.cleaned_name)
            if sim >= threshold:
                group.items.append(other)
                group.similarity = sim
                assigned[other.item_id] = gid

        groups.append(group)

    return groups


def apply_aliases(
    groups: list[ImportGroup],
    approved_only: bool = True,
) -> tuple[int, int]:
    """
    承認済みグループのエイリアスをDBに一括登録する。

    Returns
    -------
    (登録件数, スキップ件数)
    """
    from database import ProductAliasDB
    alias_db = ProductAliasDB()

    registered = 0
    skipped    = 0

    for group in groups:
        if approved_only and not any(item.approved for item in group.items):
            skipped += len(group.items)
            continue

        canonical = group.suggested_canonical
        for item in group.items:
            alias_db.add_alias(item.cleaned_name, canonical, item.platform)
            # 生データの名前もエイリアス登録
            if item.raw_name != item.cleaned_name:
                alias_db.add_alias(item.raw_name, canonical, item.platform)
            # sedori-v3のcanonical_nameも登録（完全一致検索のキーになる）
            if item.canonical_name_from_db and \
               item.canonical_name_from_db != canonical and \
               item.canonical_name_from_db != item.cleaned_name:
                alias_db.add_alias(item.canonical_name_from_db, canonical, item.platform)
            registered += 1

    return registered, skipped
