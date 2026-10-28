"""The Spider Farmer integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HISTORY_IMPORTED, CONF_TOKEN
from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .sfcloud import SpiderFarmerApi, SpiderFarmerError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: SpiderFarmerConfigEntry) -> bool:
    """Set up Spider Farmer from a config entry."""
    coordinator = SpiderFarmerCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not entry.data.get(CONF_HISTORY_IMPORTED) and "recorder" in hass.config.components:
        entry.async_create_background_task(
            hass, _async_import_history(hass, entry), "spider_farmer_history_import"
        )
    return True


async def _async_import_history(hass: HomeAssistant, entry: SpiderFarmerConfigEntry) -> None:
    """One-time import right after login, while the REST token is still valid (D11)."""
    # Imported here because it needs the recorder, which is only an after_dependency.
    from .history import async_import_history

    api = SpiderFarmerApi(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    try:
        await async_import_history(hass, api, entry.runtime_data.devices)
    except SpiderFarmerError as err:
        # Typically the app logged in meanwhile (token replaced). Not worth a reauth:
        # the import is retried on the next start, e.g. after a reauth.
        _LOGGER.info("Spider Farmer history import skipped: %s", err)
        return
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HISTORY_IMPORTED: True})


async def async_unload_entry(hass: HomeAssistant, entry: SpiderFarmerConfigEntry) -> bool:
    """Unload a config entry (the MQTT task is cancelled with the entry)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
