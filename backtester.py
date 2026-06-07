import os
import json
import datetime
from pathlib import Path

from fetcher import fetch_stock_history


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _history_path():
    return DATA_DIR / "ai_recommendations_history.json"


def save_recommendation(date, stocks):
    """儲存 AI 當日推薦清單（date: ISO YYYY-MM-DD, stocks: list of stock ids）"""
    path = _history_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
    else:
        data = []

    entry = {
        "date": str(date),
        "stocks": list(stocks),
    }
    data.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def verify_past_recommendations(days_ago_list=None):
    """讀取歷史推薦，計算從推薦日到今日的報酬情況。
    回傳格式：{days: {total, wins, rate, details:[...]}}
    """
    if days_ago_list is None:
        days_ago_list = [1, 3, 5]

    path = _history_path()
    if not path.exists():
        return {d: {"total": 0, "wins": 0, "rate": None, "note": "累積中，需要更多資料"} for d in days_ago_list}

    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []

    today = datetime.date.today()
    results = {}
    for d in days_ago_list:
        total = 0
        wins = 0
        details = []
        target_date = (today - datetime.timedelta(days=d)).isoformat()

        # find entries with date == target_date
        entries = [e for e in history if e.get("date") == target_date]
        for entry in entries:
            for sid in entry.get("stocks", []):
                total += 1
                try:
                    # fetch recent history that includes target_date and today
                    hist = fetch_stock_history(sid, days=d + 10)
                    # hist date format should be ISO-like or TWSE format; try to match by suffix
                    idx = next((i for i, it in enumerate(hist) if it.get("date") and it.get("date").endswith(target_date[-5:])), None)
                    if idx is None:
                        # fallback: find first date that contains target_date
                        idx = next((i for i, it in enumerate(hist) if it.get("date") and target_date in it.get("date")), None)
                    if idx is None:
                        details.append({"stock": sid, "result": "no_data"})
                        continue

                    # look for future index after d trading days
                    future_idx = idx + d
                    if future_idx < len(hist):
                        close_then = hist[idx]["close"]
                        close_now = hist[future_idx]["close"]
                        success = close_now > close_then
                        if success:
                            wins += 1
                        details.append({"stock": sid, "from": close_then, "to": close_now, "win": success})
                    else:
                        details.append({"stock": sid, "result": "no_future_data"})
                except Exception:
                    details.append({"stock": sid, "result": "error"})

        rate = (wins / total * 100) if total > 0 else None
        results[d] = {"total": total, "wins": wins, "rate": rate, "details": details}

    # If overall data small, include a note
    overall_total = sum(results[d]["total"] for d in days_ago_list)
    if overall_total == 0:
        for d in days_ago_list:
            results[d]["note"] = "累積中，需要更多資料"

    return results


def verify_indicator_signals(days_ago=5):
    """讀取 data/indicator_signals_history.json，計算 days_ago 後上漲比例。
    檔案格式假設：[{"date":"YYYY-MM-DD","stock":"2330","macd_golden":True,"kd_below_20":False}]
    如無檔案則回傳累積中訊息。
    """
    path = DATA_DIR / "indicator_signals_history.json"
    if not path.exists():
        return {"note": "累積中，需要更多資料"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        return {"note": "讀取檔案失敗"}

    total_macd = 0
    wins_macd = 0
    total_kd = 0
    wins_kd = 0

    for rec in records:
        sid = rec.get("stock")
        rec_date = rec.get("date")
        if not sid or not rec_date:
            continue
        try:
            hist = fetch_stock_history(sid, days=days_ago + 10)
            idx = next((i for i, it in enumerate(hist) if it.get("date") and rec_date in it.get("date")), None)
            if idx is None:
                continue
            future_idx = idx + days_ago
            if future_idx >= len(hist):
                continue
            from_price = hist[idx]["close"]
            to_price = hist[future_idx]["close"]
            up = to_price > from_price

            if rec.get("macd_golden"):
                total_macd += 1
                if up:
                    wins_macd += 1
            if rec.get("kd_below_20"):
                total_kd += 1
                if up:
                    wins_kd += 1
        except Exception:
            continue

    res = {
        "days_ago": days_ago,
        "macd": {"total": total_macd, "wins": wins_macd, "rate": (wins_macd / total_macd * 100) if total_macd else None},
        "kd": {"total": total_kd, "wins": wins_kd, "rate": (wins_kd / total_kd * 100) if total_kd else None},
    }

    if res["macd"]["total"] == 0 and res["kd"]["total"] == 0:
        return {"note": "累積中，需要更多資料"}

    return res
