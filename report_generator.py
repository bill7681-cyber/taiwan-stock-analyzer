import datetime


def generate_html_report(results, analysis_text=None, recommendations=None):
    """把每日分析結果轉成 HTML 報告"""
    today = datetime.date.today()
    date_str = today.strftime("%Y年%m月%d日")
    date_id = today.strftime("%Y-%m-%d")

    top5 = results[:5]
    bottom5 = results[-5:]
    recs = recommendations or []

    # 漲幅前5列
    top5_rows = ""
    for i, s in enumerate(top5, 1):
        pct = float(s.get("change_float", 0))
        color = "#4ade80"
        top5_rows += f"""
        <tr>
          <td>{i}</td>
          <td><strong>{s['stock_id']}</strong></td>
          <td>{s.get('stock_name','')}</td>
          <td>{s.get('close','')}</td>
          <td style="color:{color};font-weight:600">{s.get('change','')}</td>
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
          <td style="color:{color};font-weight:600">{s.get('change','')}</td>
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
              <td>{s.get('change','')}</td>
            </tr>"""
    else:
        rec_rows = '<tr><td colspan="4" style="text-align:center;color:#666">今日無明確買入訊號</td></tr>'

    # AI 分析文字
    ai_block = ""
    if analysis_text:
        paragraphs = analysis_text.replace("\r\n", "\n").split("\n")
        ai_block = "".join(
            f"<p>{p}</p>" if p.strip() else "<br>"
            for p in paragraphs
        )
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
      grid-template-columns: repeat(3, 1fr);
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
          <tr><th>#</th><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th></tr>
        </thead>
        <tbody>{top5_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>📉 跌幅最深 5 名</h2>
      <table>
        <thead>
          <tr><th>#</th><th>代號</th><th>名稱</th><th>收盤價</th><th>漲跌幅</th></tr>
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
