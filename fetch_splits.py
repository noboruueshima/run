"""ロング走・レースの FIT ファイルから 1km ごとのスプリットを作り、data/splits.csv に追記する。
FIT（ZIP）はリポジトリに保存せず、メモリ上で処理する。
対象: activities.csv のラン系アクティビティのうち、
      距離が LONG_KM 以上、またはタイトルにレース系キーワードを含むもの。
splits.csv にまだ入っていないアクティビティだけを、1回あたり MAX_PER_RUN 件まで処理する。
"""
import csv
import io
import os
import zipfile
from pathlib import Path

from fitparse import FitFile
from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator, resolve_api_key

ACTIVITIES = Path(os.getenv("OUT_PATH", "data/activities.csv"))
SPLITS = Path(os.getenv("SPLITS_PATH", "data/splits.csv"))
LONG_KM = float(os.getenv("LONG_KM") or "15")
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN") or "200")
RUN_TYPES = {"ラン", "トレイルラン", "トレッドミル", "トラックラン", "running"}
RACE_WORDS = ("マラソン", "レース", "大会", "ハーフ", "race", "Race", "Marathon")
PAUSE_SEC = 10  # 記録間隔がこれ以上空いたら一時停止とみなして集計から除く

COLUMNS = ["アクティビティID", "日付", "タイトル", "km", "区間距離", "タイム", "ペース",
           "平均心拍数", "最大心拍数", "平均ピッチ", "標高差"]


def hms(sec):
    sec = int(round(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def pace(sec, meters):
    if meters <= 0:
        return "--"
    s = int(round(sec / meters * 1000))
    return f"{s // 60}:{s % 60:02d}"


def is_target(row):
    if row["アクティビティタイプ"] not in RUN_TYPES:
        return False
    try:
        km = float(row["距離"])
    except ValueError:
        km = 0
    return km >= LONG_KM or any(w in row["タイトル"] for w in RACE_WORDS)


def read_records(zip_bytes):
    """ZIP 内の FIT から record メッセージ（時刻・距離・心拍・ピッチ・高度）を取り出す"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".fit"))
        fit = FitFile(io.BytesIO(z.read(name)))
    recs = []
    for m in fit.get_messages("record"):
        v = m.get_values()
        if v.get("distance") is None or v.get("timestamp") is None:
            continue
        cad = v.get("cadence")
        if cad is not None:
            cad = (cad + (v.get("fractional_cadence") or 0)) * 2  # 片足 rpm → 歩/分
        recs.append({
            "t": v["timestamp"].timestamp(),
            "d": float(v["distance"]),
            "hr": v.get("heart_rate"),
            "cad": cad,
            "alt": v.get("enhanced_altitude", v.get("altitude")),
        })
    return recs


def make_splits(recs):
    """record 列を 1km ごとに集計する（一時停止中の時間は除外、心拍・ピッチは時間加重平均）"""
    splits, cur = [], None
    for prev, r in zip(recs, recs[1:]):
        dt = r["t"] - prev["t"]
        km = int(prev["d"] // 1000) + 1
        if cur is None or cur["km"] != km:
            if cur:
                splits.append(cur)
            cur = {"km": km, "start_d": prev["d"], "end_d": prev["d"], "sec": 0.0,
                   "hr_sum": 0.0, "hr_t": 0.0, "hr_max": 0, "cad_sum": 0.0, "cad_t": 0.0,
                   "alt0": prev["alt"], "alt1": prev["alt"]}
        cur["end_d"] = r["d"]
        cur["alt1"] = r["alt"] if r["alt"] is not None else cur["alt1"]
        if dt <= 0 or dt > PAUSE_SEC:
            continue
        cur["sec"] += dt
        if r["hr"]:
            cur["hr_sum"] += r["hr"] * dt
            cur["hr_t"] += dt
            cur["hr_max"] = max(cur["hr_max"], r["hr"])
        if r["cad"]:
            cur["cad_sum"] += r["cad"] * dt
            cur["cad_t"] += dt
    if cur:
        splits.append(cur)
    return [s for s in splits if s["end_d"] - s["start_d"] >= 50]  # 端数の極小区間は捨てる


def to_rows(act, splits):
    rows = []
    for s in splits:
        dist = s["end_d"] - s["start_d"]
        elev = (s["alt1"] - s["alt0"]) if s["alt0"] is not None and s["alt1"] is not None else None
        rows.append({
            "アクティビティID": act["アクティビティID"],
            "日付": act["日付"],
            "タイトル": act["タイトル"],
            "km": s["km"],
            "区間距離": f"{dist / 1000:.2f}",
            "タイム": hms(s["sec"]),
            "ペース": pace(s["sec"], dist),
            "平均心拍数": f"{s['hr_sum'] / s['hr_t']:.0f}" if s["hr_t"] else "--",
            "最大心拍数": s["hr_max"] or "--",
            "平均ピッチ": f"{s['cad_sum'] / s['cad_t']:.0f}" if s["cad_t"] else "--",
            "標高差": f"{elev:+.0f}" if elev is not None else "--",
        })
    return rows


def main():
    with ACTIVITIES.open(encoding="utf-8-sig", newline="") as f:
        targets = [r for r in csv.DictReader(f) if is_target(r)]

    done = set()
    if SPLITS.exists():
        with SPLITS.open(encoding="utf-8-sig", newline="") as f:
            done = {r["アクティビティID"] for r in csv.DictReader(f)}

    todo = [a for a in targets if a["アクティビティID"] not in done][:MAX_PER_RUN]
    print(f"対象 {len(targets)} 件 / 取得済み {len(done)} 件 / 今回処理 {len(todo)} 件")
    if not todo:
        return

    with PersonalApiAuthenticator() as auth:
        token = auth.obtain_token(resolve_api_key())

    new_rows = []
    with GarminPersonalApiClient(token.access_token) as client:
        for i, act in enumerate(todo, 1):
            try:
                recs = read_records(client.download_activity(int(act["アクティビティID"])))
                rows = to_rows(act, make_splits(recs))
                new_rows.extend(rows)
                print(f"  [{i}/{len(todo)}] {act['日付']} {act['タイトル']} … {len(rows)} 区間")
            except Exception as e:  # 1件の失敗で全体を止めない（翌日に再試行される）
                print(f"  [{i}/{len(todo)}] {act['アクティビティID']} 失敗: {e}")

    write_header = not SPLITS.exists()
    SPLITS.parent.mkdir(parents=True, exist_ok=True)
    with SPLITS.open("a", encoding="utf-8-sig" if write_header else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    print(f"{len(new_rows)} 行を追記 -> {SPLITS}")


if __name__ == "__main__":
    main()
