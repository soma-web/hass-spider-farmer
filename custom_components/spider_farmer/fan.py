"""Exhaust fan (blower, 1–100 %) and circulation fan (10 levels, oscillation)."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity

CIRCULATION_LEVELS = (1, 10)
DEFAULT_SHAKE_LEVEL = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[FanEntity] = []
    for serial, state in coordinator.mqtt.states.items():
        dev = state.dev or {}
        if "blower" in dev:
            entities.append(SpiderFarmerBlower(coordinator, serial))
        if "fan" in dev:
            entities.append(SpiderFarmerCirculationFan(coordinator, serial))
    async_add_entities(entities)


class _SpiderFarmerFan(SpiderFarmerEntity, FanEntity):
    _component: str

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, self._component)
        self._attr_translation_key = self._component

    @property
    def is_on(self) -> bool | None:
        on = self.live(self._component).get("on")
        return None if on is None else on == 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode_type": self.config("device", self._component).get("modeType")}

    async def _async_send(self, patch: dict[str, Any]) -> None:
        await self.async_set_config(["device", self._component], patch)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send({"mOnOff": 0})

    def _level_for(self, percentage: int) -> int:
        raise NotImplementedError

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._async_send({"mOnOff": 1, "mLevel": self._level_for(percentage)})

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        if percentage:
            await self.async_set_percentage(percentage)
        else:
            await self._async_send({"mOnOff": 1})


class SpiderFarmerBlower(_SpiderFarmerFan):
    """Inline exhaust fan; level is a percentage."""

    _component = "blower"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )

    @property
    def percentage(self) -> int | None:
        status = self.live("blower")
        if status.get("on") == 0:
            return 0
        return status.get("level")

    def _level_for(self, percentage: int) -> int:
        return max(1, min(100, percentage))


class SpiderFarmerCirculationFan(_SpiderFarmerFan):
    """Clip/circulation fan with levels 1–10 and oscillation (`shakeLevel` 0–10)."""

    _component = "fan"
    _attr_speed_count = CIRCULATION_LEVELS[1]
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.OSCILLATE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._last_shake_level = DEFAULT_SHAKE_LEVEL

    @property
    def percentage(self) -> int | None:
        status = self.live("fan")
        if status.get("on") == 0:
            return 0
        level = status.get("level")
        return None if level is None else ranged_value_to_percentage(CIRCULATION_LEVELS, level)

    def _level_for(self, percentage: int) -> int:
        return math.ceil(percentage_to_ranged_value(CIRCULATION_LEVELS, percentage))

    @property
    def oscillating(self) -> bool | None:
        shake = self.config("device", "fan").get("shakeLevel")
        if shake:
            self._last_shake_level = shake
        return None if shake is None else shake > 0

    async def async_oscillate(self, oscillating: bool) -> None:
        await self._async_send({"shakeLevel": self._last_shake_level if oscillating else 0})
