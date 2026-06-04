import datetime
import html
import os
import requests
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

STOCK_DAY_API = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
MARKET_CAP_API = "https://www.twse.com.tw/exchangeReport/MI_INDEX"


def get_month_strings(months=2):
    today = datetime.date.today()
    result = []
    for _ in range(months):
        result.append(today.strftime("%Y%m"))
        first_day = today.replace(day=1)
        today = first_day - datetime.timedelta(days=1)
    return result


def fetch_top_stocks_by_market_cap(limit=150):
    """從 TWSE 取得市值前 N 大的股票清單"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    stocks = []
    
    try:
        api_url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL"
        today = datetime.date.today()
        params = {
            "response": "json",
            "date": today.strftime("%Y%m%d"),
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
        
        if payload.get("stat") == "OK":
            rows = payload.get("data", [])
            for row in rows:
                if len(row) >= 2:
                    stock_id = row[0].strip()
                    stock_name = row[1].strip()
                    if stock_id.isdigit() and len(stock_id) == 4 and not stock_id.startswith('0'):
                        stocks.append({"id": stock_id, "name": stock_name})
                        if len(stocks) >= limit:
                            break
            
            if len(stocks) > 0:
                return stocks
        
        raise RuntimeError("無法從 TWSE API 取得足夠的股票資料")
            
    except Exception as exc:
        print(f"警告：{exc}")
        print("將使用常見股票清單作為備用方案...")
        stocks = fetch_popular_stocks(limit)
    
    return stocks


def parse_int(value):
    try:
        return int(str(value).replace(',', '').replace('X', '').strip())
    except Exception:
        return 0


def parse_float(value):
    try:
        return float(str(value).replace(',', '').replace('X', '').strip())
    except Exception:
        return 0.0


def fetch_stock_history(stock_id, days=30):
    """抓取股票近 N 個交易日的歷史價格資料"""
    months = get_month_strings(3)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    all_rows = []

    for month in reversed(months):
        params = {
            "response": "json",
            "date": month,
            "stockNo": stock_id,
        }
        try:
            response = requests.get(STOCK_DAY_API, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if payload.get("stat") != "OK":
                continue

            rows = payload.get("data", [])
            if rows:
                all_rows.extend(rows)
        except Exception:
            continue

    if not all_rows:
        return []

    history = []
    for row in all_rows:
        if len(row) < 7:
            continue

        close_price = parse_float(row[6])
        if close_price <= 0:
            continue

        history.append({
            "date": row[0],
            "volume": parse_int(row[1]),
            "open": parse_float(row[3]),
            "high": parse_float(row[4]),
            "low": parse_float(row[5]),
            "close": close_price,
            "change": str(row[7]).strip(),
        })

    history.sort(key=lambda x: x["date"])
    return history[-days:]


def calculate_kd(history):
    """計算 KD 指標序列"""
    kd_list = []
    k = 50.0
    d = 50.0

    for idx in range(len(history)):
        window = history[max(0, idx - 8): idx + 1]
        high_n = max(item["high"] for item in window)
        low_n = min(item["low"] for item in window)
        close = history[idx]["close"]

        if high_n == low_n:
            rsv = 50.0
        else:
            rsv = (close - low_n) / (high_n - low_n) * 100

        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        kd_list.append({"k": k, "d": d, "rsv": rsv})

    return kd_list


def fetch_latest_price(stock_id):
    """抓取單一股票的今日收盤價和漲跌幅，並計算技術指標"""
    history = fetch_stock_history(stock_id, days=30)
    if not history:
        return None

    latest = history[-1]
    close_price = f"{latest['close']:.2f}"
    price_change = latest["change"]

    try:
        change_float = float(str(price_change).replace(',', '').replace('+', '').strip())
    except ValueError:
        change_float = 0.0

    ma5 = sum(item["close"] for item in history[-5:]) / 5 if len(history) >= 5 else None
    ma20 = sum(item["close"] for item in history[-20:]) / 20 if len(history) >= 20 else None

    kd_list = calculate_kd(history)
    current_kd = kd_list[-1] if kd_list else {"k": 0.0, "d": 0.0}
    prev_kd = kd_list[-2] if len(kd_list) >= 2 else current_kd
    golden_cross = prev_kd["k"] <= prev_kd["d"] and current_kd["k"] > current_kd["d"]

    last_volume = latest["volume"]
    recent_volumes = [item["volume"] for item in history[-6:-1]]
    avg_vol5 = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
    volume_increase = avg_vol5 > 0 and last_volume > avg_vol5 * 1.2
    above_5ma = ma5 is not None and latest["close"] > ma5
    buy_signal = golden_cross or (above_5ma and volume_increase)

    buy_reasons = []
    if golden_cross:
        buy_reasons.append(f"KD黃金交叉（K={current_kd['k']:.1f}、D={current_kd['d']:.1f}）")
    if above_5ma and volume_increase:
        buy_reasons.append(
            f"股價站上5日均線且量增（今日量={last_volume:,}, 5日均量={avg_vol5:,.0f}）"
        )

    return {
        "stock_id": stock_id,
        "stock_name": "",
        "date": latest["date"],
        "close": close_price,
        "change": price_change,
        "change_float": change_float,
        "ma5": ma5,
        "ma20": ma20,
        "kd_k": current_kd["k"],
        "kd_d": current_kd["d"],
        "buy_signal": buy_signal,
        "buy_reason": "；".join(buy_reasons) if buy_reasons else "",
    }


def fetch_popular_stocks(limit=150):
    """備用方案：取得常見的台灣股票清單"""
    # 這是一個備用的股票清單，包含常見的台灣股票（按市值排序）
    popular_stocks_data = {
        "2330": "台積電",
        "2317": "鴻海",
        "2454": "聯發科",
        "2412": "中華電",
        "2308": "台達電",
        "2881": "富邦金",
        "2882": "國泰金",
        "2891": "中信金",
        "2892": "第一金",
        "2887": "台新金",
        "2885": "元大金",
        "1303": "台塑",
        "1301": "台塑化",
        "2409": "友達",
        "2435": "奇力新",
        "3711": "日月光",
        "2498": "宏達電",
        "2357": "瑞昱",
        "2382": "廣達",
        "2880": "華南金",
        "2301": "光磊",
        "2327": "微星",
        "2355": "華碩",
        "2379": "瑞昱",
        "2390": "互盛",
        "2408": "南科",
        "2411": "高通",
        "2420": "新磊",
        "2425": "互盛",
        "2441": "超豐",
        "2448": "晶體",
        "2451": "創意",
        "2458": "義隆",
        "2474": "緯穎",
        "2492": "華新科",
        "2501": "國巨",
        "2535": "宏普",
        "2542": "興勤",
        "2603": "長榮",
        "2609": "陽明",
        "2615": "萬海",
        "2618": "浩鼎",
        "2633": "台灣高鐵",
        "2701": "南港",
        "2702": "華碩",
        "2801": "彩晶",
        "2823": "中環",
        "2826": "交通銀行",
        "2832": "台產",
        "2833": "台險",
        "2834": "臺灣銀行",
        "2836": "和泰",
        "2845": "遠傳",
        "2847": "台塑",
        "2849": "首信",
        "2850": "世界",
        "2851": "中信",
        "2852": "國泰",
        "2880": "華南金",
        "2881": "富邦金",
        "2882": "國泰金",
        "2883": "開發金",
        "2884": "玉山金",
        "2885": "元大金",
        "2886": "兆豐金",
        "2887": "台新金",
        "2888": "新光金",
        "2889": "國票金",
        "2890": "永豐金",
        "2891": "中信金",
        "2892": "第一金",
        "3008": "大立光",
        "3017": "奇美",
        "3019": "亞光",
        "3034": "聯詠",
        "3037": "欣興",
        "3045": "尖點",
        "3047": "銘異",
        "3050": "鈺寶科",
        "3054": "立萬歲",
        "3055": "蔚華科",
        "3057": "喜鴻",
        "3064": "銘異",
        "3066": "瑞磁",
        "3078": "僑威",
        "3105": "正達",
        "3149": "陽光",
        "3229": "晶鑫",
        "3231": "緯創",
        "3289": "宏科",
        "3437": "榮瑋",
        "3443": "創意",
        "3501": "鑫禾",
        "3533": "嘉澤",
        "3545": "同欣電",
        "3557": "嘉澤",
        "3579": "尖點",
        "3682": "亞光",
        "3711": "日月光",
        "3713": "力旺",
        "3714": "富采",
        "3721": "磊晶",
        "3722": "台積電",
        "3764": "老虎",
        "4904": "遠傳",
        "4938": "和泰",
        "5269": "祥碩",
        "5心": "宏普",
        "5521": "工業技術研究院",
        "5607": "遠端",
        "5608": "顥天",
        "5854": "愛普",
        "6005": "群益證",
        "6024": "群益期",
        "6066": "王磊",
        "6116": "相紙",
        "6121": "新普",
        "6125": "瑞磁",
        "6147": "力晶",
        "6176": "瑞昱",
        "6239": "力積電",
        "6269": "台郡",
        "6415": "矽格",
        "6442": "光磊",
        "6505": "台塑化",
        "6525": "捷敏",
        "6669": "緯軟",
        "8016": "矽創",
        "8028": "鉅祥",
        "8081": "致新",
        "8367": "光寶",
        "8454": "富邦媒",
        "9910": "豐泰",
        "9914": "美利達",
        "9917": "中美矽晶",
        "9921": "巨大",
        "9926": "新光紡",
        "9927": "中視",
        "9928": "中視",
        "9929": "華碩",
        "9933": "中華電",
        "9938": "百和",
        "9941": "裕融",
        "9942": "茂迪",
        "9945": "潤泰全",
        "9950": "股神",
    }
    
    stocks = [{"id": stock_id, "name": name} for stock_id, name in popular_stocks_data.items()]
    return stocks[:limit]


def fetch_latest_price(stock_id):
    """抓取單一股票的今日收盤價和漲跌幅"""
    months = get_month_strings(2)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    for month in months:
        params = {
            "response": "json",
            "date": month,
            "stockNo": stock_id,
        }
        try:
            response = requests.get(STOCK_DAY_API, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if payload.get("stat") != "OK":
                continue

            rows = payload.get("data", [])
            if not rows:
                continue

            latest = rows[-1]
            date = latest[0]
            close_price = latest[6].replace(",", "")
            price_change = latest[7].replace(",", "")
            
            # 轉換漲跌為浮點數便於排序
            try:
                change_float = float(price_change)
            except ValueError:
                change_float = 0.0
            
            return {
                "stock_id": stock_id,
                "stock_name": "",
                "date": date,
                "close": close_price,
                "change": price_change,
                "change_float": change_float,
            }
        except Exception:
            continue

    return None


def print_stock_list(stocks):
    """印出股票列表"""
    print("\n" + "="*80)
    print(f"{'股票代號':<10}{'名稱':<20}{'日期':<12}{'收盤價':<12}{'漲跌幅':<12}")
    print("="*80)
    for item in stocks:
        print(
            f"{item['stock_id']:<10}{item['stock_name']:<20}{item['date']:<12}{item['close']:<12}{item['change']:<12}"
        )
    print("="*80 + "\n")


def generate_email_html(top_gainers, top_losers, analysis_text=None, recommendations=None):
    """生成 HTML 格式的股票分析郵件"""
    today = datetime.date.today().strftime("%Y年%m月%d日")
    analysis_html = ""
    if analysis_text:
        escaped_analysis = html.escape(analysis_text).replace("\n", "<br>")
        analysis_html = f"""
            <h2>🧠 Claude AI 市場分析</h2>
            <div class=\"analysis\">{escaped_analysis}</div>
        """

    recommendation_html = ""
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
                margin-top: 25px;
                border-left: 5px solid #1e90ff;
                padding-left: 10px;
            }}
            .date {{
                text-align: center;
                color: #666;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
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
                        <td><span class="stock-id">{item['stock_id']}</span></td>
                        <td>{item['stock_name']}</td>
                        <td>{item['close']}</td>
                        <td><span class="change-positive">↑ {item['change']}</span></td>
                    </tr>
        """
    
    html_content += """
                </tbody>
            </table>
            
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
                        <td><span class="stock-id">{item['stock_id']}</span></td>
                        <td>{item['stock_name']}</td>
                        <td>{item['close']}</td>
                        <td><span class="change-negative">↓ {item['change']}</span></td>
                    </tr>
        """
    
    html_content += f"""
                </tbody>
            </table>
            {analysis_html}
            {recommendation_html}
            <div class="footer">
                <p>此為自動生成的股票分析報告，僅供參考。</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content


def send_email_notification(results, analysis_text=None, recommendations=None):
    """發送 Gmail 通知郵件"""
    try:
        # Gmail 信息從環境變數讀取
        sender_email = os.getenv("GMAIL_SENDER_EMAIL")
        receiver_emails = [email.strip() for email in os.getenv("GMAIL_RECEIVER_EMAILS", "").split(",") if email.strip()]
        app_password = os.getenv("GMAIL_APP_PASSWORD")

        if not sender_email or not receiver_emails or not app_password:
            print("❌ 郵件發送失敗：缺少 Gmail 環境變數，請檢查 .env 是否設定 GMAIL_SENDER_EMAIL、GMAIL_RECEIVER_EMAILS 和 GMAIL_APP_PASSWORD")
            return False

        # 生成郵件內容
        html_content = generate_email_html(
            results,
            results,
            analysis_text=analysis_text,
            recommendations=recommendations,
        )
        
        # 創建郵件對象
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 台股每日分析報告 - {datetime.date.today().strftime('%Y年%m月%d日')}"
        msg["From"] = sender_email
        msg["To"] = ", ".join(receiver_emails)
        
        # 添加 HTML 內容
        html_part = MIMEText(html_content, "html", "utf-8")
        msg.attach(html_part)
        
        # 發送郵件
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


def analyze_with_ai(results):
    """使用 OpenRouter API 的 Claude 模型分析台股數據"""
    try:
        # OpenRouter API 配置從環境變數讀取
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_endpoint = "https://openrouter.ai/api/v1/chat/completions"

        if not api_key:
            print("❌ AI 分析失敗：缺少 OPENROUTER_API_KEY 環境變數，請檢查 .env 是否設定")
            return None
        
        # 準備分析數據
        top_gainers = results[:10]  # 漲幅前 10 名
        top_losers = results[-5:]  # 跌幅前 5 名
        
        # 構建股票數據文本
        gainers_text = "漲幅前10名：\n"
        for idx, stock in enumerate(top_gainers, 1):
            gainers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"
        
        losers_text = "跌幅前5名：\n"
        for idx, stock in enumerate(top_losers, 1):
            losers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"
        
        # 計算統計數據
        total_stocks = len(results)
        up_count = sum(1 for s in results if s["change_float"] > 0)
        down_count = sum(1 for s in results if s["change_float"] < 0)
        avg_change = sum(s["change_float"] for s in results) / total_stocks if total_stocks > 0 else 0
        
        stats_text = f"統計數據：\n"
        stats_text += f"- 分析股票數：{total_stocks}\n"
        stats_text += f"- 上漲股票數：{up_count}（{up_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 下跌股票數：{down_count}（{down_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 平均漲幅：{avg_change:.2f}%\n"
        
        # 構建提示詞
        prompt = f"""請針對以下台股前150大股票的今日漲跌數據進行分析，並以繁體中文提供深入的市場分析。

