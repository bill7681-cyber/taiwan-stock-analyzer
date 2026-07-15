import datetime
import html
import os
import re

import analyzer

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "public", "reports")
ARCHIVE_NAV_DAYS = 30


def _build_archive_nav():
    """掃描 public/reports/ 目錄，列出最近 30 天內有報告的日期連結，
    格式如：← 2026-06-06 ｜ 2026-06-05 ｜ 2026-06-04 ..."""
    try:
        filenames = os.listdir(REPORTS_DIR)
    except OSError:
        return ""

    dates = []
    for name in filenames:
        match = re.match(r'^(\d{4}-\d{2}-\d{2})\.html$', name)
        if match:
            dates.append(match.group(1))

    if not dates:
        return ""

    dates.sort(reverse=True)
    dates = dates[:ARCHIVE_NAV_DAYS]

    links = " ｜ ".join(f'<a href="/reports/{d}">{d}</a>' for d in dates)
    return f'<nav class="report-nav">📅 歷史報告：← {links}</nav>'


def _markdown_to_html(markdown_text):
    """將 AI 分析常見的簡易 Markdown 語法轉成 HTML：
    # 標題 -> <h2>、## 標題 -> <h3>、### 標題 -> <h4>、
    **文字** -> <strong>、- 項目 -> <li>（以 <ul> 包裹）、--- -> <hr>。"""

    def format_inline(text):
        escaped = html.escape(text)
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)

    lines = markdown_text.replace('\r', '').split('\n')
    chunks = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            chunks.append('</ul>')
            in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            close_list()
            continue

        if re.match(r'^-{3,}$', stripped):
            close_list()
            chunks.append('<hr>')
            continue

        if stripped.startswith('### '):
            close_list()
            chunks.append(f'<h4>{format_inline(stripped[4:].strip())}</h4>')
            continue

        if stripped.startswith('## '):
            close_list()
            chunks.append(f'<h3>{format_inline(stripped[3:].strip())}</h3>')
            continue

        if stripped.startswith('# '):
            close_list()
            chunks.append(f'<h2>{format_inline(stripped[2:].strip())}</h2>')
            continue

        list_match = re.match(r'^[-+*]\s+(.*)$', stripped)
        if list_match:
            if not in_list:
                chunks.append('<ul>')
                in_list = True
            chunks.append(f'<li>{format_inline(list_match.group(1).strip())}</li>')
            continue

        close_list()
        chunks.append(f'<p>{format_inline(stripped)}</p>')

    close_list()
    return ''.join(chunks)


def _format_change_with_pct(stock):
    """組合漲跌點數與百分比，例如 +10.00 (+0.76%)。
    來源資料只有點數（change / change_float），百分比需自行換算：
    昨收 = 收盤價 - 漲跌點數，漲跌幅 = 漲跌點數 / 昨收 * 100。"""
    change_str = str(stock.get("change", "")).strip()
    try:
        change_float = float(stock.get("change_float", 0) or 0)
        prev_close = float(stock.get("close", 0)) - change_float
        if prev_close == 0:
            return change_str
        pct = change_float / prev_close * 100
        return f"{change_str} ({pct:+.2f}%)"
    except (TypeError, ValueError):
        return change_str


def _format_volume_lots(stock):
    """將成交量從股數轉換成張數（1張=1000股），並加上千分位逗號。"""
    try:
        volume = float(stock.get("volume", 0) or 0)
        return f"{volume / 1000:,.0f}"
    except (TypeError, ValueError):
        return ""


def _format_buy_reason(stock):
    """組合買入訊號觸發原因說明，例如：
    📌 KD黃金交叉(K=32→45) + 站上5日均線 + 成交量增加1.3倍
    優先採用 results 裡的 buy_reason；若為空則依技術指標重新組合出觸發條件說明。"""
    reason = str(stock.get("buy_reason", "") or "").strip()
    if reason:
        return f"📌 {reason}"

    history = stock.get("history") or []
    parts = []

    kd_k = stock.get("kd_k")
    kd_d = stock.get("kd_d")
    if kd_k is not None and kd_d is not None and len(history) >= 2:
        try:
            kd_list = analyzer.calculate_kd(history)
            prev_kd = kd_list[-2]
            if prev_kd["k"] <= prev_kd["d"] and kd_k > kd_d:
                parts.append(f"KD黃金交叉(K={prev_kd['k']:.0f}→{kd_k:.0f})")
        except Exception:
            pass

    try:
        ma5 = stock.get("ma5")
        if ma5 is not None and float(stock.get("close", 0)) > ma5:
            parts.append("站上5日均線")
    except (TypeError, ValueError):
        pass

    if len(history) >= 6:
        last_volume = history[-1]["volume"]
        recent_volumes = [item["volume"] for item in history[-6:-1]]
        avg_vol5 = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
        if avg_vol5 > 0 and last_volume > avg_vol5 * 1.2:
            parts.append(f"成交量增加{last_volume / avg_vol5:.1f}倍")

    if not parts:
        return ""
    return "📌 " + " + ".join(parts)


