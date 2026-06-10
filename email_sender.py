import datetime
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

VERCEL_URL = "https://taiwan-stock-analyzer-sigma.vercel.app"

RECEIVER_EMAILS = [
    "bill7681@gmail.com",
    "wilsonche92@gmail.com",
    "st875052007@gmail.com",
    "peitzu498500@gmail.com",
]


def _ai_one_liner(analysis_text: str) -> str:
    """取 AI 分析的第一段有意義文字（非標題、非空行）。"""
    if not analysis_text:
        return ""
    for line in analysis_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) > 10:
            # 移除 markdown 粗體符號
            stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
            return stripped[:120]
    return ""


def _change_color(change_pct):
    """漲跌顏色：台股慣例漲紅跌綠。"""
    try:
        val = float(change_pct)
    except (TypeError, ValueError):
        return "#333333"
    return "#d32f2f" if val > 0 else ("#2e7d32" if val < 0 else "#333333")


def _format_change(item):
    """回傳如 '+3.25%' 的字串。"""
    return item.get("change", "")


def generate_summary_html(results, analysis_text=None, recommendations=None, taiex=None):
    today_str = datetime.date.today().strftime("%Y/%m/%d")

    # 加權指數
    if taiex:
        chg_sign = "+" if taiex.get("change_pct", 0) >= 0 else ""
        taiex_line = (
            f"{taiex['points']:,.2f} 點　"
            f"<span style='color:{_change_color(taiex['change_pct'])};font-weight:bold;'>"
            f"{chg_sign}{taiex['change_pct']:.2f}%　({chg_sign}{taiex['change']:.2f})</span>"
        )
    else:
        taiex_line = "—"

    # 上漲/下跌支數
    up_count   = sum(1 for s in results if float(s.get("change_float", 0)) > 0)
    down_count = sum(1 for s in results if float(s.get("change_float", 0)) < 0)

    # 漲幅前3
    gainers = results[:3]
    gainer_rows = ""
    for item in gainers:
        color = _change_color(item.get("change_pct", 0))
        gainer_rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;'>"
            f"<b>{item['stock_id']}</b> {item['stock_name']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right;"
            f"color:{color};font-weight:bold;'>{_format_change(item)}</td>"
            f"</tr>"
        )

    # 跌幅前3（最後3支，已依 change_pct 降冪排列）
    losers = list(reversed(results[-3:]))
    loser_rows = ""
    for item in losers:
        color = _change_color(item.get("change_pct", 0))
        loser_rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;'>"
            f"<b>{item['stock_id']}</b> {item['stock_name']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right;"
            f"color:{color};font-weight:bold;'>{_format_change(item)}</td>"
            f"</tr>"
        )

    # 技術買入訊號
    if recommendations:
        signal_items = "".join(
            f"<li style='margin:4px 0;'><b>{r['stock_id']}</b> {r['stock_name']}</li>"
            for r in recommendations[:5]
        )
        signal_section = f"<ul style='margin:6px 0 0 0;padding-left:18px;'>{signal_items}</ul>"
    else:
        signal_section = "<p style='color:#888;margin:6px 0 0 0;'>今日無技術買入訊號</p>"

    # AI 摘要
    ai_summary = _ai_one_liner(analysis_text)
    ai_section = (
        f"<p style='margin:6px 0 0 0;color:#444;line-height:1.6;'>{ai_summary}</p>"
        if ai_summary else
        "<p style='color:#888;margin:6px 0 0 0;'>—</p>"
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:16px;background:#f5f5f5;font-family:'微軟正黑體',Arial,sans-serif;font-size:15px;color:#333;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;padding:20px 18px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <h2 style="margin:0 0 4px 0;font-size:18px;color:#1565c0;">📈 台股每日摘要</h2>
  <p style="margin:0 0 16px 0;color:#888;font-size:13px;">{today_str}</p>

  <div style="background:#f0f4ff;border-radius:8px;padding:12px 14px;margin-bottom:14px;">
    <div style="font-size:13px;color:#555;margin-bottom:4px;">加權指數</div>
    <div style="font-size:16px;">{taiex_line}</div>
    <div style="margin-top:8px;font-size:14px;">
      上漲 <span style="color:#d32f2f;font-weight:bold;">{up_count}</span> 支
      下跌 <span style="color:#2e7d32;font-weight:bold;">{down_count}</span> 支
    </div>
  </div>

  <table style="width:100%;border-collapse:collapse;margin-bottom:14px;">
    <tr><th colspan="2" style="text-align:left;padding:8px 10px;background:#fce4e4;color:#b71c1c;border-radius:6px 6px 0 0;font-size:14px;">🚀 漲幅前3名</th></tr>
    {gainer_rows}
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:14px;">
    <tr><th colspan="2" style="text-align:left;padding:8px 10px;background:#e8f5e9;color:#1b5e20;border-radius:6px 6px 0 0;font-size:14px;">📉 跌幅前3名</th></tr>
    {loser_rows}
  </table>

  <div style="margin-bottom:14px;">
    <div style="font-weight:bold;color:#1565c0;margin-bottom:4px;font-size:14px;">⚡ 技術買入訊號</div>
    {signal_section}
  </div>

  <div style="margin-bottom:18px;">
    <div style="font-weight:bold;color:#1565c0;margin-bottom:4px;font-size:14px;">🤖 AI 分析摘要</div>
    {ai_section}
  </div>

  <a href="{VERCEL_URL}" style="display:block;text-align:center;background:#1565c0;color:#fff;text-decoration:none;padding:12px;border-radius:8px;font-size:15px;font-weight:bold;">
    查看完整報告 →
  </a>

  <p style="text-align:center;color:#bbb;font-size:11px;margin-top:14px;">此為自動生成摘要，僅供參考</p>
</div>
</body>
</html>"""
    return html


def send_email_notification(results, analysis_text=None, recommendations=None, taiex=None,
                            ai_backtest=None, indicator_backtest=None):
    """發送 Gmail 簡短摘要郵件，適合手機閱讀。"""
    try:
        sender_email = os.getenv("GMAIL_SENDER_EMAIL")
        app_password = os.getenv("GMAIL_APP_PASSWORD")

        if not sender_email or not app_password:
            print("Email failed: missing GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD in .env")
            return False

        html_content = generate_summary_html(
            results,
            analysis_text=analysis_text,
            recommendations=recommendations,
            taiex=taiex,
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[台股摘要] {datetime.date.today().strftime('%Y-%m-%d')}"
        msg["From"]    = sender_email
        msg["To"]      = ", ".join(RECEIVER_EMAILS)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, RECEIVER_EMAILS, msg.as_string())

        print(f"Email sent OK ({len(html_content.encode('utf-8')) / 1024:.1f} KB)")
        return True

    except smtplib.SMTPAuthenticationError:
        print("Email failed: Gmail auth error — check app password")
        return False
    except smtplib.SMTPException as e:
        print(f"Email failed (SMTP): {e}")
        return False
    except Exception as e:
        print(f"Email failed: {e}")
        return False
