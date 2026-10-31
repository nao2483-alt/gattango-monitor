import os
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# ================= 設定項目 =================
TARGET_URL = "https://rail-mtb.resv.jp/reserve/calendar.php?direct_id=8"
TARGET_DATES = ["11/12", "11/13", "11/5"]  # テスト用に 11/5 を含めています

# GitHub SecretsからLINEのトークンを取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
# ============================================


def send_line_notification(available_slots: list[str]):
    """空きが見つかった際にLINEへ通知を送信する"""
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

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[WARN] LINE_CHANNEL_ACCESS_TOKEN が設定されていません。GitHubのSecretsを確認してください。")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print("[INFO] LINEへ通知を正常に送信しました！")
        else:
            print(f"[ERROR] LINE通知エラー: ステータス {res.status_code} / 内容: {res.text}")
    except Exception as e:
        print(f"[ERROR] LINE通信エラー: {e}")


def extract_slots_from_page(page, target_dates: list[str]) -> tuple[list[str], list[str], list[str]]:
    """画面内のカレンダー表から、対象日付の列にある空き枠を抽出する"""
    result = page.evaluate(
        """(targetDates) => {
        const debugHeaders = [];
        const found = [];
        const matchedDates = [];

        const targets = targetDates.map(str => {
            const parts = str.split('/');
            const m = parseInt(parts[0], 10);
            const d = parseInt(parts[1], 10);
            return {
                raw: str,
                m: m,
                d: d,
                ymd1: `2026-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
                ymd2: `2026${String(m).padStart(2, '0')}${String(d).padStart(2, '0')}`
            };
        });

        const bodyText = document.body.innerText || "";
        const hasMonth11 = bodyText.includes("11月") || bodyText.includes("2026/11") || bodyText.includes("2026年11月") || bodyText.includes("11/");

        // 1. カレンダーの日付見出しセル（th, td等）を探す
        const candidates = Array.from(document.querySelectorAll("th, td, div"));
        const matchedColumns = [];

        for (const el of candidates) {
            const text = (el.innerText || "").trim().replace(/\\s+/g, " ");
            if (!text || text.length > 25) continue;

            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;

            if (/(?:\\d{1,2}[\\/月]\\d{1,2}|^\\d{1,2}(?:日)?\\s*[\\(（]?[月火水木金土日][\\)）]?$)/.test(text)) {
                if (!debugHeaders.includes(text)) debugHeaders.push(text);
            }

            for (const t of targets) {
                // "11/5", "11/05", "11月5日" または11月表示中の "5(木)", "5日(木)" などにマッチ
                const regexFull = new RegExp(`(?:^|\\D)0?${t.m}[\\/月]0?${t.d}(?:日|\\D|$)`);
                const regexDayOnly = new RegExp(`^0?${t.d}(?:日)?\\s*[\\(（][月火水木金土日][\\)）]`);

                if (regexFull.test(text) || (hasMonth11 && regexDayOnly.test(text))) {
                    matchedColumns.push({
                        target: t,
                        headerText: text,
                        left: rect.left,
                        right: rect.right,
                        top: rect.top,
                        bottom: rect.bottom
                    });
                    if (!matchedDates.includes(t.raw)) {
                        matchedDates.push(t.raw);
                    }
                }
            }
        }

        // 2. 日付見出しと同じ列（真下）にあるセルから空き枠を探す
        const cells = Array.from(document.querySelectorAll("td, a"));
        for (const col of matchedColumns) {
            for (const cell of cells) {
                const rect = cell.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                const centerX = (rect.left + rect.right) / 2;
                // 見出しより下にあり、横位置がその日付の列に収まっているセル
                if (rect.top >= col.bottom - 5 && centerX >= col.left - 5 && centerX <= col.right + 5) {
                    const cellText = (cell.innerText || "").trim().replace(/\\s+/g, " ");
                    if (!cellText || cellText.length > 35) continue;

                    // 満席（×や－など）は除外
                    if (/^[×✕xX－\\-休満問]+$/.test(cellText) || cellText.includes("満席") || cellText.includes("終了")) {
                        continue;
                    }

                    const hasLink = cell.tagName.toLowerCase() === "a" || cell.querySelector("a") !== null;
                    const hasAvailMark = /(残\\s*\\d+|○|◯|△|空|予約)/.test(cellText);

                    if (hasAvailMark || (hasLink && /[0-9○◯△残]/.test(cellText))) {
                        let timeStr = "";
                        const row = cell.closest("tr");
                        if (row && row.cells && row.cells.length > 0) {
                            const firstCellText = (row.cells[0].innerText || "").trim().replace(/\\s+/g, " ");
                            if (firstCellText && firstCellText !== cellText && firstCellText.length < 25) {
                                timeStr = firstCellText;
                            }
                        }
                        const slotDesc = `${col.target.raw} ${timeStr} (${cellText})`.replace(/\\s+/g, " ").trim();
                        if (!found.includes(slotDesc)) {
                            found.push(slotDesc);
                        }
                    }
                }
            }
        }

        // 3. リンクのURLやonclick属性に日付(20261105や2026-11-05)が直接入っている場合の予備検出
        const links = Array.from(document.querySelectorAll("a, [onclick]"));
        for (const link of links) {
            const attrText = (link.getAttribute("href") || "") + " " + (link.getAttribute("onclick") || "") + " " + (link.innerText || "");
            for (const t of targets) {
                if (attrText.includes(t.ymd1) || attrText.includes(t.ymd2)) {
                    const clean = (link.innerText || "").trim().replace(/\\s+/g, " ");
                    if (clean && !/^[×✕xX－\\-]+$/.test(clean) && clean.length < 35) {
                        const slotDesc = `${t.raw} (${clean})`;
                        if (!found.includes(slotDesc)) {
                            found.push(slotDesc);
                        }
                    }
                }
            }
        }

        return {
            debugHeaders: debugHeaders,
            found: found,
            matchedDates: matchedDates
        };
    }""",
        target_dates,
    )
    return result["found"], result["debugHeaders"], result["matchedDates"]


