"""Connectivity binary sensor for Spider Farmer devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry
from .entity import SpiderFarmerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SpiderFarmerOnline(coordinator, serial) for serial in coordinator.devices)


class SpiderFarmerOnline(SpiderFarmerEntity, BinarySensorEntity):
    """Whether the controller is reachable through the cloud."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, serial: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(coordinator, serial, "online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_online(self._serial)
