import os
import sys
import time
import datetime
from pathlib import Path


class _Tee:
    """將 stdout 同時輸出到終端機與檔案。"""
    def __init__(self, stream, file_path):
        self._terminal = stream
        self._log = open(file_path, "a", encoding="utf-8", buffering=1)

    def write(self, data):
        self._terminal.write(data)
        self._log.write(data)

    def flush(self):
        self._terminal.flush()
        self._log.flush()

    def close(self):
        self._log.close()


def _setup_logging():
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.date.today().isoformat()}.txt"
    sys.stdout = _Tee(sys.stdout, log_file)
    print(f"[log] 輸出同步寫入：{log_file}")


_setup_logging()


try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from fetcher import fetch_top_stocks_by_market_cap, fetch_latest_price, fetch_taiex_index, fetch_institutional
from analyzer import compute_technical_indicators
from ai_analysis import analyze_with_ai
from email_sender import send_email_notification
from report_generator import generate_html_report
from vercel_deploy import deploy_to_vercel
from backtester import record_buy_signals, evaluate_buy_signal_accuracy


def _check_trading_day():
    """回傳 True 代表今天有交易資料，可繼續執行；False 代表跳過。
    第一層：週六(5)、週日(6) 直接跳過，不發任何 API 請求。
    第二層：呼叫 fetch_taiex_index，確認 TWSE 回傳的最新資料日期等於今天。
    若不一致（假日、收盤後尚未更新），同樣跳過。
    """
    today = datetime.date.today()

    # 第一層：週末直接跳過
    if today.weekday() >= 5:
        print(f"今日為{'週六' if today.weekday() == 5 else '週日'}（{today}），非交易日，跳過。")
        return False

    # 第二層：確認 TWSE 當天有實際資料
    try:
        taiex = fetch_taiex_index()
    except Exception as exc:
        print(f"⚠️ 無法取得加權指數資料（{exc}），繼續執行。")
        return True  # 無法確認時保守繼續

    if taiex is None:
        print(f"今日（{today}）TWSE 無加權指數資料，可能為假日，跳過。")
        return False

    taiex_date = str(taiex.get("date", ""))
    today_str = today.strftime("%Y%m%d")
    if taiex_date != today_str:
        print(f"今日非交易日或無新資料（TWSE 最新資料日期：{taiex_date}，今日：{today_str}），跳過報告產生。")
        return False

    return True


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


def main():
    if not _check_trading_day():
        sys.exit(0)

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
        stock_id = stock["id"]
        stock_name = stock["name"]
        print(f"[{idx}/{len(top_stocks)}] 抓取 {stock_id} ({stock_name})...", end=" ", flush=True)

        data = None
        for attempt in range(3):
            try:
                data = fetch_latest_price(stock_id)
                if data:
                    break
            except Exception as exc:
                if attempt < 2:
                    print(f"(重試 {attempt + 1})...", end=" ", flush=True)
                    time.sleep(2)
                else:
                    print(f"✗ (錯誤：{exc})")

        if data:
            try:
                indicators = compute_technical_indicators(data["history"])
                data.update(indicators)
                data["stock_name"] = stock_name
                data["institutional"] = fetch_institutional(stock_id)
                results.append(data)
                print("✓")
                success_count += 1
            except Exception as exc:
                print(f"✗ (處理錯誤：{exc})")
        else:
            print("✗ (無法取得資料)")

    print(f"\n成功抓取 {success_count}/{len(top_stocks)} 支股票的資料\n")

    results.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

    # 診斷：印出前3支股票的 institutional 欄位
    print("\n[診斷] 前3支股票的 institutional 欄位：")
    for item in results[:3]:
        print(f"  {item['stock_id']} ({item['stock_name']}): {item.get('institutional')}")

    print_stock_list(results)

    if results:
        print(f"漲幅前5名：")
        for idx, item in enumerate(results[:5], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")

        print(f"\n跌幅最深的5支：")
        for idx, item in enumerate(results[-5:], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")

        buy_candidates = [
            item for item in results
            if item.get("buy_signal") and float(item.get("change_pct") or 0) <= 5.0
        ]

        # ── 記錄今日技術買入訊號（供日後計算 3 天/5 天後報酬率）──
        try:
            record_buy_signals(datetime.date.today().isoformat(), buy_candidates)
        except Exception as exc:
            print(f"⚠️ 記錄買入訊號失敗：{exc}")

        # ── 計算歷史訊號準確率 ───────────────────────
        print("\n正在計算歷史訊號準確率...")
        try:
            signal_accuracy = evaluate_buy_signal_accuracy()
        except Exception as exc:
            print(f"⚠️ 計算歷史訊號準確率失敗：{exc}")
            signal_accuracy = None

        print("\n正在使用 AI 進行分析...")
        analysis = analyze_with_ai(results)
        if analysis:
            print("\n" + "="*80)
            print("📊 AI 分析結果")
            print("="*80)
            print(analysis)
            print("="*80 + "\n")
        else:
            analysis = None
            print("⚠️ 未能取得 AI 分析結果，仍繼續執行。")

        # ── 加權指數 ─────────────────────────────────
        print("\n正在取得加權指數...")
        try:
            taiex = fetch_taiex_index()
        except Exception as exc:
            print(f"⚠️ 取得加權指數失敗：{exc}")
            taiex = None

        # ── 生成 HTML 報告 ───────────────────────────
        print("\n正在生成 HTML 報告...")
        html = generate_html_report(
            results,
            analysis_text=analysis,
            recommendations=buy_candidates,
            taiex=taiex,
            signal_accuracy=signal_accuracy,
        )

        # ── 部署到 Vercel ────────────────────────────
        print("\n正在推送報告到 Vercel...")
        deployed = deploy_to_vercel(html)

        # ── Gmail 通知 ──────────────────────────────
        print("\n正在發送 Gmail 通知郵件...")
        send_email_notification(
            results,
            analysis_text=analysis,
            recommendations=buy_candidates,
            taiex=taiex,
        )

        if deployed:
            print("\n✅ 完成！報告已上傳至 Vercel。")
        else:
            print("\n⚠️ Vercel 部署失敗，請檢查 git 設定。")


if __name__ == "__main__":
    main()
