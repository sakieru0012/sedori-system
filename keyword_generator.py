"""
ラクマ検索キーワード生成モジュール

商品名 → 検索キーワード の変換を一元管理する。
TITLE_ALIASES に略称・表記ゆれを追記するだけで全体に反映される。

【設計方針】
- 英字/カタカナ の表記ゆれはカタカナ優先（ラクマはカタカナ出品が多い）
- エイリアスは「省略」ではなく「ラクマで最多使用の表記への正規化」
- 20文字制限は検索精度のためであり、意味が切れる省略はしない
"""

from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

MAX_KEYWORD_LEN = 40

# ============================================================
# 正規化辞書
#
# 【方針】
# - 省略ではなく「ラクマで最も多く出品されている表記」に統一する
# - 略称（FF10, DQ7）→ 正式カタカナ表記
# - 英語タイトル  → 日本語カタカナ表記（ラクマの出品傾向に合わせる）
# - スパロボのような「省略しすぎ」は使わない
#
# 追加方法：
#   r"マッチさせたいパターン": "ラクマで多く使われる表記"
# ============================================================
TITLE_ALIASES: dict[str, str] = {
    # ファイナルファンタジー（略称 → 正式カタカナ）
    r"\bFF\s*10\b":                 "ファイナルファンタジーX",
    r"\bFF\s*7\b":                  "ファイナルファンタジーVII",
    r"\bFF\s*8\b":                  "ファイナルファンタジーVIII",
    r"\bFF\s*9\b":                  "ファイナルファンタジーIX",
    r"\bFF\s*12\b":                 "ファイナルファンタジーXII",
    r"FINAL\s+FANTASY\s+X(?!I|V)": "ファイナルファンタジーX",
    r"FINAL\s+FANTASY\s+VII":       "ファイナルファンタジーVII",
    r"FINAL\s+FANTASY\s+VIII":      "ファイナルファンタジーVIII",
    r"FINAL\s+FANTASY":             "ファイナルファンタジー",

    # ドラゴンクエスト
    r"\bDQ\s*7\b":                  "ドラゴンクエストVII",
    r"\bDQ\s*8\b":                  "ドラゴンクエストVIII",
    r"\bDQ\s*5\b":                  "ドラゴンクエストV",
    r"DRAGON\s+QUEST":              "ドラゴンクエスト",

    # スーパーロボット大戦（省略せず正式名称に統一）
    r"第2次スーパーロボット大戦Z\s*再世編": "スーパーロボット大戦Z 再世編",
    r"第2次スーパーロボット大戦Z\s*破界篇": "スーパーロボット大戦Z 破界篇",
    r"第2次スーパーロボット大戦Z":          "スーパーロボット大戦Z",

    # その他英語タイトル → カタカナ
    r"METAL\s+GEAR\s+SOLID":       "メタルギアソリッド",
    r"METAL\s+GEAR":               "メタルギア",
    r"BIOHAZARD":                  "バイオハザード",
    r"GUILTY\s+GEAR":              "ギルティギア",
    r"SAKURA\s+WARS":              "サクラ大戦",
    r"PERSONA":                    "ペルソナ",
}

# ============================================================
# ノイズワード除去
# ============================================================
STOP_WORDS = re.compile(
    r"(?:ソフト|software|game|ゲーム|中古|新品|未開封|美品|良品"
    r"|動作確認済み?|箱説?付き?|説明書付き?|帯付き?"
    r"|送料無料|即決|即日発送|まとめ)",
    re.IGNORECASE,
)

# ============================================================
# カテゴリ補助キーワード
# ============================================================
CATEGORY_SEARCH_WORDS: dict[str, str] = {
    "PS1":              "プレイステーション",
    "PS2":              "PS2",
    "PS3":              "PS3",
    "PS4":              "PS4",
    "PS5":              "PS5",
    "VITA":             "PS Vita",
    "PSP":              "PSP",
    "DC":               "ドリームキャスト",
    "ドリームキャスト":  "ドリームキャスト",
    "SS":               "セガサターン",
    "セガサターン":      "セガサターン",
    "SFC":              "スーパーファミコン",
    "スーパーファミコン": "スーパーファミコン",
    "FC":               "ファミコン",
    "ファミコン":        "ファミコン",
    "GBA":              "ゲームボーイアドバンス",
    "ゲームボーイアドバンス": "ゲームボーイアドバンス",
    "GB":               "ゲームボーイ",
    "ゲームボーイ":      "ゲームボーイ",
    "3DS":              "3DS",
    "NDS":              "DS",
    "Switch":           "Switch",
    "360":              "Xbox360",
    "3DO":              "3DO",
}

# ============================================================
# メイン関数
# ============================================================