def _format_technical_status(stock):
    """組合技術面狀態一行說明，格式：📊 K=18.2（✅ 低檔黃金交叉） ｜ 站上月線 ｜ 量增1.96倍"""
    parts = []

    kd_k = stock.get("kd_k")
    if kd_k is not None:
        try:
            k = float(kd_k)
            if k > 80:
                parts.append(f"K={k:.1f}（⚠️ 高檔注意）")
            elif k < 30:
                parts.append(f"K={k:.1f}（✅ 低檔黃金交叉）")
            else:
                parts.append(f"K={k:.1f}")
        except (TypeError, ValueError):
            pass

    try:
        close = float(stock.get("close", 0))
        ma20 = stock.get("ma20")
        if ma20 is not None:
            parts.append("站上月線" if close > float(ma20) else "月線壓力待突破")
    except (TypeError, ValueError):
        pass

    history = stock.get("history") or []
    if len(history) >= 6:
        last_volume = history[-1]["volume"]
        recent_volumes = [item["volume"] for item in history[-6:-1]]
        avg_vol5 = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
        if avg_vol5 > 0:
            parts.append(f"量增{last_volume / avg_vol5:.2f}倍")

    if not parts:
        return ""
    return "📊 " + " ｜ ".join(parts)


def _build_signal_accuracy_block(signal_accuracy):
    """將買入訊號歷史準確率資料（來自 backtester.evaluate_buy_signal_accuracy）轉成 HTML 表格。
    顯示推薦當日收盤價與 N 個交易日後收盤價的漲跌幅統計（勝率、平均報酬率）。"""
    if not signal_accuracy:
        return '<p style="color:#666">📊 歷史訊號準確率累積中，需要更多資料。</p>'

    rows = ""
    for horizon in sorted(signal_accuracy.keys()):
        stat = signal_accuracy.get(horizon) or {}
        total = stat.get("total", 0)
        wins = stat.get("wins", 0)
        win_rate = stat.get("win_rate")
        avg_return = stat.get("avg_return")

        if total > 0 and win_rate is not None and avg_return is not None:
            win_rate_color = "#4ade80" if win_rate >= 50 else "#f87171"
            avg_return_color = "#4ade80" if avg_return >= 0 else "#f87171"
            rows += f"""
            <tr>
              <td>{horizon} 天後</td>
              <td>{total}</td>
              <td>{wins}</td>
              <td style="color:{win_rate_color};font-weight:600">{win_rate:.1f}%</td>
              <td style="color:{avg_return_color};font-weight:600">{avg_return:+.2f}%</td>
            </tr>"""
        else:
            rows += f"""
            <tr>
              <td>{horizon} 天後</td>
              <td colspan="4" style="text-align:center;color:#666">累積中，需要更多資料</td>
            </tr>"""

    return f"""
      <table>
        <thead>
          <tr><th>追蹤天數</th><th>樣本數</th><th>上漲筆數</th><th>勝率</th><th>平均報酬率</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:12px;font-size:0.8rem;color:#6b7280">📌 統計基礎：技術買入訊號觸發當日收盤價，與 N 個交易日後收盤價的漲跌幅比較（樣本持續累積中）</p>"""


