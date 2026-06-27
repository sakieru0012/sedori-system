"""
せどり判定システム v2
Streamlit フロントエンド（売買実績DB連携版）

モード：
  - ウォッチリスト解析：貼り付け → DB照合 → 入札判定
  - リサーチDB：未調査商品への予想売価入力・一覧
  - 実績サマリ：売買実績の確認
"""

import logging
import streamlit as st
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")

# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="せどり判定 v2",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
    background: #0a0f1e;
    color: #e2e8f0;
}

/* ヘッダー */
.app-header {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2744 100%);
    border: 1px solid #2d3f5e;
    border-radius: 14px;
    padding: 24px 32px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}
.app-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
}
.app-header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0 0 4px;
}
.app-header p { color: #64748b; font-size: 0.82rem; margin: 0; }

/* タブ */
.stTabs [data-baseweb="tab-list"] {
    background: #111827;
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
    border: 1px solid #1f2937;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #6b7280;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: #1d4ed8 !important;
    color: white !important;
}

/* 判定カード */
.verdict-card {
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    border-left: 4px solid;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}
.verdict-bid      { background: #f0fdf4; border-color: #22c55e; }
.verdict-consider { background: #fffbeb; border-color: #f59e0b; }
.verdict-pass     { background: #fef2f2; border-color: #ef4444; }
.verdict-unknown  { background: #f8fafc; border-color: #94a3b8; }

.verdict-icon { font-size: 1.4rem; line-height: 1; flex-shrink: 0; margin-top: 2px; }
.verdict-body { flex: 1; min-width: 0; }
.verdict-name {
    font-weight: 700; font-size: 0.9rem; color: #0f172a;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.verdict-sub  { font-size: 0.75rem; color: #334155; margin-top: 3px; line-height: 1.4; }
.verdict-meta { font-size: 0.72rem; color: #64748b; margin-top: 4px; }

.verdict-right { text-align: right; flex-shrink: 0; }
.bid-price {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.1rem; font-weight: 700; color: #1d4ed8;
}
.bid-profit {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem; font-weight: 600; color: #15803d; margin-top: 2px;
}
.cur-price {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem; color: #475569; margin-top: 2px;
}
.diff-pos { color: #16a34a; font-size: 0.75rem; font-weight: 700; }
.diff-neg { color: #dc2626; font-size: 0.75rem; font-weight: 700; }

/* 統計カード */
.stat-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.stat-card {
    flex: 1; min-width: 100px;
    background: #111827; border: 1px solid #1f2937;
    border-radius: 10px; padding: 14px 16px; text-align: center;
}
.stat-label { color: #6b7280; font-size: 0.7rem; margin-bottom: 4px; }
.stat-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.4rem; font-weight: 700; color: #f1f5f9;
}
.stat-value.green  { color: #22c55e; }
.stat-value.yellow { color: #f59e0b; }
.stat-value.red    { color: #ef4444; }
.stat-value.blue   { color: #3b82f6; }

/* フォーム */
.stTextArea textarea, .stTextInput input, .stNumberInput input {
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    color: #0f172a !important;
    border-radius: 8px !important;
}
.stSelectbox > div > div {
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    color: #0f172a !important;
    border-radius: 8px !important;
}
.stSelectbox label, .stTextInput label, .stNumberInput label,
.stTextArea label, .stCheckbox label {
    color: #334155 !important;
    font-weight: 600 !important;
}
/* エクスパンダー内のテキスト */
.stExpander {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
}
.streamlit-expanderContent {
    background: #f8fafc !important;
}
/* caption・markdown テキスト */
.stMarkdown p, .stCaption, small {
    color: #475569 !important;
}
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
    color: white; border: none; border-radius: 8px;
    font-weight: 600; padding: 8px 20px;
    transition: all 0.2s;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(29,78,216,0.4);
}

/* リサーチDBテーブル */
.research-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.research-table th {
    background: #0f172a; color: #6b7280; font-size: 0.68rem;
    font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 10px 12px; text-align: left; border-bottom: 1px solid #1f2937;
}
.research-table td {
    padding: 10px 12px; border-bottom: 1px solid #1a2230;
    color: #cbd5e1;
}
.research-table tr:hover td { background: #131f35; }
.mono { font-family: 'JetBrains Mono', monospace; }

/* セクションラベル */
.section-label {
    color: #6b7280; font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    margin: 20px 0 8px;
}

.badge {
    display: inline-block; border-radius: 4px;
    padding: 2px 8px; font-size: 0.68rem; font-weight: 700;
    margin-left: 8px; vertical-align: middle;
}
.badge-blue   { background: rgba(59,130,246,0.2); color: #60a5fa; }
.badge-green  { background: rgba(34,197,94,0.2);  color: #4ade80; }
.badge-yellow { background: rgba(245,158,11,0.2); color: #fbbf24; }
.badge-gray   { background: rgba(100,116,139,0.2);color: #94a3b8; }

.stAlert { border-radius: 8px; }
.stExpander { border: 1px solid #1f2937 !important; border-radius: 8px !important; }
/* コードブロック（コピー用）を見やすく */
.stCode, .stCode code, pre, pre code {
    background: #f1f5f9 !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
}
/* ラジオボタン・ラベル全般 */
.stRadio label, .stRadio div, .stRadio p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] p {
    color: #0f172a !important;
    font-weight: 600 !important;
}
/* ラジオボタン選択肢のテキスト */
.stRadio [data-testid="stMarkdownContainer"] p {
    color: #0f172a !important;
}
/* エキスパンダーのタイトル */
.stExpander summary,
.stExpander summary p,
.stExpander summary span,
[data-testid="stExpander"] summary {
    color: #0f172a !important;
    font-weight: 700 !important;
}
/* キャプション・サブテキスト */
.stCaption, [data-testid="stCaptionContainer"] p {
    color: #334155 !important;
}
/* セレクトボックスの文字色 */
.stSelectbox > div > div,
.stSelectbox > div > div > div,
.stSelectbox span,
[data-baseweb="select"] span,
[data-baseweb="select"] div {
    color: #0f172a !important;
    background: #ffffff !important;
}
/* ドロップダウンの選択肢 */
[role="listbox"] li,
[role="option"] {
    color: #0f172a !important;
    background: #ffffff !important;
}
[role="option"]:hover {
    background: #f1f5f9 !important;
}
</style>
<script>
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).catch(() => {
        const el = document.createElement('textarea');
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
    });
}
</script>
""", unsafe_allow_html=True)

# ============================================================
# ヘッダー
# ============================================================
st.markdown("""
<div class="app-header">
    <h1>🎮 せどり判定システム <span style="color:#3b82f6;font-size:0.8em">v2</span></h1>
    <p>売買実績DBを活用した推奨入札額算出・ウォッチリスト照合ツール</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# エンジン初期化（アプリ全体で1回だけ生成）
# ============================================================
@st.cache_resource
def get_engine():
    from sedori_engine import SedoriEngine
    return SedoriEngine()

engine = get_engine()

# ============================================================
# タブ構成
# ============================================================
tab_watch, tab_research, tab_wizard, tab_summary = st.tabs([
    "📋 ウォッチリスト解析",
    "🔍 リサーチDB",
    "⚙️ 取り込みウィザード",
    "📊 実績サマリ",
])

# ============================================================
# TAB 1: ウォッチリスト解析
# ============================================================
with tab_watch:
    col_input, col_help = st.columns([3, 1])

    with col_input:
        st.markdown('<div class="section-label">ウォッチリスト テキスト貼り付け</div>',
                    unsafe_allow_html=True)
        raw_text = st.text_area(
            label="watchlist",
            placeholder="ヤフオクのウォッチリストページを Ctrl+A → Ctrl+C してここに貼り付け",
            height=180,
            label_visibility="collapsed",
            key="watchlist_input",
        )

    with col_help:
        st.markdown('<div class="section-label">凡例</div>', unsafe_allow_html=True)
        st.markdown("""
<div style="font-size:0.8rem;line-height:2;color:#94a3b8">
🟢 <b>入札</b>　合計≤上限<br>
🟡 <b>検討</b>　送料次第・不明<br>
🔴 <b>見送り</b>　上限超過<br>
⚫ <b>未調査</b>　DB未登録
</div>
""", unsafe_allow_html=True)
        if st.button("サンプルで試す", use_container_width=True):
            st.session_state["load_sample"] = True

    if st.session_state.get("load_sample"):
        st.session_state["load_sample"] = False
        raw_text = open("/mnt/user-data/uploads/watchlist.txt",
                        encoding="utf-8").read() if \
            __import__("pathlib").Path("/mnt/user-data/uploads/watchlist.txt").exists() \
            else ""

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        run = st.button("🔍 解析・照合", use_container_width=True)

    if not (run or raw_text.strip()):
        st.markdown("""
<div style="text-align:center;padding:60px 0;color:#374151">
    <div style="font-size:2.5rem;margin-bottom:12px">📋</div>
    <div style="font-size:0.9rem">ウォッチリストを貼り付けて「解析・照合」を押してください</div>
</div>
""", unsafe_allow_html=True)

    elif not raw_text.strip():
        st.warning("テキストを貼り付けてください。")

    else:
        # ---- パース ----
        from yahoo_parser import parse_watchlist
        with st.spinner("解析中..."):
            products = parse_watchlist(raw_text)

        if not products:
            st.error("商品を検出できませんでした。")
        else:

            # ---- DB照合 ----
            with st.spinner(f"{len(products)}件をDB照合中..."):
                results = engine.process_batch(products)

            # ---- 統計 ----
            from sedori_engine import VERDICT_BID, VERDICT_CONSIDER, VERDICT_PASS, VERDICT_UNKNOWN
            cnt_bid      = sum(1 for r in results if r.verdict == VERDICT_BID)
            cnt_consider = sum(1 for r in results if r.verdict == VERDICT_CONSIDER)
            cnt_pass     = sum(1 for r in results if r.verdict == VERDICT_PASS)
            cnt_unknown  = sum(1 for r in results if r.verdict == VERDICT_UNKNOWN)

            st.markdown(f"""
        <div class="stat-row">
          <div class="stat-card">
            <div class="stat-label">解析件数</div>
            <div class="stat-value blue">{len(results)}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">🟢 入札</div>
            <div class="stat-value green">{cnt_bid}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">🟡 検討</div>
            <div class="stat-value yellow">{cnt_consider}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">🔴 見送り</div>
            <div class="stat-value red">{cnt_pass}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">⚫ 未調査</div>
            <div class="stat-value">{cnt_unknown}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

            # ---- ソート切り替え ----
            sort_key = f"sort_mode_{id(results)}"
            if sort_key not in st.session_state:
                st.session_state[sort_key] = "貼り付け順"

            col_sort1, col_sort2, _ = st.columns([2, 2, 6])
            with col_sort1:
                if st.button(
                    "📋 貼り付け順",
                    use_container_width=True,
                    type="primary" if st.session_state[sort_key] == "貼り付け順" else "secondary",
                    key=f"sort_orig_{sort_key}",
                ):
                    st.session_state[sort_key] = "貼り付け順"
            with col_sort2:
                if st.button(
                    "🎯 判定順",
                    use_container_width=True,
                    type="primary" if st.session_state[sort_key] == "判定順" else "secondary",
                    key=f"sort_verdict_{sort_key}",
                ):
                    st.session_state[sort_key] = "判定順"

            ORDER = {VERDICT_BID: 0, VERDICT_CONSIDER: 1, VERDICT_PASS: 2, VERDICT_UNKNOWN: 3}
            if st.session_state[sort_key] == "判定順":
                sorted_results = sorted(results, key=lambda r: ORDER.get(r.verdict, 9))
            else:
                sorted_results = results  # 貼り付け順そのまま

            # ---- 判定カード一覧 ----
            st.markdown('<div class="section-label">照合結果</div>', unsafe_allow_html=True)

            # 未調査商品の入力フォーム管理
            if "research_inputs" not in st.session_state:
                st.session_state.research_inputs = {}

            for r in sorted_results:
                p   = r.product
                cls = {
                    VERDICT_BID:      "verdict-bid",
                    VERDICT_CONSIDER: "verdict-consider",
                    VERDICT_PASS:     "verdict-pass",
                    VERDICT_UNKNOWN:  "verdict-unknown",
                }.get(r.verdict, "verdict-unknown")

                # 推奨上限・差額・利益計算
                if r.recommended_max_bid > 0:
                    bid_str  = f"{r.recommended_max_bid:,}円"
                    diff_val = (r.recommended_max_bid - (p.current_price or 0))
                    diff_str = (
                        f'<span class="diff-pos">+{diff_val:,}円 余裕</span>'
                        if diff_val >= 0 else
                        f'<span class="diff-neg">{diff_val:,}円 超過</span>'
                    )
                    # 推奨上限で落札した場合の想定利益
                    from profit_calculator import calc_profit_target
                    if r.sell_price > 0:
                        est_profit = calc_profit_target(r.sell_price)
                        profit_str = (
                            f'<div class="bid-profit">利益 約{est_profit:,}円</div>'
                            if est_profit > 0 else
                            f'<div class="bid-profit" style="color:#dc2626">利益 約{est_profit:,}円</div>'
                        )
                    else:
                        profit_str = ""
                else:
                    bid_str    = "-"
                    diff_str   = ""
                    profit_str = ""

                cur_str = f"{p.current_price:,}円" if p.current_price else "-"
                sf_str  = (f"送料{p.shipping_fee:,}円" if p.shipping_fee is not None
                           else "送料不明")

                basis_badge = (
                    f'<span class="badge badge-green">{r.basis}</span>'
                    if r.basis else
                    '<span class="badge badge-gray">未登録</span>'
                )
                # 怪しいフラグ
                doubtful_badge = ""
                if r.research_item and r.research_item.doubtful:
                    doubtful_badge = '<span class="badge" style="background:rgba(239,68,68,0.15);color:#dc2626">⚠️ 売れるか怪しい</span>'

                sell_str = r.sell_price_display()
                url_link = (f'<a href="{p.url}" target="_blank" '
                            f'style="color:#3b82f6;font-size:0.72rem">ヤフオク ↗</a>'
                            if p.url else "")

                st.markdown(f"""
        <div class="verdict-card {cls}">
          <div class="verdict-icon">{r.verdict_icon}</div>
          <div class="verdict-body">
            <div class="verdict-name">{r.product.name}</div>
            <div class="verdict-sub">{r.verdict_reason}</div>
            <div class="verdict-meta">
              {basis_badge}
              {doubtful_badge}
              {'　売値実績: ' + sell_str if sell_str != '-' else ''}
              {'　' + url_link if url_link else ''}
            </div>
          </div>
          <div class="verdict-right">
            <div class="bid-price">{bid_str}</div>
            {profit_str}
            <div class="cur-price">現在 {cur_str}　{sf_str}</div>
            <div style="margin-top:4px">{diff_str}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

                # ---- アクションボタン ----
                btn_cols = st.columns([3, 3, 4])
                # オークファンで開く
                if p.item_id:
                    aucfan_url = f"https://aucview.aucfan.com/yahoo/{p.item_id}/"
                    with btn_cols[0]:
                        st.markdown(
                            f'<a href="{aucfan_url}" target="_blank">'
                            f'<button style="width:100%;padding:4px 8px;background:#16a34a;'
                            f'color:white;border:none;border-radius:6px;cursor:pointer;'
                            f'font-size:0.75rem">🔖 オークファン</button></a>',
                            unsafe_allow_html=True,
                        )
                # 推奨上限をコピー
                if r.recommended_max_bid > 0:
                    with btn_cols[1]:
                        st.code(str(r.recommended_max_bid), language=None)

                # 実績詳細の展開表示
                if r.sales_summary and r.sales_summary.records:
                    with st.expander(
                        f"📊 実績詳細（{r.sales_summary.sales_count}件）"
                        f"　平均売値: {r.sales_summary.avg_sold_price:,}円"
                        f"　平均利益: {r.sales_summary.avg_profit:,}円"
                    ):
                        rows_html = ""
                        for rec in r.sales_summary.records:
                            date_str = (rec.sold_at or "日付不明")[:10]
                            profit_color = "#22c55e" if rec.profit >= 0 else "#ef4444"
                            rows_html += f"""
<tr>
  <td style="color:#94a3b8;font-size:0.72rem">{date_str}</td>
  <td class="mono">{rec.sold_price:,}円</td>
  <td class="mono">{rec.purchase_price:,}円</td>
  <td class="mono" style="color:{profit_color}">{rec.profit:,}円</td>
  <td style="color:#64748b;font-size:0.72rem">{rec.platform_sold or '-'}</td>
</tr>"""
                        st.markdown(f"""
<table class="research-table">
<thead><tr>
  <th>販売日</th><th>売値</th><th>仕入値</th><th>利益</th><th>販売先</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)
                        st.caption(
                            "💡 状態による価格差がある場合は sedori-v3 の登録時に"
                            "メモ欄へ「箱説付き」「ソフトのみ」等を記録してください"
                        )

                # 名寄せ・予想売価入力フォーム（未調査 or 名寄せ未確定）
                if r.verdict == VERDICT_UNKNOWN or (
                    r.resolution and not r.resolution.is_confirmed
                ):
                    with st.expander(
                        f"{'🔗 名寄せ・' if r.needs_resolution else '💡 '}"
                        f"{r.product.name[:35]} を登録"
                    ):
                        res      = r.resolution
                        key_base = f"{r.product.name}_{r.product.category_short}"

                        # セッションステートでソフトリストを管理
                        items_key = f"items_{key_base}"
                        if items_key not in st.session_state:
                            st.session_state[items_key] = [
                                {"canonical": "", "price": 0, "listing_price": 0,
                                 "skip": False, "skip_reason": "", "doubtful": False, "memo": ""}
                            ]

                        # ============================================================
                        # Step 1: 出品名の扱い
                        # ============================================================
                        is_bundle = "まとめ" in r.product.name or "セット" in r.product.name \
                                    or "点" in r.product.name

                        if is_bundle:
                            st.info(
                                "⚠️ まとめ商品が検出されました。\n"
                                "含まれるソフトを個別に入力してください。"
                                "各ソフトが単品でDBに登録され、次回から照合できます。"
                            )
                        elif res and not res.is_confirmed:
                            # 通常商品の名寄せ
                            st.markdown("**Step 1: 正規商品名を選択してください**")
                            if res.candidates:
                                options = (
                                    [c.canonical_name for c in res.candidates]
                                    + ["➕ 新規登録（別の商品）"]
                                )
                                hints = (
                                    [c.match_reason for c in res.candidates] + [""]
                                )
                                sel = st.radio(
                                    "候補",
                                    options,
                                    format_func=lambda x: (
                                        f"{x}　({hints[options.index(x)]})"
                                        if hints[options.index(x)] else x
                                    ),
                                    key=f"radio_{key_base}",
                                    label_visibility="collapsed",
                                )
                                if sel == "➕ 新規登録（別の商品）":
                                    st.session_state[items_key][0]["canonical"] = st.text_input(
                                        "正式商品名を入力",
                                        value=r.product.name,
                                        key=f"new_name_{key_base}",
                                    )
                                else:
                                    st.session_state[items_key][0]["canonical"] = sel
                            else:
                                st.session_state[items_key][0]["canonical"] = st.text_input(
                                    "正式商品名（初登録）",
                                    value=r.product.name,
                                    key=f"new_name_{key_base}",
                                )
                            st.divider()

                        # ============================================================
                        # Step 2: ソフトリスト入力（1件 or 複数）
                        # ============================================================
                        st.markdown(
                            "**ソフト情報を入力してください**"
                            if not is_bundle else
                            "**含まれるソフトを入力してください**"
                        )

                        items_list = st.session_state[items_key]
                        to_delete  = []

                        for idx, item in enumerate(items_list):
                            st.markdown(
                                f"<div style='color:#6b7280;font-size:0.72rem;"
                                f"margin:8px 0 4px'>ソフト {idx+1}</div>",
                                unsafe_allow_html=True,
                            )
                            col_n, col_del = st.columns([9, 1])

                            with col_n:
                                # ソフト名入力（まとめ商品 or 名寄せ確定済みの場合）
                                if is_bundle or (res and res.is_confirmed):
                                    canonical_val = st.text_input(
                                        "ソフト名",
                                        value=item["canonical"],
                                        key=f"cname_{key_base}_{idx}",
                                        placeholder="正式なソフト名を入力...",
                                    )
                                    # リアルタイム候補表示
                                    if canonical_val and len(canonical_val) >= 3:
                                        candidates = engine.resolver._find_candidates(
                                            canonical_val,
                                            r.product.category_short,
                                        )
                                        if candidates:
                                            best = candidates[0]
                                            if best.similarity >= 0.5:
                                                use_cand = st.checkbox(
                                                    f"候補: {best.canonical_name[:35]}"
                                                    f"（{best.match_reason}）",
                                                    key=f"use_cand_{key_base}_{idx}",
                                                )
                                                canonical_val = best.canonical_name \
                                                    if use_cand else canonical_val
                                    items_list[idx]["canonical"] = canonical_val
                                else:
                                    # 通常商品は Step1 で確定した正規名を使用
                                    canonical_val = items_list[0].get("canonical", r.product.name)
                                    items_list[idx]["canonical"] = canonical_val
                                    st.caption(f"正規名:")
                                    st.code(canonical_val, language=None)

                            with col_del:
                                if idx > 0:
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    if st.button("✕", key=f"del_{key_base}_{idx}"):
                                        to_delete.append(idx)

                            # 売価入力 or スキップ
                            col_skip, col_price, col_listing, col_memo = st.columns([2, 2, 2, 2])
                            with col_skip:
                                skip_opt = st.selectbox(
                                    "売価",
                                    ["入力する", "後で入力", "相場読めず・対象外"],
                                    key=f"skip_{key_base}_{idx}",
                                )
                                items_list[idx]["skip"]        = skip_opt != "入力する"
                                items_list[idx]["skip_reason"] = "" if skip_opt == "入力する" \
                                                                 else skip_opt
                            with col_price:
                                if not items_list[idx]["skip"]:
                                    items_list[idx]["price"] = st.number_input(
                                        "予想売価（円）",
                                        min_value=0, step=100,
                                        key=f"price_{key_base}_{idx}",
                                    )
                                else:
                                    st.caption(f"スキップ: {skip_opt}")
                            with col_listing:
                                items_list[idx]["listing_price"] = st.number_input(
                                    "出品予定価格（円）",
                                    min_value=0, step=100,
                                    key=f"listing_{key_base}_{idx}",
                                    help="実際に出品する価格（省略可）",
                                )
                            with col_memo:
                                col_doubt, col_m2 = st.columns([1, 3])
                                with col_doubt:
                                    items_list[idx]["doubtful"] = st.checkbox(
                                        "⚠️ 売れるか怪しい",
                                        key=f"doubtful_{key_base}_{idx}",
                                    )
                                with col_m2:
                                    items_list[idx]["memo"] = st.text_input(
                                        "メモ", key=f"memo_{key_base}_{idx}"
                                    )

                        # 削除処理
                        for idx in reversed(to_delete):
                            items_list.pop(idx)

                        # ソフト追加ボタン
                        col_add, col_total, col_save = st.columns([2, 4, 2])
                        with col_add:
                            if st.button("＋ ソフトを追加", key=f"add_{key_base}"):
                                items_list.append({
                                    "canonical": "", "price": 0, "listing_price": 0,
                                    "skip": False, "skip_reason": "", "doubtful": False, "memo": ""
                                })
                                st.rerun()

                        # 合計推奨上限を表示
                        from profit_calculator import calc_max_bid
                        total_max = sum(
                            calc_max_bid(item["price"])
                            for item in items_list
                            if not item["skip"] and item["price"] > 0
                        )
                        with col_total:
                            if total_max > 0:
                                n_priced = sum(
                                    1 for item in items_list
                                    if not item["skip"] and item["price"] > 0
                                )
                                st.markdown(
                                    f"<div style='padding-top:8px;color:#3b82f6;"
                                    f"font-weight:700'>合計推奨上限: "
                                    f"{total_max:,}円（{n_priced}件分）</div>",
                                    unsafe_allow_html=True,
                                )

                        # 保存ボタン
                        with col_save:
                            if st.button("✅ 確定・保存", key=f"save_{key_base}",
                                         type="primary"):
                                saved = 0
                                errors = []
                                for idx, item in enumerate(items_list):
                                    cname = item["canonical"].strip()
                                    if not cname:
                                        errors.append(f"ソフト{idx+1}: 商品名が未入力")
                                        continue

                                    # 名寄せ確定（通常商品・初回のみ）
                                    if not is_bundle and res and not res.is_confirmed \
                                            and idx == 0:
                                        engine.resolver.confirm(
                                            r.product.name, cname,
                                            r.product.category_short,
                                        )

                                    # リサーチDB保存
                                    skip_reason = item.get("skip_reason", "")
                                    price       = 0 if item["skip"] else item["price"]
                                    engine.save_research(
                                        canonical_name       = cname,
                                        platform             = r.product.category_short,
                                        original_name        = r.product.name,
                                        estimated_sell_price = price,
                                        listing_price        = item.get("listing_price", 0),
                                        doubtful             = item.get("doubtful", False),
                                        memo = f"[{skip_reason}] {item['memo']}"
                                               if skip_reason else item["memo"],
                                    )
                                    saved += 1

                                if errors:
                                    for e in errors:
                                        st.warning(e)
                                if saved:
                                    st.success(
                                        f"✅ {saved}件保存しました！"
                                        + (f"　合計推奨上限: {total_max:,}円"
                                           if total_max > 0 else "")
                                    )
                                    # フォームをリセットして再描画
                                    del st.session_state[items_key]
                                    st.rerun()

            # ---- CSV出力 ----
            import io, csv
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["判定", "商品名", "カテゴリ", "現在価格", "送料",
                        "合計仕入れ額", "推奨上限", "差額", "根拠", "URL"])
            for r in sorted_results:
                p = r.product
                total = (p.current_price or 0) + (p.shipping_fee or 0)
                diff  = r.recommended_max_bid - (p.current_price or 0) if r.recommended_max_bid else ""
                w.writerow([
                    r.verdict, p.name, p.category_short,
                    p.current_price or "", p.shipping_fee or "",
                    total, r.recommended_max_bid or "", diff,
                    r.basis, p.url,
                ])

            st.markdown('<div class="section-label">エクスポート</div>', unsafe_allow_html=True)
            st.download_button(
                "📥 CSV ダウンロード",
                data=buf.getvalue().encode("utf-8-sig"),
                file_name="watchlist_verdict.csv",
                mime="text/csv",
            )


# ============================================================
# TAB 2: リサーチDB
# ============================================================
with tab_research:
    subtab_research, subtab_alias = st.tabs(["📝 リサーチDB", "🔗 名寄せ辞書"])

    # ---- リサーチDB一覧 ----
    with subtab_research:
        st.markdown('<div class="section-label">リサーチDB一覧</div>',
                    unsafe_allow_html=True)
        items = engine.research_db.list_all()

        if not items:
            st.markdown("""
<div style="text-align:center;padding:40px 0;color:#374151">
    <div style="font-size:2rem;margin-bottom:8px">📭</div>
    <div style="font-size:0.85rem">リサーチDBはまだ空です。<br>
    ウォッチリスト解析で未調査商品に予想売価を入力すると保存されます。</div>
</div>
""", unsafe_allow_html=True)
        else:
            from profit_calculator import calc_max_bid, ReliabilityScore
            rows_html = ""
            for item in items:
                lp_str = f"{item.listing_price:,}円" if item.listing_price > 0 else "-"
                doubt_str = "⚠️" if item.doubtful else ""
                rows_html += f"""
<tr>
  <td>{item.canonical_name}</td>
  <td>{item.platform}</td>
  <td class="mono">{item.estimated_sell_price:,}円</td>
  <td class="mono"><b>{item.recommended_max_bid:,}円</b></td>
  <td class="mono" style="color:#1d4ed8">{lp_str}</td>
  <td style="text-align:center">{doubt_str}</td>
  <td><span class="badge {'badge-green' if item.basis=='実績' else 'badge-yellow'}">{item.basis}</span></td>
  <td style="color:#64748b;font-size:0.72rem">{item.memo or '-'}</td>
  <td style="color:#64748b;font-size:0.72rem">{(item.updated_at or '')[:10]}</td>
</tr>"""
            st.markdown(f"""
<table class="research-table">
<thead><tr>
  <th>商品名</th><th>プラットフォーム</th>
  <th>予想売価</th><th>推奨上限</th><th>出品予定価格</th>
  <th>⚠️</th><th>根拠</th><th>メモ</th><th>更新日</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)

        st.markdown('<div class="section-label">手動追加</div>',
                    unsafe_allow_html=True)
        with st.expander("＋ 商品を手動でリサーチDBに追加"):
            from profit_calculator import calc_max_bid
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                manual_name = st.text_input("商品名", key="manual_name")
            with col2:
                manual_platform = st.selectbox(
                    "プラットフォーム",
                    ["PS2", "PS", "PS3", "PS4", "PS5", "PSP", "PS VITA",
                     "スーパーファミコン", "ファミコン", "ゲームボーイ",
                     "ゲームボーイアドバンス", "ドリームキャスト", "セガサターン",
                     "3DS", "DS", "Switch", "その他"],
                    key="manual_platform"
                )
            with col3:
                manual_price = st.number_input(
                    "予想売価（円）", min_value=0, step=100, key="manual_price"
                )
            manual_memo = st.text_input("メモ", key="manual_memo")
            if st.button("リサーチDBに追加", key="manual_add"):
                if manual_name and manual_price > 0:
                    engine.save_research(
                        canonical_name       = manual_name,
                        platform             = manual_platform,
                        original_name        = manual_name,
                        estimated_sell_price = manual_price,
                        memo                 = manual_memo,
                    )
                    st.success(f"追加しました！推奨上限: {calc_max_bid(manual_price):,}円")
                    st.rerun()
                else:
                    st.warning("商品名と予想売価を入力してください。")

    # ---- 名寄せ辞書 ----
    with subtab_alias:
        st.markdown('<div class="section-label">名寄せ辞書（登録済みエイリアス）</div>',
                    unsafe_allow_html=True)
        from name_resolver import NameResolver
        resolver_view = NameResolver()
        aliases = resolver_view.list_aliases()

        if not aliases:
            st.markdown("""
<div style="text-align:center;padding:40px 0;color:#374151">
    <div style="font-size:2rem;margin-bottom:8px">🔗</div>
    <div style="font-size:0.85rem">名寄せ辞書はまだ空です。<br>
    ウォッチリスト解析で商品を登録すると表示されます。</div>
</div>
""", unsafe_allow_html=True)
        else:
            rows_html = ""
            for a in aliases:
                same = "<span style='color:#64748b;font-size:0.75rem'>(同一)</span>" \
                       if a["alias"] == a["canonical_name"] else ""
                rows_html += f"""
<tr>
  <td>{a["alias"]}</td>
  <td style="color:#6b7280">→</td>
  <td><b>{a["canonical_name"]}</b> {same}</td>
  <td>{a["platform"] or "-"}</td>
  <td style="color:#64748b;font-size:0.72rem">{(a["created_at"] or "")[:10]}</td>
</tr>"""
            st.markdown(f"""
<table class="research-table">
<thead><tr>
  <th>元の商品名</th><th></th><th>正規名</th>
  <th>プラットフォーム</th><th>登録日</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)

        st.markdown('<div class="section-label">手動エイリアス追加</div>',
                    unsafe_allow_html=True)
        with st.expander("＋ エイリアスを手動追加"):
            col1, col2, col3 = st.columns([3, 3, 1])
            with col1:
                alias_input     = st.text_input("元の商品名（表記ゆれ）", key="alias_input")
            with col2:
                canonical_input = st.text_input("正規名", key="canonical_input")
            with col3:
                alias_platform  = st.text_input("機種", key="alias_platform")
            if st.button("追加", key="alias_add"):
                if alias_input and canonical_input:
                    from name_resolver import NameResolver as NR
                    NR().confirm(alias_input, canonical_input, alias_platform)
                    st.success(f"追加: '{alias_input}' → '{canonical_input}'")
                    st.rerun()
                else:
                    st.warning("元の商品名と正規名を入力してください。")

# ============================================================
# TAB 3: 取り込みウィザード
# ============================================================
with tab_wizard:
    st.markdown('<div class="section-label">Supabase実績データ 初回取り込みウィザード</div>',
                unsafe_allow_html=True)
    st.info(
        "利益管理アプリ（sedori-v3）の商品データをクリーニングして名寄せ辞書に一括登録します。\n\n"
        "登録後はウォッチリスト照合で実績データが自動的に参照されます。"
    )

    # ---- Step1: データ取得 ----
    if "wizard_items" not in st.session_state:
        st.session_state.wizard_items  = []
        st.session_state.wizard_groups = []
        st.session_state.wizard_done   = False

    col_fetch, col_reset = st.columns([2, 1])
    with col_fetch:
        if st.button("📥 Supabaseからデータを取得", use_container_width=True,
                     disabled=bool(st.session_state.wizard_items)):
            try:
                import config
                url = getattr(config, "SUPABASE_URL", "")
                key = getattr(config, "SUPABASE_KEY", "")
                if not url or not key:
                    st.error("config.py に SUPABASE_URL / SUPABASE_KEY が設定されていません。")
                else:
                    from import_wizard import fetch_supabase_items, group_by_similarity
                    with st.spinner("Supabaseからデータを取得中..."):
                        items = fetch_supabase_items(url, key)
                    with st.spinner(f"{len(items)}件をグルーピング中..."):
                        groups = group_by_similarity(items, threshold=0.6)
                    st.session_state.wizard_items  = items
                    st.session_state.wizard_groups = groups
                    st.success(f"取得完了: {len(items)}件 / {len(groups)}グループ")
                    st.rerun()
            except Exception as e:
                st.error(f"取得エラー: {e}")

    with col_reset:
        if st.button("🔄 リセット", use_container_width=True):
            st.session_state.wizard_items  = []
            st.session_state.wizard_groups = []
            st.session_state.wizard_done   = False
            st.rerun()

    if not st.session_state.wizard_items:
        st.markdown("""
<div style="text-align:center;padding:30px 0;color:#374151">
    <div style="font-size:1.5rem;margin-bottom:8px">⬆️</div>
    <div style="font-size:0.85rem">「Supabaseからデータを取得」を押してください</div>
</div>
""", unsafe_allow_html=True)
    else:

        groups = st.session_state.wizard_groups
        items  = st.session_state.wizard_items

        # ---- サマリ ----
        multi_groups  = [g for g in groups if len(g.items) > 1]
        single_groups = [g for g in groups if len(g.items) == 1]
        sold_items    = [i for i in items if i.sold_count > 0]

        st.markdown(f"""
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">総件数</div>
        <div class="stat-value blue">{len(items)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">グループ数</div>
        <div class="stat-value">{len(groups)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">類似グループ</div>
        <div class="stat-value yellow">{len(multi_groups)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">売却済み</div>
        <div class="stat-value green">{len(sold_items)}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

        # ---- Step2: グループ確認・正規名承認 ----
        st.markdown('<div class="section-label">Step 2: 正規名を確認・修正してください</div>',
                    unsafe_allow_html=True)

        # 類似グループ（確認が必要なもの）を先に表示
        if multi_groups:
            st.markdown("**⚠️ 類似商品グループ（要確認）**")
            for group in multi_groups:
                with st.expander(
                    f"グループ {group.group_id+1}: "
                    f"{group.suggested_canonical[:40]} "
                    f"（{len(group.items)}件）"
                ):
                    # グループ内商品一覧
                    for item in group.items:
                        sold_badge = f"✅ 売却{item.sold_count}回" if item.sold_count > 0 else "　未売却"
                        st.markdown(
                            f"- `{item.cleaned_name[:50]}` "
                            f"　{sold_badge}　[{item.platform}]"
                        )
                    st.divider()
                    # 正規名の確認・修正
                    key_g = f"wizard_canonical_{group.group_id}"
                    new_canonical = st.text_input(
                        "正規名（修正可）",
                        value=group.suggested_canonical,
                        key=key_g,
                    )
                    group.suggested_canonical = new_canonical

            st.markdown("---")

        # 単独グループ（確認不要・一括承認）
        st.markdown(f"**単独商品: {len(single_groups)}件**（自動承認）")
        with st.expander("単独商品一覧を確認"):
            for group in single_groups[:50]:
                item = group.items[0]
                sold_badge = f"✅{item.sold_count}回" if item.sold_count > 0 else ""
                st.markdown(
                    f"- [{item.platform}] `{item.cleaned_name[:45]}` {sold_badge}"
                )
            if len(single_groups) > 50:
                st.caption(f"... 他 {len(single_groups)-50}件")

        # ---- Step3: 一括登録 ----
        st.markdown('<div class="section-label">Step 3: エイリアスDBに登録</div>',
                    unsafe_allow_html=True)

        col_all, col_sold, _ = st.columns([2, 2, 3])
        with col_all:
            if st.button("✅ 全件登録", use_container_width=True, type="primary"):
                from import_wizard import apply_aliases
                # 全グループを承認済みにする
                for g in groups:
                    for item in g.items:
                        item.approved = True
                registered, skipped = apply_aliases(groups, approved_only=False)
                st.success(f"登録完了: {registered}件のエイリアスを登録しました")
                st.session_state.wizard_done = True
                # キャッシュをクリアしてエンジンを再初期化
                st.cache_resource.clear()
                st.rerun()

        with col_sold:
            if st.button("✅ 売却済みのみ登録", use_container_width=True):
                from import_wizard import apply_aliases
                # 売却済みがあるグループのみ承認
                for g in groups:
                    if any(item.sold_count > 0 for item in g.items):
                        for item in g.items:
                            item.approved = True
                registered, skipped = apply_aliases(groups, approved_only=True)
                st.success(f"登録完了: {registered}件（売却済みグループのみ）")
                st.session_state.wizard_done = True
                st.cache_resource.clear()
                st.rerun()

        if st.session_state.wizard_done:
            st.success("✅ 取り込み完了！ウォッチリスト解析タブで照合を試してください。")

    # ============================================================
# TAB 4: 実績サマリ
# ============================================================
with tab_summary:
    st.markdown('<div class="section-label">売買実績サマリ</div>', unsafe_allow_html=True)

    # Supabase から全実績を集計
    try:
        import config, httpx, json as _json
        _url = getattr(config, "SUPABASE_URL", "")
        _key = getattr(config, "SUPABASE_KEY", "")

        if not _url or not _key:
            st.info("config.py に SUPABASE_URL / SUPABASE_KEY を設定してください。")
        else:
            @st.cache_data(ttl=300)  # 5分キャッシュ
            def load_summary_data(url, key):
                client = httpx.Client(
                    base_url=url,
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    timeout=30.0,
                )
                all_items = []
                offset, limit = 0, 1000
                while True:
                    resp = client.get("/rest/v1/items", params={
                        "select": "item_id,name,platform,bid_price,ship_in,sales_json",
                        "limit":  str(limit),
                        "offset": str(offset),
                    })
                    batch = resp.json()
                    if not batch:
                        break
                    all_items.extend(batch)
                    if len(batch) < limit:
                        break
                    offset += limit
                return all_items

            with st.spinner("実績データを読み込み中..."):
                all_items = load_summary_data(_url, _key)

            # 集計
            summary_map = {}
            total_profit = 0
            total_sales  = 0

            for item in all_items:
                name     = item.get("name", "")
                platform = item.get("platform") or ""
                bid      = (item.get("bid_price") or 0) + (item.get("ship_in") or 0)
                sales    = item.get("sales_json") or []
                if isinstance(sales, str):
                    try:
                        sales = _json.loads(sales)
                    except Exception:
                        sales = []

                for s in sales:
                    sold  = s.get("sellPrice") or 0
                    fee   = s.get("fee") or 0
                    ship  = s.get("shipOut") or 0
                    profit = sold - fee - ship - bid
                    date   = s.get("soldAt", "")

                    key = (name, platform)
                    if key not in summary_map:
                        summary_map[key] = {
                            "name": name, "platform": platform,
                            "count": 0, "total_sold": 0, "max_sold": 0,
                            "total_profit": 0, "last_date": "",
                        }
                    d = summary_map[key]
                    d["count"]        += 1
                    d["total_sold"]   += sold
                    d["max_sold"]      = max(d["max_sold"], sold)
                    d["total_profit"] += profit
                    if date and date > d["last_date"]:
                        d["last_date"] = date
                    total_profit += profit
                    total_sales  += 1

            sold_items = [d for d in summary_map.values() if d["count"] > 0]
            sold_items.sort(key=lambda x: x["count"], reverse=True)

            # 統計カード
            st.markdown(f"""
<div class="stat-row">
  <div class="stat-card">
    <div class="stat-label">総販売件数</div>
    <div class="stat-value blue">{total_sales}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">商品種類</div>
    <div class="stat-value">{len(sold_items)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">累計利益</div>
    <div class="stat-value {'green' if total_profit >= 0 else 'red'}">{total_profit:,}円</div>
  </div>
</div>
""", unsafe_allow_html=True)

            if not sold_items:
                st.markdown("""
<div style="text-align:center;padding:40px 0;color:#374151">
    <div style="font-size:2rem;margin-bottom:8px">📊</div>
    <div style="font-size:0.85rem">売却済みデータがまだありません。</div>
</div>
""", unsafe_allow_html=True)
            else:
                rows_html = ""
                for d in sold_items:
                    avg_sell   = int(d["total_sold"]   / d["count"])
                    avg_profit = int(d["total_profit"] / d["count"])
                    profit_color = "#22c55e" if avg_profit >= 0 else "#ef4444"
                    rows_html += f"""
<tr>
  <td>{d['name'][:45]}</td>
  <td style="text-align:center">{d['platform'] or '-'}</td>
  <td style="text-align:center;font-weight:700">{d['count']}</td>
  <td class="mono">{avg_sell:,}円</td>
  <td class="mono">{d['max_sold']:,}円</td>
  <td class="mono" style="color:{profit_color}">{avg_profit:,}円</td>
  <td style="color:#64748b;font-size:0.72rem">{(d['last_date'] or '-')[:10]}</td>
</tr>"""

                st.markdown(f"""
<table class="research-table">
<thead><tr>
  <th>商品名</th><th>機種</th><th style="text-align:center">販売数</th>
  <th>平均売値</th><th>最高売値</th><th>平均利益</th><th>最終販売日</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"データ取得エラー: {e}")
