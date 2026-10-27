"""Circulation fan oscillation level (`shakeLevel` 0–10, 0 = off)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SpiderFarmerOscillation(coordinator, serial)
        for serial, state in coordinator.mqtt.states.items()
        if "fan" in (state.dev or {})
    )


class SpiderFarmerOscillation(SpiderFarmerEntity, NumberEntity):
    _attr_translation_key = "oscillation"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "fan_oscillation")

    @property
    def native_value(self) -> float | None:
        return self.config("device", "fan").get("shakeLevel")

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_config(["device", "fan"], {"shakeLevel": int(value)})