def _safe_change_pct(stock):
    """取得百分比漲跌幅，優先使用 change_pct 欄位，否則從 close/change_float 推算。"""
    val = stock.get("change_pct")
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    try:
        change_float = float(stock.get("change_float", 0) or 0)
        close = float(stock.get("close", 0) or 0)
        prev_close = close - change_float
        return change_float / prev_close * 100 if prev_close > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def generate_html_report(results, analysis_text=None, recommendations=None, taiex=None, signal_accuracy=None):
    """把每日分析結果轉成 HTML 報告"""
    today = datetime.date.today()
    date_str = today.strftime("%Y年%m月%d日")
    date_id = today.strftime("%Y-%m-%d")

    archive_nav = _build_archive_nav()
    signal_accuracy_block = _build_signal_accuracy_block(signal_accuracy)

    # 加權指數
    if taiex:
        taiex_change = float(taiex.get("change", 0) or 0)
        taiex_pct = float(taiex.get("change_pct", 0) or 0)
        taiex_css = "up" if taiex_change > 0 else ("down" if taiex_change < 0 else "flat")
        taiex_points = f"{float(taiex.get('points', 0) or 0):,.2f}"
        taiex_sub = f"{taiex_change:+,.2f}（{taiex_pct:+.2f}%）"
    else:
        taiex_css = "flat"
        taiex_points = "—"
        taiex_sub = "今日無加權指數資料"

    sorted_results = sorted(results, key=_safe_change_pct, reverse=True)
    top_gainers = [s for s in sorted_results if _safe_change_pct(s) > 0][:5]
    bottom5 = sorted_results[-5:]
    recs = recommendations or []

    # 漲幅前5列（只顯示上漲股票）
    if top_gainers:
        top5_rows = ""
        for i, s in enumerate(top_gainers, 1):
            top5_rows += f"""
        <tr>
          <td>{i}</td>
          <td><strong>{s['stock_id']}</strong></td>
          <td>{s.get('stock_name','')}</td>
          <td>{s.get('close','')}</td>
          <td style="color:#f87171;font-weight:600">{_format_change_with_pct(s)}</td>
          <td>{_format_volume_lots(s)}</td>
        </tr>"""
    else:
        top5_rows = '<tr><td colspan="6" style="text-align:center;color:#666">今日無上漲股票</td></tr>'

    # 跌幅最深5列
    bottom5_rows = ""
    for i, s in enumerate(bottom5, 1):
        color = "#f87171"
        bottom5_rows += f"""
        <tr>
          <td>{i}</td>
          <td><strong>{s['stock_id']}</strong></td>
          <td>{s.get('stock_name','')}</td>
          <td>{s.get('close','')}</td>
          <td style="color:{color};font-weight:600">{_format_change_with_pct(s)}</td>
          <td>{_format_volume_lots(s)}</td>
        </tr>"""

    # 買入訊號
    rec_rows = ""
    if recs:
        for s in recs[:10]:
            reason_text = _format_buy_reason(s)
            reason_row = ""
            if reason_text:
                reason_row = f"""
            <tr>
              <td colspan="5" style="border-top:none;padding-top:0;color:#94a3b8;font-size:0.82rem">{reason_text}</td>
            </tr>"""
            tech_status = _format_technical_status(s)
            tech_row = ""
            if tech_status:
                tech_row = f"""
            <tr>
              <td colspan="5" style="border-top:none;padding-top:2px;padding-bottom:10px;color:#60a5fa;font-size:0.8rem">{tech_status}</td>
            </tr>"""
            rec_rows += f"""
            <tr>
              <td><strong>{s['stock_id']}</strong></td>
              <td>{s.get('stock_name','')}</td>
              <td>{s.get('close','')}</td>
              <td>{_format_change_with_pct(s)}</td>
              <td>{_format_volume_lots(s)}</td>
            </tr>{reason_row}{tech_row}"""
    else:
        rec_rows = '<tr><td colspan="5" style="text-align:center;color:#666">今日無符合條件的早期訊號</td></tr>'

    # AI 分析文字（將 Markdown 語法轉換成 HTML）
    if analysis_text:
        ai_block = _markdown_to_html(analysis_text)
    else:
        ai_block = "<p style='color:#666'>今日未取得 AI 分析結果。</p>"

    total = len(results)
    up_count = sum(1 for s in results if float(s.get("change_float", 0)) > 0)
    down_count = sum(1 for s in results if float(s.get("change_float", 0)) < 0)
    flat_count = total - up_count - down_count

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>台股分析報告 {date_str}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, 'Segoe UI', sans-serif;
      background: #0a0a0f;
      color: #e2e8f0;
      line-height: 1.6;
    }}
    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      border-bottom: 1px solid #1e3a5f;
      padding: 28px 32px;
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; color: #fff; }}
    header p {{ color: #94a3b8; font-size: 0.9rem; margin-top: 4px; }}
    .report-nav {{
      margin-top: 14px;
      font-size: 0.8rem;
      color: #6b7280;
      line-height: 1.8;
    }}
    .report-nav a {{
      color: #93c5fd;
      text-decoration: none;
      margin: 0 2px;
    }}
    .report-nav a:hover {{ text-decoration: underline; }}
    .container {{ max-width: 960px; margin: 0 auto; padding: 32px 20px; }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 32px;
    }}
    .stat-card {{
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 12px;
      padding: 20px;
      text-align: center;
    }}
    .stat-card .num {{ font-size: 2rem; font-weight: 700; }}
    .stat-card .label {{ font-size: 0.82rem; color: #6b7280; margin-top: 4px; }}
    .up {{ color: #4ade80; }}
    .down {{ color: #f87171; }}
    .flat {{ color: #94a3b8; }}
    section {{ margin-bottom: 36px; }}
    section h2 {{
      font-size: 1.1rem;
      font-weight: 600;
      color: #cbd5e1;
      border-left: 3px solid #3b82f6;
      padding-left: 12px;
      margin-bottom: 16px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #111827;
      border-radius: 12px;
      overflow: hidden;
      font-size: 0.88rem;
    }}
    thead {{ background: #1f2937; }}
    th {{
      padding: 12px 16px;
      text-align: left;
      color: #9ca3af;
      font-weight: 500;
      font-size: 0.8rem;
      letter-spacing: 0.05em;
    }}
    td {{ padding: 12px 16px; border-top: 1px solid #1f2937; }}
    tbody tr:hover {{ background: #1a2234; }}
    .ai-box {{
      background: #0f172a;
      border: 1px solid #1e3a5f;
      border-radius: 12px;
      padding: 24px;
      font-size: 0.9rem;
      line-height: 1.8;
      color: #cbd5e1;
    }}
    .ai-box p {{ margin-bottom: 10px; }}
    .ai-box h2 {{ font-size: 1.15rem; font-weight: 700; color: #fff; margin: 20px 0 12px; }}
    .ai-box h3 {{ font-size: 1rem; font-weight: 600; color: #e2e8f0; margin: 18px 0 10px; }}
    .ai-box h4 {{ font-size: 0.92rem; font-weight: 600; color: #cbd5e1; margin: 14px 0 8px; }}
    .ai-box ul {{ margin: 0 0 12px 1.4em; }}
    .ai-box li {{ margin-bottom: 6px; }}
    .ai-box hr {{ border: none; border-top: 1px solid #1e3a5f; margin: 18px 0; }}
    .ai-box strong {{ color: #fff; }}
    footer {{
      text-align: center;
      padding: 24px;
      color: #374151;
      font-size: 0.8rem;
      border-top: 1px solid #1f2937;
    }}
    @media (max-width: 600px) {{
      .stats-grid {{ grid-template-columns: 1fr; }}
      header {{ padding: 20px 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>📊 台股每日分析報告</h1>
    <p>{date_str} ｜ 台股市值前 150 大自動分析</p>
    {archive_nav}
  </header>

  <div class="container">

    <section>
      <h2>市場總覽</h2>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="num {taiex_css}">{taiex_points}</div>
          <div class="label">加權指數 {taiex_sub}</div>
        </div>
        <div class="stat-card">
          <div class="num">{total}</div>
          <div class="label">分析股票數</div>
        </div>
        <div class="stat-card">
          <div class="num up">{up_count}</div>
          <div class="label">上漲</div>
        </div>
        <div class="stat-card">
          <div class="num down">{down_count}</div>
          <div class="label">下跌</div>
        </div>
      </div>
    </section>

    <section>
      <h2>🚀 漲幅前 5 名</h2>
      <table>
        <thead>
          <tr><th>#</th><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th><th>成交量(張)</th></tr>
        </thead>
        <tbody>{top5_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>📉 跌幅最深 5 名</h2>
      <table>
        <thead>
          <tr><th>#</th><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th><th>成交量(張)</th></tr>
        </thead>
        <tbody>{bottom5_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>💡 技術買入訊號</h2>
      <p style="font-size:0.8rem;color:#6b7280;margin-bottom:14px">※ 篩選條件：KD黃金交叉 ＋ 站上5日均線 ＋ 量增 ＋ 當日漲幅 ≤ 5%（已排除當日漲幅超過5%的個股，避免追高訊號）</p>
      <table>
        <thead>
          <tr><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th><th>成交量(張)</th></tr>
        </thead>
        <tbody>{rec_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>🎯 歷史訊號準確率</h2>
      {signal_accuracy_block}
    </section>

    <section>
      <h2>🤖 AI 市場分析</h2>
      <div class="ai-box">{ai_block}</div>
    </section>

  </div>

  <footer>
    <p>由 taiwan-stock-analyzer 自動生成 ｜ {date_str} 16:30 更新</p>
  </footer>
</body>
</html>"""

    return html
