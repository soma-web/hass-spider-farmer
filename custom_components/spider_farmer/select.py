"""Light mode (`modeType`): manual, schedule (time window) or PPFD."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LIGHT_MODES, MODE_MANUAL
from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity

MODE_BY_OPTION = {option: mode for mode, option in LIGHT_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SpiderFarmerLightMode(coordinator, serial)
        for serial, state in coordinator.mqtt.states.items()
        if "light" in (state.dev or {})
    )


class SpiderFarmerLightMode(SpiderFarmerEntity, SelectEntity):
    # Not a config entity: it is the everyday way back to the schedule, so it belongs
    # on the dashboard next to the light.
    _attr_translation_key = "light_mode"
    _attr_options = list(LIGHT_MODES.values())

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "light_mode")

    @property
    def current_option(self) -> str | None:
        return LIGHT_MODES.get(self.config("device", "light").get("modeType"))

    async def async_select_option(self, option: str) -> None:
        mode = MODE_BY_OPTION[option]
        patch: dict[str, Any] = {"modeType": mode}
        if mode == MODE_MANUAL:
            # Keep the light as it is right now instead of jumping to the stored manual level,
            # e.g. don't switch it on during the dark phase.
            level = self.live("light").get("level") or 0
            patch["mOnOff"] = 1 if level > 0 else 0
            if level > 0:
                patch["mLevel"] = level
        else:
            patch["lastAutoModeType"] = mode
        await self.async_set_config(["device", "light"], patch)
