"""Circulation fan oscillation (`shakeLevel` 0–10) and the light schedule's target brightness."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity
from .sfcloud.mqtt import config_at


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for serial, state in coordinator.mqtt.states.items():
        dev = state.dev or {}
        if "fan" in dev:
            entities.append(SpiderFarmerOscillation(coordinator, serial))
        if "light" in dev and config_at(state.config, ["device", "light"]).get("timePeriod"):
            entities.append(SpiderFarmerScheduleBrightness(coordinator, serial))
    async_add_entities(entities)


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


class SpiderFarmerScheduleBrightness(SpiderFarmerEntity, NumberEntity):
    """Brightness the light runs at during its time window (first `timePeriod` entry)."""

    _attr_translation_key = "schedule_brightness"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "light_schedule_brightness")

    @property
    def _periods(self) -> list[dict]:
        return self.config("device", "light").get("timePeriod") or []

    @property
    def native_value(self) -> float | None:
        periods = self._periods
        return periods[0].get("brightness") if periods else None

    async def async_set_native_value(self, value: float) -> None:
        periods = [dict(p) for p in self._periods]
        if not periods:
            return
        periods[0]["brightness"] = int(value)
        await self.async_set_config(["device", "light"], {"timePeriod": periods})
