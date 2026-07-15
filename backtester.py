import os
import json
import datetime
from pathlib import Path

from fetcher import fetch_stock_history


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _history_path():
    return DATA_DIR / "ai_recommendations_history.json"


def _buy_signal_history_path():
    return DATA_DIR / "buy_signal_history.json"


def record_buy_signals(date, stocks):
    """記錄當日觸發技術買入訊號的個股，及推薦當下的收盤價，供日後計算報酬率。
    stocks: list of dict，至少需包含 stock_id（或 id）、close，可選 stock_name。
    若同一天已有紀錄則覆蓋，避免重複累積。"""
    path = _buy_signal_history_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
    else:
        data = []

    date_str = str(date)
    data = [e for e in data if e.get("date") != date_str]

    entry_stocks = []
    for s in stocks:
        stock_id = s.get("stock_id") or s.get("id")
        if not stock_id:
            continue
        try:
            close = float(str(s.get("close", "")).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if close <= 0:
            continue
        entry_stocks.append({
            "stock_id": stock_id,
            "stock_name": s.get("stock_name", ""),
            "close": close,
        })

    if not entry_stocks:
        return

    data.append({"date": date_str, "stocks": entry_stocks})

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _twse_date_to_iso(date_str):
    """將 TWSE 民國年日期 '115/06/07' 轉換成 ISO '2026-06-07'。
    若已是 ISO 格式（含 '-'）則原樣返回。"""
    s = str(date_str).strip()
    parts = s.split('/')
    if len(parts) == 3:
        try:
            return f"{int(parts[0]) + 1911}-{parts[1]}-{parts[2]}"
        except ValueError:
            pass
    return s


def evaluate_buy_signal_accuracy(horizons=None):
    """讀取歷史買入訊號紀錄，計算推薦後 N 個交易日的報酬率與勝率。

    修正：
    - 將 TWSE 民國年日期轉成 ISO 後再比對，避免格式不符導致永遠找不到
    - 評估所有歷史訊號（不限定「剛好 h 曆日前」），有查到未來收盤價才計入
    - total 只計入成功查到兩端價格的筆數，避免分母虛高
    """
    if horizons is None:
        horizons = [3, 5]

    path = _buy_signal_history_path()
    if not path.exists():
        return {h: {"total": 0, "wins": 0, "win_rate": None, "avg_return": None,
                     "note": "累積中，需要更多資料"} for h in horizons}

    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []

    today = datetime.date.today()
    acc = {h: {"total": 0, "wins": 0, "return_sum": 0.0, "details": []} for h in horizons}

    for entry in history:
        signal_date_iso = entry.get("date")
        if not signal_date_iso:
            continue
        try:
            signal_dt = datetime.date.fromisoformat(signal_date_iso)
        except ValueError:
            continue
        if signal_dt >= today:
            continue

        for s in entry.get("stocks", []):
            sid = s.get("stock_id")
            close_then = s.get("close")
            if not sid or not close_then:
                continue

            fetch_days = max(horizons) + 20
            try:
                hist = fetch_stock_history(sid, days=fetch_days)
            except Exception:
                continue

            if not hist:
                continue

            # 找到訊號日在歷史中的索引（比對時先把 TWSE 民國年轉成 ISO）
            signal_idx = None
            for i, row in enumerate(hist):
                if _twse_date_to_iso(row.get("date", "")) == signal_date_iso:
                    signal_idx = i
                    break

            # 若訊號日不是交易日（如週末），往前找最近的交易日
            if signal_idx is None:
                for i in range(len(hist) - 1, -1, -1):
                    if _twse_date_to_iso(hist[i].get("date", "")) <= signal_date_iso:
                        signal_idx = i
                        break

            if signal_idx is None:
                continue

            for h in horizons:
                future_idx = signal_idx + h
                if future_idx >= len(hist):
                    acc[h]["details"].append({"stock": sid, "result": "no_future_data"})
                    continue

                close_now = hist[future_idx]["close"]
                return_pct = (close_now - close_then) / close_then * 100
                win = return_pct > 0

                acc[h]["total"] += 1
                if win:
                    acc[h]["wins"] += 1
                acc[h]["return_sum"] += return_pct
                acc[h]["details"].append({
                    "stock": sid,
                    "stock_name": s.get("stock_name", ""),
                    "signal_date": signal_date_iso,
                    "from": close_then,
                    "to": close_now,
                    "return_pct": round(return_pct, 2),
                    "win": win,
                })

    final = {}
    for h in horizons:
        total = acc[h]["total"]
        wins = acc[h]["wins"]
        return_sum = acc[h]["return_sum"]
        final[h] = {
            "total": total,
            "wins": wins,
            "win_rate": (wins / total * 100) if total > 0 else None,
            "avg_return": (return_sum / total) if total > 0 else None,
            "details": acc[h]["details"],
        }
        if total == 0:
            final[h]["note"] = "累積中，需要更多資料"

    return final


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