{gainers_text}

{losers_text}

{stats_text}

請提供以下四點分析：

1. **今日大盤趨勢**：分析整體市場走勢、上升或下跌的主要原因，以及市場情緒。

2. **值得關注的強勢股**：從漲幅前10名的股票中，分析哪些股票具有持續上漲的潛力，以及背後的可能原因。

3. **需要注意的弱勢股**：從跌幅前5名的股票中，分析這些股票下跌的原因，以及是否存在反彈機會。

4. **明日操作建議**：基於今日分析，提供投資者明日可能的操作策略和需要關注的重點。

請用專業但易懂的語言進行分析，並避免過度樂觀或悲觀的表述。"""
        
        # 調用 OpenRouter API
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "anthropic/claude-sonnet-4-5",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            analysis_text = data["choices"][0]["message"]["content"]
            return analysis_text
        else:
            return "無法獲取 AI 分析結果"
    
    except requests.exceptions.Timeout:
        print("❌ AI 分析超時：API 響應時間過長")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ AI 分析失敗：無法連接 OpenRouter API")
        return None
    except Exception as e:
        print(f"❌ AI 分析失敗：{e}")
        return None


def main():
    print("正在取得台股市值前150大的股票清單...")
    try:
        top_stocks = fetch_top_stocks_by_market_cap(limit=150)
        print(f"已取得 {len(top_stocks)} 支股票清單")
    except Exception as exc:
        print(f"錯誤：{exc}")
        sys.exit(1)
    
    print("\n正在逐一抓取股票報價...")
    results = []
    success_count = 0
    
    for idx, stock in enumerate(top_stocks, 1):
        try:
            stock_id = stock["id"]
            stock_name = stock["name"]
            print(f"[{idx}/{len(top_stocks)}] 抓取 {stock_id} ({stock_name})...", end=" ", flush=True)
            
            data = fetch_latest_price(stock_id)
            if data:
                data["stock_name"] = stock_name
                results.append(data)
                print("✓")
                success_count += 1
            else:
                print("✗ (無法取得資料)")
        except Exception as exc:
            print(f"✗ (錯誤：{exc})")
    
    print(f"\n成功抓取 {success_count}/{len(top_stocks)} 支股票的資料\n")
    
    # 依照漲跌幅排序（從高到低）
    results.sort(key=lambda x: x["change_float"], reverse=True)
    
    # 印出結果
    print_stock_list(results)
    
    # 統計資訊
    if results:
        print(f"漲幅前5名：")
        for idx, item in enumerate(results[:5], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")
        
        print(f"\n跌幅最深的5支：")
        for idx, item in enumerate(results[-5:], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")
        
        buy_candidates = [item for item in results if item.get("buy_signal")]

        # 使用 AI 進行分析
        print("\n正在使用 Claude 進行 AI 分析...")
        analysis = analyze_with_ai(results)
        if analysis:
            print("\n" + "="*80)
            print("📊 Claude AI 分析結果")
            print("="*80)
            print(analysis)
            print("="*80 + "\n")
        else:
            analysis = None
            print("⚠️ 未能取得 AI 分析結果，郵件仍會照常發送。")

        # 發送 Gmail 通知
        print("\n正在發送 Gmail 通知郵件...")
        send_email_notification(
            results,
            analysis_text=analysis,
            recommendations=buy_candidates,
        )


if __name__ == "__main__":
    main()
