"""Data models for the Spider Farmer cloud API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LoginResult:
    """Credentials returned by `ulogin/mailLogin`."""

    token: str
    user_id: int
    mqtt_username: str
    mqtt_password: str
    nick_name: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> LoginResult:
        return cls(
            token=data["token"],
            user_id=int(data["userId"]),
            mqtt_username=data["mqttName"],
            mqtt_password=data["mqttPwd"],
            nick_name=data.get("nickName"),
        )


def topic_prefix(product_type: str) -> str:
    """MQTT topic prefix for a product type, e.g. "SF-GGS-PS5" -> "SF/GGS/PS5"."""
    return product_type.replace("-", "/")


@dataclass(slots=True)
class Device:
    """A device from `udm/getDeviceList`."""

    serial: str
    name: str
    product_type: str
    hardware_version: str | None
    online: bool
    room_id: int | None
    info: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any], room_id: int | None = None) -> Device:
        info = data.get("deviceInfo") or {}
        if isinstance(info, str):  # arrives as a JSON string
            try:
                info = json.loads(info)
            except json.JSONDecodeError:
                info = {}
        return cls(
            serial=data["deviceSerialnum"],
            name=data.get("deviceName") or data["deviceSerialnum"],
            product_type=data.get("productType") or "",
            hardware_version=data.get("hardwareVersion"),
            online=data.get("connectStatus") == 1,
            room_id=room_id,
            info=info,
            raw=data,
        )

    @property
    def up_topic(self) -> str:
        return f"{topic_prefix(self.product_type)}/API/UP/{self.serial}"

    @property
    def down_topic(self) -> str:
        return f"{topic_prefix(self.product_type)}/API/DOWN/{self.serial}"