def check_availability() -> list[str]:
    """Playwrightでカレンダーを開き、対象日の空き枠リストを返す"""
    found_slots = []
    seen_target_dates = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)  # カレンダー表の描画完了をしっかり待つ

            for week_idx in range(4):
                slots, debug_headers, matched_dates = extract_slots_from_page(page, TARGET_DATES)
                print(f"[DEBUG] {week_idx + 1}週目の画面で検出した日付見出し: {debug_headers[:10]}")

                for s in slots:
                    if s not in found_slots:
                        found_slots.append(s)

                seen_target_dates.update(matched_dates)

                # 監視したい日付をすべて確認できたらループ終了
                if all(d in seen_target_dates for d in TARGET_DATES):
                    break

                # 「翌週」「次週」「次の週」などのボタンを探してクリック
                next_btn = page.locator(
                    "a:has-text('翌週'), a:has-text('次週'), a:has-text('次の週'), "
                    "a:has-text('次の7日'), a:has-text('翌7日'), a:has-text('次へ'), "
                    "button:has-text('翌週'), button:has-text('次週'), "
                    "a:has-text('＞'), a:has-text('>'), input[value*='次'], input[value*='翌']"
                ).first

                if next_btn.count() > 0 and next_btn.is_visible():
                    print("[DEBUG] 次の週のカレンダーへ移動します...")
                    next_btn.click()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(2500)
                else:
                    print("[DEBUG] 次週へ進むボタンが見つからないため移動を終了します。")
                    break

        except Exception as e:
            print(f"[ERROR] スクレイピング中にエラーが発生しました: {e}")
        finally:
            browser.close()

    return found_slots


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 空き状況を確認中... (対象日: {', '.join(TARGET_DATES)})")

    available = check_availability()

    if available:
        print(f"[INFO] 空き枠を {len(available)} 件検知しました！")
        send_line_notification(available)
    else:
        print(f"[{now_str}] 対象日の空き枠はありませんでした。")


if __name__ == "__main__":
    main()