def generate_search_keyword(
    product_name: str,
    category_short: str = "",
    max_len: int = MAX_KEYWORD_LEN,
    apply_aliases: bool = True,
    append_platform: bool = True,
) -> str:
    """
    商品名からラクマ検索用キーワードを生成する。

    処理順序：
      1. 正規化辞書（TITLE_ALIASES）でエイリアス変換
      2. 「英字/カタカナ」「カタカナ/カタカナ」副タイトル → カタカナ優先で統一
      3. ノイズワード除去
      4. プラットフォームキーワード付与（重複しない場合のみ）
      5. 最大文字数でカット（意味の切れ目で）
    """
    keyword = product_name.strip()

    # ① 先頭のプラットフォーム短縮名を除去
    #    yahoo_parser が付与した先頭のプラットフォーム名は
    #    カテゴリ補助語として後で改めて付与するので削除する
    platform_prefix = re.compile(
        r"^(?:PlayStation\s*VITA|PlayStation\s*Portable|PlayStation\s*[1-5]?"
        r"|PSP|3DS|NDS|DS|Switch|Xbox360|3DO|Wii\s*U|Wii"
        r"|スーパーファミコン|ファミコン|ファミリーコンピュータ"
        r"|ゲームボーイアドバンス|ゲームボーイ"
        r"|ドリームキャスト|セガサターン)\s+",
        re.IGNORECASE,
    )
    keyword = platform_prefix.sub("", keyword)

    # ② エイリアス変換
    if apply_aliases:
        for pattern, replacement in TITLE_ALIASES.items():
            keyword, n = re.subn(pattern, replacement, keyword, flags=re.IGNORECASE)
            if n:
                logger.debug(f"エイリアス適用: '{pattern}' → '{replacement}'")

    # ③ 「英字/カタカナ」副タイトル → カタカナ優先
    #    先頭を [A-Za-z] に限定（数字で始まるものは誤マッチを防ぐ）
    #    例: "GUILTY GEAR X/ギルティギア ゼクス" → "ギルティギア ゼクス"
    #        "SUSHI/スシ"                        → "スシ"
    #        "妖怪ウォッチ 3 SUSHI/スシ" の「3」は消えない
    keyword = re.sub(
        r"[A-Za-z][A-Za-z0-9 ]*/([\u30A0-\u30FF][^\s]*)",
        lambda m: m.group(1),
        keyword,
    )
    # 「カタカナ/カタカナ」重複除去（エイリアス変換後に残るケース）
    keyword = re.sub(
        r"[\u30A0-\u30FF]+/([\u30A0-\u30FF][^\s]*)",
        lambda m: m.group(1),
        keyword,
    )
    # カタカナ重複除去（"ギルティギア ギルティギア" など）
    keyword = re.sub(r"([\u30A0-\u30FF]{3,})(\s+\1)+", r"\1", keyword)

    keyword = re.sub(r"\s+", " ", keyword).strip()

    # ④ ノイズワード除去
    keyword = STOP_WORDS.sub("", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip()

    # ⑤ プラットフォームキーワード付与
    if append_platform and category_short:
        cat_word = CATEGORY_SEARCH_WORDS.get(category_short, "")
        if cat_word and cat_word not in keyword:
            candidate = f"{keyword} {cat_word}".strip()
            # 付与後も max_len に収まる場合のみ付与（収まらない場合は商品名優先）
            if len(candidate) <= max_len:
                keyword = candidate

    # ⑥ 最大文字数でカット
    if len(keyword) > max_len:
        truncated = keyword[:max_len]
        last_space = truncated.rfind(" ")
        keyword = truncated[:last_space] if last_space > max_len // 2 else truncated
        keyword = keyword.strip()

    return keyword


# ============================================================
# 検索失敗判定
# ============================================================

FAILURE_THRESHOLD = 2

def is_search_failure(sold_count: int) -> bool:
    return sold_count <= FAILURE_THRESHOLD

def failure_reason(sold_count: int) -> str:
    if sold_count == 0:
        return "売れ済み0件（キーワード不一致の可能性）"
    return f"売れ済み{sold_count}件（データ不足・信頼度低）"


# ============================================================
# ラクマ カテゴリID対応表
#
# 実際のHTMLから確認したID:
#   家庭用ゲームソフト : 788
#   携帯用ゲームソフト : 790
#   携帯用ゲーム機本体 : 789（除外対象）
#
# 検索URL形式: https://fril.jp/s?query=XXX&category_id=788&transaction=soldout
# ============================================================

RAKUMA_CATEGORY_IDS: dict[str, int] = {
    # 家庭用ゲームソフト (788)
    "PS1":              788,
    "PS2":              788,
    "PS3":              788,
    "PS4":              788,
    "PS5":              788,
    "DC":               788,
    "ドリームキャスト":  788,
    "SS":               788,
    "セガサターン":      788,
    "SFC":              788,
    "スーパーファミコン": 788,
    "FC":               788,
    "ファミコン":        788,
    "3DO":              788,
    "MD":               788,
    "PCE":              788,
    "360":              788,
    # 携帯用ゲームソフト (790)
    "PSP":              790,
    "VITA":             790,
    "3DS":              790,
    "NDS":              790,
    "GBA":              790,
    "ゲームボーイアドバンス": 790,
    "GB":               790,
    "ゲームボーイ":      790,
    "Switch":           790,
}

def get_rakuma_category_id(category_short: str) -> int:
    """
    カテゴリ短縮形からラクマのカテゴリIDを返す。
    対応表にない場合は 0（カテゴリ指定なし）を返す。
    """
    return RAKUMA_CATEGORY_IDS.get(category_short, 0)
