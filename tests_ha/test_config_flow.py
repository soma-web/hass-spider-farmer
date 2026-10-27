"""Config flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spider_farmer.const import CONF_DEVICES, CONF_TOKEN, DOMAIN
from custom_components.spider_farmer.sfcloud import ApiError, Device, LoginResult

from .conftest import DEVICE_RAW, EMAIL, USER_ID

API = "custom_components.spider_farmer.config_flow.SpiderFarmerApi"
LOGIN = LoginResult(token="new-token", user_id=USER_ID, mqtt_username=EMAIL, mqtt_password="pw")


def _mock_api(api: AsyncMock) -> None:
    api.return_value.request_email_code = AsyncMock()
    api.return_value.login = AsyncMock(return_value=LOGIN)
    api.return_value.get_all_devices = AsyncMock(return_value=[Device.from_api(DEVICE_RAW)])


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    with (
        patch(API) as api,
        patch("custom_components.spider_farmer.async_setup_entry", return_value=True),
    ):
        _mock_api(api)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": f" {EMAIL} "}
        )
        assert result["step_id"] == "code"
        api.return_value.request_email_code.assert_awaited_once_with(EMAIL)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "123456"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["result"].unique_id == str(USER_ID)
    assert result["data"][CONF_TOKEN] == "new-token"
    assert result["data"][CONF_DEVICES][0]["deviceSerialnum"] == DEVICE_RAW["deviceSerialnum"]


async def test_invalid_code_shows_error(hass: HomeAssistant) -> None:
    with patch(API) as api:
        _mock_api(api)
        api.return_value.login.side_effect = ApiError("201", "bad code", "ulogin/mailLogin/v2")
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"email": EMAIL})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "000000"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_code"}


async def test_reauth_updates_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    with (
        patch(API) as api,
        patch("custom_components.spider_farmer.async_setup_entry", return_value=True),
    ):
        _mock_api(api)
        result = await config_entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "code"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "123456"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "new-token"
