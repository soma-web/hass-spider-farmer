"""Base entity for Spider Farmer."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SpiderFarmerCoordinator
from .sfcloud import DeviceState


class SpiderFarmerEntity(CoordinatorEntity[SpiderFarmerCoordinator]):
    """An entity belonging to one Spider Farmer device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str, key: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{serial}_{key}"
        device = coordinator.devices[serial]
        sys = coordinator.mqtt.states[serial].sys or {}
        sys = sys.get("sys", sys)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=device.product_type,
            serial_number=serial,
            sw_version=sys.get("ver") or device.hardware_version,
            hw_version=sys.get("hwver"),
        )

    @property
    def device_state(self) -> DeviceState:
        return self.coordinator.mqtt.states[self._serial]

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.is_online(self._serial)
