import os
import requests


def analyze_with_ai(stock_data):
    """使用 OpenRouter API 的 Claude 模型分析台股數據"""
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_endpoint = "https://openrouter.ai/api/v1/chat/completions"

        if not api_key:
            print("❌ AI 分析失敗：缺少 OPENROUTER_API_KEY 環境變數，請檢查 .env 是否設定")
            return None

        results = stock_data.get("stocks") if isinstance(stock_data, dict) else stock_data
        if results is None:
            results = []

        top_gainers = results[:10]
        top_losers = results[-5:]

        gainers_text = "漲幅前10名：\n"
        for idx, stock in enumerate(top_gainers, 1):
            gainers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"

        losers_text = "跌幅前5名：\n"
        for idx, stock in enumerate(top_losers, 1):
            losers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"

        def format_institutional(stock):
            ins = stock.get("institutional") or {}
            if not ins:
                return f"{stock['stock_id']} ({stock['stock_name']}): 未取得法人資料\n"
            return (
                f"{stock['stock_id']} ({stock['stock_name']}): 外資{ins.get('foreign_net', 0):,}、"
                f"投信{ins.get('investment_trust_net', 0):,}、自營商{ins.get('dealer_net', 0):,}\n"
            )

        institutional_text = "法人籌碼摘要：\n"
        for stock in top_gainers[:3] + top_losers[:2]:
            institutional_text += format_institutional(stock)

        institutional_available = any(
            stock.get("institutional") for stock in top_gainers[:3] + top_losers[:2]
        )

        def format_news(stock):
            if not stock.get("news"):
                return f"{stock['stock_id']} ({stock['stock_name']}): 無近期新聞\n"
            text = f"{stock['stock_id']} ({stock['stock_name']}):\n"
            for item in stock["news"][:2]:
                text += f"  - {item['published']} {item['title']} ({item['link']})\n"
            return text

        news_text = "近期新聞摘要：\n"
        for stock in top_gainers[:2] + top_losers[:2]:
            news_text += format_news(stock)

        total_stocks = len(results)
        up_count = sum(1 for s in results if s.get("change_float", 0) > 0)
        down_count = sum(1 for s in results if s.get("change_float", 0) < 0)
        avg_change = sum(s.get("change_pct", 0) for s in results) / total_stocks if total_stocks > 0 else 0

        stats_text = "統計數據：\n"
        stats_text += f"- 分析股票數：{total_stocks}\n"
        stats_text += f"- 上漲股票數：{up_count}（{up_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 下跌股票數：{down_count}（{down_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 平均漲幅：{avg_change:.2f}%\n"

        if institutional_available:
            recommendation_rules = (
                "- 推薦清單最多 5 支股票，請只列出最符合條件的個股，不要把所有符合條件的股票都列出。\n"
                "- 每支推薦股票必須同時滿足至少兩個條件：\n"
                "  1. 技術面：收盤價站上 5 日均線，且成交量有放大（相對於昨日或近五日平均量）。\n"
                "  2. 籌碼面：法人合計買超 > 0（外資 + 投信 + 自營商）。\n"
                "  3. 消息面：有近期正面新聞或利多題材。\n"
                "- 每支推薦請附上綜合評分（1-5 星）和一句話理由。\n"
                "- 若整體法人籌碼偏空，請根據實際數據說明原因，並依當日情況給出具體操作建議，不要以固定套語帶過。\n"
            )
            section_four = "4. **法人籌碼與新聞影響**：評估法人籌碼與近期新聞對個股及整體市場的影響。\n\n"
        else:
            recommendation_rules = (
                "- 今日法人籌碼資料尚未到位（今日法人數據待補），請勿臆測或捏造法人買賣超數字。\n"
                "- 推薦清單最多 5 支股票，請只列出最符合條件的個股，不要把所有符合條件的股票都列出。\n"
                "- 每支推薦股票必須同時滿足至少兩個條件：\n"
                "  1. 技術面：收盤價站上 5 日均線，且成交量有放大（相對於昨日或近五日平均量）。\n"
                "  2. 產業面：所屬產業出現資金輪動或同族群股票同步表現的跡象。\n"
                "  3. 消息面：有近期正面新聞或利多題材。\n"
                "- 每支推薦請附上綜合評分（1-5 星）和一句話理由。\n"
            )
            section_four = (
                "4. **技術面訊號與產業輪動**：今日法人籌碼資料尚未到位，請在本段開頭明確標示「今日法人數據待補」，"
                "並改為著重分析技術面訊號（如均線、成交量變化、KD、MACD 等指標）以及產業輪動現象"
                "（資金在不同產業族群間的流動方向與強弱），不要硬寫法人籌碼分析內容。\n\n"
            )

        prompt = (
            "請針對以下台股前150大股票的今日漲跌數據進行分析，並以繁體中文提供深入的市場分析。\n\n"
            f"{gainers_text}\n{losers_text}\n{institutional_text}\n{news_text}\n{stats_text}\n\n"
            f"請根據以下規則提供推薦：\n\n{recommendation_rules}\n"
            "請提供以下內容：\n\n"
            "1. **今日大盤趨勢**：分析整體市場走勢、主要驅動因素與市場情緒。\n\n"
            "2. **推薦買入個股**：最多 5 支，請依符合條件與整體表現排序，每支附上 1-5 星評分與一句話理由。\n\n"
            "3. **觀察名單**：如果有值得追蹤但尚未完全符合入選條件的個股，可簡要提出 1-2 支。\n\n"
            f"{section_four}"
            "5. **操作建議**：根據以上分析，提供具體的操作建議與風險提醒。\n\n"
            "請用專業但易懂的語言撰寫分析，並避免過度樂觀或悲觀的用詞。"
        )

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
            "max_tokens": 3000
        }

        response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
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
