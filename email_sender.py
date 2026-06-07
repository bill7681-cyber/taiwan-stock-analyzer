import datetime
import html
import os
import re
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from chart_generator import (
    generate_change_bar_chart,
    generate_market_breadth_pie,
    generate_institutional_bar_chart,
    chart_html_block,
    market_breadth_html_block,
    institutional_bar_html_block,
)


def convert_markdown_to_html(markdown_text):
    """Convert a simple Markdown text block into HTML."""
    import re

    def escape_and_format(text):
        escaped = html.escape(text)
        bolded = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
        bolded = re.sub(r'__(.+?)__', r'<b>\1</b>', bolded)
        return bolded

    lines = markdown_text.replace('\r', '').split('\n')
    html_chunks = []
    in_list = False
    paragraph_lines = []

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            content = '<br>'.join(paragraph_lines)
            html_chunks.append(f'<p>{content}</p>')
            paragraph_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_chunks.append('</ul>')
                in_list = False
            flush_paragraph()
            continue

        if stripped.startswith('### '):
            if in_list:
                html_chunks.append('</ul>')
                in_list = False
            flush_paragraph()
            html_chunks.append(f'<h4>{escape_and_format(stripped[4:].strip())}</h4>')
            continue
        if stripped.startswith('## '):
            if in_list:
                html_chunks.append('</ul>')
                in_list = False
            flush_paragraph()
            html_chunks.append(f'<h3>{escape_and_format(stripped[3:].strip())}</h3>')
            continue
        if stripped.startswith('# '):
            if in_list:
                html_chunks.append('</ul>')
                in_list = False
            flush_paragraph()
            html_chunks.append(f'<h2>{escape_and_format(stripped[2:].strip())}</h2>')
            continue

        list_match = re.match(r'^[-+\*]\s+(.*)$', stripped)
        if list_match:
            if not in_list:
                flush_paragraph()
                html_chunks.append('<ul>')
                in_list = True
            html_chunks.append(f'<li>{escape_and_format(list_match.group(1).strip())}</li>')
            continue

        paragraph_lines.append(escape_and_format(stripped))

    if in_list:
        html_chunks.append('</ul>')
    flush_paragraph()
    return ''.join(html_chunks)


def _filter_recommendations(recommendations):
    """篩選推薦清單至最多5支，優先保留法人合計買超 > 0 的股票"""
    if not recommendations:
        return []
    
    # 分類：法人買超 vs 其他
    institutional_positive = []
    others = []
    
    for item in recommendations:
        inst = item.get("institutional") or {}
        three_major_net = inst.get("three_major_net", 0)
        if three_major_net > 0:
            institutional_positive.append(item)
        else:
            others.append(item)
    
    # 優先法人買超，最多5支
    result = institutional_positive + others
    return result[:5]


