# 🚲 Gattan Go!! 空席監視＆LINE通知システム

レールマウンテンバイク「Gattan Go!!」の予約サイトを24時間自動で巡回し、希望日にキャンセル（空き枠）が出た瞬間にLINEへ自動通知するシステムです。

* **PC不要・完全無料**：GitHub Actions 上で動くため、PCの電源を切っていても裏側で自動稼働します。
* **翌週以降のページにも対応**：カレンダーの「翌週」ボタンを自動でめくって対象日を確認します。
* **重複通知防止機能**：一度通知した空き枠は `notified_slots.json` に自動記録され、同じ枠で何度もLINEが鳴り続けるのを防ぎます。

---

## 📱 パターン1：同じLINE通知を一緒に受け取りたい方（家族・同行者向け）

すでに動いている監視システムの通知を一緒に受け取るだけの場合は、GitHubの操作は不要です。

1. このシステムの管理者から **LINE公式アカウントのQRコード（またはID）** を受け取ります。
2. スマホのLINEアプリで **「友だち追加」** するだけで完了です。空きが出た際、全員のLINEに同時に通知が届きます。

---

## 🛠️ パターン2：自分用にコピーして別の日付・コースを監視したい方

ご自身のLINEアカウントや、希望する別の日付で監視したい場合は、以下の5ステップで自分専用システムとして複製できます（所要時間：約10分）。

### Step 1：このリポジトリを自分用にコピー（Fork）する
1. GitHubにログインした状態で、このページ右上にある **「Fork」** ボタンをクリックします。
2. **「Create fork」** を押すと、あなたのアカウント内に同じプログラム一式が複製されます（公開設定は無料の **Public** のままで問題ありません）。

### Step 2：LINEの通知用トークンを取得する
1. [LINE Developersコンソール](https://developers.line.biz/ja/) にログインし、新規プロバイダーと **「Messaging API」** チャネルを作成します。
2. 作成したチャネルの **「Messaging API設定」** タブを開き、画面内の **QRコード** をスマホのLINEで読み取って **友だち追加** します。
3. 同じ画面の一番下にある **「チャネルアクセストークン（長期）」** の「発行」ボタンを押し、表示された長い文字列をコピーします。

### Step 3：GitHubにLINEトークンを登録する（暗号化保管）
1. コピーした自分のリポジトリ画面上部の **「Settings」** ＞ 左メニューの **「Secrets and variables」** ＞ **「Actions」** を開きます。
2. 緑色の **「New repository secret」** ボタンを押します。
3. 以下のように入力して **「Add secret」** で保存します（外部には一切公開されません）。
   * **Name**：`LINE_CHANNEL_ACCESS_TOKEN`
   * **Secret**：Step 2でコピーしたチャネルアクセストークン

### Step 4：監視したい日付やコースURLを変更する
1. リポジトリのファイル一覧から **`monitor_gattango.py`** を開き、右上の **鉛筆マーク（Edit this file）** をクリックします。
2. 上部にある設定項目を自分の希望に合わせて書き換えます。
   * **監視する日付を変える場合**：`TARGET_DATES = ["11/12", "11/13"]` の日付を希望日（例：`["11/20", "11/21"]` など）に変更します。
   * **監視するコースを変える場合**：`TARGET_URL` のURLを、監視したいコースの予約カレンダーURLに変更します。
   * **テスト通知を送りたい場合**：現在予約サイトで実際に空いている直近の日付を1つ `TARGET_DATES` に追加して実行すると、LINE通知の動作テストができます（確認後は元の希望日に戻してください）。
3. 右上の **「Commit changes...」** を押して保存します。
4. あわせて **`.github/workflows/monitor.yml`** を鉛筆マークから開き、`if [ "$CURRENT_DATE" -gt "20261113" ]; then` の `20261113` の部分を、自分の監視したい最終日（西暦8桁）に書き換えて保存します。

### Step 5：自動実行（Actions）を有効化してテストする
1. リポジトリ上部の **「Actions」** タブを開きます。
2. 初回のみ緑色のボタン **「I understand my workflows, go ahead and enable them」** が表示されるのでクリックして有効化します。
3. 左メニューの **「Gattan Go Vacancy Monitor」** を押し、右側の **「Run workflow」** から手動テスト実行を行います。1〜2分後に緑色のチェックマークが付けば稼働開始です！

---

## ⚡（オプション）監視間隔を正確に5分おきにする方法

GitHub Actionsの標準タイマーはサーバー混雑時に15〜30分おきに遅延することがあります。きっちり5分間隔で動かしたい場合は、無料サービス [cron-job.org](https://console.cron-job.org/) を併用します。

1. GitHub右上のアイコン ＞ **Settings** ＞ **Developer settings** ＞ **Personal access tokens (Tokens classic)** から、`repo` と `workflow` にチェックを入れたトークン（`ghp_...`）を発行します。
2. cron-job.org で新規ジョブを作成し、URLに `https://api.github.com/repos/あなたのユーザー名/リポジトリ名/actions/workflows/monitor.yml/dispatches` を指定して5分間隔に設定します。
3. **ADVANCED** タブで、Request method を `POST`、Request body を `{"ref":"main"}` にし、Headers に以下の3つを設定します。
   * `Authorization`: `Bearer 発行したトークン`
   * `Accept`: `application/vnd.github+json`
   * `Content-Type`: `application/json`

---

## 📁 ファイル構成

* `monitor_gattango.py`：Playwrightを用いたカレンダー巡回・空席判定・LINE通知スクリプト本体
* `.github/workflows/monitor.yml`：GitHub Actions 自動実行スケジュール設定ファイル
* `requirements.txt`：使用するPythonライブラリ一覧
* `notified_slots.json`：通知済み空き枠の自動記録ファイル（空き枠検知時に自動生成・更新されます）
