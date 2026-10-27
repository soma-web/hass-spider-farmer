"""Tests for API data models."""

import json

from sfcloud import Device, LoginResult, topic_prefix

DEVICE_INFO = {
    "sensor": {"temp": 30.2, "humi": 45.8, "vpd": 2.33},
    "outlet": {"psmode": 1, "O1": {"on": 0}},
    "light": {"level": 0},
}


def test_topic_prefix() -> None:
    assert topic_prefix("SF-GGS-PS5") == "SF/GGS/PS5"


def test_device_from_api_parses_info_string() -> None:
    device = Device.from_api(
        {
            "deviceSerialnum": "ABC123",
            "deviceName": "Tent",
            "productType": "SF-GGS-PS5",
            "hardwareVersion": "3.14",
            "connectStatus": 1,
            "deviceInfo": json.dumps(DEVICE_INFO),
        },
        room_id=7,
    )
    assert device.info == DEVICE_INFO
    assert device.online is True
    assert device.room_id == 7
    assert device.up_topic == "SF/GGS/PS5/API/UP/ABC123"
    assert device.down_topic == "SF/GGS/PS5/API/DOWN/ABC123"


def test_device_from_api_tolerates_bad_info() -> None:
    device = Device.from_api({"deviceSerialnum": "X", "deviceInfo": "not json"})
    assert device.info == {}
    assert device.name == "X"
    assert device.online is False


def test_login_result() -> None:
    result = LoginResult.from_api(
        {"token": "t", "userId": "42", "mqttName": "u", "mqttPwd": "p", "nickName": "n"}
    )
    assert result.user_id == 42
    assert result.mqtt_password == "p"
