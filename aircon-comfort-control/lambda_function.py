"""エアコン快適制御 Lambda エントリポイント。

1サイクルの処理: SwitchBotからセンサー値取得 → 不快指数計算 → 前回状態(S3)と比較し
判定 → 必要ならSwitchBot経由でエアコンの設定温度を変更 → 状態をS3に保存。
"""

import logging
import os
from dataclasses import replace
from datetime import datetime, timezone

import boto3

from lib.comfort import ActionType, LastState, Mode, calculate_discomfort_index, decide_action
from lib.state_store import load_state, save_state
from lib.switchbot_client import SwitchBotClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _load_config() -> dict:
    return {
        "switchbot_token": os.environ["SWITCHBOT_TOKEN"],
        "switchbot_secret": os.environ["SWITCHBOT_SECRET"],
        "sensor_device_id": os.environ["SWITCHBOT_SENSOR_DEVICE_ID"],
        "aircon_device_id": os.environ["SWITCHBOT_AIRCON_DEVICE_ID"],
        "presence_device_id": os.environ.get("SWITCHBOT_PRESENCE_DEVICE_ID"),
        "s3_bucket": os.environ["S3_BUCKET"],
        "s3_state_key": os.environ.get("S3_STATE_KEY", "state.json"),
        "di_target_min": float(os.environ.get("DI_TARGET_MIN", "60")),
        "di_target_max": float(os.environ.get("DI_TARGET_MAX", "70")),
        "di_deadband": float(os.environ.get("DI_DEADBAND", "2")),
        "cooldown_minutes": int(os.environ.get("COOLDOWN_MINUTES", "15")),
        "temp_min": int(os.environ.get("TEMP_MIN", "20")),
        "temp_max": int(os.environ.get("TEMP_MAX", "28")),
        "temp_step_max": int(os.environ.get("TEMP_STEP_MAX", "1")),
        "aircon_mode_cool": int(os.environ.get("AIRCON_MODE_COOL", "2")),
        "aircon_mode_dry": int(os.environ.get("AIRCON_MODE_DRY", "3")),
        "aircon_fan_speed": int(os.environ.get("AIRCON_FAN_SPEED", "1")),
        "temp_correction_learning_rate": float(os.environ.get("TEMP_CORRECTION_LEARNING_RATE", "0.3")),
        "temp_correction_max_offset": float(os.environ.get("TEMP_CORRECTION_MAX_OFFSET", "5")),
        "humidity_target_max": float(os.environ.get("HUMIDITY_TARGET_MAX", "60")),
        "humidity_deadband": float(os.environ.get("HUMIDITY_DEADBAND", "5")),
    }


def lambda_handler(event, context):
    config = _load_config()
    s3_client = boto3.client("s3")
    switchbot = SwitchBotClient(config["switchbot_token"], config["switchbot_secret"])

    if config["presence_device_id"] and not switchbot.is_device_powered_on(config["presence_device_id"]):
        logger.info("presence=away, skipping this cycle")
        return {"action": ActionType.NOOP.value, "discomfort_index": None, "new_temp": None}

    reading = switchbot.get_sensor_reading(config["sensor_device_id"])
    di = calculate_discomfort_index(reading.temperature_c, reading.humidity_percent)
    logger.info(
        "temperature=%.1f humidity=%.1f discomfort_index=%.1f",
        reading.temperature_c,
        reading.humidity_percent,
        di,
    )

    last_state = load_state(s3_client, config["s3_bucket"], config["s3_state_key"])
    now = datetime.now(timezone.utc)

    decision = decide_action(
        di,
        reading.humidity_percent,
        last_state,
        now,
        config["di_target_min"],
        config["di_target_max"],
        config["di_deadband"],
        config["cooldown_minutes"],
        config["temp_min"],
        config["temp_max"],
        config["temp_step_max"],
        config["temp_correction_learning_rate"],
        config["temp_correction_max_offset"],
        config["humidity_target_max"],
        config["humidity_deadband"],
    )
    logger.info(
        "action=%s correction_offset=%.2f",
        decision.action.value,
        decision.correction_offset,
    )

    new_state = replace(
        last_state,
        last_target_di=decision.pending_target_di,
        correction_offset=decision.correction_offset,
        mode=decision.new_mode if decision.new_mode is not None else last_state.mode,
    )

    if decision.action != ActionType.NOOP:
        mode_code = config["aircon_mode_dry"] if new_state.mode == Mode.DRY else config["aircon_mode_cool"]
        switchbot.send_aircon_command(
            config["aircon_device_id"],
            temperature=decision.new_temp,
            mode=mode_code,
            fan_speed=config["aircon_fan_speed"],
            power_on=True,
        )
        new_state = replace(new_state, last_set_temp=decision.new_temp, last_action_at=now)
        logger.info("set temperature to %d mode to %s", decision.new_temp, new_state.mode.value)

    if new_state != last_state:
        save_state(s3_client, config["s3_bucket"], config["s3_state_key"], new_state)

    return {"action": decision.action.value, "discomfort_index": di, "new_temp": decision.new_temp}
