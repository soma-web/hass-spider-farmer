"""Import the cloud sensor history into Home Assistant's long-term statistics.

The cloud keeps 5-minute samples (`dr/getDeviceTHPData`, UTC timestamps, string
values). They are aggregated to hourly mean/min/max and imported for the hours
before the integration was set up, so the history graphs don't start empty.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN, HISTORY_DAYS
from .sensor import SENSORS
from .sfcloud import SpiderFarmerApi

_LOGGER = logging.getLogger(__name__)

# History field -> sensor description key.
HISTORY_FIELDS = {
    "temp": "temperature",
    "humi": "humidity",
    "vpd": "vpd",
    "ppfd": "ppfd",
    "co2": "co2",
    "tempSoil": "soil_temperature",
    "humiSoil": "soil_moisture",
    "ecSoil": "soil_ec",
}

_TIME_FORMAT = "%m-%d-%Y %H:%M:%S"


def _parse_time(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, _TIME_FORMAT).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _parse_value(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def hourly_statistics(
    samples: Iterable[dict[str, Any]], field: str, before: datetime
) -> list[StatisticData]:
    """Aggregate samples of `field` into hourly mean/min/max for hours before `before`."""
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for sample in samples:
        when = _parse_time(sample.get("addTime"))
        value = _parse_value(sample.get(field))
        if when is None or value is None:
            continue
        hour = when.replace(minute=0, second=0, microsecond=0)
        if hour < before:
            buckets[hour].append(value)
    return [
        StatisticData(start=hour, mean=sum(values) / len(values), min=min(values), max=max(values))
        for hour, values in sorted(buckets.items())
    ]


async def async_fetch_history(
    api: SpiderFarmerApi, serial: str, until: datetime, days: int = HISTORY_DAYS
) -> list[dict[str, Any]]:
    """Fetch up to `days` days of samples ending at `until`; stops at the first empty day."""
    samples: list[dict[str, Any]] = []
    for day in range(days):
        end = until - timedelta(days=day)
        rows = await api.get_sensor_history(
            serial, end - timedelta(days=1), end - timedelta(seconds=1)
        )
        if not rows:
            break
        samples.extend(rows)
    return samples


async def async_import_history(
    hass: HomeAssistant, api: SpiderFarmerApi, serials: Iterable[str]
) -> None:
    """Import the cloud history of all devices into the recorder statistics."""
    registry = er.async_get(hass)
    descriptions = {d.key: d for d in SENSORS}
    # Only full hours before now: HA records everything after setup itself.
    before = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)

    for serial in serials:
        samples = await async_fetch_history(api, serial, before)
        _LOGGER.debug("Fetched %s history samples for %s", len(samples), serial)
        for field, key in HISTORY_FIELDS.items():
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{serial}_{key}")
            if entity_id is None:
                continue
            statistics = hourly_statistics(samples, field, before)
            if not statistics:
                continue
            description = descriptions[key]
            converter = UNIT_CONVERTERS.get(description.device_class)
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.ARITHMETIC,
                has_sum=False,
                name=None,
                source="recorder",
                statistic_id=entity_id,
                unit_class=converter.UNIT_CLASS if converter else None,
                unit_of_measurement=description.native_unit_of_measurement,
            )
            async_import_statistics(hass, metadata, statistics)
            _LOGGER.debug("Imported %s hours of history for %s", len(statistics), entity_id)