def generate_email_html(top_gainers, top_losers, analysis_text=None, recommendations=None,
                        ai_backtest=None, indicator_backtest=None, chart_blocks=None):
    """
    生成 HTML 格式的股票分析郵件。
    chart_blocks: dict 可選，keys = 'bar','pie','inst','kline'，values = HTML img 字串。
                  提供時直接使用（CID 發信用）；不提供時自動生成 base64 inline（本地預覽用）。
    """
    today = datetime.date.today().strftime("%Y年%m月%d日")

    # 篩選推薦清單至最多5支
    recommendations = _filter_recommendations(recommendations)

    if chart_blocks is None:
        # 本地預覽：生成 base64 inline 圖表
        all_results = sorted(top_gainers, key=lambda x: x.get("change_float", 0), reverse=True)
        chart_blocks = {
            "bar":  chart_html_block(all_results),
            "pie":  market_breadth_html_block(all_results),
            "inst": institutional_bar_html_block(all_results[:10]),
        }

    chart_block         = chart_blocks.get("bar", "")
    breadth_block       = chart_blocks.get("pie", "")
    institutional_block = chart_blocks.get("inst", "")

    analysis_html = ""
    if analysis_text:
        formatted_analysis = convert_markdown_to_html(analysis_text)
        analysis_html = f"""
            <h2>Claude AI Market Analysis</h2>
            <div class=\"analysis\">{formatted_analysis}</div>
        """

    if recommendations:
        recommendation_html = f"""
            <h2>🤖 AI推薦買入股票</h2>
            <table class="rec-table">
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>股票代號</th>
                        <th>名稱</th>
                        <th>收盤價</th>
                        <th>推薦理由</th>
                    </tr>
                </thead>
                <tbody>
        """
        for idx, item in enumerate(recommendations, 1):
            escaped_reason = html.escape(item.get("buy_reason", "")).replace("\n", "<br>")
            recommendation_html += f"""
                    <tr>
                        <td>{idx}</td>
                        <td><span class=\"stock-id\">{item['stock_id']}</span></td>
                        <td>{item['stock_name']}</td>
                        <td>{item['close']}</td>
                        <td>{escaped_reason}</td>
                    </tr>
            """
        recommendation_html += """
                </tbody>
            </table>
        """
    else:
        recommendation_html = """
            <h2>🤖 AI推薦買入股票</h2>
            <div class=\"analysis\">今日無符合條件之買入股票。</div>
        """

    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: '微軟正黑體', 'Arial Unicode MS', sans-serif;
                background-color: #f5f5f5;
                padding: 20px;
            }}
            .container {{
                max-width: 700px;
                margin: 0 auto;
                background-color: #ffffff;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                text-align: center;
                border-bottom: 3px solid #1e90ff;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #1e90ff;
                margin-top: 0;
                margin-bottom: 10px;
                border-left: 5px solid #1e90ff;
                padding-left: 10px;
            }}
            .date {{
                text-align: center;
                color: #666;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            .table-wrapper {{
                display: flex;
                gap: 20px;
                justify-content: space-between;
                align-items: flex-start;
                margin-top: 15px;
                flex-wrap: wrap;
            }}
            .table-card {{
                flex: 1 1 300px;
                max-width: calc(50% - 10px);
                min-width: 280px;
                box-sizing: border-box;
                margin-bottom: 20px;
            }}
            .table-card h2 {{
                margin-top: 0;
                margin-bottom: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 0;
                table-layout: fixed;
            }}
            th {{
                background-color: #1e90ff;
                color: white;
                padding: 10px 8px;
                text-align: left;
                font-weight: bold;
                border: 1px solid #1e90ff;
                word-break: break-word;
                overflow-wrap: break-word;
            }}
            td {{
                padding: 10px 8px;
                border: 1px solid #ddd;
                word-break: break-word;
                overflow-wrap: break-word;
            }}
            .table-card table th:nth-child(1),
            .table-card table td:nth-child(1) {{ width: 10%; text-align: center; }}
            .table-card table th:nth-child(2),
            .table-card table td:nth-child(2) {{ width: 18%; }}
            .table-card table th:nth-child(3),
            .table-card table td:nth-child(3) {{ width: 34%; }}
            .table-card table th:nth-child(4),
            .table-card table td:nth-child(4) {{ width: 18%; }}
            .table-card table th:nth-child(5),
            .table-card table td:nth-child(5) {{ width: 20%; }}
            .rec-table th:nth-child(1),
            .rec-table td:nth-child(1) {{ width: 8%; text-align: center; }}
            .rec-table th:nth-child(2),
            .rec-table td:nth-child(2) {{ width: 13%; }}
            .rec-table th:nth-child(3),
            .rec-table td:nth-child(3) {{ width: 20%; }}
            .rec-table th:nth-child(4),
            .rec-table td:nth-child(4) {{ width: 13%; }}
            .rec-table th:nth-child(5),
            .rec-table td:nth-child(5) {{ width: 46%; }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            tr:hover {{
                background-color: #f0f8ff;
            }}
            .stock-id {{
                font-weight: bold;
                color: #1e90ff;
            }}
            @media (max-width: 720px) {{
                .table-wrapper {{
                    flex-direction: column;
                }}
                .table-card {{
                    max-width: 100%;
                }}
            }}
            .change-positive {{
                color: #ff4444;
                font-weight: bold;
            }}
            .change-negative {{
                color: #00aa00;
                font-weight: bold;
            }}
            .analysis {{
                margin-top: 15px;
                padding: 15px;
                background-color: #f9f9f9;
                border: 1px solid #e1e1e1;
                border-radius: 6px;
                line-height: 1.7;
                color: #333;
                white-space: pre-wrap;
            }}
            .footer {{
                text-align: center;
                color: #999;
                font-size: 12px;
                margin-top: 30px;
                padding-top: 15px;
                border-top: 1px solid #ddd;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 台股每日分析報告</h1>
            <div class="date">{today}</div>
            <div class="table-wrapper">
                <div class="table-card">
                    <h2>🚀 今日漲幅前10名</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>排名</th>
                                <th>股票代號</th>
                                <th>名稱</th>
                                <th>收盤價</th>
                                <th>漲跌幅</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    for idx, item in enumerate(top_gainers[:10], 1):
        html_content += f"""
                            <tr>
                                <td>{idx}</td>
                                <td><span class=\"stock-id\">{item['stock_id']}</span></td>
                                <td>{item['stock_name']}</td>
                                <td>{item['close']}</td>
                                <td><span class=\"change-positive\">↑ {item['change']}</span></td>
                            </tr>
        """
    html_content += """
                        </tbody>
                    </table>
                </div>
                <div class="table-card">
                    <h2>📉 今日跌幅前5名</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>排名</th>
                                <th>股票代號</th>
                                <th>名稱</th>
                                <th>收盤價</th>
                                <th>跌幅</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    for idx, item in enumerate(top_losers[-5:], 1):
        html_content += f"""
                            <tr>
                                <td>{idx}</td>
                                <td><span class=\"stock-id\">{item['stock_id']}</span></td>
                                <td>{item['stock_name']}</td>
                                <td>{item['close']}</td>
                                <td><span class=\"change-negative\">↓ {item['change']}</span></td>
                            </tr>
        """
    html_content += f"""
                        </tbody>
                    </table>
                </div>
            </div>
            {chart_block}
            {breadth_block}
            {institutional_block}
            {analysis_html}
            {recommendation_html}
            <div class="backtest">
                <h2>📈 AI建議回測結果</h2>
"""

    # AI 回測結果呈現
    if ai_backtest:
        for days, stats in ai_backtest.items():
            if stats.get('note'):
                html_content += f"<p>回溯 {days} 日：{stats.get('note')}</p>"
            else:
                rate = f"{stats.get('rate'):.1f}%" if stats.get('rate') is not None else "N/A"
                html_content += f"<p>回溯 {days} 日：共 {stats.get('total')} 支，{stats.get('wins')} 支上漲，正確率：{rate}</p>"
    else:
        html_content += "<p>AI 建議回測：累積中，需要更多資料。</p>"

    html_content += """
            </div>
            <div class="backtest">
                <h2>🔎 技術指標訊號回測（MACD / KD）</h2>
"""

    # 技術指標回測呈現
    if indicator_backtest:
        if indicator_backtest.get('note'):
            html_content += f"<p>{indicator_backtest.get('note')}</p>"
        else:
            macd = indicator_backtest.get('macd', {})
            kd = indicator_backtest.get('kd', {})
            macd_rate = f"{macd.get('rate'):.1f}%" if macd.get('rate') is not None else "N/A"
            kd_rate = f"{kd.get('rate'):.1f}%" if kd.get('rate') is not None else "N/A"
            html_content += f"<p>MACD 黃金交叉：共 {macd.get('total')} 支，其中 {macd.get('wins')} 支在 {indicator_backtest.get('days_ago')} 日後上漲（成功率：{macd_rate}）</p>"
            html_content += f"<p>KD &lt;20：共 {kd.get('total')} 支，其中 {kd.get('wins')} 支在 {indicator_backtest.get('days_ago')} 日後上漲（成功率：{kd_rate}）</p>"
    else:
        html_content += "<p>技術指標回測：累積中，需要更多資料。</p>"

    html_content += """
            <div class="footer">
                <p>此為自動生成的股票分析報告，僅供參考。</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content


def save_preview_html(html_content: str, path: str = None) -> str:
    """將 HTML 內容儲存為本地預覽檔（data/chart_preview.html）。"""
    if path is None:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "data", "chart_preview.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[preview] HTML saved: {path}")
    return path


def _cid_img_block(cid: str, alt: str, style: str = "max-width:100%;") -> str:
    return (
        f'<div style="width:100%;display:block;text-align:center;margin:16px 0;">'
        f'<img src="cid:{cid}" alt="{alt}" '
        f'style="{style}border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.12);">'
        f'</div>'
    )


def send_email_notification(results, analysis_text=None, recommendations=None,
                            ai_backtest=None, indicator_backtest=None):
    """發送 Gmail 通知郵件（圖表以 CID MIME 附件嵌入，避免 Gmail base64 封鎖與 102KB 截斷）。"""
    try:
        sender_email    = os.getenv("GMAIL_SENDER_EMAIL")
        receiver_emails = [
            "bill7681@gmail.com",
            "wilsonche92@gmail.com",
            "st875052007@gmail.com",
            "peitzu498500@gmail.com",
        ]
        app_password = os.getenv("GMAIL_APP_PASSWORD")

        if not sender_email or not app_password:
            print("Email failed: missing GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD in .env")
            return False

        # ── 1. 生成三張圖表 bytes ──
        all_sorted = sorted(results, key=lambda x: x.get("change_float", 0), reverse=True)

        _charts = {
            "chart_bar":  (generate_change_bar_chart(all_sorted),       "漲跌幅排行圖"),
            "chart_pie":  (generate_market_breadth_pie(all_sorted),     "大盤多空比例圖"),
            "chart_inst": (generate_institutional_bar_chart(all_sorted[:10]), "法人買賣超圖"),
        }
        charts = {cid: v for cid, v in _charts.items() if v[0]}

        # ── 2. 組 CID HTML 區塊 ──
        chart_blocks = {
            "bar":  _cid_img_block("chart_bar",  "漲跌幅排行圖")  if "chart_bar"  in charts else "",
            "pie":  _cid_img_block("chart_pie",  "大盤多空比例圖") if "chart_pie"  in charts else "",
            "inst": _cid_img_block("chart_inst", "法人買賣超圖")   if "chart_inst" in charts else "",
        }

        # ── 3. 生成 HTML body（CID 引用，不含 base64） ──
        html_content = generate_email_html(
            results, results,
            analysis_text=analysis_text,
            recommendations=recommendations,
            ai_backtest=ai_backtest,
            indicator_backtest=indicator_backtest,
            chart_blocks=chart_blocks,
        )
        html_content = re.sub(r'\n[ \t]+\n', '\n', html_content)
        html_content = re.sub(r'\n{3,}', '\n\n', html_content)

        # ── 4. 儲存本地預覽（base64 版） ──
        preview_html = generate_email_html(
            results, results,
            analysis_text=analysis_text,
            recommendations=recommendations,
            ai_backtest=ai_backtest,
            indicator_backtest=indicator_backtest,
        )
        save_preview_html(preview_html)

        # ── 5. 組 MIME 郵件 ──
        # 正確結構：multipart/related
        #            └── multipart/alternative   ← Gmail 需要此層才能解析 CID
        #                 └── text/html
        #            ├── image/png  [Content-ID: <chart_bar>]
        #            ├── image/png  [Content-ID: <chart_pie>]
        #            └── image/png  [Content-ID: <chart_inst>]
        msg = MIMEMultipart("related")
        msg["Subject"] = f"[Taiwan Stock] Daily Report - {datetime.date.today().strftime('%Y-%m-%d')}"
        msg["From"]    = sender_email
        msg["To"]      = ", ".join(receiver_emails)

        alt_wrapper = MIMEMultipart("alternative")
        alt_wrapper.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt_wrapper)

        for cid, (img_bytes, _alt_text) in charts.items():
            mime_img = MIMEImage(img_bytes, "png")
            mime_img.add_header("Content-ID", f"<{cid}>")
            mime_img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
            msg.attach(mime_img)

        # ── 6. 發送 ──
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_emails, msg.as_string())

        body_kb = len(html_content.encode("utf-8")) / 1024
        print(f"Email sent OK. HTML body: {body_kb:.1f} KB, images: {len(charts)}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("Email failed: Gmail auth error — check app password")
        return False
    except smtplib.SMTPException as e:
        print(f"Email failed (SMTP): {e}")
        return False
    except Exception as e:
        print(f"Email failed: {e}")
        return False
