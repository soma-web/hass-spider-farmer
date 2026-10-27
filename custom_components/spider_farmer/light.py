"""Grow light with brightness (level 0–100 %)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity

LEVEL_RANGE = (1, 100)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SpiderFarmerLight(coordinator, serial)
        for serial, state in coordinator.mqtt.states.items()
        if "light" in (state.dev or {})
    )


class SpiderFarmerLight(SpiderFarmerEntity, LightEntity):
    """Light on the controller's light port. Controls the manual level (`mOnOff`/`mLevel`)."""

    _attr_translation_key = "light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: SpiderFarmerCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "light")

    @property
    def _level(self) -> int | None:
        return self.live("light").get("level")

    @property
    def is_on(self) -> bool | None:
        level = self._level
        return None if level is None else level > 0

    @property
    def brightness(self) -> int | None:
        level = self._level
        return value_to_brightness(LEVEL_RANGE, level) if level else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode_type": self.config("device", "light").get("modeType")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        patch: dict[str, Any] = {"mOnOff": 1}
        if ATTR_BRIGHTNESS in kwargs:
            patch["mLevel"] = max(
                1, round(brightness_to_value(LEVEL_RANGE, kwargs[ATTR_BRIGHTNESS]))
            )
        elif not self.config("device", "light").get("mLevel"):
            patch["mLevel"] = LEVEL_RANGE[1]
        await self.async_set_config(["device", "light"], patch)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_config(["device", "light"], {"mOnOff": 0})
