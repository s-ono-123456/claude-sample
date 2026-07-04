import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest

from lib.switchbot_client import SwitchBotApiError, SwitchBotClient


@pytest.fixture
def client():
    return SwitchBotClient(token="test-token", secret="test-secret")


def test_build_headers_signature_matches_hmac(client):
    headers = client._build_headers()
    t = headers["t"]
    nonce = headers["nonce"]
    string_to_sign = f"test-token{t}{nonce}".encode("utf-8")
    expected_sign = base64.b64encode(
        hmac.new(b"test-secret", msg=string_to_sign, digestmod=hashlib.sha256).digest()
    ).decode("utf-8")

    assert headers["sign"] == expected_sign
    assert headers["Authorization"] == "test-token"


@patch("lib.switchbot_client.requests.get")
def test_get_sensor_reading_success(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "statusCode": 100,
        "body": {"temperature": 26.5, "humidity": 55},
        "message": "success",
    }
    mock_get.return_value = mock_response

    reading = client.get_sensor_reading("device-1")

    assert reading.temperature_c == 26.5
    assert reading.humidity_percent == 55
    called_url = mock_get.call_args.args[0]
    assert called_url.endswith("/devices/device-1/status")


@patch("lib.switchbot_client.requests.get")
def test_get_sensor_reading_raises_on_api_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"statusCode": 190, "message": "error"}
    mock_get.return_value = mock_response

    with pytest.raises(SwitchBotApiError):
        client.get_sensor_reading("device-1")


@patch("lib.switchbot_client.requests.get")
def test_is_device_powered_on_true_when_power_on(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "statusCode": 100,
        "body": {"power": "on"},
        "message": "success",
    }
    mock_get.return_value = mock_response

    assert client.is_device_powered_on("plug-1") is True
    called_url = mock_get.call_args.args[0]
    assert called_url.endswith("/devices/plug-1/status")


@patch("lib.switchbot_client.requests.get")
def test_is_device_powered_on_false_when_power_off(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "statusCode": 100,
        "body": {"power": "off"},
        "message": "success",
    }
    mock_get.return_value = mock_response

    assert client.is_device_powered_on("plug-1") is False


@patch("lib.switchbot_client.requests.get")
def test_is_device_powered_on_raises_on_api_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"statusCode": 190, "message": "error"}
    mock_get.return_value = mock_response

    with pytest.raises(SwitchBotApiError):
        client.is_device_powered_on("plug-1")


@patch("lib.switchbot_client.requests.get")
def test_list_devices_success(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "statusCode": 100,
        "body": {
            "deviceList": [{"deviceId": "device-1", "deviceName": "meter"}],
            "infraredRemoteList": [{"deviceId": "aircon-1", "deviceName": "aircon"}],
        },
        "message": "success",
    }
    mock_get.return_value = mock_response

    result = client.list_devices()

    assert result["deviceList"][0]["deviceId"] == "device-1"
    assert result["infraredRemoteList"][0]["deviceId"] == "aircon-1"
    called_url = mock_get.call_args.args[0]
    assert called_url.endswith("/devices")


@patch("lib.switchbot_client.requests.get")
def test_list_devices_raises_on_api_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"statusCode": 190, "message": "error"}
    mock_get.return_value = mock_response

    with pytest.raises(SwitchBotApiError):
        client.list_devices()


@patch("lib.switchbot_client.requests.post")
def test_send_aircon_command_success(mock_post, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"statusCode": 100, "body": {}, "message": "success"}
    mock_post.return_value = mock_response

    client.send_aircon_command("device-2", temperature=25, mode=2, fan_speed=1, power_on=True)

    called_kwargs = mock_post.call_args.kwargs
    assert called_kwargs["json"]["parameter"] == "25,2,1,on"
    called_url = mock_post.call_args.args[0]
    assert called_url.endswith("/devices/device-2/commands")
