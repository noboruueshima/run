"""Garmin 公式 Personal API で Garmin Connect から直近のアクティビティを取得し、data/activities.csv に追記する。
既存の Activities.csv（Garmin Connect のエクスポート）とほぼ同じ列構成で出力する。
"""
import csv
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator, resolve_api_key

OUT = Path(os.getenv("OUT_PATH", "data/activities.csv"))
DAYS = int(os.getenv("FETCH_DAYS") or "14")  # 何日分さかのぼるか。0 で全期間を取得

COLUMNS = [
    "アクティビティID", "アクティビティタイプ", "日付", "タイトル", "距離", "カロリー", "タイム",
    "平均心拍数", "最大心拍数", "有酸素トレーニング効果", "平均ピッチ", "最高ピッチ",
    "平均ペース", "最高ペース", "総上昇量", "総下降量", "平均歩幅", "ステップ",
    "ラップ数", "移動時間", "経過時間", "最低高度", "最高高度",
]

TYPE_JA = {"running": "ラン", "trail_running": "トレイルラン", "treadmill_running": "トレッドミル",
           "track_running": "トラックラン", "walking": "ウォーキング", "cycling": "サイクリング"}


def hms(sec):
    if not sec:
        return "--"
    sec = int(round(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def pace(mps):
    """m/s → 分:秒/km"""
    if not mps:
        return "--"
    s = int(round(1000 / mps))
    return f"{s // 60}:{s % 60:02d}"


def num(v, fmt="{:.0f}"):
    return "--" if v is None else fmt.format(v)


def to_row(a):
    t = a.get("activityType", {}).get("typeKey", "")
    return {
        "アクティビティID": a["activityId"],
        "アクティビティタイプ": TYPE_JA.get(t, t),
        "日付": a.get("startTimeLocal", ""),
        "タイトル": a.get("activityName", ""),
        "距離": num((a.get("distance") or 0) / 1000, "{:.2f}"),
        "カロリー": num(a.get("calories")),
        "タイム": hms(a.get("duration")),
        "平均心拍数": num(a.get("averageHR")),
        "最大心拍数": num(a.get("maxHR")),
        "有酸素トレーニング効果": num(a.get("aerobicTrainingEffect"), "{:.1f}"),
        "平均ピッチ": num(a.get("averageRunningCadenceInStepsPerMinute")),
        "最高ピッチ": num(a.get("maxRunningCadenceInStepsPerMinute")),
        "平均ペース": pace(a.get("averageSpeed")),
        "最高ペース": pace(a.get("maxSpeed")),
        "総上昇量": num(a.get("elevationGain")),
        "総下降量": num(a.get("elevationLoss")),
        "平均歩幅": num((a.get("avgStrideLength") or 0) / 100, "{:.2f}"),
        "ステップ": num(a.get("steps")),
        "ラップ数": num(a.get("lapCount")),
        "移動時間": hms(a.get("movingDuration")),
        "経過時間": hms(a.get("elapsedDuration")),
        "最低高度": num(a.get("minElevation")),
        "最高高度": num(a.get("maxElevation")),
    }


def fetch(client, start, end):
    """期間内のアクティビティを100件ずつページングして全件取得"""
    acts, offset = [], 0
    while True:
        if start is None:  # 全期間
            page = client.search_activities(start=offset, limit=100)
        else:
            page = client.search_activities(start=offset, limit=100,
                                            start_date=start, end_date=end)
        if isinstance(page, dict):  # 念のため dict 形式にも対応
            page = page.get("activityList") or page.get("activities") or []
        acts.extend(page)
        print(f"  {len(acts)} 件取得済み...")
        if len(page) < 100:
            return acts
        offset += 100


def main():
    # 鍵は 環境変数 GARMIN_PERSONAL_API_KEY → ~/.config/garmin/connect-personal-api-key の順に探す
    with PersonalApiAuthenticator() as auth:
        token = auth.obtain_token(resolve_api_key())

    end = date.today()
    start = None if DAYS == 0 else end - timedelta(days=DAYS)
    with GarminPersonalApiClient(token.access_token) as client:
        acts = fetch(client, start, end)

    rows = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8-sig", newline="") as f:
            rows = {r["アクティビティID"]: r for r in csv.DictReader(f)}

    added = 0
    for a in acts:
        key = str(a["activityId"])
        if key not in rows:
            added += 1
        rows[key] = to_row(a)  # 既存分も最新値で上書き

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: r["日付"], reverse=True):
            w.writerow(r)

    print(f"{datetime.now():%Y-%m-%d %H:%M} 取得 {len(acts)} 件 / 新規 {added} 件 -> {OUT}")


if __name__ == "__main__":
    main()
