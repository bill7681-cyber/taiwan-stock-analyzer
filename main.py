import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from fetcher import fetch_top_stocks_by_market_cap, fetch_latest_price, fetch_taiex_index
from analyzer import compute_technical_indicators
from ai_analysis import analyze_with_ai
from email_sender import send_email_notification
from report_generator import generate_html_report
from vercel_deploy import deploy_to_vercel, send_telegram_link


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

        # ── Gmail 通知 ──────────────────────────────
        # print("\n正在發送 Gmail 通知郵件...")
        # send_email_notification(
        #     results,
        #     analysis_text=analysis,
        #     recommendations=buy_candidates,
        # )

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
        )

        # ── 部署到 Vercel ────────────────────────────
        print("\n正在推送報告到 Vercel...")
        deployed = deploy_to_vercel(html)

        # ── Telegram 發送連結 ────────────────────────
        up_count = sum(1 for s in results if float(s.get("change_float", 0)) > 0)
        down_count = sum(1 for s in results if float(s.get("change_float", 0)) < 0)

        print("\n正在發送 Telegram 通知...")
        send_telegram_link(
            up_count=up_count,
            down_count=down_count,
            top3=results[:3],
        )

        if deployed:
            print("\n✅ 完成！報告已上傳至 Vercel。")
        else:
            print("\n⚠️ Vercel 部署失敗，請檢查 git 設定。")


if __name__ == "__main__":
    main()
