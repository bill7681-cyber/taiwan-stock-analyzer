import fetcher

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


def compute_technical_indicators(history):
    """計算技術指標並判斷是否為買入訊號"""
    if not history:
        return {
            "ma5": None,
            "ma20": None,
            "kd_k": 0.0,
            "kd_d": 0.0,
            "buy_signal": False,
            "buy_reason": "",
        }

    latest = history[-1]
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
    buy_signal = golden_cross and above_5ma and volume_increase

    buy_reasons = []
    if buy_signal:
        buy_reasons.append(f"KD黃金交叉（K={current_kd['k']:.1f}、D={current_kd['d']:.1f}）")
        buy_reasons.append(
            f"股價站上5日均線且量增（今日量={last_volume:,}, 5日均量={avg_vol5:,.0f}）"
        )

    return {
        "ma5": ma5,
        "ma20": ma20,
        "kd_k": current_kd["k"],
        "kd_d": current_kd["d"],
        "buy_signal": buy_signal,
        "buy_reason": "；".join(buy_reasons) if buy_reasons else "",
    }


def analyze(history, stock_code=None, stock_name=None):
    """整合技術指標、法人籌碼與近期新聞"""
    analysis_result = compute_technical_indicators(history)
    institutional = {}
    news = []

    if stock_code:
        try:
            institutional = fetcher.fetch_institutional(stock_code)
        except Exception:
            institutional = {}

    if stock_code and stock_name:
        try:
            news = fetcher.fetch_news(stock_code, stock_name)
        except Exception:
            news = []

    analysis_result["institutional"] = institutional
    analysis_result["news"] = news
    return analysis_result
