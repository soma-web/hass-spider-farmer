"""Setup and entity tests against a fake broker."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeBroker


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.tent_temperature").state == "21.1"
    assert hass.states.get("sensor.tent_humidity").state == "59.8"
    assert hass.states.get("sensor.tent_soil_ec").state == "0.96"
    assert hass.states.get("binary_sensor.tent_connectivity").state == "on"
    # No CO2 sensor attached -> no entity.
    assert hass.states.get("sensor.tent_carbon_dioxide") is None


async def test_controls_state(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)

    assert hass.states.get("switch.tent_outlet_1").state == "on"
    assert hass.states.get("switch.tent_outlet_3").state == "off"
    blower = hass.states.get("fan.tent_exhaust_fan")
    assert blower.state == "on"
    assert blower.attributes["percentage"] == 37
    fan = hass.states.get("fan.tent_circulation_fan")
    assert fan.attributes["percentage"] == 20
    assert fan.attributes["oscillating"] is False
    assert hass.states.get("light.tent_light").state == "off"


async def test_switch_sends_full_outlet_config(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.tent_outlet_3"}, blocking=True
    )
    assert broker[0].commands[-1] == {
        "keyPath": ["outlet", "O3"],
        "O3": {"modeType": 0, "tempAdd": 1, "humiAdd": 1, "mOnOff": 1},
    }


async def test_command_uses_fresh_config(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    """Changes made in the app must not be overwritten by a stale cache."""
    await _setup(hass, config_entry)
    broker[0].config["configFile"]["device"]["fan"]["shakeLevel"] = 7  # changed in the app

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.tent_circulation_fan", "percentage": 50},
        blocking=True,
    )
    sent = broker[0].commands[-1]["fan"]
    assert sent["mLevel"] == 5
    assert sent["shakeLevel"] == 7


async def test_blower_and_light_commands(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.tent_exhaust_fan", "percentage": 0},
        blocking=True,
    )
    assert broker[0].commands[-1]["blower"]["mOnOff"] == 0

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.tent_light", "brightness_pct": 50},
        blocking=True,
    )
    light = broker[0].commands[-1]["light"]
    assert light["mOnOff"] == 1
    assert light["mLevel"] == 50


async def test_oscillation_number(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.tent_oscillation", "value": 4},
        blocking=True,
    )
    assert broker[0].commands[-1]["fan"]["shakeLevel"] == 4


async def test_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
