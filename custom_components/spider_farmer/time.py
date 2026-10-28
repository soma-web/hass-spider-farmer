"""Start and end of the light's time window."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
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
    async_add_entities(
        SpiderFarmerScheduleTime(coordinator, serial, field)
        for serial, state in coordinator.mqtt.states.items()
        if light_schedule(state)
        for field in ("startTime", "endTime")
    )


class SpiderFarmerScheduleTime(SpiderFarmerEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str, field: str) -> None:
        key = "light_on_time" if field == "startTime" else "light_off_time"
        super().__init__(coordinator, serial, key)
        self._attr_translation_key = key
        self._field = field

    @property
    def native_value(self) -> time | None:
        seconds = (light_schedule(self.device_state) or {}).get(self._field)
        if seconds is None:
            return None
        seconds %= 86400
        return time(seconds // 3600, seconds % 3600 // 60)

    async def async_set_value(self, value: time) -> None:
        await self.async_set_light_schedule(**{self._field: value.hour * 3600 + value.minute * 60})
