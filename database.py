"""
データベース接続層

【設計方針】
- SalesDB: Supabase（本番）/ SQLiteモック（開発中）を切り替え可能
- ResearchDB: ローカルSQLite固定（リサーチ結果はローカル管理）
- 接続先は config.py の SUPABASE_URL の有無で自動判定

Supabase未接続の間はSQLiteモックで全機能が動作する。
sedori-v3の改修完了後、config.pyにSupabase接続情報を追加するだけで切り替わる。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# データクラス
# ============================================================

@dataclass
class SalesRecord:
    """売買実績1件"""
    id: Optional[int]
    name: str                    # 商品名（正規化前）
    canonical_name: str          # 正規化後商品名
    platform: str                # PS2 / SFC / ゲームボーイ 等
    purchase_price: int          # 仕入れ価格（bid_price + ship_in）
    sold_price: int              # 販売価格
    fee: int                     # 販売手数料
    ship_out: int                # 発送送料
    profit: int                  # 利益額
    platform_sold: str           # 販売先（mercari / yahooflea 等）
    sold_at: Optional[str]       # 販売日
    source: str = "ヤフオク"      # 仕入れ先

@dataclass
class SalesSummary:
    """商品ごとの売買実績サマリ"""
    canonical_name: str
    platform: str
    sales_count: int
    avg_sold_price: int
    max_sold_price: int
    avg_purchase_price: int
    avg_profit: int
    last_sold_at: Optional[str]
    recommended_max_bid: int
    records: list = field(default_factory=list)  # 個別実績リスト

@dataclass
class ResearchItem:
    """リサーチDB 1件"""
    id: Optional[int]
    name: str
    canonical_name: str
    platform: str
    estimated_sell_price: int        # 手動入力の予想売価（入札判断用）
    recommended_max_bid: int         # 計算済み推奨上限入札額
    listing_price: int = 0           # 出品予定価格
    doubtful: bool = False           # 売れるか怪しい場合はTrue
    basis: str = "手動予想"
    memo: str = ""
    created_at: str = ""
    updated_at: str = ""


# ============================================================
# SQLite モックDB（Supabase未接続時）
# ============================================================

MOCK_DB_PATH = Path("sedori_mock.db")

def _init_mock_db(conn: sqlite3.Connection):
    """モックDB スキーマ作成"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sales_records (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            canonical_name   TEXT NOT NULL,
            platform         TEXT DEFAULT '',
            purchase_price   INTEGER DEFAULT 0,
            sold_price       INTEGER DEFAULT 0,
            fee              INTEGER DEFAULT 0,
            ship_out         INTEGER DEFAULT 0,
            profit           INTEGER DEFAULT 0,
            platform_sold    TEXT DEFAULT '',
            sold_at          TEXT,
            source           TEXT DEFAULT 'ヤフオク',
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS research_items (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT NOT NULL,
            canonical_name        TEXT NOT NULL,
            platform              TEXT DEFAULT '',
            estimated_sell_price  INTEGER DEFAULT 0,
            recommended_max_bid   INTEGER DEFAULT 0,
            listing_price         INTEGER DEFAULT 0,
            doubtful              INTEGER DEFAULT 0,
            basis                 TEXT DEFAULT '手動予想',
            memo                  TEXT DEFAULT '',
            created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS product_aliases (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            alias          TEXT NOT NULL UNIQUE,
            canonical_name TEXT NOT NULL,
            platform       TEXT DEFAULT '',
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 既存DBへのマイグレーション（listing_priceカラムがない場合に追加）
    try:
        conn.execute("ALTER TABLE research_items ADD COLUMN listing_price INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE research_items ADD COLUMN doubtful INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()

@contextmanager
def _mock_conn():
    conn = sqlite3.connect(MOCK_DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_mock_db(conn)
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# SalesDB（売買実績）
# ============================================================

class SalesDB:
    """
    売買実績DBへのアクセスクラス。

    use_supabase=True  → Supabase（sedori-v3）に接続
    use_supabase=False → ローカルSQLiteモックを使用
    """

    def __init__(self, use_supabase: bool = False,
                 supabase_url: str = "", supabase_key: str = ""):
        self.use_supabase = use_supabase
        self._url = supabase_url
        self._key = supabase_key
        if use_supabase:
            self._init_supabase()
        else:
            logger.info("SalesDB: SQLiteモックを使用中")

    def _init_supabase(self):
        try:
            import httpx
            self._client = httpx.Client(
                base_url=self._url,
                headers={
                    "apikey": self._key,
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            logger.info("SalesDB: Supabase接続OK")
        except ImportError:
            logger.warning("httpxが未インストール。pip install httpx")
            self.use_supabase = False

    # ---- Supabase からのデータ取得 ----

    def _fetch_supabase_items(self, name_query: str = "") -> list[dict]:
        """
        Supabase の items テーブルから取得する。
        name_query が指定されたら部分一致フィルタを適用。
        """
        params = {"select": "item_id,name,platform,bid_price,ship_in,sales_json"}
        if name_query:
            # Supabase REST API の正しいフィルタ形式
            # params に直接渡すとURLエンコードされて壊れるため
            # url に直接クエリを追加する
            encoded = name_query.replace(" ", "%20")
            url = f"/rest/v1/items?select=item_id,name,platform,bid_price,ship_in,sales_json&name=ilike.*{encoded}*"
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"Supabase取得エラー: {e}")
                return []
        try:
            resp = self._client.get("/rest/v1/items", params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Supabase取得エラー: {e}")
            return []

    def _parse_supabase_item(self, item: dict) -> list[SalesRecord]:
        """
        Supabase の items レコードを SalesRecord のリストに変換する。
        実際のデータ形式:
          sales_json: [{"id":..., "platform":"mercari", "sellPrice":1000,
                        "shipOut":200, "fee":null, "soldAt":"2024-03-15"}]

        - fee は null の場合があるので 0 にフォールバック
        - soldAt は新規登録分から入る（既存データは None）
        - platform は items テーブルのカラムを使用（sedori-v3で追加済み）
        """
        records = []
        sales_list = []
        try:
            raw = item.get("sales_json")
            if raw is None:
                sales_list = []
            elif isinstance(raw, list):
                sales_list = raw          # JSONB型：すでにリスト
            elif isinstance(raw, str):
                sales_list = json.loads(raw) if raw not in ("[]", "null", "") else []
            else:
                sales_list = []
        except (json.JSONDecodeError, TypeError):
            pass

        purchase_price = (item.get("bid_price") or 0) + (item.get("ship_in") or 0)

        for s in sales_list:
            sold_price = s.get("sellPrice") or 0
            fee        = s.get("fee") or 0        # null → 0
            ship_out   = s.get("shipOut") or 0
            profit     = sold_price - fee - ship_out - purchase_price
            records.append(SalesRecord(
                id             = item.get("item_id"),
                name           = item.get("name", ""),
                canonical_name = item.get("name", ""),  # 取り込みウィザードで正規化予定
                platform       = item.get("platform", ""),  # itemsテーブルのplatformカラム
                purchase_price = purchase_price,
                sold_price     = sold_price,
                fee            = fee,
                ship_out       = ship_out,
                profit         = profit,
                platform_sold  = s.get("platform", ""),  # sales_json内のplatform（販売先）
                sold_at        = s.get("soldAt"),         # 新規登録分から入る
                source         = "ヤフオク",
            ))
        return records

    # ---- 公開API ----

    def find_by_name(self, canonical_name: str,
                     platform: str = "") -> Optional[SalesSummary]:
        """
        正規化済み商品名で実績を検索し、サマリを返す。
        実績なしの場合は None。
        """
        records = self._get_records(canonical_name, platform)
        if not records:
            return None
        return self._summarize(canonical_name, platform, records)

    def _get_records(self, canonical_name: str,
                     platform: str = "") -> list[SalesRecord]:
        if self.use_supabase:
            records = []
            seen_ids: set = set()

            def add_records(items):
                for item in items:
                    for rec in self._parse_supabase_item(item):
                        if rec.id not in seen_ids:
                            seen_ids.add(rec.id)
                            records.append(rec)

            # ① canonical_name で完全一致検索（新規登録分・正規化済み）
            encoded = canonical_name.replace(" ", "%20")
            url = (
                f"/rest/v1/items"
                f"?select=item_id,name,platform,bid_price,ship_in,sales_json,canonical_name"
                f"&canonical_name=eq.{encoded}"
                f"&limit=100"
            )
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                add_records(resp.json())
            except Exception as e:
                logger.warning(f"canonical_name検索エラー: {e}")

            # ② ヒットしなければエイリアス逆引き → ilike フォールバック
            if not records:
                search_names = set([canonical_name])
                try:
                    with _mock_conn() as conn:
                        rows = conn.execute(
                            "SELECT alias FROM product_aliases WHERE canonical_name = ?",
                            (canonical_name,)
                        ).fetchall()
                        for row in rows:
                            search_names.add(row["alias"])
                except Exception:
                    pass

                for search_name in search_names:
                    items = self._fetch_supabase_items(search_name)
                    add_records(items)

            return records
        else:
            with _mock_conn() as conn:
                q = "SELECT * FROM sales_records WHERE canonical_name LIKE ?"
                params = [f"%{canonical_name}%"]
                if platform:
                    q += " AND platform = ?"
                    params.append(platform)
                rows = conn.execute(q, params).fetchall()
                return [SalesRecord(
                    id=r["id"], name=r["name"], canonical_name=r["canonical_name"],
                    platform=r["platform"], purchase_price=r["purchase_price"],
                    sold_price=r["sold_price"], fee=r["fee"], ship_out=r["ship_out"],
                    profit=r["profit"], platform_sold=r["platform_sold"],
                    sold_at=r["sold_at"], source=r["source"],
                ) for r in rows]

    def _summarize(self, canonical_name: str, platform: str,
                   records: list[SalesRecord]) -> SalesSummary:
        from profit_calculator import calc_max_bid
        sold_prices     = [r.sold_price     for r in records if r.sold_price]
        purchase_prices = [r.purchase_price for r in records if r.purchase_price]
        profits         = [r.profit         for r in records]
        sold_dates      = sorted([r.sold_at for r in records if r.sold_at], reverse=True)

        avg_sold = int(sum(sold_prices) / len(sold_prices)) if sold_prices else 0

        # 個別実績リスト（sold_at の新しい順）
        detail_records = sorted(
            records,
            key=lambda r: r.sold_at or "",
            reverse=True,
        )

        return SalesSummary(
            canonical_name      = canonical_name,
            platform            = platform,
            sales_count         = len(records),
            avg_sold_price      = avg_sold,
            max_sold_price      = max(sold_prices) if sold_prices else 0,
            avg_purchase_price  = int(sum(purchase_prices) / len(purchase_prices)) if purchase_prices else 0,
            avg_profit          = int(sum(profits) / len(profits)) if profits else 0,
            last_sold_at        = sold_dates[0] if sold_dates else None,
            recommended_max_bid = calc_max_bid(avg_sold) if avg_sold else 0,
            records             = detail_records,
        )

    def add_mock_record(self, record: SalesRecord) -> int:
        """モックDB にテスト用レコードを追加する"""
        with _mock_conn() as conn:
            cur = conn.execute("""
                INSERT INTO sales_records
                (name, canonical_name, platform, purchase_price, sold_price,
                 fee, ship_out, profit, platform_sold, sold_at, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (record.name, record.canonical_name, record.platform,
                  record.purchase_price, record.sold_price, record.fee,
                  record.ship_out, record.profit, record.platform_sold,
                  record.sold_at, record.source))
            conn.commit()
            return cur.lastrowid


# ============================================================
# ResearchDB（リサーチDB）
# ============================================================

# ============================================================
# ResearchDB（リサーチDB）
# Supabase優先・SQLiteフォールバック
# ============================================================

class ResearchDB:
    """
    リサーチDB。

    Supabase接続情報が config.py にあれば Supabase に保存し
    sedori-v3 から参照できるようにする。
    接続情報がなければ SQLite ローカルに保存（フォールバック）。
    """

    def __init__(self):
        self._use_supabase = False
        self._client = None
        try:
            import config, httpx
            url = getattr(config, "SUPABASE_URL", "")
            key = getattr(config, "SUPABASE_KEY", "")
            if url and key:
                self._client = httpx.Client(
                    base_url=url,
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    timeout=15.0,
                )
                self._use_supabase = True
                logger.info("ResearchDB: Supabaseモード")
        except Exception:
            pass

    def _to_item(self, row: dict) -> ResearchItem:
        """Supabaseのレコードを ResearchItem に変換"""
        return ResearchItem(
            id                   = row.get("id"),
            name                 = row.get("canonical_name", ""),
            canonical_name       = row.get("canonical_name", ""),
            platform             = row.get("platform", ""),
            estimated_sell_price = row.get("estimated_sell_price", 0) or 0,
            recommended_max_bid  = 0,  # Supabaseには保存しない（都度計算）
            listing_price        = row.get("listing_price", 0) or 0,
            doubtful             = bool(row.get("doubtful", False)),
            basis                = "手動予想",
            memo                 = row.get("memo", ""),
            created_at           = str(row.get("created_at", "")),
            updated_at           = str(row.get("updated_at", "")),
        )

    def find(self, canonical_name: str,
             platform: str = "") -> Optional[ResearchItem]:
        if self._use_supabase:
            try:
                encoded = canonical_name.replace(" ", "%20")
                url = (
                    f"/rest/v1/research_items"
                    f"?canonical_name=ilike.*{encoded}*"
                    f"&limit=1&order=updated_at.desc"
                )
                if platform:
                    url += f"&platform=eq.{platform}"
                resp = self._client.get(url)
                resp.raise_for_status()
                rows = resp.json()
                if rows:
                    item = self._to_item(rows[0])
                    from profit_calculator import calc_max_bid
                    item.recommended_max_bid = calc_max_bid(item.estimated_sell_price) \
                        if item.estimated_sell_price > 0 else 0
                    return item
                # Supabase に 0件 → SQLite にフォールバック
            except Exception as e:
                logger.warning(f"ResearchDB.find Supabaseエラー: {e}")

        # SQLite フォールバック
        with _mock_conn() as conn:
            q = "SELECT * FROM research_items WHERE canonical_name LIKE ?"
            params = [f"%{canonical_name}%"]
            if platform:
                q += " AND platform = ?"
                params.append(platform)
            q += " ORDER BY updated_at DESC LIMIT 1"
            row = conn.execute(q, params).fetchone()
            if not row:
                return None
            return ResearchItem(
                id                   = row["id"],
                name                 = row["name"],
                canonical_name       = row["canonical_name"],
                platform             = row["platform"],
                estimated_sell_price = row["estimated_sell_price"],
                recommended_max_bid  = row["recommended_max_bid"],
                listing_price        = row["listing_price"] if "listing_price" in row.keys() else 0,
                doubtful             = bool(row["doubtful"]) if "doubtful" in row.keys() else False,
                basis                = row["basis"],
                memo                 = row["memo"],
                created_at           = row["created_at"],
                updated_at           = row["updated_at"],
            )

    def save(self, item: ResearchItem) -> int:
        """Supabase（優先）またはSQLiteに保存する"""
        from profit_calculator import calc_max_bid

        if self._use_supabase:
            try:
                data = {
                    "canonical_name"       : item.canonical_name,
                    "platform"             : item.platform,
                    "estimated_sell_price" : item.estimated_sell_price,
                    "listing_price"        : item.listing_price,
                    "memo"                 : item.memo,
                }
                # 既存チェック
                encoded = item.canonical_name.replace(" ", "%20")
                check_url = (
                    f"/rest/v1/research_items"
                    f"?canonical_name=ilike.*{encoded}*"
                    f"&platform=eq.{item.platform}&limit=1"
                )
                resp = self._client.get(check_url)
                existing = resp.json()

                if existing:
                    # UPDATE
                    row_id = existing[0]["id"]
                    self._client.patch(
                        f"/rest/v1/research_items?id=eq.{row_id}",
                        json=data,
                    )
                    logger.info(f"ResearchDB更新（Supabase）: {item.canonical_name}")
                    return row_id
                else:
                    # INSERT
                    resp = self._client.post(
                        "/rest/v1/research_items",
                        json=data,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    new_id = result[0]["id"] if result else 0
                    logger.info(f"ResearchDB登録（Supabase）: {item.canonical_name}")
                    return new_id
            except Exception as e:
                logger.warning(f"ResearchDB.save Supabaseエラー: {e} → SQLiteに保存")

        # SQLite フォールバック
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _mock_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM research_items WHERE canonical_name = ? AND platform = ?",
                (item.canonical_name, item.platform)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE research_items
                    SET estimated_sell_price=?, recommended_max_bid=?,
                        listing_price=?, doubtful=?, basis=?, memo=?, updated_at=?
                    WHERE id=?
                """, (item.estimated_sell_price, item.recommended_max_bid,
                      item.listing_price, int(item.doubtful),
                      item.basis, item.memo, now, existing["id"]))
                conn.commit()
                return existing["id"]
            else:
                cur = conn.execute("""
                    INSERT INTO research_items
                    (name, canonical_name, platform, estimated_sell_price,
                     recommended_max_bid, listing_price, doubtful, basis, memo, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (item.name, item.canonical_name, item.platform,
                      item.estimated_sell_price, item.recommended_max_bid,
                      item.listing_price, int(item.doubtful),
                      item.basis, item.memo, now, now))
                conn.commit()
                return cur.lastrowid

    def list_all(self) -> list[ResearchItem]:
        if self._use_supabase:
            try:
                resp = self._client.get(
                    "/rest/v1/research_items?order=updated_at.desc&limit=1000"
                )
                resp.raise_for_status()
                rows = resp.json()
                if rows:
                    from profit_calculator import calc_max_bid
                    items = []
                    for row in rows:
                        item = self._to_item(row)
                        item.recommended_max_bid = calc_max_bid(item.estimated_sell_price) \
                            if item.estimated_sell_price > 0 else 0
                        items.append(item)
                    return items
                # Supabase に 0件 → SQLite にフォールバック
            except Exception as e:
                logger.warning(f"ResearchDB.list_all Supabaseエラー: {e}")

        # SQLite フォールバック
        with _mock_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM research_items ORDER BY updated_at DESC"
            ).fetchall()
            return [ResearchItem(
                id=r["id"], name=r["name"], canonical_name=r["canonical_name"],
                platform=r["platform"],
                estimated_sell_price=r["estimated_sell_price"],
                recommended_max_bid=r["recommended_max_bid"],
                listing_price=r["listing_price"] if "listing_price" in r.keys() else 0,
                doubtful=bool(r["doubtful"]) if "doubtful" in r.keys() else False,
                basis=r["basis"], memo=r["memo"],
                created_at=r["created_at"], updated_at=r["updated_at"],
            ) for r in rows]


# ============================================================
# ProductAliasDB（別名辞書）
# ============================================================

class ProductAliasDB:
    """
    商品名の別名辞書DB。

    Supabase接続情報があればSupabaseを優先して使用し、
    sedori-v3やスマホからのアクセスでもデータが永続化される。
    接続情報がなければローカルSQLiteにフォールバック（従来動作）。

    ローカルSQLiteのデータは削除されず、バックアップとして残る。
    """

    def __init__(self):
        self._use_supabase = False
        self._client = None
        try:
            import config, httpx
            url = getattr(config, "SUPABASE_URL", "")
            key = getattr(config, "SUPABASE_KEY", "")
            if url and key:
                self._client = httpx.Client(
                    base_url=url,
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    timeout=15.0,
                )
                # テーブルが存在するか軽く確認（失敗してもSQLiteにフォールバック）
                resp = self._client.get(
                    "/rest/v1/product_aliases", params={"select": "alias", "limit": "1"}
                )
                if resp.status_code == 200:
                    self._use_supabase = True
                    logger.info("ProductAliasDB: Supabaseモード")
                else:
                    logger.info(
                        "ProductAliasDB: product_aliasesテーブル未作成のためSQLiteを使用"
                    )
        except Exception:
            pass

    def find_canonical(self, name: str) -> Optional[str]:
        """別名から正規名を返す。なければNone。"""
        if self._use_supabase:
            try:
                encoded = name.replace(" ", "%20")
                resp = self._client.get(
                    "/rest/v1/product_aliases",
                    params={"alias": f"eq.{encoded}", "select": "canonical_name", "limit": "1"},
                )
                rows = resp.json()
                if rows:
                    return rows[0]["canonical_name"]
                return None
            except Exception as e:
                logger.warning(f"ProductAliasDB.find_canonical Supabaseエラー: {e}")

        with _mock_conn() as conn:
            row = conn.execute(
                "SELECT canonical_name FROM product_aliases WHERE alias = ?",
                (name,)
            ).fetchone()
            return row["canonical_name"] if row else None

    def add_alias(self, alias: str, canonical_name: str,
                  platform: str = "") -> None:
        if self._use_supabase:
            try:
                # 既存チェック → UPSERT相当
                encoded = alias.replace(" ", "%20")
                resp = self._client.get(
                    "/rest/v1/product_aliases",
                    params={"alias": f"eq.{encoded}", "select": "id", "limit": "1"},
                )
                existing = resp.json()
                if existing:
                    self._client.patch(
                        f"/rest/v1/product_aliases?id=eq.{existing[0]['id']}",
                        json={"canonical_name": canonical_name, "platform": platform},
                    )
                else:
                    self._client.post(
                        "/rest/v1/product_aliases",
                        json={"alias": alias, "canonical_name": canonical_name,
                              "platform": platform},
                    )
                logger.info(f"別名追加（Supabase）: '{alias}' → '{canonical_name}'")
                return
            except Exception as e:
                logger.warning(f"ProductAliasDB.add_alias Supabaseエラー: {e} → SQLiteに保存")

        with _mock_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO product_aliases
                (alias, canonical_name, platform)
                VALUES (?,?,?)
            """, (alias, canonical_name, platform))
            conn.commit()
            logger.info(f"別名追加（SQLite）: '{alias}' → '{canonical_name}'")

    def list_canonical_names(self) -> list[dict]:
        """登録済みの正規名一覧（重複除去）を返す。candidatesの検索対象として使用。"""
        if self._use_supabase:
            try:
                resp = self._client.get(
                    "/rest/v1/product_aliases",
                    params={"select": "canonical_name,platform", "limit": "2000"},
                )
                rows = resp.json()
                seen = set()
                result = []
                for r in rows:
                    cn = r.get("canonical_name", "")
                    if cn and cn not in seen:
                        seen.add(cn)
                        result.append({"canonical_name": cn, "platform": r.get("platform", "")})
                return result
            except Exception as e:
                logger.warning(f"ProductAliasDB.list_canonical_names Supabaseエラー: {e}")

        with _mock_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT canonical_name, platform FROM product_aliases"
            ).fetchall()
            return [{"canonical_name": r["canonical_name"], "platform": r["platform"]} for r in rows]

    def list_all(self) -> list[dict]:
        """登録済みエイリアス一覧（元の商品名→正規名の対応）を返す。"""
        if self._use_supabase:
            try:
                resp = self._client.get(
                    "/rest/v1/product_aliases",
                    params={"select": "alias,canonical_name,platform,created_at",
                            "order": "created_at.desc", "limit": "2000"},
                )
                return resp.json()
            except Exception as e:
                logger.warning(f"ProductAliasDB.list_all Supabaseエラー: {e}")

        with _mock_conn() as conn:
            rows = conn.execute(
                "SELECT alias, canonical_name, platform, created_at "
                "FROM product_aliases ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
