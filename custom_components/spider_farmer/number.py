"""Circulation fan oscillation (`shakeLevel` 0–10) and the light's time window settings."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity, light_schedule


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
        if "light" in dev and light_schedule(state):
            entities.append(SpiderFarmerScheduleBrightness(coordinator, serial))
            entities.append(SpiderFarmerScheduleFade(coordinator, serial))
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
    """Brightness the light runs at during its time window."""

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
    def native_value(self) -> float | None:
        return (light_schedule(self.device_state) or {}).get("brightness")

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_light_schedule(brightness=int(value))


class SpiderFarmerScheduleFade(SpiderFarmerEntity, NumberEntity):
    """Sunrise/sunset: how long the light ramps up and down at the window's edges."""

    _attr_translation_key = "schedule_fade"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "light_schedule_fade")

    @property
    def native_value(self) -> float | None:
        seconds = (light_schedule(self.device_state) or {}).get("fadeTime")
        return None if seconds is None else seconds // 60

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_light_schedule(fadeTime=int(value) * 60)
