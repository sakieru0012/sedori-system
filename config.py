# ============================================================
# せどりリサーチシステム - 設定ファイル
# ============================================================

# LINE通知設定（Messaging API）
LINE_CHANNEL_ACCESS_TOKEN = ""                  # チャンネルアクセストークン
LINE_USER_ID = ""                               # 通知先ユーザーID（Uxxxxxxxxx形式）

# 利益計算設定
SHIPPING_COST = 210          # 送料（円・固定）
MERCARI_FEE_RATE = 0.10     # ラクマ手数料率（10%）

# フィルタ設定
MIN_PROFIT = 200            # 最低利益額（円）- これ以下は通知しない
MIN_PROFIT_RATE = 5.0       # 最低利益率（%）- これ以下は通知しない
RAKUMA_SOLD_COUNT = 5       # ラクマ売れ済み取得件数

# 駿河屋対象カテゴリ
SURUGAYA_CATEGORIES = [
    {
        "name": "PlayStation（PS1）",
        "url": "https://www.suruga-ya.jp/search?category=20004&search_word=&page={page}",
        "short": "PS1"
    },
    {
        "name": "PlayStation2（PS2）",
        "url": "https://www.suruga-ya.jp/search?category=20002&search_word=&page={page}",
        "short": "PS2"
    },
    {
        "name": "セガサターン",
        "url": "https://www.suruga-ya.jp/search?category=20014&search_word=&page={page}",
        "short": "SS"
    },
    {
        "name": "ドリームキャスト",
        "url": "https://www.suruga-ya.jp/search?category=20015&search_word=&page={page}",
        "short": "DC"
    },
]

# スクレイピング設定
MAX_PAGES_PER_CATEGORY = 3    # カテゴリごとの最大取得ページ数
REQUEST_DELAY = 1.5           # リクエスト間隔（秒）
REQUEST_TIMEOUT = 15          # タイムアウト（秒）
MAX_PRODUCTS_PER_NOTIFY = 10  # 1回の通知で送る最大商品数

# Seleniumヘッドレスモード
HEADLESS = False

# ログ設定
LOG_FILE = "sedori_research.log"
LOG_LEVEL = "INFO"

# Supabase接続設定
SUPABASE_URL = "https://csacyrmcytumkblrvxpv.supabase.co"
SUPABASE_KEY = "sb_publishable_jKoZu4ZaNHDH21JteeyITg_2m7B3-55"
