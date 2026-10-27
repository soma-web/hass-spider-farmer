"""Diagnostics download (credentials and identifiers redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .const import CONF_MQTT_PASSWORD, CONF_MQTT_USERNAME, CONF_TOKEN, CONF_USER_ID
from .coordinator import SpiderFarmerConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_TOKEN,
    CONF_USER_ID,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    "deviceSerialnum",
    "deviceName",
    "deviceImg",
    "deviceIp",
    "userId",
    "uid",
    "pid",
    "id",
    "belonginRroom",
    "country",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SpiderFarmerConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = {}
    for index, (serial, state) in enumerate(coordinator.mqtt.states.items(), start=1):
        device = coordinator.devices[serial]
        devices[f"device_{index}"] = {
            "product_type": device.product_type,
            "online": coordinator.is_online(serial),
            "state": asdict(state),
        }
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "mqtt_connected": coordinator.mqtt.connected,
            "devices": devices,
        },
        TO_REDACT,
    )
