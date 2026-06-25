"""
ヤフオクウォッチリスト テキストパーサー

【実際のコピーテキストフォーマット】
◆プラットフォーム/カタカナ メーカー/カタカナ 商品名 ソフト  ← 2行繰り返し
現在
154円
+ 送料360円
ストア / 入札数 / 残り時間
出品中の商品
商品ID：b1231762702
"""

import re
import logging
from typing import Optional
from models import Product

logger = logging.getLogger(__name__)

# ============================================================
# カテゴリ推定（全プラットフォーム対応）
# ============================================================
_CATEGORY_HINTS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"PlayStation\s*VITA|PS\s*VITA",                                         re.I), "PS Vita",           "VITA"),
    (re.compile(r"PlayStation\s*Portable|プレイステーションポータブル|/PSP\b|\bPSP\b",    re.I), "PSP",               "PSP"),
    (re.compile(r"PlayStation\s*5|PS\s*5\b",                                             re.I), "PS5",               "PS5"),
    (re.compile(r"PlayStation\s*4|PS\s*4\b",                                             re.I), "PS4",               "PS4"),
    (re.compile(r"PlayStation\s*3|PS\s*3\b",                                             re.I), "PS3",               "PS3"),
    (re.compile(r"PlayStation\s*2|PS\s*2\b|プレイステーション\s*2|プレステ\s*2",          re.I), "PS2",               "PS2"),
    (re.compile(r"PlayStation\b(?!\s*[2345]|Portable|VITA)|プレイステーション(?!2|3|4|5|Portable|VITA)", re.I), "PS", "PS1"),
    (re.compile(r"Dreamcast|ドリームキャスト|/DC\b",                                      re.I), "ドリームキャスト",   "ドリームキャスト"),
    (re.compile(r"セガサターン|SEGA\s*SATURN|/SS\b",                                      re.I), "セガサターン",       "セガサターン"),
    (re.compile(r"スーパーファミコン|スーファミ|/SFC\b",                                   re.I), "スーパーファミコン", "スーパーファミコン"),
    (re.compile(r"ファミリーコンピュータ|ファミコン|/FC\b",                                re.I), "ファミコン",         "ファミコン"),
    (re.compile(r"NINTENDO\s*SWITCH|ニンテンドースイッチ|/スイッチ\b|\bスイッチ\b|"
                 r"(?:任天堂|Nintendo|ニンテンドー).{0,20}\bSwitch\b",                      re.I), "Switch",            "Switch"),
    (re.compile(r"Wii\s*U|ウィーユー",                                                     re.I), "WiiU",              "WiiU"),
    (re.compile(r"\bWii\b",                                                               re.I), "Wii",               "Wii"),
    (re.compile(r"NINTENDO\s*3DS|ニンテンドー\s*3DS|new\s*NINTENDO\s*3DS|(?:任天堂|Nintendo|ニンテンドー)(?:/[^\s]+)*\s*3DS", re.I), "3DS", "3DS"),
    (re.compile(r"NINTENDO\s*DS(?!i)|ニンテンドーDS(?!i)",                                re.I), "DS",                "NDS"),
    (re.compile(r"GAME\s*BOY\s*ADVANCE|ゲームボーイアドバンス|\bGBA\b",                   re.I), "ゲームボーイアドバンス", "ゲームボーイアドバンス"),
    (re.compile(r"GAME\s*BOY|ゲームボーイ|\bGB\b",                                        re.I), "ゲームボーイ",       "ゲームボーイ"),
    (re.compile(r"XBOX\s*360",                                                            re.I), "Xbox360",           "360"),
    (re.compile(r"MEGA\s*DRIVE|メガドライブ",                                              re.I), "メガドライブ",       "MD"),
    (re.compile(r"PC\s*エンジン|PC-ENGINE",                                               re.I), "PCエンジン",         "PCE"),
    (re.compile(r"3DO",                                                                   re.I), "3DO",               "3DO"),
]

def _infer_category(name: str) -> tuple[str, str]:
    for pattern, category, short in _CATEGORY_HINTS:
        if pattern.search(name):
            return category, short
    return "その他", ""

