"""Sensors for Spider Farmer (climate, soil, diagnostics)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfConductivity,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpiderFarmerConfigEntry, SpiderFarmerCoordinator
from .entity import SpiderFarmerEntity
from .sfcloud import DeviceState


def _climate(key: str) -> Callable[[DeviceState], Any]:
    return lambda state: ((state.dev or {}).get("sensor") or {}).get(key)


def _sys(state: DeviceState) -> dict[str, Any]:
    sys = state.sys or {}
    return sys.get("sys", sys)


@dataclass(frozen=True, kw_only=True)
class SpiderFarmerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DeviceState], Any]
    # Climate sensors only exist if the controller reports the value at all.
    climate_key: str | None = None


SENSORS: tuple[SpiderFarmerSensorDescription, ...] = (
    SpiderFarmerSensorDescription(
        key="temperature",
        climate_key="temp",
        value_fn=_climate("temp"),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="humidity",
        climate_key="humi",
        value_fn=_climate("humi"),
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="vpd",
        translation_key="vpd",
        climate_key="vpd",
        value_fn=_climate("vpd"),
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SpiderFarmerSensorDescription(
        key="ppfd",
        translation_key="ppfd",
        climate_key="ppfd",
        value_fn=_climate("ppfd"),
        native_unit_of_measurement="µmol/m²/s",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="co2",
        climate_key="co2",
        value_fn=_climate("co2"),
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="soil_temperature",
        translation_key="soil_temperature",
        climate_key="tempSoil",
        value_fn=_climate("tempSoil"),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="soil_moisture",
        translation_key="soil_moisture",
        climate_key="humiSoil",
        value_fn=_climate("humiSoil"),
        device_class=SensorDeviceClass.MOISTURE,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SpiderFarmerSensorDescription(
        key="soil_ec",
        translation_key="soil_ec",
        climate_key="ECSoil",
        value_fn=_climate("ECSoil"),
        device_class=SensorDeviceClass.CONDUCTIVITY,
        native_unit_of_measurement=UnitOfConductivity.MILLISIEMENS_PER_CM,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SpiderFarmerSensorDescription(
        key="wifi_signal",
        value_fn=lambda state: (_sys(state).get("wifi") or {}).get("rssi"),
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SpiderFarmerSensorDescription(
        key="uptime",
        translation_key="uptime",
        value_fn=lambda state: _sys(state).get("upTime"),
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpiderFarmerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for serial, state in coordinator.mqtt.states.items():
        reported = (state.dev or {}).get("sensor") or {}
        entities.extend(
            SpiderFarmerSensor(coordinator, serial, description)
            for description in SENSORS
            if description.climate_key is None or description.climate_key in reported
        )
        # Individual soil probes; with a single probe they equal the averages above.
        probes = soil_probes(state)
        if len(probes) > 1:
            entities.extend(
                SpiderFarmerProbeSensor(coordinator, serial, probe_id, description)
                for probe_id, values in probes.items()
                for description in PROBE_SENSORS
                if description.climate_key in values
            )
    async_add_entities(entities)


def soil_probes(state: DeviceState) -> dict[str, dict[str, Any]]:
    """Soil probes from getDevSta `sensors[]` by id (e.g. "AA01"), without the average."""
    return {
        str(entry["id"]): entry
        for entry in (state.dev or {}).get("sensors") or []
        if isinstance(entry, dict) and entry.get("id") not in (None, "avg")
    }


# Per-probe variants of the soil sensors.
PROBE_SENSORS = tuple(
    dataclasses.replace(description, translation_key=f"probe_{description.key}")
    for description in SENSORS
    if description.key in ("soil_temperature", "soil_moisture", "soil_ec")
)


class SpiderFarmerSensor(SpiderFarmerEntity, SensorEntity):
    entity_description: SpiderFarmerSensorDescription

    def __init__(
        self,
        coordinator: SpiderFarmerCoordinator,
        serial: str,
        description: SpiderFarmerSensorDescription,
    ) -> None:
        super().__init__(coordinator, serial, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device_state)


class SpiderFarmerProbeSensor(SpiderFarmerEntity, SensorEntity):
    """One value of one soil probe."""

    entity_description: SpiderFarmerSensorDescription

    def __init__(
        self,
        coordinator: SpiderFarmerCoordinator,
        serial: str,
        probe_id: str,
        description: SpiderFarmerSensorDescription,
    ) -> None:
        super().__init__(coordinator, serial, f"probe_{probe_id.lower()}_{description.key}")
        self.entity_description = description
        self._probe_id = probe_id
        self._attr_translation_placeholders = {"probe": probe_id}

    @property
    def native_value(self) -> Any:
        probe = soil_probes(self.device_state).get(self._probe_id) or {}
        return probe.get(self.entity_description.climate_key)
