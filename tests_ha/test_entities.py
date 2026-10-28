"""Setup and entity tests against a fake broker."""

from __future__ import annotations

from unittest.mock import patch

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
    assert light["modeType"] == 0
    assert light["mOnOff"] == 1
    assert light["mLevel"] == 50
    assert light["timePeriod"][0]["brightness"] == 80

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.tent_light"}, blocking=True
    )
    light = broker[0].commands[-1]["light"]
    assert light["modeType"] == 0
    assert light["mOnOff"] == 0


async def test_light_mode_select(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)
    assert hass.states.get("select.tent_light_mode").state == "schedule"

    # Light is off (dark phase): switching to manual must not turn it on.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.tent_light_mode", "option": "manual"},
        blocking=True,
    )
    light = broker[0].commands[-1]["light"]
    assert light["modeType"] == 0
    assert light["mOnOff"] == 0
    assert light["mLevel"] == 16

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.tent_light_mode", "option": "schedule"},
        blocking=True,
    )
    light = broker[0].commands[-1]["light"]
    assert light["modeType"] == 1
    assert light["lastAutoModeType"] == 1


async def test_schedule_brightness_number(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)
    entity_id = "number.tent_light_target_brightness"
    assert hass.states.get(entity_id).state == "80"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 65}, blocking=True
    )
    light = broker[0].commands[-1]["light"]
    assert light["modeType"] == 1
    assert light["timePeriod"][0]["brightness"] == 65
    assert light["timePeriod"][0]["startTime"] == 64800


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


async def test_soil_probes_only_with_multiple_probes(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    from .conftest import DEV_STA

    probes = [
        {"id": "avg", "tempSoil": 20.5, "humiSoil": 50, "ECSoil": 1.0},
        {"id": "AA01", "type": 2, "tempSoil": 20.2, "humiSoil": 52.1, "ECSoil": 0.96},
        {"id": "AA02", "type": 2, "tempSoil": 20.8, "humiSoil": 47.9, "ECSoil": 1.04},
    ]
    with patch.dict(DEV_STA, {"sensors": probes}):
        await _setup(hass, config_entry)

    assert hass.states.get("sensor.tent_soil_moisture_aa02").state == "47.9"
    assert hass.states.get("sensor.tent_soil_ec_aa01").state == "0.96"


async def test_diagnostics_are_redacted(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    from custom_components.spider_farmer.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    from .conftest import EMAIL, SERIAL

    await _setup(hass, config_entry)
    result = await async_get_config_entry_diagnostics(hass, config_entry)

    text = str(result)
    assert SERIAL not in text
    assert EMAIL not in text
    assert "secret" not in text
    assert result["devices"]["device_1"]["state"]["dev"]["sensor"]["temp"] == 21.1


async def test_light_time_window_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, broker: list[FakeBroker]
) -> None:
    await _setup(hass, config_entry)
    assert hass.states.get("time.tent_light_on").state == "18:00:00"
    assert hass.states.get("time.tent_light_off").state == "06:00:00"
    assert float(hass.states.get("sensor.tent_light_duration").state) == 12
    assert hass.states.get("number.tent_light_sunrise_sunset").state == "20"

    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.tent_light_off", "time": "07:30"}, blocking=True
    )
    period = broker[0].commands[-1]["light"]["timePeriod"][0]
    assert period["endTime"] == 27000
    assert period["startTime"] == 64800
    assert period["brightness"] == 80

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.tent_light_sunrise_sunset", "value": 10},
        blocking=True,
    )
    assert broker[0].commands[-1]["light"]["timePeriod"][0]["fadeTime"] == 600
