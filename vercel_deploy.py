import os
import re
import subprocess
import datetime
import requests


VERCEL_URL = "https://taiwan-stock-analyzer-sigma.vercel.app"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8920848566:AAFRjK2TX2ImV6-mZOLROyQSsQY3jT3inak")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8238969400")

REPORT_RETENTION_DAYS = 90


def _inject_version_meta(html_content):
    """在 HTML 的 <head> 加入版本號 meta tag（含部署時間戳記，例如
    <meta name="version" content="2026-06-07-1630">），讓每次部署的 HTML
    內容都不同，藉此強制 CDN 更新快取（不依賴 Vercel API / VERCEL_TOKEN）。"""
    version = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    meta_tag = f'<meta name="version" content="{version}">'

    if "<head>" in html_content:
        return html_content.replace("<head>", f"<head>\n  {meta_tag}", 1)
    return meta_tag + "\n" + html_content


def _cleanup_old_reports(archive_dir, retention_days=REPORT_RETENTION_DAYS):
    """刪除超過保留天數（預設 90 天）的歷史報告檔案"""
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)

    try:
        filenames = os.listdir(archive_dir)
    except OSError:
        return

    for name in filenames:
        match = re.match(r'^(\d{4}-\d{2}-\d{2})\.html$', name)
        if not match:
            continue
        try:
            file_date = datetime.datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue

        if file_date < cutoff:
            try:
                os.remove(os.path.join(archive_dir, name))
                print(f"🗑️ 已刪除過期歷史報告：{name}")
            except OSError as exc:
                print(f"⚠️ 刪除過期歷史報告失敗 {name}：{exc}")


def deploy_to_vercel(html_content: str) -> bool:
    """將 HTML 報告寫入 public/index.html 並 git push 觸發 Vercel 部署"""
    try:
        repo_dir = os.path.dirname(__file__)

        # 推送前先暫存未提交的修改、同步遠端最新狀態，再還原暫存
        # 流程：git stash -> git pull --rebase -> git stash pop
        stash_result = subprocess.run(
            ["git", "stash"], cwd=repo_dir,
            capture_output=True, text=True
        )
        stashed = "No local changes to save" not in (stash_result.stdout + stash_result.stderr)
        if stash_result.returncode != 0:
            print("✗ git stash 失敗，停止部署")
            print(stash_result.stderr)
            return False
        if stashed:
            print("✓ 已暫存工作目錄的未提交修改（git stash）")

        print("正在同步遠端最新狀態（git pull --rebase）...")
        sync_result = subprocess.run(
            ["git", "pull", "--rebase"], cwd=repo_dir,
            capture_output=True, text=True
        )
        if sync_result.returncode != 0:
            print("✗ git pull --rebase 失敗，停止部署")
            print(sync_result.stderr)
            if stashed:
                subprocess.run(["git", "stash", "pop"], cwd=repo_dir, capture_output=True, text=True)
                print("⚠️ 已還原暫存的修改（git stash pop）")
            return False

        if stashed:
            pop_result = subprocess.run(
                ["git", "stash", "pop"], cwd=repo_dir,
                capture_output=True, text=True
            )
            if pop_result.returncode != 0:
                print("✗ git stash pop 失敗（可能發生衝突），請手動執行 git stash list 處理")
                print(pop_result.stderr)
                return False
            print("✓ 已還原暫存的修改（git stash pop）")

        date_str = datetime.date.today().strftime("%Y-%m-%d")

        # 在 <head> 加入版本號 meta tag，讓每次部署的 HTML 內容都不同，
        # 強制 CDN 更新快取（搭配 vercel.json 的 Cache-Control no-store）
        html_content = _inject_version_meta(html_content)

        output_path = os.path.join(repo_dir, "public", "index.html")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✓ 報告已寫入 {output_path}")

        # 同時寫入歷史存檔 public/reports/YYYY-MM-DD.html，並清理過期報告
        archive_dir = os.path.join(repo_dir, "public", "reports")
        os.makedirs(archive_dir, exist_ok=True)

        archive_path = os.path.join(archive_dir, f"{date_str}.html")
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✓ 歷史報告已存檔至 {archive_path}")

        _cleanup_old_reports(archive_dir)

        cmds = [
            ["git", "add", "public/index.html"],
            ["git", "add", "-A", "public/reports"],
            ["git", "commit", "-m", f"report: {date_str}"],
        ]
        for cmd in cmds:
            result = subprocess.run(
                cmd, cwd=repo_dir,
                capture_output=True, text=True
            )
            if result.returncode != 0:
                # commit 時若無變更不算錯誤
                if "nothing to commit" in result.stdout + result.stderr:
                    print("⚠️ git: 無新變更，略過 commit")
                    break
                print(f"✗ git 指令失敗：{' '.join(cmd)}")
                print(result.stderr)
                return False

        push_result = subprocess.run(
            ["git", "push"], cwd=repo_dir,
            capture_output=True, text=True
        )
        if push_result.returncode != 0:
            print("⚠️ git push 失敗，嘗試 git pull --rebase 後重試...")
            print(push_result.stderr)

            pull_result = subprocess.run(
                ["git", "pull", "--rebase"], cwd=repo_dir,
                capture_output=True, text=True
            )
            if pull_result.returncode != 0:
                print("✗ git pull --rebase 失敗")
                print(pull_result.stderr)
                return False

            push_result = subprocess.run(
                ["git", "push"], cwd=repo_dir,
                capture_output=True, text=True
            )
            if push_result.returncode != 0:
                print("✗ git push 重試後仍失敗")
                print(push_result.stderr)
                return False

        print(f"✓ 已推送至 GitHub，Vercel 自動部署中...")
        return True

    except Exception as e:
        print(f"✗ deploy_to_vercel 錯誤：{e}")
        return False


def send_telegram_link(up_count: int, down_count: int, top3: list) -> bool:
    """發送 Vercel 連結到 Telegram"""
    try:
        date_str = datetime.date.today().strftime("%Y/%m/%d")

        top3_text = ""
        for i, s in enumerate(top3[:3], 1):
            top3_text += f"  {i}. {s['stock_id']} {s.get('stock_name','')} {s.get('change','')}\n"

        message = (
            f"📊 *台股每日分析報告*\n"
            f"📅 {date_str}\n\n"
            f"市場概況：⬆️ {up_count} 支 ｜ ⬇️ {down_count} 支\n\n"
            f"🚀 漲幅前三名：\n{top3_text}\n"
            f"🔗 [點此查看完整報告]({VERCEL_URL})"
        )

        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )

        if resp.status_code == 200:
            print(f"✓ Telegram 連結已發送")
            return True
        else:
            print(f"✗ Telegram 發送失敗：{resp.text}")
            return False

    except Exception as e:
        print(f"✗ send_telegram_link 錯誤：{e}")
        return False
