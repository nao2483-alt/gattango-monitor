import json
import os
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# ================= 設定項目 =================
TARGET_URL = "https://rail-mtb.resv.jp/reserve/calendar.php?direct_id=8"
TARGET_DATES = ["11/12", "11/13"]  # 監視したい日付
STATE_FILE = "notified_slots.json"  # 通知済み枠の記録ファイル

# GitHub SecretsからLINEのトークンを取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
# ============================================


def load_previous_slots() -> list[str]:
    """前回までに検知・通知した空き枠リストを読み込む"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[WARN] 状態ファイルの読み込みに失敗しました: {e}")
    return []


def save_current_slots(slots: list[str]):
    """現在空いている枠リストをファイルに保存する"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(slots, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 状態ファイルの保存に失敗しました: {e}")


def send_line_notification(available_slots: list[str]):
    """空きが見つかった際にLINEへ通知を送信する"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slot_text = "\n".join([f"・{slot}" for slot in available_slots])
    message = (
        f"🚲 【Gattan Go!! 渓谷コース】空き枠が出ました！\n"
        f"検知時刻: {now_str}\n\n"
        f"【新規空き枠詳細】\n{slot_text}\n\n"
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
        const hasMonth11 = bodyText.includes("11月") || bodyText.includes("2026/11") || bodyText.includes("2026年11月") || bodyText.includes("11/") || bodyText.includes("Nov");

        // 1. カレンダーの日付見出しセル（th, td等）を探す
        const candidates = Array.from(document.querySelectorAll("th, td, div"));
        const matchedColumns = [];

        for (const el of candidates) {
            const text = (el.innerText || "").trim().replace(/\\s+/g, " ");
            if (!text || text.length > 25) continue;

            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;

            if (/(?:\\d{1,2}[\\/月]\\d{1,2}|^\\d{1,2}(?:日)?\\s*[\\(（]?(?:[月火水木金土日]|Sun|Mon|Tue|Wed|Thu|Thr|Fri|Sat)[\\)）]?$)/i.test(text)) {
                if (!debugHeaders.includes(text)) debugHeaders.push(text);
            }

            for (const t of targets) {
                const regexFull = new RegExp(`(?:^|\\D)0?${t.m}[\\/月]0?${t.d}(?:日|\\D|$)`);
                const regexDayOnly = new RegExp(`^0?${t.d}(?:日)?\\s*[\\(（](?:[月火水木金土日]|Sun|Mon|Tue|Wed|Thu|Thr|Fri|Sat)[\\)）]`, "i");

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
                if (rect.top >= col.bottom - 5 && centerX >= col.left - 5 && centerX <= col.right + 5) {
                    const cellText = (cell.innerText || "").trim().replace(/\\s+/g, " ");
                    if (!cellText || cellText.length > 35) continue;

                    if (/^[×✕xX－\\-休満問]+$/.test(cellText) || cellText.includes("満席") || cellText.includes("終了") || cellText.toLowerCase().includes("full")) {
                        continue;
                    }

                    const hasLink = cell.tagName.toLowerCase() === "a" || cell.querySelector("a") !== null;
                    const hasAvailMark = /(残\\s*\\d+|○|◯|△|空|予約|left|avail)/i.test(cellText);

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

        // 3. リンクのURLやonclick属性に日付が直接入っている場合の予備検出
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


def click_next_week_button(page, prev_first_header: str) -> bool:
    """『翌週』ボタン単体をピンポイントで探し出し、Playwrightで確実にクリックして画面更新を待つ"""
    # 1. Playwrightのネイティブロケータで「翌週」単体の要素を探す（親要素を誤クリックしないよう文字数制限）
    target_locator = None
    matched_desc = ""

    # 候補となるセレクタを順番にチェック
    selectors = [
        "a:text-is('翌週')",
        "button:text-is('翌週')",
        "span:text-is('翌週')",
        "li:text-is('翌週')",
        "div:text-is('翌週')",
        "input[value='翌週']",
        "a:has-text('翌週')",
        "button:has-text('翌週')",
        "[onclick*='next']:has-text('翌週')",
    ]

    for sel in selectors:
        loc = page.locator(sel)
        count = loc.count()
        for i in range(count):
            el = loc.nth(i)
            if el.is_visible():
                txt = (el.inner_text() or "").strip()
                # 「翌月 翌週 前週 前月」のような親コンテナを除外し、8文字以下の単体ボタンのみ対象にする
                if len(txt) <= 8:
                    target_locator = el
                    matched_desc = f"{sel} (text='{txt}')"
                    break
        if target_locator:
            break

    if target_locator:
        print(f"[DEBUG] 次の週のカレンダーへ移動します... (検出: {matched_desc})")
        target_locator.click()
    else:
        # 2. フォールバック：JavaScriptで一番内側（最小サイズ）の「翌週」要素を探してクリック
        js_res = page.evaluate(
            """() => {
            const all = Array.from(document.querySelectorAll("a, button, input, span, li, td, div"));
            const matches = [];
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const txt = (el.innerText || el.value || "").trim().replace(/[\\s＞>»▶→]+/g, "");
                if (txt === "翌週" || txt === "次の週" || txt === "次週" || txt.toLowerCase() === "nextweek") {
                    matches.push({ el, area: rect.width * rect.height, tag: el.tagName, onclick: el.getAttribute("onclick") || "", href: el.getAttribute("href") || "" });
                }
            }
            // 面積が一番小さい（＝一番内側のボタンそのもの）を選択
            matches.sort((a, b) => a.area - b.area);
            if (matches.length > 0) {
                const best = matches[0];
                best.el.click();
                return { clicked: true, info: `tag=${best.tag} onclick=${best.onclick} href=${best.href}` };
            }
            return { clicked: false, info: "" };
        }"""
        )
        if js_res["clicked"]:
            print(f"[DEBUG] 次の週のカレンダーへ移動します... (JS最小要素検出: {js_res['info']})")
        else:
            print("[DEBUG] 『翌週』単体のボタンが見つかりませんでした。")
            return False

    # 3. クリック後、カレンダーの先頭日付が切り替わるまで最大6秒間待機する
    for _ in range(12):
        page.wait_for_timeout(500)
        _, current_headers, _ = extract_slots_from_page(page, [])
        if current_headers and current_headers[0] != prev_first_header:
            return True

    page.wait_for_timeout(1500)
    return True


def check_availability() -> tuple[list[str], bool]:
    """Playwrightでカレンダーを開き、(空き枠リスト, 対象日をすべて確認できたか) を返す"""
    found_slots = []
    seen_target_dates = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            extra_http_headers={"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            for week_idx in range(4):
                slots, debug_headers, matched_dates = extract_slots_from_page(page, TARGET_DATES)
                print(f"[DEBUG] {week_idx + 1}週目の画面で検出した日付見出し: {debug_headers[:10]}")

                for s in slots:
                    if s not in found_slots:
                        found_slots.append(s)

                seen_target_dates.update(matched_dates)

                # TARGET_DATES（11/12と11/13）の両方が画面で確認できたら完了
                if all(d in seen_target_dates for d in TARGET_DATES):
                    break

                prev_first = debug_headers[0] if debug_headers else ""
                if not click_next_week_button(page, prev_first):
                    print("[DEBUG] これ以上次の週へ進めないため移動を終了します。")
                    break

        except Exception as e:
            print(f"[ERROR] スクレイピング中にエラーが発生しました: {e}")
        finally:
            browser.close()

    is_success = all(d in seen_target_dates for d in TARGET_DATES)
    return found_slots, is_success


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 空き状況を確認中... (対象日: {', '.join(TARGET_DATES)})")

    previous_slots = load_previous_slots()
    current_slots, is_success = check_availability()

    if not is_success:
        print("[WARN] 対象日(11/12・13)のカレンダーまで到達できなかったため、状態ファイルの更新をスキップします。")
        return

    # 前回はなかった「新規の空き枠」だけを抽出
    new_slots = [s for s in current_slots if s not in previous_slots]

    if new_slots:
        print(f"[INFO] 新規の空き枠を {len(new_slots)} 件検知しました！LINE通知を送信します。")
        send_line_notification(new_slots)
    elif current_slots:
        print(f"[INFO] 現在も空き枠がありますが、既に通知済みのためLINE送信をスキップしました: {current_slots}")
    else:
        print(f"[{now_str}] 11/12・13の空き枠はありませんでした。（2週目まで正常に確認完了）")

    # 状態に変化があった場合のみファイルを書き換える
    if set(current_slots) != set(previous_slots):
        save_current_slots(current_slots)
        print(f"[INFO] 通知済み状態ファイルを更新しました: {current_slots}")


if __name__ == "__main__":
    main()