# ============================================================
# 非ゲーム商品フィルタ
# ============================================================
_NON_GAME_KEYWORDS = re.compile(
    r"写真集|ブロマイド|缶バッジ|アクリル(?:スタンド|キーホルダー|板)|キーホルダー|"
    r"タペストリー|ポスター|フィギュア|ぬいぐるみ|タオル|Tシャツ|コスプレ|"
    r"ミュージカル|舞台|公演|チケット|パンフレット|"
    r"(?<!ゲーム)DVD|Blu-?ray|サントラ|カードダス|トレカ|遊戯王|ポケカ|"
    r"梱包資材|ダンボール箱|ダンボール\s*\d+\s*枚|トップローダー|スリーブ|プロテクター|"
    r"キャンバスアート|絵師\d*人展|画集|イラスト集",
    re.I,
)

# まとめ商品フラグ（除外せず警告）
_BUNDLE_KEYWORDS = re.compile(
    r"まとめ|[0-9０-９]+点セット|[0-9０-９]+枚|[0-9０-９]+本セット|大量|一式|詰め合わせ",
    re.I,
)

# ============================================================
# 商品名クリーニング
# ============================================================
_PLATFORM_PATTERNS = [
    # 任天堂メーカー名（任天堂/Nintendo/ニンテンドーがどの順序でも） + 本体名
    # 本体名込みで一括除去し、short を商品名の前に付け直す
    (re.compile(r'^(?:任天堂|Nintendo|NINTENDO|ニンテンドー)(?:/(?:任天堂|Nintendo|NINTENDO|ニンテンドー)){0,2}\s*/?\s*3DS(?:/[^\s]+)*\s*', re.I), '3DS'),
    (re.compile(r'^(?:任天堂|Nintendo|NINTENDO|ニンテンドー)(?:/(?:任天堂|Nintendo|NINTENDO|ニンテンドー)){0,2}\s*/?\s*DS(?:i)?(?:/[^\s]+)*\s*', re.I), 'DS'),
    (re.compile(r'^(?:任天堂|Nintendo|NINTENDO|ニンテンドー)(?:/(?:任天堂|Nintendo|NINTENDO|ニンテンドー)){0,2}\s*/?\s*Wii\s*U(?:/[^\s]+)*\s*', re.I), 'WiiU'),
    (re.compile(r'^(?:任天堂|Nintendo|NINTENDO|ニンテンドー)(?:/(?:任天堂|Nintendo|NINTENDO|ニンテンドー)){0,2}\s*/?\s*Wii(?:/[^\s]+)*\s*', re.I), 'Wii'),
    (re.compile(r'^(?:任天堂|Nintendo|NINTENDO|ニンテンドー)(?:/(?:任天堂|Nintendo|NINTENDO|ニンテンドー)){0,2}\s*/?\s*Switch(?:/[^\s]+)*\s*', re.I), 'Switch'),
    # Nintendo 系
    (re.compile(r'^new\s+NINTENDO\s*3DS(?:/[^\s]+)*\s*',      re.I), '3DS'),
    (re.compile(r'^NINTENDO\s*3DS(?:/[^\s]+)*\s*',             re.I), '3DS'),
    (re.compile(r'^NINTENDO\s*DS(?:/[^\s]+)*\s*',              re.I), 'DS'),
    (re.compile(r'^NINTENDO\s*SWITCH(?:/[^\s]+)*\s*',          re.I), 'Switch'),
    # PlayStation 系
    # 数字付きは「/別名（スペース+数字で終わる）」を繰り返しマッチして一括除去
    (re.compile(r'^PlayStation\s*VITA(?:/[^\s]+)*\s*',         re.I), 'PS VITA'),
    (re.compile(r'^PlayStation\s*Portable(?:/[^\s]+)*\s*',     re.I), 'PSP'),
    (re.compile(r'^PlayStation\s*5(?:/[^\s/]+(?:\s+5)?)*\s+', re.I), 'PS5'),
    (re.compile(r'^PlayStation\s*4(?:/[^\s/]+(?:\s+4)?)*\s+', re.I), 'PS4'),
    (re.compile(r'^PlayStation\s*3(?:/[^\s/]+(?:\s+3)?)*\s+', re.I), 'PS3'),
    (re.compile(r'^PlayStation\s*2(?:/[^\s/]+(?:\s+2)?)*\s+', re.I), 'PS2'),
    (re.compile(r'^PlayStation\s*1(?:/[^\s/]+(?:\s+1)?)*\s+', re.I), 'PS'),
    (re.compile(r'^PlayStation(?:/[^\s]+)*\s*',                 re.I), 'PS'),
    # PSP・VITA の英字短縮形が先頭に来るパターン（例: PSP/プレイステーションポータブル）
    (re.compile(r'^PSP(?:/[^\s]+)*\s*',                        re.I), 'PSP'),
    (re.compile(r'^PS\s*VITA(?:/[^\s]+)*\s*',                  re.I), 'PS VITA'),
    # カタカナ先頭のPlayStation系
    (re.compile(r'^プレイステーション\s*ポータブル(?:/[^\s]+)*\s*',  re.I), 'PSP'),
    (re.compile(r'^プレイステーション\s*VITA(?:/[^\s]+)*\s*',       re.I), 'PS VITA'),
    (re.compile(r'^プレイステーション\s*5(?:/[^\s/]+(?:\s+5)?)*\s+', re.I), 'PS5'),
    (re.compile(r'^プレイステーション\s*4(?:/[^\s/]+(?:\s+4)?)*\s+', re.I), 'PS4'),
    (re.compile(r'^プレイステーション\s*3(?:/[^\s/]+(?:\s+3)?)*\s+', re.I), 'PS3'),
    (re.compile(r'^プレイステーション\s*2(?:/[^\s/]+(?:\s+2)?)*\s+', re.I), 'PS2'),
    (re.compile(r'^プレイステーション\s*1(?:/[^\s/]+(?:\s+1)?)*\s+', re.I), 'PS'),
    (re.compile(r'^プレイステーション(?:/[^\s]+)*\s+',               re.I), 'PS'),
    (re.compile(r'^プレステ\s*2(?:/[^\s/]+(?:\s+2)?)*\s+',          re.I), 'PS2'),
    (re.compile(r'^プレステ\s*3(?:/[^\s/]+(?:\s+3)?)*\s+',          re.I), 'PS3'),
    # カタカナ先頭パターン（スーファミ・ファミコン等）
    (re.compile(r'^スーパーファミコン(?:/[^\s]+)*\s*',              re.I), 'スーパーファミコン'),
    (re.compile(r'^ファミリーコンピュータ(?:/[^\s]+)*\s*',          re.I), 'ファミコン'),
    (re.compile(r'^ファミコン(?:/[^\s]+)*\s*',                      re.I), 'ファミコン'),
    (re.compile(r'^ゲームボーイアドバンス(?:/[^\s]+)*\s*',          re.I), 'ゲームボーイアドバンス'),
    (re.compile(r'^ゲームボーイ(?:カラー)?(?:/[^\s]+)*\s*',         re.I), 'ゲームボーイ'),
    (re.compile(r'^ドリームキャスト(?:/[^\s]+)*\s*',                re.I), 'ドリームキャスト'),
    (re.compile(r'^セガサターン(?:/[^\s]+)*\s*',                    re.I), 'セガサターン'),
    # 英字先頭のカタカナ系
    (re.compile(r'^Dreamcast\.?(?:/[^\s]+)*\s*',                  re.I), 'ドリームキャスト'),
    (re.compile(r'^SEGA\s*SATURN(?:/[^\s]+)*\s*',                 re.I), 'セガサターン'),
    (re.compile(r'^GAME\s*BOY\s*ADVANCE(?:/[^\s]+)*\s*',         re.I), 'ゲームボーイアドバンス'),
    (re.compile(r'^GAME\s*BOY(?:/[^\s]+)*\s*',                    re.I), 'ゲームボーイ'),
    # その他
    (re.compile(r'^3DO(?:\s+[A-Z/\s]+)?\s*',                      re.I), '3DO'),
    (re.compile(r'^XBOX\s*360(?:/[^\s]+)*\s*',                    re.I), 'Xbox360'),
    (re.compile(r'^XBOX360\s+',                                     re.I), 'Xbox360'),
]

