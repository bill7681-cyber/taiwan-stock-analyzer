import datetime
import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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


def generate_email_html(top_gainers, top_losers, analysis_text=None, recommendations=None, ai_backtest=None, indicator_backtest=None):
    """生成 HTML 格式的股票分析郵件"""
    today = datetime.date.today().strftime("%Y年%m月%d日")
    analysis_html = ""
    if analysis_text:
        formatted_analysis = convert_markdown_to_html(analysis_text)
        analysis_html = f"""
            <h2>🧠 Claude AI 市場分析</h2>
            <div class=\"analysis\">{formatted_analysis}</div>
        """

    if recommendations:
        recommendation_html = f"""
            <h2>🤖 AI推薦買入股票</h2>
            <table>
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
                max-width: 800px;
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
            }}
            th {{
                background-color: #1e90ff;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: bold;
                border: 1px solid #1e90ff;
            }}
            td {{
                padding: 12px;
                border: 1px solid #ddd;
            }}
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


def send_email_notification(results, analysis_text=None, recommendations=None, ai_backtest=None, indicator_backtest=None):
    """發送 Gmail 通知郵件"""
    try:
        sender_email = os.getenv("GMAIL_SENDER_EMAIL")
        receiver_emails = [
            "bill7681@gmail.com",
            "wilsonche92@gmail.com",
            "st875052007@gmail.com",
            "peitzu498500@gmail.com",
        ]
        app_password = os.getenv("GMAIL_APP_PASSWORD")

        if not sender_email or not receiver_emails or not app_password:
            print("❌ 郵件發送失敗：缺少 Gmail 環境變數，請檢查 .env 是否設定 GMAIL_SENDER_EMAIL 和 GMAIL_APP_PASSWORD")
            return False

        html_content = generate_email_html(
            results,
            results,
            analysis_text=analysis_text,
            recommendations=recommendations,
            ai_backtest=ai_backtest,
            indicator_backtest=indicator_backtest,
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 台股每日分析報告 - {datetime.date.today().strftime('%Y年%m月%d日')}"
        msg["From"] = sender_email
        msg["To"] = ", ".join(receiver_emails)

        html_part = MIMEText(html_content, "html", "utf-8")
        msg.attach(html_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_emails, msg.as_string())

        print("✅ 郵件發送成功！")
        return True

    except smtplib.SMTPAuthenticationError:
        print("❌ 郵件發送失敗：Gmail 認證失敗，請檢查應用程式密碼是否正確")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ 郵件發送失敗：{e}")
        return False
    except Exception as e:
        print(f"❌ 郵件發送失敗：{e}")
        return False
