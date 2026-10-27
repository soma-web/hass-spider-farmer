"""Tests for MQTT message handling and command building (no broker needed)."""

from __future__ import annotations

import json
from typing import Any

from sfcloud import Device, SpiderFarmerMqtt
from sfcloud.mqtt import build_set_config, component_config

DEVICE = Device.from_api({"deviceSerialnum": "S1", "productType": "SF-GGS-PS5"})
BLOWER = {"modeType": 0, "minSpeed": 0, "maxSpeed": 36, "mOnOff": 0, "mLevel": 35}


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, payload: str) -> None:
        self.published.append((topic, json.loads(payload)))


def make() -> tuple[SpiderFarmerMqtt, FakeClient, list]:
    received: list = []
    mqtt = SpiderFarmerMqtt("u", "p", 42, [DEVICE], on_message=lambda s, m: received.append((s, m)))
    client = FakeClient()
    mqtt._client = client  # type: ignore[assignment]
    return mqtt, client, received


def test_component_config_flat_and_nested() -> None:
    assert component_config({"blower": BLOWER}, "blower") == BLOWER
    assert component_config({"device": {"blower": BLOWER}}, "blower") == BLOWER
    assert component_config(None, "blower") == {}


def test_build_set_config_sends_full_object() -> None:
    cmd = build_set_config("S1", "42", "blower", BLOWER, {"mOnOff": 1})
    assert cmd["method"] == "setConfigField"
    assert cmd["params"]["keyPath"] == ["device", "blower"]
    assert cmd["params"]["blower"] == {**BLOWER, "mOnOff": 1}


def test_handle_updates_state_and_calls_back() -> None:
    mqtt, _, received = make()
    msg = {"method": "getDevSta", "pid": "S1", "code": 200, "data": {"sensor": {"temp": 20.9}}}
    mqtt._handle(DEVICE.up_topic, json.dumps(msg).encode())
    assert mqtt.states["S1"].dev == {"sensor": {"temp": 20.9}}
    assert received == [("S1", msg)]


def test_handle_ignores_garbage() -> None:
    mqtt, _, received = make()
    mqtt._handle(DEVICE.up_topic, b"\x00not json")
    assert received == []


async def test_request_publishes_on_down_topic() -> None:
    mqtt, client, _ = make()
    await mqtt.request("S1", "getDevSta")
    topic, payload = client.published[0]
    assert topic == "SF/GGS/PS5/API/DOWN/S1"
    assert payload["method"] == "getDevSta"
    assert payload["pid"] == "S1"
    assert payload["uid"] == "42"


async def test_set_component_merges_cached_config() -> None:
    mqtt, client, _ = make()
    mqtt.states["S1"].config = {"blower": dict(BLOWER), "fan": {"mOnOff": 0}}
    await mqtt.set_component("S1", "blower", {"mOnOff": 1, "mLevel": 40})
    _, payload = client.published[0]
    assert payload["params"]["blower"] == {**BLOWER, "mOnOff": 1, "mLevel": 40}
    assert mqtt.states["S1"].config["blower"]["mLevel"] == 40
    assert mqtt.states["S1"].config["fan"] == {"mOnOff": 0}
