import os
import subprocess
import datetime
import requests


VERCEL_URL = "https://taiwan-stock-analyzer-sigma.vercel.app"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8920848566:AAFRjK2TX2ImV6-mZOLROyQSsQY3jT3inak")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8238969400")


def deploy_to_vercel(html_content: str) -> bool:
    """將 HTML 報告寫入 public/index.html 並 git push 觸發 Vercel 部署"""
    try:
        output_path = os.path.join(os.path.dirname(__file__), "public", "index.html")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✓ 報告已寫入 {output_path}")

        date_str = datetime.date.today().strftime("%Y-%m-%d")

        repo_dir = os.path.dirname(__file__)
        cmds = [
            ["git", "add", "public/index.html"],
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
