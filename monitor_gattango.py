import os
import re
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# ================= 設定項目 =================
TARGET_URL = "https://rail-mtb.resv.jp/reserve/calendar.php?direct_id=8"
TARGET_DATES = ["11/12", "11/13"]  # 監視したい日付

# GitHub Secrets（環境変数）から通知設定を取得
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
# ============================================


def send_notification(available_slots: list[str]):
    """空きが見つかった際に通知を送信する"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slot_text = "\n".join([f"・{slot}" for slot in available_slots])
    message = (
        f"🚲 【Gattan Go!! 渓谷コース】空き枠が出ました！\n"
        f"検知時刻: {now_str}\n\n"
        f"【空き枠詳細】\n{slot_text}\n\n"
        f"▼ 今すぐ予約ページへ\n{TARGET_URL}"
    )
    print("\n" + "=" * 50)
    print(message)
    print("=" * 50 + "\n")

    # 1. Discord通知
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
            print("[INFO] Discordへ通知を送信しました。")
        except Exception as e:
            print(f"[ERROR] Discord通知エラー: {e}")

    # 2. メール通知 (Gmail)
    if GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
        try:
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = "【空席通知】Gattan Go!! 11/12・13に空きが出ました！"
            msg["From"] = GMAIL_ADDRESS
            msg["To"] = GMAIL_ADDRESS

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                server.send_message(msg)
            print("[INFO] メール通知を送信しました。")
        except Exception as e:
            print(f"[ERROR] メール送信エラー: {e}")


def check_availability() -> list[str]:
    """Playwrightでカレンダーを開き、対象日の空き枠リストを返す"""
    found_slots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state("networkidle")

            for _ in range(4):
                body_text = page.inner_text("body")

                if any(d in body_text for d in TARGET_DATES):
                    links = page.locator("a, td, div").all_inner_texts()
                    for text in links:
                        clean_text = " ".join(text.split())
                        for target_date in TARGET_DATES:
                            if target_date in clean_text and len(clean_text) < 40:
                                if re.search(r"(残\s*\d+|○|◯|△)", clean_text):
                                    if clean_text not in found_slots:
                                        found_slots.append(clean_text)

                if all(d in body_text for d in TARGET_DATES):
                    break

                next_btn = page.locator(
                    "a:has-text('次の週'), a:has-text('次へ'), a:has-text('＞'), a:has-text('>'), input[value*='次']"
                ).first
                if next_btn.count() > 0 and next_btn.is_visible():
                    next_btn.click()
                    page.wait_for_timeout(1500)
                else:
                    break

        except Exception as e:
            print(f"[ERROR] スクレイピング中にエラーが発生しました: {e}")
        finally:
            browser.close()

    return found_slots


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 空き状況を確認中...")

    available = check_availability()

    if available:
        send_notification(available)
    else:
        print(f"[{now_str}] 11/12・13の空き枠はありませんでした。")


if __name__ == "__main__":
    main()
