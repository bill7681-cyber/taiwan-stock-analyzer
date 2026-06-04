import os
import requests


def analyze_with_ai(results):
    """使用 OpenRouter API 的 Claude 模型分析台股數據"""
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_endpoint = "https://openrouter.ai/api/v1/chat/completions"

        if not api_key:
            print("❌ AI 分析失敗：缺少 OPENROUTER_API_KEY 環境變數，請檢查 .env 是否設定")
            return None

        top_gainers = results[:10]
        top_losers = results[-5:]

        gainers_text = "漲幅前10名：\n"
        for idx, stock in enumerate(top_gainers, 1):
            gainers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"

        losers_text = "跌幅前5名：\n"
        for idx, stock in enumerate(top_losers, 1):
            losers_text += f"{idx}. {stock['stock_id']} ({stock['stock_name']})：{stock['change']}（收盤價：{stock['close']}）\n"

        total_stocks = len(results)
        up_count = sum(1 for s in results if s["change_float"] > 0)
        down_count = sum(1 for s in results if s["change_float"] < 0)
        avg_change = sum(s["change_float"] for s in results) / total_stocks if total_stocks > 0 else 0

        stats_text = "統計數據：\n"
        stats_text += f"- 分析股票數：{total_stocks}\n"
        stats_text += f"- 上漲股票數：{up_count}（{up_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 下跌股票數：{down_count}（{down_count/total_stocks*100:.1f}%）\n"
        stats_text += f"- 平均漲幅：{avg_change:.2f}%\n"

        prompt = f"""請針對以下台股前150大股票的今日漲跌數據進行分析，並以繁體中文提供深入的市場分析。\n\n{gainers_text}\n{losers_text}\n{stats_text}\n請提供以下四點分析：\n\n1. **今日大盤趨勢**：分析整體市場走勢、上升或下跌的主要原因，以及市場情緒。\n\n2. **值得關注的強勢股**：從漲幅前10名的股票中，分析哪些股票具有持續上漲的潛力，以及背後的可能原因。\n\n3. **需要注意的弱勢股**：從跌幅前5名的股票中，分析這些股票下跌的原因，以及是否存在反彈機會。\n\n4. **明日操作建議**：基於今日分析，提供投資者明日可能的操作策略和需要關注的重點。\n\n請用專業但易懂的語言進行分析，並避免過度樂觀或悲觀的表述。"""

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
