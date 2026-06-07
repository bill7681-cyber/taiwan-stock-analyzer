import json
import datetime
from pathlib import Path

import backtester

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

today = datetime.date.today()
dates = [(today - datetime.timedelta(days=d)).isoformat() for d in (1,3,5)]

history = [
    {"date": dates[0], "stocks": ["AAA", "BBB"]},
    {"date": dates[1], "stocks": ["AAA"]},
    {"date": dates[2], "stocks": ["BBB"]},
]
with open(DATA_DIR / "ai_recommendations_history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

signals = [
    {"date": dates[2], "stock": "AAA", "macd_golden": True, "kd_below_20": False},
    {"date": dates[1], "stock": "BBB", "macd_golden": False, "kd_below_20": True},
]
with open(DATA_DIR / "indicator_signals_history.json", "w", encoding="utf-8") as f:
    json.dump(signals, f, ensure_ascii=False, indent=2)

# Stub fetch_stock_history used by backtester

def fake_fetch(sid, days=30):
    # produce a sequence of dates from today-10 to today+10
    start = today - datetime.timedelta(days=10)
    hist = []
    for i in range(25):
        d = start + datetime.timedelta(days=i)
        base = 100.0 if sid == "AAA" else 50.0
        # AAA trends upward, BBB trends downward
        if sid == "AAA":
            price = base + (i - 10) * 1.0
        else:
            price = base - (i - 10) * 0.5
        hist.append({"date": d.isoformat(), "close": float(price)})
    return hist

# Monkey patch backtester to use fake data
backtester.fetch_stock_history = fake_fetch

res = backtester.verify_past_recommendations()
ind = backtester.verify_indicator_signals(5)

print(json.dumps({"ai_backtest": res, "indicator_backtest": ind}, ensure_ascii=False, indent=2))
