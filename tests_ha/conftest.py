"""Fixtures for Home Assistant tests (run in WSL/Linux, see README)."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spider_farmer.const import (
    CONF_DEVICES,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_TOKEN,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.spider_farmer.sfcloud.mqtt import SpiderFarmerMqtt

SERIAL = "AABBCCDDEEFF"
USER_ID = 12345
EMAIL = "grower@example.com"

DEVICE_RAW = {
    "deviceSerialnum": SERIAL,
    "deviceName": "Tent",
    "productType": "SF-GGS-PS5",
    "hardwareVersion": "3.14",
    "connectStatus": 1,
}

# Shapes taken from real captures (values anonymized/shortened).
SYS_STA = {"sys": {"ver": "3.14", "hwver": "S-ZC5-V2.5", "upTime": 1592800, "wifi": {"rssi": -58}}}
DEV_STA = {
    "outlet": {
        "psmode": 1,
        "O1": {"modeType": 3, "on": 1},
        "O2": {"on": 0},
        "O3": {"on": 0},
        "O4": {"on": 0},
        "O5": {"on": 0},
    },
    "sensor": {
        "temp": 21.1,
        "humi": 59.8,
        "vpd": 1.01,
        "ppfd": 0,
        "tempSoil": 20.2,
        "humiSoil": 52.1,
        "ECSoil": 0.96,
    },
    "light": {"modeType": 1, "level": 0},
    "blower": {"on": 1, "level": 37},
    "fan": {"on": 1, "level": 2},
}
CONFIG_FILE = {
    "configFile": {
        "outlet": {
            "O3": {"modeType": 0, "tempAdd": 1, "humiAdd": 1, "mOnOff": 0},
        },
        "device": {
            "light": {"modeType": 1, "mOnOff": 1, "mLevel": 16},
            "fan": {"modeType": 0, "shakeLevel": 0, "natural": 0, "mOnOff": 1, "mLevel": 2},
            "blower": {"modeType": 0, "maxSpeed": 36, "mOnOff": 1, "mLevel": 37},
        },
    }
}


class FakeBroker:
    """Stands in for the aiomqtt client: answers requests like the device does."""

    def __init__(self, mqtt: SpiderFarmerMqtt) -> None:
        self.mqtt = mqtt
        self.published: list[dict[str, Any]] = []
        self.config = copy.deepcopy(CONFIG_FILE)

    def reply(self, method: str, data: dict[str, Any] | None = None) -> None:
        device = self.mqtt.devices[SERIAL]
        msg: dict[str, Any] = {"method": method, "pid": SERIAL, "code": 200, "msg": "ok"}
        if data is not None:
            msg["data"] = data
        self.mqtt._handle(device.up_topic, json.dumps(msg).encode())

    async def publish(self, topic: str, payload: str) -> None:
        msg = json.loads(payload)
        self.published.append(msg)
        method = msg["method"]
        if method == "getConfigFile":
            self.reply(method, copy.deepcopy(self.config))
        elif method == "getDevSta":
            self.reply(method, DEV_STA)
        elif method == "getSysSta":
            self.reply(method, SYS_STA)
        elif method == "setConfigField":
            self.reply(method)

    @property
    def commands(self) -> list[dict[str, Any]]:
        return [m["params"] for m in self.published if m["method"] == "setConfigField"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=str(USER_ID),
        data={
            "email": EMAIL,
            CONF_TOKEN: "token",
            CONF_USER_ID: USER_ID,
            CONF_MQTT_USERNAME: EMAIL,
            CONF_MQTT_PASSWORD: "secret",
            CONF_DEVICES: [DEVICE_RAW],
        },
    )


@pytest.fixture
def broker() -> Generator[list[FakeBroker]]:
    """Replace the broker connection; yields the list holding the active FakeBroker."""
    brokers: list[FakeBroker] = []

    async def fake_run_once(self: SpiderFarmerMqtt) -> None:
        fake = FakeBroker(self)
        brokers.append(fake)
        self._client = fake  # type: ignore[assignment]
        if self._on_connection_change:
            self._on_connection_change(True)
        for serial in self.devices:
            for method in ("getSysSta", "getDevSta", "getConfigFile"):
                await self.request(serial, method)
        await asyncio.Event().wait()

    with patch.object(SpiderFarmerMqtt, "_run_once", fake_run_once):
        yield brokers
