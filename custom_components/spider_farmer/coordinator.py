"""Coordinator: keeps the cloud MQTT connection and fans out device state."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COMMAND_TIMEOUT_SECONDS,
    CONF_DEVICES,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_USER_ID,
    CONFIG_REFRESH_SECONDS,
    DOMAIN,
    FIRST_DATA_TIMEOUT_SECONDS,
    OFFLINE_AFTER_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from .sfcloud import AuthError, CannotConnect, Device, DeviceState, SpiderFarmerMqtt
from .sfcloud.mqtt import GET_CONFIG_FILE, GET_DEV_STA, GET_SYS_STA

_LOGGER = logging.getLogger(__name__)

type SpiderFarmerConfigEntry = ConfigEntry[SpiderFarmerCoordinator]

_STATE_METHODS = (GET_DEV_STA, GET_SYS_STA, GET_CONFIG_FILE)


def devices_from_entry(entry: ConfigEntry) -> list[Device]:
    """Devices stored in the config entry (REST is only needed at setup, see D11)."""
    return [Device.from_api(raw) for raw in entry.data[CONF_DEVICES]]


class SpiderFarmerCoordinator(DataUpdateCoordinator[dict[str, DeviceState]]):
    """Push-driven: MQTT messages update the data; polling is only a fallback.

    Every push calls `async_set_updated_data`, which also reschedules the poll,
    so `_async_update_data` only runs when the device stops pushing.
    """

    config_entry: SpiderFarmerConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SpiderFarmerConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.devices = {d.serial: d for d in devices_from_entry(entry)}
        self.mqtt = SpiderFarmerMqtt(
            entry.data[CONF_MQTT_USERNAME],
            entry.data[CONF_MQTT_PASSWORD],
            entry.data[CONF_USER_ID],
            self.devices.values(),
            on_message=self._on_message,
            on_connection_change=self._on_connection_change,
        )
        self._last_seen: dict[str, float] = {}
        self._config_requested: dict[str, float] = {s: time.monotonic() for s in self.devices}
        self._first_data = asyncio.Event()

    async def async_start(self) -> None:
        """Connect and wait until every device reported its status once."""
        self.config_entry.async_create_background_task(
            self.hass, self._async_run(), f"{DOMAIN}_mqtt_{self.config_entry.entry_id}"
        )
        try:
            async with asyncio.timeout(FIRST_DATA_TIMEOUT_SECONDS):
                await self._first_data.wait()
        except TimeoutError as err:
            raise ConfigEntryNotReady("No status received from the Spider Farmer cloud") from err

    async def _async_run(self) -> None:
        try:
            await self.mqtt.run()
        except AuthError:
            _LOGGER.warning("Spider Farmer MQTT login rejected, re-authentication required")
            self.config_entry.async_start_reauth(self.hass)

    @callback
    def _on_connection_change(self, connected: bool) -> None:
        _LOGGER.debug("MQTT connected: %s", connected)
        if not connected and self.data is not None:
            self.async_update_listeners()

    @callback
    def _on_message(self, serial: str | None, msg: dict[str, Any]) -> None:
        if serial not in self.devices or msg.get("method") not in _STATE_METHODS:
            if serial is None:
                _LOGGER.debug("Account message: %s", msg)
            return
        now = time.monotonic()
        self._last_seen[serial] = now
        if now - self._config_requested.get(serial, now) > CONFIG_REFRESH_SECONDS:
            self._config_requested[serial] = now
            self.config_entry.async_create_background_task(
                self.hass, self.mqtt.request(serial, GET_CONFIG_FILE), f"{DOMAIN}_config_refresh"
            )
        if all(self.mqtt.states[s].dev is not None for s in self.devices):
            self._first_data.set()
        if self._first_data.is_set():
            self.async_set_updated_data(self.mqtt.states)

    async def _async_update_data(self) -> dict[str, DeviceState]:
        if not self.mqtt.connected:
            raise UpdateFailed("Not connected to the Spider Farmer cloud")
        for serial in self.devices:
            for method in _STATE_METHODS:
                await self.mqtt.request(serial, method)
        return self.mqtt.states

    async def async_set_config(
        self, serial: str, key_path: list[str], patch: dict[str, Any]
    ) -> None:
        """Send a config change; the device confirms by pushing its new state.

        The full sub-config is sent, so it is re-read first – otherwise changes
        made in the app since our last read would be overwritten.
        """
        try:
            await self.mqtt.query(serial, GET_CONFIG_FILE, timeout=COMMAND_TIMEOUT_SECONDS)
            await self.mqtt.set_config(serial, key_path, patch)
        except (CannotConnect, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        # Reflect the change right away; the device's push follows within seconds.
        self.async_update_listeners()

    def is_online(self, serial: str) -> bool:
        last = self._last_seen.get(serial)
        return (
            self.mqtt.connected
            and last is not None
            and time.monotonic() - last < OFFLINE_AFTER_SECONDS
        )
