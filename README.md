# Garmin → CSV 自動エクスポート（公式 Personal API 版）

## 1. ローカルで動作確認
```
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GARMIN_PERSONAL_API_KEY = "取得したキー"
python fetch_activities.py
```
`data/activities.csv` ができればOK。

## 2. GitHub
1. プライベートリポジトリを作成し、この一式を push
2. Settings → Secrets and variables → Actions → New repository secret
   - Name: `GARMIN_PERSONAL_API_KEY` / Value: Personal API キー
3. Actions タブ →「Garmin export」→「Run workflow」で手動テスト
4. 以後は毎朝 6:00 JST に自動実行

## キーの更新
キーには有効期限（30日〜1年）があり、期限の約1週間前に Garmin からメールが届く。
Garmin Connect で新しいキーを作成し、Secret を上書きする。

## Windows タスクスケジューラーで動かす場合
キーを `%USERPROFILE%\.config\garmin\connect-personal-api-key` に保存（中身はキーのみ）。
- プログラム: `.venv\Scripts\python.exe` のフルパス
- 引数: `fetch_activities.py`
- 開始: このフォルダのパス
- 出力先を変えるなら環境変数 `OUT_PATH`

## 環境変数
| 変数 | 既定値 | 内容 |
|---|---|---|
| GARMIN_PERSONAL_API_KEY | （なし） | Personal API キー |
| OUT_PATH | data/activities.csv | 出力先 |
| FETCH_DAYS | 14 | 何日分さかのぼるか |
