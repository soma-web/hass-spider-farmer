"""Power strip outlets (O1–O5) as switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity

OUTLETS = ("O1", "O2", "O3", "O4", "O5")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SpiderFarmerOutlet(coordinator, serial, outlet)
        for serial, state in coordinator.mqtt.states.items()
        for outlet in OUTLETS
        if outlet in ((state.dev or {}).get("outlet") or {})
    )


class SpiderFarmerOutlet(SpiderFarmerEntity, SwitchEntity):
    """One outlet. Switching sends `mOnOff` like the app's manual control."""

    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_translation_key = "outlet"

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str, outlet: str) -> None:
        super().__init__(coordinator, serial, f"outlet_{outlet.lower()}")
        self._outlet = outlet
        self._attr_translation_placeholders = {"number": outlet[1:]}

    @property
    def is_on(self) -> bool | None:
        on = self.live("outlet", self._outlet).get("on")
        return None if on is None else on == 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Raw controller mode (0 = manual as observed; others: schedule/cycle/…).
        return {"mode_type": self.config("outlet", self._outlet).get("modeType")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_set_config(["outlet", self._outlet], {"mOnOff": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_config(["outlet", self._outlet], {"mOnOff": 0})
