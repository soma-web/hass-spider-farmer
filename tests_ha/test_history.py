"""History import tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.spider_farmer.const import CONF_HISTORY_IMPORTED
from custom_components.spider_farmer.history import hourly_statistics
from custom_components.spider_farmer.sfcloud import AuthError

from .conftest import SERIAL, FakeBroker


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """The recorder must start before `hass`, so request it first in this module."""


def _sample(when: datetime, temp: str, humi: str = "60") -> dict[str, str]:
    return {
        "deviceSerialnum": SERIAL,
        "addTime": when.strftime("%m-%d-%Y %H:%M:%S"),
        "temp": temp,
        "humi": humi,
        "co2": None,
    }


def test_hourly_statistics_aggregates_and_cuts_off() -> None:
    base = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
    samples = [
        _sample(base, "20"),
        _sample(base + timedelta(minutes=5), "22"),
        _sample(base + timedelta(hours=1), "25"),
        _sample(base + timedelta(hours=2), "30"),  # not before the cutoff
        {"addTime": "garbage", "temp": "1"},
        _sample(base, ""),
    ]
    stats = hourly_statistics(samples, "temp", before=base + timedelta(hours=2))
    assert [s["start"] for s in stats] == [base, base + timedelta(hours=1)]
    assert stats[0]["mean"] == 21
    assert stats[0]["min"] == 20
    assert stats[0]["max"] == 22
    assert hourly_statistics(samples, "co2", before=base + timedelta(hours=3)) == []


async def test_import_on_first_setup(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    broker: list[FakeBroker],
) -> None:
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    rows = [_sample(hour, "20"), _sample(hour + timedelta(minutes=30), "24")]
    history = AsyncMock(side_effect=[rows, []])

    with patch("custom_components.spider_farmer.SpiderFarmerApi.get_sensor_history", history):
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    stats = await recorder_mock.async_add_executor_job(
        statistics_during_period,
        hass,
        hour - timedelta(hours=1),
        None,
        {"sensor.tent_temperature"},
        "hour",
        None,
        {"mean", "min", "max"},
    )
    rows_out = stats["sensor.tent_temperature"]
    assert len(rows_out) == 1
    assert rows_out[0]["mean"] == 22
    assert config_entry.data[CONF_HISTORY_IMPORTED] is True


async def test_import_skipped_when_token_replaced(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    broker: list[FakeBroker],
) -> None:
    history = AsyncMock(side_effect=AuthError("102", "registered remotely", "dr"))
    with patch("custom_components.spider_farmer.SpiderFarmerApi.get_sensor_history", history):
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Not marked as done, so it is retried after the next login.
    assert CONF_HISTORY_IMPORTED not in config_entry.data
