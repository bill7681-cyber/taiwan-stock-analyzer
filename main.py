import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from fetcher import fetch_top_stocks_by_market_cap, fetch_latest_price
from analyzer import compute_technical_indicators
from ai_analysis import analyze_with_ai
from email_sender import send_email_notification


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
                indicators = compute_technical_indicators(data["history"])
                data.update(indicators)
                data["stock_name"] = stock_name
                results.append(data)
                print("✓")
                success_count += 1
            else:
                print("✗ (無法取得資料)")
        except Exception as exc:
            print(f"✗ (錯誤：{exc})")

    print(f"\n成功抓取 {success_count}/{len(top_stocks)} 支股票的資料\n")

    results.sort(key=lambda x: x["change_float"], reverse=True)
    print_stock_list(results)

    if results:
        print(f"漲幅前5名：")
        for idx, item in enumerate(results[:5], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")

        print(f"\n跌幅最深的5支：")
        for idx, item in enumerate(results[-5:], 1):
            print(f"  {idx}. {item['stock_id']} ({item['stock_name']})：{item['change']}")

        buy_candidates = [item for item in results if item.get("buy_signal")]

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

        print("\n正在發送 Gmail 通知郵件...")
        send_email_notification(
            results,
            analysis_text=analysis,
            recommendations=buy_candidates,
        )


if __name__ == "__main__":
    main()
