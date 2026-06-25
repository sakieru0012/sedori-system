"""
商品名名寄せモジュール

【設計方針】
  - 完全自動化しない
  - 一度ユーザーが承認した対応はエイリアスDBに保存
  - 次回以降は自動変換
  - 将来のAI名寄せ補助を差し込める構造

【フロー】
  1. エイリアスDBを検索 → ヒットすれば即変換（確定済み）
  2. 商品マスタから類似候補を提示（未確定）
  3. ユーザーが候補を選択 or 新規正規名を入力
  4. エイリアスDBに保存
"""

from __future__ import annotations

import re
import unicodedata
import logging
from dataclasses import dataclass
from typing import Optional

from database import ProductAliasDB, _mock_conn

logger = logging.getLogger(__name__)


# ============================================================
# 文字列正規化ユーティリティ
# ============================================================

def _normalize_for_search(text: str) -> str:
    """
    検索用に文字列を正規化する。
    全角→半角、カタカナ→ひらがな、小文字化、記号除去。
    """
    # 全角英数→半角
    text = unicodedata.normalize("NFKC", text)
    # 小文字化
    text = text.lower()
    # 記号・スペース除去（ひらがな・カタカナ・漢字・英数字のみ残す）
    text = re.sub(r"[^\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", "", text)
    return text


