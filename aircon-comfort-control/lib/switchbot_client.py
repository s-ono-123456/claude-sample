"""SwitchBot OpenAPI v1.1 クライアント。温湿度センサーのステータス取得とエアコン(赤外線リモコン)へのコマンド送信を行う。"""

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass

import requests

API_BASE_URL = "https://api.switch-bot.com/v1.1"


class SwitchBotApiError(Exception):
    pass


@dataclass
class SensorReading:
    temperature_c: float
    humidity_percent: float


class SwitchBotClient:
    def __init__(self, token: str, secret: str, timeout_seconds: float = 10.0):
        self._token = token
        self._secret = secret
        self._timeout_seconds = timeout_seconds

    def _build_headers(self) -> dict[str, str]:
        nonce = str(uuid.uuid4())
        t = str(int(round(time.time() * 1000)))
        string_to_sign = f"{self._token}{t}{nonce}".encode("utf-8")
        sign = base64.b64encode(
            hmac.new(self._secret.encode("utf-8"), msg=string_to_sign, digestmod=hashlib.sha256).digest()
        )
        return {
            "Authorization": self._token,
            "Content-Type": "application/json",
            "charset": "utf8",
            "t": t,
            "sign": sign.decode("utf-8"),
            "nonce": nonce,
        }

    def get_sensor_reading(self, device_id: str) -> SensorReading:
        response = requests.get(
            f"{API_BASE_URL}/devices/{device_id}/status",
            headers=self._build_headers(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("statusCode") != 100:
            raise SwitchBotApiError(f"SwitchBot API error: {body}")
        result = body["body"]
        return SensorReading(
            temperature_c=result["temperature"],
            humidity_percent=result["humidity"],
        )

    def is_device_powered_on(self, device_id: str) -> bool:
        response = requests.get(
            f"{API_BASE_URL}/devices/{device_id}/status",
            headers=self._build_headers(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("statusCode") != 100:
            raise SwitchBotApiError(f"SwitchBot API error: {body}")
        return body["body"]["power"] == "on"

    def list_devices(self) -> dict:
        response = requests.get(
            f"{API_BASE_URL}/devices",
            headers=self._build_headers(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("statusCode") != 100:
            raise SwitchBotApiError(f"SwitchBot API error: {body}")
        return body["body"]

    def send_aircon_command(
        self,
        device_id: str,
        temperature: int,
        mode: int,
        fan_speed: int,
        power_on: bool,
    ) -> None:
        """mode: 1=自動 2=冷房 3=除湿 4=送風 5=暖房。fan_speed: 1=自動 2=弱 3=中 4=強"""
        parameter = f"{temperature},{mode},{fan_speed},{'on' if power_on else 'off'}"
        response = requests.post(
            f"{API_BASE_URL}/devices/{device_id}/commands",
            headers=self._build_headers(),
            json={"command": "setAll", "parameter": parameter, "commandType": "command"},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("statusCode") != 100:
            raise SwitchBotApiError(f"SwitchBot API error: {body}")
