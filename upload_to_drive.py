"""data/ の CSV を Google Drive 上の既存ファイルに上書きアップロードする。

サービスアカウントは自分の保存容量を持たないため、新規作成ではなく
「あなたの Drive にあるファイルを、共有されたサービスアカウントが上書き」する方式。

環境変数:
  GDRIVE_SA_KEY             サービスアカウントの JSON キー（中身そのもの）
  GDRIVE_ACTIVITIES_FILE_ID activities.csv のファイルID
  GDRIVE_SPLITS_FILE_ID     splits.csv のファイルID
"""
import json
import os
import sys

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SCOPES = ["https://www.googleapis.com/auth/drive"]
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files/{}?uploadType=media&supportsAllDrives=true"

TARGETS = [
    ("data/activities.csv", "GDRIVE_ACTIVITIES_FILE_ID"),
    ("data/splits.csv", "GDRIVE_SPLITS_FILE_ID"),
]


def main() -> int:
    key = os.environ.get("GDRIVE_SA_KEY")
    if not key:
        print("GDRIVE_SA_KEY が未設定のため Drive アップロードをスキップ")
        return 0

    creds = service_account.Credentials.from_service_account_info(json.loads(key), scopes=SCOPES)
    session = AuthorizedSession(creds)

    failed = False
    for path, env_name in TARGETS:
        file_id = os.environ.get(env_name)
        if not file_id:
            print(f"{env_name} が未設定: {path} をスキップ")
            continue
        if not os.path.exists(path):
            print(f"{path} が存在しないためスキップ")
            continue
        with open(path, "rb") as f:
            resp = session.patch(
                UPLOAD_URL.format(file_id),
                data=f.read(),
                headers={"Content-Type": "text/csv"},
            )
        if resp.ok:
            print(f"{path} → Drive ({file_id}) 更新OK")
        else:
            failed = True
            print(f"{path} の更新に失敗: {resp.status_code} {resp.text}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