# スラッシュなしカタカナのみのメーカー名（先頭に残るケース）
_MAKER_ONLY = re.compile(
    r'^(?:バンダイナムコ|ナムコ|BANDAI|KONAMI|SEGA(?=\s)|SONY|任天堂)\s+'
)

def _clean_name(raw: str) -> str:
    """
    「◆プラットフォーム/カタカナ メーカー/カタカナ 商品名 ソフト」
    → 「プラットフォーム短縮名 商品名」 に変換する。

    例:
      ◆NINTENDO DS/ニンテンドーDS BANDAI NAMCO/バンダイナムコ みつけて！ケロロ軍曹 ～ ソフト
      → DS みつけて！ケロロ軍曹 ～
    """
    name = raw.lstrip('◆').strip()

    # 【未開封】等タグを退避
    tags = re.findall(r'【[^】]+】', name)
    name = re.sub(r'【[^】]+】\s*', '', name)

    # プラットフォームを短縮名に置換
    platform = ''
    for pat, short in _PLATFORM_PATTERNS:
        m = pat.match(name)
        if m:
            platform = short
            name = name[m.end():]
            break

    # メーカー名除去：先頭の「英字/カタカナ」を1回だけ除去
    # ただし除去した結果、タイトルが空になる場合は「英語タイトル/カタカナタイトル」
    # という商品タイトル自体の表記だったと判断し、除去しない
    _maker_pattern = re.compile(
        r'^[A-Za-z0-9][A-Za-z0-9\s&/\.]*'
        r'/[\u30A0-\u30FF][^\s]*\s*'
    )
    m_maker = _maker_pattern.match(name)
    if m_maker:
        candidate = name[m_maker.end():]
        candidate_check = re.sub(r'\s*ソフト\s*$', '', candidate).strip()
        if candidate_check:
            # 除去後も中身が残るのでメーカー名として除去してOK
            name = candidate
        # 残らない場合は除去せず name をそのまま維持（タイトル自体だった）

    # スラッシュなしカタカナのみのメーカーを除去
    name = _MAKER_ONLY.sub('', name)

    # 末尾「ソフト」除去・空白整理
    name = re.sub(r'\s*ソフト\s*$', '', name).strip()
    name = re.sub(r'\s+', ' ', name).strip()

    # タグを復元
    tag_str = ' '.join(tags) + ' ' if tags else ''
    result = f'{platform} {tag_str}{name}'.strip()
    return result[:45]


