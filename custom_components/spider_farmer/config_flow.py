"""Config flow for Spider Farmer: e-mail -> one-time code -> done."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_CODE, CONF_EMAIL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICES,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_TOKEN,
    CONF_USER_ID,
    DOMAIN,
)
from .sfcloud import ApiError, CannotConnect, SpiderFarmerApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str})
STEP_CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class SpiderFarmerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in with the e-mail one-time code, like the app does."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._api: SpiderFarmerApi | None = None

    async def _async_send_code(self, email: str) -> str | None:
        """Request a code; returns an error key or None."""
        self._api = SpiderFarmerApi(async_get_clientsession(self.hass))
        try:
            await self._api.request_email_code(email)
        except CannotConnect:
            return "cannot_connect"
        except ApiError as err:
            _LOGGER.debug("Requesting a code failed: %s", err)
            return "send_code_failed"
        self._email = email
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            if not (error := await self._async_send_code(email)):
                return await self.async_step_code()
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._email is not None
        if user_input is not None:
            if not (error := await self._async_send_code(self._email)):
                return await self.async_step_code()
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"email": self._email},
            errors=errors,
        )

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._api is not None and self._email is not None
        if user_input is not None:
            try:
                login = await self._api.login(self._email, user_input[CONF_CODE].strip())
                devices = await self._api.get_all_devices(login.user_id)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ApiError as err:
                _LOGGER.debug("Login failed: %s", err)
                errors["base"] = "invalid_code"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                if not devices:
                    return self.async_abort(reason="no_devices")
                await self.async_set_unique_id(str(login.user_id))
                data = {
                    CONF_EMAIL: self._email,
                    CONF_TOKEN: login.token,
                    CONF_USER_ID: login.user_id,
                    CONF_MQTT_USERNAME: login.mqtt_username,
                    CONF_MQTT_PASSWORD: login.mqtt_password,
                    # Stored so the integration runs on MQTT alone (D11).
                    CONF_DEVICES: [d.raw for d in devices],
                }
                if self.source == SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=self._email, data=data)

        return self.async_show_form(
            step_id="code",
            data_schema=STEP_CODE_SCHEMA,
            description_placeholders={"email": self._email},
            errors=errors,
        )
