import asyncio
import datetime
import io
import os

from telegram import Bot
from telegram.error import TelegramError

from chart_generator import (
    generate_change_bar_chart,
    generate_market_breadth_pie,
    generate_institutional_bar_chart,
)


TELEGRAM_MAX_LEN = 4096


def _split_text(text, max_len=TELEGRAM_MAX_LEN):
    """將長文字依長度上限切割，盡量沿著換行處切分，避免訊息被截斷在句子中間。"""
    text = text.strip()
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _format_full_analysis_messages(analysis_text):
    """組合完整 AI 分析內容（大盤趨勢、推薦個股、觀察名單、法人籌碼與新聞、操作建議），
    並依 Telegram 4096 字上限自動切割成多則訊息。"""
    header = "🤖 AI 完整分析報告\n" + "－" * 12
    body = f"{header}\n\n{analysis_text.strip()}"

    chunks = _split_text(body)
    if len(chunks) == 1:
        return chunks

    return [f"{chunk}\n\n（{idx}/{len(chunks)}）" for idx, chunk in enumerate(chunks, 1)]


def _format_summary(results, analysis_text=None, ai_backtest=None, indicator_backtest=None):
    today = datetime.date.today().strftime("%Y/%m/%d")

    total = len(results)
    up   = sum(1 for s in results if s.get("change_float", 0) > 0)
    down = sum(1 for s in results if s.get("change_float", 0) < 0)
    flat = total - up - down
    avg  = sum(s.get("change_pct", 0) for s in results) / total if total else 0

    gainers = sorted(
        [s for s in results if s.get("change_float", 0) > 0],
        key=lambda x: x.get("change_pct", 0), reverse=True
    )[:3]
    losers = sorted(
        [s for s in results if s.get("change_float", 0) < 0],
        key=lambda x: x.get("change_pct", 0)
    )[:3]

    lines = [
        f"📈 台股每日分析報告  {today}",
        "",
        "📊 大盤概況",
        f"上漲 {up} 支  下跌 {down} 支  平盤 {flat} 支",
        f"平均漲跌：{avg:+.2f}%",
        "",
        "🚀 漲幅前3名",
    ]
    for s in gainers:
        lines.append(f"  {s['stock_id']} {s['stock_name']}  {s['change']}")

    lines += ["", "📉 跌幅前3名"]
    for s in losers:
        lines.append(f"  {s['stock_id']} {s['stock_name']}  {s['change']}")

    # AI 一句話摘要（取第一行有意義的文字）
    if analysis_text:
        lines += ["", "🤖 AI 建議"]
        for line in analysis_text.replace("\r", "").split("\n"):
            cleaned = line.strip().lstrip("#").strip()
            if cleaned and not cleaned.startswith("-") and len(cleaned) > 10:
                lines.append(cleaned[:120])
                break

    # 回測準確率
    backtest_lines = []
    if ai_backtest:
        for days, stats in ai_backtest.items():
            if not stats.get("note") and stats.get("rate") is not None:
                backtest_lines.append(
                    f"  AI {days}日：{stats['rate']:.1f}%（{stats['wins']}/{stats['total']}）"
                )
    if indicator_backtest and not indicator_backtest.get("note"):
        macd = indicator_backtest.get("macd", {})
        kd   = indicator_backtest.get("kd", {})
        days_ago = indicator_backtest.get("days_ago", "?")
        if macd.get("rate") is not None:
            backtest_lines.append(
                f"  MACD {days_ago}日：{macd['rate']:.1f}%（{macd['wins']}/{macd['total']}）"
            )
        if kd.get("rate") is not None:
            backtest_lines.append(
                f"  KD {days_ago}日：{kd['rate']:.1f}%（{kd['wins']}/{kd['total']}）"
            )
    if backtest_lines:
        lines += ["", "📐 回測準確率"] + backtest_lines

    return "\n".join(lines)


async def _send_all(token, chat_id, results, analysis_text, ai_backtest, indicator_backtest):
    bot = Bot(token=token)

    # 第一則：文字摘要
    text = _format_summary(results, analysis_text, ai_backtest, indicator_backtest)
    await bot.send_message(chat_id=chat_id, text=text)

    # 接著：完整 AI 分析內容（大盤趨勢、推薦個股、觀察名單、法人籌碼與新聞、操作建議），
    # 超過 4096 字自動分成多則發送
    if analysis_text:
        for chunk in _format_full_analysis_messages(analysis_text):
            await bot.send_message(chat_id=chat_id, text=chunk)

    # 接著：三張圖表（各自發送）
    all_sorted = sorted(results, key=lambda x: x.get("change_pct", 0), reverse=True)
    charts = [
        (generate_change_bar_chart(all_sorted),             "漲跌幅排行圖"),
        (generate_market_breadth_pie(all_sorted),           "大盤多空比例圖"),
        (generate_institutional_bar_chart(all_sorted[:10]), "法人買賣超圖"),
    ]
    for img_bytes, caption in charts:
        if img_bytes:
            await bot.send_photo(
                chat_id=chat_id,
                photo=io.BytesIO(img_bytes),
                caption=caption,
            )


def send_telegram_notification(results, analysis_text=None, ai_backtest=None,
                                indicator_backtest=None):
    """發送 Telegram 文字摘要 + 三張圖表，可同時發送給多個 chat_id。
    優先讀取 TELEGRAM_CHAT_IDS（逗號分隔），不存在則 fallback 到單一的 TELEGRAM_CHAT_ID。
    回傳 True 表示至少有一個 chat_id 發送成功。"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    raw_chat_ids = os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID", "")
    chat_ids = [c.strip() for c in raw_chat_ids.split(",") if c.strip()]

    if not token or not chat_ids:
        print("Telegram skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_IDS/TELEGRAM_CHAT_ID in .env")
        return False

    success_count = 0
    for chat_id in chat_ids:
        try:
            asyncio.run(_send_all(token, chat_id, results, analysis_text, ai_backtest, indicator_backtest))
            print(f"Telegram sent OK to chat_id={chat_id}.")
            success_count += 1
        except TelegramError as e:
            print(f"Telegram failed (API) for chat_id={chat_id}: {e}")
        except Exception as e:
            print(f"Telegram failed for chat_id={chat_id}: {e}")

    return success_count > 0
