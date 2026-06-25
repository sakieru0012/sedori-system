"""
ヤフオク→ラクマ せどりリサーチ
Streamlit フロントエンド（第二段階：ラクマ相場連携・推奨入札額表示）

モード切り替え：
  - テキスト解析のみ：ラクマ取得なし（即時）
  - ラクマ相場取得：Selenium起動・商品ごとにスクレイピング
"""

import io
import csv
import logging
import streamlit as st
from typing import Optional

from yahoo_parser import parse_watchlist
from models import Product
from profit_calculator import ProfitResult, calculate, ReliabilityScore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="ヤフオク解析 | せどりリサーチ",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }

.app-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 12px; padding: 24px 32px 18px;
    margin-bottom: 24px; border: 1px solid #e94560;
    box-shadow: 0 4px 24px rgba(233,69,96,0.15);
}
.app-header h1 { color: #e94560; font-size: 1.6rem; margin: 0 0 4px 0; }
.app-header p  { color: #8892a4; margin: 0; font-size: 0.85rem; }

.badge {
    display: inline-block; background: #22c55e; color: white;
    border-radius: 4px; padding: 2px 8px; font-size: 0.72rem;
    font-weight: 700; margin-left: 8px; vertical-align: middle;
}

.metric-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.metric-card {
    flex: 1; min-width: 100px;
    background: #1e293b; border: 1px solid #334155;
    border-radius: 10px; padding: 14px 16px; text-align: center;
}
.metric-card .label { color: #8892a4; font-size: 0.72rem; margin-bottom: 4px; }
.metric-card .value {
    color: #e2e8f0; font-size: 1.4rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}
.metric-card .value.accent { color: #e94560; }
.metric-card .value.green  { color: #22c55e; }
.metric-card .value.yellow { color: #f59e0b; }

.section-label {
    color: #8892a4; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase; margin: 20px 0 8px;
}

/* HTMLテーブル */
.result-table-wrap { overflow-x: auto; border-radius: 10px; }
table.result-table {
    width: 100%; border-collapse: collapse;
    font-size: 0.82rem; background: #1e293b;
}
table.result-table th {
    background: #0f172a; color: #8892a4; font-size: 0.70rem;
    font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 10px 12px; text-align: right; white-space: nowrap;
    position: sticky; top: 0;
}
table.result-table th:first-child,
table.result-table th:nth-child(2) { text-align: left; }
table.result-table td {
    padding: 9px 12px; border-bottom: 1px solid #263347;
    color: #e2e8f0; text-align: right; white-space: nowrap;
    font-family: 'JetBrains Mono', monospace; font-size: 0.80rem;
}
table.result-table td:first-child { text-align: left; font-family: 'Noto Sans JP', sans-serif; font-size: 0.82rem; white-space: normal; max-width: 220px; }
table.result-table td:nth-child(2) { text-align: center; font-family: 'Noto Sans JP', sans-serif; white-space: nowrap; }
table.result-table tr:hover td { background: #263347; }

/* 色クラス */
.c-green  { color: #22c55e !important; font-weight: 700; }
.c-yellow { color: #f59e0b !important; font-weight: 700; }
.c-red    { color: #f87171 !important; font-weight: 700; }
.c-gray   { color: #64748b !important; }

/* 差額バッジ */
.diff-badge {
    display: inline-block; border-radius: 4px;
    padding: 2px 7px; font-size: 0.75rem; font-weight: 700;
}
.diff-pos { background: rgba(34,197,94,0.15);  color: #22c55e; }
.diff-zero{ background: rgba(245,158,11,0.15); color: #f59e0b; }
.diff-neg { background: rgba(248,113,113,0.15);color: #f87171; }

/* 入札不可バッジ */
.no-bid { color: #475569 !important; font-size: 0.72rem; }

.stTextArea textarea {
    font-family: 'JetBrains Mono', monospace; font-size: 0.80rem;
    background: #0f172a; color: #e2e8f0; border: 1px solid #334155;
}
.stButton > button {
    background: linear-gradient(135deg, #e94560, #c0392b);
    color: white; border: none; border-radius: 8px;
    font-weight: 700; padding: 10px 24px; font-size: 0.95rem;
    transition: all 0.2s; box-shadow: 0 2px 12px rgba(233,69,96,0.3);
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(233,69,96,0.5);
}
.stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# ヘッダー
# ============================================================
st.markdown("""
<div class="app-header">
    <h1>🎮 ヤフオク→ラクマ せどりリサーチ <span class="badge">第二段階</span></h1>
    <p>ウォッチリストを貼り付け → ラクマ相場取得 → 推奨入札額・差額・ROIを一覧表示</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# サンプルテキスト（実フォーマット準拠）
# ============================================================
SAMPLE_TEXT = """\
◆Dreamcast./ドリームキャスト/DC SEGA/セガ サクラ大戦 ソフト
◆Dreamcast./ドリームキャスト/DC SEGA/セガ サクラ大戦 ソフト

現在
1,210円
+ 送料360円
ストア
6
20時間
出品中の商品
商品ID：g1231769911

ON

◆NINTENDO 3DS/ニンテンドー3DS SQUARE ENIX/スクウェアエニックス DRAGON QUEST/ドラゴンクエスト 7 エデンの戦士たち ソフト
◆NINTENDO 3DS/ニンテンドー3DS SQUARE ENIX/スクウェアエニックス DRAGON QUEST/ドラゴンクエスト 7 エデンの戦士たち ソフト

現在
133円
+ 送料360円
ストア
10
20時間
出品中の商品
商品ID：v1231768218

ON

◆Dreamcast./ドリームキャスト/DC Summy/サミー GUILTY GEAR X/ギルティギア ゼクス ソフト
◆Dreamcast./ドリームキャスト/DC Summy/サミー GUILTY GEAR X/ギルティギア ゼクス ソフト

現在
1円
+ 送料360円
ストア
2
20時間
出品中の商品
商品ID：o1231777001

ON

◆PlayStation VITA/PS VITA ATLUS/アトラス ペルソナ4 ザ・ゴールデン ソフト
◆PlayStation VITA/PS VITA ATLUS/アトラス ペルソナ4 ザ・ゴールデン ソフト

現在
800円
商品ID：x9999999999

ON

ウォッチリストの関連商品
"""

# ============================================================
# ユーティリティ：色分けHTML生成
# ============================================================

def diff_html(diff: Optional[int]) -> str:
    """差額セルのHTML"""
    if diff is None:
        return '<span class="c-gray">-</span>'
    sign = "+" if diff > 0 else ""
    cls = "diff-pos" if diff > 0 else ("diff-zero" if diff == 0 else "diff-neg")
    return f'<span class="diff-badge {cls}">{sign}{diff:,}円</span>'


def roi_html(roi: Optional[float]) -> str:
    """ROIセルのHTML"""
    if roi is None:
        return '<span class="c-gray">-</span>'
    cls = "c-green" if roi >= 100 else ("c-yellow" if roi >= 50 else "c-red")
    return f'<span class="{cls}">{roi}%</span>'


def reliability_html(r: ReliabilityScore) -> str:
    """信頼度セルのHTML"""
    icons = {"高": ("🟢", "c-green"), "中": ("🟡", "c-yellow"),
             "低": ("🔴", "c-red"),   "不明": ("⚫", "c-gray")}
    icon, cls = icons.get(r.level, ("⚫", "c-gray"))
    return f'<span class="{cls}">{icon} {r.level}<br><small style="font-size:0.68rem;font-weight:400">{r.sold_count}件</small></span>'


def bid_cell(bid: int, biddable: bool) -> str:
    """入札額セルのHTML"""
    if not biddable:
        return f'<span class="no-bid">{bid:,}円<br>入札不可</span>'
    return f'{bid:,}円'


def price_or_dash(v: Optional[int]) -> str:
    return f"{v:,}円" if v is not None else '<span class="c-gray">-</span>'


def gap_rate_html(current_min: Optional[int], sold_median: Optional[int]) -> str:
    """
    価格乖離率セルのHTML。
    gap_rate = current_min / sold_median * 100

    80%以上 → 🟢 正常
    50〜80% → 🟡 注意
    50%未満 → 🔴 警告
    """
    if current_min is None or sold_median is None or sold_median == 0:
        return '<span class="c-gray">-</span>'
    rate = current_min / sold_median * 100
    if rate >= 80:
        cls, icon = "c-green", "🟢"
    elif rate >= 50:
        cls, icon = "c-yellow", "🟡"
    else:
        cls, icon = "c-red", "🔴"
    return f'<span class="{cls}">{icon} {rate:.0f}%</span>'


def rakuma_search_url(keyword: str, category_short: str = "") -> str:
    """ラクマ売れ済み検索URLを生成する（カテゴリID付き）"""
    from urllib.parse import quote
    from keyword_generator import get_rakuma_category_id
    encoded   = quote(keyword)
    cat_id    = get_rakuma_category_id(category_short)
    cat_param = f"&category_id={cat_id}" if cat_id else ""
    return f"https://fril.jp/s?query={encoded}{cat_param}&transaction=soldout&sort=created_at&order=desc"


def rakuma_link_html(keyword: str, category_short: str = "") -> str:
    """ラクマ検索リンクのHTML"""
    if not keyword:
        return '<span class="c-gray">-</span>'
    url = rakuma_search_url(keyword, category_short)
    return (
        f'<a href="{url}" target="_blank" '
        f'style="color:#7c3aed;text-decoration:none;font-size:0.78rem;'
        f'background:rgba(124,58,237,0.12);padding:3px 8px;border-radius:4px;'
        f'white-space:nowrap">🔍 ラクマ</a>'
    )


# ============================================================
# ProfitResult → テーブル行 HTML
# ============================================================

def result_to_row(r: ProfitResult, idx: int) -> str:
    p   = r.product
    b   = r.bid
    cur = p.current_price or 0

    # 売値予測
    sell_str = price_or_dash(r.sell_price_estimate)

    # 安全入札
    if b:
        safe     = b["safe_bid"]
        agg      = b["aggressive_bid"]
        safe_ok  = b["safe_biddable"]
        agg_ok   = b["aggressive_biddable"]
        safe_diff = safe - cur
        agg_diff  = agg - cur
        profit   = b.get("profit_safe")
        roi      = b.get("roi_safe")
    else:
        safe = agg = 0
        safe_ok = agg_ok = False
        safe_diff = agg_diff = None
        profit = roi = None

    # 送料表示
    sf = p.shipping_fee
    sf_str = "無料" if sf == 0 else (f"{sf:,}円" if sf is not None else "?")

    # current_min 警告アイコン
    warn_icon = " ⚠️" if r.current_min_alert else ""

    name_cell = (
        f'<a href="{p.url}" target="_blank" style="color:#94a3b8;text-decoration:none">'
        f'{p.name}{warn_icon}</a>'
        if p.url else f'{p.name}{warn_icon}'
    )

    # 最安値・乖離率・ラクマリンク
    cmin     = r.market.current_min if hasattr(r, "market") else None
    median   = r.sell_price_estimate   # estimate_sell_price は median 優先なのでそのまま使用
    cmin_str = price_or_dash(cmin)
    gap_str  = gap_rate_html(cmin, median)
    kw       = r.market.search_keyword if hasattr(r, "market") else ""
    rakuma_link = rakuma_link_html(kw, p.category_short)

    # 検索キーワードセル（失敗候補は赤字ハイライト）
    from keyword_generator import is_search_failure
    is_fail = is_search_failure(r.reliability.sold_count)
    kw_display = kw or "-"
    kw_cell = (
        f'<span class="c-red" title="検索失敗候補">⚠️ {kw_display}</span>'
        if is_fail else
        f'<span style="color:#94a3b8;font-size:0.78rem">{kw_display}</span>'
    )

    bg = "background:#263347;" if idx % 2 == 0 else ""
    # 失敗候補行は左端に薄い赤ボーダー
    row_style = f"{bg}border-left:3px solid #f87171;" if is_fail else bg

    return f"""
<tr style="{row_style}">
  <td style="text-align:left">{name_cell}</td>
  <td style="text-align:left;max-width:160px">{kw_cell}</td>
  <td style="text-align:center">{reliability_html(r.reliability)}</td>
  <td>{cur:,}円<br><small class="c-gray">{sf_str}</small></td>
  <td>{sell_str}</td>
  <td>{cmin_str}</td>
  <td style="text-align:center">{gap_str}</td>
  <td>{bid_cell(safe, safe_ok)}</td>
  <td>{diff_html(safe_diff if b else None)}</td>
  <td>{bid_cell(agg, agg_ok)}</td>
  <td>{diff_html(agg_diff if b else None)}</td>
  <td>{price_or_dash(profit)}</td>
  <td>{roi_html(roi)}</td>
  <td style="text-align:center">{rakuma_link}</td>
</tr>"""


def build_table_html(results: list[ProfitResult]) -> str:
    header = """
<div class="result-table-wrap">
<table class="result-table">
<thead><tr>
  <th style="text-align:left">商品名</th>
  <th style="text-align:left">検索キーワード</th>
  <th style="text-align:center">相場信頼度</th>
  <th>現在価格</th>
  <th>売値予測</th>
  <th>最安値</th>
  <th style="text-align:center">乖離率</th>
  <th>安全入札額</th>
  <th>安全差額</th>
  <th>攻め入札額</th>
  <th>攻め差額</th>
  <th>想定利益</th>
  <th>ROI</th>
  <th style="text-align:center">相場確認</th>
</tr></thead>
<tbody>"""
    rows = "".join(result_to_row(r, i) for i, r in enumerate(results))
    return header + rows + "</tbody></table></div>"


# ============================================================
# CSV 生成
# ============================================================

def results_to_csv_bytes(results: list[ProfitResult]) -> bytes:
    fields = [
        "商品名", "カテゴリ", "現在価格", "送料",
        "売値予測", "相場信頼度", "売れ済み件数",
        "安全入札額", "安全差額",
        "攻め入札額", "攻め差額",
        "想定利益", "ROI(%)",
        "同梱失敗利益", "ROI_同梱失敗(%)",
        "URL",
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in results:
        p  = r.product
        b  = r.bid
        cur = p.current_price or 0
        sf  = p.shipping_fee if p.shipping_fee is not None else 0
        safe = b.get("safe_bid", "")
        agg  = b.get("aggressive_bid", "")
        w.writerow({
            "商品名"         : p.name,
            "カテゴリ"       : p.category_short,
            "現在価格"       : cur,
            "送料"           : sf,
            "売値予測"       : r.sell_price_estimate or "",
            "相場信頼度"     : r.reliability.level,
            "売れ済み件数"   : r.reliability.sold_count,
            "安全入札額"     : safe,
            "安全差額"       : (safe - cur) if isinstance(safe, int) else "",
            "攻め入札額"     : agg,
            "攻め差額"       : (agg - cur) if isinstance(agg, int) else "",
            "想定利益"       : b.get("profit_safe", ""),
            "ROI(%)"         : b.get("roi_safe", ""),
            "同梱失敗利益"   : b.get("profit_aggressive_fail", ""),
            "ROI_同梱失敗(%)": b.get("roi_aggressive_fail", ""),
            "URL"            : p.url,
        })
    return buf.getvalue().encode("utf-8-sig")


# ============================================================
# ダミー相場データ生成（テスト解析モード用）
# ============================================================

def make_dummy_result(product: Product) -> ProfitResult:
    """
    ラクマ未取得時のダミー ProfitResult。
    sold_count=0・売値予測Noneで「データなし」状態を表現する。
    """
    class _Empty:
        sold_avg = None; sold_count = 0; current_min = None
        search_keyword = ""; sold_prices = []; sold_median = None
    return calculate(product, _Empty())


# ============================================================
# 入力エリア
# ============================================================
col_input, col_help = st.columns([3, 1])

with col_input:
    st.markdown('<div class="section-label">📋 ウォッチリスト テキスト貼り付け</div>',
                unsafe_allow_html=True)
    raw_text = st.text_area(
        label="ウォッチリストのテキスト",
        placeholder="ヤフオクのウォッチリスト画面を Ctrl+A → Ctrl+C してここに貼り付け",
        height=200,
        label_visibility="collapsed",
    )

with col_help:
    st.markdown('<div class="section-label">⚙️ 設定</div>', unsafe_allow_html=True)
    rakuma_mode = st.radio(
        "モード",
        ["テキスト解析のみ（即時）", "ラクマ相場取得（Selenium）"],
        help="ラクマ相場取得は商品1件あたり約5〜10秒かかります",
    )
    if st.button("サンプルを試す", use_container_width=True):
        st.session_state["sample_loaded"] = True

if st.session_state.get("sample_loaded"):
    raw_text = SAMPLE_TEXT
    st.session_state["sample_loaded"] = False

# ============================================================
# 解析実行
# ============================================================
col_btn, _ = st.columns([1, 4])
with col_btn:
    run = st.button("🔍 解析する", use_container_width=True)

if not (run or raw_text.strip()):
    st.stop()

if not raw_text.strip():
    st.warning("テキストを貼り付けてから「解析する」を押してください。")
    st.stop()

# ---- パース ----
with st.spinner("テキスト解析中..."):
    products: list[Product] = parse_watchlist(raw_text)

if not products:
    st.error("商品を検出できませんでした。テキストのフォーマットを確認してください。")
    st.stop()

# ---- 相場取得 ----
use_rakuma = "ラクマ相場取得" in rakuma_mode
results: list[ProfitResult] = []

if use_rakuma:
    from market_data import MarketDataAggregator, RakumaSource
    from profit_calculator import calculate as pc_calculate

    progress = st.progress(0, text="ラクマ相場取得中...")
    agg = MarketDataAggregator()
    src = RakumaSource()
    src.start()
    agg.add_source(src)

    try:
        for i, product in enumerate(products):
            progress.progress(
                (i + 1) / len(products),
                text=f"[{i+1}/{len(products)}] {product.name[:30]}..."
            )
            snapshot = agg.fetch(product.name, product.category_short)

            class _Adapter:
                sold_avg       = snapshot.sold_avg
                sold_count     = snapshot.sold_count
                current_min    = snapshot.current_min
                search_keyword = snapshot.search_keyword
                sold_prices    = snapshot.sold_prices
                sold_median    = snapshot.sold_median

            results.append(pc_calculate(product, _Adapter()))
    finally:
        agg.teardown()
        progress.empty()
else:
    # テキスト解析のみ：全商品ダミー結果
    results = [make_dummy_result(p) for p in products]

# ============================================================
# メトリクス
# ============================================================
total      = len(results)
biddable   = sum(1 for r in results if r.is_worth_bidding())
no_data    = sum(1 for r in results if not r.sell_price_estimate)
warn_count = sum(1 for r in results if r.current_min_alert)
avg_roi    = (
    round(sum(r.bid["roi_safe"] for r in results
              if r.bid.get("roi_safe") is not None) /
          max(1, total - no_data), 1)
    if total > no_data else None
)

st.markdown(f"""
<div class="metric-row">
  <div class="metric-card">
    <div class="label">検出件数</div>
    <div class="value accent">{total}</div>
  </div>
  <div class="metric-card">
    <div class="label">入札候補</div>
    <div class="value green">{biddable}</div>
  </div>
  <div class="metric-card">
    <div class="label">データなし</div>
    <div class="value">{no_data}</div>
  </div>
  <div class="metric-card">
    <div class="label">競合注意</div>
    <div class="value yellow">{warn_count}</div>
  </div>
  <div class="metric-card">
    <div class="label">平均ROI</div>
    <div class="value {'green' if avg_roi and avg_roi >= 50 else 'accent'}">{f'{avg_roi}%' if avg_roi else '-'}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 凡例
# ============================================================
with st.expander("📖 色分け凡例", expanded=False):
    st.markdown("""
| 項目 | 🟢 緑 | 🟡 黄 | 🔴 赤 | ⚫ グレー |
|---|---|---|---|---|
| **差額** | +（まだ入札可） | ±0 | −（現在価格超過） | - |
| **ROI** | 100%以上 | 50〜100% | 50%未満 | データなし |
| **相場信頼度** | 高（10件以上） | 中（5〜9件） | 低（1〜4件） | 不明（0件） |
| **乖離率** | 80%以上（正常） | 50〜80%（注意） | 50%未満（警告） | データなし |

**乖離率** = 最安値 ÷ 売値予測（中央値）× 100。低いほど「状態違い品が混在している可能性」が高いです。  
⚠️マークは「現在最安値が売値予測を大きく下回っている（競合注意）」商品です。  
「入札不可」は安全入札額が現在価格を下回っており、追加入札の余地がない状態です。  
🔍ラクマボタンで売れ済み一覧を直接確認できます。
""")

# ============================================================
# 結果テーブル
# ============================================================
st.markdown('<div class="section-label">📊 解析結果</div>', unsafe_allow_html=True)

if not use_rakuma:
    st.info(
        "📌 現在は **テキスト解析のみモード** です。"
        "売値予測・入札額は表示されません。"
        "「ラクマ相場取得」モードに切り替えると全項目が表示されます。"
    )

table_html = build_table_html(results)
st.markdown(table_html, unsafe_allow_html=True)

# ============================================================
# 検索失敗候補セクション
# ============================================================
from keyword_generator import is_search_failure, failure_reason, FAILURE_THRESHOLD

failures = [r for r in results if is_search_failure(r.reliability.sold_count)]
if failures:
    with st.expander(
        f"⚠️ 検索失敗候補 {len(failures)}件（売れ済み{FAILURE_THRESHOLD}件以下）",
        expanded=True,
    ):
        st.caption(
            "以下の商品はラクマの売れ済みデータが少なく、相場の信頼性が低いです。"
            "🔍ラクマリンクで検索語を確認し、正規化辞書への追加を検討してください。"
        )
        for r in failures:
            kw = r.market.search_keyword if hasattr(r, "market") else "-"
            from urllib.parse import quote
            rakuma_url = f"https://fril.jp/s?query={quote(kw)}&transaction=soldout" if kw else ""
            link_html = f'<a href="{rakuma_url}" target="_blank">🔍 ラクマで確認</a>' if rakuma_url else ""
            st.markdown(
                f"**{r.product.name}**　"
                f"`{kw}`　"
                f"{failure_reason(r.reliability.sold_count)}　"
                + (f"[🔍 ラクマで確認]({rakuma_url})" if rakuma_url else ""),
                unsafe_allow_html=False,
            )

    # 失敗ログCSVダウンロード
    if use_rakuma:
        import csv, io as _io
        from datetime import datetime
        fail_buf = _io.StringIO()
        fw = csv.DictWriter(fail_buf, fieldnames=[
            "日時", "商品名", "検索キーワード", "売れ済み件数",
            "プラットフォーム", "現在価格", "ラクマ検索URL"
        ])
        fw.writeheader()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in failures:
            p  = r.product
            kw = r.market.search_keyword if hasattr(r, "market") else ""
            from urllib.parse import quote as _q
            fw.writerow({
                "日時"           : now_str,
                "商品名"         : p.name,
                "検索キーワード" : kw,
                "売れ済み件数"   : r.reliability.sold_count,
                "プラットフォーム": p.category_short,
                "現在価格"       : p.current_price or "",
                "ラクマ検索URL"  : f"https://fril.jp/s?query={_q(kw)}&transaction=soldout" if kw else "",
            })
        st.download_button(
            label="📥 検索失敗ログ CSV",
            data=fail_buf.getvalue().encode("utf-8-sig"),
            file_name=f"search_failures_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

# ============================================================
# competitive_min 警告一覧
# ============================================================
alerts = [(r.product.name, r.current_min_alert)
          for r in results if r.current_min_alert]
if alerts:
    with st.expander(f"⚠️ 競合注意商品 {len(alerts)}件", expanded=False):
        for name, alert in alerts:
            st.warning(f"**{name}**\n{alert}")

# ============================================================
# CSV エクスポート
# ============================================================
st.markdown('<div class="section-label">💾 エクスポート</div>', unsafe_allow_html=True)

csv_bytes = results_to_csv_bytes(results)
col_dl, _ = st.columns([1, 3])
with col_dl:
    st.download_button(
        label="📥 CSV ダウンロード",
        data=csv_bytes,
        file_name="yahooauction_research.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ============================================================
# デバッグ
# ============================================================
with st.expander("🔧 デバッグ情報", expanded=False):
    st.code(raw_text[:2000], language="text")
    st.caption(f"入力行数: {len(raw_text.splitlines())} / 検出: {total}件")