# ============================================================
# ウォッチリスト範囲の切り出し
# ============================================================
_END_MARKERS = [
    "ウォッチリストの関連商品",
    "あなたへのおすすめコレクション",
    "[PR]ストアのおすすめ商品",
    "リマインダーの設定方法",
]

def _trim_to_watchlist(text: str) -> str:
    for marker in _END_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text


# ============================================================
# 商品ブロック解析
# ============================================================
_ITEM_START   = re.compile(r"^(?:◆|【)", re.MULTILINE)
_BLOCK_SEP    = re.compile(r"^　[ \t]*$", re.MULTILINE)  # 全角スペース単独行（商品の区切り）
_RE_ITEM_ID   = re.compile(r"商品ID[：:]\s*([A-Za-z0-9]+)")
_RE_PRICE_LINE = re.compile(r"^([0-9,，]+)円\s*$", re.MULTILINE)
_RE_SHIP_FREE  = re.compile(r"送料\s*(?:無料|0円|込み?)")
_RE_SHIP_PAID  = re.compile(r"[+＋]\s*送料\s*([0-9,，]+)円")

def _parse_price_str(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", "").replace("，", ""))
    except Exception:
        return None

def _parse_block(block: str) -> Optional[Product]:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if len(lines) < 2:
        return None

    raw_name = lines[0]

    # 非ゲーム除外（全角英数字を正規化してから判定: Ｔシャツ等も検出できるように）
    import unicodedata
    normalized_for_check = unicodedata.normalize("NFKC", raw_name)
    if _NON_GAME_KEYWORDS.search(normalized_for_check):
        logger.debug(f"非ゲーム商品スキップ: {raw_name[:40]}")
        return None

    is_bundle = bool(_BUNDLE_KEYWORDS.search(raw_name))
    name = _clean_name(raw_name)
    if not name:
        return None

    # 商品ID → URL
    id_m = _RE_ITEM_ID.search(block)
    item_id = id_m.group(1) if id_m else ""
    url = f"https://page.auctions.yahoo.co.jp/jp/auction/{item_id}" if item_id else ""

    # 現在価格（「現在」行の次行）
    current_price: Optional[int] = None
    for i, line in enumerate(lines):
        if line == "現在" and i + 1 < len(lines):
            m = re.match(r"^([0-9,，]+)円$", lines[i + 1])
            if m:
                current_price = _parse_price_str(m.group(1))
                break
    if current_price is None:
        pm = _RE_PRICE_LINE.search(block)
        if pm:
            current_price = _parse_price_str(pm.group(1))
    if current_price is None:
        return None

    # 送料
    shipping_fee: Optional[int] = None
    shipping_warning = False
    if _RE_SHIP_FREE.search(block):
        shipping_fee = 0
    else:
        sm = _RE_SHIP_PAID.search(block)
        if sm:
            shipping_fee = _parse_price_str(sm.group(1))
        else:
            shipping_fee = 0          # 不明は0円で計算
            shipping_warning = True   # ⑤ アラートフラグ

    category, category_short = _infer_category(raw_name)

    # 注記を商品名に付与
    notes = []
    if is_bundle:
        notes.append("⚠️まとめ商品")
    if shipping_warning:
        notes.append("⚠️送料不明(要確認)")
    display_name = f"{name}  {'  '.join(notes)}" if notes else name

    p = Product(
        name=display_name,
        price=current_price,
        condition="中古",
        url=url,
        image_url="",
        category=category,
        category_short=category_short,
        source="ヤフオク",
        current_price=current_price,
        shipping_fee=shipping_fee,
    )
    # Streamlit用の追加フラグ（dataclassの外に動的付与）
    p._shipping_warning = shipping_warning
    p._is_bundle = is_bundle
    return p


# ============================================================
# メイン解析関数
# ============================================================
def parse_watchlist(raw_text: str) -> list[Product]:
    """
    ヤフオクウォッチリストのコピーテキストを解析し、
    Product オブジェクトのリストを返す。

    商品ブロックの区切りは「　」（全角スペース単独行）を基準にする。
    これはPC版・スマホ版どちらの貼り付けでも商品の直前に必ず入っている。
    （メーカー名から始まる商品名など ◆/【 がない商品にも対応するため）

    見つからない場合は ◆/【 開始行ベースの判定にフォールバックする。
    """
    if not raw_text or not raw_text.strip():
        return []

    text = _trim_to_watchlist(raw_text)

    # ① 全角スペース区切りで分割（優先）
    sep_matches = list(_BLOCK_SEP.finditer(text))
    blocks: list[str] = []

    if len(sep_matches) >= 2:
        for i in range(len(sep_matches) - 1):
            block = text[sep_matches[i].end():sep_matches[i + 1].start()].strip()
            if block:
                blocks.append(block)
        # 最後の区切り以降も商品ブロックの可能性があるので追加
        tail = text[sep_matches[-1].end():].strip()
        if tail and ("現在" in tail or "商品ID" in tail):
            blocks.append(tail)
    else:
        # ② フォールバック: ◆/【 開始行ベース
        starts = [m.start() for m in _ITEM_START.finditer(text)]
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(text)
            block = text[start:end].strip()
            if block:
                blocks.append(block)

    if not blocks:
        return []

    products: list[Product] = []
    seen_ids: set[str] = set()

    for block in blocks:
        try:
            p = _parse_block(block)
            if p is None:
                continue
            key = p.url or p.name
            if key in seen_ids:
                continue
            seen_ids.add(key)
            products.append(p)
        except Exception as e:
            logger.debug(f"ブロック解析失敗: {e}")

    logger.info(f"解析完了: {len(products)}件 / {len(blocks)}ブロック")
    return products
