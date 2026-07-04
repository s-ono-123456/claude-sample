"""S3バケット内の単一JSONオブジェクトで前回操作状態(設定温度・操作時刻・学習済み補正量等)を読み書きする。"""

import json
from datetime import datetime

from botocore.exceptions import ClientError

from lib.comfort import LastState, Mode


def _empty_state() -> LastState:
    return LastState(
        last_set_temp=None, last_action_at=None, last_target_di=None, correction_offset=0.0, mode=Mode.COOL
    )


def load_state(s3_client, bucket: str, key: str) -> LastState:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] == "NoSuchKey":
            return _empty_state()
        raise

    data = json.loads(response["Body"].read())
    last_action_at = data.get("last_action_at")
    return LastState(
        last_set_temp=data.get("last_set_temp"),
        last_action_at=datetime.fromisoformat(last_action_at) if last_action_at else None,
        last_target_di=data.get("last_target_di"),
        correction_offset=data.get("correction_offset", 0.0),
        mode=Mode(data.get("mode", "cool")),
    )


def save_state(s3_client, bucket: str, key: str, state: LastState) -> None:
    body = json.dumps(
        {
            "last_set_temp": state.last_set_temp,
            "last_action_at": state.last_action_at.isoformat() if state.last_action_at else None,
            "last_target_di": state.last_target_di,
            "correction_offset": state.correction_offset,
            "mode": state.mode.value,
        }
    )
    s3_client.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")