def _similarity(a: str, b: str) -> float:
    """
    2文字列の類似度を 0.0〜1.0 で返す。
    bigram（2文字N-gram）ベースの Dice 係数を使用。
    外部ライブラリ不要・高速。
    """
    na = _normalize_for_search(a)
    nb = _normalize_for_search(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    def bigrams(s: str) -> set[str]:
        return {s[i:i+2] for i in range(len(s) - 1)}

    sa, sb = bigrams(na), bigrams(nb)
    if not sa or not sb:
        # 1文字の場合は含有チェック
        return 1.0 if (na in nb or nb in na) else 0.0

    intersection = len(sa & sb)
    return 2 * intersection / (len(sa) + len(sb))


# ============================================================
# データクラス
# ============================================================

@dataclass
class ResolutionCandidate:
    """名寄せ候補1件"""
    canonical_name: str
    platform: str
    similarity: float         # 0.0〜1.0
    source: str               # "alias" / "master" / "research" / "sales"
    match_reason: str         # 表示用の一致理由


@dataclass
class ResolutionResult:
    """名寄せ結果"""
    original_name: str
    platform: str
    canonical_name: Optional[str]     # 確定済みの正規名（Noneは未確定）
    is_confirmed: bool                # Trueなら自動変換済み
    candidates: list[ResolutionCandidate]  # 未確定時の候補リスト


# ============================================================
# 名寄せエンジン
# ============================================================

class NameResolver:
    """
    商品名の名寄せを担当するクラス。

    confirmed_only=True の場合、確定済み変換のみ実施（バッチ処理向け）。
    confirmed_only=False の場合、候補を提示して承認を待つ（UI向け）。
    """

    HIGH_SIMILARITY_THRESHOLD = 0.7
    CANDIDATE_THRESHOLD = 0.5   # 30% → 50% に引き上げ
    MAX_CANDIDATES = 5

    # 類似度計算時に除外するプラットフォーム名
    # これらの単語だけが共通しても候補に出ないようにする
    _PLATFORM_WORDS = re.compile(
        r"^(?:PS2|PS3|PS4|PS5|PS1|PS|PSP|VITA|スーパーファミコン|ファミコン"
        r"|ゲームボーイアドバンス|ゲームボーイ|ドリームキャスト|セガサターン"
        r"|3DS|NDS|DS|Switch|GBA|GB|Xbox360|Wii|3DO|MD|PCE)\s*",
        re.I,
    )

    def _core_title(self, name: str) -> str:
        """プラットフォーム名を除いたコアタイトル部分を返す"""
        return self._PLATFORM_WORDS.sub("", name).strip()

    def __init__(self):
        self._alias_db = ProductAliasDB()
        # Supabase実績データのキャッシュ（起動時に1回だけ取得）
        self._supabase_cache: list[dict] = []
        self._cache_loaded = False

    def load_supabase_cache(self, supabase_url: str = "",
                             supabase_key: str = "") -> int:
        """
        Supabaseの実績データを起動時に一度キャッシュする。
        商品名と類似度計算のためだけに使用（売価計算には使わない）。

        Returns
        -------
        int : キャッシュした件数
        """
        if not supabase_url or not supabase_key:
            # config.py から取得を試みる
            try:
                import config
                supabase_url = getattr(config, "SUPABASE_URL", "")
                supabase_key = getattr(config, "SUPABASE_KEY", "")
            except ImportError:
                pass

        if not supabase_url or not supabase_key:
            logger.debug("Supabase未設定 → キャッシュなし")
            self._cache_loaded = True
            return 0

        try:
            import httpx
            client = httpx.Client(
                base_url=supabase_url,
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                timeout=15.0,
            )
            # name と platform だけ取得（軽量）
            resp = client.get("/rest/v1/items", params={
                "select": "name,platform",
                "limit":  "1000",
            })
            resp.raise_for_status()
            items = resp.json()
            # 重複除去してキャッシュ
            seen = set()
            for item in items:
                name = item.get("name", "").strip()
                if name and name not in seen:
                    seen.add(name)
                    self._supabase_cache.append({
                        "name":     name,
                        "platform": item.get("platform") or "",
                    })
            self._cache_loaded = True
            logger.info(f"Supabaseキャッシュ: {len(self._supabase_cache)}件")
            return len(self._supabase_cache)
        except Exception as e:
            logger.warning(f"Supabaseキャッシュ取得失敗: {e}")
            self._cache_loaded = True
            return 0

    def resolve(self, product_name: str,
                platform: str = "") -> ResolutionResult:
        """
        商品名を名寄せする。

        1. エイリアスDB（確定済み）を検索
        2. 見つからなければ類似候補を提示

        Parameters
        ----------
        product_name : yahoo_parser._clean_name() 済みの商品名
        platform     : カテゴリ（PS2 / スーパーファミコン 等）

        Returns
        -------
        ResolutionResult
        """
        # ① エイリアスDB（確定済み）を検索
        canonical = self._alias_db.find_canonical(product_name)
        if canonical:
            return ResolutionResult(
                original_name  = product_name,
                platform       = platform,
                canonical_name = canonical,
                is_confirmed   = True,
                candidates     = [],
            )

        # ② 類似候補を検索
        candidates = self._find_candidates(product_name, platform)

        return ResolutionResult(
            original_name  = product_name,
            platform       = platform,
            canonical_name = None,
            is_confirmed   = False,
            candidates     = candidates,
        )

    def confirm(self, original_name: str, canonical_name: str,
                platform: str = "") -> None:
        """
        ユーザーが承認した名寄せをエイリアスDBに保存する。
        以降は resolve() で自動変換される。
        """
        self._alias_db.add_alias(original_name, canonical_name, platform)
        logger.info(f"名寄せ確定: '{original_name}' → '{canonical_name}'")

    def register_new(self, original_name: str, platform: str = "") -> str:
        """
        新規商品として登録する（original_name をそのまま正規名にする）。
        """
        self.confirm(original_name, original_name, platform)
        logger.info(f"新規登録: '{original_name}'")
        return original_name

    def _find_candidates(self, name: str,
                         platform: str = "") -> list[ResolutionCandidate]:
        """
        エイリアスDB・リサーチDB・実績DBから類似候補を検索する。

        類似度計算はプラットフォーム名を除いたコアタイトルで行う。
        「スーパーファミコン」が共通しているだけで候補に出るのを防ぐ。
        """
        candidates: list[ResolutionCandidate] = []
        seen: set[str] = set()

        # 入力名のコアタイトル
        name_core = self._core_title(name)

        # ---- エイリアスDBの正規名リストと照合（Supabase/SQLite自動切替） ----
        for row in self._alias_db.list_canonical_names():
            cname = row["canonical_name"]
            if cname in seen:
                continue
            cname_core = self._core_title(cname)
            # コアタイトルが空（プラットフォーム名のみ）はスキップ
            if not cname_core or not name_core:
                continue
            sim = _similarity(name_core, cname_core)
            if sim >= self.CANDIDATE_THRESHOLD:
                seen.add(cname)
                candidates.append(ResolutionCandidate(
                    canonical_name = cname,
                    platform       = row["platform"] or platform,
                    similarity     = sim,
                    source         = "alias",
                    match_reason   = f"登録済み別名（類似度{sim:.0%}）",
                ))

        # ---- リサーチDB・実績DBとの照合（ローカルSQLite部分はそのまま） ----
        with _mock_conn() as conn:
            # ---- リサーチDBの商品名と照合 ----
            rows2 = conn.execute(
                "SELECT DISTINCT canonical_name, platform FROM research_items"
            ).fetchall()
            for row in rows2:
                cname = row["canonical_name"]
                if cname in seen:
                    continue
                cname_core = self._core_title(cname)
                if not cname_core or not name_core:
                    continue
                sim = _similarity(name_core, cname_core)
                if sim >= self.CANDIDATE_THRESHOLD:
                    seen.add(cname)
                    candidates.append(ResolutionCandidate(
                        canonical_name = cname,
                        platform       = row["platform"] or platform,
                        similarity     = sim,
                        source         = "research",
                        match_reason   = f"リサーチDB（類似度{sim:.0%}）",
                    ))

            # ---- 実績DBの商品名と照合 ----
            rows3 = conn.execute(
                "SELECT DISTINCT canonical_name, platform FROM sales_records"
            ).fetchall()
            for row in rows3:
                cname = row["canonical_name"]
                if cname in seen:
                    continue
                cname_core = self._core_title(cname)
                if not cname_core or not name_core:
                    continue
                sim = _similarity(name_core, cname_core)
                if sim >= self.CANDIDATE_THRESHOLD:
                    seen.add(cname)
                    candidates.append(ResolutionCandidate(
                        canonical_name = cname,
                        platform       = row["platform"] or platform,
                        similarity     = sim,
                        source         = "sales",
                        match_reason   = f"販売実績（類似度{sim:.0%}）",
                    ))

        # 類似度の高い順にソートして上位N件を返す
        candidates.sort(key=lambda c: c.similarity, reverse=True)

        # ---- Supabaseキャッシュと照合 ----
        # キャッシュ未ロードなら自動でロード
        if not self._cache_loaded:
            self.load_supabase_cache()

        for item in self._supabase_cache:
            cname = item["name"]
            if cname in seen:
                continue
            cname_core = self._core_title(cname)
            if not cname_core or not name_core:
                continue
            sim = _similarity(name_core, cname_core)
            if sim >= self.CANDIDATE_THRESHOLD:
                seen.add(cname)
                candidates.append(ResolutionCandidate(
                    canonical_name = cname,
                    platform       = item["platform"] or platform,
                    similarity     = sim,
                    source         = "supabase",
                    match_reason   = f"利益管理アプリの実績（類似度{sim:.0%}）",
                ))

        # 再ソート（Supabase候補追加後）
        candidates.sort(key=lambda c: c.similarity, reverse=True)
        return candidates[:self.MAX_CANDIDATES]

    def bulk_resolve(self, names: list[tuple[str, str]]) -> list[ResolutionResult]:
        """
        複数商品を一括名寄せする。
        confirmed_only: 確定済みのみ変換（未確定はoriginal_nameをそのまま使用）

        Parameters
        ----------
        names : list of (product_name, platform)
        """
        return [self.resolve(name, platform) for name, platform in names]

    def list_aliases(self) -> list[dict]:
        """登録済みエイリアス一覧を返す（Supabase/SQLite自動切替）"""
        return self._alias_db.list_all()
