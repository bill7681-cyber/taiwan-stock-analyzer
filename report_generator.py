import datetime
import html
import re


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


def generate_html_report(results, analysis_text=None, recommendations=None, taiex=None):
    """把每日分析結果轉成 HTML 報告"""
    today = datetime.date.today()
    date_str = today.strftime("%Y年%m月%d日")
    date_id = today.strftime("%Y-%m-%d")

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

    top5 = results[:5]
    bottom5 = results[-5:]
    recs = recommendations or []

    # 漲幅前5列
    top5_rows = ""
    for i, s in enumerate(top5, 1):
        color = "#4ade80"
        top5_rows += f"""
        <tr>
          <td>{i}</td>
          <td><strong>{s['stock_id']}</strong></td>
          <td>{s.get('stock_name','')}</td>
          <td>{s.get('close','')}</td>
          <td style="color:{color};font-weight:600">{_format_change_with_pct(s)}</td>
          <td>{_format_volume_lots(s)}</td>
        </tr>"""

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
            rec_rows += f"""
            <tr>
              <td><strong>{s['stock_id']}</strong></td>
              <td>{s.get('stock_name','')}</td>
              <td>{s.get('close','')}</td>
              <td>{_format_change_with_pct(s)}</td>
            </tr>"""
    else:
        rec_rows = '<tr><td colspan="4" style="text-align:center;color:#666">今日無明確買入訊號</td></tr>'

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
      <table>
        <thead>
          <tr><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th></tr>
        </thead>
        <tbody>{rec_rows}</tbody>
      </table>
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
